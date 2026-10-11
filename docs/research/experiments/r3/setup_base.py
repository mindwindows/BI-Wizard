from r3lib import *
a = admin()
ids = {}
for t in ('dv_1', 'dv_2', 'dv_3'):
    st, j = a.post('/api/v1/dataset/', {"database": 1, "schema": "bi_data", "table_name": t}); print(t, st, j if st != 201 else j['id'])
    ids[t] = j['id']
st, j = a.post('/api/v1/dataset/', {"database": 1, "schema": "public", "table_name": "x20_pub"}); print('x20_pub', st, j if st != 201 else j['id']); ids['x20_pub'] = j.get('id')

def chart(name, ds, cols):
    p = {"viz_type": "table", "datasource": f"{ds}__table", "query_mode": "raw", "all_columns": cols, "row_limit": 1000, "order_desc": True, "server_pagination": False, "adhoc_filters": []}
    st, j = a.post('/api/v1/chart/', {"slice_name": name, "viz_type": "table", "datasource_id": ds, "datasource_type": "table", "params": json.dumps(p)})
    print(name, st, j.get('id') if st == 201 else j); return j['id']
c1 = chart('x21_chart1 dv_1', ids['dv_1'], ['period_a', 'team', 'value'])
c2 = chart('x21_chart2 dv_2', ids['dv_2'], ['base_date', 'team', 'value'])
ids['c1'] = c1; ids['c2'] = c2

def dash(title, fid, default):
    pos = {"DASHBOARD_VERSION_KEY": "v2", "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
           "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": ["ROW-1"], "parents": ["ROOT_ID"]},
           "HEADER_ID": {"id": "HEADER_ID", "type": "HEADER", "meta": {"text": title}},
           "ROW-1": {"type": "ROW", "id": "ROW-1", "children": ["CHART-1", "CHART-2"], "parents": ["ROOT_ID", "GRID_ID"], "meta": {"background": "BACKGROUND_TRANSPARENT"}}}
    for i, (cid, nm) in enumerate(((c1, 'x21_chart1 dv_1'), (c2, 'x21_chart2 dv_2')), 1):
        pos[f"CHART-{i}"] = {"type": "CHART", "id": f"CHART-{i}", "children": [], "parents": ["ROOT_ID", "GRID_ID", "ROW-1"], "meta": {"width": 6, "height": 50, "chartId": cid, "sliceName": nm}}
    if default:
        dm = {"extraFormData": {"filters": [{"col": "team", "op": "IN", "val": default}]}, "filterState": {"value": default}, "ownState": {}}
    else:
        dm = {"extraFormData": {}, "filterState": {}, "ownState": {}}
    nf = [{"id": fid, "name": "팀", "filterType": "filter_select", "targets": [{"datasetId": ids['dv_1'], "column": {"name": "team"}}], "defaultDataMask": dm,
           "controlValues": {"enableEmptyFilter": False, "defaultToFirstItem": False, "multiSelect": True, "searchAllOptions": False, "inverseSelection": False},
           "cascadeParentIds": [], "scope": {"rootPath": ["ROOT_ID"], "excluded": []}, "type": "NATIVE_FILTER", "description": ""}]
    jm = {"native_filter_configuration": nf, "timed_refresh_immune_slices": [], "expanded_slices": {}, "refresh_frequency": 0, "default_filters": "{}", "color_scheme": "", "label_colors": {}, "shared_label_colors": [], "map_label_colors": {}, "color_scheme_domain": [], "cross_filters_enabled": True, "chart_configuration": {}}
    st, j = a.post('/api/v1/dashboard/', {"dashboard_title": title, "position_json": json.dumps(pos), "json_metadata": json.dumps(jm)}); print(title, st, j.get('id') if st == 201 else j)
    return j['id']
d1 = dash('x21_dash_nodefault', 'NATIVE_FILTER-teamsel1', None)
d2 = dash('x21_dash_default3', 'NATIVE_FILTER-teamsel2', ['팀3'])
for cid in (c1, c2):
    print('link', cid, a.put(f'/api/v1/chart/{cid}', {"dashboards": [d1, d2]})[0])
ids['d1'] = d1; ids['d2'] = d2
json.dump(ids, open('base_ids.json', 'w')); print(ids)
