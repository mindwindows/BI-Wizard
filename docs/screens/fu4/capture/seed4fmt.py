"""FU-4 표시 형식(display_decimals·display_thousands) 화면 촬영용 합성 데이터 시드(스텁 쿠키 + HTTP API만 사용).

사전 조건: 스택이 떠 있고(AUTH_STUB_ENABLED=true, APP_ENV=local) `python -m app.cli seed-stub-users`가 한 번 실행된 새 DB.
사용: python3 seed4fmt.py <포털 API 기준 주소, 예: http://127.0.0.1:36280/bi-wizard/api> <ids4fmt.json 출력 경로>
모든 값은 합성이다. 비밀값은 다루지 않는다(스텁 쿠키 값은 로그인 ID일 뿐이다).
만드는 것(05 계약 B2·B5·C2·D4·B7):
- A팀 데이터셋 "월별 지표"(월 단위): 기준일(날짜), 사용량·단가(숫자),
  계산 열 연도(=YEAR([기준일]), 쉼표 때문에 2,026으로 보이는 열), 단가당 사용량(=[사용량] / [단가], 소수가 길게 나오는 열),
  전기요금(=[사용량] * [단가], 설정을 건드리지 않는 대조 열), 구분(글자 결과)
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



ADMIN, DEFINER, ENTRY = "stub-admin", "stub-definer", "stub-entry"
me = must(call(DEFINER, "GET", "/me"))
team_id = next(m["team_id"] for m in me["memberships"] if m["role"] == "definer" and m["team_is_active"])


def build(name):
    ds = must(call(DEFINER, "POST", "/datasets", {"team_id": team_id, "name": name, "date_unit": "month"}))
    state = {"v": ds["def_version"], "id": ds["id"]}

    def column(display_name, col_type, **extra):
        saved = must(call(DEFINER, "POST", f"/datasets/{state['id']}/columns", {"expected_version": state["v"], "display_name": display_name, "type": col_type, **extra}))
        state["v"] = saved["def_version"]
        return saved["column"]

    def formula(display_name, expression, **extra):
        saved = must(call(DEFINER, "POST", f"/datasets/{state['id']}/formulas", {"expected_version": state["v"], "display_name": display_name, "expression": expression, **extra}))
        state["v"] = saved["def_version"]
        return saved["column"]

    base = column("기준일", "date", required=True)
    usage = column("사용량", "number")
    price = column("단가", "number")
    saved = must(call(DEFINER, "PATCH", f"/datasets/{state['id']}", {"expected_version": state["v"], "base_date_column_id": base["id"]}))
    state["v"] = saved["def_version"]
    year = formula("연도", "YEAR([기준일])")
    ratio = formula("단가당 사용량", "[사용량] / [단가]")
    fee = formula("전기요금", "[사용량] * [단가]")
    kind = formula("구분", 'IF([사용량] > 1000, "많음", "보통")')
    for day, u, p in (("2026-01-01", "1250", "120"), ("2026-02-01", "980", "120"), ("2026-03-01", "1100", "125")):
        saved = must(call(ENTRY, "POST", f"/datasets/{state['id']}/rows", {"expected_version": state["v"], "cells": {str(base["id"]): day, str(usage["id"]): u, str(price["id"]): p}}))
        state["v"] = saved["def_version"]
    return state["id"], {"base": base["id"], "usage": usage["id"], "price": price["id"], "year": year["id"], "ratio": ratio["id"], "fee": fee["id"], "kind": kind["id"]}


live_id, live_cols = build("월별 지표")

with open(OUT, "w", encoding="utf8") as handle:
    json.dump({"definer": DEFINER, "member": ENTRY, "dataset_id": live_id, "cols": live_cols}, handle, ensure_ascii=False)
print("시드 완료", OUT)
