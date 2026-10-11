from r5lib import *
I = load_ids(); did = I['ds']; sc = I['scratch']
s = U('a27_svc', envval('SUPERSET_ADMIN_PASSWORD')); s.start()
KEYS = ('id','column_name','type','verbose_name','description','is_dttm','groupby','filterable','expression')
def snap(d, label=''):
    st, j = s.req('GET', f'/api/v1/dataset/{d}'); r = j['result']
    print(f'  [{label}] table_name={r["table_name"]!r} main_dttm_col={r["main_dttm_col"]!r} metrics={[m["metric_name"] for m in r["metrics"]]} n_cols={len(r["columns"])}')
    for c in sorted(r['columns'], key=lambda c: c['id']): print('   ', {k: c.get(k) for k in KEYS})
    return r
def put(d, body, label, qs=''):
    st, j = s.put(f'/api/v1/dataset/{d}{qs}', body); show(label, st, j, 500); return st, j
ids = {c['column_name']: c['id'] for c in s.req('GET', f'/api/v1/dataset/{sc}')[1]['result']['columns']}
print('scratch ids', ids)

print('\n=== a) id+verbose_name, column_name 생략')
put(sc, {"columns": [{"id": ids['c_1'], "verbose_name": "매출"}]}, 'PUT w/o column_name'); 
print('\n=== b) 알 수 없는 필드')
put(sc, {"columns": [{"id": ids['c_1'], "column_name": "c_1", "verbose_name": "매출", "foo": 1}]}, 'PUT unknown field')
print('\n=== c) 다른 데이터셋의 열 id (main ds 열 1)')
put(sc, {"columns": [{"id": 1, "column_name": "c_1", "verbose_name": "x"}]}, 'PUT foreign column id'); snap(did, 'main unchanged?')
print('\n=== d) 열 id 와 다른 column_name (id=c_2 의 column_name을 zzz로)')
snap(sc, 'before d')
put(sc, {"columns": [{"id": ids['c_1'], "column_name": "c_1", "verbose_name": "매출"}, {"id": ids['c_2'], "column_name": "c_2", "verbose_name": "비용"}, {"id": ids['c_3'], "column_name": "c_3", "verbose_name": "상태"}, {"id": ids['team'], "column_name": "team", "verbose_name": "팀"}, {"id": ids['period'], "column_name": "period", "verbose_name": "기간"}]}, 'PUT all 5 (scratch)')
put(sc, {"columns": [{"id": ids['c_2'], "column_name": "zzz", "verbose_name": "비용2"}, {"id": ids['c_1'], "column_name": "c_1"}, {"id": ids['c_3'], "column_name": "c_3"}, {"id": ids['team'], "column_name": "team"}, {"id": ids['period'], "column_name": "period"}]}, 'PUT column_name changed (c_2->zzz)')
snap(sc, 'after d')
put(sc, {"columns": [{"id": ids['c_2'], "column_name": "c_2", "verbose_name": "비용"}, {"id": ids['c_1'], "column_name": "c_1"}, {"id": ids['c_3'], "column_name": "c_3"}, {"id": ids['team'], "column_name": "team"}, {"id": ids['period'], "column_name": "period"}]}, 'PUT restore c_2')

print('\n=== e) 일부 열만 보내기 (c_1 한 개만)')
put(sc, {"columns": [{"id": ids['c_1'], "column_name": "c_1", "verbose_name": "매출(부분)"}]}, 'PUT only c_1')
r = snap(sc, 'after partial'); print('main_dttm_col after partial:', r['main_dttm_col'])
print('\n=== f) 이어서 refresh')
st, j = s.put(f'/api/v1/dataset/{sc}/refresh', {}); show('refresh', st, j)
r = snap(sc, 'after refresh (restored cols)')
print('\n=== g) columns: [] (빈 배열)')
put(sc, {"columns": []}, 'PUT empty columns'); snap(sc, 'after empty')
st, j = s.put(f'/api/v1/dataset/{sc}/refresh', {}); show('refresh', st, j); snap(sc, 'after refresh')
print('\n=== h) table_name + columns 같은 호출')
ids = {c['column_name']: c['id'] for c in s.req('GET', f'/api/v1/dataset/{sc}')[1]['result']['columns']}
allcols = lambda vn: [{"id": i, "column_name": n, **({"verbose_name": vn[n]} if n in vn else {})} for n, i in ids.items()]
put(sc, {"table_name": "[a27 scratch] 이름 변경", "columns": allcols({"c_1": "매출", "c_2": "비용", "c_3": "상태", "team": "팀", "period": "기간"})}, 'PUT table_name+columns')
snap(sc, 'after h')
print('\n=== i) verbose_name null / 빈 문자열 / description')
put(sc, {"columns": allcols({"c_1": None, "c_2": "", "c_3": "상태"})}, 'PUT verbose null (c_1) "" (c_2)'); snap(sc, 'after i')
put(sc, {"columns": [dict(x, **({"description": "내부 번호 c_1 = 매출"} if x['column_name']=='c_1' else {})) for x in allcols({"c_1": "매출", "c_2": "비용", "c_3": "상태", "team": "팀", "period": "기간"})]}, 'PUT description'); snap(sc, 'after description')
print('\n=== j) 긴 verbose_name (2000자) / 특수문자')
put(sc, {"columns": allcols({"c_1": "매출 \"따옴표\" <b>x</b> 'a' %s {x}"})}, 'PUT special chars'); 
put(sc, {"columns": allcols({"c_2": "가"*2000})}, 'PUT 2000-char verbose_name')
r = snap(sc, 'after j')
print('len verbose c_2', [len(c['verbose_name'] or '') for c in r['columns'] if c['column_name']=='c_2'])
