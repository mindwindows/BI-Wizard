#!/bin/sh
# X-29.3 왕복 테스트 틀: (동적 객체가 이미 있는 DB, head 상태에서 시작)
# 스냅샷 S_head0 -> downgrade base -> S_base0 -> upgrade head -> S_head1 (=S_head0?) -> downgrade base -> S_base1 (=S_base0?)
cd /home/user/BI-Wizard/_workspace/gate3/experiments/r4/db
O=out/x29/rt; mkdir -p $O
export X29_TARGET=meta X29_SCHEMAS=0 X29_FILTER=both
snap() { ./run.sh x29_snapshot.py > $O/$1.json 2> $O/$1.err; }
snap S_head0
./a.sh bi_owner downgrade base > $O/downgrade1.out 2>&1; tail -1 $O/downgrade1.out; snap S_base0
./a.sh bi_owner upgrade head > $O/upgrade1.out 2>&1; tail -1 $O/upgrade1.out; snap S_head1
./a.sh bi_owner downgrade base > $O/downgrade2.out 2>&1; tail -1 $O/downgrade2.out; snap S_base1
./a.sh bi_owner upgrade head > $O/upgrade2.out 2>&1; tail -1 $O/upgrade2.out; snap S_head2
echo "--- head0 vs head1 (upgrade 상태 복원, 동적 객체 포함)"; python3 snapdiff.py $O/S_head0.json $O/S_head1.json
echo "--- base0 vs base1 (downgrade 상태 반복 일치, 동적 객체 포함)"; python3 snapdiff.py $O/S_base0.json $O/S_base1.json
echo "--- head0 vs head2"; python3 snapdiff.py $O/S_head0.json $O/S_head2.json
echo "--- bootstrap(A) vs base0, 정규화+동적 객체 제외"; python3 snapdiff.py out/x29/snap_A_bootstrap.json $O/S_base0.json --normalize --ignore-dynamic
echo "--- bootstrap(A) vs base0, 정규화 없음 (복원 안 되는 것 목록)"; python3 snapdiff.py out/x29/snap_A_bootstrap.json $O/S_base0.json --ignore-dynamic
echo "--- check at head2"; ./a.sh bi_owner check 2>&1 | tail -2
