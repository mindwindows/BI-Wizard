"""오류 칸 점검·행 조회·뷰 점검 시험(05 D7~D10, C1~C4와 계산 열, 07 §3-1·§8). 실제 PostgreSQL
필요."""

from __future__ import annotations

import threading
import time
from datetime import date

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import ddl
from app.core.ports import DefinitionHooks
from app.db_metadata import datasets
from app.formula.hook import FormulaDefinitionHook
from app.formula.status import ViewStatus
from app.main import create_app
from tests.api_helpers import make_caller
from tests.conftest import Db
from tests.formula_api_helpers import (
    add_column,
    add_formula,
    dataset_hash,
    err,
    insert_rows,
    make_dataset,
    post_formula,
    version,
)


@pytest.fixture
def db(pg_app_engine, pg_owner_engine, clean_pg):
    yield Db("pg", pg_app_engine, pg_owner_engine)


@pytest.fixture
def ds(api, world):
    dataset = make_dataset(api, world, "점검 시험")
    return {
        "id": dataset["id"],
        "매출": add_column(api, dataset["id"], "매출")["id"],
        "비용": add_column(api, dataset["id"], "비용")["id"],
        "이름": add_column(api, dataset["id"], "이름", "text")["id"],
    }


# --- 행 조회(C1)와 계산 열 (RowViewPort) ----


def test_c1_returns_computed_values_and_error_cells_but_calculated_columns_are_not_stored(
    api, db, ds
):
    ratio = add_formula(api, ds["id"], "비율", "[매출] / [비용]")
    sliced = add_formula(api, ds["id"], "앞글자", "LEFT([이름], [매출])")
    insert_rows(
        db,
        ds["id"],
        [
            {ds["매출"]: 10, ds["비용"]: 4, ds["이름"]: "가나다"},  # 정상
            {ds["매출"]: 1, ds["비용"]: 0, ds["이름"]: "라"},  # 비율 E1
            {ds["매출"]: -1, ds["비용"]: 2, ds["이름"]: "마"},  # 앞글자 E2
            {ds["매출"]: None, ds["비용"]: None, ds["이름"]: None},  # 빈 값(오류 아님)
        ],
    )
    body = api("viewer", "GET", f"/api/datasets/{ds['id']}/rows").json()
    rows = {r["row_id"]: r for r in body["items"]}
    ratio_key, slice_key = str(ratio["id"]), str(sliced["id"])
    assert rows[1]["cells"][ratio_key] == "2.5000000000000000" and rows[1]["errors"] == {}
    assert rows[1]["cells"][slice_key] == "10"[:0] + "가나다"[:3] and rows[1]["errors"] == {}
    # 오류 칸: 값은 null + errors에 코드. 빈 값: 값 null + errors 없음.
    assert rows[2]["cells"][ratio_key] is None and rows[2]["errors"] == {ratio_key: "E1"}
    assert rows[3]["cells"][slice_key] is None and rows[3]["errors"] == {slice_key: "E2"}
    assert rows[4]["cells"][ratio_key] is None and rows[4]["cells"][slice_key] is None
    assert rows[4]["errors"] == {}
    # 저장되지 않는다: 원본 표에 계산 열이 없다.
    names = {
        c["name"] for c in sa.inspect(db.engine).get_columns(f"ds_{ds['id']}", schema="bi_data")
    }
    assert f"c_{ratio['id']}" not in names and f"c_{sliced['id']}" not in names


def test_c1_matches_the_preview_for_every_row(api, db, ds):
    add_formula(api, ds["id"], "비율", "[매출] / [비용]")
    insert_rows(
        db,
        ds["id"],
        [{ds["매출"]: v, ds["비용"]: w} for v, w in [(1, 3), (7, 0), (None, 2), (2.5, 0.5)]],
    )
    preview = api(
        "definer",
        "POST",
        f"/api/datasets/{ds['id']}/formulas/preview",
        json={"expression": "[매출] / [비용]"},
    ).json()
    column_id = next(
        c["id"]
        for c in api("viewer", "GET", f"/api/datasets/{ds['id']}").json()["columns"]
        if c["kind"] == "formula"
    )
    rows = {
        r["row_id"]: r
        for r in api("viewer", "GET", f"/api/datasets/{ds['id']}/rows").json()["items"]
    }
    for item in preview["rows"]:
        row = rows[item["row_id"]]
        assert row["cells"][str(column_id)] == item["value"]
        assert row["errors"].get(str(column_id)) == item["error"]


