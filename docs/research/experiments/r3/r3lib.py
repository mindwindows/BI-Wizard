import sys, os, json, subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sslib import *   # S, BASE, envval, json
ORIGIN = "http://127.0.0.1:25173"
class U(S):
    """Superset REST session for any user (JWT + CSRF + cookie jar)."""
    def __init__(self, user=None, pw=None):
        super().__init__(); self.user = user or envval('SUPERSET_ADMIN_USER'); self.pw = pw or envval('SUPERSET_ADMIN_PASSWORD')
    def login(self):
        st, j = self.req('POST', '/api/v1/security/login', {"username": self.user, "password": self.pw, "provider": "db", "refresh": True})
        if st == 200: self.tok = j['access_token']; self.ref = j.get('refresh_token')
        return st
    def csrf_fetch(self):
        st, j = self.req('GET', '/api/v1/security/csrf_token/')
        if st == 200: self.csrf = j['result']
        return st
    def start(self):
        st = self.login()
        if st != 200: return st
        return self.csrf_fetch()
    def delete(self, path):
        return self.req('DELETE', path, None, {'X-CSRFToken': self.csrf, 'Referer': BASE + '/'})
    def body(self, method, path, body=None):
        return self.req(method, path, body, {'X-CSRFToken': self.csrf, 'Referer': BASE + '/'})
def admin():
    a = U(); assert a.start() == 200; return a
def psql(sql, db='bi_wizard'):
    r = subprocess.run(['docker','exec','g3x-postgres-1','psql','-U','bi_wizard','-d',db,'-X','-q','-t','-A','-c',sql],capture_output=True,text=True)
    return (r.stdout + r.stderr).strip()
def ensure_role(a, name):
    st, j = a.req('GET', '/api/v1/security/roles/search/?q=' + "(filters:!((col:name,opr:eq,value:'%s')))" % name)
    if st == 200 and j['result']: return j['result'][0]['id']
    st, j = a.body('POST', '/api/v1/security/roles/', {"name": name}); assert st in (200, 201), (st, j); return j['id']
def pvm_id(a, perm, view):
    q = "(filters:!((col:permission.name,opr:eq,value:'%s'),(col:view_menu.name,opr:eq,value:'%s')),page_size:5)" % (perm, view.replace("'", "!'"))
    st, j = a.req('GET', '/api/v1/security/permissions-resources/?q=' + urllib.parse.quote(q, safe="(),:!'"))
    return (j['result'][0]['id'] if st == 200 and j.get('result') else None), st, j
import urllib.parse
def all_pvms(a):
    out = []; page = 0
    while True:
        st, j = a.req('GET', '/api/v1/security/permissions-resources/?q=(page:%d,page_size:100)' % page)
        assert st == 200, (st, j)
        out += [(r['id'], r['permission']['name'], r['view_menu']['name']) for r in j['result']]
        if len(out) >= j['count'] or not j['result']: break
        page += 1
    return out
def pvm_map(a):
    return {(p, v): i for i, p, v in all_pvms(a)}
def role_by_name(a, name):
    st, j = a.req('GET', '/api/v1/security/roles/search/?q=(page_size:100)')
    for r in j['result']:
        if r['name'] == name: return r
    return None
