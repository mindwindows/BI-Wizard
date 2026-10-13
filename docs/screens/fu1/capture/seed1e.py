"""FU-1 1e(Superset 연동) 화면 촬영용 합성 데이터 시드.

사전 조건: 스택(Superset 포함)이 떠 있고 `python -m app.cli seed-stub-users`가 한 번 실행된 새 DB.
비밀값은 파일에 쓰지 않는다. Superset 관리자 계정은 환경변수로만 받는다:
  SUPERSET_ADMIN_USER, SUPERSET_ADMIN_PASSWORD   (임시 env 파일의 값을 셸에서 export)

사용:
  python3 seed1e.py portal    <포털 API 기준 주소(예: http://127.0.0.1:36180/bi-wizard/api)> <ids1e.json>
  python3 seed1e.py superset  <포털 API 기준 주소> <Superset 기준 주소(예: http://127.0.0.1:36180/bi-wizard/superset)> <ids1e.json> <허용 도메인(포털 origin)>
  python3 seed1e.py extra     <포털 API 기준 주소> <데이터셋 이름> [팀 번호]      (빈 데이터셋 하나를 더 만든다. 동기 상태 연출용)

portal   : '일별 손익'(시험 A팀, 365일 x 구분 4종, 계산 열 이익·비용률)과 빈 데이터셋 '월별 수금'을 만든다.
superset : Superset에서 지원 차트 6종 대시보드(d1), 계산 열 숫자 대시보드(d2), 허용 도메인이 다른 대시보드(d3)를 만들고
           임베드를 켠 뒤 포털에 연결(E4)한다. d1은 포털 origin을 허용 도메인으로 쓴다.
모든 값은 합성 데이터다.
"""
import datetime
import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


