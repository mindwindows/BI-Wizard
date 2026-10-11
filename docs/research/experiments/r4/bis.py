import sys, json, subprocess, time, os
sys.path.insert(0, '/home/user/BI-Wizard/_workspace/gate3/experiments/r4')
from x25lib import *
a = admin(); m = pvm_map(a); G20 = [p for p in G21 if p in m]
rid = role_id(a)
CORE = ["tab2", "team", "time", "amount", "cross"]
def run(label, perms, steps=CORE, extra=None):
    global a
    a = admin()
    st, _ = set_perms(a, rid, perms); assert st == 200
    cfg = {"label": label, "dash": "A", "isolate": True, "steps": steps, "shot": f"shots/bisect/{label}"}
    if extra: cfg.update(extra)
    t0 = time.time()
    r = subprocess.run(['node', 'emb.js', json.dumps(cfg), f'out/bisect/{label}.json'], capture_output=True, text=True, cwd='/home/user/BI-Wizard/_workspace/gate3/experiments/r4')
    try: j = json.load(open(f'out/bisect/{label}.json'))
    except Exception: return {"label": label, "error": r.stderr[-300:]}
    fails = {k: v for k, v in j['steps'].items() if not v.get('ok')}
    bad = sorted(set(j['allBad']))
    return {"label": label, "n_perms": len(perms), "pass": j['pass'], "attempts": len(j['attempts']), "failing_steps": list(fails), "bad_requests": bad[:12], "state_err": {k: {c: s for c, s in v.get('state', {}).items() if s != 'ok'} for k, v in fails.items()}, "console": j['consoleErrors'][:3], "sec": round(time.time() - t0)}
if __name__ == '__main__':
    which = sys.argv[1]
    out = []
    if which == 'single':
        items = [(f"rm_{i:02d}_{p[0]}_{p[1]}", [q for q in G20 if q != p]) for i, p in enumerate(G20)]
        if len(sys.argv) > 2: items = [x for x in items if x[0].split('_')[1] in sys.argv[2].split(',')]
        for label, perms in items:
            res = run(label, perms); out.append(res); print(json.dumps(res, ensure_ascii=False), flush=True)
            json.dump(out, open('out/bisect_single_%s.json' % ('all' if len(sys.argv) == 2 else sys.argv[2].replace(',', '-')), 'w'), ensure_ascii=False, indent=1)
    set_perms(a, rid, G20)
