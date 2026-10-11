from x23_lib import *
import threading, base64, time
a=admin(); I=json.load(open('base_ids.json')); R=I['x22']
def setperms(role,pids): return a.body('POST',f"/api/v1/security/roles/{role}/permissions",{"permission_view_menu_ids":sorted(pids)})[0]
SVC=[11,12,234,192]   # can_read Dataset, can_write Dataset, schema_access bi_data, can_read SecurityRestApi
print('service role perms set',setperms(R['role'],SVC))
svc=U('x22_svc'); print('login',svc.login(),'csrf',svc.csrf_fetch())
print("=== (a) token / CSRF / cookie behaviour")
tok=svc.tok; pl=json.loads(base64.urlsafe_b64decode(tok.split('.')[1]+'==')); print('access token claims:',{k:pl[k] for k in ('iat','exp','type','fresh') if k in pl},'lifetime sec =',pl['exp']-pl['iat'])
rt=svc.ref; pr=json.loads(base64.urlsafe_b64decode(rt.split('.')[1]+'==')); print('refresh token lifetime sec =',pr['exp']-pr['iat'])
print('POST without CSRF header:',svc.req('POST','/api/v1/dataset/',{"database":1,"schema":"bi_data","table_name":"x22_probe"})[0])
other=U('x22_svc'); other.login(); other.csrf=svc.csrf
print('POST with CSRF token from another session (different cookie jar):',other.post('/api/v1/dataset/',{"database":1,"schema":"bi_data","table_name":"x22_probe"})[0])
nocookie=U('x22_svc'); nocookie.login(); nocookie.csrf_fetch(); nocookie.jar.clear()
print('POST with valid token but cookie jar cleared:',nocookie.post('/api/v1/dataset/',{"database":1,"schema":"bi_data","table_name":"x22_probe"})[0])
old=svc.csrf; svc.login(); print('re-login in same jar, OLD csrf token still valid?',svc.post('/api/v1/dataset/',{"database":1,"schema":"bi_data","table_name":"x22_probe"})[0],'(422/201=accepted, 400=rejected)')
svc.csrf_fetch(); print('csrf token same value after refetch in same session?',old==svc.csrf)
# expired / bad tokens (forged with the QA dummy secret; test instance only)
import hmac, hashlib
def mint(claims,secret):
    h=base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).rstrip(b'=').decode(); p=base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b'=').decode()
    sig=base64.urlsafe_b64encode(hmac.new(secret.encode(),f"{h}.{p}".encode(),hashlib.sha256).digest()).rstrip(b'=').decode(); return f"{h}.{p}.{sig}"
sec=envval('SUPERSET_SECRET_KEY'); exp_claims=dict(pl); exp_claims['exp']=int(time.time())-60; exp_claims['iat']=int(time.time())-960
t_exp=mint(exp_claims,sec)
x=U('x22_svc'); x.tok=t_exp; print('SIMULATED expired access token (signed with QA dummy secret):',x.req('GET','/api/v1/dataset/?q=(page_size:1)'))
x.tok=tok[:-3]+'abc'; print('bad signature token:',x.req('GET','/api/v1/dataset/?q=(page_size:1)'))
r=U('x22_svc'); r.tok=svc.ref; st,j=r.req('POST','/api/v1/security/refresh'); print('POST /security/refresh with refresh token',st,list(j.keys()) if isinstance(j,dict) else j)
if st==200:
    r.tok=j['access_token']; print('  new access token works for GET:',r.req('GET','/api/v1/dataset/?q=(page_size:1)')[0],'| POST needs csrf from same cookie jar:',r.csrf_fetch(),r.post('/api/v1/dataset/',{"database":1,"schema":"bi_data","table_name":"x22_probe"})[0])
