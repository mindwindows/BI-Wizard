import json, urllib.request, urllib.error, os, re, http.cookiejar
BASE = "http://127.0.0.1:25173/bi-wizard/superset"
def envval(k):
    for l in open('/home/user/BI-Wizard/_workspace/qa/g3x.env', encoding='utf-8'):
        if l.startswith(k+'='): return l.strip().split('=',1)[1]
class S:
    def __init__(self):
        self.tok=None; self.csrf=None
        self.jar=http.cookiejar.CookieJar()
        self.op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
    def req(self, method, path, body=None, headers=None, raw=False):
        h={'Content-Type':'application/json','Accept':'application/json'}
        if self.tok: h['Authorization']='Bearer '+self.tok
        if headers: h.update(headers)
        data=json.dumps(body).encode() if body is not None else None
        r=urllib.request.Request(BASE+path, data=data, method=method, headers=h)
        try:
            with self.op.open(r, timeout=60) as resp:
                t=resp.read().decode(); 
                return resp.status, (t if raw else (json.loads(t) if t else None))
        except urllib.error.HTTPError as e:
            t=e.read().decode()
            try: return e.code, json.loads(t)
            except Exception: return e.code, t[:300]
    def login(self):
        st,j=self.req('POST','/api/v1/security/login',{"username":envval('SUPERSET_ADMIN_USER'),"password":envval('SUPERSET_ADMIN_PASSWORD'),"provider":"db","refresh":True})
        self.tok=j['access_token']; return st

    def with_csrf(self):
        st,j=self.req('GET','/api/v1/security/csrf_token/'); self.csrf=j['result']; return st
    def post(self, path, body, csrf=True):
        h={'X-CSRFToken':self.csrf,'Referer':BASE+'/'} if csrf else {}
        return self.req('POST',path,body,h)
    def put(self, path, body):
        return self.req('PUT',path,body,{'X-CSRFToken':self.csrf,'Referer':BASE+'/'})
