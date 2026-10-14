"""`REF` 기준값을 실제 PostgreSQL에서 시험한다(07 §3-2, 06 §3-4, 03b 32, 05 R5·B4).

- 함수 사전 `REF`의 `cases`를 실제 기준값 표로 평가한다.
- 안 B 뷰: `REF` 계산 열의 `dv_`·`de_`가 연도 일치 값·누락 E4(이월 없음)를 내고, 읽기 전용 계정은
  뷰는 읽지만 기준값 표는 직접 못 읽는다(42501). 인덱스를 쓴다(EXPLAIN).
- 기준값을 정정·추가해도 뷰 정의·해시·버전이 그대로이고 DDL이 0건인데 값은 바뀐다.
- C-6: 기준 날짜 열 해제는 `BASE_DATE_IN_USE`(422)로 막히고 모든 것이 그대로다.
- 컴파일 호출 지점 6곳이 같은 결과를 낸다(환경 전달).
- 동시성: 정정 중에도 뷰 읽기가 막히지 않고, 정정과 정의 변경을 동시에 반복해도 교착이 없다.
"""

from __future__ import annotations

import datetime
import json
import threading
from decimal import Decimal
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.auth.models import CurrentUser
from app.core.db_errors import sqlstate
from app.dataset import service as dataset_service
from app.db_metadata import dataset_columns, datasets
from app.formula import ReferenceEnv, compile_formula, get_default_registry
from app.formula.cases import ERROR, OK, REJECT
from app.formula.errors import CELL_ERROR_BY_NUMBER
from app.formula.hook import FormulaDefinitionHook, make_probe
from app.formula.reconcile import view_needs_rebuild
from app.formula.refenv import load_env
from app.formula.views import build_column_infos, compile_all, source_columns, source_table
from tests.audit_helpers import Ctx, audit_rows
from tests.conftest import Db
from tests.formula_api_helpers import (
    add_column,
    add_formula,
    dataset_hash,
    err,
    insert_rows,
    make_dataset,
    post_formula,
    put_formula,
    version,
    view_rows,
)
from tests.formula_runner import case_columns, case_env, case_sources, values_equal
from tests.reference_helpers import (
    add_item,
    add_value,
    api_add_item,
    api_add_value,
    api_update_value,
    item_rows,
    set_value,
    value_rows,
)
from tests.test_dataset_archive_pg import FORBIDDEN_STATEMENT, StatementLog, fingerprint

D = datetime.date


@pytest.fixture
def db(pg_app_engine, pg_owner_engine, clean_pg):
    yield Db("pg", pg_app_engine, pg_owner_engine)


# --- 준비 도구 ----


def make_ref_dataset(
    ctx: Ctx, name: str = "기준값 시험", date_unit: str = "day", value_name: str = "사용량"
) -> dict[str, int]:
    """기준 날짜 열(일자)과 숫자 열(사용량)이 있는 데이터셋. 행은 0개, 계산 열은 아직 없다."""
    dataset = make_dataset(ctx.call, ctx.world, name, date_unit)
    date_col = add_column(ctx.call, dataset["id"], "일자", "date")["id"]
    value_col = add_column(ctx.call, dataset["id"], value_name)["id"]
    response = ctx.call(
        "definer",
        "PATCH",
        f"/api/datasets/{dataset['id']}",
        json={
            "expected_version": version(ctx.call, dataset["id"]),
            "base_date_column_id": date_col,
        },
    )
    assert response.status_code == 200, response.text
    return {"id": dataset["id"], "date": date_col, "value": value_col}


def seed_item(ctx: Ctx, name: str = "전기요금", values: dict[int, str] | None = None) -> int:
    item = add_item(ctx.db, name, ctx.uid("admin"))
    for year, value in (values or {}).items():
        add_value(ctx.db, item, year, value, ctx.uid("admin"))
    return item


def view_def(db: Db, dataset_id: int, kind: str = "dv") -> str:
    with db.writer.connect() as conn:
        return conn.execute(
            sa.text("SELECT pg_get_viewdef(to_regclass(:n)::oid)"),
            {"n": f"bi_data.{kind}_{dataset_id}"},
        ).scalar_one()


def column_values(db: Db, dataset_id: int, column_id: int) -> list[Any]:
    return [r[f"c_{column_id}"] for r in view_rows(db, dataset_id)]


def column_errors(db: Db, dataset_id: int, column_id: int) -> list[Any]:
    return [r[f"e_{column_id}"] for r in view_rows(db, dataset_id, "de")]


# --- 함수 사전 `REF`의 사례를 실제 기준값 표로 ----


def _run_reference_case(db: Db, case, user_id: int) -> tuple[Any, Any, Any]:
    """사례의 기준값을 실제 표에 넣고 (컴파일 결과, 값, 오류 번호)를 돌려준다."""
    ids: dict[str, int] = {}
    for name, per_year in case.refs.items():
        item = add_item(db, f"{name}", user_id)
        ids[name] = item
        for year, value in per_year.items():
            add_value(db, item, year, value, user_id)
    columns = case_columns(case)
    base = case_env(case, columns).base_date_column_id
    env = ReferenceEnv(item_ids=ids, base_date_column_id=base)
    with db.engine.connect() as conn:
        result = compile_formula(
            case.expression,
            columns,
            source_columns=case_sources(case, columns, typed_cast=True),
            env=env,
        )
        if not result.ok or case.expect == REJECT:
            return result, None, None
        error = result.error if result.error is not None else sa.cast(sa.null(), sa.SmallInteger())
        row = conn.execute(sa.select(result.value.label("v"), error.label("e"))).one()
        return result, row.v, row.e


