"""BI-Wizard Superset 설정(고정 파일). 모든 값은 환경변수에서 읽는다.

- Superset 내부 코드는 수정하지 않는다. 설정은 이 파일(PYTHONPATH의 superset_config)로만 바꾼다.
- Secret은 이미지에 넣지 않는다. compose.yml이 .env의 값을 환경변수로 전달한다.
- 하위 경로는 환경변수 SUPERSET_APP_ROOT를 Superset이 직접 읽는다(공식 변수명 그대로).
  Superset 6.1.0은 접두로 시작하지 않는 요청에 404를 낸다. 프록시는 접두를 떼지 않고 전달해야 한다.
"""

import copy
import logging
import os
import uuid
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from sqlalchemy.engine import URL
from superset.config import TALISMAN_CONFIG as _DEFAULT_TALISMAN_CONFIG
from superset.config import TALISMAN_DEV_CONFIG as _DEFAULT_TALISMAN_DEV_CONFIG


def _required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"환경변수 {name}가 비어 있습니다. .env를 확인하세요.")
    return value


# 기본 자리표시 값을 .env의 Secret으로 덮어쓴다(기본값이면 Superset이 시작을 거부한다).
SECRET_KEY = _required("SUPERSET_SECRET_KEY")
GUEST_TOKEN_JWT_SECRET = _required("GUEST_TOKEN_JWT_SECRET")

# 메타데이터 DB: 같은 PostgreSQL 안의 별도 데이터베이스 `superset`, 소유 역할 `superset_meta`(db-bootstrap이 만든다).
# Superset 6.1.0 이미지의 SQLAlchemy 1.4는 URL을 문자열로 만들 때 비밀번호의 '@', ':', '/'만 인코딩한다.
# '%', '#', '?' 같은 문자가 들어가도 되돌려 읽을 수 있도록 비밀번호를 먼저 완전히 URL 인코딩한다.
SQLALCHEMY_DATABASE_URI = URL.create(
    drivername="postgresql+psycopg2",
    username="superset_meta",
    password=quote(_required("SUPERSET_DB_PASSWORD"), safe=""),
    host=_required("POSTGRES_HOST"),
    port=int(_required("POSTGRES_PORT")),
    database="superset",
).render_as_string(hide_password=False)

# 포털이 Embedded SDK(guest token)로 대시보드를 넣는다.
FEATURE_FLAGS = {"EMBEDDED_SUPERSET": True}

# guest token 보유자의 역할(승인: 03b 4-2 Z2, 사용자 결정 2026-10-11). 기본값은 Public이다.
# 이름 단일 출처는 bi_roles.py의 GUEST_ROLE이고 이 값은 같은 문자열을 따로 적는다(웹 프로세스는 bi_roles.py를 읽지 못한다).
# 어긋나면 superset-init의 ensure_roles.py가 실제 적용된 설정과 비교해 실패한다. 역할은 superset-init이 매 기동 만든다
# (권한 4개). PUBLIC_ROLE_LIKE는 설정하지 않는다(Public 권한 0개 유지, ensure_roles.py가 확인한다).
# guest 토큰 유효 시간 GUEST_TOKEN_JWT_EXP_SECONDS는 Superset 기본값 300초(5분)를 그대로 쓴다(Z5, 설정하지 않는다).
GUEST_ROLE_NAME = "bi_guest"

_log = logging.getLogger("bi_wizard.guest_token")

# FU-1e 이월: "포털 등록 표(superset_dashboards)의 embedded uuid만 허용" 검사는 등록 표가 FU-1에서 생기므로 아직 없다.
# 그때 이 목록에 검사 함수 `(body) -> bool`을 추가한다(False를 돌려주면 거부). 훅은 포털 DB를 읽지 않으므로
# 포털 등록과의 일치는 backend가 발급 전에 보장한다(08 §4). 지금은 비어 있다.
_EXTRA_GUEST_TOKEN_CHECKS: list[Callable[[dict[str, Any]], bool]] = []


def _is_uuid(value: str) -> bool:
    try:
        return str(uuid.UUID(value)) == value.lower()
    except ValueError:
        return False


def _reject(reason: str) -> bool:
    # 사유 코드만 남긴다(요청 본문·사용자 이름·토큰은 남기지 않는다).
    _log.warning("guest token 발급 거부: %s", reason)
    return False


