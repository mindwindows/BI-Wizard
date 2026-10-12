"""업무 데이터 연결의 schema 권한 항목(schema_access)을 만든다(멱등).

`POST /api/v1/database/{id}/sync_permissions/`가 부르는 SyncPermissionsCommand를 앱 컨텍스트에서 직접 실행한다
(REST 호출 없음, Superset 내부 코드는 수정하지 않는다). 명령이 현재 사용자(g.user)를 요구하므로 Superset 자신의
Celery 작업(sync_database_permissions_task)과 같이 test_request_context 안에서 관리자를 g.user로 둔다.
새 schema(`bi_data`)의 schema_access 항목은 첫 데이터셋 생성이나 이 호출 때 생기므로 역할에 부여하기 전에 실행해야 한다.
비동기 모드(SYNC_DB_PERMISSIONS_IN_ASYNC_MODE)이면 Celery 작업으로 넘어가 끝났는지 알 수 없고 Celery가 없으므로 실패시킨다.
로그에는 예외 종류만 출력한다(연결 정보가 예외 메시지에 들어갈 수 있다).
"""

import os
import sys

from flask import g

from bi_roles import DATABASE_NAME
from superset.app import create_app

username = os.environ.get("SUPERSET_ADMIN_USER", "")
if not username:
    print("[superset-init] SUPERSET_ADMIN_USER가 필요합니다.", file=sys.stderr)
    sys.exit(1)

app = create_app()
with app.app_context():
    # 설정은 superset_config.py가 아니라 실제 적용된 app.config로 확인한다.
    if app.config.get("SYNC_DB_PERMISSIONS_IN_ASYNC_MODE"):
        print(
            "[superset-init] SYNC_DB_PERMISSIONS_IN_ASYNC_MODE가 켜져 있어 권한 동기화를 끝까지 확인할 수 없습니다. 끄세요.",
            file=sys.stderr,
        )
        sys.exit(1)

    from superset import db
    from superset.commands.database.sync_permissions import SyncPermissionsCommand
    from superset.models.core import Database

    try:
        # ensure_accounts와 같은 대소문자 무시 조회(FAB auth_username_ci). 명령에는 저장된 이름을 넘긴다.
        admin = app.appbuilder.sm.find_user(username=username)
        if admin is None:
            print("[superset-init] 관리자 계정이 없어 권한을 동기화할 수 없습니다.", file=sys.stderr)
            sys.exit(1)
        database = db.session.query(Database).filter_by(database_name=DATABASE_NAME).one_or_none()
        if database is None:
            print("[superset-init] 업무 데이터 연결이 없어 권한을 동기화할 수 없습니다.", file=sys.stderr)
            sys.exit(1)
        with app.test_request_context():
            g.user = admin
            SyncPermissionsCommand(database.id, admin.username).run()
    except Exception as exc:
        print(f"[superset-init] 권한 동기화에 실패했습니다: {type(exc).__name__}", file=sys.stderr)
        sys.exit(1)
print("[superset-init] 업무 데이터 연결 권한 동기화 완료")