def test_every_ref_dictionary_case_evaluates_on_postgresql(db: Db, ctx: Ctx):
    spec = get_default_registry().get("REF")
    assert spec is not None and spec.precheck is not None
    for case in spec.cases:
        result, value, error = _run_reference_case(db, case, ctx.uid("admin"))
        label = f"{case.expression} {dict(case.row)}"
        if case.expect == REJECT:
            assert not result.ok and case.error in [i.code for i in result.issues], label
        elif case.expect == ERROR:
            assert result.ok and value is None, label
            assert error is not None and CELL_ERROR_BY_NUMBER[int(error)] == case.error, label
        else:
            assert case.expect == OK and result.ok and error is None, label
            assert values_equal(value, case.value), (label, value)
        db.writer.dispose()
        _clear_references(db)


def _clear_references(db: Db) -> None:
    from app.db_metadata import reference_items, reference_values

    with db.writer.begin() as conn:
        conn.execute(sa.delete(reference_values))
        conn.execute(sa.delete(reference_items))


# --- 뷰: 연도 일치, 누락 E4, 이월 없음 ----


def test_view_gives_the_year_value_and_e4_without_carrying_over(ctx: Ctx, db: Db):
    ds = make_ref_dataset(ctx)
    seed_item(ctx, "전기요금", {2025: "10", 2026: "12.5"})
    column = add_formula(ctx.call, ds["id"], "요금", 'REF("전기요금")')["id"]
    insert_rows(
        db,
        ds["id"],
        [
            {ds["date"]: D(2025, 12, 31)},
            {ds["date"]: D(2026, 1, 1)},
            {ds["date"]: D(2026, 12, 31)},
            {ds["date"]: D(2027, 1, 1)},  # 2027 값이 없다: 전년 값을 이월하지 않는다
            {ds["date"]: D(2024, 6, 30)},  # 2024 값도 없다
        ],
    )
    assert column_values(db, ds["id"], column) == [
        Decimal("10"),
        Decimal("12.5"),
        Decimal("12.5"),
        None,
        None,
    ]
    assert column_errors(db, ds["id"], column) == [None, None, None, 4, 4]


def test_e4_appears_in_the_check_screen_apis(ctx: Ctx, db: Db):
    ds = make_ref_dataset(ctx)
    seed_item(ctx, "전기요금", {2026: "1"})
    column = add_formula(ctx.call, ds["id"], "요금", 'REF("전기요금")')["id"]
    insert_rows(db, ds["id"], [{ds["date"]: D(2026, 1, 1)}, {ds["date"]: D(2030, 1, 1)}])
    summary = ctx.call("viewer", "GET", "/api/checks/formula-errors").json()["items"]
    assert [(i["dataset_id"], i["column_id"], i["error_count"]) for i in summary] == [
        (ds["id"], column, 1)
    ]
    cells = ctx.call("viewer", "GET", f"/api/datasets/{ds['id']}/formula-errors").json()["items"]
    assert [(c["column_id"], c["error"]) for c in cells] == [(column, "E4")]
    assert "기준값" in cells[0]["message"]
    shown = ctx.call("viewer", "GET", f"/api/datasets/{ds['id']}/formulas/{column}").json()
    assert shown["error_count"] == 1 and shown["text"] == 'REF("전기요금")'
    rows = ctx.call("viewer", "GET", f"/api/datasets/{ds['id']}/rows").json()
    assert [r["errors"].get(str(column)) for r in rows["items"]] == [None, "E4"] or [
        r["errors"].get(str(column)) for r in rows["items"]
    ] == ["E4", None]
    functions = ctx.call("viewer", "GET", "/api/formulas/functions").json()
    assert any(f["name"] == "REF" and f["returns"] == "숫자" for f in functions["functions"])
    assert "E4" in functions["cell_errors"]


def test_host_formulas_use_the_reference_value_and_propagate_e4(ctx: Ctx, db: Db):
    ds = make_ref_dataset(ctx)
    seed_item(ctx, "단가", {2026: "2.5"})
    seed_item(ctx, "공제", {2026: "1"})
    mul = add_formula(ctx.call, ds["id"], "곱", '[사용량] * REF("단가")')["id"]
    sub = add_formula(ctx.call, ds["id"], "차", 'REF("단가") - REF("공제")')["id"]
    guard = add_formula(ctx.call, ds["id"], "안전", 'IFERROR(REF("단가"), 0)')["id"]
    pick = add_formula(ctx.call, ds["id"], "선택", 'IF([사용량] > 5, REF("단가"), 0)')["id"]
    round_ = add_formula(ctx.call, ds["id"], "반올림", 'ROUND(REF("단가") * 3, 0)')["id"]
    nested = add_formula(ctx.call, ds["id"], "중첩", "[곱] + 1")["id"]  # 계산 열이 REF 열을 참조
    insert_rows(
        db,
        ds["id"],
        [
            {ds["date"]: D(2026, 3, 1), ds["value"]: 4},  # 값 있음, 5 이하
            {ds["date"]: D(2026, 3, 2), ds["value"]: 10},
            {ds["date"]: D(2026, 3, 3), ds["value"]: None},  # 사용량 빈 값
            {ds["date"]: D(2027, 3, 1), ds["value"]: 10},  # 연도 없음: E4
        ],
    )
    values, errors = view_rows(db, ds["id"]), view_rows(db, ds["id"], "de")
    got = lambda rows, col: [r[col] for r in rows]  # noqa: E731
    assert got(values, f"c_{mul}") == [Decimal("10"), Decimal("25"), None, None]
    assert got(errors, f"e_{mul}") == [None, None, None, 4]  # 빈 값은 오류가 아니다
    assert got(values, f"c_{sub}") == [Decimal("1.5")] * 3 + [None]
    assert got(errors, f"e_{sub}") == [None, None, None, 4]
    assert got(values, f"c_{guard}") == [Decimal("2.5")] * 3 + [Decimal("0")]  # IFERROR가 E4를 대체
    assert got(errors, f"e_{guard}") == [None] * 4
    assert got(values, f"c_{pick}") == [Decimal("0"), Decimal("2.5"), None, None]
    assert got(errors, f"e_{pick}") == [None, None, None, 4]
    assert got(values, f"c_{round_}") == [Decimal("8")] * 3 + [None]
    assert got(values, f"c_{nested}") == [Decimal("11"), Decimal("26"), None, None]
    assert got(errors, f"e_{nested}") == [None, None, None, 4]


