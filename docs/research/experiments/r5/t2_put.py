from r5lib import *
I = load_ids(); did = I['ds']
s = U('a27_svc', envval('SUPERSET_ADMIN_PASSWORD')); s.start()
KEYS = ('id','column_name','type','verbose_name','description','is_dttm','groupby','filterable','expression','is_active','python_date_format','extra')
def snap(did, label=''):
    st, j = s.req('GET', f'/api/v1/dataset/{did}'); r = j['result']
    print(f'  [{label}] table_name={r["table_name"]!r} main_dttm_col={r["main_dttm_col"]!r} metrics={[(m["metric_name"]) for m in r["metrics"]]} sql={r["sql"]!r}')
    for c in sorted(r['columns'], key=lambda c: c['id']): print('   ', {k: c.get(k) for k in KEYS})
    return r
def put(did, body, label, qs=''):
    st, j = s.put(f'/api/v1/dataset/{did}{qs}', body); show(label, st, j, 700); return st, j

print('=== 2-1 최소 본문: 5개 열 모두 id+column_name+verbose_name')
snap(did, 'before')
names = {1: ('c_1', '매출'), 2: ('c_2', '비용'), 3: ('c_3', '상태'), 4: ('team', '팀'), 5: ('period', '기간')}
body = {"columns": [{"id": i, "column_name": n, "verbose_name": v} for i, (n, v) in names.items()]}
print('REQUEST', json.dumps(body, ensure_ascii=False))
put(did, body, 'PUT minimal')
r = snap(did, 'after')

print('\n=== 2-2 id 없이 column_name+verbose_name만 (id 생략)')
# use a scratch dataset to avoid creating duplicate columns on the main one
st, j = s.post('/api/v1/dataset/', {"database": 1, "schema": "bi_data", "table_name": "[a27 scratch] 부분 시험", "sql": "SELECT * FROM bi_data.dv_1"}); show('POST scratch', st, j, 80)
sc = j['id']; I['scratch'] = sc; save_ids(I)
sr = snap(sc, 'scratch initial')
put(sc, {"columns": [{"column_name": "c_1", "verbose_name": "매출"}]}, 'PUT columns w/o id (c_1)')
snap(sc, 'scratch after no-id')