def test_writes_reject_calculated_column_keys_as_read_only(api, db, ds):
    calc = add_formula(api, ds["id"], "합", "[매출] + [비용]")
    key = str(calc["id"])
    created = api(
        "definer",
        "POST",
        f"/api/datasets/{ds['id']}/rows",
        json={"expected_version": version(api, ds["id"]), "cells": {key: "5"}},
    )
    assert created.status_code == 422
    assert err(created)["details"]["fields"][0] == {
        "field": f"cells.{key}",
        "code": "READ_ONLY",
        "message": "바꿀 수 없는 항목입니다.",
    }
    (row_id,) = insert_rows(db, ds["id"], [{ds["매출"]: 1}])
    patched = api(
        "definer",
        "PATCH",
        f"/api/datasets/{ds['id']}/rows/{row_id}",
        json={
            "expected_version": version(api, ds["id"]),
            "changes": [{"column_id": calc["id"], "expected": None, "value": "5"}],
        },
    )
    assert (
        patched.status_code == 422 and err(patched)["details"]["fields"][0]["code"] == "READ_ONLY"
    )
    pasted = api(
        "definer",
        "POST",
        f"/api/datasets/{ds['id']}/rows/paste",
        json={
            "expected_version": version(api, ds["id"]),
            "column_ids": [calc["id"]],
            "rows": [{"row_id": None, "values": ["5"]}],
        },
    )
    assert pasted.status_code == 422
    assert err(pasted)["details"]["fields"][0]["code"] == "READ_ONLY"


def test_row_writes_return_the_computed_columns_in_the_same_transaction(api, db, ds):
    calc = add_formula(api, ds["id"], "합", "[매출] + [비용]")
    created = api(
        "definer",
        "POST",
        f"/api/datasets/{ds['id']}/rows",
        json={
            "expected_version": version(api, ds["id"]),
            "cells": {str(ds["매출"]): "3", str(ds["비용"]): "4"},
        },
    )
    assert created.status_code == 201, created.text
    row = created.json()["row"]
    assert row["cells"][str(calc["id"])] == "7" and row["errors"] == {}
    patched = api(
        "definer",
        "PATCH",
        f"/api/datasets/{ds['id']}/rows/{row['row_id']}",
        json={
            "expected_version": version(api, ds["id"]),
            "changes": [{"column_id": ds["비용"], "expected": "4", "value": None}],
        },
    )
    assert patched.status_code == 200
    assert patched.json()["row"]["cells"][str(calc["id"])] is None  # 빈 칸 전파


def test_missing_views_do_not_break_reads(api, db, ds):
    """뷰를 읽지 못하면(만들기에 실패한 데이터셋) 행 조회는 계속되고 계산 열만 빈 값이다."""
    calc = add_formula(api, ds["id"], "합", "[매출] + 1")
    insert_rows(db, ds["id"], [{ds["매출"]: 1}])
    with db.writer.begin() as conn:
        conn.execute(
            sa.schema.DropView(sa.Table(f"dv_{ds['id']}", sa.MetaData(), schema="bi_data"))
        )
    response = api("viewer", "GET", f"/api/datasets/{ds['id']}/rows")
    assert response.status_code == 200
    row = response.json()["items"][0]
    assert row["cells"][str(ds["매출"])] == "1" and row["cells"][str(calc["id"])] is None


# --- D7·D8 ----


@pytest.fixture
def errors_ds(api, db, world):
    dataset = make_dataset(api, world, "오류 점검", "month")
    period = add_column(api, dataset["id"], "기간", "date")["id"]
    sales = add_column(api, dataset["id"], "매출")["id"]
    cost = add_column(api, dataset["id"], "비용")["id"]
    api(
        "definer",
        "PATCH",
        f"/api/datasets/{dataset['id']}",
        json={"expected_version": version(api, dataset["id"]), "base_date_column_id": period},
    )
    ratio = add_formula(api, dataset["id"], "비율", "[매출] / [비용]")
    clean = add_formula(api, dataset["id"], "깨끗", "[매출] + [비용]")
    insert_rows(
        db,
        dataset["id"],
        [
            {period: date(2026, m, 1), sales: m, cost: 0 if m in (2, 4, 6) else 1}
            for m in range(1, 8)
        ],
    )
    return {"id": dataset["id"], "ratio": ratio["id"], "clean": clean["id"], "period": period}


