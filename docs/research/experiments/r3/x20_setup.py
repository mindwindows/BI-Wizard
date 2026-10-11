from r3lib import *
a=admin(); ids=json.load(open('base_ids.json'))
pvm=pvm_map(a); inv={v:k for k,v in pvm.items()}
gamma=role_by_name(a,'Gamma'); print('Gamma id',gamma['id'],'n perms',len(gamma['permission_ids']))
gamma_set=sorted(gamma['permission_ids'])
json.dump([(i,)+inv[i] for i in gamma_set],open('x20_gamma_perms.json','w'),ensure_ascii=False)
rc=ensure_role(a,'x20_author_copy'); rs=ensure_role(a,'x20_author_schema_bi_data'); print('roles',rc,rs)
st,j=a.body('POST',f'/api/v1/security/roles/{rc}/permissions',{"permission_view_menu_ids":gamma_set}); print('copy perms POST',st,j if st!=200 else '')
sch=pvm.get(('schema_access','[BI-Wizard (read-only)].[bi_wizard].[bi_data]')); print('schema_access pvm',sch)
st,j=a.body('POST',f'/api/v1/security/roles/{rs}/permissions',{"permission_view_menu_ids":[sch]}); print('schema role perms POST',st,j if st!=200 else '')
def mkuser(u):
    st,j=a.body('POST','/api/v1/security/users/',{"username":u,"first_name":u,"last_name":"x20","email":u+"@example.invalid","password":envval('SUPERSET_ADMIN_PASSWORD'),"active":True,"roles":[rc,rs]}); print('user',u,st,j if st>=300 else j.get('id')); return j.get('id')
uid1=mkuser('x20_author1'); uid2=mkuser('x20_author2')
ids.update({'x20':{'role_copy':rc,'role_schema':rs,'u1':uid1,'u2':uid2,'gamma':gamma['id'],'sch_pvm':sch}})
# extra datasets for the test: virtual over bi_data, information_schema dataset
st,j=a.post('/api/v1/dataset/',{"database":1,"schema":"bi_data","table_name":"x20_virtual","sql":"SELECT * FROM bi_data.dv_1"}); print('virtual',st,j if st!=201 else j['id']); ids['x20']['virt']=j.get('id')
st,j=a.post('/api/v1/dataset/',{"database":1,"schema":"information_schema","table_name":"tables"}); print('info_schema.tables',st,j if st!=201 else j['id']); ids['x20']['info']=j.get('id')
json.dump(ids,open('base_ids.json','w'))
st,j=a.req('GET',f'/api/v1/security/roles/{rc}/permissions/'); print('copy role perms API', st, len(j.get('result',[])) if isinstance(j,dict) else j)
