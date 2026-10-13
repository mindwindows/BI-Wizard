"""FU-1 1d(수식 열) 화면 촬영용 합성 데이터 시드(스텁 쿠키 + HTTP API만 사용).

사전 조건: 스택이 떠 있고 `python -m app.cli seed-stub-users`가 한 번 실행된 새 DB.
사용: python3 seed1d.py <포털 API 기준 주소, 예: http://127.0.0.1:65173/bi-wizard/api> <ids1d.json 출력 경로>
모든 값은 합성 데이터다. 비밀값은 다루지 않는다(스텁 쿠키 값은 로그인 ID일 뿐이다).

만드는 것:
- '월별 손익'(시험 A팀, 정의 담당자 stub-definer): 기준월 date, 매출·인원·광고비·물류비(태그 비용) number, 담당 text.
  26개월 행. 인원 0이 2개월(0으로 나눔 E1), 인원 빈 값 1개월, 광고비 빈 값 1개월, 담당 빈 값 1개월.
  계산 열: 1인당 매출 = [매출]/[인원], 총비용 = SUMTAG("비용"), 구분 = IF(...), 손익 = [매출]-[총비용], 손익률 = [손익]/[매출].
- '월별 수금'(시험 B팀, 정의 담당자 stub-multi): 청구·수금 number, 청구 0이 1개월. 계산 열 수금률 = [수금]/[청구].
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


# 26개월(2024-09 ~ 2026-10): 미리보기가 최근 20행을 모두 채우도록 20행보다 많이 둔다.
months = [f"2024-{m:02d}-01" for m in range(9, 13)] + [f"2025-{m:02d}-01" for m in range(1, 13)] + [f"2026-{m:02d}-01" for m in range(1, 11)]
base_sales = [820000, 905000, 1180000, 760000, 995000, 1250000, 1430000, 1010000, 880000, 1320000, 1075000, 990000, 1510000]
sales = [base_sales[(i * 5 + 3) % 13] + (i // 13) * 21000 for i in range(26)]
heads = [8 + (i * 3) % 7 for i in range(26)]
heads[12] = 0   # 0으로 나눔(E1)
heads[20] = 0
heads[17] = ""  # 빈 값
ads = [120000 + (i * 7919) % 90000 for i in range(26)]
ads[9] = ""     # 빈 값(SUMTAG 결과도 빈 값)
logi = [59000 + (i * 4231) % 64000 for i in range(26)]
names = ["김민수", "박지연", "최도윤", "이서준"]
owners = [names[i % 4] for i in range(26)]
owners[15] = ""


def pl_rows():
    for i, month in enumerate(months):
        cells = {"기준월": month, "매출": str(sales[i]), "물류비": str(logi[i])}
        if heads[i] != "":
            cells["인원"] = str(heads[i])
        if ads[i] != "":
            cells["광고비"] = str(ads[i])
        if owners[i]:
            cells["담당"] = owners[i]
        yield cells


teams = {t["code"]: t["id"] for t in must(call("stub-admin", "GET", "/teams"))["items"]}
ids = {"team_a": teams["stub_a"], "team_b": teams["stub_b"]}


def make_dataset(user, team_id, name):
    body = must(call(user, "POST", "/datasets", {"team_id": team_id, "name": name, "date_unit": "month"}))
    return {"id": body["id"], "ver": body["def_version"], "user": user, "cols": {}}


def add_col(ds, name, typ, **kw):
    body = must(call(ds["user"], "POST", f"/datasets/{ds['id']}/columns",
                     dict(expected_version=ds["ver"], display_name=name, type=typ, **kw)))
    ds["ver"] = body["def_version"]
    ds["cols"][name] = body["column"]["id"]


def add_formula(ds, name, expression, **kw):
    body = must(call(ds["user"], "POST", f"/datasets/{ds['id']}/formulas",
                     dict(expected_version=ds["ver"], display_name=name, expression=expression, **kw)))
    ds["ver"] = body["def_version"]
    ds["cols"][name] = body["column"]["id"]


def set_base(ds, col_name):
    body = must(call(ds["user"], "PATCH", f"/datasets/{ds['id']}",
                     {"expected_version": ds["ver"], "base_date_column_id": ds["cols"][col_name]}))
    ds["ver"] = body["def_version"]


def add_row(ds, cells):
    must(call(ds["user"], "POST", f"/datasets/{ds['id']}/rows",
              {"expected_version": ds["ver"], "cells": {str(ds["cols"][k]): v for k, v in cells.items()}}))


if len(sys.argv) > 3 and sys.argv[3] == "backfill":
    # 이미 만든 데이터셋(ids 파일)에 오래된 12개월 행만 더한다(14개월로 시드한 DB 보충용).
    ids = json.load(open(OUT, encoding="utf8"))
    ds = ids["pl"]
    ds["ver"] = must(call("stub-definer", "GET", f"/datasets/{ds['id']}"))["def_version"]
    for k, cells in enumerate(pl_rows()):
        if k < 12:
            add_row(ds, cells)
    print("보충 완료")
    raise SystemExit(0)



# --- 월별 손익 -----------------------------------------------------------------
pl = make_dataset("stub-definer", ids["team_a"], "월별 손익")
add_col(pl, "기준월", "date")
add_col(pl, "매출", "number", rules={"decimals": 0})
add_col(pl, "인원", "number", rules={"decimals": 0})
add_col(pl, "광고비", "number", rules={"decimals": 0}, tag="비용")
add_col(pl, "물류비", "number", rules={"decimals": 0}, tag="비용")
add_col(pl, "담당", "text", rules={"max_length": 20})
set_base(pl, "기준월")
for cells in pl_rows():
    add_row(pl, cells)
add_formula(pl, "1인당 매출", "[매출]/[인원]")
add_formula(pl, "총비용", 'SUMTAG("비용")')
add_formula(pl, "구분", 'IF([매출]>1000000,"우수","보통")')
add_formula(pl, "손익", "[매출]-[총비용]")
add_formula(pl, "손익률", "[손익]/[매출]")
add_formula(pl, "등급", 'IF([매출]>1000000,"A","B")')
ids["pl"] = pl

# --- 월별 수금(다른 팀: S5 목록에 두 번째 행) ---------------------------------------
ar = make_dataset("stub-multi", ids["team_b"], "월별 수금")
add_col(ar, "기준월", "date")
add_col(ar, "청구", "number", rules={"decimals": 0})
add_col(ar, "수금", "number", rules={"decimals": 0})
set_base(ar, "기준월")
for i in range(8):
    add_row(ar, {"기준월": f"2026-{i + 1:02d}-01", "청구": str([500000, 620000, 0, 710000, 540000, 660000, 0, 580000][i]),
                 "수금": str([480000, 600000, 0, 650000, 540000, 600000, 100000, 520000][i])})
add_formula(ar, "수금률", "[수금]/[청구]")
ids["ar"] = ar

with open(OUT, "w", encoding="utf8") as f:
    json.dump(ids, f, ensure_ascii=False, indent=1)
print("시드 완료:", OUT)
