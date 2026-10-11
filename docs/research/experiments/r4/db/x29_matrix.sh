#!/bin/sh
# X-29.1 행렬: alembic check (+ 일부 revision --autogenerate). 출력: out/x29/matrix_<이름>.out
cd /home/user/BI-Wizard/_workspace/gate3/experiments/r4/db
run() { # name; env는 호출 전에 export
  name="$1"; shift
  ./a.sh bi_owner check > out/x29/matrix_$name.out 2>&1
  echo "== $name | TARGET=${X29_TARGET:-none} SCHEMAS=${X29_SCHEMAS:-0} FILTER=${X29_FILTER:-none} MODEL=${X29_MODEL:-base} COMPARE_TYPE=${X29_COMPARE_TYPE:-1}"
  grep -v "^INFO  \[alembic.runtime" out/x29/matrix_$name.out | cut -c1-700
}
export X29_TARGET=meta
for S in 0 1; do for F in none object name both; do export X29_SCHEMAS=$S X29_FILTER=$F; run "s${S}_f${F}"; done; done
