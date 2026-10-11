from r5lib import *
a = admin(); I = load_ids()
st, j = a.body('POST', '/api/v1/database/1/sync_permissions/', {}); show('sync_permissions', st, j)
pvm = pvm_map(a)
def need(p, v):
    i = pvm.get((p, v)); assert i, (p, v); return i
sch_name = [v for (p, v) in pvm if p == 'schema_access' and v.endswith('.[bi_data]')]
print('schema_access names', sch_name)
sch = pvm[('schema_access', sch_name[0])]
svc_perms = [need('can_read', 'Dataset'), need('can_write', 'Dataset'), sch, need('can_read', 'SecurityRestApi')]
rid = ensure_role(a, 'a27_service')
st, j = a.body('POST', f'/api/v1/security/roles/{rid}/permissions', {"permission_view_menu_ids": sorted(svc_perms)}); show('svc role perms', st, j)
pw = envval('SUPERSET_ADMIN_PASSWORD')
st, j = a.body('POST', '/api/v1/security/users/', {"username": "a27_svc", "first_name": "a27", "last_name": "service", "email": "a27_svc@example.invalid", "password": pw, "active": True, "roles": [rid]}); show('svc user', st, j); svc_uid = j.get('id')
# author: Gamma copy + schema role
gamma = role_by_name(a, 'Gamma'); print('Gamma perms', len(gamma['permission_ids']))
rc = ensure_role(a, 'a27_author_copy'); rs = ensure_role(a, 'a27_author_schema_bi_data')
st, j = a.body('POST', f'/api/v1/security/roles/{rc}/permissions', {"permission_view_menu_ids": sorted(gamma['permission_ids'])}); show('copy perms', st, j)
st, j = a.body('POST', f'/api/v1/security/roles/{rs}/permissions', {"permission_view_menu_ids": [sch]}); show('schema role perms', st, j)
st, j = a.body('POST', '/api/v1/security/users/', {"username": "a27_author1", "first_name": "a27", "last_name": "author", "email": "a27_author1@example.invalid", "password": pw, "active": True, "roles": [rc, rs]}); show('author user', st, j); au = j.get('id')
I.update({'svc_role': rid, 'svc_uid': svc_uid, 'sch_pvm': sch, 'svc_perms': svc_perms, 'author_copy': rc, 'author_schema': rs, 'author_uid': au})
save_ids(I)
st, j = a.req('GET', f'/api/v1/security/roles/{rid}/permissions/'); show('svc role perms (readback)', st, [(r.get('permission_name'), r.get('view_menu_name')) for r in j['result']])
