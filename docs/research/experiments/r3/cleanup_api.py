from r3lib import *
a=admin(); log=[]
def lst(path,cols):
    out=[]; page=0
    while True:
        st,j=a.req('GET',f'{path}?q=(page:{page},page_size:100,columns:!({cols}))')
        if st!=200 or not j.get('result'): break
        out+=j['result']; 
        if len(out)>=j['count']: break
        page+=1
    return out
n={}
for d in lst('/api/v1/dashboard/','id,dashboard_title'):
    if d['dashboard_title'].startswith(('x2',)): n.setdefault('dashboards',[]).append((d['id'],a.delete(f"/api/v1/dashboard/{d['id']}")[0]))
for c in lst('/api/v1/chart/','id,slice_name'):
    if c['slice_name'].startswith('x2'): n.setdefault('charts',[]).append((c['id'],a.delete(f"/api/v1/chart/{c['id']}")[0]))
# charts of base datasets without x2 prefix are none; datasets: delete all registered (test DB anyway)
for d in lst('/api/v1/dataset/','id,table_name'): n.setdefault('datasets',[]).append((d['id'],d['table_name'],a.delete(f"/api/v1/dataset/{d['id']}")[0]))
st,j=a.req('GET','/api/v1/security/users/?q=(page_size:100)')
for u in j['result']:
    if u['username'].startswith(('x20_','x22_')): n.setdefault('users',[]).append((u['username'],a.delete(f"/api/v1/security/users/{u['id']}")[0]))
st,j=a.req('GET','/api/v1/security/roles/search/?q=(page_size:100)')
for r in j['result']:
    if r['name'].startswith(('x20_','x22_')): n.setdefault('roles',[]).append((r['name'],a.delete(f"/api/v1/security/roles/{r['id']}")[0]))
for k,v in n.items(): print(k,len(v),'non-200:',[x for x in v if x[-1] not in (200,)])
print('remaining roles:',[r['name'] for r in a.req('GET','/api/v1/security/roles/search/?q=(page_size:100)')[1]['result']])
print('remaining users:',[u['username'] for u in a.req('GET','/api/v1/security/users/?q=(page_size:100)')[1]['result']])
print('remaining dashboards/charts/datasets:',[len(lst('/api/v1/dashboard/','id')),len(lst('/api/v1/chart/','id')),len(lst('/api/v1/dataset/','id'))])
print('Gamma perms',len(role_by_name(a,'Gamma')['permission_ids']))
