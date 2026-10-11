from r5lib import *
I = load_ids(); a = admin()
sc2 = I['scratch2']
s = U('a27_svc', envval('SUPERSET_ADMIN_PASSWORD')); s.start()
au = U('a27_author1', envval('SUPERSET_ADMIN_PASSWORD')); au.start()
print('=== 5-1 관리자가 등록한 데이터셋(소유자=admin)에 대한 서비스 계정')
st, j = a.post('/api/v1/dataset/', {"database": 1, "schema": "bi_data", "table_name": "[a27 admin] 관리자 소유", "sql": "SELECT * FROM bi_data.dv_1"}); show('admin POST', st, j, 60); adm = j['id']; I['admin_ds'] = adm; save_ids(I)
st, j = a.req('GET', f'/api/v1/dataset/{adm}'); cols = j['result']['columns']; print('owners', j['result']['owners'])
body = {"columns": [{"id": c['id'], "column_name": c['column_name'], "verbose_name": 'X' + c['column_name']} for c in cols]}
st, j = s.req('GET', f'/api/v1/dataset/{adm}'); print('svc GET admin ds:', st)
st, j = s.put(f'/api/v1/dataset/{adm}', body); show('svc PUT columns on admin-owned', st, j, 200)
st, j = s.put(f'/api/v1/dataset/{adm}/refresh', {}); show('svc refresh admin-owned', st, j, 200)
st, j = s.put(f'/api/v1/dataset/{adm}', {"owners": [I['svc_uid']]}); show('svc PUT owners (self-add) admin-owned', st, j, 200)
print('--- 작성자(author1)가 서비스 계정 소유 데이터셋 수정 시도')
st, j = au.put(f'/api/v1/dataset/{sc2}', {"columns": [{"id": c['id'], "column_name": c['column_name'], "verbose_name": 'Y'} for c in s.req('GET', f'/api/v1/dataset/{sc2}')[1]['result']['columns']]}); show('author PUT', st, j, 200)
print('--- 관리자가 서비스 계정을 소유자로 추가 후')
st, j = a.put(f'/api/v1/dataset/{adm}', {"owners": [1, I['svc_uid']]}); show('admin PUT owners [1, svc]', st, j, 120)
st, j = s.put(f'/api/v1/dataset/{adm}', body); show('svc PUT columns after owner add', st, j, 200)
st, j = s.req('GET', f'/api/v1/dataset/{adm}'); print([(c['column_name'], c['verbose_name']) for c in j['result']['columns']])

print('\n=== 5-2 4개 권한 중 하나씩 뺐을 때 (소유한 데이터셋 scratch2에서 GET / PUT columns / refresh / POST 등록)')
rid = I['svc_role']; P = I['svc_perms']; names = {P[0]: 'can_read Dataset', P[1]: 'can_write Dataset', P[2]: 'schema_access bi_data', P[3]: 'can_read SecurityRestApi'}
def setp(ids): return a.body('POST', f'/api/v1/security/roles/{rid}/permissions', {"permission_view_menu_ids": sorted(ids)})[0]
import time
def trial(ids, label):
    setp(ids); t = U('a27_svc', envval('SUPERSET_ADMIN_PASSWORD')); lst = t.login(); cst = t.csrf_fetch(); out = {'login': lst, 'csrf': cst}
    g = t.req('GET', f'/api/v1/dataset/{sc2}'); out['GET'] = g[0]
    cols = g[1]['result']['columns'] if g[0] == 200 else [{"id": c['id'], "column_name": c['column_name']} for c in s.req('GET', f'/api/v1/dataset/{sc2}')[1]['result']['columns']] if False else None
    if cols is None:
        st0, j0 = a.req('GET', f'/api/v1/dataset/{sc2}'); cols = j0['result']['columns']
    body2 = {"columns": [{"id": c['id'], "column_name": c['column_name'], "verbose_name": 'V_' + c['column_name']} for c in cols]}
    out['PUT columns'] = t.put(f'/api/v1/dataset/{sc2}', body2)[0] if t.csrf else None
    out['refresh'] = t.put(f'/api/v1/dataset/{sc2}/refresh', {})[0] if t.csrf else None
    out['POST new'] = None
    if t.csrf:
        st, j = t.post('/api/v1/dataset/', {"database": 1, "schema": "bi_data", "table_name": f"a27_tmp_{time.time_ns()}", "sql": "SELECT * FROM bi_data.dv_1"}); out['POST new'] = st
        if st == 201: a.delete(f"/api/v1/dataset/{j['id']}")
    print(f'{label:40s}', out); return out
trial(P, 'all 4')
for p in P: trial([x for x in P if x != p], 'minus ' + names[p])
setp(P)
print('restored role perms', a.req('GET', f'/api/v1/security/roles/{rid}/permissions/')[1]['result'] and [(r['permission_name'], r['view_menu_name']) for r in a.req('GET', f'/api/v1/security/roles/{rid}/permissions/')[1]['result']])
print('\n=== 5-3 오래된 열 id (refresh로 바뀐 id)로 PUT')
st, j = s.put(f'/api/v1/dataset/{sc2}', {"columns": [{"id": 26, "column_name": "c_4", "verbose_name": "이익"}]}); show('PUT stale id 26 (deleted by refresh)', st, j, 200)
