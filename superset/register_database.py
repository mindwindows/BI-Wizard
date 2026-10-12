"""업무 데이터 연결(bi_readonly)을 Superset에 등록한다(멱등: 이미 있으면 URI를 갱신한다).

`superset set_database_uri` CLI는 내부적으로 같은 함수(superset.utils.database.get_or_create_db)를 부른다.
CLI는 URI를 명령줄 인수로 받아 같은 컨테이너의 프로세스 목록에 비밀번호가 보이므로,
같은 함수를 앱 컨텍스트에서 직접 호출해 인수를 없앴다(Superset 내부 코드는 수정하지 않는다).
URI는 로그에 출력하지 않는다.
"""

import os
import sys
from urllib.parse import quote

from sqlalchemy.engine import URL

from bi_roles import DATABASE_NAME  # ensure_roles.py의 schema_access 이름과 같은 값을 공유한다.
from superset.app import create_app

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
).render_as_string(hide_password=False)

app = create_app()
with app.app_context():
    from superset import db
    from superset.utils.database import get_or_create_db

    try:
        get_or_create_db(DATABASE_NAME, uri)
        db.session.commit()  # pylint: disable=consider-using-transaction
    except Exception as exc:
        db.session.rollback()  # pylint: disable=consider-using-transaction
        # 예외 메시지에 URI가 들어갈 수 있어 예외 종류만 출력한다.
        print(f"[superset-init] 업무 데이터 연결 등록에 실패했습니다: {type(exc).__name__}", file=sys.stderr)
        sys.exit(1)
print("[superset-init] 업무 데이터 연결 등록 완료")