# access token used on refresh endpoint?
r2=U('x22_svc'); r2.tok=svc.tok; print('POST /security/refresh with ACCESS token:',r2.req('POST','/api/v1/security/refresh')[0])
print("=== (b) register virtual dataset for view dv_1 as service account")
name="[팀1] 월별 실적"
st,j=svc.post('/api/v1/dataset/',{"database":1,"schema":"bi_data","table_name":name,"sql":"SELECT * FROM bi_data.dv_1 WHERE team = '팀1'"}); print('POST dataset',st,s(j,150)); DSV=j.get('id'); R['DSV']=DSV
st,j=svc.req('GET',f'/api/v1/dataset/{DSV}'); r=j['result']; print('GET',st,'name',r['table_name'],'schema',r['schema'],'kind',r['kind'],'owners',[o['first_name'] for o in r['owners']],'columns',[(c['column_name'],c['type'],c['is_dttm']) for c in r['columns']],'main_dttm_col',r['main_dttm_col'],'extra',r.get('extra'))
print('DB row:',sup(f"select id,table_name,schema,perm,schema_perm from tables where id={DSV}"))
# who can see it: author1 (schema role)
u1=U('x20_author1'); u1.start(); print('author1 (schema_access) GET new dataset',u1.req('GET',f'/api/v1/dataset/{DSV}')[0],'| in list:',DSV in [r['id'] for r in u1.req('GET','/api/v1/dataset/?q=(page_size:100)')[1]['result']])
print('what svc can/cannot do besides datasets:')
for lab,(m,p) in {'GET /chart/':('GET','/api/v1/chart/'),'GET /dashboard/':('GET','/api/v1/dashboard/'),'GET /database/':('GET','/api/v1/database/'),'GET /security/users/':('GET','/api/v1/security/users/'),'GET /security/roles/search/':('GET','/api/v1/security/roles/search/')}.items(): print('  ',lab,svc.req(m,p)[0])
print('  POST chart/data on DSV:',svc.post('/api/v1/chart/data',{"datasource":{"id":DSV,"type":"table"},"queries":[{"columns":["team"],"row_limit":3}],"result_format":"json","result_type":"full"})[0])
print('  POST chart create:',svc.post('/api/v1/chart/',{"slice_name":"x22_svc_chart","viz_type":"table","datasource_id":DSV,"datasource_type":"table","params":"{}"})[0])
print('  POST dataset on schema public (no schema_access):',svc.post('/api/v1/dataset/',{"database":1,"schema":"public","table_name":"x20_pub"})[0], svc.post('/api/v1/dataset/',{"database":1,"schema":"public","table_name":"x22_v2","sql":"select 1 as a"})[0])
print('  PUT database / POST database:',svc.put('/api/v1/database/1',{"database_name":"x"})[0],svc.post('/api/v1/database/',{"database_name":"e","sqlalchemy_uri":"postgresql://a:b@h/d"})[0])
print("=== (f) service account vs embedded / guest token")
dd=json.load(open('base_ids.json'))['x20']['AD1']
print('POST embedded on a dashboard (no perms):',svc.body('POST',f'/api/v1/dashboard/{dd}/embedded',{"allowed_domains":[]})[0],'| PUT:',svc.body('PUT',f'/api/v1/dashboard/{dd}/embedded',{"allowed_domains":[]})[0],'| GET:',svc.req('GET',f'/api/v1/dashboard/{dd}/embedded')[0])
emb=json.load(open('base_ids.json'))['emb']['1']
print('POST guest_token (no can_grant_guest_token):',svc.post('/api/v1/security/guest_token/',{"user":{"username":"g"},"resources":[{"type":"dashboard","id":emb}],"rls":[]})[0])
setperms(R['role'],SVC+[191]); svc2=U('x22_svc'); svc2.start(); print('POST guest_token WITH can_grant_guest_token added:',svc2.post('/api/v1/security/guest_token/',{"user":{"username":"g"},"resources":[{"type":"dashboard","id":emb}],"rls":[]})[0])
setperms(R['role'],SVC)
json.dump(I,open('base_ids.json','w'))
