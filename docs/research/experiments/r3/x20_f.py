from r3lib import *
import subprocess
a=admin(); I=json.load(open('base_ids.json')); X=I['x20']
def s(j,n=140): return (json.dumps(j,ensure_ascii=False) if not isinstance(j,str) else j)[:n]
pvm=pvm_map(a); inv={v:k for k,v in pvm.items()}
def setperms(role_id, ids): return a.body('POST',f'/api/v1/security/roles/{role_id}/permissions',{"permission_view_menu_ids":sorted(set(ids))})[0]
def cmp(label):
    g=role_by_name(a,'Gamma'); c=role_by_name(a,'x20_author_copy'); gs,cs=set(g['permission_ids']),set(c['permission_ids'])
    print(f"[{label}] Gamma={len(gs)} copy={len(cs)} | only Gamma: {[inv.get(i,i) for i in sorted(gs-cs)]} | only copy: {[inv.get(i,i) for i in sorted(cs-gs)]}")
cmp('start')
# (1) simulate "old version": drop can_export from BOTH, then superset init (re-adds to Gamma like a new version would)
gid=X['gamma']; cid=X['role_copy']; exp=pvm[('can_export','Dashboard')]
g=role_by_name(a,'Gamma'); c=role_by_name(a,'x20_author_copy')
print('remove can_export Dashboard from Gamma',setperms(gid,set(g['permission_ids'])-{exp}),'and from copy',setperms(cid,set(c['permission_ids'])-{exp}))
# (2) simulate a custom extra permission on Gamma that init would not know
st,j=a.body('POST','/api/v1/security/resources/',{"name":"X20_NewView"}); print('create view_menu X20_NewView',st,s(j))
vm=j.get('id'); 
st,j=a.body('POST','/api/v1/security/permissions-resources/',{"permission_id":1,"view_menu_id":vm}); print('create PVM can_read on X20_NewView',st,s(j))
newpvm=j.get('id')
g=role_by_name(a,'Gamma'); print('add extra PVM to Gamma',setperms(gid,set(g['permission_ids'])|{newpvm}))
cmp('before init (Gamma lacks can_export, has extra X20 pvm; copy lacks can_export)')
r=subprocess.run(['docker','exec','g3x-superset-1','superset','init'],capture_output=True,text=True,timeout=280); print('superset init exit',r.returncode, (r.stdout+r.stderr).strip().splitlines()[-3:])
pvm=pvm_map(a); inv={v:k for k,v in pvm.items()}
cmp('after superset init')
g=role_by_name(a,'Gamma'); c=role_by_name(a,'x20_author_copy')
print('Gamma has can_export again?',exp in g['permission_ids'],'| Gamma still has extra X20 pvm?',newpvm in g['permission_ids'],'| copy has can_export?',exp in c['permission_ids'])
print('custom roles still exist after init:',[r['name'] for r in a.req('GET','/api/v1/security/roles/search/?q=(page_size:100)')[1]['result']])
print('author1 can still export dashboard (copy lacks can_export Dashboard)? ->', end=' ')
u1=U('x20_author1'); u1.start(); print(u1.req('GET',f"/api/v1/dashboard/export/?q=!({X['da']})")[0],'(Gamma-based user would get 200 if has can_export)')
# restore copy = Gamma (as before) so later tests use a consistent role
print('restore copy := Gamma', setperms(cid,g['permission_ids'])); cmp('restored')
