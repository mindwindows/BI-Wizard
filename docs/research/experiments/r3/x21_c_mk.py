from r3lib import *
a=admin(); fid='NATIVE_FILTER-teamsel1'
mask={"id":fid,"extraFormData":{"filters":[{"col":"team","op":"IN","val":["팀2"]}]},"filterState":{"value":["팀2"]}}
res={}
for name,body in {
  'P1_map_full':{"dataMask":{fid:mask}},
  'P2_single_mask':{"dataMask":mask},
  'P3_map_filterState_only':{"dataMask":{fid:{"id":fid,"filterState":{"value":["팀2"]}}}},
  'P4_map_with_activeTabs_anchor':{"dataMask":{fid:mask},"activeTabs":[],"anchor":""},
}.items():
    st,j=a.body('POST','/api/v1/dashboard/1/permalink',body); print(name,st,j); res[name]=j
json.dump(res,open('x21/permalinks.json','w'),ensure_ascii=False)
# read one back
k=res['P1_map_full']['key']; print(a.req('GET','/api/v1/dashboard/permalink/'+k))
# is the permalink API usable with a non-owner (Gamma-like) user? later in X-20