def bi_wizard_guest_token_validator(body: dict[str, Any]) -> bool:
    """POST /api/v1/security/guest_token/ 검증 훅(Superset 6.1.0 security/api.py).

    Superset이 스키마 검증(`GuestTokenCreateSchema`)과 임베드 대시보드 존재 확인(`validate_guest_token_resources`)을
    마친 뒤 `body`(`user`, `resources`, `rls`를 담은 dict)로 호출한다. 반환값이 거짓이면 Superset이 400
    ("Guest token validation failed")으로 응답한다. 이 훅은 발급 API 경로에서만 불리므로 직접 서명한 토큰은 막지 못한다
    (그래서 backend는 GUEST_TOKEN_JWT_SECRET을 받지 않는다).
    거부 조건: rls가 비어 있지 않음, 리소스가 정확히 1개가 아니거나 type이 dashboard가 아니거나 id가 uuid 형식이 아님,
    user(username) 누락.
    예외를 내지 않는다(예외는 500이 된다): 알 수 없는 입력은 모두 거부한다.
    """
    try:
        if not isinstance(body, dict):
            return _reject("본문 형식")
        if body.get("rls") != []:
            return _reject("rls가 비어 있지 않음")
        resources = body.get("resources")
        if not isinstance(resources, list) or len(resources) != 1:
            return _reject("리소스가 정확히 1개가 아님")
        resource = resources[0]
        if not isinstance(resource, dict) or resource.get("type") != "dashboard":
            return _reject("리소스 유형이 dashboard가 아님")
        # 리소스 id는 임베드 uuid 형식이어야 한다. Superset 기본 검사는 숫자 id·slug도 대시보드로 인정해(임베드를 켜지 않은
        # 대시보드도 통과, 03c X-28) 그것만으로는 임베드 안 한 대시보드의 입장권이 발급된다. 등록 여부는 확인하지 않는다(FU-1e).
        resource_id = resource.get("id")
        if not isinstance(resource_id, str) or not _is_uuid(resource_id):
            return _reject("리소스 id가 uuid 형식이 아님")
        user = body.get("user")
        if not isinstance(user, dict) or not user.get("username"):
            return _reject("user(username) 누락")
        for check in _EXTRA_GUEST_TOKEN_CHECKS:
            if not check(body):
                return _reject("추가 검사 실패")
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
        return _reject(f"검증 중 오류({type(exc).__name__})")
    return True


GUEST_TOKEN_VALIDATOR_HOOK = bi_wizard_guest_token_validator

# 프록시(frontend nginx 또는 메인 플랫폼) 뒤에서 동작한다.
# x_prefix=0: 접두는 SUPERSET_APP_ROOT로 직접 처리하므로 X-Forwarded-Prefix로 다시 붙이지 않는다.
ENABLE_PROXY_FIX = True
PROXY_FIX_CONFIG = {"x_for": 1, "x_proto": 1, "x_host": 1, "x_port": 0, "x_prefix": 0}

# Superset 텔레메트리(Scarf) 차단(결정: 2026-10-11).
# SCARF_ANALYTICS=false는 6.1.0에서 효과가 없다(메뉴 컴포넌트가 값과 무관하게 픽셀 이미지를 요청한다).
# 대신 기본 CSP의 허용 목록에서 scarf.sh 호스트를 제거해 브라우저가 요청을 보내지 못하게 한다.
# 기본 CSP를 복사해 해당 항목만 거르므로 나머지 정책은 Superset 기본값 그대로다(내부 코드 수정 아님).
_BLOCKED_HOSTS = ("scarf.sh",)


def _without_blocked_hosts(config: dict) -> dict:
    cfg = copy.deepcopy(config)
    csp = cfg.get("content_security_policy")
    if isinstance(csp, dict):
        for directive, sources in csp.items():
            if isinstance(sources, list):
                csp[directive] = [s for s in sources if not any(h in s for h in _BLOCKED_HOSTS)]
    return cfg


TALISMAN_CONFIG = _without_blocked_hosts(_DEFAULT_TALISMAN_CONFIG)
TALISMAN_DEV_CONFIG = _without_blocked_hosts(_DEFAULT_TALISMAN_DEV_CONFIG)
