from r3lib import *
a=admin(); I=json.load(open('base_ids.json')); X=I['x20']
u1=U('x20_author1'); u1.start()
def pos(charts,title='t'):
    p={"DASHBOARD_VERSION_KEY":"v2","ROOT_ID":{"type":"ROOT","id":"ROOT_ID","children":["GRID_ID"]},"GRID_ID":{"type":"GRID","id":"GRID_ID","children":["ROW-1"],"parents":["ROOT_ID"]},"HEADER_ID":{"id":"HEADER_ID","type":"HEADER","meta":{"text":title}},"ROW-1":{"type":"ROW","id":"ROW-1","children":[f"CHART-{i}" for i,_ in enumerate(charts,1)],"parents":["ROOT_ID","GRID_ID"],"meta":{"background":"BACKGROUND_TRANSPARENT"}}}
    for i,c in enumerate(charts,1): p[f"CHART-{i}"]={"type":"CHART","id":f"CHART-{i}","children":[],"parents":["ROOT_ID","GRID_ID","ROW-1"],"meta":{"width":4,"height":40,"chartId":c,"sliceName":f"c{c}"}}
    return p
da=X['da']
def save(charts,label):
    p=pos(charts); jm={"native_filter_configuration":[],"chart_configuration":{},"positions":p}
    st,j=u1.put(f'/api/v1/dashboard/{da}',{"position_json":json.dumps(p),"json_metadata":json.dumps(jm)})
    st2,j2=u1.req('GET',f'/api/v1/dashboard/{da}/charts'); print(label,'PUT',st,'-> attached charts',[(r['id'],r['slice_name']) for r in j2.get('result',[])] if st2==200 else j2, '' if st==200 else str(j)[:150])
save([X['ca'],X['cv']],'UI-style save [own phys, own virtual]')
save([X['ca'],X['cv'],1],'UI-style save + ADMIN-owned chart 1')
save([X['ca'],X['cv'],X['cp']],'UI-style save + own chart on inaccessible public dataset')
st,j=u1.req('GET',f"/api/v1/chart/{X['cp']}"); print('author1 GET own chart 9 (public dataset, no access)',st,str(j)[:100])
st,j=u1.req('GET','/api/v1/chart/'); print('author1 chart list',[(r['id']) for r in j['result']])
st,j=cdata=u1.post('/api/v1/chart/data',{"datasource":{"id":4,"type":"table"},"queries":[{"columns":["team"],"filters":[],"row_limit":5}],"result_format":"json","result_type":"full"}); print('chart/data on public ds',st)
st,j=u1.req('GET',f"/api/v1/chart/{X['cp']}/data/"); print('GET chart 9 /data/ (saved chart data)',st,str(j)[:140])