def test_the_view_reads_reference_values_only_through_the_one_allowed_shape(ctx: Ctx, db: Db):
    ds = make_ref_dataset(ctx)
    item = seed_item(ctx, "전기요금", {2026: "1"})
    add_formula(ctx.call, ds["id"], "요금", 'REF("전기요금")')
    for kind in ("dv", "de"):
        definition = view_def(db, ds["id"], kind)
        assert "reference_values" in definition and "reference_items" not in definition
        assert (
            f"item_id = {item}" in definition
        )  # 항목 번호는 정수 상수로 굳는다(이름은 SQL에 없다)
        assert "전기요금" not in definition
        assert "EXTRACT(year FROM" in definition and f"c_{ds['date']}" in definition


# --- 읽기 전용 계정: 뷰는 읽고 표는 직접 못 읽는다 ----


def test_readonly_account_reads_the_view_but_not_the_reference_tables(
    ctx: Ctx, db: Db, pg_readonly_engine: Engine
):
    ds = make_ref_dataset(ctx)
    seed_item(ctx, "전기요금", {2026: "12.5"})
    column = add_formula(ctx.call, ds["id"], "요금", 'REF("전기요금")')["id"]
    insert_rows(db, ds["id"], [{ds["date"]: D(2026, 5, 1)}])
    with pg_readonly_engine.connect() as conn:
        value = conn.execute(sa.text(f"SELECT c_{column} FROM bi_data.dv_{ds['id']}")).scalar_one()  # noqa: S608
        assert value == Decimal("12.5")
        for table in ("reference_values", "reference_items"):
            with pytest.raises(DBAPIError) as caught:
                conn.execute(sa.text(f"SELECT * FROM public.{table}"))  # noqa: S608
            assert sqlstate(caught.value) == "42501"
            conn.rollback()
    with db.writer.connect() as conn:
        acl = conn.execute(
            sa.text(
                "SELECT relname, relacl::text FROM pg_class "
                "WHERE relname IN ('reference_items', 'reference_values')"
            )
        ).all()
    assert all("bi_readonly" not in (row.relacl or "") and "=" in (row.relacl or "") for row in acl)
    assert all(not (row.relacl or "").startswith("=") and ",=" not in row.relacl for row in acl)


def test_the_view_uses_the_unique_index_for_the_year_lookup(ctx: Ctx, db: Db):
    ds = make_ref_dataset(ctx)
    for index in range(40):  # 항목 40개 x 연도 50개: 표가 충분히 커야 계획이 인덱스를 고른다
        item = add_item(db, f"항목{index}", ctx.uid("admin"))
        with db.writer.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO reference_values (item_id, year, number_value, created_by) "
                    "SELECT :i, y, 1, :u FROM generate_series(1960, 2009) y"
                ),
                {"i": item, "u": ctx.uid("admin")},
            )
    seed_item(ctx, "전기요금", {2026: "1"})
    column = add_formula(ctx.call, ds["id"], "요금", 'REF("전기요금")')["id"]
    insert_rows(
        db, ds["id"], [{ds["date"]: D(2026, 1, 1) + datetime.timedelta(days=n)} for n in range(300)]
    )
    with db.writer.begin() as conn:
        conn.execute(sa.text("ANALYZE reference_values"))
        conn.execute(sa.text(f"ANALYZE bi_data.ds_{ds['id']}"))
        plan = conn.execute(
            sa.text(f"EXPLAIN (FORMAT JSON) SELECT c_{column} FROM bi_data.dv_{ds['id']}")  # noqa: S608
        ).scalar_one()
    text = json.dumps(plan) if not isinstance(plan, str) else plan
    assert "uq_reference_values_item_id_year" in text and "Index" in text
    assert "Seq Scan on reference_values" not in text


# --- 정정·추가는 뷰를 다시 만들지 않는다 ----


