from r3lib import *
import itertools, time
a=admin(); I=json.load(open('base_ids.json')); R=I['x22']
cand={'A:can_read Dataset':11,'B:can_write Dataset':12,'C:can_read Database':17,'D:schema_access bi_data':234,'E:database_access':232,'F:can_read Chart':7,'G:can_read Dashboard':15}
H=192  # can_read SecurityRestApi (csrf_token)
names=list(cand); ids=[cand[n] for n in names]
def setperms(pids): return a.body('POST',f"/api/v1/security/roles/{R['role']}/permissions",{"permission_view_menu_ids":sorted(pids)})[0]
setperms([])
# fixture owned by svc (admin creates), plus a chart on it
st,j=a.post('/api/v1/dataset/',{"database":1,"schema":"bi_data","table_name":"x22_fixture","sql":"SELECT * FROM bi_data.dv_1","owners":[R['uid']]}); print('fixture',st,j if st!=201 else j['id']); F=j['id']
st,j=a.post('/api/v1/chart/',{"slice_name":"x22_fixture_chart","viz_type":"table","datasource_id":F,"datasource_type":"table","params":json.dumps({"viz_type":"table","datasource":f"{F}__table","query_mode":"raw","all_columns":["team"]})}); print('fixture chart',st); FC=j['id']
R['fixture']=F; R['fixture_chart']=FC; json.dump(I,open('base_ids.json','w'))
def one(pset, with_H=True):
    pids=set(pset)|({H} if with_H else set()); setperms(pids)
    s=U('x22_svc'); lst=s.login(); cst=s.csrf_fetch()
    out={'login':lst,'csrf':cst}
    out['lookup']=s.req('GET',"/api/v1/dataset/?q=(filters:!((col:table_name,opr:ct,value:x22_fix)),columns:!(id,table_name))")[0]
    out['get']=s.req('GET',f'/api/v1/dataset/{F}')[0]
    # throwaway to delete (admin creates, svc owner)
    st,j=a.post('/api/v1/dataset/',{"database":1,"schema":"bi_data","table_name":f"x22_del_{time.time_ns()}","sql":"SELECT * FROM bi_data.dv_1","owners":[R['uid']]}); D=j['id']
    nm=f"x22_new_{time.time_ns()}"
    st,j=s.post('/api/v1/dataset/',{"database":1,"schema":"bi_data","table_name":nm,"sql":"SELECT * FROM bi_data.dv_2"}) if s.csrf else (None,None)
    out['create']=st
    if st==201: a.delete(f"/api/v1/dataset/{j['id']}")
    out['rename']=s.put(f'/api/v1/dataset/{F}',{"table_name":f"x22_fixture_{time.time_ns()}"})[0] if s.csrf else None
    out['refresh']=s.put(f'/api/v1/dataset/{F}/refresh',{})[0] if s.csrf else None
    st,j=s.req('GET',f'/api/v1/dataset/{F}/related_objects'); out['related']=st
    out['delete']=s.delete(f'/api/v1/dataset/{D}')[0] if s.csrf else None
    a.delete(f'/api/v1/dataset/{D}')  # cleanup if not deleted
    return out
res=[]; t0=time.time()
for k in range(0,len(ids)+1):
    for comb in itertools.combinations(range(len(ids)),k):
        ps=[ids[i] for i in comb]; r=one(ps); res.append({'perms':[names[i] for i in comb],**r})
    print('subset size',k,'done',round(time.time()-t0),'s',flush=True)
json.dump(res,open('x22_min_results.json','w'),ensure_ascii=False,indent=0)
