from x23_lib import *
import threading, urllib.parse
a=admin(); I=json.load(open('base_ids.json')); R=I['x22']
svc=U('x22_svc'); svc.start()
print("=== (e) duplicates / idempotent registration")
body={"database":1,"schema":"bi_data","table_name":"x22_v"}
st,j=svc.post('/api/v1/dataset/',body); print('physical x22_v registered AGAIN (already exists)',st,s(j,200))
vb={"database":1,"schema":"bi_data","table_name":"x22 가상 v","sql":"SELECT * FROM bi_data.x22_v"}
st,j=svc.post('/api/v1/dataset/',vb); print('virtual same name AGAIN',st,s(j,200))
vb2={"database":1,"schema":"bi_data","table_name":"x22 가상 v2","sql":"SELECT * FROM bi_data.x22_v"}
st,j=svc.post('/api/v1/dataset/',vb2); print('virtual DIFFERENT name, same SQL',st); v2=j.get('id')
print('delete it',svc.delete(f'/api/v1/dataset/{v2}')[0])
# lookup by name (idempotency) with rison filter; Korean + brackets + spaces
def lookup(name,schema='bi_data'):
    q=f"(filters:!((col:table_name,opr:eq,value:'{name}'),(col:schema,opr:eq,value:{schema})),columns:!(id,table_name,schema,kind))"
    st,j=svc.req('GET','/api/v1/dataset/?q='+urllib.parse.quote(q,safe="(),:!'"))
    return st,(j.get('result') if st==200 else j)
print('lookup physical',lookup('x22_v')); print('lookup virtual Korean with spaces',lookup('x22 가상 v')); print('lookup name with brackets',lookup('[팀1] 월별 실적')); print('lookup not existing',lookup('nope'))
# name with special chars: single quote must be rison-escaped (!')
print('lookup name containing a quote, rison-escaped',lookup("a!'b"))
# idempotent update of an existing virtual dataset: PUT sql
V=R['V']; st,j=svc.put(f'/api/v1/dataset/{V}',{"sql":"SELECT period, team FROM bi_data.x22_v"}); print('PUT sql on existing virtual dataset',st,s(j,150)); print('  columns after PUT sql only:',[c['column_name'] for c in a.req('GET',f'/api/v1/dataset/{V}')[1]['result']['columns']]); 
print('  then refresh',svc.put(f'/api/v1/dataset/{V}/refresh',{})[0],[c['column_name'] for c in a.req('GET',f'/api/v1/dataset/{V}')[1]['result']['columns']])
# concurrency: two simultaneous POSTs of the same new name
print(psql("\\d tables").split('Indexes:')[1][:400] if '\\' else '')
res=[]
def post(n):
    t=U('x22_svc'); t.start(); res.append(t.post('/api/v1/dataset/',{"database":1,"schema":"bi_data","table_name":"x22_race","sql":"SELECT 1 AS a"})[0])
th=[threading.Thread(target=post,args=(i,)) for i in range(3)]; [t.start() for t in th]; [t.join() for t in th]; print('3 concurrent POSTs same new name ->',sorted(res))
print('rows with that name in DB:',sup("select count(*) from tables where table_name='x22_race'"))
st,j=lookup('x22_race'); [svc.delete(f"/api/v1/dataset/{r['id']}") for r in (j if st==200 else [])]
# unique constraint evidence
print(sup("select indexdef from pg_indexes where tablename='tables' and indexdef like '%UNIQUE%'"))
print(sup("select conname, pg_get_constraintdef(oid) from pg_constraint where conrelid='tables'::regclass and contype='u'"))
