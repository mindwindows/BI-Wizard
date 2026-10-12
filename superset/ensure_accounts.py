"""서비스 계정과 발급 전용 계정을 멱등으로 맞춘다(작성자 계정은 만들지 않는다: 관리자가 수동).

- 계정마다 역할 하나만 갖는다: 서비스 계정=bi_service, 발급 계정=bi_guest_issuer. 관리자 역할은 주지 않는다.
- 계정이 없으면 만들고, 있으면 매 기동 비밀번호를 환경변수 값으로 다시 맞추고(.env를 바꾸면 다음 기동에 반영)
  활성화하며 역할을 목록대로 되돌린다. 계정 이름 변경·재생성 로직은 없다(이름을 바꾸면 새 계정이 생기고
  기존 계정이 소유한 데이터셋은 이전되지 않는다 -> 이름은 바꾸지 않는다).
- 사람 계정 보호: 이름 비교는 대소문자를 무시한다(FAB auth_username_ci가 find_user를 대소문자 무시로 비교한다).
  변경 전에 기존 계정을 모두 조회한다. 같은 이름의 기존 계정은 **우리가 만든 표식**(first_name이 BI-Wizard이고
  email이 <이름>@localhost, email만 대소문자 무시)이 있을 때만 진행한다. 표식이 없으면 역할과 관계없이(역할 0개, Gamma,
  bi_service 하나만 있어도) 비밀번호 재설정 없이 아무것도 바꾸지 않고 거부한다(사용자 결정 03b 12-1 ③, 사람 계정을 덮어쓰지
  않는다). 새로 만들 계정의 이메일이 다른 계정과 겹치면 마찬가지로 사전에 거부한다(두 번째 계정 단계에서 일부만 바뀌는 것을
  막는다). 하나라도 거부 대상이면 어느 계정도 바꾸지 않는다.
- 강제 복구(EW-3 확인 사항 결정, 03b 10-1): **표식이 있는 기존 계정**에 허용 밖 역할(Admin 포함)이 붙어 있으면 정해진 역할
  하나(bi_service 또는 bi_guest_issuer)만 남기고 모두 제거한다(권한을 줄이는 방향). 복구했으면 경고 로그를 남기고
  마지막 줄 `점검 요약: 강제 복구 N건`(0건이어도)으로 확인할 수 있게 한다. 표식이 없는 계정은 복구하지 않고 거부한다.
  표식은 계정이 만들어질 때 이 스크립트가 넣는 값이라 누군가 같은 이름·표식으로 사람 계정을 만들면 복구 대상이 된다(이름 충돌 점검은 운영 항목).
- 비밀번호는 환경변수로만 받는다. 인수·로그·예외 메시지에 넣지 않고 예외는 종류만 출력한다.
  저장 뒤 재읽기에서 해시가 환경변수 값과 맞는지 확인한다(reset_password는 저장 실패를 조용히 삼킨다).
  FAB 자체 로그(예외에 해시·SQL 파라미터가 들어갈 수 있다)는 이 스크립트 안에서 끈다.
  로그에는 계정·역할 이름과 권한 개수만 나온다(경고에는 제거한 역할 이름 목록).
Superset 내부 코드는 수정하지 않는다.
"""

import logging
import os
import sys

from werkzeug.security import check_password_hash

from bi_roles import GUEST_ISSUER_ROLE, SERVICE_ROLE
from superset.app import create_app

# (계정 이름 변수, 비밀번호 변수, 역할, 표시 이름)
ACCOUNTS = (
    ("SUPERSET_SERVICE_USER", "SUPERSET_SERVICE_PASSWORD", SERVICE_ROLE, ("BI-Wizard", "Service")),
    ("SUPERSET_GUEST_ISSUER_USER", "SUPERSET_GUEST_ISSUER_PASSWORD", GUEST_ISSUER_ROLE, ("BI-Wizard", "Guest Issuer")),
)


def fail(message: str) -> None:
    print(f"[superset-init] {message}", file=sys.stderr)
    sys.exit(1)


admin_name = os.environ.get("SUPERSET_ADMIN_USER", "")
settings = []
problems = []
for user_var, password_var, role_name, names in ACCOUNTS:
    username = os.environ.get(user_var, "")
    password = os.environ.get(password_var, "")
    if not username:
        problems.append(user_var)
    if not password:
        problems.append(password_var)
    settings.append((user_var, username, password, role_name, names))
if problems:
    fail(f"환경변수가 비어 있습니다: {', '.join(problems)}")

# 계정 이름이 서로 또는 관리자와 같으면 기존 계정(관리자 포함)의 역할을 덮어쓰게 되므로 거부한다.
# 대소문자는 구분하지 않는다(Admin과 admin은 같은 계정으로 조회된다).
all_names = [name.casefold() for name in [admin_name] + [item[1] for item in settings]]
if len(set(all_names)) != len(all_names):
    fail("SUPERSET_ADMIN_USER, SUPERSET_SERVICE_USER, SUPERSET_GUEST_ISSUER_USER는 서로 달라야 합니다.")

