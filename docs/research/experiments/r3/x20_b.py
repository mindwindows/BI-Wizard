from r3lib import *
a=admin(); I=json.load(open('base_ids.json')); X=I['x20']
u1=U('x20_author1'); assert u1.start()==200
u2=U('x20_author2'); assert u2.start()==200
def short(j,n=110):
    s=json.dumps(j,ensure_ascii=False) if not isinstance(j,str) else j
    return s[:n]
def cd(sess, ds, metrics=None, where=None, cols=None):
    q={"columns":cols or ["team"],"filters":[],"row_limit":5,"orderby":[]}
    if metrics: q["metrics"]=metrics; q["columns"]=[] if cols is None else cols
    if where: q["extras"]={"where":where}
    return sess.post('/api/v1/chart/data',{"datasource":{"id":ds,"type":"table"},"force":False,"queries":[q],"result_format":"json","result_type":"full"})
print("=== (b) data access of author1 (x20_author_copy + x20_author_schema_bi_data)")
st,j=u1.req('GET','/api/v1/dataset/?q=(page_size:50)'); print('dataset list',st,[(r['id'],r['schema'],r['table_name'],r['kind']) for r in j.get('result',[])] if st==200 else j)
for name,ds in [('dv_1 physical bi_data',1),('dv_2 physical bi_data',2),('x20_virtual (bi_data virtual)',X['virt']),('public.x20_pub',4),('information_schema.tables',X['info'])]:
    st,j=u1.req('GET',f'/api/v1/dataset/{ds}'); st2,j2=cd(u1,ds)
    print(f'  {name}: GET dataset {st}; chart/data {st2}', (j2.get('result') or [{}])[0].get('rowcount') if st2==200 else short(j2,90))
st,j=u1.req('GET','/api/v1/database/'); print('database list',st,short(j if st!=200 else [r['database_name'] for r in j['result']]))
st,j=u1.req('GET','/api/v1/database/1/schemas/'); print('schemas',st,short(j.get('result') if st==200 else j))
st,j=u1.req('GET','/api/v1/database/1/tables/?q=(force:!f,schema_name:public)'); print('tables in public',st,short(j.get('result') if st==200 else j,200))
st,j=u1.req('GET','/api/v1/database/1/tables/?q=(force:!f,schema_name:bi_data)'); print('tables in bi_data',st,short([t['value'] for t in j.get('result',[])] if st==200 else j,200))
st,j=u1.req('GET','/api/v1/chart/'); print('chart list (admin charts visible?)',st,[(r['id'],r['slice_name']) for r in j.get('result',[])] if st==200 else j)
st,j=u1.req('GET','/api/v1/dashboard/'); print('dashboard list',st,[(r['id'],r['dashboard_title']) for r in j.get('result',[])] if st==200 else j)
st,j=u1.req('GET','/api/v1/dashboard/1'); print('GET admin dashboard 1 (unpublished)',st)
print('-- adhoc SQL on accessible dataset trying to read public.x20_pub (DB-level grant exists for bi_readonly in this test)')
st,j=cd(u1,1,metrics=[{"expressionType":"SQL","sqlExpression":"(SELECT count(*) FROM public.x20_pub)","label":"pubcount"}],cols=[]); print('  metric subselect',st,short(j if st!=200 else j['result'][0].get('data'),200))
st,j=cd(u1,1,where="team IN (SELECT team FROM public.x20_pub)"); print('  WHERE subselect',st,short(j if st!=200 else (j['result'][0].get('rowcount'), j['result'][0].get('data')),200))
st,j=cd(u1,1,cols=[{"expressionType":"SQL","sqlExpression":"(SELECT string_agg(team,',') FROM public.x20_pub)","label":"leak"}]) ; print('  adhoc column subselect',st,short(j if st!=200 else j['result'][0].get('data'),200))
st,j=cd(u1,1,cols=[{"expressionType":"SQL","sqlExpression":"(SELECT string_agg(table_name,',') FROM information_schema.tables WHERE table_schema='public')","label":"leak2"}]); print('  adhoc column info_schema',st,short(j if st!=200 else j['result'][0].get('data'),200))

