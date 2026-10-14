"""FU-3(기준값) 화면 촬영용 합성 데이터 시드 초안(스텁 쿠키 + HTTP API만 사용). 아직 실행하지 않았다(backend 구현 뒤 촬영 단계에서 처음 실행한다).

사전 조건: 스택이 떠 있고(AUTH_STUB_ENABLED=true, APP_ENV=local) `python -m app.cli seed-stub-users`가 한 번 실행된 새 DB.
사용: python3 seed3.py <포털 API 기준 주소, 예: http://127.0.0.1:36280/bi-wizard/api> <ids3.json 출력 경로>
모든 값은 합성이다. 비밀값은 다루지 않는다(스텁 쿠키 값은 로그인 ID일 뿐이다).
만드는 것(05 계약 B2·B4·B5·C2·D4·R2·R4):
- 기준값 항목 "전기요금_A팀"(2025년 11.00, 2026년 12.50, 2027년은 일부러 비움), "환율"(값 없음)
- A팀 데이터셋 "월별 전력"(월 단위, 기준 날짜 열 '기준일', 숫자 열 '사용량', 계산 열 '전기요금' = [사용량] * REF("전기요금_A팀"))
  행: 2026-01-01(값 있음), 2027-01-01(2027년 값 없음 -> E4)
- 정정 확인창에서 R6 영향 목록이 보이도록 위 데이터셋이 REF를 쓴다.
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

# 1) 기준값 항목과 연도 값(관리자)
elec = must(call(ADMIN, "POST", "/reference-items", {"name": "전기요금_A팀", "description": "A팀 사무실의 연도별 전기요금 단가"}))
must(call(ADMIN, "POST", f"/reference-items/{elec['id']}/values", {"year": 2025, "value": "11.00"}))
must(call(ADMIN, "POST", f"/reference-items/{elec['id']}/values", {"year": 2026, "value": "12.50"}))
fx = must(call(ADMIN, "POST", "/reference-items", {"name": "환율"}))

# 2) 데이터셋: stub-definer의 팀 번호는 /me에서 얻는다.
me = must(call(DEFINER, "GET", "/me"))
team_id = next(m["team_id"] for m in me["memberships"] if m["role"] == "definer" and m["team_is_active"])
ds = must(call(DEFINER, "POST", "/datasets", {"team_id": team_id, "name": "월별 전력", "date_unit": "month"}))
version = ds["def_version"]


def add_column(name, col_type, **extra):
    global version
    saved = must(call(DEFINER, "POST", f"/datasets/{ds['id']}/columns", {"expected_version": version, "display_name": name, "type": col_type, **extra}))
    version = saved["def_version"]
    return saved["column"]


base_col = add_column("기준일", "date", required=True)
usage_col = add_column("사용량", "number")
ds = must(call(DEFINER, "PATCH", f"/datasets/{ds['id']}", {"expected_version": version, "base_date_column_id": base_col["id"]}))
version = ds["def_version"]
saved = must(call(DEFINER, "POST", f"/datasets/{ds['id']}/formulas", {"expected_version": version, "display_name": "전기요금", "expression": '[사용량] * REF("전기요금_A팀")'}))
version = saved["def_version"]
formula_column_id = saved["column"]["id"]
for day in ("2026-01-01", "2027-01-01"):
    saved = must(call(ENTRY, "POST", f"/datasets/{ds['id']}/rows", {"expected_version": version, "cells": {str(base_col["id"]): day, str(usage_col["id"]): "100"}}))
    version = saved["def_version"]

with open(OUT, "w", encoding="utf8") as handle:
    json.dump({"admin": ADMIN, "member": ENTRY, "elec_id": elec["id"], "fx_id": fx["id"], "dataset_id": ds["id"], "formula_column_id": formula_column_id}, handle, ensure_ascii=False)
print("시드 완료", OUT)