def test_correction_changes_values_without_touching_view_definitions_or_ddl(ctx: Ctx, db: Db):
    ds = make_ref_dataset(ctx)
    item = api_add_item(ctx.call, "전기요금").json()["id"]
    first = api_add_value(ctx.call, item, 2026, "10").json()["id"]
    api_add_value(ctx.call, item, 2025, "7")
    column = add_formula(ctx.call, ds["id"], "요금", 'REF("전기요금")')["id"]
    insert_rows(db, ds["id"], [{ds["date"]: D(2026, 2, 1)}, {ds["date"]: D(2025, 2, 1)}])
    before = fingerprint(db, ds["id"])
    defs_before = (view_def(db, ds["id"]), view_def(db, ds["id"], "de"))
    hash_before, version_before = dataset_hash(db, ds["id"]), version(ctx.call, ds["id"])
    assert column_values(db, ds["id"], column) == [Decimal("10"), Decimal("7")]

    with StatementLog(db.engine) as app_log, StatementLog(db.writer) as owner_log:
        assert api_update_value(ctx.call, item, first, "11.25").status_code == 200
    forbidden = [
        s for s in (*app_log.statements, *owner_log.statements) if FORBIDDEN_STATEMENT.match(s)
    ]
    assert forbidden == []  # CREATE·ALTER·DROP·GRANT 0건
    assert not any("bi_data" in s for s in app_log.statements)  # 정정은 bi_data를 건드리지 않는다
    assert column_values(db, ds["id"], column) == [Decimal("11.25"), Decimal("7")]  # 정정된 연도만
    after = fingerprint(db, ds["id"])
    assert after == before  # 뷰 정의 해시·행 해시·객체 번호·def_hash·def_version·수식이 같다
    assert (view_def(db, ds["id"]), view_def(db, ds["id"], "de")) == defs_before
    assert (dataset_hash(db, ds["id"]), version(ctx.call, ds["id"])) == (
        hash_before,
        version_before,
    )


def test_adding_the_missing_year_turns_e4_into_a_value_without_ddl(ctx: Ctx, db: Db):
    ds = make_ref_dataset(ctx)
    item = api_add_item(ctx.call, "전기요금").json()["id"]
    column = add_formula(ctx.call, ds["id"], "요금", 'REF("전기요금")')["id"]
    insert_rows(db, ds["id"], [{ds["date"]: D(2026, 2, 1)}])
    assert column_values(db, ds["id"], column) == [None] and column_errors(
        db, ds["id"], column
    ) == [4]
    before = fingerprint(db, ds["id"])
    with StatementLog(db.engine) as log:
        assert api_add_value(ctx.call, item, 2026, "3").status_code == 201
    assert [s for s in log.statements if FORBIDDEN_STATEMENT.match(s)] == []
    assert column_values(db, ds["id"], column) == [Decimal("3")]
    assert column_errors(db, ds["id"], column) == [None]
    assert fingerprint(db, ds["id"]) == before


def test_preview_matches_the_view_before_and_after_a_correction(ctx: Ctx, db: Db):
    ds = make_ref_dataset(ctx)
    item = api_add_item(ctx.call, "전기요금").json()["id"]
    value_id = api_add_value(ctx.call, item, 2026, "10").json()["id"]
    column = add_formula(ctx.call, ds["id"], "요금", '[사용량] * REF("전기요금")')["id"]
    insert_rows(
        db,
        ds["id"],
        [{ds["date"]: D(2026, 2, 1), ds["value"]: 2}, {ds["date"]: D(2027, 2, 1), ds["value"]: 3}],
    )
    for new_value in (None, "20"):
        if new_value is not None:
            assert api_update_value(ctx.call, item, value_id, new_value).status_code == 200
        preview = ctx.call(
            "definer",
            "POST",
            f"/api/datasets/{ds['id']}/formulas/preview",
            json={"expression": '[사용량] * REF("전기요금")', "column_id": column},
        )
        assert preview.status_code == 200, preview.text
        body = preview.json()
        by_row = {r["row_id"]: r for r in body["rows"]}
        view_values, view_errors = view_rows(db, ds["id"]), view_rows(db, ds["id"], "de")
        for v_row, e_row in zip(view_values, view_errors, strict=True):
            shown = by_row[v_row["row_id"]]
            expected = v_row[f"c_{column}"]
            assert (Decimal(shown["value"]) if shown["value"] is not None else None) == expected
            code = e_row[f"e_{column}"]
            assert shown["error"] == (CELL_ERROR_BY_NUMBER[code] if code else None)
        assert body["error_count"] == 1  # 2027년 행은 늘 E4


# --- C0·저장: REF_UNKNOWN·BASE_DATE_REQUIRED ----


