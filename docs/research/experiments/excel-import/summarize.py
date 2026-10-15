"""bench.py 결과(jsonl)를 마크다운 표로 요약한다. 사용: python summarize.py <결과.jsonl> [<결과2.jsonl> ...]"""

import json
import sys
from collections import defaultdict
from statistics import mean

groups = defaultdict(list)
for path in sys.argv[1:]:
    for line in open(path):
        r = json.loads(line)
        key = (r.get("runner"), r.get("file"), r.get("mode"), " ".join(r.get("args", [])),
               "defused=off" if r.get("env", {}).get("OPENPYXL_DEFUSEDXML") == "False" else "")
        groups[key].append(r)

print("| 실행 | 파일 | 모드 | 인수 | 비고 | 횟수 | 시간 평균/최대(s) | 최대 RSS 평균/최대(MB) | 증가분 평균(MB) | 결과 |")
print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
for key, rs in groups.items():
    ok = [r for r in rs if r.get("status") == "ok"]
    use = ok or rs
    t = [r.get("total_s", 0) for r in use]
    m = [r.get("max_rss_mb", 0) or 0 for r in use]
    d = [r.get("delta_rss_mb", 0) or 0 for r in use]
    rc = sorted({r.get("rc") for r in rs})
    extra = rs[0]
    detail = []
    for k in ("rows", "cells", "stop", "items", "periods", "errors_total", "formula_cells", "out_cells"):
        if k in extra and extra[k] not in (None,):
            detail.append(f"{k}={extra[k]}")
    status = rs[0].get("status") if len(ok) == len(rs) else f"{len(ok)}/{len(rs)} ok; {rs[-1].get('status')}; rc={rc}"
    print(f"| {key[0]} | {key[1]} | {key[2]} | {key[3]} | {key[4]} | {len(rs)} | {mean(t):.2f} / {max(t):.2f} | "
          f"{mean(m):.1f} / {max(m):.1f} | {mean(d):.1f} | {status} {' '.join(detail)} |")
