"""raw/*.jsonl을 (mode,file,n)별로 3회 평균·최대 표로 만든다. 사용: python summarize.py raw/matrix.jsonl [mode ...]"""
import sys, json, collections, statistics as st
rows = collections.defaultdict(list)
for line in open(sys.argv[1], encoding="utf-8"):
    line = line.strip()
    if not line.startswith("{"):
        continue
    d = json.loads(line)
    rows[(d["mode"], d["file"], d["n"])].append(d)
modes = set(sys.argv[2:])
def f(v): return "-" if v is None else f"{v:.2f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)
print("| mode | file | n | reps | wall평균(s) | wall최대 | open평균(s) | iter평균(s) | worker RSS최대(MB) | worker RSS평균 | 증가분(RSS-기준)최대 | cgroup피크최대(MB) | RSS합피크최대 | 행 | 셀 | 중단/비고 |")
print("|" + "---|" * 16)
for (mode, file, n), reps in sorted(rows.items()):
    if modes and mode not in modes: continue
    ws = [w for r in reps for w in r["workers"]]
    def col(k): return [w[k] for w in ws if k in w]
    wall = [r["wall_s"] for r in reps]
    rss = col("maxrss_mb"); d = [w["maxrss_mb"] - w.get("base_rss_mb", 0) for w in ws if "maxrss_mb" in w]
    note = set(w.get("stop") or w.get("error") or (";".join(w["reasons"]) if w.get("reasons") else ("OK" if "reasons" in w else "")) for w in ws)
    rc = set(w.get("returncode") for w in ws)
    if rc != {0}: note.add(f"rc={sorted(rc, key=str)}")
    print(f"| {mode} | {file} | {n} | {len(reps)} | {f(round(st.mean(wall),2))} | {f(max(wall))} | {f(round(st.mean(col('open_s')),2)) if col('open_s') else '-'} | {f(round(st.mean(col('iter_s')),2)) if col('iter_s') else '-'} | {f(max(rss)) if rss else '-'} | {f(round(st.mean(rss),1)) if rss else '-'} | {f(round(max(d),1)) if d else '-'} | {f(max(r['peak_cgroup_mb'] for r in reps))} | {f(max(r['peak_rss_sum_mb'] for r in reps))} | {ws[0].get('rows','-')} | {ws[0].get('cells','-')} | {'; '.join(sorted(map(str,note)))[:110]} |")