def test_d7_lists_only_columns_with_error_cells_and_is_open_to_every_reader(api, errors_ds, world):
    other = make_dataset(api, world, "다른 데이터셋")
    other_cost = add_column(api, other["id"], "원가")["id"]
    add_formula(api, other["id"], "역수", "1 / [원가]")
    assert other_cost
    for who in ("admin", "definer", "entry", "other", "viewer"):
        response = api(who, "GET", "/api/checks/formula-errors")
        assert response.status_code == 200, who
        body = response.json()
        assert set(body) == {"items", "total", "limit", "offset"}
        assert body["items"] == [
            {
                "dataset_id": errors_ds["id"],
                "dataset_name": "오류 점검",
                "team_name": "A팀",
                "column_id": errors_ds["ratio"],
                "column_name": "비율",
                "error_count": 3,
            }
        ]
    assert api(None, "GET", "/api/checks/formula-errors").status_code == 401


def test_d7_pagination(api, db, world, errors_ds):
    for name in ("가", "나", "다"):
        extra = make_dataset(api, world, f"데이터셋 {name}")
        amount = add_column(api, extra["id"], "양")["id"]
        add_formula(api, extra["id"], "역", "1 / [양]")
        insert_rows(db, extra["id"], [{amount: 0}])
    page = api("viewer", "GET", "/api/checks/formula-errors?limit=2&offset=1").json()
    assert page["total"] == 4 and page["limit"] == 2 and page["offset"] == 1
    assert len(page["items"]) == 2


def test_d8_lists_error_cells_with_period_code_and_message_and_paginates(api, errors_ds):
    response = api("viewer", "GET", f"/api/datasets/{errors_ds['id']}/formula-errors")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["items"] == [
        {
            "row_id": row_id,
            "period": f"2026-{month:02d}-01",
            "column_id": errors_ds["ratio"],
            "error": "E1",
            "message": "0으로 나눌 수 없어 계산하지 못했습니다.",
        }
        for row_id, month in ((2, 2), (4, 4), (6, 6))
    ]
    filtered = api(
        "viewer",
        "GET",
        f"/api/datasets/{errors_ds['id']}/formula-errors?column_id={errors_ds['ratio']}&limit=2&offset=1",
    ).json()
    assert filtered["total"] == 3 and [i["row_id"] for i in filtered["items"]] == [4, 6]
    clean = api(
        "viewer",
        "GET",
        f"/api/datasets/{errors_ds['id']}/formula-errors?column_id={errors_ds['clean']}",
    ).json()
    assert clean["items"] == [] and clean["total"] == 0


def test_d8_unknown_dataset_or_column_is_404_and_wrong_column_kind_too(api, errors_ds):
    assert api("viewer", "GET", "/api/datasets/999999/formula-errors").status_code == 404
    path = f"/api/datasets/{errors_ds['id']}/formula-errors"
    assert api("viewer", "GET", f"{path}?column_id=999999").status_code == 404
    assert api("viewer", "GET", f"{path}?column_id={errors_ds['period']}").status_code == 404


def test_d8_combines_several_calculated_columns_in_column_order(api, db, ds):
    first = add_formula(api, ds["id"], "가", "1 / [매출]")
    second = add_formula(api, ds["id"], "나", "1 / [비용]")
    insert_rows(db, ds["id"], [{ds["매출"]: 0, ds["비용"]: 0}, {ds["매출"]: 1, ds["비용"]: 0}])
    items = api("viewer", "GET", f"/api/datasets/{ds['id']}/formula-errors").json()["items"]
    assert [(i["column_id"], i["row_id"]) for i in items] == [
        (first["id"], 1),
        (second["id"], 1),
        (second["id"], 2),
    ]
    page = api("viewer", "GET", f"/api/datasets/{ds['id']}/formula-errors?limit=1&offset=1").json()
    assert [(i["column_id"], i["row_id"]) for i in page["items"]] == [(second["id"], 1)]


