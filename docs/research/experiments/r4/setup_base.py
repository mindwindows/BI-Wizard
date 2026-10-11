import sys, json
sys.path.insert(0, '/home/user/BI-Wizard/_workspace/gate3/experiments/r4')
from lib import *
a = admin()
st, j = a.req('GET', '/api/v1/database/'); print('dbs', st, [(r['id'], r['database_name']) for r in j['result']])
DB = j['result'][0]['id']
ids = {}
def mk(path, body, label):
    st, j = a.post(path, body); print(label, st, j if st not in (200, 201) else (j.get('id') or j)); assert st in (200, 201), j; return j
ids['ds_phys'] = mk('/api/v1/dataset/', {"database": DB, "schema": "bi_data", "table_name": "dv_x25"}, 'ds_phys')['id']
ids['ds_virt'] = mk('/api/v1/dataset/', {"database": DB, "schema": "bi_data", "table_name": "x25 가상 데이터셋", "sql": "SELECT * FROM bi_data.dv_x25"}, 'ds_virt')['id']
ds = ids['ds_phys']
# annotation layer
lay = mk('/api/v1/annotation_layer/', {"name": "x25_layer", "descr": "x25"}, 'layer')['id']
mk(f'/api/v1/annotation_layer/{lay}/annotation/', {"short_descr": "e1", "long_descr": "event", "start_dttm": "2025-03-01T00:00:00", "end_dttm": "2025-03-02T00:00:00"}, 'annotation')
ids['layer'] = lay
M = lambda: {"expressionType": "SIMPLE", "column": {"column_name": "amount", "type": "NUMERIC"}, "aggregate": "SUM", "label": "SUM(amount)", "hasCustomLabel": False, "optionName": "metric_sum_amount"}
TF = lambda: [{"expressionType": "SIMPLE", "subject": "period", "operator": "TEMPORAL_RANGE", "comparator": "No filter", "clause": "WHERE", "isExtra": False}]
def chart(name, viz, extra, dsid=None):
    dsid = dsid or ds
    p = {"viz_type": viz, "datasource": f"{dsid}__table", "adhoc_filters": TF(), "row_limit": 1000}
    p.update(extra)
    j = mk('/api/v1/chart/', {"slice_name": name, "viz_type": viz, "datasource_id": dsid, "datasource_type": "table", "params": json.dumps(p)}, name)
    return j['id']
ann = [{"name": "ev", "annotationType": "EVENT", "sourceType": "NATIVE", "value": lay, "show": True, "showLabel": False, "opacity": "", "style": "solid", "color": None, "width": 1, "hideLine": False, "overrides": {}},
       {"name": "fm", "annotationType": "FORMULA", "sourceType": "", "value": "y=1000", "show": True, "showLabel": False, "opacity": "", "style": "solid", "color": None, "width": 1, "overrides": {}}]
C = {}
C['table'] = chart('x25 표', 'table', {"query_mode": "aggregate", "groupby": ["team", "product"], "metrics": [M()], "all_columns": [], "percent_metrics": [], "order_desc": True, "server_page_length": 10, "table_timestamp_format": "smart_date"})
C['bar'] = chart('x25 막대', 'echarts_timeseries_bar', {"x_axis": "period", "time_grain_sqla": "P1M", "metrics": [M()], "groupby": ["team"], "orientation": "vertical", "show_legend": True, "row_limit": 10000})
C['line'] = chart('x25 선(주석)', 'echarts_timeseries_line', {"x_axis": "period", "time_grain_sqla": "P1M", "metrics": [M()], "groupby": ["team"], "annotation_layers": ann, "show_legend": True, "row_limit": 10000})
C['big'] = chart('x25 큰 숫자', 'big_number_total', {"metric": M(), "header_font_size": 0.4, "subheader_font_size": 0.15, "y_axis_format": "SMART_NUMBER"})
C['pie'] = chart('x25 파이', 'pie', {"groupby": ["product"], "metric": M(), "sort_by_metric": True, "color_scheme": "supersetColors", "show_labels": True, "label_type": "key_value_percent", "show_legend": True, "donut": False, "outerRadius": 70, "innerRadius": 30})
C['pivot'] = chart('x25 피벗', 'pivot_table_v2', {"groupbyRows": ["team"], "groupbyColumns": ["product"], "metrics": [M()], "metricsLayout": "COLUMNS", "aggregateFunction": "Sum", "rowOrder": "key_a_to_z", "colOrder": "key_a_to_z", "transposePivot": False, "combineMetric": False, "rowSubtotalPosition": "Top", "colSubtotalPosition": "Top", "rowTotals": True, "colTotals": True, "valueFormat": "SMART_NUMBER", "dateFormat": "smart_date", "row_limit": 10000})
C['virt_table'] = chart('x25 가상 표', 'table', {"query_mode": "aggregate", "groupby": ["team"], "metrics": [M()], "all_columns": [], "percent_metrics": [], "order_desc": True, "server_page_length": 10}, ds_virt := ids['ds_virt'])
C['bigtrend'] = chart('x25 큰 숫자 추세', 'big_number', {"x_axis": "period", "time_grain_sqla": "P1M", "metric": M(), "show_trend_line": True, "start_y_axis_at_zero": True, "color_picker": {"r": 0, "g": 122, "b": 135, "a": 1}, "header_font_size": 0.4, "subheader_font_size": 0.15, "y_axis_format": "SMART_NUMBER", "rolling_type": "None", "compare_lag": 1, "comparison_type": "values"})
ids['charts'] = C
def pos_for(title, tabs, md=True):
    pos = {"DASHBOARD_VERSION_KEY": "v2", "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["TABS-top"]},
           "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": [], "parents": ["ROOT_ID"]},
           "HEADER_ID": {"id": "HEADER_ID", "type": "HEADER", "meta": {"text": title}},
           "TABS-top": {"type": "TABS", "id": "TABS-top", "children": [], "parents": ["ROOT_ID"], "meta": {}}}
    n = 0
    for ti, (tname, rows) in enumerate(tabs, 1):
        tid = f"TAB-{ti}"
        pos["TABS-top"]["children"].append(tid)
        pos[tid] = {"type": "TAB", "id": tid, "children": [], "parents": ["ROOT_ID", "TABS-top"], "meta": {"text": tname, "defaultText": "Tab title", "placeholder": "Tab title"}}
        for ri, row in enumerate(rows, 1):
            rid = f"ROW-{ti}-{ri}"; pos[tid]["children"].append(rid)
            pos[rid] = {"type": "ROW", "id": rid, "children": [], "parents": ["ROOT_ID", "TABS-top", tid], "meta": {"background": "BACKGROUND_TRANSPARENT"}}
            for item in row:
                n += 1; cid = f"CHART-{ti}-{n}" if isinstance(item, int) else f"MARKDOWN-{ti}-{n}"
                pos[rid]["children"].append(cid)
                if isinstance(item, int):
                    pos[cid] = {"type": "CHART", "id": cid, "children": [], "parents": ["ROOT_ID", "TABS-top", tid, rid], "meta": {"width": 4, "height": 50, "chartId": item, "sliceName": f"chart{item}"}}
                else:
                    pos[cid] = {"type": "MARKDOWN", "id": cid, "children": [], "parents": ["ROOT_ID", "TABS-top", tid, rid], "meta": {"width": 4, "height": 50, "code": item}}
    return pos