def test_check_reports_unknown_item_and_missing_base_date_with_positions(ctx: Ctx):
    seed_item(ctx, "전기요금", {2026: "1"})
    ds = make_ref_dataset(ctx)
    path = f"/api/datasets/{ds['id']}/formulas/check"

    unknown = ctx.call("definer", "POST", path, json={"expression": 'REF("전기요금_B팀")'}).json()
    assert unknown["ok"] is False
    (issue,) = unknown["errors"]
    assert issue["code"] == "REF_UNKNOWN" and "전기요금_B팀" in issue["message"]
    assert (issue["start"], issue["end"]) == (4, 13)  # 인수 글자 구간(따옴표 포함)
    assert "전기요금" in issue["message"]  # 비슷한 이름 안내

    ok = ctx.call("definer", "POST", path, json={"expression": 'REF("전기요금") * 2'}).json()
    assert ok["ok"] is True and ok["result_type"] == "number" and ok["refs"] == []

    nodate = make_dataset(ctx.call, ctx.world, "날짜 없음")
    bare = ctx.call(
        "definer",
        "POST",
        f"/api/datasets/{nodate['id']}/formulas/check",
        json={"expression": 'REF("전기요금")'},
    ).json()
    assert [e["code"] for e in bare["errors"]] == ["BASE_DATE_REQUIRED"]
    assert "기준 날짜 열" in bare["errors"][0]["message"]

    both = ctx.call(
        "definer",
        "POST",
        f"/api/datasets/{nodate['id']}/formulas/check",
        json={"expression": 'REF("없는 이름")'},
    ).json()
    assert sorted(e["code"] for e in both["errors"]) == ["BASE_DATE_REQUIRED", "REF_UNKNOWN"]

    shape = [
        ("REF()", "ARG_COUNT"),
        ('REF("전기요금", 2026)', "ARG_COUNT"),
        ("REF(1)", "ARG_TYPE"),
        ('REF("전기" & "요금")', "CONST_REQUIRED"),
        ('REF("가' + "나" * 60 + '")', "CONST_RANGE"),
    ]
    for expression, code in shape:
        result = ctx.call("definer", "POST", path, json={"expression": expression}).json()
        assert code in [e["code"] for e in result["errors"]], expression


def test_nfd_item_name_matches_the_nfc_item(ctx: Ctx):
    import unicodedata

    seed_item(ctx, "전기요금", {2026: "1"})
    ds = make_ref_dataset(ctx)
    nfd = unicodedata.normalize("NFD", "전기요금")
    result = ctx.call(
        "definer",
        "POST",
        f"/api/datasets/{ds['id']}/formulas/check",
        json={"expression": f'REF("{nfd}")'},
    ).json()
    assert result["ok"] is True


def test_save_and_preview_reject_bad_ref_with_formula_invalid(ctx: Ctx):
    ds = make_ref_dataset(ctx)
    for expression, code in (('REF("없음")', "REF_UNKNOWN"), ("REF()", "ARG_COUNT")):
        saved = post_formula(ctx.call, ds["id"], "나쁜 식", expression)
        assert (saved.status_code, err(saved)["code"]) == (422, "FORMULA_INVALID"), expression
        assert err(saved)["details"]["errors"][0]["code"] == code
        preview = ctx.call(
            "definer",
            "POST",
            f"/api/datasets/{ds['id']}/formulas/preview",
            json={"expression": expression},
        )
        assert (preview.status_code, err(preview)["code"]) == (422, "FORMULA_INVALID")
    columns = ctx.call("definer", "GET", f"/api/datasets/{ds['id']}").json()["columns"]
    assert [c for c in columns if c["kind"] == "formula"] == []


def test_ref_in_a_dataset_without_base_date_is_rejected_on_save(ctx: Ctx):
    seed_item(ctx, "전기요금", {2026: "1"})
    dataset = make_dataset(ctx.call, ctx.world, "날짜 없는 데이터셋")
    saved = post_formula(ctx.call, dataset["id"], "요금", 'REF("전기요금")')
    assert (saved.status_code, err(saved)["code"]) == (422, "FORMULA_INVALID")
    assert err(saved)["details"]["errors"][0]["code"] == "BASE_DATE_REQUIRED"


def test_ref_does_not_make_formula_deps_edges_and_is_a_number(ctx: Ctx, db: Db):
    ds = make_ref_dataset(ctx)
    seed_item(ctx, "전기요금", {2026: "1"})
    column = add_formula(ctx.call, ds["id"], "요금", 'REF("전기요금")')
    assert column["type"] == "number"
    from app.db_metadata import formula_deps

    assert db.rows(formula_deps) == []  # 간선 없음(07 §3-2)
    stored = db.rows(sa.table("formulas", sa.column("column_id"), sa.column("ast")))
    assert stored[0]["ast"] == {"t": "call", "n": "REF", "a": [{"t": "text", "v": "전기요금"}]}
    assert "item" not in json.dumps(stored[0]["ast"])  # 항목 번호는 저장하지 않는다


# --- C-6: 기준 날짜 열 해제 ----


def patch_dataset(ctx: Ctx, dataset_id: int, **body: Any):
    return ctx.call(
        "definer",
        "PATCH",
        f"/api/datasets/{dataset_id}",
        json={"expected_version": version(ctx.call, dataset_id), **body},
    )


def test_clearing_the_base_date_column_is_blocked_while_ref_is_used(ctx: Ctx, db: Db):
    ds = make_ref_dataset(ctx)
    seed_item(ctx, "전기요금", {2026: "1"})
    add_formula(ctx.call, ds["id"], "요금 하나", 'REF("전기요금")')
    second = add_formula(ctx.call, ds["id"], "요금 둘", 'REF("전기요금") * 2')["id"]
    before = fingerprint(db, ds["id"])
    audit_before = audit_rows(db)
    response = patch_dataset(ctx, ds["id"], base_date_column_id=None)
    assert (response.status_code, err(response)["code"]) == (422, "BASE_DATE_IN_USE")
    details = err(response)["details"]
    assert set(details["column"]) == {"column_id", "display_name"}
    assert details["column"]["display_name"] in {"요금 하나", "요금 둘"}
    assert details["column"]["column_id"] in {second - 1, second}
    assert "REF" in err(response)["message"] and "기준 날짜 열을 해제" in err(response)["message"]
    assert fingerprint(db, ds["id"]) == before  # 열·뷰·수식·버전·해시가 그대로
    assert audit_rows(db) == audit_before  # 감사 행이 없다
    with db.writer.connect() as conn:  # DDL(NOT NULL·CHECK·유일 인덱스)도 함께 롤백됐다
        idx = conn.execute(
            sa.text("SELECT count(*) FROM pg_indexes WHERE indexname = :n"),
            {"n": f"ux_ds_{ds['id']}_period"},
        ).scalar_one()
        assert idx == 1
        nullable = conn.execute(
            sa.text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_schema='bi_data' AND table_name=:t AND column_name=:c"
            ),
            {"t": f"ds_{ds['id']}", "c": f"c_{ds['date']}"},
        ).scalar_one()
        assert nullable == "NO"
    base = ctx.call("definer", "GET", f"/api/datasets/{ds['id']}").json()["base_date_column_id"]
    assert base == ds["date"]


