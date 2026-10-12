"""역할 5개(bi_service, bi_guest_issuer, bi_author, bi_author_schema, bi_guest)를 멱등으로 맞춘다.

- 권한 목록은 bi_roles.py 한 곳에 있다. 비밀번호는 다루지 않는다.
- bi_service, bi_guest_issuer, bi_author_schema, bi_guest: 매 기동 `없으면 생성 -> 권한 목록 통째 교체 -> 커밋 -> 재읽기 비교`.
  목록의 권한(PermissionView)이 하나라도 Superset에 없으면 아무것도 바꾸지 않고 전체 실패한다.
  (schema_access 항목은 sync_permissions.py가 먼저 만든다. 항목 이름은 DATABASE_NAME과 POSTGRES_DB로 조립한다.)
  새 권한은 자동으로 추가하지 않는다(목록에 없는 권한은 통째 교체로 제거된다).
- guest 불변식(고치지 않고 실패한다, 아무것도 바꾸기 전에 확인한다): 실제 적용된 설정 `GUEST_ROLE_NAME`이 bi_roles.GUEST_ROLE과
  같다(이름 단일 출처 확인), `PUBLIC_ROLE_LIKE` 미설정, `Public` 역할의 권한 0개. bi_guest 목록에 금지 권한(내보내기·쓰기·
  Explore·SQL Lab·데이터 접근 계열, bi_roles.forbidden_reason)이 있으면 실패한다.
- bi_author(Gamma 복사본): **처음 만들 때만** 내장 Gamma의 권한을 복사한다(add_role로 역할과 권한을 한 번에 넣는다).
  그 뒤에는 Gamma와의 차이를 로그로 알리기만 하고 권한은 바꾸지 않는다(권한이 0개여도 되살리지 않는다.
  사람이 비워 둔 역할일 수 있어 다시 복사하면 권한 확대가 된다. 0개이면 "점검 필요" 로그만 남긴다)(superset init은 Gamma에만 새 권한을 더하고 복사본은 갱신하지 않는다).
  차이가 알려지면 사람이 확인하고 처리 여부를 결정한다(docs/deploy-coordination.md).
Superset 내부 코드는 수정하지 않는다. 로그에는 역할 이름과 권한 개수(그리고 bi_author 차이의 권한 이름)만 출력한다.
"""

import os
import sys

from bi_roles import (
    AUTHOR_ROLE,
    GAMMA_ROLE,
    GUEST_ROLE,
    ROLE_PERMISSIONS,
    forbidden_reason,
    resolve,
)
from superset.app import create_app

postgres_db = os.environ.get("POSTGRES_DB", "")
if not postgres_db:
    print("[superset-init] POSTGRES_DB가 필요합니다.", file=sys.stderr)
    sys.exit(1)


def fail(message: str) -> None:
    print(f"[superset-init] {message}", file=sys.stderr)
    sys.exit(1)


def pairs(role) -> set:
    return {(pv.permission.name, pv.view_menu.name) for pv in role.permissions}


def label(pair) -> str:
    return f"{pair[0]} {pair[1]}"


