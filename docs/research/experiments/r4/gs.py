import sys, json, re, urllib.request, urllib.error, http.cookiejar, urllib.parse, base64, subprocess
sys.path.insert(0, '/home/user/BI-Wizard/_workspace/gate3/experiments/r4')
from lib import *
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k): return None
class GS:
    """Guest session that behaves like the Embedded SDK: GET /embedded/<uuid> (cookie + csrf input), then X-GuestToken + X-CSRFToken."""
    def __init__(self, token, uuid, load=True, send_csrf=True):
        self.token = token; self.uuid = uuid; self.csrf = None; self.send_csrf = send_csrf; self.timeout = 30
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj), NoRedirect)
        self.load_status = None
        if load: self.load_status = self.load()
    def load(self):
        r = urllib.request.Request(BASE + '/embedded/' + self.uuid, headers={'Accept': 'text/html'})
        try:
            with self.op.open(r, timeout=60) as resp:
                t = resp.read().decode(); st = resp.status
        except urllib.error.HTTPError as e:
            t = e.read().decode(); st = e.code
        m = re.search(r'id="csrf_token"\s+value="([^"]*)"', t) or re.search(r'name="csrf_token"[^>]*value="([^"]+)"', t)
        self.csrf = m.group(1) if m else None
        return st
    def call(self, method, path, body=None, headers=None, raw=False, token=True, ctype='application/json'):
        h = {'Accept': 'application/json', 'Referer': BASE + '/embedded/' + self.uuid}
        if body is not None: h['Content-Type'] = ctype
        if token and self.token: h['X-GuestToken'] = self.token
        if self.csrf and self.send_csrf: h['X-CSRFToken'] = self.csrf
        if headers: h.update(headers)
        data = (json.dumps(body).encode() if not isinstance(body, (bytes, str)) else (body if isinstance(body, bytes) else body.encode())) if body is not None else None
        r = urllib.request.Request(BASE + path if path.startswith('/') else path, data=data, method=method, headers=h)
        try:
            with self.op.open(r, timeout=self.timeout) as resp:
                t = resp.read(); ct = resp.headers.get('Content-Type', ''); st = resp.status; loc = None
        except urllib.error.HTTPError as e:
            t = e.read(); ct = e.headers.get('Content-Type', ''); st = e.code; loc = e.headers.get('Location')
        except Exception as e:
            t = ('CLIENT TIMEOUT/ERROR ' + repr(e)[:80]).encode(); ct = ''; st = 0; loc = None
        txt = t.decode('utf-8', 'replace')
        if raw: return st, txt, ct, loc
        try: return st, json.loads(txt)
        except Exception: return st, (('REDIRECT ' + str(loc)) if loc else txt[:200])
def issue(uuid, user='x25_user', via='admin', rls=None):
    r = subprocess.run(['python3', '/home/user/BI-Wizard/_workspace/gate3/experiments/r4/gtok4.py', uuid, user], capture_output=True, text=True)
    return r.stdout.strip()
def claims(tok):
    p = tok.split('.')[1]; p += '=' * (-len(p) % 4); return json.loads(base64.urlsafe_b64decode(p))
def dsign(mode, cl):
    sec = envval('GUEST_TOKEN_JWT_SECRET')
    r = subprocess.run(['docker', 'exec', '-e', 'GUEST_TOKEN_JWT_SECRET=' + sec, 'g3x-x28-sign', 'python', '/x/sign.py', mode, json.dumps(cl, ensure_ascii=False)], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else 'ERR ' + r.stderr[-200:]
