#!/bin/bash
cd /home/user/BI-Wizard/_workspace/gate3/experiments/r4/import
B="docker exec g3x27-lab python /work/scripts/bench.py"
O=raw/matrix2.jsonl
: > $O
for m in 5 10 20; do F=/work/files/wide100_${m}mb.xlsx
  $B precheck 1 3 $F >> $O; $B preview 1 3 $F >> $O; $B scan 1 3 $F >> $O; $B scan_unlimited 1 3 $F >> $O
done
for m in 5 10; do $B normal 1 3 /work/files/wide100_${m}mb.xlsx >> $O; done
for f in b_rows_100000_c5 b_rows_100001_c5 b_rows_300000_c3 b_cols_100_r1000 b_cols_101_r1000 b_cells_2000000_r20000_c100 b_cells_2000100_r20001_c100; do
  $B scan 1 3 /work/files/$f.xlsx >> $O
done
# 동시 실행
for n in 2 3; do
  for f in tall_5mb tall_10mb tall_20mb fmt_10mb multi_10mb wide100_10mb; do
    $B scan $n 3 /work/files/$f.xlsx >> $O
  done
  $B preview $n 3 /work/files/tall_10mb.xlsx >> $O
done
echo done > raw/matrix2.done
