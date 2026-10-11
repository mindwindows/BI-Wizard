"""관리자 계정을 멱등으로 만든다(이미 있으면 건너뛴다). 비밀번호는 환경변수로만 받는다."""

import os
import sys

from superset.app import create_app

username = os.environ.get("SUPERSET_ADMIN_USER", "")
password = os.environ.get("SUPERSET_ADMIN_PASSWORD", "")
if not username or not password:
    print("[superset-init] SUPERSET_ADMIN_USER와 SUPERSET_ADMIN_PASSWORD가 필요합니다.", file=sys.stderr)
    sys.exit(1)

app = create_app()
with app.app_context():
    security_manager = app.appbuilder.sm
    if security_manager.find_user(username=username):
        print("[superset-init] 관리자 계정이 이미 있어 건너뜁니다.")
        sys.exit(0)
    role = security_manager.find_role(security_manager.auth_role_admin) or security_manager.add_role(
        security_manager.auth_role_admin
    )
    user = security_manager.add_user(
        username=username,
        first_name="BI-Wizard",
        last_name="Admin",
        email=f"{username}@localhost",
        role=role,
        password=password,
    )
    if not user:
        print("[superset-init] 관리자 계정을 만들지 못했습니다.", file=sys.stderr)
        sys.exit(1)
    print("[superset-init] 관리자 계정을 만들었습니다.")
