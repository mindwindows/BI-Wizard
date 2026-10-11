import json, sys
sys.stdout.reconfigure(errors="backslashreplace")
lo = sys.argv[1] if len(sys.argv)>1 else ""
for l in open('out/x26_1_matrix.out'):
    if not l.startswith('{'): print(l.strip()); continue
    r=json.loads(l)
    if lo and not r['id'].startswith(lo): continue
    print(r['id'],r['label'],'|',r.get('rendered','')[-80:],'|',r.get('exec','')[:230].replace('\n',' '),'|',r.get('readback'),r.get('readback_type'),'| match=',r.get('match'),r.get('match_value_only',''),'|',r.get('pg_typeof'),'|',r.get('viewdef','')[:100], r.get('render_error',''))
