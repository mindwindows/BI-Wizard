from x23_lib import *
a=admin(); I=json.load(open('base_ids.json')); Z=json.load(open('x23_ids.json'))['Z']
print("=== (b) delete a chart that is in a dashboard layout (+ (c) delete the dashboard)")
D2=mk_ds(a,'x23_v2'); C3=mk_chart(a,D2,'x23_C3'); C4=mk_chart(a,D2,'x23_C4'); DB2=mk_dash(a,'x23_dash2',[C3,C4],filter_ds=D2)
Z.update({'D2':D2,'C3':C3,'C4':C4,'DB2':DB2}); print({k:Z[k] for k in ('D2','C3','C4','DB2')})
print('BEFORE',json.dumps(snap([],[C3,C4],[DB2]),ensure_ascii=False))
st,j=a.delete(f'/api/v1/chart/{C4}'); print('DELETE chart C4',st,s(j))
print('AFTER dashboard_slices',snap([],[C3,C4],[DB2]))
st,j=a.req('GET',f'/api/v1/dashboard/{DB2}'); r=j['result']; pos=json.loads(r['position_json']); jm=json.loads(r['json_metadata'])
print('GET dashboard',st,'| position_json CHART nodes chartIds:',[(k,v['meta']['chartId']) for k,v in pos.items() if isinstance(v,dict) and v.get('type')=='CHART'],'| json_metadata.positions chartIds:',[v['meta']['chartId'] for v in jm.get('positions',{}).values() if isinstance(v,dict) and v.get('type')=='CHART'],'| chart_configuration:',jm.get('chart_configuration'))
st,j=a.req('GET',f'/api/v1/dashboard/{DB2}/charts'); print('GET dashboard/charts',st,[(x['id'],x['slice_name']) for x in j.get('result',[])])
st,j=a.req('GET',f'/api/v1/chart/{C4}'); print('GET deleted chart',st)
# (c) delete dashboard
st,j=a.delete(f'/api/v1/dashboard/{DB2}'); print('DELETE dashboard DB2',st,s(j))
print('slices after dashboard delete',snap([],[C3],[DB2]))
st,j=a.req('GET',f'/api/v1/chart/{C3}'); print('chart C3 still there?',st,'dashboards=',j['result'].get('dashboards') if st==200 else j)
st,j=a.req('GET',f'/api/v1/dataset/{D2}/related_objects'); print('related_objects D2 after chart+dashboard delete',st,s(j,300))
# dataset D2 can now be deleted; are charts blocking? (C3 still there)
json.dump({'Z':Z},open('x23_ids.json','w'))