def test_clearing_the_base_date_column_is_allowed_when_no_ref_is_used(ctx: Ctx):
    ds = make_ref_dataset(ctx)
    add_formula(ctx.call, ds["id"], "배", "[사용량] * 2")
    response = patch_dataset(ctx, ds["id"], base_date_column_id=None)
    assert response.status_code == 200 and response.json()["base_date_column_id"] is None


def test_base_date_in_use_judgement_order(ctx: Ctx, db: Db):
    ds = make_ref_dataset(ctx)
    seed_item(ctx, "전기요금", {2026: "1"})
    add_formula(ctx.call, ds["id"], "요금", 'REF("전기요금")')
    # 낡은 버전이 먼저(409)
    stale = ctx.call(
        "definer",
        "PATCH",
        f"/api/datasets/{ds['id']}",
        json={"expected_version": 1, "base_date_column_id": None},
    )
    assert (stale.status_code, err(stale)["code"]) == (409, "DEFINITION_VERSION_MISMATCH")
    # 행이 있으면 DATASET_HAS_ROWS가 먼저(422): 해제는 행이 0개일 때만 도달한다
    insert_rows(db, ds["id"], [{ds["date"]: D(2026, 1, 1)}])
    rows = patch_dataset(ctx, ds["id"], base_date_column_id=None)
    assert (rows.status_code, err(rows)["code"]) == (422, "DATASET_HAS_ROWS")
    with db.writer.begin() as conn:
        conn.execute(sa.text(f"DELETE FROM bi_data.ds_{ds['id']}"))  # noqa: S608
    # 보관 중이면 DATASET_ARCHIVED(409)가 먼저
    assert ctx.call("definer", "POST", f"/api/datasets/{ds['id']}/archive").status_code == 200
    archived = patch_dataset(ctx, ds["id"], base_date_column_id=None)
    assert (archived.status_code, err(archived)["code"]) == (409, "DATASET_ARCHIVED")
    assert ctx.call("definer", "POST", f"/api/datasets/{ds['id']}/restore").status_code == 200
    final = patch_dataset(ctx, ds["id"], base_date_column_id=None)
    assert (final.status_code, err(final)["code"]) == (422, "BASE_DATE_IN_USE")


def test_switching_the_base_date_column_rebuilds_ref_on_the_new_column(ctx: Ctx, db: Db):
    ds = make_ref_dataset(ctx)
    other = add_column(ctx.call, ds["id"], "다른 일자", "date")["id"]
    seed_item(ctx, "전기요금", {2025: "1", 2026: "2"})
    column = add_formula(ctx.call, ds["id"], "요금", 'REF("전기요금")')["id"]
    before = view_def(db, ds["id"])
    assert f"c_{ds['date']}" in before
    response = patch_dataset(ctx, ds["id"], base_date_column_id=other)
    assert response.status_code == 200, response.text
    after = view_def(db, ds["id"])
    assert f"c_{other}" in after and f"c_{ds['date']})" not in after
    insert_rows(db, ds["id"], [{ds["date"]: D(2026, 1, 1), other: D(2025, 7, 1)}])
    assert column_values(db, ds["id"], column) == [Decimal("1")]  # 새 기준 열의 연도(2025)


def test_other_definition_changes_keep_ref_working(ctx: Ctx, db: Db):
    ds = make_ref_dataset(ctx)
    seed_item(ctx, "전기요금", {2026: "2"})
    column = add_formula(ctx.call, ds["id"], "요금", 'REF("전기요금")')["id"]
    insert_rows(db, ds["id"], [{ds["date"]: D(2026, 1, 1), ds["value"]: 1}])
    add_column(ctx.call, ds["id"], "추가 열")  # B5
    assert patch_dataset(ctx, ds["id"], name="새 이름").status_code == 200  # B4 이름 변경
    assert put_formula(ctx.call, ds["id"], column, 'REF("전기요금") + 1').status_code == 200  # D5
    assert column_values(db, ds["id"], column) == [Decimal("3")]
    update = ctx.call(
        "definer",
        "PATCH",
        f"/api/datasets/{ds['id']}/columns/{ds['date']}",
        json={"expected_version": version(ctx.call, ds["id"]), "display_name": "새 일자"},
    )
    assert update.status_code == 200, update.text  # 기준 날짜 열 이름 변경은 REF에 영향이 없다
    assert column_values(db, ds["id"], column) == [Decimal("3")]


# --- 컴파일 호출 지점 6곳 ----


