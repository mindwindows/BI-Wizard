#!/usr/bin/env bash
# superset-init: 일회성 서비스. docker compose up 때마다 멱등으로 실행된다.
# 순서: db upgrade -> 관리자(없을 때만) -> init -> 업무 데이터 연결(bi_readonly) 등록
#       -> schema 권한 동기화 -> 역할 4개 -> 서비스·발급 계정 2개.
# (compose가 migrate 완료 뒤에 시작하므로 bi_readonly의 bi_data USAGE가 이미 있다.)
# Superset 내부 코드는 수정하지 않고 공식 CLI와 설정만 쓴다.
set -euo pipefail

echo "[superset-init] 메타데이터 DB 업그레이드"
superset db upgrade

echo "[superset-init] 관리자 계정 확인"
python /app/bi-wizard/ensure_admin.py

echo "[superset-init] 권한/역할 초기화"
superset init

echo "[superset-init] 업무 데이터 연결(읽기 전용 계정) 등록"
# 비밀번호가 명령줄 인수(프로세스 목록)에 보이지 않도록 CLI 대신 같은 함수를 파이썬으로 호출한다.
python /app/bi-wizard/register_database.py

echo "[superset-init] schema 권한(schema_access) 동기화"
python /app/bi-wizard/sync_permissions.py

echo "[superset-init] 역할 확인(bi_service, bi_guest_issuer, bi_author, bi_author_schema)"
python /app/bi-wizard/ensure_roles.py

echo "[superset-init] 서비스·발급 전용 계정 확인"
python /app/bi-wizard/ensure_accounts.py

echo "[superset-init] 완료"
