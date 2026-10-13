"""FU-2a(감사 로그, S10) 화면 촬영용 합성 데이터 시드(스텁 쿠키 + HTTP API만 사용).

사전 조건: 스택이 떠 있고(AUTH_STUB_ENABLED=true, APP_ENV=local) `python -m app.cli seed-stub-users`가 한 번 실행된 새 DB.
사용: python3 seed2a.py <포털 API 기준 주소, 예: http://127.0.0.1:36280/bi-wizard/api> <ids2a.json 출력 경로>
모든 값은 합성이다. 비밀값은 다루지 않는다(스텁 쿠키 값은 로그인 ID일 뿐이다).
서버 명령 행(user.bootstrap_admin)은 이 스크립트가 아니라 `python -m app.cli create-admin`으로 따로 만든다(README 참고).

기록 순서(오래된 것 -> 새 것): 대시보드 이름 변경 40번(쪽 이동이 보이도록 50건을 넘긴다) -> 팀·사용자·소속 -> 데이터셋·열·수식 -> 대시보드 연결 해제/다시 연결.
"""
import json
import sys
import urllib.error
import urllib.request
import uuid

BASE = sys.argv[1].rstrip("/")
OUT = sys.argv[2]


def call(user, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"content-type": "application/json", "Cookie": "bi_stub_login=" + user}
    request = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as error:
        raw = error.read()
        try:
            return error.code, json.loads(raw)
        except ValueError:
            return error.code, {"_raw": raw[:200].decode("utf8", "replace")}


def must(result, expected=(200, 201, 204)):
    status, body = result
    if status not in expected:
        raise SystemExit(f"실패 {status}: {body}")
    return body


ADMIN, DEFINER = "stub-admin", "stub-definer"
users = {u["login_id"]: u["id"] for u in must(call(ADMIN, "GET", "/users?limit=200"))["items"]}
teams = {t["code"]: t["id"] for t in must(call(ADMIN, "GET", "/teams?limit=200"))["items"]}
ids = {"users": users, "teams": teams}

# 1) 대시보드 연결 + 이름 변경 40번
dash = must(call(ADMIN, "POST", "/dashboards", {"name": "경영 현황판 v0", "embedded_uuid": str(uuid.uuid4())}))
for n in range(1, 41):
    must(call(ADMIN, "PATCH", f"/dashboards/{dash['id']}", {"name": f"경영 현황판 v{n}"}))
ids["dashboard"] = dash["id"]

# 2) 팀·사용자·소속
team = must(call(ADMIN, "POST", "/teams", {"code": "quality", "name": "품질관리팀"}))
must(call(ADMIN, "PATCH", f"/teams/{team['id']}", {"name": "품질관리 1팀"}))
newbie = must(call(ADMIN, "POST", "/users", {"login_id": "shot-newbie", "display_name": "신입 사원"}))
must(call(ADMIN, "PUT", f"/teams/{team['id']}/members/{newbie['id']}", {"role": "entry"}))
must(call(ADMIN, "PUT", f"/teams/{team['id']}/members/{newbie['id']}", {"role": "definer"}))
must(call(ADMIN, "PATCH", f"/users/{newbie['id']}", {"display_name": "신입 사원(수습)", "is_admin": False}))
must(call(ADMIN, "DELETE", f"/teams/{team['id']}/members/{newbie['id']}"))
ids["team_quality"], ids["newbie"] = team["id"], newbie["id"]

# 3) 데이터셋·열·수식 (정의 담당자)
ds = must(call(DEFINER, "POST", "/datasets", {"team_id": teams["stub_a"], "name": "월별 매출", "date_unit": "month"}))
ver = ds["def_version"]


def add_col(name, typ, **kw):
    global ver
    body = must(call(DEFINER, "POST", f"/datasets/{ds['id']}/columns", dict(expected_version=ver, display_name=name, type=typ, **kw)))
    ver = body["def_version"]
    return body["column"]["id"]


base_col = add_col("기준월", "date")
sales = add_col("매출", "number", rules={"decimals": 0})
cost = add_col("비용", "number", rules={"decimals": 0}, tag="비용")
ver = must(call(DEFINER, "PATCH", f"/datasets/{ds['id']}", {"expected_version": ver, "base_date_column_id": base_col}))["def_version"]
ver = must(call(DEFINER, "PATCH", f"/datasets/{ds['id']}", {"expected_version": ver, "name": "월별 매출 현황"}))["def_version"]
ver = must(call(DEFINER, "PATCH", f"/datasets/{ds['id']}/columns/{sales}", {"expected_version": ver, "display_name": "매출액", "required": True}))["def_version"]
formula = must(call(DEFINER, "POST", f"/datasets/{ds['id']}/formulas", {"expected_version": ver, "display_name": "이익", "expression": "[매출액]-[비용]"}))
ver, fcol = formula["def_version"], formula["column"]["id"]
must(call(DEFINER, "PUT", f"/datasets/{ds['id']}/formulas/{fcol}", {"expected_version": ver, "expression": "[매출액]-[비용]*2"}))
ids["dataset"] = ds["id"]

# 4) 대시보드 연결 해제 / 다시 연결
must(call(ADMIN, "PATCH", f"/dashboards/{dash['id']}", {"is_active": False}))
must(call(ADMIN, "PATCH", f"/dashboards/{dash['id']}", {"is_active": True}))
must(call(ADMIN, "PATCH", f"/dashboards/{dash['id']}", {"is_active": False}))

json.dump(ids, open(OUT, "w", encoding="utf8"), ensure_ascii=False)
print("시드 완료", {k: v for k, v in ids.items() if k not in ("users", "teams")})