def portal_call(base, user, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"content-type": "application/json", "Cookie": "bi_stub_login=" + user}
    request = urllib.request.Request(base.rstrip("/") + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
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
        raise SystemExit(f"실패 {status}: {str(body)[:300]}")
    return body


def seed_portal(base, out):
    definer, entry = "stub-definer", "stub-entry"
    team = must(portal_call(base, definer, "GET", "/me"))["memberships"][0]["team_id"]
    ds = must(portal_call(base, definer, "POST", "/datasets", {"team_id": team, "name": "일별 손익", "date_unit": "day"}))
    ds_id, ver = ds["id"], ds["def_version"]
    ids = {"ds": ds_id, "team": team}

    def add_col(name, kind, **extra):
        nonlocal ver
        body = must(portal_call(base, definer, "POST", f"/datasets/{ds_id}/columns", dict(expected_version=ver, display_name=name, type=kind, **extra)))
        ver = body["def_version"]
        return body["column"]["id"]

    ids["cd"] = add_col("기간", "date")
    ids["cs"] = add_col("매출", "number", rules={"decimals": 2})
    ids["cb"] = add_col("비용", "number", rules={"decimals": 2})
    ids["cg"] = add_col("구분", "text")
    ver = must(portal_call(base, definer, "PATCH", f"/datasets/{ds_id}", {"expected_version": ver, "base_date_column_id": ids["cd"]}))["def_version"]
    cats = ["A", "B", "C", "D"]
    start = datetime.date(2025, 7, 1)
    for k in range(365):
        day = start + datetime.timedelta(days=k)
        ci = k % 4
        sales = 1000 + k * 3 + ci * 211 + (k * ci) % 13
        cost = int(sales * 0.6) + ci * 17 + k % 7 + 1
        cells = {str(ids["cd"]): day.isoformat(), str(ids["cs"]): str(sales), str(ids["cb"]): str(cost), str(ids["cg"]): cats[ci]}
        must(portal_call(base, entry, "POST", f"/datasets/{ds_id}/rows", {"expected_version": ver, "cells": cells}))
    body = must(portal_call(base, definer, "POST", f"/datasets/{ds_id}/formulas", {"expected_version": ver, "display_name": "이익", "expression": "[매출] - [비용]"}))
    ids["ci"], ver = body["column"]["id"], body["def_version"]
    body = must(portal_call(base, definer, "POST", f"/datasets/{ds_id}/formulas", {"expected_version": ver, "display_name": "비용률", "expression": "[비용] / [매출]"}))
    ids["cr"] = body["column"]["id"]
    # 빈 데이터셋 하나 더(날짜 열 하나, 수금 열 하나)
    seed_extra(base, "월별 수금", team)
    json.dump(ids, open(out, "w"))
    print("portal 시드 완료", ids)


def seed_extra(base, name, team=None):
    definer = "stub-definer"
    team = int(team) if team else must(portal_call(base, definer, "GET", "/me"))["memberships"][0]["team_id"]
    ds = must(portal_call(base, definer, "POST", "/datasets", {"team_id": team, "name": name, "date_unit": "month"}))
    ver = ds["def_version"]
    body = must(portal_call(base, definer, "POST", f"/datasets/{ds['id']}/columns", {"expected_version": ver, "display_name": "기준월", "type": "date"}))
    ver = body["def_version"]
    must(portal_call(base, definer, "POST", f"/datasets/{ds['id']}/columns", {"expected_version": ver, "display_name": "수금", "type": "number", "rules": {"decimals": 0}}))
    print("데이터셋", ds["id"], name)
    return ds["id"]


class Superset:
    def __init__(self, root, user, password):
        self.root = root.rstrip("/")
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.token = None
        self.csrf = None
        status, body = self.raw("POST", "/api/v1/security/login", {"username": user, "password": password, "provider": "db", "refresh": True}, auth=False)
        if status != 200:
            raise SystemExit(f"Superset 로그인 실패 {status}")
        self.token = body["access_token"]

    def raw(self, method, path, body=None, auth=True):
        headers = {"Content-Type": "application/json"}
        if auth and self.token:
            headers["Authorization"] = "Bearer " + self.token
        if self.csrf and method != "GET":
            headers["X-CSRFToken"] = self.csrf
            headers["Referer"] = self.root + "/"
        path = urllib.parse.quote(path, safe="/?&=:!(),'%_-.~*@+$;")
        request = urllib.request.Request(self.root + path, data=(json.dumps(body).encode() if body is not None else None), method=method, headers=headers)
        try:
            with self.opener.open(request, timeout=120) as response:
                text = response.read()
                status = response.status
        except urllib.error.HTTPError as error:
            text, status = error.read(), error.code
        try:
            return status, json.loads(text)
        except ValueError:
            return status, {"_raw": text[:200].decode("utf8", "replace")}

    def call(self, method, path, body=None):
        if method != "GET" and not self.csrf:
            self.csrf = self.raw("GET", "/api/v1/security/csrf_token/")[1].get("result")
        return self.raw(method, path, body)


def seed_superset(base, root, out, origin):
    ids = json.load(open(out))
    admin = Superset(root, os.environ["SUPERSET_ADMIN_USER"], os.environ["SUPERSET_ADMIN_PASSWORD"])
    # 포털이 등록한 가상 데이터셋(이름 '[시험 A팀] 일별 손익')이 생길 때까지 기다린다
    sid = None
    for _ in range(60):
        status, body = admin.call("GET", "/api/v1/dataset/?q=(filters:!((col:table_name,opr:ct,value:'일별 손익')))")
        if status == 200 and body.get("count") == 1:
            sid = body["result"][0]["id"]
            break
        time.sleep(2)
    if sid is None:
        raise SystemExit("Superset에서 '일별 손익' 데이터셋을 찾지 못했다(동기화 대기)")
    print("superset dataset id", sid)

    def col(key):
        return f"c_{ids[key]}"

    def metric(expr, label):
        return {"expressionType": "SQL", "sqlExpression": expr, "label": label, "hasCustomLabel": True}

    def time_filter():
        return {"expressionType": "SIMPLE", "subject": col("cd"), "operator": "TEMPORAL_RANGE", "comparator": "No filter", "clause": "WHERE", "isExtra": False}

    datasource = f"{sid}__table"
    common = {"datasource": datasource, "adhoc_filters": [time_filter()], "row_limit": 10000, "extra_form_data": {}}
    sum_sales = metric(f"SUM({col('cs')})", "매출합계")
    sum_cost = metric(f"SUM({col('cb')})", "비용합계")
    avg_rate = metric(f"AVG({col('cr')})", "비용률평균")

    def params(viz, **kw):
        base_params = dict(common, viz_type=viz)
        base_params.update(kw)
        return base_params

    six = [
        ("선", "echarts_timeseries_line", params("echarts_timeseries_line", x_axis=col("cd"), time_grain_sqla="P1M", metrics=[sum_sales], groupby=[], x_axis_sort_asc=True, seriesType="line")),
        ("막대", "echarts_timeseries_bar", params("echarts_timeseries_bar", x_axis=col("cd"), time_grain_sqla="P3M", metrics=[sum_cost], groupby=[col("cg")], x_axis_sort_asc=True, stack=None)),
        ("표", "table", params("table", query_mode="aggregate", groupby=[col("cg")], metrics=[sum_sales, sum_cost, avg_rate], all_columns=[], percent_metrics=[], order_desc=True, table_timestamp_format="smart_date", include_search=False, page_length=0)),
        ("큰 숫자 추세", "big_number", params("big_number", x_axis=col("cd"), time_grain_sqla="P1M", metric=sum_sales, show_trend_line=True, start_y_axis_at_zero=True, color_picker={"r": 0, "g": 122, "b": 135, "a": 1}, header_font_size=0.4, subheader_font_size=0.15, show_timestamp=False, rolling_type="None", compare_lag=None)),
        ("원형", "pie", params("pie", groupby=[col("cg")], metric=sum_sales, row_limit=100, sort_by_metric=True, label_type="key_value", show_legend=True, show_labels=True, number_format="SMART_NUMBER")),
        ("혼합", "mixed_timeseries", params("mixed_timeseries", x_axis=col("cd"), time_grain_sqla="P1M", metrics=[sum_sales], groupby=[], seriesType="bar", metrics_b=[sum_cost], groupby_b=[], seriesTypeB="line", adhoc_filters_b=[time_filter()], row_limit_b=10000, x_axis_sort_asc=True)),
    ]
    calc = [
        ("계산 열 원시 표", "table", params("table", query_mode="raw", groupby=[], metrics=[], all_columns=[col("cd"), col("cg"), col("cr"), col("ci")], order_by_cols=[json.dumps([col("cd"), True])], row_limit=12, include_search=False, page_length=0)),
        ("비용률 큰 숫자", "big_number", params("big_number", x_axis=col("cd"), time_grain_sqla="P1M", metric=avg_rate, show_trend_line=True, start_y_axis_at_zero=True, rolling_type="None", compare_lag=None)),
        ("비용률 선", "echarts_timeseries_line", params("echarts_timeseries_line", x_axis=col("cd"), time_grain_sqla="P1M", metrics=[avg_rate], groupby=[], x_axis_sort_asc=True)),
    ]

    def make_dashboard(title, slug, charts, domains):
        status, body = admin.call("POST", "/api/v1/dashboard/", {"dashboard_title": title, "slug": slug, "published": True})
        assert status == 201, (status, body)
        dash_id = body["id"]
        made = []
        for name, viz, chart_params in charts:
            status, body = admin.call("POST", "/api/v1/chart/", {"slice_name": name, "viz_type": viz, "datasource_id": sid, "datasource_type": "table", "params": json.dumps(chart_params), "dashboards": [dash_id]})
            assert status == 201, (name, status, body)
            made.append((body["id"], name))
        half = (len(made) + 1) // 2
        kids = [f"CHART-{i}" for i in range(len(made))]
        positions = {
            "DASHBOARD_VERSION_KEY": "v2",
            "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
            "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": ["ROW-0", "ROW-1"], "parents": ["ROOT_ID"]},
            "HEADER_ID": {"id": "HEADER_ID", "type": "HEADER", "meta": {"text": title}},
        }
        for r, group in enumerate([kids[:half], kids[half:]]):
            positions[f"ROW-{r}"] = {"type": "ROW", "id": f"ROW-{r}", "children": group, "parents": ["ROOT_ID", "GRID_ID"], "meta": {"background": "BACKGROUND_TRANSPARENT"}}
        for i, (chart_id, name) in enumerate(made):
            r = 0 if i < half else 1
            positions[f"CHART-{i}"] = {"type": "CHART", "id": f"CHART-{i}", "children": [], "parents": ["ROOT_ID", "GRID_ID", f"ROW-{r}"], "meta": {"width": 4, "height": 50, "chartId": chart_id, "sliceName": name}}
        scope = {"rootPath": ["ROOT_ID"], "excluded": []}
        filters = [
            {"id": "NATIVE_FILTER-time", "name": "기간", "filterType": "filter_time", "targets": [{}], "defaultDataMask": {"extraFormData": {}, "filterState": {}}, "controlValues": {}, "cascadeParentIds": [], "scope": scope, "type": "NATIVE_FILTER", "description": ""},
            {"id": "NATIVE_FILTER-team", "name": "팀", "filterType": "filter_select", "targets": [{"datasetId": sid, "column": {"name": "team"}}], "defaultDataMask": {"extraFormData": {}, "filterState": {}}, "controlValues": {"multiSelect": True, "enableEmptyFilter": False, "defaultToFirstItem": False, "inverseSelection": False, "searchAllOptions": False}, "cascadeParentIds": [], "scope": scope, "type": "NATIVE_FILTER", "description": ""},
        ]
        meta = {"native_filter_configuration": filters, "positions": positions, "chart_configuration": {}, "global_chart_configuration": {"scope": scope, "chartsInScope": [c for c, _ in made]}, "color_scheme": "", "refresh_frequency": 0, "expanded_slices": {}, "label_colors": {}, "timed_refresh_immune_slices": [], "cross_filters_enabled": False, "default_filters": "{}", "shared_label_colors": [], "map_label_colors": {}, "color_scheme_domain": []}
        status, body = admin.call("PUT", f"/api/v1/dashboard/{dash_id}", {"position_json": json.dumps(positions), "json_metadata": json.dumps(meta)})
        assert status == 200, (status, body)
        status, body = admin.call("POST", f"/api/v1/dashboard/{dash_id}/embedded", {"allowed_domains": domains})
        assert status == 200, (status, body)
        return {"superset_id": dash_id, "uuid": body["result"]["uuid"], "title": title}

    out_ids = dict(ids, sid=sid)
    specs = (
        ("d1", "손익 현황 (지원 차트 6종)", "shot1e-six", six, [origin]),
        ("d2", "계산 열 숫자 확인", "shot1e-calc", calc, [origin]),
        ("d3", "허용 도메인이 다른 대시보드", "shot1e-blocked", calc[:1], ["https://other.example"]),
    )
    for key, title, slug, charts, domains in specs:
        info = make_dashboard(title, slug, charts, domains)
        created = must(portal_call(base, "stub-admin", "POST", "/dashboards", {"name": title, "embedded_uuid": info["uuid"]}))
        info["portal_id"] = created["id"]
        out_ids[key] = info
        print(key, info)
    json.dump(out_ids, open(out, "w"))


if __name__ == "__main__":
    command = sys.argv[1]
    if command == "portal":
        seed_portal(sys.argv[2], sys.argv[3])
    elif command == "superset":
        seed_superset(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
    elif command == "extra":
        seed_extra(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
    else:
        raise SystemExit("portal | superset | extra")
