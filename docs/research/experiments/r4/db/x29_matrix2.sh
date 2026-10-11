#!/bin/sh
cd /home/user/BI-Wizard/_workspace/gate3/experiments/r4/db
short() { grep -v "^INFO  \[alembic.runtime" "$1" | sed 's/\(.\{420\}\).*/\1.../'; }
run() { name="$1"; ./a.sh bi_owner check > out/x29/m2_$name.out 2>&1
  echo "== $name | TARGET=${X29_TARGET:-none} SCHEMAS=${X29_SCHEMAS:-0} FILTER=${X29_FILTER:-none} MODEL=${X29_MODEL:-base} COMPARE_TYPE=${X29_COMPARE_TYPE:-1}"; short out/x29/m2_$name.out; }
export X29_TARGET=meta
echo "######## A. 모델 = DB (정적 표만, 변경 없음): 8가지 구성"
for S in 0 1; do for F in none object name both; do X29_SCHEMAS=$S X29_FILTER=$F X29_MODEL=base run "base_s${S}_f${F}"; done; done
echo "######## B. 정적 모델 변경 감지 (권장 구성 후보 2개: SCHEMAS=0+both, SCHEMAS=1+both)"
for M in add_col add_table drop_col type_change int_to_bigint; do
  for S in 0 1; do X29_SCHEMAS=$S X29_FILTER=both X29_MODEL=$M run "${M}_s${S}_fboth"; done
done
echo "######## C. compare_type=0 일 때 타입 변경"
for M in type_change int_to_bigint; do X29_SCHEMAS=0 X29_FILTER=both X29_MODEL=$M X29_COMPARE_TYPE=0 run "${M}_ct0"; done
echo "######## D. target_metadata=None (현재 저장소 상태)"
X29_TARGET=none run "target_none"
