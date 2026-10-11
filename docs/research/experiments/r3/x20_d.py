from r3lib import *
a=admin(); I=json.load(open('base_ids.json')); X=I['x20']
def s(j,n=110): return (json.dumps(j,ensure_ascii=False) if not isinstance(j,str) else j)[:n]
# admin-owned dashboards using chart 1 (dataset the author can access)
def mkdash(title, published):
    pos={"DASHBOARD_VERSION_KEY":"v2","ROOT_ID":{"type":"ROOT","id":"ROOT_ID","children":["GRID_ID"]},"GRID_ID":{"type":"GRID","id":"GRID_ID","children":["ROW-1"],"parents":["ROOT_ID"]},"HEADER_ID":{"id":"HEADER_ID","type":"HEADER","meta":{"text":title}},"ROW-1":{"type":"ROW","id":"ROW-1","children":["CHART-1"],"parents":["ROOT_ID","GRID_ID"],"meta":{"background":"BACKGROUND_TRANSPARENT"}},"CHART-1":{"type":"CHART","id":"CHART-1","children":[],"parents":["ROOT_ID","GRID_ID","ROW-1"],"meta":{"width":4,"height":40,"chartId":1,"sliceName":"c1"}}}
    st,j=a.post('/api/v1/dashboard/',{"dashboard_title":title,"position_json":json.dumps(pos),"json_metadata":json.dumps({"native_filter_configuration":[],"chart_configuration":{},"positions":pos}),"published":published}); d=j['id']
    a.put('/api/v1/chart/1',{"dashboards":[1,2,d]}) if False else None
    return d
AD1=mkdash('x20_admin_pub_noembed',True); AD2=mkdash('x20_admin_draft_noembed',False); AD3=mkdash('x20_admin_pub_embedded',True)
# attach chart 1 to the new dashboards via the dashboard's positions (admin)
for d in (AD1,AD2,AD3):
    pass
print('admin dashboards',AD1,AD2,AD3)
# make chart 1 belong to all of them: admin chart PUT (all dashboards incl. 1,2,own)
print('chart1 dashboards', a.put('/api/v1/chart/1',{"dashboards":[1,2,AD1,AD2,AD3]})[0])
st,j=a.body('POST',f'/api/v1/dashboard/{AD3}/embedded',{"allowed_domains":["https://portal.example"]}); print('admin enable embedded AD3',st); ad3uuid=j['result']['uuid']
X.update({'AD1':AD1,'AD2':AD2,'AD3':AD3}); json.dump(I,open('base_ids.json','w'))
u1=U('x20_author1'); u1.start()
print('author1 sees AD1/AD2/AD3?',[ (d,u1.req('GET',f'/api/v1/dashboard/{d}')[0]) for d in (AD1,AD2,AD3)])
print("--- BEFORE granting can_set_embedded (Gamma copy as is)")
for d,l in ((X['da'],'own'),(AD1,'admin pub')): print(l,'POST',u1.body('POST',f'/api/v1/dashboard/{d}/embedded',{"allowed_domains":[]})[0])
# grant can_set_embedded to author_copy (replace semantics check)
pvm=pvm_map(a); sid=pvm[('can_set_embedded','Dashboard')]; g=role_by_name(a,'Gamma'); c=role_by_name(a,'x20_author_copy')
print('copy perms before',len(c['permission_ids']))
print('add can_set_embedded to copy',a.body('POST',f"/api/v1/security/roles/{X['role_copy']}/permissions",{"permission_view_menu_ids":sorted(set(c['permission_ids'])|{sid})})[0], 'copy perms after',len(role_by_name(a,'x20_author_copy')['permission_ids']))
u1=U('x20_author1'); u1.start()   # fresh token (permissions are read from DB per request, but be safe)
print("--- AFTER granting can_set_embedded")
st,j=u1.body('POST',f"/api/v1/dashboard/{X['da']}/embedded",{"allowed_domains":[]}); print('author1 own dashboard POST',st,s(j,120))
st,j=u1.body('POST',f'/api/v1/dashboard/{AD1}/embedded',{"allowed_domains":[]}); print('author1 ADMIN-owned PUBLISHED dashboard (not owner) POST',st,s(j,120))
st,j=u1.body('POST',f'/api/v1/dashboard/{AD2}/embedded',{"allowed_domains":[]}); print('author1 ADMIN-owned DRAFT dashboard (not visible) POST',st,s(j,120))
st,j=u1.body('PUT',f'/api/v1/dashboard/{AD3}/embedded',{"allowed_domains":[]}); print('author1 PUT allowed_domains=[] on ADMIN-owned embedded dashboard',st,s(j,160))
st,j=a.req('GET',f'/api/v1/dashboard/{AD3}/embedded'); print('  admin view of AD3 embedded now',st,s(j['result'] if st==200 else j,200),'(uuid before',ad3uuid,')')
st,j=u1.body('DELETE',f'/api/v1/dashboard/{AD3}/embedded'); print('author1 DELETE embedded on ADMIN-owned dashboard',st,s(j,100))
st,j=a.req('GET',f'/api/v1/dashboard/{AD3}/embedded'); print('  admin view of AD3 embedded after DELETE',st,s(j,100))
# who is recorded as changed_by
st,j=a.req('GET',f'/api/v1/dashboard/{AD1}/embedded'); print('AD1 embedded record (changed_by)',st,s(j.get('result',{}).get('changed_by') if st==200 else j,120), s(j.get('result',{}).get('uuid') if st==200 else '',60))
# restore: remove can_set_embedded from copy again
print('remove can_set_embedded from copy',a.body('POST',f"/api/v1/security/roles/{X['role_copy']}/permissions",{"permission_view_menu_ids":sorted(set(role_by_name(a,'x20_author_copy')['permission_ids'])-{sid})})[0], len(role_by_name(a,'x20_author_copy')['permission_ids']))