def test_oversized_dataset_error_lists_are_capped_by_the_page_limit(api, ds):
    assert (
        api("viewer", "GET", f"/api/datasets/{ds['id']}/formula-errors?limit=201").status_code
        == 422
    )


# --- 정의 변경 직렬화와 행 쓰기 경쟁 ----


def test_concurrent_definition_changes_one_wins_the_other_gets_version_mismatch(
    db, stub_settings, sync, world
):
    """같은 `expected_version`으로 동시에 계산 열을 만들면 한쪽만 성공한다(409
    DEFINITION_VERSION_MISMATCH)."""
    app = create_app(stub_settings, engine=db.engine, dataset_sync=sync)
    with TestClient(app) as client:
        call = make_caller(client)
        dataset = make_dataset(call, world, "경쟁")
        add_column(call, dataset["id"], "매출")
        start = version(call, dataset["id"])
    results = []

    def attempt(name):
        other_app = create_app(stub_settings, engine=db.engine, dataset_sync=sync)
        with TestClient(other_app) as c:
            response = make_caller(c)(
                "definer",
                "POST",
                f"/api/datasets/{dataset['id']}/formulas",
                json={"expected_version": start, "display_name": name, "expression": "1"},
            )
            results.append((response.status_code, response.json()))

    threads = [threading.Thread(target=attempt, args=(n,)) for n in ("가", "나")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    codes = sorted(code for code, _ in results)
    assert codes == [201, 409], results
    loser = next(body for code, body in results if code == 409)
    assert loser["error"]["code"] == "DEFINITION_VERSION_MISMATCH"
    assert loser["error"]["details"]["current_version"] == start + 1


def test_row_write_waiting_on_a_definition_change_then_gets_version_mismatch(
    db, stub_settings, sync, world
):
    """정의 변경(훅 안에서 멈춤)이 `datasets` 행을 잡고 있으면 행 쓰기가 기다렸다가 409가 된다."""
    from app.formula import service as formula_service

    app = create_app(stub_settings, engine=db.engine, dataset_sync=sync)
    with TestClient(app) as client:
        call = make_caller(client)
        dataset = make_dataset(call, world, "경쟁 쓰기")
        sales = add_column(call, dataset["id"], "매출")["id"]
        start = version(call, dataset["id"])
    entered, release = threading.Event(), threading.Event()
    status = ViewStatus()
    real_hook = FormulaDefinitionHook(status)
    hooks = DefinitionHooks()

    def slow_hook(session, dataset_id):
        result = real_hook(session, dataset_id)
        entered.set()
        assert release.wait(timeout=20)
        return result

    hooks.register(slow_hook)

    def define():
        with Session(db.engine) as session:
            return formula_service.create_formula_column(
                session,
                hooks,
                dataset["id"],
                expected_version=start,
                display_name="합",
                expression="[매출] + 1",
                tag=None,
                position=None,
            )

    results: dict[str, object] = {}

    def run_define():
        results["define"] = define()

    definer = threading.Thread(target=run_define)
    definer.start()
    assert entered.wait(timeout=20)

    def write():
        with TestClient(create_app(stub_settings, engine=db.engine, dataset_sync=sync)) as c:
            started = time.monotonic()
            response = make_caller(c)(
                "definer",
                "POST",
                f"/api/datasets/{dataset['id']}/rows",
                json={"expected_version": start, "cells": {str(sales): "1"}},
            )
            results["write"] = (response.status_code, response.json(), time.monotonic() - started)

    writer = threading.Thread(target=write)
    writer.start()
    time.sleep(0.5)  # 행 쓰기가 FOR SHARE를 기다리는 동안
    release.set()
    definer.join(timeout=30)
    writer.join(timeout=30)
    code, body, _elapsed = results["write"]
    assert code in (409, 503), (
        body
    )  # 기다림이 lock_timeout(3초)을 넘으면 WRITE_BUSY도 안전한 결과다
    if code == 409:
        assert body["error"]["code"] == "DEFINITION_VERSION_MISMATCH"
    assert results["define"].def_version == start + 1


# --- 시작 시 해시 대조와 재생성, D9·D10 ----


class CreateViewSpy:
    """`ddl.create_view` 호출을 기록하고 지정한 데이터셋에서는 실패시킨다."""

    def __init__(self, real) -> None:
        self.real = real
        self.calls: list[tuple[str, int]] = []
        self.fail_for: set[int] = set()

    def __call__(self, conn, kind, dataset_id, *args, **kwargs):
        self.calls.append((kind, dataset_id))
        if dataset_id in self.fail_for:
            raise RuntimeError("뷰 만들기 실패 시뮬레이션")
        return self.real(conn, kind, dataset_id, *args, **kwargs)


@pytest.fixture
def spy(monkeypatch) -> CreateViewSpy:
    spy = CreateViewSpy(ddl.create_view)
    monkeypatch.setattr(ddl, "create_view", spy)
    return spy


def start_app(db: Db, settings, sync):
    return TestClient(create_app(settings, engine=db.engine, dataset_sync=sync))


def three_datasets(api, world):
    ids = []
    for name in ("하나", "둘", "셋"):
        dataset = make_dataset(api, world, name)
        column = add_column(api, dataset["id"], "값")["id"]
        add_formula(api, dataset["id"], "두배", "[값] * 2")
        assert column
        ids.append(dataset["id"])
    return ids


def test_startup_with_no_datasets_has_no_views(db, stub_settings, sync):
    with start_app(db, stub_settings, sync) as client:
        health = client.get("/api/health").json()
    assert health["views"] == 0 and health["views_failed_count"] == 0
    assert sa.inspect(db.engine).get_view_names(schema="bi_data") == []


def test_startup_rebuilds_only_the_views_whose_definition_hash_differs(
    api, db, world, stub_settings, sync, spy
):
    first, second, third = three_datasets(api, world)
    good_hash = dataset_hash(db, second)
    with db.writer.begin() as conn:
        conn.execute(sa.update(datasets).where(datasets.c.id == second).values(def_hash="stale"))
    spy.calls.clear()
    with start_app(db, stub_settings, sync) as client:
        health = client.get("/api/health").json()
    assert sorted(spy.calls) == [("de", second), ("dv", second)]  # 다른 데이터셋은 건드리지 않는다
    assert dataset_hash(db, second) == good_hash
    assert health["views"] == 3 and health["views_failed_count"] == 0
    assert first and third


def test_startup_does_not_bump_the_definition_version(api, db, world, stub_settings, sync, spy):
    first, *_ = three_datasets(api, world)
    with db.writer.begin() as conn:
        conn.execute(sa.update(datasets).where(datasets.c.id == first).values(def_hash="stale"))
    before = version(api, first)
    with start_app(db, stub_settings, sync):
        pass
    assert version(api, first) == before


def test_startup_recreates_a_view_that_was_dropped(api, db, world, stub_settings, sync, spy):
    first, *_ = three_datasets(api, world)
    with db.writer.begin() as conn:
        conn.execute(sa.schema.DropView(sa.Table(f"de_{first}", sa.MetaData(), schema="bi_data")))
    spy.calls.clear()
    with start_app(db, stub_settings, sync) as client:
        assert client.get("/api/health").json()["views_failed_count"] == 0
    assert sorted(spy.calls) == [("de", first), ("dv", first)]
    assert f"de_{first}" in sa.inspect(db.engine).get_view_names(schema="bi_data")


def test_startup_failure_does_not_stop_the_app_and_is_reported_then_retried_with_d10(
    api, db, world, stub_settings, sync, spy
):
    first, second, third = three_datasets(api, world)
    with db.writer.begin() as conn:
        conn.execute(
            sa.update(datasets).where(datasets.c.id.in_([second, third])).values(def_hash="stale")
        )
    spy.fail_for = {second}
    with start_app(db, stub_settings, sync) as client:
        call = make_caller(client)
        health = client.get("/api/health")
        assert health.status_code == 200  # 뷰 실패가 있어도 시작하고 200
        assert health.json()["views"] == 3 and health.json()["views_failed_count"] == 1
        report = call("admin", "GET", "/api/checks/views").json()
        assert report["views"] == 3 and report["views_failed_count"] == 1
        (failure,) = report["failed"]
        assert failure["dataset_id"] == second and failure["dataset_name"] == "둘"
        assert failure["reason"].startswith("UNEXPECTED:")
        assert failure["since"].endswith("+09:00")
        for token in ("SELECT", "CREATE VIEW", "시뮬레이션", "bi_data"):
            assert token not in failure["reason"]
        assert dataset_hash(db, third) != "stale"  # 다른 데이터셋은 재생성됐다
        assert (
            dataset_hash(db, second) == "stale"
        )  # 실패한 것은 저장값이 안 바뀐다(다음에 다시 대상)
        # 비관리자는 볼 수 없다.
        assert call("definer", "GET", "/api/checks/views").status_code == 403
        # 원인이 사라진 뒤 D10으로 다시 시도한다.
        spy.fail_for = set()
        retried = call("admin", "POST", "/api/checks/views/retry", json={})
        assert retried.status_code == 200
        assert retried.json() == {"rebuilt": 1, "views_failed_count": 0}
        assert client.get("/api/health").json()["views_failed_count"] == 0
        assert call("admin", "GET", "/api/checks/views").json()["failed"] == []
        assert dataset_hash(db, second) != "stale"
    assert first


def test_d10_retries_given_datasets_even_when_the_hash_is_equal_and_404s_unknown_ids(
    api, db, world, stub_settings, sync, spy
):
    first, second, _third = three_datasets(api, world)
    with start_app(db, stub_settings, sync) as client:
        call = make_caller(client)
        spy.calls.clear()
        response = call("admin", "POST", "/api/checks/views/retry", json={"dataset_ids": [first]})
        assert response.json() == {"rebuilt": 1, "views_failed_count": 0}
        assert sorted(spy.calls) == [("de", first), ("dv", first)]
        none = call("admin", "POST", "/api/checks/views/retry", json={})
        assert none.json() == {"rebuilt": 0, "views_failed_count": 0}
        spy.calls.clear()
        missing = call(
            "admin", "POST", "/api/checks/views/retry", json={"dataset_ids": [first, 999999]}
        )
        assert missing.status_code == 404 and spy.calls == []  # 아무것도 하기 전에 거부
        bad = call("admin", "POST", "/api/checks/views/retry", json={"dataset_ids": "all"})
        assert bad.status_code == 422
    assert second


def test_startup_lock_timeout_is_a_reported_failure_and_does_not_hang(
    api, db, world, stub_settings, sync, spy
):
    first, *_ = three_datasets(api, world)
    with db.writer.begin() as conn:
        conn.execute(sa.update(datasets).where(datasets.c.id == first).values(def_hash="stale"))
    holder = db.writer.connect()
    try:
        holder.execute(sa.text("BEGIN"))
        holder.execute(sa.text("SELECT id FROM datasets WHERE id = :id FOR UPDATE"), {"id": first})
        started = time.monotonic()
        with start_app(db, stub_settings, sync) as client:
            elapsed = time.monotonic() - started
            call = make_caller(client)
            report = call("admin", "GET", "/api/checks/views").json()
            # D10도 잠금을 못 잡으면 503 DEFINITION_BUSY다.
            busy = call("admin", "POST", "/api/checks/views/retry", json={})
    finally:
        holder.rollback()
        holder.close()
    assert elapsed < 15
    assert report["views_failed_count"] == 1
    assert report["failed"][0]["reason"].startswith("LOCK_TIMEOUT:")
    assert busy.status_code == 503 and err(busy)["code"] == "DEFINITION_BUSY"


def test_successful_definition_change_clears_a_recorded_failure(
    api, db, world, stub_settings, sync, spy
):
    first, *_ = three_datasets(api, world)
    with db.writer.begin() as conn:
        conn.execute(sa.update(datasets).where(datasets.c.id == first).values(def_hash="stale"))
    spy.fail_for = {first}
    with start_app(db, stub_settings, sync) as client:
        call = make_caller(client)
        assert client.get("/api/health").json()["views_failed_count"] == 1
        spy.fail_for = set()
        response = post_formula(call, first, "새 계산", "[값] + 1")
        assert response.status_code == 201, response.text
        assert client.get("/api/health").json()["views_failed_count"] == 0
