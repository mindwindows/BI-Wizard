"""Print a guest token. usage: gtok4.py <uuid> [username] ; env X_MODE=admin (default) | issuer ; X_RLS json"""
import sys, os, json
sys.path.insert(0, '/home/user/BI-Wizard/_workspace/gate3/experiments/r4')
from lib import *
uuid = sys.argv[1]; user = sys.argv[2] if len(sys.argv) > 2 else 'x25_guest_user'
mode = os.environ.get('X_MODE', 'admin')
if mode == 'issuer':
    s = U(os.environ.get('X_ISSUER', 'x28_issuer'), envval('SUPERSET_ADMIN_PASSWORD')); assert s.start() == 200
else:
    s = admin()
rls = json.loads(os.environ.get('X_RLS', '[]'))
st, j = s.body('POST', '/api/v1/security/guest_token/', {"user": {"username": user, "first_name": "x25", "last_name": "guest"}, "resources": [{"type": "dashboard", "id": uuid}], "rls": rls})
print(j['token'] if st == 200 else 'ERR %s %s' % (st, j))
