import json, sys, collections
sys.stdout.reconfigure(errors="backslashreplace")
for mode in ("plain", "typed"):
    rows=[json.loads(l) for l in open(f'out/x26_3_equiv_{mode}.out') if l.startswith('{')]
    print("==", mode, len(rows), dict(collections.Counter(r['verdict'] for r in rows)))
    agg=collections.defaultdict(collections.Counter)
    for r in rows: agg[(r['kind'])][r['verdict']]+=1
    for k,v in agg.items(): print("  ", k, dict(v))
    nonsame = collections.defaultdict(list)
    for r in rows:
        if r['verdict']!='SAME': nonsame[(r['kind'], r['expr'], r['verdict'])].append(r['value'])
    for (k,e,v),vals in sorted(nonsame.items()): print("   !", k, "|", e, "|", v, "|", len(vals), "건", vals[:3])
