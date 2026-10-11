from r5lib import *
I = load_ids(); did = I['ds']
s = U('a27_svc', envval('SUPERSET_ADMIN_PASSWORD')); s.start()
st, j = s.req('GET', f'/api/v1/dataset/{did}'); r = j['result']
new = {'c_1': '총매출', 'c_2': '총비용'}
body = {"columns": [{"id": c['id'], "column_name": c['column_name'], "verbose_name": new.get(c['column_name'], c['verbose_name'])} for c in r['columns']]}
print('REQUEST', json.dumps(body, ensure_ascii=False)); st, j = s.put(f'/api/v1/dataset/{did}', body); show('PUT rename', st, j, 120)
