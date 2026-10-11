#!/usr/bin/env bash
# superset-init: 일회성 서비스. docker compose up 때마다 멱등으로 실행된다.
# 순서: db upgrade -> 관리자(없을 때만) -> init -> 업무 데이터 연결(bi_readonly) 등록.
# Superset 내부 코드는 수정하지 않고 공식 CLI와 설정만 쓴다.
set -euo pipefail

echo "[superset-init] 메타데이터 DB 업그레이드"
superset db upgrade

echo "[superset-init] 관리자 계정 확인"
python /app/bi-wizard/ensure_admin.py

echo "[superset-init] 권한/역할 초기화"
superset init

echo "[superset-init] 업무 데이터 연결(읽기 전용 계정) 등록"
uri="$(python /app/bi-wizard/readonly_uri.py)"
superset set_database_uri -d "BI-Wizard (read-only)" -u "${uri}"

echo "[superset-init] 완료"
