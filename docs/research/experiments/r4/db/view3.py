import json, sys, collections
sys.stdout.reconfigure(errors="backslashreplace")
rows=[json.loads(l) for l in open('out/x26_3_equiv_'+sys.argv[2]+'.out') if l.startswith('{')]
cnt=collections.Counter(r['verdict'] for r in rows); print(cnt, len(rows))
only = sys.argv[1] if len(sys.argv)>1 and sys.argv[1]!='-' else None
for r in rows:
    if r['verdict']=='SAME': continue
    if only and not r['verdict'].startswith(only): continue
    b,w=r['bind'],r['view']
    f=lambda x: x.get('error','')[:90] if 'error' in x else f"{x['val']}:{x['pytype']}/{x['pg']}/'{x['txt']}'"
    print(r['verdict'],'|',r['kind'],r['value'],'|',r['expr'],'\n    BIND:',r['bind_sql'][:100],'=>',f(b),'\n    VIEW:',r.get('view_sql','')[-100:],'=>',f(w))
