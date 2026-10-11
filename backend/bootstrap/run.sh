#!/usr/bin/env bash
# BI-Wizard db-bootstrap 실행 스크립트(postgres 이미지 안에서 실행된다).
# docker compose up 때마다 멱등으로 실행한다. initdb.d는 쓰지 않는다(볼륨이 있으면 재실행되지 않기 때문).
#
# 접속 정보는 환경변수(PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE)로 받는다.
# 비밀번호를 명령줄에 넣지 않는다. 같은 스크립트를 테스트 DB에 적용하려면 PGHOST만 바꾼다:
#   docker compose --profile test run --rm --no-deps -e PGHOST=postgres-test db-bootstrap
set -euo pipefail

for name in PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE POSTGRES_READONLY_PASSWORD SUPERSET_DB_PASSWORD; do
  if [ -z "${!name:-}" ]; then
    echo "[db-bootstrap] 환경변수 ${name}가 비어 있거나 없습니다. .env를 확인하세요." >&2
    exit 1
  fi
done

# 접속 계정(POSTGRES_USER)이 상수 역할 이름과 같으면 슈퍼유저 비밀번호를 덮어쓰고 읽기 전용이 걸린다.
case "${PGUSER}" in
  bi_readonly | superset_meta)
    echo "[db-bootstrap] POSTGRES_USER는 bi_readonly, superset_meta와 같은 이름일 수 없습니다." >&2
    exit 1
    ;;
esac

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# healthcheck 이후에 시작되지만, 대상이 바뀌는 경우(테스트 DB 등)를 위해 짧게 기다린다.
for _ in $(seq 1 30); do
  if pg_isready -q; then
    break
  fi
  sleep 1
done

exec psql --no-psqlrc --set=ON_ERROR_STOP=1 --file="${script_dir}/roles.sql"
