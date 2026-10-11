from r3lib import *
a=admin(); I=json.load(open('base_ids.json'))
rid=ensure_role(a,'x22_service'); print('role',rid)
st,j=a.body('POST','/api/v1/security/users/',{"username":"x22_svc","first_name":"x22","last_name":"service","email":"x22_svc@example.invalid","password":envval('SUPERSET_ADMIN_PASSWORD'),"active":True,"roles":[rid]}); print('user',st,j if st>=300 else j['id']); uid=j.get('id')
if uid is None:
    st,j=a.req('GET','/api/v1/security/users/?q=(page_size:100)'); uid=[u['id'] for u in j['result'] if u['username']=='x22_svc'][0]
I['x22']={'role':rid,'uid':uid}; json.dump(I,open('base_ids.json','w'))
# svc with ZERO permissions: can it even log in / read csrf / list datasets?
s=U('x22_svc'); print('login',s.login(),'csrf',s.csrf_fetch(), s.req('GET','/api/v1/dataset/')[0], s.req('GET','/api/v1/me/')[0])
