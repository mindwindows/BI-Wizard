"""업무 데이터 연결(bi_readonly) URI를 출력한다. 비밀번호는 URL 인코딩된다."""

import os
import sys
from urllib.parse import quote

from sqlalchemy.engine import URL

NAMES = ("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_READONLY_PASSWORD")
values = {name: os.environ.get(name, "") for name in NAMES}
missing = [name for name, value in values.items() if not value]
if missing:
    print(f"[superset-init] 환경변수가 비어 있습니다: {', '.join(missing)}", file=sys.stderr)
    sys.exit(1)

# SQLAlchemy 1.4(Superset 6.1.0 이미지)는 URL을 문자열로 만들 때 '@', ':', '/'만 인코딩한다.
# '#', '?' 같은 문자도 안전하도록 비밀번호를 먼저 완전히 URL 인코딩한다.
# 단 비밀번호에 '%'가 있으면 Superset 자체가 저장된 URI를 되읽을 때 깨지므로 .env에서 '%'를 쓰지 않는다.
uri = URL.create(
    drivername="postgresql+psycopg2",
    username="bi_readonly",
    password=quote(values["POSTGRES_READONLY_PASSWORD"], safe=""),
    host=values["POSTGRES_HOST"],
    port=int(values["POSTGRES_PORT"]),
    database=values["POSTGRES_DB"],
)
print(uri.render_as_string(hide_password=False))
