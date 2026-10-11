from r3lib import *
def sup(sql): return psql(sql, db='superset')
def s(j,n=200): return (json.dumps(j,ensure_ascii=False) if not isinstance(j,str) else j)[:n]
def mk_ds(a, view, name=None):
    st,j=a.post('/api/v1/dataset/',{"database":1,"schema":"bi_data","table_name":view}); assert st==201,(st,j); return j['id']
def mk_chart(a, ds, name, owners=None):
    p={"viz_type":"table","datasource":f"{ds}__table","query_mode":"raw","all_columns":["period","team","value"],"row_limit":100,"adhoc_filters":[]}
    b={"slice_name":name,"viz_type":"table","datasource_id":ds,"datasource_type":"table","params":json.dumps(p)}
    if owners: b['owners']=owners
    st,j=a.post('/api/v1/chart/',b); assert st==201,(st,j); return j['id']
def mk_dash(a, title, charts, filter_ds=None, published=True, sess=None):
    sess=sess or a
    pos={"DASHBOARD_VERSION_KEY":"v2","ROOT_ID":{"type":"ROOT","id":"ROOT_ID","children":["GRID_ID"]},"GRID_ID":{"type":"GRID","id":"GRID_ID","children":["ROW-1"] if charts else [],"parents":["ROOT_ID"]},"HEADER_ID":{"id":"HEADER_ID","type":"HEADER","meta":{"text":title}}}
    if charts:
        pos["ROW-1"]={"type":"ROW","id":"ROW-1","children":[f"CHART-{i}" for i,_ in enumerate(charts,1)],"parents":["ROOT_ID","GRID_ID"],"meta":{"background":"BACKGROUND_TRANSPARENT"}}
        for i,c in enumerate(charts,1): pos[f"CHART-{i}"]={"type":"CHART","id":f"CHART-{i}","children":[],"parents":["ROOT_ID","GRID_ID","ROW-1"],"meta":{"width":4,"height":50,"chartId":c,"sliceName":f"chart{c}"}}
    nf=[]
    if filter_ds:
        nf=[{"id":"NATIVE_FILTER-x23","name":"팀","filterType":"filter_select","targets":[{"datasetId":filter_ds,"column":{"name":"team"}}],"defaultDataMask":{"extraFormData":{},"filterState":{},"ownState":{}},"controlValues":{"enableEmptyFilter":False,"defaultToFirstItem":False,"multiSelect":True,"searchAllOptions":False,"inverseSelection":False},"cascadeParentIds":[],"scope":{"rootPath":["ROOT_ID"],"excluded":[]},"type":"NATIVE_FILTER","description":""}]
    jm={"native_filter_configuration":nf,"chart_configuration":{},"positions":pos,"default_filters":"{}","refresh_frequency":0}
    st,j=sess.post('/api/v1/dashboard/',{"dashboard_title":title,"position_json":json.dumps(pos),"json_metadata":json.dumps(jm),"published":published}); assert st==201,(st,j); d=j['id']
    for c in charts: 
        st,j=sess.put(f'/api/v1/chart/{c}',{"dashboards":sorted(set(dashes_of(sess,c)+[d]))}); assert st==200,(st,j)
    return d
def dashes_of(a,c):
    st,j=a.req('GET',f'/api/v1/chart/{c}'); return [x['id'] for x in j['result'].get('dashboards',[])] if st==200 else []
def snap(ids_ds=(), ids_chart=(), ids_dash=()):
    out={}
    if ids_chart: out['slices']=sup("select id,slice_name,datasource_id,datasource_type,datasource_name,perm,schema_perm from slices where id in (%s) order by id"%','.join(map(str,ids_chart)))
    if ids_dash: out['dashboard_slices']=sup("select dashboard_id,slice_id from dashboard_slices where dashboard_id in (%s) order by 1,2"%','.join(map(str,ids_dash)))
    if ids_ds: 
        out['tables']=sup("select id,table_name,schema,perm,schema_perm,sql is not null as virtual from tables where id in (%s)"%','.join(map(str,ids_ds)))
        out['columns']=sup("select table_id,count(*) from table_columns where table_id in (%s) group by 1"%','.join(map(str,ids_ds)))
        out['pvm']=sup("select vm.name from ab_permission_view pv join ab_view_menu vm on vm.id=pv.view_menu_id join ab_permission p on p.id=pv.permission_id where p.name='datasource_access' and (%s)"%' or '.join(f"vm.name like '%(id:{i})'" for i in ids_ds))
    return out