app = create_app()
# FAB의 사용자 추가·갱신 실패 로그는 예외(해시, SQL 파라미터 포함 가능)를 그대로 남기므로 끈다.
# 실패는 아래 재읽기 비교가 잡아 종류만 출력한다.
logging.getLogger("flask_appbuilder.security.sqla.manager").setLevel(logging.CRITICAL)
with app.app_context():
    sm = app.appbuilder.sm
    admin_role = sm.auth_role_admin

    # 1) 변경 전에 기존 계정을 모두 확인한다. 하나라도 거부 대상이면 아무것도 바꾸지 않는다. 표식이 있는 계정의 허용 밖 역할은 거부하지 않고 복구 대상으로 모은다.
    recoveries = {}  # 계정 이름 -> 제거할 역할 이름 목록(우리 표식이 있는 계정만)
    for _user_var, username, _password, role_name, (first_name, _last) in settings:
        email = f"{username}@localhost"
        existing = sm.find_user(username=username)
        if existing is None:
            # 새로 만들 계정의 이메일이 다른 계정과 겹치면 add_user가 실패해 일부만 바뀔 수 있으므로 미리 거부한다.
            if sm.find_user(email=email) is not None:
                fail(f"계정 {username}을(를) 만들 이메일({email})이 다른 계정과 겹칩니다(이메일 충돌).")
            continue
        existing_roles = {item.name for item in existing.roles}
        ours = existing.first_name == first_name and (existing.email or "").casefold() == email.casefold()
        if not ours:
            # 표식이 없는 기존 계정은 역할과 관계없이 거부한다(비밀번호·활성·역할을 바꾸지 않는다). 역할 이름만 알린다.
            fail(
                f"계정 {username}은(는) 이미 있고 이 스크립트가 만든 계정 표식(이름 BI-Wizard, 이메일 {email})이 없어 "
                f"덮어쓰지 않습니다(현재 역할: {', '.join(sorted(existing_roles)) or '없음'}). "
                "사람 계정이면 .env의 계정 이름을 바꾸고, 예전에 만든 서비스·발급 계정이면 표식을 보정하세요"
                "(skills/local-environment/SKILL.md의 표식 없는 기존 계정 정리)."
            )
        # 표식이 있는 계정: 정해진 역할 하나 밖의 역할(허용 밖 역할, Admin 포함)은 2단계에서 모두 제거한다.
        outside = sorted(existing_roles - {role_name})
        if outside:
            recoveries[username] = outside

    # 2) 계정을 만들거나 갱신한다.
    for user_var, username, password, role_name, (first_name, last_name) in settings:
        role = sm.find_role(role_name)
        if role is None:
            fail(f"역할 {role_name}이(가) 없습니다(ensure_roles 단계가 먼저 성공해야 합니다).")
        try:
            user = sm.find_user(username=username)
            if user is None:
                created = sm.add_user(
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    email=f"{username}@localhost",
                    role=role,
                    password=password,
                )
                if not created:
                    fail(f"계정 {username}을(를) 만들지 못했습니다(이메일 충돌 가능).")
                action = "만듦"
            else:
                sm.reset_password(user.id, password)
                user = sm.find_user(username=username)
                user.active = True
                user.roles = [role]
                if sm.update_user(user) is False:
                    fail(f"계정 {username}을(를) 갱신하지 못했습니다.")
                action = "갱신(비밀번호·활성·역할)"
        except Exception as exc:
            sm.session.rollback()  # pylint: disable=consider-using-transaction
            # 예외 메시지에 비밀번호 해시나 연결 정보가 들어갈 수 있어 예외 종류만 출력한다.
            fail(f"계정 {username} 처리 중 오류: {type(exc).__name__}")
        sm.session.expire_all()
        stored = sm.find_user(username=username)
        roles = [item.name for item in stored.roles] if stored else []
        if stored is None or not stored.active or roles != [role_name] or admin_role in roles:
            fail(f"계정 {username}의 상태가 기대와 다릅니다(재읽기 비교 실패).")
        # 저장된 해시가 환경변수 값과 맞는지 확인한다(값은 출력하지 않는다).
        if not check_password_hash(stored.password, password):
            fail(f"계정 {username}의 비밀번호가 환경변수 값으로 저장되지 않았습니다(재읽기 비교 실패).")
        print(f"[superset-init] 계정 {username}: {action}, 역할 {role_name}(권한 {len(stored.roles[0].permissions)}개)")
        if username in recoveries:
            # 제거한 역할 이름만 출력한다(비밀번호·해시·계정 정보는 출력하지 않는다).
            print(
                f"[superset-init] 경고: 계정 {username}의 허용 밖 역할({', '.join(recoveries[username])})을 제거하고 "
                f"{role_name}로 강제 복구했습니다"
            )
print("[superset-init] 계정 확인 완료")
print(f"[superset-init] 점검 요약: 강제 복구 {len(recoveries)}건")
