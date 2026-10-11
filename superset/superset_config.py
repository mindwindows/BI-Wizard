"""BI-Wizard Superset 설정(고정 파일). 모든 값은 환경변수에서 읽는다.

- Superset 내부 코드는 수정하지 않는다. 설정은 이 파일(PYTHONPATH의 superset_config)로만 바꾼다.
- Secret은 이미지에 넣지 않는다. compose.yml이 .env의 값을 환경변수로 전달한다.
- 하위 경로는 환경변수 SUPERSET_APP_ROOT를 Superset이 직접 읽는다(공식 변수명 그대로).
  Superset 6.1.0은 접두로 시작하지 않는 요청에 404를 낸다. 프록시는 접두를 떼지 않고 전달해야 한다.
"""

import copy
import os
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
