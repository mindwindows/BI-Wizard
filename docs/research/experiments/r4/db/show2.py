import sys,json
sys.stdout.reconfigure(errors="backslashreplace")
for l in sys.stdin:
    if not l.startswith('{'): print(l.strip()); continue
    r=json.loads(l); print(r['payload'],'|',r['exec'][:110].replace("\n"," "),'| readback:',r.get('readback'),'| equal:',r.get('roundtrip_equal'),'| after:',r['state_after'])
