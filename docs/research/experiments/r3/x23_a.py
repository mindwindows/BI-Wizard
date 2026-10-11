from x23_lib import *
a=admin(); I=json.load(open('base_ids.json')); Z={}
print("=== (a) delete dataset that has charts + dashboard")
D1=mk_ds(a,'x23_v1'); C1=mk_chart(a,D1,'x23_C1'); C2=mk_chart(a,D1,'x23_C2'); DB1=mk_dash(a,'x23_dash1',[C1,C2],filter_ds=D1)
Z.update({'D1':D1,'C1':C1,'C2':C2,'DB1':DB1}); print(Z)
print('BEFORE',json.dumps(snap([D1],[C1,C2],[DB1]),ensure_ascii=False))
st,j=a.req('GET',f'/api/v1/dataset/{D1}/related_objects'); print('related_objects before delete',st,s(j,300))
st,j=a.delete(f'/api/v1/dataset/{D1}'); print('DELETE dataset',st,s(j))
print('AFTER',json.dumps(snap([D1],[C1,C2],[DB1]),ensure_ascii=False))
st,j=a.req('GET',f'/api/v1/chart/{C1}'); r=j.get('result',{}) if st==200 else j; print('GET chart',st, s({k:r.get(k) for k in ('id','slice_name','datasource_id','datasource_type','datasource_name_text','datasource_url','dashboards')} if st==200 else j,400))
st,j=a.req('GET','/api/v1/chart/?q=(filters:!((col:slice_name,opr:ct,value:x23_C)),columns:!(id,slice_name,datasource_id,datasource_name_text,datasource_url,table))'); print('chart list',st,s(j.get('result') if st==200 else j,500))
st,j=a.req('GET',f'/api/v1/chart/{C1}/data/'); print('GET chart/<id>/data/',st,s(j,300))
st,j=a.post('/api/v1/chart/data',{"datasource":{"id":D1,"type":"table"},"queries":[{"columns":["team"],"row_limit":5}],"result_format":"json","result_type":"full"}); print('POST chart/data by dataset id',st,s(j,300))
st,j=a.req('GET',f'/api/v1/dashboard/{DB1}'); print('GET dashboard',st,'has position chartIds', [v['meta']['chartId'] for v in json.loads(j['result']['position_json']).values() if isinstance(v,dict) and v.get('type')=='CHART'] if st==200 else j, '| filter targets', [t for f in json.loads(j['result']['json_metadata'])['native_filter_configuration'] for t in f['targets']])
st,j=a.req('GET',f'/api/v1/dashboard/{DB1}/charts'); print('GET dashboard/charts',st,[(r['id'],r['slice_name']) for r in j.get('result',[])] if st==200 else s(j))
st,j=a.req('GET',f'/api/v1/dashboard/{DB1}/datasets'); print('GET dashboard/datasets',st,s(j,300))
st,j=a.req('GET',f'/api/v1/dashboard/{DB1}/charts'); 
# explore link of the chart
json.dump({'Z':Z},open('x23_ids.json','w'))