app = create_app()
with app.app_context():
    sm = app.appbuilder.sm

    # 0) guest 불변식. 설정은 superset_config.py가 아니라 실제 적용된 app.config로 확인한다.
    #    하나라도 어긋나면 아무것도 바꾸지 않고 실패한다(자동으로 고치지 않는다).
    applied_guest_role = app.config.get("GUEST_ROLE_NAME")
    if applied_guest_role != GUEST_ROLE:
        fail(
            f"설정 GUEST_ROLE_NAME이 {GUEST_ROLE}이(가) 아닙니다(superset_config.py와 bi_roles.GUEST_ROLE이 어긋남). "
            "guest 입장권이 다른 역할로 동작하게 되므로 중단합니다."
        )
    if app.config.get("PUBLIC_ROLE_LIKE"):
        fail("설정 PUBLIC_ROLE_LIKE가 설정되어 있습니다. Public 역할이 권한을 갖게 되므로 설정하지 마세요.")
    public_role = sm.find_role(sm.auth_role_public)
    if public_role is None:
        fail(f"{sm.auth_role_public} 역할이 없어 권한 0개를 확인할 수 없습니다(superset init 뒤에 실행해야 합니다).")
    if len(public_role.permissions) != 0:
        fail(
            f"{sm.auth_role_public} 역할의 권한이 {len(public_role.permissions)}개입니다(0개여야 합니다). "
            "자동으로 고치지 않으므로 원인을 확인하고 관리자가 비운 뒤 다시 실행하세요."
        )

    # 1) 모든 목록의 권한을 먼저 찾는다. 하나라도 없으면 아무것도 바꾸지 않고 실패한다.
    resolved = {}
    missing = []
    for role_name, entries in ROLE_PERMISSIONS.items():
        wanted = resolve(entries, postgres_db)
        for pair in wanted:
            reason = forbidden_reason(role_name, pair)
            if reason is not None:
                fail(f"{role_name}의 권한 목록에 금지된 권한이 있습니다: {label(pair)} ({reason})")
        views = []
        for pair in wanted:
            pvm = sm.find_permission_view_menu(*pair)
            if pvm is None:
                missing.append(f"{role_name}: {label(pair)}")
            else:
                views.append(pvm)
        resolved[role_name] = (wanted, views)
    if missing:
        for item in missing:
            print(f"[superset-init] 없는 권한: {item}", file=sys.stderr)
        fail(
            "권한 목록에 Superset에 없는 항목이 있어 역할을 만들지 않습니다"
            "(schema_access라면 sync_permissions 단계와 업무 데이터 연결 이름을 확인하세요)."
        )

    # 2) 목록 역할: 목록으로 통째 교체하고 재읽기로 비교한다.
    for role_name, (wanted, views) in resolved.items():
        role = sm.find_role(role_name) or sm.add_role(role_name, views)
        if role is None:
            fail(f"역할 {role_name}을(를) 만들지 못했습니다.")
        role.permissions = views
        try:
            sm.session.commit()  # pylint: disable=consider-using-transaction
        except Exception as exc:
            sm.session.rollback()  # pylint: disable=consider-using-transaction
            fail(f"역할 {role_name} 저장에 실패했습니다: {type(exc).__name__}")
        sm.session.expire_all()
        stored = sm.find_role(role_name)
        if stored is None or pairs(stored) != set(wanted) or len(stored.permissions) != len(wanted):
            fail(f"역할 {role_name}의 권한이 목록과 다릅니다(재읽기 비교 실패).")
        print(f"[superset-init] 역할 {role_name}: 권한 {len(wanted)}개 적용")

    # 3) bi_author: 처음 만들 때만 Gamma 권한을 복사한다. 이후에는 차이를 알리기만 한다.
    gamma = sm.find_role(GAMMA_ROLE)
    if gamma is None or not gamma.permissions:
        fail(f"내장 역할 {GAMMA_ROLE}이(가) 없거나 권한이 없습니다(superset init 뒤에 실행해야 합니다).")
    author = sm.find_role(AUTHOR_ROLE)
    if author is None:
        # 처음 만들 때만 Gamma 권한을 복사한다(역할과 권한을 한 번에 넣는다).
        author = sm.add_role(AUTHOR_ROLE, list(gamma.permissions))
        if author is None:
            fail(f"역할 {AUTHOR_ROLE}을(를) 만들지 못했습니다.")
        sm.session.expire_all()
        author = sm.find_role(AUTHOR_ROLE)
        gamma = sm.find_role(GAMMA_ROLE)
        if author is None or pairs(author) != pairs(gamma):
            fail(f"역할 {AUTHOR_ROLE}의 Gamma 권한 복사가 맞지 않습니다.")
        print(f"[superset-init] 역할 {AUTHOR_ROLE}: 새로 만들고 {GAMMA_ROLE} 권한 {len(pairs(author))}개를 복사")
    else:
        if not author.permissions:
            # 되살리지 않는다(사람이 비워 둔 역할일 수 있다). 알리기만 하고 계속한다.
            print(f"[superset-init] 점검 필요: 역할 {AUTHOR_ROLE}의 권한이 0개입니다. 권한은 바꾸지 않았습니다.")
        only_gamma = sorted(pairs(gamma) - pairs(author))
        only_author = sorted(pairs(author) - pairs(gamma))
        if not only_gamma and not only_author:
            print(f"[superset-init] 역할 {AUTHOR_ROLE}: {GAMMA_ROLE}와 차이 없음(권한 {len(pairs(author))}개)")
        else:
            # 권한은 바꾸지 않는다. 사람이 확인하고 처리 여부를 정한다.
            print(
                f"[superset-init] 점검 필요: 역할 {AUTHOR_ROLE}이(가) {GAMMA_ROLE}와 다릅니다 "
                f"({GAMMA_ROLE}에만 {len(only_gamma)}개, {AUTHOR_ROLE}에만 {len(only_author)}개). 권한은 바꾸지 않았습니다."
            )
            for pair in only_gamma:
                print(f"[superset-init]   {GAMMA_ROLE}에만 있음: {label(pair)}")
            for pair in only_author:
                print(f"[superset-init]   {AUTHOR_ROLE}에만 있음: {label(pair)}")
print("[superset-init] 역할 확인 완료")
