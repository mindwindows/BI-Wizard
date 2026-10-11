#!/bin/bash
cd /home/user/BI-Wizard/_workspace/gate3/experiments/r4/import
T="docker exec -e BENCH_TIMEOUT=120 g3x27-lab python /work/scripts/bench_t.py"
TD="docker exec -e BENCH_TIMEOUT=120 -e USE_DEFUSED=1 g3x27-lab python /work/scripts/bench_t.py"
O=raw/tamper2.jsonl
: > $O
P=/work/files/tamper
# (d) XML 엔티티: defusedxml 없음 / 있음
for f in xxe_billion_sheet xxe_billion_sst xxe_external xxe_external_sst xxe_quadratic; do
  $T precheck 1 1 $P/$f.xlsx >> $O
  $T dump 1 1 $P/$f.xlsx >> $O
  $T scan 1 1 $P/$f.xlsx >> $O
  $TD dump 1 1 $P/$f.xlsx >> $O
  $TD scan 1 1 $P/$f.xlsx >> $O
done
# (e) 시트 수
for f in sheets_5000 sheets_50000_refs; do
  $T precheck 1 3 $P/$f.xlsx >> $O
  $T open_only 1 3 $P/$f.xlsx >> $O
  $T preview 1 1 $P/$f.xlsx >> $O
  $T scan 1 1 $P/$f.xlsx >> $O
done
# (f)(g) 형식 위장·암호화·매크로·외부 링크·경로 순회
for f in not_zip_random.xlsx not_zip_text.xlsx empty_file.xlsx truncated_zip.xlsx png_as_xlsx.xlsx zip_not_xlsx.xlsx ole2_signature_only.xlsx encrypted_xlsx.xlsx xlsm_macro.xlsm xlsm_macro_renamed.xlsx external_link.xlsx zip_path_traversal.xlsx; do
  $T precheck 1 1 $P/$f >> $O
  $T dump 1 1 $P/$f >> $O
done
echo done > raw/tamper2.done
