#!/bin/bash
# X-27 (1)(2) 정상 파일 측정 매트릭스. 컨테이너 g3x27-lab(--memory=1g)에서 실행한다.
cd /home/user/BI-Wizard/_workspace/gate3/experiments/r4/import
B="docker exec g3x27-lab python /work/scripts/bench.py"
O=raw/matrix.jsonl
: > $O
for f in tall wide fmt multi; do for m in 5 10 20; do
  F=/work/files/${f}_${m}mb.xlsx
  $B precheck 1 3 $F >> $O
  $B preview 1 3 $F >> $O
  $B scan 1 3 $F >> $O
  $B scan_unlimited 1 3 $F >> $O
done; done
for f in tall wide fmt multi; do for m in 5 10; do
  $B normal 1 3 /work/files/${f}_${m}mb.xlsx >> $O
done; done
echo done > raw/matrix.done
