from x23_lib import *
import threading
a=admin(); I=json.load(open('base_ids.json')); R=I['x22']
svc=U('x22_svc'); svc.start()
print(psql("CREATE VIEW bi_data.x22_v AS SELECT period, team, value FROM bi_data.x23_src") or 'view x22_v created (period date, team text, value numeric)')
st,j=svc.post('/api/v1/dataset/',{"database":1,"schema":"bi_data","table_name":"x22_v"}); print('svc POST physical',st); P=j['id']
st,j=svc.post('/api/v1/dataset/',{"database":1,"schema":"bi_data","table_name":"x22 가상 v","sql":"SELECT * FROM bi_data.x22_v"}); print('svc POST virtual',st); V=j['id']
cols=lambda i:[(c['column_name'],c['type']) for c in a.req('GET',f'/api/v1/dataset/{i}')[1]['result']['columns']]
print('physical cols',cols(P)); print('virtual cols',cols(V))
Cq=mk_chart(a,P,'x22_chart_on_x22_v'); DBq=mk_dash(a,'x22_dash_x22_v',[Cq])
R.update({'P':P,'V':V,'Cq':Cq,'DBq':DBq})
def chartdata(i,cols_,metric=None):
    q={"columns":cols_,"row_limit":3}
    if metric: q={"columns":["team"],"metrics":[metric],"row_limit":3}
    st,j=a.post('/api/v1/chart/data',{"datasource":{"id":i,"type":"table"},"queries":[q],"result_format":"json","result_type":"full"}); return st,(j.get('result',[{}])[0].get('data') if st==200 else str(j)[:160])
print("--- (d1) add a column to the view, refresh")
print(psql("CREATE OR REPLACE VIEW bi_data.x22_v AS SELECT period, team, value, value*2 AS value2 FROM bi_data.x23_src") or 'view replaced (+value2)')
print('before refresh: physical',[c[0] for c in cols(P)],'virtual',[c[0] for c in cols(V)])
r1=svc.put(f'/api/v1/dataset/{P}/refresh',{}); r2=svc.put(f'/api/v1/dataset/{V}/refresh',{}); print('svc refresh physical',r1[0],r1[1],'virtual',r2[0],r2[1])
print('after refresh: physical',cols(P),'virtual',[c[0] for c in cols(V)])
print("--- (d2) type change + column removal in one transaction (DROP VIEW + CREATE VIEW)")
print(psql("BEGIN; DROP VIEW bi_data.x22_v; CREATE VIEW bi_data.x22_v AS SELECT period, team, value::text AS value FROM bi_data.x23_src; COMMIT;") or 'view re-created: value now TEXT, value2 removed')
print('chart/data on column value before refresh',chartdata(P,['team','value']),'| metric SUM(value)',chartdata(P,None,{"expressionType":"SQL","sqlExpression":"SUM(value)","label":"s"}))
r1=svc.put(f'/api/v1/dataset/{P}/refresh',{}); r2=svc.put(f'/api/v1/dataset/{V}/refresh',{}); print('svc refresh physical',r1[0],'virtual',r2[0])
print('after refresh: physical',cols(P),'virtual',cols(V))
print('chart/data after refresh column value',chartdata(P,['team','value']),'| removed column value2',chartdata(P,['team','value2']))
print('saved chart still lists removed column? (chart params):',json.loads(a.req('GET',f'/api/v1/chart/{Cq}')[1]['result']['params']).get('all_columns'))
print("--- (d3) column removal only (value dropped)")
print(psql("BEGIN; DROP VIEW bi_data.x22_v; CREATE VIEW bi_data.x22_v AS SELECT period, team FROM bi_data.x23_src; COMMIT;") or 'view re-created without value')
r1=svc.put(f'/api/v1/dataset/{P}/refresh',{}); print('refresh',r1[0],r1[1]); print('physical cols',cols(P))
print('saved chart on removed column:',chartdata(P,['team','value']))
json.dump(I,open('base_ids.json','w'))
