#!/bin/bash
cd /home/user/BI-Wizard/_workspace/gate3/experiments/r4/import
U="docker exec -e BENCH_TIMEOUT=150 g3x27-lab python /work/scripts/bench_u.py"
O=raw/extra2.jsonl
: > $O
for f in files/*.xlsx files/tamper/*.xlsx files/tamper/*.xlsm; do
  case "$f" in */_base.xlsx) continue;; esac
  $U precheck2 1 3 /work/$f >> $O
done
echo done > raw/extra2.done
