from x23_lib import *
import threading
a=admin(); I=json.load(open('base_ids.json')); R=I['x22']; DSV=R['DSV']
svc=U('x22_svc'); svc.start()
NAME0="[팀1] 월별 실적"; NAME1="[팀1] 월별 실적 (개정)"
print("=== (c) rename")
C=mk_chart(a,DSV,'x22_chart_on_dsv'); DB=mk_dash(a,'x22_dash_dsv',[C],published=True); R.update({'chart_dsv':C,'dash_dsv':DB})
pvm=pvm_map(a); inv={v:k for k,v in pvm.items()}
ds_pv=[(i,p,v) for (p,v),i in pvm.items() if p=='datasource_access' and f'(id:{DSV})' in v]; print('datasource_access PVM of DSV:',ds_pv)
g=role_by_name(a,'Gamma'); rid=ensure_role(a,'x22_ds_role'); print('role perms',a.body('POST',f'/api/v1/security/roles/{rid}/permissions',{"permission_view_menu_ids":sorted(set(g['permission_ids'])|{ds_pv[0][0]})})[0])
st,j=a.body('POST','/api/v1/security/users/',{"username":"x22_dsuser","first_name":"x22ds","last_name":"u","email":"x22ds@example.invalid","password":envval('SUPERSET_ADMIN_PASSWORD'),"active":True,"roles":[rid]}); print('dsuser',st); R['ds_role']=rid
dsu=U('x22_dsuser'); dsu.start()
def probe(label):
    q={"datasource":{"id":DSV,"type":"table"},"queries":[{"columns":["team","value"],"row_limit":3}],"result_format":"json","result_type":"full"}
    print(f"  [{label}] dsuser: GET dataset {dsu.req('GET',f'/api/v1/dataset/{DSV}')[0]}, chart/data {dsu.post('/api/v1/chart/data',q)[0]}, GET chart {dsu.req('GET',f'/api/v1/chart/{C}')[0]}, GET dashboard {dsu.req('GET',f'/api/v1/dashboard/{DB}')[0]}, dataset in list {DSV in [r['id'] for r in dsu.req('GET','/api/v1/dataset/?q=(page_size:100)')[1]['result']]} | admin chart/data {a.post('/api/v1/chart/data',q)[0]}")
    print('   DB tables.perm:',sup(f"select perm,schema_perm from tables where id={DSV}"),'| slices.perm/schema_perm/datasource_name:',sup(f"select perm,schema_perm,datasource_name from slices where id={C}"))
    print('   view_menu names with (id:%d):'%DSV, sup(f"select pv.id, vm.name from ab_permission_view pv join ab_view_menu vm on vm.id=pv.view_menu_id where vm.name like '%(id:{DSV})' order by 1").replace('\n',' ; '))
    rr=role_by_name(a,'x22_ds_role'); print('   x22_ds_role datasource PVMs:',[inv.get(i) or i for i in rr['permission_ids'] if i==ds_pv[0][0]], '(pvm id',ds_pv[0][0],')')
probe('before rename')
st,j=svc.put(f'/api/v1/dataset/{DSV}',{"table_name":NAME1}); print('svc PUT rename',st,s(j,120))
pvm=pvm_map(a); inv={v:k for k,v in pvm.items()}
probe('after rename')
print('PVMs now named for id:',[(i,v) for (p,v),i in pvm.items() if p=='datasource_access' and f'(id:{DSV})' in v])
st,j=svc.put(f'/api/v1/dataset/{DSV}',{"table_name":"dv_1"}); print('svc rename to a name that exists as a physical dataset? (dv_1 in same schema)',st,s(j,200))
st,j=svc.put(f'/api/v1/dataset/1',{"table_name":"hijack"}); print('svc PUT rename on ADMIN-registered dataset id 1 (not owner)',st,s(j,100))
st,j=svc.put(f'/api/v1/dataset/1/refresh',{}); print('svc refresh on admin-registered dataset 1',st,s(j,100))
st,j=svc.delete(f'/api/v1/dataset/1'); print('svc DELETE admin-registered dataset 1',st,s(j,100))
st,j=svc.put(f'/api/v1/dataset/{DSV}',{"table_name":NAME0}); print('rename back',st)
json.dump(I,open('base_ids.json','w'))