def nf(fid, name, ftype, targets, cv, ds_default=None):
    return {"id": fid, "name": name, "filterType": ftype, "targets": targets, "defaultDataMask": {"extraFormData": {}, "filterState": {}, "ownState": {}}, "controlValues": cv, "cascadeParentIds": [], "scope": {"rootPath": ["ROOT_ID"], "excluded": []}, "type": "NATIVE_FILTER", "description": ""}
FILTERS = [nf('NATIVE_FILTER-team', '팀', 'filter_select', [{"datasetId": ds, "column": {"name": "team"}}], {"enableEmptyFilter": False, "defaultToFirstItem": False, "multiSelect": True, "searchAllOptions": False, "inverseSelection": False}),
           nf('NATIVE_FILTER-time', '기간', 'filter_time', [{}], {}),
           nf('NATIVE_FILTER-amount', '금액', 'filter_range', [{"datasetId": ds, "column": {"name": "amount"}}], {"enableEmptyFilter": False, "inverseSelection": False})]
def dash(title, tabs, filters=True, css=''):
    jm = {"native_filter_configuration": FILTERS if filters else [], "timed_refresh_immune_slices": [], "expanded_slices": {}, "refresh_frequency": 0, "default_filters": "{}", "color_scheme": "", "label_colors": {}, "shared_label_colors": [], "map_label_colors": {}, "color_scheme_domain": [], "cross_filters_enabled": True, "chart_configuration": {}}
    j = mk('/api/v1/dashboard/', {"dashboard_title": title, "position_json": json.dumps(pos_for(title, tabs)), "json_metadata": json.dumps(jm), "css": css, "published": True}, title)
    return j['id']
tab1 = [[C['table'], C['bar'], C['line']], [C['big'], C['pie'], C['pivot']], ["# x25 마크다운\n\n설명 텍스트"]]
tab2 = [[C['virt_table'], C['bigtrend']]]
dA = dash('x25_dashA', [("탭1", tab1), ("탭2", tab2)], css='.dashboard-header { background: #f5f5f5; }')
dB = dash('x25_dashB', [("탭1", [[C['table'], C['pie']]])], filters=False)
dC = dash('x25_dashC_noembed', [("탭1", [[C['table']]])], filters=False)
ids['dA'], ids['dB'], ids['dC'] = dA, dB, dC
allc = list(C.values())
# link charts to dashboards (chart -> dashboards)
links = {C['table']: [dA, dB, dC], C['pie']: [dA, dB], C['bar']: [dA], C['line']: [dA], C['big']: [dA], C['pivot']: [dA], C['virt_table']: [dA], C['bigtrend']: [dA]}
for cid, ds_ in links.items():
    st, j = a.put(f'/api/v1/chart/{cid}', {"dashboards": ds_}); print('link', cid, st)
# embed A and B (not C)
for k, d in (('embA', dA), ('embB', dB)):
    st, j = a.post(f'/api/v1/dashboard/{d}/embedded', {"allowed_domains": []}); print(k, st, j); ids[k] = j['result']['uuid']
json.dump(ids, open('/home/user/BI-Wizard/_workspace/gate3/experiments/r4/ids.json', 'w'), indent=1); print(ids)
