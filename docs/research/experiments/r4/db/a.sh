#!/bin/sh
# 사용: [환경변수...] ./a.sh <사용자> <alembic 인자...>  (scratch를 /work/scratch에 rw 마운트, root로 실행: 새 revision 파일 쓰기 때문)
# 종료 코드를 마지막 줄 EXIT=<n> 으로 출력한다.
U="$1"; shift
case "$U" in bi_owner) PW=dummy_owner;; bi_app) PW=dummy_app;; postgres) PW=dummy;; esac
D=/home/user/BI-Wizard/_workspace/gate3/experiments/r4/alembic_scratch
docker run --rm --user 0 --network container:g3x26-pg -v "$D":/work/scratch -w /work/scratch \
  -e POSTGRES_HOST=127.0.0.1 -e POSTGRES_PORT=5432 -e POSTGRES_DB="${X29_DB:-x29}" -e POSTGRES_USER="$U" -e POSTGRES_PASSWORD="$PW" \
  -e X29_TARGET -e X29_SCHEMAS -e X29_FILTER -e X29_COMPARE_TYPE -e X29_TPM -e X29_VERSION_SCHEMA -e X29_MODEL \
  --entrypoint sh bi-wizard-backend:local -c 'python -m alembic "$@"; echo "EXIT=$?"' sh "$@"
