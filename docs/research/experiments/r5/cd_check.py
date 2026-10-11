from r5lib import *
I = load_ids(); did = I['ds']
au = U('a27_author1', envval('SUPERSET_ADMIN_PASSWORD')); au.start()
st, j = au.req('GET', f'/api/v1/chart/{I["chart_table"]}/data/'); print(st, str(j)[:300])
def qc(kind):
    if kind == 'table':
        q = {"columns": ["c_1","c_2","c_3","team","period"], "metrics": [], "orderby": [], "row_limit": 1000, "filters": [], "extras": {"having": "", "where": ""}}
    else:
        m = {"expressionType": "SIMPLE", "column": {"column_name": "c_1"}, "aggregate": "SUM", "label": "SUM(c_1)"}
        q = {"columns": [{"timeGrain": "P1M", "columnType": "BASE_AXIS", "sqlExpression": "period", "label": "period", "expressionType": "SQL"}, "team"], "metrics": [m], "orderby": [[m, False]], "row_limit": 10000, "filters": [], "extras": {"having": "", "where": ""}, "series_columns": ["team"], "is_timeseries": True}
    return {"datasource": {"id": did, "type": "table"}, "queries": [q], "force": True, "result_format": "json", "result_type": "full"}
for k in ('table', 'bar'):
    st, j = au.post('/api/v1/chart/data', qc(k)); r = (j.get('result') or [{}])[0] if isinstance(j, dict) else {}
    print(k, st, r.get('rowcount'), r.get('colnames'), (r.get('error') or '')[:100], str(j)[:200] if st != 200 else '')
