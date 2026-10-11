#!/bin/sh
# 사용: ./run.sh <스크립트.py> [인자...]   (backend 이미지, g3x26-pg 네트워크 공유, db/ 폴더를 /work로 읽기 전용 마운트)
D=/home/user/BI-Wizard/_workspace/gate3/experiments/r4/db
S="$1"; shift
exec docker run --rm -i --network container:g3x26-pg -v "$D":/work:ro --entrypoint python bi-wizard-backend:local -I "/work/$S" "$@"
