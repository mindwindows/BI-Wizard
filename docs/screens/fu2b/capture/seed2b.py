"""FU-2b(데이터셋 보관·복구) 화면 촬영용 합성 데이터 시드(스텁 쿠키 + HTTP API만 사용).

사전 조건: 스택이 떠 있고(AUTH_STUB_ENABLED=true, APP_ENV=local) `python -m app.cli seed-stub-users`가 한 번 실행된 새 DB.
사용: python3 seed2b.py <포털 API 기준 주소, 예: http://127.0.0.1:36280/bi-wizard/api> <ids2b.json 출력 경로>
모든 값은 합성이다. 비밀값은 다루지 않는다(스텁 쿠키 값은 로그인 ID일 뿐이다).
결과: A팀(stub-definer가 정의 담당자, stub-entry는 입력자) 사용 중 2개 + 보관 2개, B팀(stub-multi가 정의 담당자) 사용 중 1개,
비활성이 된 "폐쇄팀"(stub-definer가 정의 담당자) 소유 보관 데이터셋 1개.
"""
import json
import sys
import urllib.error
import urllib.request

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


ADMIN, DEFINER, MULTI = "stub-admin", "stub-definer", "stub-multi"
users = {u["login_id"]: u["id"] for u in must(call(ADMIN, "GET", "/users?limit=200"))["items"]}
teams = {t["code"]: t["id"] for t in must(call(ADMIN, "GET", "/teams?limit=200"))["items"]}
ids = {"users": users, "teams": teams, "definer": DEFINER}


def dataset(user, team_id, name, unit="month"):
    return must(call(user, "POST", "/datasets", {"team_id": team_id, "name": name, "date_unit": unit}))


def add_col(user, ds, ver, name, typ, **kw):
    body = must(call(user, "POST", f"/datasets/{ds['id']}/columns", dict(expected_version=ver, display_name=name, type=typ, **kw)))
    return body["column"]["id"], body["def_version"]


# 1) 사용 중: 월별 매출 현황(열·수식·행), 일별 가동
sales = dataset(DEFINER, teams["stub_a"], "월별 매출 현황")
ver = sales["def_version"]
base_col, ver = add_col(DEFINER, sales, ver, "기준월", "date")
rev, ver = add_col(DEFINER, sales, ver, "매출액", "number", rules={"decimals": 0})
cost, ver = add_col(DEFINER, sales, ver, "비용", "number", rules={"decimals": 0})
ver = must(call(DEFINER, "PATCH", f"/datasets/{sales['id']}", {"expected_version": ver, "base_date_column_id": base_col}))["def_version"]
formula = must(call(DEFINER, "POST", f"/datasets/{sales['id']}/formulas", {"expected_version": ver, "display_name": "이익", "expression": "[매출액]-[비용]"}))
ver = formula["def_version"]
for month, (r, c) in zip(["2026-07-01", "2026-08-01", "2026-09-01"], [(1200, 800), (1500, 900), (1350, 870)]):
    body = must(call(DEFINER, "POST", f"/datasets/{sales['id']}/rows", {"expected_version": ver, "cells": {str(base_col): month, str(rev): str(r), str(cost): str(c)}}))
    ver = body["def_version"]
ids["active"] = sales["id"]
ids["active_name"] = "월별 매출 현황"
dataset(DEFINER, teams["stub_a"], "일별 가동", "day")

# 2) B팀(stub-multi가 정의 담당자) 사용 중 1개
dataset(MULTI, teams["stub_b"], "설비 점검 기록")

# 3) 보관: 작년 매출(열·행 있음 -> 보관 중 읽기 전용 배너 촬영), 임시 실험
old = dataset(DEFINER, teams["stub_a"], "작년 매출")
oldver = old["def_version"]
obase, oldver = add_col(DEFINER, old, oldver, "기준월", "date")
orev, oldver = add_col(DEFINER, old, oldver, "매출액", "number", rules={"decimals": 0})
oldver = must(call(DEFINER, "PATCH", f"/datasets/{old['id']}", {"expected_version": oldver, "base_date_column_id": obase}))["def_version"]
oformula = must(call(DEFINER, "POST", f"/datasets/{old['id']}/formulas", {"expected_version": oldver, "display_name": "매출 두 배", "expression": "[매출액]*2"}))
oldver = oformula["def_version"]
for month, r in [("2025-11-01", 1000), ("2025-12-01", 1100)]:
    oldver = must(call(DEFINER, "POST", f"/datasets/{old['id']}/rows", {"expected_version": oldver, "cells": {str(obase): month, str(orev): str(r)}}))["def_version"]
must(call(DEFINER, "POST", f"/datasets/{old['id']}/archive"))
exp = dataset(DEFINER, teams["stub_a"], "임시 실험")
must(call(DEFINER, "POST", f"/datasets/{exp['id']}/archive"))
ids["archived"], ids["archived_name"] = old["id"], "작년 매출"
ids["archived2"] = exp["id"]

# 4) 비활성 팀 소유 보관 데이터셋
closed = must(call(ADMIN, "POST", "/teams", {"code": "closed", "name": "폐쇄팀"}))
must(call(ADMIN, "PUT", f"/teams/{closed['id']}/members/{users[DEFINER]}", {"role": "definer"}))
legacy = dataset(DEFINER, closed["id"], "옛 설비 기록")
must(call(DEFINER, "POST", f"/datasets/{legacy['id']}/archive"))
must(call(ADMIN, "PATCH", f"/teams/{closed['id']}", {"is_active": False}))
ids["closed_team"], ids["closed_dataset"] = closed["id"], legacy["id"]

json.dump(ids, open(OUT, "w", encoding="utf8"), ensure_ascii=False)
print("시드 완료", {k: v for k, v in ids.items() if k not in ("users", "teams")})
