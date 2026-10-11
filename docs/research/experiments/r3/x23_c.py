from x23_lib import *
a=admin(); I=json.load(open('base_ids.json')); Z=json.load(open('x23_ids.json'))['Z']; X=I['x20']; R=I['x22']
print("=== (d) related_objects accuracy and required permission")
D3=mk_ds(a,'x23_v3'); Z['D3']=D3
u1=U('x20_author1'); u1.start(); u2=U('x20_author2'); u2.start()
Ca1=mk_chart(a,D3,'x23_admin_chart_in_two_dash'); Ca2=mk_chart(a,D3,'x23_admin_chart_no_dash')
Cu=mk_chart(u1,D3,'x23_author1_chart')
DBa=mk_dash(a,'x23_admin_pub_dash',[Ca1],published=True)
DBb=mk_dash(a,'x23_admin_draft_dash',[Ca1],published=False)
DBu=mk_dash(u1,'x23_author1_draft_dash',[Cu],published=False)       # author1's own draft: invisible to others
DBf=mk_dash(a,'x23_filter_only_dash',[],filter_ds=D3,published=True)  # references D3 ONLY by a native filter
DBx=mk_dash(a,'x23_other_dataset_dash',[],filter_ds=X['virt'] if False else 1,published=True)  # filter on another dataset (control)
Z.update({'Ca1':Ca1,'Ca2':Ca2,'Cu':Cu,'DBa':DBa,'DBb':DBb,'DBu':DBu,'DBf':DBf}); json.dump({'Z':Z},open('x23_ids.json','w'))
truth_c=sup(f"select id,slice_name from slices where datasource_id={D3} order by id"); truth_d=sup(f"select distinct d.id,d.dashboard_title from dashboards d join dashboard_slices ds on ds.dashboard_id=d.id join slices s on s.id=ds.slice_id where s.datasource_id={D3} order by 1")
filt=sup(f"select id,dashboard_title from dashboards where json_metadata like '%\"datasetId\": {D3},%'")
print('DB truth charts:',truth_c.replace('\n',' ; ')); print('DB truth dashboards via charts:',truth_d.replace('\n',' ; ')); print('DB: dashboards whose native filter targets D3:',filt.replace('\n',' ; '))
def ro(sess,label):
    st,j=sess.req('GET',f'/api/v1/dataset/{D3}/related_objects')
    if st==200: print(f"{label}: {st} charts={j['charts']['count']} {[(r['id'],r['slice_name']) for r in j['charts']['result']]} | dashboards={j['dashboards']['count']} {[(r['id'],r.get('dashboard_title') or r.get('title'),sorted(r.keys())) for r in j['dashboards']['result']][:1]} ids={[r['id'] for r in j['dashboards']['result']]}")
    else: print(f"{label}: {st} {s(j,100)}")
    return j
j=ro(a,'admin')
print('  dashboard result keys:',sorted(j['dashboards']['result'][0].keys()),'| json_metadata len of first:',len(j['dashboards']['result'][0].get('json_metadata','')))
ro(u1,'author1 (can_read Dataset, owns the draft)'); ro(u2,'author2 (can_read Dataset, sees neither draft)')
print('by uuid:',a.req('GET',f"/api/v1/dataset/{a.req('GET',f'/api/v1/dataset/{D3}')[1]['result']['uuid']}/related_objects")[0])
# service account permission matrix for related_objects
def setperms(pids): return a.body('POST',f"/api/v1/security/roles/{R['role']}/permissions",{"permission_view_menu_ids":sorted(pids)})[0]
for label,ps in (('svc: no permission',[]),('svc: can_read SecurityRestApi only',[192]),('svc: can_read Dataset only',[11]),('svc: can_write Dataset only',[12]),('svc: can_read Chart+Dashboard only',[7,15]),('svc: can_read Dataset + schema_access bi_data',[11,234])):
    setperms(ps); sv=U('x22_svc'); sv.login(); ro(sv,label)
setperms([])
# a dataset deletion now: charts in 2 dashboards + others
# dashboards listing visible to a non-privileged user: does delete of dataset by svc break? (not needed)
print("=== (e) DROP VIEW before deleting the dataset")
D4=mk_ds(a,'x23_v4'); C8=mk_chart(a,D4,'x23_C8'); DB8=mk_dash(a,'x23_dash8',[C8],filter_ds=D4); Z.update({'D4':D4,'C8':C8,'DB8':DB8})
print('before DROP: refresh',a.put(f'/api/v1/dataset/{D4}/refresh',{})[0],'cols',[c['column_name'] for c in a.req('GET',f'/api/v1/dataset/{D4}')[1]['result']['columns']])
print('DROP VIEW:',psql('DROP VIEW bi_data.x23_v4') or 'ok')
st,j=a.put(f'/api/v1/dataset/{D4}/refresh',{}); print('PUT refresh after DROP',st,s(j,400))
st,j=a.req('GET',f'/api/v1/dataset/{D4}'); print('GET dataset after DROP',st,'columns still',[c['column_name'] for c in j['result']['columns']] if st==200 else s(j))
st,j=a.post('/api/v1/chart/data',{"datasource":{"id":D4,"type":"table"},"queries":[{"columns":["team"],"row_limit":5}],"result_format":"json","result_type":"full"}); print('POST chart/data after DROP',st,s(j,500))
st,j=a.req('GET',f'/api/v1/dataset/{D4}/samples') if False else (None,None)
st,j=a.post(f'/api/v1/datasource/samples?datasource_id={D4}&datasource_type=table',{}); print('samples after DROP',st,s(j,300))
st,j=a.req('GET',f'/api/v1/database/1/table_metadata/?name=x23_v4&schema=bi_data'); print('table_metadata of dropped view',st,s(j,200))
st,j=a.req('GET','/api/v1/database/1/tables/?q=(force:!t,schema_name:bi_data)'); print('tables list (force) contains x23_v4?',st,'x23_v4' in s(j,3000))
Z['D4_ui']=D4; json.dump({'Z':Z},open('x23_ids.json','w'))
