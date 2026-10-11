from r3lib import *
a=admin(); I=json.load(open('base_ids.json')); X=I['x20']
u1=U('x20_author1'); u1.start(); u2=U('x20_author2'); u2.start()
def s(j,n=100): return (json.dumps(j,ensure_ascii=False) if not isinstance(j,str) else j)[:n]
print("=== (d) SQL Lab / dataset create / DB connection change as author1")
st,j=u1.post('/api/v1/sqllab/execute/',{"database_id":1,"sql":"select 1","schema":"bi_data","runAsync":False}); print('POST sqllab/execute',st,s(j))
st,j=u1.req('GET','/api/v1/sqllab/'); print('GET sqllab bootstrap',st,s(j,80))
st,j=u1.req('GET','/api/v1/saved_query/'); print('GET saved_query',st,s(j,80))
st,j=u1.req('GET','/api/v1/query/'); print('GET query history',st,s(j,80))
st,j=u1.post('/api/v1/dataset/',{"database":1,"schema":"bi_data","table_name":"ds_1"}); print('create physical dataset',st,s(j,80))
st,j=u1.post('/api/v1/dataset/',{"database":1,"schema":"bi_data","table_name":"x20_v2","sql":"select * from bi_data.dv_1"}); print('create virtual dataset',st,s(j,80))
st,j=u1.put('/api/v1/dataset/1',{"table_name":"renamed_by_author"}); print('rename dataset 1',st,s(j,80))
st,j=u1.put('/api/v1/database/1',{"database_name":"x"}); print('PUT database 1',st,s(j,80))
st,j=u1.post('/api/v1/database/',{"database_name":"evil","sqlalchemy_uri":"postgresql://x:y@h/d"}); print('POST database',st,s(j,80))
st,j=u1.req('GET','/api/v1/database/1'); print('GET database 1 (connection info)',st,s(j,200))
st,j=u1.req('GET','/api/v1/database/1/connection'); print('GET database 1 connection',st,s(j,120))
print("=== (e) embedded on/off as author1 without can_set_embedded")
da=X['da']
for m,p,b in [('POST',f'/api/v1/dashboard/{da}/embedded',{"allowed_domains":[]}),('PUT',f'/api/v1/dashboard/{da}/embedded',{"allowed_domains":[]}),('GET',f'/api/v1/dashboard/{da}/embedded',None),('DELETE',f'/api/v1/dashboard/{da}/embedded',None)]:
    st,j=u1.body(m,p,b); print(' own dashboard',m,st,s(j,100))
st,j=u1.body('PUT','/api/v1/dashboard/1/embedded',{"allowed_domains":[]}); print(' ADMIN dashboard 1 (published, already embedded by admin) PUT',st,s(j,100))
st,j=u1.req('GET','/api/v1/dashboard/1/embedded'); print(' ADMIN dashboard 1 GET embedded (Gamma has can_get_embedded)',st,s(j,140))
st,j=u1.delete('/api/v1/dashboard/1/embedded'); print(' ADMIN dashboard 1 DELETE embedded (Gamma has can_delete_embedded)',st,s(j,100))
st,j=a.req('GET','/api/v1/dashboard/1/embedded'); print(' (admin re-check dashboard 1 embedded still there?)',st,s(j,120))