def test_all_six_compile_call_sites_handle_ref_the_same_way(ctx: Ctx, db: Db):
    ds = make_ref_dataset(ctx)
    seed_item(ctx, "전기요금", {2026: "4"})
    insert_rows(db, ds["id"], [{ds["date"]: D(2026, 1, 1), ds["value"]: 2}])
    expression = '[사용량] * REF("전기요금")'
    path = f"/api/datasets/{ds['id']}"
    # D2 check, D3 preview
    assert ctx.call(
        "definer", "POST", f"{path}/formulas/check", json={"expression": expression}
    ).json()["ok"]
    preview = ctx.call(
        "definer", "POST", f"{path}/formulas/preview", json={"expression": expression}
    ).json()
    assert preview["rows"][0]["value"] == "8"
    # D4 save (`_compile_for_save`), D5 update
    column = add_formula(ctx.call, ds["id"], "요금", expression)["id"]
    assert put_formula(ctx.call, ds["id"], column, expression + " + 1").status_code == 200
    # D6 view_formula(C0만, build_sql=False)
    shown = ctx.call("viewer", "GET", f"{path}/formulas/{column}").json()
    assert shown["text"] == '[사용량] * REF("전기요금") + 1'
    # 훅 compile_all은 D4·D5·B4·B5에서 이미 실행됐다. 시작 대조와 직접 compile_all
    with Session(db.engine) as session:
        assert (
            view_needs_rebuild(session, ds["id"]) is False
        )  # 기준값이 있어도 정상 경로는 건너뛴다
        defn = dataset_service.read_definition(session, ds["id"])
        from app.formula import repo

        infos = build_column_infos(defn, repo.load_formulas(session, ds["id"]))
        results = compile_all(
            infos,
            source_columns(defn, source_table(defn)),
            make_probe(session),
            env=load_env(session, defn),
        )
        assert results[column].ok and len(results[column].reference_uses) == 1
        session.rollback()
    assert column_values(db, ds["id"], column) == [Decimal("9")]


def test_compile_without_an_environment_fails_loudly_on_ref(ctx: Ctx, db: Db):
    ds = make_ref_dataset(ctx)
    seed_item(ctx, "전기요금", {2026: "4"})
    add_formula(ctx.call, ds["id"], "요금", 'REF("전기요금")')
    with Session(db.engine) as session:
        defn = dataset_service.read_definition(session, ds["id"])
        from app.formula import repo

        infos = build_column_infos(defn, repo.load_formulas(session, ds["id"]))
        session.rollback()
    with pytest.raises(RuntimeError, match="ReferenceEnv"):
        compile_formula('REF("전기요금")', infos, build_sql=False)
    with pytest.raises(RuntimeError, match="ReferenceEnv"):
        from app.formula import check_formula

        check_formula('REF("전기요금")', infos)


def test_startup_reconcile_skips_ref_views_when_only_reference_values_changed(ctx: Ctx, db: Db):
    from app.core.ports import DefinitionHooks
    from app.formula.reconcile import reconcile_all
    from app.formula.status import ViewStatus

    ds = make_ref_dataset(ctx)
    item = seed_item(ctx, "전기요금", {2026: "4"})
    add_formula(ctx.call, ds["id"], "요금", 'REF("전기요금")')
    hooks = DefinitionHooks()
    status = ViewStatus()
    hooks.register(FormulaDefinitionHook(status))
    value_id = value_rows(db)[0]["id"]
    set_value(db, value_id, "5")  # 정정과 같다: 값만 바뀐다
    add_value(db, item, 2027, "6", ctx.uid("admin"))
    before = fingerprint(db, ds["id"])
    with StatementLog(db.engine) as log:
        reconcile_all(db.engine, hooks, status)
    assert status.failed_count == 0
    assert [s for s in log.statements if FORBIDDEN_STATEMENT.match(s)] == []
    assert fingerprint(db, ds["id"]) == before


def test_startup_reconcile_reports_a_stored_ref_whose_item_vanished_without_stopping(
    ctx: Ctx, db: Db
):
    """항목이 수동으로 지워져도(항목은 삭제 기능이 없다) 시작을 막지 않고 실패로 남긴다."""
    from app.core.ports import DefinitionHooks
    from app.formula.reconcile import reconcile_all
    from app.formula.status import ViewStatus

    ds = make_ref_dataset(ctx)
    seed_item(ctx, "전기요금", {})
    add_formula(ctx.call, ds["id"], "요금", 'REF("전기요금")')
    with db.writer.begin() as conn:  # 수동 정리(skills/admin-cleanup)에 해당: 감사에 남지 않는다
        conn.execute(sa.text("DELETE FROM reference_items"))
    hooks, status = DefinitionHooks(), ViewStatus()
    hooks.register(FormulaDefinitionHook(status))
    reconcile_all(db.engine, hooks, status)
    assert status.failed_count == 1
    assert "FORMULA_INVALID" in status.failures()[0].reason


# --- 동시성 ----


