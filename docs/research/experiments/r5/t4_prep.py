from r5lib import *
I = load_ids(); did = I['ds']
s = U('a27_svc', envval('SUPERSET_ADMIN_PASSWORD')); s.start()
st, j = s.req('GET', f'/api/v1/dataset/{did}'); r = j['result']
names = {'c_1': ('매출', '매출액(원)'), 'c_2': ('비용', None), 'c_3': ('상태', None), 'team': ('팀', None), 'period': ('기간', None), 'c_4': ('이익', None)}
body = {"columns": [dict({"id": c['id'], "column_name": c['column_name'], "verbose_name": names[c['column_name']][0]}, **({"description": names[c['column_name']][1]} if names[c['column_name']][1] else {})) for c in r['columns']]}
st, j = s.put(f'/api/v1/dataset/{did}', body); show('PUT names for UI phase A', st, j, 150)
st, j = s.req('GET', f'/api/v1/dataset/{did}'); print([(c['id'], c['column_name'], c['verbose_name'], c['description']) for c in j['result']['columns']])
