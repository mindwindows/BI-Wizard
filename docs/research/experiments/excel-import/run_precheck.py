"""폴더의 xlsx 전부에 precheck를 돌려 표를 출력한다. 사용: python run_precheck.py <폴더> [upload_limit_mib=5]"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from precheck import Limits, precheck  # noqa: E402

folder = sys.argv[1]
mib = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
lim = Limits(upload_limit=int(mib * 1048576))
print(f"| 파일 | 크기 | 해제 합계 | 비율 | 판정 | 사유 코드 | 시간 |")
print("| --- | --- | --- | --- | --- | --- | --- |")
for name in sorted(os.listdir(folder)):
    if not name.endswith(".xlsx") or name.startswith("_"):
        continue
    path = os.path.join(folder, name)
    size = os.path.getsize(path)
    times = []
    for _ in range(3):
        t0 = time.perf_counter()
        r = precheck(path, size, lim)
        times.append((time.perf_counter() - t0) * 1000)
    unc = r.info.get("unc_total")
    print(f"| {name} | {size / 1048576:.2f} MiB | {unc / 1048576:.1f} MiB | {r.info.get('ratio')} | {'통과' if r.ok else '거부'} | {','.join(r.codes) or '-'} | {min(times):.1f} ms |"
          if unc is not None else
          f"| {name} | {size / 1048576:.3f} MiB | - | - | {'통과' if r.ok else '거부'} | {','.join(r.codes) or '-'} | {min(times):.1f} ms |")
