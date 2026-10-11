from r5lib import *
I = load_ids()
s = U('a27_svc', envval('SUPERSET_ADMIN_PASSWORD')); print('login', s.login(), 'csrf', s.csrf_fetch())
st, j = s.post('/api/v1/dataset/', {"database": 1, "schema": "bi_data", "table_name": "[팀1] 월별 실적", "sql": "SELECT * FROM bi_data.dv_1"}); show('POST dataset (svc)', st, j)
did = j['id']; I['ds'] = did; save_ids(I)
st, j = s.req('GET', f'/api/v1/dataset/{did}'); show('GET dataset (svc) summary', st, {k: j['result'][k] for k in ('id','table_name','schema','sql','main_dttm_col','owners','is_sqllab_view')})
cols = j['result']['columns']
json.dump(cols, open('t1_columns_initial.json', 'w'), ensure_ascii=False, indent=1)
for c in cols: print({k: c.get(k) for k in ('id','column_name','type','verbose_name','description','is_dttm','groupby','filterable','expression','is_active','python_date_format','extra','advanced_data_type')})
print('metrics', [(m['id'], m['metric_name'], m['verbose_name']) for m in j['result']['metrics']])
print('GET result keys', sorted(j['result'].keys()))
