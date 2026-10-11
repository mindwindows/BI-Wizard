#!/bin/bash
cd /home/user/BI-Wizard/_workspace/gate3/experiments/r4/import
U="docker exec -e BENCH_TIMEOUT=150 g3x27-lab python /work/scripts/bench_u.py"
UR="docker exec -e BENCH_TIMEOUT=150 -e RLIMIT_AS_MB=700 g3x27-lab python /work/scripts/bench_u.py"
O=raw/extra.jsonl
: > $O
F=/work/files; P=/work/files/tamper
for m in 5 10 20; do
  $U preview 1 3 $F/nodim_tall_${m}mb.xlsx >> $O
  $U scan 1 1 $F/nodim_tall_${m}mb.xlsx >> $O
done
$U scan 1 1 $P/dim_false_20000rows.xlsx >> $O
$U scan_unlimited 1 1 $P/dim_false_20000rows.xlsx >> $O
$U scan 1 1 $P/dim_small_20000rows.xlsx >> $O
$U scan_unlimited 1 1 $P/dim_small_20000rows.xlsx >> $O
# precheck2: 정상 파일과 변조 파일 전부
for f in $F/*.xlsx $P/*.xlsx $P/*.xlsm; do
  case "$f" in */_base.xlsx) continue;; esac
  $U precheck2 1 3 $f >> $O
done
# RLIMIT_AS 700MB (HZ2의 메모리 제한 메커니즘)
for f in bomb_rows_300mb bomb_rows_800mb bomb_whitespace_900mb bomb_celltext_500mb bomb_sst_many_300mb; do
  $UR scan 1 1 $P/$f.xlsx >> $O
done
$UR scan 1 3 $F/tall_10mb.xlsx >> $O
$UR scan 1 1 $F/tall_20mb.xlsx >> $O
echo done > raw/extra.done
