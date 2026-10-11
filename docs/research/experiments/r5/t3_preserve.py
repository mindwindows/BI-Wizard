from r5lib import *
I = load_ids(); did = I['ds']
s = U('a27_svc', envval('SUPERSET_ADMIN_PASSWORD')); s.start()
au = U('a27_author1', envval('SUPERSET_ADMIN_PASSWORD')); au.start()
KEYS = ('id','column_name','type','verbose_name','description','is_dttm','groupby','filterable','expression')
def snap(label=''):
    st, j = s.req('GET', f'/api/v1/dataset/{did}'); r = j['result']
    print(f'  [{label}] main_dttm_col={r["main_dttm_col"]!r} metrics={[m["metric_name"] for m in r["metrics"]]} n_cols={len(r["columns"])}')
    for c in sorted(r['columns'], key=lambda c: c['id']): print('   ', {k: c.get(k) for k in KEYS})
    return r
def chartdata(label):
    out = {}
    for name, cid in (('table', I['chart_table']), ('bar', I['chart_bar'])):
        st, j = au.req('GET', f'/api/v1/chart/{cid}/data/')
        res = (j.get('result') or [{}])[0] if isinstance(j, dict) else {}
        out[name] = (st, res.get('rowcount'), (res.get('error') or '')[:100] if isinstance(res, dict) else '', list((res.get('colnames') or [])))
    print('  chart data', label, out); return out
def sql(q):
    import subprocess
    r = subprocess.run(['docker','exec','-i','g3x-postgres-1','psql','-U','bi_wizard','-d','bi_wizard','-X','-q','-v','ON_ERROR_STOP=1'], input=q, capture_output=True, text=True); print('  SQL:', q.strip().replace('\n',' ')[:150], '->', (r.stdout+r.stderr).strip()[:200])

print('=== 3-0 기준: 차트 데이터'); snap('start'); chartdata('start')
print('\n=== 3a refresh 후 verbose_name 유지?')
st, j = s.put(f'/api/v1/dataset/{did}/refresh', {}); show('refresh', st, j); snap('after refresh'); chartdata('after refresh')

print('\n=== 3b 뷰에 c_4 추가 후 refresh')
sql("ALTER TABLE bi_data.ds_1 ADD COLUMN c_4 numeric; UPDATE bi_data.ds_1 SET c_4 = c_1 - c_2; CREATE OR REPLACE VIEW bi_data.dv_1 AS SELECT c_1, c_2, c_3, team, period, c_4 FROM bi_data.ds_1;")
st, j = s.put(f'/api/v1/dataset/{did}/refresh', {}); show('refresh', st, j); r = snap('after add c_4'); chartdata('after add c_4')
c4 = [c['id'] for c in r['columns'] if c['column_name'] == 'c_4'][0]
print('\n  -- 3b-2 새 열에 표시 이름: 모든 열을 다시 보내지 않고 c_4만 보내면?')
# DANGER on main; do on a scratch copy instead
st, j = s.post('/api/v1/dataset/', {"database": 1, "schema": "bi_data", "table_name": "[a27 scratch2] c4", "sql": "SELECT * FROM bi_data.dv_1"}); sc2 = j['id']; I['scratch2'] = sc2; save_ids(I)
st, j = s.req('GET', f'/api/v1/dataset/{sc2}'); cc = {c['column_name']: c['id'] for c in j['result']['columns']}; print('  scratch2 cols', cc)
st, j = s.put(f'/api/v1/dataset/{sc2}', {"columns": [{"id": cc['c_4'], "column_name": "c_4", "verbose_name": "이익"}]}); show('PUT only c_4', st, j, 200)
st, j = s.req('GET', f'/api/v1/dataset/{sc2}'); print('  scratch2 cols after PUT only c_4:', [(c['id'], c['column_name'], c['verbose_name']) for c in j['result']['columns']])
print('  -- 3b-3 main: 기존 열 id + 새 열 id를 모두 보내 병합 (GET → verbose_name 채움 → PUT)')
r = snap('main before PUT'); 
names = {'c_1': '매출', 'c_2': '비용', 'c_3': '상태', 'team': '팀', 'period': '기간', 'c_4': '이익'}
body = {"columns": [{"id": c['id'], "column_name": c['column_name'], "verbose_name": names[c['column_name']]} for c in r['columns']]}
print('  REQUEST', json.dumps(body, ensure_ascii=False)); st, j = s.put(f'/api/v1/dataset/{did}', body); show('PUT all 6', st, j, 200); snap('after PUT all 6'); chartdata('after PUT 6')

print('\n=== 3d 표시 이름만 바꿈 → 저장된 차트 영향')
st, j = au.req('GET', f'/api/v1/chart/{I["chart_table"]}'); p0 = j['result']['params']; q0 = j['result'].get('query_context')
body = {"columns": [{"id": c['id'], "column_name": c['column_name'], "verbose_name": {"c_1": "총매출", "c_2": "총비용"}.get(c['column_name'], c['verbose_name'])} for c in snap('before rename')['columns']]}
st, j = s.put(f'/api/v1/dataset/{did}', body); show('PUT rename c_1->총매출, c_2->총비용', st, j, 100)
snap('after rename'); chartdata('after rename')
st, j = au.req('GET', f'/api/v1/chart/{I["chart_table"]}'); print('  chart params unchanged:', j['result']['params'] == p0)
st, j = au.req('GET', f'/api/v1/dashboard/{I["dash"]}'); print('  dashboard native filters still ref column names:', [(f['name'], f['targets']) for f in json.loads(j['result']['json_metadata'])['native_filter_configuration']])

print('\n=== 3c 뷰에서 c_4 제거 후 refresh')
sql("DROP VIEW bi_data.dv_1; CREATE VIEW bi_data.dv_1 AS SELECT c_1, c_2, c_3, team, period FROM bi_data.ds_1;")
st, j = s.put(f'/api/v1/dataset/{did}/refresh', {}); show('refresh', st, j); snap('after remove c_4'); chartdata('after remove c_4')
st, j = s.req('GET', f'/api/v1/dataset/{sc2}'); print('  scratch2 cols (c_4 remains?) before refresh:', [(c['id'], c['column_name'], c['verbose_name']) for c in j['result']['columns']])
st, j = s.put(f'/api/v1/dataset/{sc2}/refresh', {}); show('scratch2 refresh', st, j)
st, j = s.req('GET', f'/api/v1/dataset/{sc2}'); print('  scratch2 cols after refresh:', [(c['id'], c['column_name'], c['verbose_name']) for c in j['result']['columns']])
print('\n=== 3b-4 c_4 다시 추가(같은 이름) → 이전 표시 이름 복원되나?')
sql("DROP VIEW bi_data.dv_1; CREATE VIEW bi_data.dv_1 AS SELECT c_1, c_2, c_3, team, period, c_4 FROM bi_data.ds_1;")
st, j = s.put(f'/api/v1/dataset/{did}/refresh', {}); show('refresh', st, j); snap('after re-add c_4')
