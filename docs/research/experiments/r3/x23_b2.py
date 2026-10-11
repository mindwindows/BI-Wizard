from x23_lib import *
a=admin(); Z=json.load(open('x23_ids.json'))['Z']
D=Z['D2']; Cb1=mk_chart(a,D,'x23_Cb1'); Cb2=mk_chart(a,D,'x23_Cb2'); DBb=mk_dash(a,'x23_dash_b',[Cb1,Cb2],filter_ds=D)
print('delete Cb2',a.delete(f'/api/v1/chart/{Cb2}')[0]); Z.update({'DBb':DBb,'Cb1':Cb1,'Cb2':Cb2}); json.dump({'Z':Z},open('x23_ids.json','w')); print(DBb)