print("=== (c) create/save/own/others")
def chartbody(ds,name): return {"slice_name":name,"viz_type":"table","datasource_id":ds,"datasource_type":"table","params":json.dumps({"viz_type":"table","datasource":f"{ds}__table","query_mode":"raw","all_columns":["period_a","team","value"],"row_limit":100,"adhoc_filters":[]})}
st,j=u1.post('/api/v1/chart/',chartbody(1,'x20_chart_a1_phys')); print('author1 create chart on physical',st,short(j)); ca=j.get('id')
st,j=u1.post('/api/v1/chart/',chartbody(X['virt'],'x20_chart_a1_virt')); print('author1 create chart on virtual',st,short(j)); cv=j.get('id')
st,j=u1.post('/api/v1/chart/',chartbody(4,'x20_chart_a1_public_ds')); print('author1 create chart on public.x20_pub dataset (no access)',st,short(j)); cp=j.get('id')
st,j=u1.post('/api/v1/chart/',chartbody(X['info'],'x20_chart_a1_infoschema_ds')); print('author1 create chart on information_schema dataset',st,short(j)); ci=j.get('id')
st,j=u1.put(f'/api/v1/chart/{ca}',{"slice_name":"x20_chart_a1_phys renamed"}); print('author1 update own chart',st)
st,j=u1.req('GET',f'/api/v1/chart/{ca}'); print('author1 GET own chart owners',st,[o.get('first_name') for o in j['result']['owners']] if st==200 else j)
st,j=u1.put('/api/v1/chart/1',{"slice_name":"hijack"}); print('author1 update ADMIN-owned chart 1',st,short(j,80))
st,j=u1.delete('/api/v1/chart/1'); print('author1 delete ADMIN-owned chart 1',st,short(j,80))
st,j=u1.req('GET','/api/v1/chart/1'); print('author1 GET admin chart 1',st)
# dashboards
def dashbody(title,charts): 
    pos={"DASHBOARD_VERSION_KEY":"v2","ROOT_ID":{"type":"ROOT","id":"ROOT_ID","children":["GRID_ID"]},"GRID_ID":{"type":"GRID","id":"GRID_ID","children":["ROW-1"],"parents":["ROOT_ID"]},"HEADER_ID":{"id":"HEADER_ID","type":"HEADER","meta":{"text":title}},"ROW-1":{"type":"ROW","id":"ROW-1","children":[f"CHART-{i}" for i,_ in enumerate(charts,1)],"parents":["ROOT_ID","GRID_ID"],"meta":{"background":"BACKGROUND_TRANSPARENT"}}}
    for i,c in enumerate(charts,1): pos[f"CHART-{i}"]={"type":"CHART","id":f"CHART-{i}","children":[],"parents":["ROOT_ID","GRID_ID","ROW-1"],"meta":{"width":4,"height":40,"chartId":c,"sliceName":f"c{c}"}}
    return {"dashboard_title":title,"position_json":json.dumps(pos),"json_metadata":json.dumps({"native_filter_configuration":[],"chart_configuration":{}})}
st,j=u1.post('/api/v1/dashboard/',dashbody('x20_dash_a1',[])); print('author1 create dashboard',st,short(j)); da=j.get('id')
st,j=u1.put(f'/api/v1/chart/{ca}',{"dashboards":[da]}); print('author1 add OWN chart to OWN dashboard (chart.dashboards)',st,short(j,100))
st,j=u1.put(f'/api/v1/dashboard/{da}',dashbody('x20_dash_a1 saved',[ca,cv])); print('author1 save own dashboard with positions of own charts',st,short(j,100))
st,j=u1.req('GET',f'/api/v1/dashboard/{da}/charts'); print('  dashboard charts after save',st,[r['slice_name'] for r in j.get('result',[])] if st==200 else j)
st,j=u1.put(f'/api/v1/dashboard/{da}',dashbody('x20_dash_a1 with ADMIN chart',[ca,1])); print('author1 save own dashboard including ADMIN-owned chart 1 in positions',st,short(j,100))
st,j=u1.req('GET',f'/api/v1/dashboard/{da}/charts'); print('  dashboard charts',st,[r['slice_name'] for r in j.get('result',[])] if st==200 else j)
st,j=u1.put('/api/v1/chart/1',{"dashboards":[da]}); print('author1 PUT admin chart 1 dashboards=[own]',st,short(j,100))
st,j=u1.put('/api/v1/dashboard/1',{"dashboard_title":"hijack"}); print('author1 update ADMIN-owned dashboard 1',st,short(j,80))
st,j=u1.delete('/api/v1/dashboard/1'); print('author1 delete ADMIN-owned dashboard 1',st,short(j,80))
st,j=u2.put(f'/api/v1/chart/{ca}',{"slice_name":"hijack2"}); print('author2 update author1 chart',st,short(j,80))
st,j=u2.put(f'/api/v1/dashboard/{da}',{"dashboard_title":"hijack2"}); print('author2 update author1 dashboard',st,short(j,80))
st,j=u2.req('GET',f'/api/v1/dashboard/{da}'); print('author2 GET author1 dashboard (draft, other owner)',st)
st,j=u2.req('GET','/api/v1/dashboard/'); print('author2 dashboard list',st,[(r['id'],r['dashboard_title'],r['status']) for r in j.get('result',[])] if st==200 else j)
st,j=u2.req('GET','/api/v1/chart/'); print('author2 chart list',st,[(r['id'],r['slice_name']) for r in j.get('result',[])] if st==200 else j)
# published visibility
print('-- publish author1 dashboard -> author2 sees?')
st,j=u1.put(f'/api/v1/dashboard/{da}',{"published":True}); print('author1 publish own dashboard',st)
st,j=u2.req('GET',f'/api/v1/dashboard/{da}'); print('author2 GET published dashboard of author1',st)
st,j=u2.req('GET','/api/v1/dashboard/'); print('author2 dashboard list',st,[(r['id'],r['dashboard_title'],r['status']) for r in j.get('result',[])] if st==200 else j)
print('-- admin publishes admin dashboards 1,2 -> author1 sees?')
for d in (1,2): print('admin publish',d,a.put(f'/api/v1/dashboard/{d}',{"published":True})[0])
st,j=u1.req('GET','/api/v1/dashboard/1'); print('author1 GET admin dashboard 1 (published)',st)
st,j=u1.req('GET','/api/v1/dashboard/'); print('author1 dashboard list',st,[(r['id'],r['dashboard_title'],r['status']) for r in j.get('result',[])] if st==200 else j)
st,j=u1.req('GET','/api/v1/chart/'); print('author1 chart list',st,[(r['id'],r['slice_name']) for r in j.get('result',[])] if st==200 else j)
st,j=u1.req('GET','/api/v1/chart/1'); print('author1 GET admin chart 1',st)
I['x20'].update({'ca':ca,'cv':cv,'cp':cp,'ci':ci,'da':da}); json.dump(I,open('base_ids.json','w'))
