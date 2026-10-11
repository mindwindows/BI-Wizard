from r5lib import *
I = load_ids(); did = I['ds']
au = U('a27_author1', envval('SUPERSET_ADMIN_PASSWORD')); print('author login/csrf', au.login(), au.csrf_fetch())
# dataset visible to author?
st, j = au.req('GET', f'/api/v1/dataset/{did}'); print('author GET dataset', st)
cols = {c['column_name']: c for c in j['result']['columns']}
def tbl_chart():
    p = {"viz_type": "table", "datasource": f"{did}__table", "query_mode": "raw", "all_columns": ["c_1", "c_2", "c_3", "team", "period"], "row_limit": 1000, "order_desc": True, "server_pagination": False, "adhoc_filters": [], "table_timestamp_format": "smart_date"}
    st, j = au.post('/api/v1/chart/', {"slice_name": "a27 표 차트", "viz_type": "table", "datasource_id": did, "datasource_type": "table", "params": json.dumps(p)}); show('chart table', st, j, 200); return j['id']
def bar_chart():
    m = {"expressionType": "SIMPLE", "column": {"column_name": "c_1", "type": "DECIMAL", "id": cols['c_1']['id']}, "aggregate": "SUM", "label": "SUM(c_1)", "hasCustomLabel": False, "optionName": "metric_a27_1"}
    p = {"viz_type": "echarts_timeseries_bar", "datasource": f"{did}__table", "x_axis": "period", "time_grain_sqla": "P1M", "x_axis_sort_asc": True, "metrics": [m], "groupby": ["team"], "adhoc_filters": [], "row_limit": 10000, "orientation": "vertical", "show_legend": True, "legendType": "scroll", "legendOrientation": "top", "x_axis_title_margin": 15, "y_axis_title_margin": 15, "x_axis_title": "", "y_axis_title": "", "rich_tooltip": True, "tooltipTimeFormat": "smart_date", "y_axis_format": "SMART_NUMBER", "truncateYAxis": False, "stack": None, "comparison_type": "values", "zoomable": False, "extra_form_data": {}, "order_desc": True, "contributionMode": None}
    st, j = au.post('/api/v1/chart/', {"slice_name": "a27 막대 차트", "viz_type": "echarts_timeseries_bar", "datasource_id": did, "datasource_type": "table", "params": json.dumps(p)}); show('chart bar', st, j, 200); return j['id']
c1 = tbl_chart(); c2 = bar_chart()
pos = {"DASHBOARD_VERSION_KEY": "v2", "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
       "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": ["ROW-1"], "parents": ["ROOT_ID"]},
       "HEADER_ID": {"id": "HEADER_ID", "type": "HEADER", "meta": {"text": "a27 대시보드"}},
       "ROW-1": {"type": "ROW", "id": "ROW-1", "children": ["CHART-1", "CHART-2"], "parents": ["ROOT_ID", "GRID_ID"], "meta": {"background": "BACKGROUND_TRANSPARENT"}}}
for i, (cid, nm) in enumerate(((c1, 'a27 표 차트'), (c2, 'a27 막대 차트')), 1):
    pos[f"CHART-{i}"] = {"type": "CHART", "id": f"CHART-{i}", "children": [], "parents": ["ROOT_ID", "GRID_ID", "ROW-1"], "meta": {"width": 6, "height": 50, "chartId": cid, "sliceName": nm}}
def nf(fid, name, col):
    return {"id": fid, "name": name, "filterType": "filter_select", "targets": [{"datasetId": did, "column": {"name": col}}], "defaultDataMask": {"extraFormData": {}, "filterState": {}, "ownState": {}},
            "controlValues": {"enableEmptyFilter": False, "defaultToFirstItem": False, "multiSelect": True, "searchAllOptions": False, "inverseSelection": False}, "cascadeParentIds": [], "scope": {"rootPath": ["ROOT_ID"], "excluded": []}, "type": "NATIVE_FILTER", "description": ""}
jm = {"native_filter_configuration": [nf("NATIVE_FILTER-a27team", "팀", "team"), nf("NATIVE_FILTER-a27status", "상태", "c_3")], "timed_refresh_immune_slices": [], "expanded_slices": {}, "refresh_frequency": 0, "default_filters": "{}", "color_scheme": "", "label_colors": {}, "shared_label_colors": [], "map_label_colors": {}, "color_scheme_domain": [], "cross_filters_enabled": True, "chart_configuration": {}}
st, j = au.post('/api/v1/dashboard/', {"dashboard_title": "a27 대시보드", "position_json": json.dumps(pos), "json_metadata": json.dumps(jm), "published": True}); show('dashboard', st, j, 200); d1 = j['id']
for cid in (c1, c2): print('link', cid, au.put(f'/api/v1/chart/{cid}', {"dashboards": [d1]})[0])
I.update({'chart_table': c1, 'chart_bar': c2, 'dash': d1}); save_ids(I)