def test_a_read_is_not_blocked_by_an_uncommitted_correction_and_sees_it_after_commit(
    ctx: Ctx, db: Db, pg_readonly_engine: Engine
):
    ds = make_ref_dataset(ctx)
    seed_item(ctx, "전기요금", {2026: "1"})
    column = add_formula(ctx.call, ds["id"], "요금", 'REF("전기요금")')["id"]
    insert_rows(db, ds["id"], [{ds["date"]: D(2026, 1, 1)}])
    value_id = value_rows(db)[0]["id"]
    read = sa.text(f"SELECT c_{column} FROM bi_data.dv_{ds['id']}")  # noqa: S608
    with db.engine.connect() as writer:  # bi_app: 열 단위 UPDATE 권한
        writer.execute(sa.text("SET lock_timeout = '1s'"))
        writer.execute(
            sa.text("UPDATE reference_values SET number_value = 9 WHERE id = :i"), {"i": value_id}
        )
        with pg_readonly_engine.connect() as reader:  # 정정이 커밋 전이어도 읽기는 기다리지 않는다
            reader.execute(sa.text("SET statement_timeout = '2s'"))
            assert reader.execute(read).scalar_one() == Decimal("1")
        writer.commit()
    with pg_readonly_engine.connect() as reader:
        assert reader.execute(read).scalar_one() == Decimal("9")


def test_corrections_and_definition_changes_repeated_together_never_deadlock(ctx: Ctx, db: Db):
    ds = make_ref_dataset(ctx)
    item = seed_item(ctx, "전기요금", {2026: "1"})
    add_formula(ctx.call, ds["id"], "요금", 'REF("전기요금")')
    insert_rows(db, ds["id"], [{ds["date"]: D(2026, 1, 1), ds["value"]: 1}])
    value_id = value_rows(db)[0]["id"]
    admin = CurrentUser(
        id=ctx.uid("admin"), display_name="관리자", is_admin=True, is_active=True, memberships=()
    )
    errors: list[BaseException] = []
    rounds = 25

    def corrector() -> None:
        try:
            from app.reference import service as reference_service

            for n in range(rounds):
                with Session(db.engine) as session:
                    reference_service.update_value(
                        session, admin, item, value_id, value=str(100 + n)
                    )
        except BaseException as error:
            errors.append(error)

    def definer() -> None:
        try:
            for n in range(rounds):
                response = ctx.call(
                    "definer",
                    "POST",
                    f"/api/datasets/{ds['id']}/columns",
                    json={
                        "expected_version": version(ctx.call, ds["id"]),
                        "display_name": f"열{n}",
                        "type": "number",
                    },
                )
                assert response.status_code in {201, 409, 503}, response.text
        except BaseException as error:
            errors.append(error)

    threads = [threading.Thread(target=corrector), threading.Thread(target=definer)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert not any(t.is_alive() for t in threads)
    deadlocks = [e for e in errors if isinstance(e, DBAPIError) and sqlstate(e) == "40P01"]
    assert deadlocks == [] and errors == [], errors


def test_concurrent_corrections_of_the_same_item_serialize_and_record_every_transition(
    ctx: Ctx, db: Db
):
    item = add_item(db, "전기요금", ctx.uid("admin"))
    value_id = add_value(db, item, 2026, "0", ctx.uid("admin"))
    admin = CurrentUser(
        id=ctx.uid("admin"), display_name="관리자", is_admin=True, is_active=True, memberships=()
    )
    from app.reference import service as reference_service

    failures: list[BaseException] = []

    def correct(value: str) -> None:
        try:
            with Session(db.engine) as session:
                reference_service.update_value(session, admin, item, value_id, value=value)
        except BaseException as error:
            failures.append(error)

    threads = [threading.Thread(target=correct, args=(str(n + 1),)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert failures == []
    rows = [r for r in audit_rows(db) if r["action"] == "reference_value.update"]
    assert len(rows) == 8
    chain = {r["details"]["value_from"]: r["details"]["value_to"] for r in rows}
    cursor, seen = "0", []
    while cursor in chain:  # 이전 값 -> 이후 값이 끊기지 않는 한 줄로 이어진다(잠금 아래 직렬화)
        seen.append(cursor)
        cursor = chain[cursor]
    assert len(seen) == 8 and Decimal(cursor) == value_rows(db)[0]["number_value"]


def test_write_busy_when_the_item_row_lock_is_held(ctx: Ctx, db: Db):
    item = add_item(db, "전기요금", ctx.uid("admin"))
    with db.writer.begin() as holder:
        holder.execute(
            sa.text("SELECT id FROM reference_items WHERE id = :i FOR UPDATE"), {"i": item}
        )
        response = api_add_value(ctx.call, item, 2026, "1")
    assert (response.status_code, err(response)["code"]) == (503, "WRITE_BUSY")
    assert err(response)["details"]["retry_after"] > 0
    assert value_rows(db) == [] and audit_rows(db) == []


def test_static_tables_are_untouched_by_reference_writes_except_the_two_reference_tables(
    ctx: Ctx, db: Db
):
    """기준값 쓰기는 `datasets`·`dataset_columns`·`superset_*` 행을 건드리지 않는다(06 §5)."""
    make_ref_dataset(ctx)
    before = db.rows(datasets, datasets.c.id), db.rows(dataset_columns, dataset_columns.c.id)
    item = api_add_item(ctx.call, "전기요금").json()["id"]
    value_id = api_add_value(ctx.call, item, 2026, "1").json()["id"]
    api_update_value(ctx.call, item, value_id, "2")
    after = db.rows(datasets, datasets.c.id), db.rows(dataset_columns, dataset_columns.c.id)
    assert after == before
    assert len(item_rows(db)) == 1 and len(value_rows(db)) == 1
    assert len([r for r in audit_rows(db) if r["target_type"] == "reference"]) == 3
