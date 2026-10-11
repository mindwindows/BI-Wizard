import sys
from r3lib import *
a=admin()
uuid=sys.argv[1]; user=sys.argv[2] if len(sys.argv)>2 else 'x21_guest'
st,j=a.body('POST','/api/v1/security/guest_token/',{"user":{"username":user,"first_name":"x21","last_name":"guest"},"resources":[{"type":"dashboard","id":uuid}],"rls":[]})
print(j['token'] if st==200 else 'ERR %s %s'%(st,j))
