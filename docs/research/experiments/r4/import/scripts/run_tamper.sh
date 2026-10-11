#!/bin/bash
cd /home/user/BI-Wizard/_workspace/gate3/experiments/r4/import
T="docker exec -e BENCH_TIMEOUT=120 g3x27-lab python /work/scripts/bench_t.py"
TD="docker exec -e BENCH_TIMEOUT=120 -e USE_DEFUSED=1 g3x27-lab python /work/scripts/bench_t.py"
O=raw/tamper.jsonl
: > $O
P=/work/files/tamper
# (a) 압축 폭탄·거짓 크기
for f in bomb_rows_300mb bomb_rows_800mb bomb_rows_1gb bomb_rows_rattr_300mb bomb_whitespace_900mb bomb_whitespace_1gb bomb_celltext_500mb bomb_sst_many_300mb bomb_sst_one_200mb bomb_small_declared_lie bomb_small_declared_lie_local; do
  $T precheck 1 3 $P/$f.xlsx >> $O
  $T preview 1 1 $P/$f.xlsx >> $O
  $T scan 1 1 $P/$f.xlsx >> $O
done
# (b) 거짓 dimension, (c) 큰 sst·긴 문자열·열 많음
for f in dim_false sst_unique_big cell_long_string cols_10000 cols_16384_rows_20; do
  $T precheck 1 3 $P/$f.xlsx >> $O
  $T preview 1 1 $P/$f.xlsx >> $O
  $T scan 1 1 $P/$f.xlsx >> $O
  $T scan_unlimited 1 1 $P/$f.xlsx >> $O
done
echo done > raw/tamper.done
