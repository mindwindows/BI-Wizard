import sys, os, time, json
sys.path.insert(0, '/home/user/BI-Wizard/_workspace/gate3/experiments/r4')
from gs import dsign
uuid = sys.argv[1]; user = sys.argv[2] if len(sys.argv) > 2 else 'direct_user'
now = time.time(); aud = os.environ.get('X_AUD', 'http://0.0.0.0:8080/'); mode = os.environ.get('X_SIGN', 'stdlib')
rls = json.loads(os.environ.get('X_RLS', '[]')); exp = int(os.environ.get('X_EXPSEC', '300'))
cl = {"user": {"username": user, "first_name": "d", "last_name": "x"}, "resources": [{"type": "dashboard", "id": uuid}], "rls_rules": rls, "iat": now, "exp": now + exp, "aud": aud, "type": "guest"}
print(dsign(mode, cl))
