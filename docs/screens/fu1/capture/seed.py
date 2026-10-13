"""FU-1 화면 촬영용 합성 데이터 시드(스텁 쿠키 + HTTP API만 사용).

사전 조건: 스택이 떠 있고 `python -m app.cli seed-stub-users`가 한 번 실행된 새 DB.
사용: python3 seed.py <포털 API 기준 주소, 예: http://127.0.0.1:36173/bi-wizard/api> <ids.json 출력 경로>
모든 값은 합성 데이터다. 비밀값은 다루지 않는다(스텁 쿠키 값은 로그인 ID일 뿐이다).
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


ADMIN = "stub-admin"
ids = {}

# --- 팀·사용자 -------------------------------------------------------------
teams = {t["code"]: t["id"] for t in must(call(ADMIN, "GET", "/teams"))["items"]}
ids["team_a"], ids["team_b"] = teams["stub_a"], teams["stub_b"]
team_old = must(call(ADMIN, "POST", "/teams", {"code": "old_sales", "name": "구 영업팀"}))
ids["team_old"] = team_old["id"]
users = {u["login_id"]: u["id"] for u in must(call(ADMIN, "GET", "/users"))["items"]}
for login, name in [("kim-free", "김비소속"), ("lee-sales", "이영업"), ("park-fin", "박재무")]:
    users[login] = must(call(ADMIN, "POST", "/users", {"login_id": login, "display_name": name}))["id"]
ids["users"] = users
# 비활성 팀에 소속을 먼저 넣고 나서 팀을 비활성으로 바꾼다(비활성 팀 소속 표시를 만들려고).
for login in ("stub-multi", "lee-sales"):
    must(call(ADMIN, "PUT", f"/teams/{ids['team_old']}/members/{users[login]}", {"role": "entry"}))
must(call(ADMIN, "PUT", f"/teams/{ids['team_a']}/members/{users['park-fin']}", {"role": "entry"}))
must(call(ADMIN, "PATCH", f"/teams/{ids['team_old']}", {"is_active": False}))

# --- 데이터셋 -------------------------------------------------------------
def make_dataset(user, team_id, name, unit):
    body = must(call(user, "POST", "/datasets", {"team_id": team_id, "name": name, "date_unit": unit}))
    return {"id": body["id"], "ver": body["def_version"], "user": user, "cols": {}}


def add_col(ds, name, typ, **kw):
    body = must(call(ds["user"], "POST", f"/datasets/{ds['id']}/columns",
                     dict(expected_version=ds["ver"], display_name=name, type=typ, **kw)))
    ds["ver"] = body["def_version"]
    ds["cols"][name] = body["column"]["id"]
    return body["column"]["id"]


def set_base(ds, col_name):
    body = must(call(ds["user"], "PATCH", f"/datasets/{ds['id']}",
                     {"expected_version": ds["ver"], "base_date_column_id": ds["cols"][col_name]}))
    ds["ver"] = body["def_version"]


def add_row(ds, cells):
    must(call(ds["user"], "POST", f"/datasets/{ds['id']}/rows",
              {"expected_version": ds["ver"], "cells": {str(ds["cols"][k]): v for k, v in cells.items()}}))


sales = make_dataset("stub-definer", ids["team_a"], "월별 매출", "month")
add_col(sales, "기준월", "date")
add_col(sales, "매출", "number", required=True, rules={"decimals": 2, "min": "0", "max": "1000000"}, tag="수익")
add_col(sales, "담당", "text", rules={"max_length": 20})
add_col(sales, "구분", "choice", rules={"options": ["국내", "해외", "온라인"]})
add_col(sales, "확정", "boolean")
set_base(sales, "기준월")
months = [f"2025-{m:02d}-01" for m in (10, 11, 12)] + [f"2026-{m:02d}-01" for m in range(1, 11)]
amounts = ["120500.00", "98400.5", "154300.25", "0", "87650", "132000.75", "145210", "99999.99",
           "210450.4", "187300", "176020.8", "203110", "224870.35"]
owners = ["김민수", "박지연", "", "최도윤", "김민수", "", "이서준", "박지연", "최도윤", "", "김민수", "이서준", "박지연"]
kinds = ["국내", "해외", "온라인", "국내", "", "해외", "온라인", "국내", "해외", "온라인", "", "국내", "해외"]
for i, month in enumerate(months):
    cells = {"기준월": month, "매출": amounts[i]}
    if owners[i]:
        cells["담당"] = owners[i]
    if kinds[i]:
        cells["구분"] = kinds[i]
    if i < 11:
        cells["확정"] = "true" if i % 4 != 3 else "false"
    add_row(sales, cells)
ids["sales"] = sales

daily = make_dataset("stub-definer", ids["team_a"], "일별 방문자", "day")
add_col(daily, "기준일", "date")
add_col(daily, "방문자", "number", required=True, rules={"decimals": 0, "min": "0"})
add_col(daily, "비고", "text")
set_base(daily, "기준일")
for d in range(1, 15):
    add_row(daily, {"기준일": f"2026-10-{d:02d}", "방문자": str(800 + d * 37 % 311)})
ids["daily"] = daily

wide = make_dataset("stub-multi", ids["team_b"], "월별 지표(항목 많음)", "month")
add_col(wide, "기준월", "date")
add_col(wide, "매출", "number", rules={"decimals": 2})
for i, name in enumerate(["신규 고객", "재구매 고객", "반품 건수", "광고비", "물류비", "인건비", "임차료", "기타 비용",
                           "목표 달성률", "재고 금액", "미수금", "미지급금", "담당 부서", "비고 메모"]):
    add_col(wide, name, "text" if i >= 12 else "number", **({"rules": {"decimals": 0}} if i < 12 else {}))
set_base(wide, "기준월")
for i in range(1, 9):
    cells = {"기준월": f"2026-{i:02d}-01", "매출": f"{100000 + i * 7311}.50"}
    for j, name in enumerate(["신규 고객", "재구매 고객", "반품 건수", "광고비", "물류비", "인건비"]):
        cells[name] = str((i * 13 + j * 7) % 90 * 100)
    cells["담당 부서"] = "영업" if i % 2 else "운영"
    add_row(wide, cells)
ids["wide"] = wide

defn = make_dataset("stub-definer", ids["team_a"], "정의 시험용", "month")
add_col(defn, "기준월", "date")
add_col(defn, "금액", "number", rules={"decimals": 2})
ids["defn"] = defn

with open(OUT, "w", encoding="utf8") as f:
    json.dump(ids, f, ensure_ascii=False, indent=1)
print("시드 완료:", OUT)
