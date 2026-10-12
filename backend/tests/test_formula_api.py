"""수식 API 시험(05 §2-4 D1~D6, 실제 PostgreSQL 필요: 뷰·읽기 전용 트랜잭션·상수 SELECT를 쓴다).

`REQUIRE_PG=1`이면 환경이 없을 때 실패한다(건너뛰지 않는다, `skills/permission-management` 8절).
이 파일의 시험은 모두 API로 데이터셋·열·계산 열을 만들고 실제 뷰를 읽어 확인한다.
"""

from __future__ import annotations

import logging
import time

import pytest
import sqlalchemy as sa

from app.db_metadata import dataset_columns, formula_deps, formulas
from app.formula.errors import CELL_ERROR_MESSAGES_KO
from app.formula.functions import get_default_registry
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


@pytest.fixture
def db(pg_app_engine, pg_owner_engine, clean_pg):
    """이 파일은 PostgreSQL만 쓴다(conftest의 sqlite/pg 변형 대신)."""
    yield Db("pg", pg_app_engine, pg_owner_engine)


@pytest.fixture
def ds(api, world):
    """매출·비용(숫자), 이름(글자), 일자(날짜), 사용(참거짓) 열이 있는 데이터셋."""
    dataset = make_dataset(api, world)
    cols = {
        "매출": add_column(api, dataset["id"], "매출")["id"],
        "비용": add_column(api, dataset["id"], "비용")["id"],
        "이름": add_column(api, dataset["id"], "이름", "text")["id"],
        "일자": add_column(api, dataset["id"], "일자", "date")["id"],
        "사용": add_column(api, dataset["id"], "사용", "boolean")["id"],
    }
    return {"id": dataset["id"], **cols}


def stored(db: Db, column_id: int):
    with db.writer.connect() as conn:
        formula = (
            conn.execute(sa.select(formulas).where(formulas.c.column_id == column_id))
            .mappings()
            .first()
        )
        deps = (
            conn.execute(
                sa.select(formula_deps.c.depends_on_column_id)
                .where(formula_deps.c.column_id == column_id)
                .order_by(formula_deps.c.depends_on_column_id)
            )
            .scalars()
            .all()
        )
    return formula, list(deps)


# --- D1 ----


def test_d1_catalog_comes_from_the_dictionary(api, world):
    response = api("viewer", "GET", "/api/formulas/functions")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"functions", "cell_errors"}
    described = get_default_registry().describe()
    assert body["functions"] == described
    for item in body["functions"]:
        assert set(item) == {"name", "signature", "returns", "help_ko", "excel_diff"}
        assert all(isinstance(item[k], str) and item[k] for k in item)
    assert body["cell_errors"] == CELL_ERROR_MESSAGES_KO
    assert set(body["cell_errors"]) == {"E1", "E2", "E3"}
    names = {f["name"] for f in body["functions"]}
    assert {"IF", "SUMTAG", "IFERROR", "ROUND", "DATE", "+", "/"} <= names


# --- D2 ----


def test_d2_check_ok_returns_type_and_refs(api, ds):
    response = api(
        "definer",
        "POST",
        f"/api/datasets/{ds['id']}/formulas/check",
        json={"expression": "[매출] - [비용]"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "result_type": "number",
        "refs": [
            {"column_id": ds["매출"], "display_name": "매출"},
            {"column_id": ds["비용"], "display_name": "비용"},
        ],
        "errors": [],
    }


def test_d2_check_failure_is_still_200_with_easy_messages_and_code_point_positions(api, ds):
    # 앞에 한글과 보충 평면 문자(이모지)가 있어도 위치는 코드포인트 번호(0부터, end 미포함)다.
    expression = '"가😀나" & [없는 열]'
    response = api(
        "definer",
        "POST",
        f"/api/datasets/{ds['id']}/formulas/check",
        json={"expression": expression},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False and body["result_type"] is None
    (error,) = body["errors"]
    assert error["code"] == "UNKNOWN_COLUMN"
    assert expression[error["start"] : error["end"]] == "[없는 열]"
    assert "열을 찾을 수 없습니다" in error["message"]
    for forbidden in ("SELECT", "ORA-", "psycopg", "pg8000", "traceback"):
        assert forbidden.lower() not in error["message"].lower()


def test_d2_check_runs_the_constant_probe_on_the_database(api, ds):
    """`1/0`은 상수 부분식이라 C0가 DB 상수 SELECT로 평가해 거부한다(07 §3)."""
    response = api(
        "definer", "POST", f"/api/datasets/{ds['id']}/formulas/check", json={"expression": "1/0"}
    )
    body = response.json()
    assert body["ok"] is False and body["errors"][0]["code"] == "CONSTANT_ERROR"


def test_d2_check_unknown_edit_target_is_404(api, ds):
    for column_id in (999999, ds["매출"]):  # 없는 열, 계산 열이 아닌 원본 열
        response = api(
            "definer",
            "POST",
            f"/api/datasets/{ds['id']}/formulas/check",
            json={"expression": "1", "column_id": column_id},
        )
        assert response.status_code == 404, column_id
        assert err(response)["code"] == "NOT_FOUND"


@pytest.mark.parametrize(
    "body",
    [{}, {"expression": 1}, {"expression": "1", "extra": 1}, {"expression": "x" * 10_001}],
)
def test_d2_rejects_malformed_bodies_with_422(api, ds, body):
    response = api("definer", "POST", f"/api/datasets/{ds['id']}/formulas/check", json=body)
    assert response.status_code == 422 and err(response)["code"] == "VALIDATION_ERROR"


def test_d2_long_expression_is_a_check_error_not_a_server_error(api, ds):
    response = api(
        "definer",
        "POST",
        f"/api/datasets/{ds['id']}/formulas/check",
        json={"expression": "1+" * 1500 + "1"},
    )
    assert response.status_code == 200
    assert response.json()["errors"][0]["code"] == "TOO_LONG"


# --- D3 ----


def test_d3_preview_returns_values_errors_empty_counts_and_formats(api, db, ds):
    insert_rows(
        db,
        ds["id"],
        [
            {ds["매출"]: 10, ds["비용"]: 4},
            {ds["매출"]: 5, ds["비용"]: 0},  # 0으로 나눔 -> 오류 칸 E1
            {ds["매출"]: None, ds["비용"]: 2},  # 빈 값
        ],
    )
    response = api(
        "definer",
        "POST",
        f"/api/datasets/{ds['id']}/formulas/preview",
        json={"expression": "[매출] / [비용]"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {
        "result_type",
        "rows",
        "total_rows",
        "error_count",
        "empty_count",
        "def_version",
    }
    assert body["result_type"] == "number" and body["total_rows"] == 3
    assert body["error_count"] == 1 and body["empty_count"] == 1
    assert body["def_version"] == version(api, ds["id"])
    rows = {r["row_id"]: r for r in body["rows"]}
    assert [r["row_id"] for r in body["rows"]] == sorted(rows, reverse=True)  # 최근(큰 번호) 순
    assert rows[1]["value"] == "2.5000000000000000" and rows[1]["error"] is None
    assert rows[2] == {"row_id": 2, "period": None, "value": None, "error": "E1"}
    assert rows[3]["value"] is None and rows[3]["error"] is None  # 빈 값은 오류가 아니다


def test_d3_value_formats_by_result_type(api, db, ds):
    from datetime import date

    insert_rows(db, ds["id"], [{ds["일자"]: date(2024, 2, 29), ds["사용"]: True, ds["이름"]: "가"}])

    def preview(expression):
        response = api(
            "definer",
            "POST",
            f"/api/datasets/{ds['id']}/formulas/preview",
            json={"expression": expression},
        )
        assert response.status_code == 200, response.text
        return response.json()

    assert preview("DATE(YEAR([일자]), MONTH([일자]) + 1, 1)")["rows"][0]["value"] == "2024-03-01"
    flag = preview("NOT([사용])")
    assert flag["result_type"] == "boolean" and flag["rows"][0]["value"] is False
    text = preview('[이름] & "나"')
    assert text["result_type"] == "text" and text["rows"][0]["value"] == "가나"
    number = preview("ROUND(2.5, 0)")
    assert number["rows"][0]["value"] == "3"  # 숫자는 십진 문자열(0에서 먼 쪽으로 반올림)


def test_d3_shows_only_twenty_rows_newest_first_and_counts_all_rows(api, db, world):
    dataset = make_dataset(api, world, "기간 시험", "month")
    period = add_column(api, dataset["id"], "기간", "date")["id"]
    amount = add_column(api, dataset["id"], "금액")["id"]
    response = api(
        "definer",
        "PATCH",
        f"/api/datasets/{dataset['id']}",
        json={"expected_version": version(api, dataset["id"]), "base_date_column_id": period},
    )
    assert response.status_code == 200
    from datetime import date

    insert_rows(
        db,
        dataset["id"],
        [{period: date(2020 + i // 12, i % 12 + 1, 1), amount: i} for i in range(30)],
    )
    # 계산 결과가 기간에 따라 오류가 나게: 금액이 0이면 0으로 나눔
    body = api(
        "definer",
        "POST",
        f"/api/datasets/{dataset['id']}/formulas/preview",
        json={"expression": "1 / [금액]"},
    ).json()
    assert len(body["rows"]) == 20 and body["total_rows"] == 30
    periods = [r["period"] for r in body["rows"]]
    assert periods == sorted(periods, reverse=True) and periods[0] == "2022-06-01"
    assert body["error_count"] == 1  # 전체 행 대상 집계(보이는 20행 밖의 오류도 센다)
    assert any(r["error"] == "E1" for r in body["rows"]) is False  # 오류 행(첫 달)은 20행 밖


def test_d3_invalid_expression_is_422_formula_invalid_with_d2_shaped_errors(api, ds):
    response = api(
        "definer",
        "POST",
        f"/api/datasets/{ds['id']}/formulas/preview",
        json={"expression": "[매출] + "},
    )
    assert response.status_code == 422
    error = err(response)
    assert error["code"] == "FORMULA_INVALID"
    first = error["details"]["errors"][0]
    assert set(first) == {"code", "message", "start", "end"}


def test_d3_database_failures_are_normalized_without_leaking_details(
    api, db, ds, monkeypatch, caplog
):
    """시간 초과 같은 DB 예외는 `FORMULA_RUNTIME_ERROR`로만 나가고 SQL·상수는 로그에도 없다."""
    from app.formula import service

    insert_rows(db, ds["id"], [{ds["매출"]: 1}])
    real = service.compile_formula

    def slow(*args, **kwargs):
        import dataclasses

        result = real(*args, **kwargs)
        sleepy = sa.case(
            (sa.func.pg_sleep(2).cast(sa.Text) == "", result.value), else_=result.value
        )
        return dataclasses.replace(result, value=sleepy)

    monkeypatch.setattr(service, "compile_formula", slow)
    monkeypatch.setattr(service, "READ_STATEMENT_TIMEOUT", "100ms")
    with caplog.at_level(logging.DEBUG):
        response = api(
            "definer",
            "POST",
            f"/api/datasets/{ds['id']}/formulas/preview",
            json={"expression": "[매출] + 12345.678"},
        )
    assert response.status_code == 422
    assert err(response)["code"] == "FORMULA_RUNTIME_ERROR"
    text = response.text + caplog.text
    for secret in ("12345.678", "pg_sleep", "SELECT", "statement timeout", "bi_data"):
        assert secret not in text, secret


def test_d3_is_read_only_and_does_not_change_the_dataset(api, db, ds):
    insert_rows(db, ds["id"], [{ds["매출"]: 1}])
    before = (version(api, ds["id"]), dataset_hash(db, ds["id"]))
    api(
        "definer",
        "POST",
        f"/api/datasets/{ds['id']}/formulas/preview",
        json={"expression": "[매출] + 1"},
    )
    assert (version(api, ds["id"]), dataset_hash(db, ds["id"])) == before
    with db.writer.connect() as conn:
        assert conn.execute(sa.select(sa.func.count()).select_from(formulas)).scalar_one() == 0


def test_d3_per_user_and_global_concurrency_limits_return_429_with_retry_after(api, ds):
    from app.core.errors import ErrorCode
    from app.core.limits import HeavyReadLimiter
    from app.main import create_app  # noqa: F401 - 앱이 limiter를 쓰는지 아래에서 직접 확인한다

    limiter = HeavyReadLimiter(global_limit=2)
    with limiter.slot(user_id=1):
        with pytest.raises(Exception) as busy:  # 같은 사용자의 두 번째 동시 요청
            with limiter.slot(user_id=1):
                pass
        assert busy.value.code == ErrorCode.PREVIEW_BUSY and busy.value.status_code == 429
        assert busy.value.details == {"retry_after": 2}
        assert busy.value.headers == {"Retry-After": "2"}
        with limiter.slot(user_id=2):  # 다른 사용자는 된다(전역 2건까지)
            with pytest.raises(Exception) as full:
                with limiter.slot():
                    pass
            assert full.value.code == ErrorCode.PREVIEW_BUSY
    assert limiter.active == 0  # 자리는 반드시 반납된다


def test_d3_http_429_when_the_global_slots_are_taken(api, ds, stub_settings, db):
    """실제 앱의 전역 상한을 모두 점유하면 미리보기·오류 칸 조회·계산 열 행 조회가 429다."""
    from fastapi.testclient import TestClient

    from app.main import create_app
    from tests.api_helpers import make_caller

    add_formula(api, ds["id"], "계산", "[매출] + 1")
    app = create_app(stub_settings, engine=db.engine)
    with TestClient(app) as client:
        call = make_caller(client)
        with app.state.heavy_reads.slot(), app.state.heavy_reads.slot():
            preview = call(
                "definer",
                "POST",
                f"/api/datasets/{ds['id']}/formulas/preview",
                json={"expression": "1"},
            )
            assert preview.status_code == 429 and preview.headers["Retry-After"] == "2"
            assert err(preview)["code"] == "PREVIEW_BUSY"
            assert err(preview)["details"] == {"retry_after": 2}
            for path in (
                "/api/checks/formula-errors",
                f"/api/datasets/{ds['id']}/formula-errors",
                f"/api/datasets/{ds['id']}/rows",  # 계산 열이 있는 C1
            ):
                assert call("viewer", "GET", path).status_code == 429, path
            # 계산 열이 없는 데이터셋의 C1과 D2 검사는 상한과 무관하다.
            assert call("viewer", "GET", "/api/datasets").status_code == 200
            assert (
                call(
                    "definer",
                    "POST",
                    f"/api/datasets/{ds['id']}/formulas/check",
                    json={"expression": "1"},
                ).status_code
                == 200
            )
        assert (
            call("definer", "GET", f"/api/datasets/{ds['id']}/rows").status_code == 200
        )  # 자리가 풀리면 된다


# --- D4 ----


def test_d4_creates_a_calculated_column_in_one_transaction(api, db, ds):
    before_version = version(api, ds["id"])
    response = post_formula(api, ds["id"], "이익", "[매출] - [비용]", tag="합계")
    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == {"column", "def_version"}
    column = body["column"]
    assert column["kind"] == "formula" and column["type"] == "number"
    assert column["display_name"] == "이익" and column["tag"] == "합계"
    assert column["required"] is False and column["rules"] is None
    assert body["def_version"] == before_version + 1 == version(api, ds["id"])
    formula, deps = stored(db, column["id"])
    assert formula["expression"] == "[매출] - [비용]"
    assert formula["ast"] == {
        "t": "call",
        "n": "-",
        "a": [{"t": "col", "id": ds["매출"]}, {"t": "col", "id": ds["비용"]}],
    }
    assert len(formula["ast_hash"]) == 64
    assert deps == sorted([ds["매출"], ds["비용"]])
    # 계산 열은 원본 표에 저장되지 않는다(뷰가 계산한다).
    with db.writer.connect() as conn:
        names = {
            c["name"] for c in sa.inspect(conn).get_columns(f"ds_{ds['id']}", schema="bi_data")
        }
    assert f"c_{column['id']}" not in names
    dv = sa.inspect(db.engine).get_columns(f"dv_{ds['id']}", schema="bi_data")
    assert [c["name"] for c in dv][-1] == f"c_{column['id']}"
    assert [
        c["name"] for c in sa.inspect(db.engine).get_columns(f"de_{ds['id']}", schema="bi_data")
    ] == [
        "row_id",
        f"e_{column['id']}",
    ]


def test_d4_default_position_follows_existing_columns_and_explicit_position_is_kept(api, ds):
    a = add_formula(api, ds["id"], "계산1", "1")
    b = add_formula(api, ds["id"], "계산2", "2", position=99)
    assert a["position"] == 5 and b["position"] == 99


def test_d4_version_mismatch_and_duplicate_name(api, ds):
    stale = version(api, ds["id"])
    add_formula(api, ds["id"], "계산", "1")
    response = api(
        "definer",
        "POST",
        f"/api/datasets/{ds['id']}/formulas",
        json={"expected_version": stale, "display_name": "다른 계산", "expression": "1"},
    )
    assert response.status_code == 409
    assert err(response)["code"] == "DEFINITION_VERSION_MISMATCH"
    assert err(response)["details"] == {"current_version": version(api, ds["id"])}
    duplicate = post_formula(api, ds["id"], "계산", "2")
    assert duplicate.status_code == 409
    assert err(duplicate)["code"] == "ALREADY_EXISTS"
    assert err(duplicate)["details"] == {"field": "display_name"}
    clash = post_formula(api, ds["id"], "매출", "2")  # 원본 열과 같은 이름
    assert clash.status_code == 409


def test_d4_invalid_formula_is_422_and_changes_nothing(api, db, ds):
    before = (version(api, ds["id"]), dataset_hash(db, ds["id"]))
    response = post_formula(api, ds["id"], "나쁜 수식", "[매출] + ")
    assert response.status_code == 422
    assert err(response)["code"] == "FORMULA_INVALID"
    assert err(response)["details"]["errors"]
    again = post_formula(api, ds["id"], "나쁜 수식", "[없음] * 2")
    assert err(again)["code"] == "FORMULA_INVALID"
    assert (version(api, ds["id"]), dataset_hash(db, ds["id"])) == before
    with db.writer.connect() as conn:
        count = conn.execute(
            sa.select(sa.func.count())
            .select_from(dataset_columns)
            .where(dataset_columns.c.dataset_id == ds["id"], dataset_columns.c.kind == "formula")
        ).scalar_one()
    assert count == 0


def test_d4_validation_errors_for_name_tag_and_extra_fields(api, ds):
    cases = [
        ({"display_name": "team"}, "RESERVED"),
        ({"display_name": "열[1]"}, "BAD_FORMAT"),
        ({"display_name": "가" * 101}, "TOO_LONG"),
    ]
    for extra, code in cases:
        response = post_formula(api, ds["id"], extra.pop("display_name"), "1", **extra)
        assert response.status_code == 422, code
        assert err(response)["details"]["fields"][0]["code"] == code
    # 태그는 숫자 결과에만
    response = post_formula(api, ds["id"], "글자 계산", '"가"', tag="합계")
    assert response.status_code == 422
    assert err(response)["details"]["fields"][0] == {
        "field": "tag",
        "code": "BAD_FORMAT",
        "message": "형식이 올바르지 않습니다.",
    }
    response = api(
        "definer",
        "POST",
        f"/api/datasets/{ds['id']}/formulas",
        json={"expected_version": 1, "display_name": "x", "expression": "1", "rls": []},
    )
    assert response.status_code == 422


def test_d4_self_tag_sum_is_a_circular_reference_with_a_name_path(api, db, ds):
    """새 열에 붙일 태그를 자기 `SUMTAG`가 합산하면 순환이다: `FORMULA_CIRCULAR`, 경로는 열 이름."""
    api(
        "definer",
        "PATCH",
        f"/api/datasets/{ds['id']}/columns/{ds['매출']}",
        json={"expected_version": version(api, ds["id"]), "tag": "수입"},
    )
    before = (version(api, ds["id"]), dataset_hash(db, ds["id"]))
    response = post_formula(api, ds["id"], "합계열", 'SUMTAG("수입")', tag="수입")
    assert response.status_code == 422
    assert err(response)["code"] == "FORMULA_CIRCULAR"
    assert err(response)["details"]["path"] == ["합계열", "합계열"]
    assert (version(api, ds["id"]), dataset_hash(db, ds["id"])) == before


def test_d4_circular_through_the_new_column_name_is_reported_as_path(api, ds):
    """새 열이 자기 자신을 참조하면(자기 이름) 아직 없는 열이라 이름을 찾을 수 없다."""
    response = post_formula(api, ds["id"], "자기", "[자기] + 1")
    assert response.status_code == 422 and err(response)["code"] == "FORMULA_INVALID"


def test_d4_is_serialized_and_busy_when_the_dataset_row_is_locked(api, db, ds):
    holder = db.writer.connect()
    try:
        holder.execute(sa.text("BEGIN"))
        holder.execute(
            sa.text("SELECT id FROM datasets WHERE id = :id FOR UPDATE"), {"id": ds["id"]}
        )
        response = post_formula(api, ds["id"], "바쁨", "1")
    finally:
        holder.rollback()
        holder.close()
    assert response.status_code == 503
    assert err(response)["code"] == "DEFINITION_BUSY"
    assert err(response)["details"] == {"retry_after": 2}
    assert post_formula(api, ds["id"], "바쁨", "1").status_code == 201  # 풀리면 된다


# --- D5 ----


def test_d5_updates_the_formula_and_bumps_the_version_once(api, db, ds):
    column = add_formula(api, ds["id"], "이익", "[매출] - [비용]")
    insert_rows(db, ds["id"], [{ds["매출"]: 10, ds["비용"]: 4}])
    old = version(api, ds["id"])
    response = put_formula(api, ds["id"], column["id"], "[매출] * [비용]")
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"column", "def_version", "result_type_changed"}
    assert body["def_version"] == old + 1 and body["result_type_changed"] is False
    assert view_rows(db, ds["id"])[0][f"c_{column['id']}"] == 40
    formula, deps = stored(db, column["id"])
    assert formula["expression"] == "[매출] * [비용]" and deps == sorted([ds["매출"], ds["비용"]])


def test_d5_same_formula_is_a_no_op_without_a_version_bump(api, db, ds):
    column = add_formula(api, ds["id"], "이익", "[매출] - [비용]")
    old, old_hash = version(api, ds["id"]), dataset_hash(db, ds["id"])
    # 공백만 다른 같은 수식은 같은 AST라 아무것도 바꾸지 않는다.
    response = put_formula(api, ds["id"], column["id"], "[매출]  -  [비용]")
    assert response.status_code == 200
    assert response.json()["def_version"] == old and response.json()["result_type_changed"] is False
    assert (version(api, ds["id"]), dataset_hash(db, ds["id"])) == (old, old_hash)


def test_d5_result_type_change_updates_column_type_and_the_view_column_type(api, db, ds):
    column = add_formula(api, ds["id"], "결과", "[매출] + 1")
    insert_rows(db, ds["id"], [{ds["매출"]: 1, ds["이름"]: "가"}])
    response = put_formula(api, ds["id"], column["id"], '[이름] & "나"')
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["result_type_changed"] is True and body["column"]["type"] == "text"
    detail = api("viewer", "GET", f"/api/datasets/{ds['id']}").json()
    assert {c["id"]: c["type"] for c in detail["columns"]}[column["id"]] == "text"
    assert view_rows(db, ds["id"])[0][f"c_{column['id']}"] == "가나"
    types = {
        c["name"]: str(c["type"])
        for c in sa.inspect(db.engine).get_columns(f"dv_{ds['id']}", schema="bi_data")
    }
    assert types[f"c_{column['id']}"] == "TEXT"


def test_d5_circular_path_uses_column_names(api, ds):
    a = add_formula(api, ds["id"], "가", "[매출]")
    b = add_formula(api, ds["id"], "나", "[가] + 1")
    c = add_formula(api, ds["id"], "다", "[나] + 1")
    before = version(api, ds["id"])
    response = put_formula(api, ds["id"], a["id"], "[다] + 1")
    assert response.status_code == 422
    error = err(response)
    assert error["code"] == "FORMULA_CIRCULAR"
    path = error["details"]["path"]
    assert path[0] == path[-1] and set(path) == {"가", "나", "다"}
    assert all(isinstance(name, str) for name in path)
    assert version(api, ds["id"]) == before
    direct = put_formula(api, ds["id"], b["id"], "[나]")  # 자기 참조
    assert err(direct)["code"] == "FORMULA_CIRCULAR" and err(direct)["details"]["path"] == [
        "나",
        "나",
    ]
    assert c["id"]  # 사용


def test_d5_unknown_or_raw_column_is_404_and_version_mismatch_is_409(api, ds):
    column = add_formula(api, ds["id"], "계산", "1")
    assert put_formula(api, ds["id"], 999999, "1").status_code == 404
    assert put_formula(api, ds["id"], ds["매출"], "1").status_code == 404  # 원본 열
    stale = put_formula(api, ds["id"], column["id"], "2", expected_version=1)
    assert stale.status_code == 409
    assert err(stale)["code"] == "DEFINITION_VERSION_MISMATCH"


def test_d5_breaking_a_dependent_formula_is_rejected_and_rolled_back(api, db, ds):
    base = add_formula(api, ds["id"], "기준", "[매출] + 1")
    dependent = add_formula(api, ds["id"], "파생", "[기준] * 2")
    old = version(api, ds["id"])
    response = put_formula(api, ds["id"], base["id"], '[이름] & "가"')  # 숫자 -> 글자
    assert response.status_code == 422
    error = err(response)
    assert error["code"] == "FORMULA_INVALID"
    assert any("'파생'" in item["message"] for item in error["details"]["errors"])
    assert version(api, ds["id"]) == old
    formula, _deps = stored(db, base["id"])
    assert formula["expression"] == "[매출] + 1"
    assert dependent["id"]


def test_changing_a_referenced_formula_updates_dependent_types_in_one_step(api, db, ds):
    base = add_formula(api, ds["id"], "기준", "[매출] > 1")  # 참거짓
    dependent = add_formula(api, ds["id"], "파생", "IF([기준], 1, 0)")
    response = put_formula(api, ds["id"], base["id"], "[비용] > 5")  # 같은 형
    assert response.status_code == 200 and response.json()["result_type_changed"] is False
    assert dependent["type"] == "number"


# --- D6 ----


def test_d6_text_uses_current_names_and_original_expression_is_not_exposed(api, db, ds):
    column = add_formula(api, ds["id"], "이익", "  [매출]   -[비용]  ")
    response = api("viewer", "GET", f"/api/datasets/{ds['id']}/formulas/{column['id']}")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"column_id", "text", "refs", "tag_columns", "error_count"}
    assert body["text"] == "[매출] - [비용]"
    assert "expression" not in body and "  " not in body["text"]
    assert body["refs"] == [
        {"column_id": ds["매출"], "display_name": "매출", "kind": "raw"},
        {"column_id": ds["비용"], "display_name": "비용", "kind": "raw"},
    ]
    assert body["tag_columns"] == [] and body["error_count"] == 0
    # 열 이름을 바꾸면 수식 보기가 새 이름으로 나오고 저장된 AST는 그대로다.
    formula_before, _ = stored(db, column["id"])
    renamed = api(
        "definer",
        "PATCH",
        f"/api/datasets/{ds['id']}/columns/{ds['매출']}",
        json={"expected_version": version(api, ds["id"]), "display_name": "총매출"},
    )
    assert renamed.status_code == 200
    after = api("viewer", "GET", f"/api/datasets/{ds['id']}/formulas/{column['id']}").json()
    assert after["text"] == "[총매출] - [비용]"
    assert after["refs"][0]["display_name"] == "총매출"
    formula_after, _ = stored(db, column["id"])
    assert formula_after["ast"] == formula_before["ast"]
    assert formula_after["ast_hash"] == formula_before["ast_hash"]


def test_d6_text_can_be_saved_again_as_the_formula(api, ds):
    column = add_formula(
        api, ds["id"], "복잡", "IF(AND([매출] > 0, NOT([사용])), ROUND([매출] / 3, 2), -[비용])"
    )
    text = api("viewer", "GET", f"/api/datasets/{ds['id']}/formulas/{column['id']}").json()["text"]
    old = version(api, ds["id"])
    response = put_formula(api, ds["id"], column["id"], text)
    assert response.status_code == 200
    assert response.json()["def_version"] == old  # 같은 AST: 바뀐 것이 없다
    check = api(
        "definer", "POST", f"/api/datasets/{ds['id']}/formulas/check", json={"expression": text}
    )
    assert check.json()["ok"] is True


def test_d6_lists_sumtag_columns_error_count_and_404(api, db, ds):
    api(
        "definer",
        "PATCH",
        f"/api/datasets/{ds['id']}/columns/{ds['매출']}",
        json={"expected_version": version(api, ds["id"]), "tag": "수입"},
    )
    other = add_column(api, ds["id"], "기타수입", tag="수입")
    column = add_formula(api, ds["id"], "수입합", 'SUMTAG("수입")')
    body = api("viewer", "GET", f"/api/datasets/{ds['id']}/formulas/{column['id']}").json()
    assert body["text"] == 'SUMTAG("수입")'
    assert body["tag_columns"] == ["매출", "기타수입"]
    assert other["id"]
    divide = add_formula(api, ds["id"], "나눔", "[매출] / [비용]")
    insert_rows(db, ds["id"], [{ds["매출"]: 1, ds["비용"]: 0}, {ds["매출"]: 1, ds["비용"]: 1}])
    assert (
        api("viewer", "GET", f"/api/datasets/{ds['id']}/formulas/{divide['id']}").json()[
            "error_count"
        ]
        == 1
    )
    assert (
        api("viewer", "GET", f"/api/datasets/{ds['id']}/formulas/{ds['매출']}").status_code == 404
    )
    assert api("viewer", "GET", f"/api/datasets/{ds['id']}/formulas/999999").status_code == 404
    assert api("viewer", "GET", "/api/datasets/999999/formulas/1").status_code == 404


# --- 열 태그(B6)와 순환·TAG_EMPTY (07 §7) ----


def test_tag_change_that_creates_a_cycle_is_rejected_and_rolled_back(api, db, ds):
    api(
        "definer",
        "PATCH",
        f"/api/datasets/{ds['id']}/columns/{ds['매출']}",
        json={"expected_version": version(api, ds["id"]), "tag": "수입"},
    )
    sum_column = add_formula(api, ds["id"], "합계열", 'SUMTAG("수입")')
    # 합계 열 자신에게 같은 태그를 붙이면 자기 태그를 합산하는 순환이다(숫자 계산 열은 태그 가능).
    old = version(api, ds["id"])
    response = api(
        "definer",
        "PATCH",
        f"/api/datasets/{ds['id']}/columns/{sum_column['id']}",
        json={"expected_version": old, "tag": "수입"},
    )
    assert response.status_code == 422
    assert err(response)["code"] == "FORMULA_CIRCULAR"
    path = err(response)["details"]["path"]
    assert path[0] == path[-1] == "합계열"
    assert version(api, ds["id"]) == old
    column = next(
        c
        for c in api("viewer", "GET", f"/api/datasets/{ds['id']}").json()["columns"]
        if c["id"] == sum_column["id"]
    )
    assert column["tag"] is None  # 롤백됨


def test_removing_the_last_tagged_column_while_sumtag_is_used_is_rejected(api, ds):
    api(
        "definer",
        "PATCH",
        f"/api/datasets/{ds['id']}/columns/{ds['매출']}",
        json={"expected_version": version(api, ds["id"]), "tag": "수입"},
    )
    add_formula(api, ds["id"], "수입합", 'SUMTAG("수입")')
    old = version(api, ds["id"])
    response = api(
        "definer",
        "PATCH",
        f"/api/datasets/{ds['id']}/columns/{ds['매출']}",
        json={"expected_version": old, "tag": None},
    )
    assert response.status_code == 422
    assert err(response)["code"] == "FORMULA_INVALID"
    assert any(e["code"] == "TAG_EMPTY" for e in err(response)["details"]["errors"])
    assert version(api, ds["id"]) == old


def test_adding_a_tagged_column_changes_deps_values_and_the_view_hash(api, db, ds):
    api(
        "definer",
        "PATCH",
        f"/api/datasets/{ds['id']}/columns/{ds['매출']}",
        json={"expected_version": version(api, ds["id"]), "tag": "수입"},
    )
    column = add_formula(api, ds["id"], "수입합", 'SUMTAG("수입")')
    assert stored(db, column["id"])[1] == [ds["매출"]]
    hash_before = dataset_hash(db, ds["id"])
    extra = add_column(api, ds["id"], "추가수입", tag="수입")
    insert_rows(db, ds["id"], [{ds["매출"]: 1, extra["id"]: 2}])
    assert stored(db, column["id"])[1] == sorted([ds["매출"], extra["id"]])
    assert dataset_hash(db, ds["id"]) != hash_before
    assert view_rows(db, ds["id"])[0][f"c_{column['id']}"] == 3  # 새 열이 자동 포함


# --- 비밀·로그 노출 없음 ----


def test_errors_and_logs_do_not_expose_sql_constants_or_login_ids(api, db, ds, caplog):
    secret = "비밀상수값123"
    with caplog.at_level(logging.DEBUG):
        responses = [
            post_formula(api, ds["id"], "나쁨", f'"{secret}" + 1'),
            post_formula(api, ds["id"], "나쁨", f'[없는열] & "{secret}"'),
            put_formula(api, ds["id"], 999999, f'"{secret}"'),
            api(
                "definer",
                "POST",
                f"/api/datasets/{ds['id']}/formulas/preview",
                json={"expression": f'"{secret}" + 1'},
            ),
            api(
                "definer",
                "POST",
                f"/api/datasets/{ds['id']}/formulas/check",
                json={"expression": f'"{secret}" + 1'},
            ),
        ]
    for response in responses:
        for token in ("SELECT", "bi_data", "dv_", "de_", "pg8000", "definer"):
            assert token not in response.text, (token, response.text)
    # 상수 값이 오류 응답에 되돌아오는 곳은 C0 오류의 위치 정보뿐이다(사용자가 쓴 글자의 위치).
    logs = caplog.text
    assert secret not in logs
    assert "definer" not in logs.replace("definer ", "")  # login_id 0건


# --- 추가 경계 ----


def test_d3_on_an_empty_dataset_returns_no_rows_and_zero_counts(api, ds):
    body = api(
        "definer",
        "POST",
        f"/api/datasets/{ds['id']}/formulas/preview",
        json={"expression": "[매출] + 1"},
    ).json()
    assert body["rows"] == [] and body["total_rows"] == 0
    assert body["error_count"] == 0 and body["empty_count"] == 0


def test_choice_and_boolean_columns_are_usable_and_match_between_preview_and_view(api, db, world):
    dataset = make_dataset(api, world, "선택 목록")
    region = add_column(api, dataset["id"], "지역", "choice", rules={"options": ["서울", "부산"]})[
        "id"
    ]
    done = add_column(api, dataset["id"], "완료", "boolean")["id"]
    column = add_formula(
        api, dataset["id"], "표시", 'IF([완료], [지역] & "(완료)", LEFT([지역], 1))'
    )
    insert_rows(db, dataset["id"], [{region: "서울", done: True}, {region: "부산", done: False}])
    preview = api(
        "definer",
        "POST",
        f"/api/datasets/{dataset['id']}/formulas/preview",
        json={"expression": 'IF([완료], [지역] & "(완료)", LEFT([지역], 1))'},
    ).json()
    values = {r["row_id"]: r["value"] for r in preview["rows"]}
    assert values == {1: "서울(완료)", 2: "부"}
    assert [r[f"c_{column['id']}"] for r in view_rows(db, dataset["id"])] == ["서울(완료)", "부"]


ODD_NAMES = [
    "총 매출 (원)",
    "a,b",
    "1+1",
    "IF",
    "SUM",
    "TRUE",
    "x(y)",
    "\uff3b전각\uff3d",
    "가-나_다.라",
    "%율",
    "O'Brien",
    "a'b",
    "한 글  이름",
    "숫자 1.5",
    "= 같다",
    "é́é",
]


def test_odd_column_names_survive_the_text_round_trip_that_every_recompile_uses(api, db, world):
    """훅은 저장된 AST를 현재 열 이름으로 풀어 쓴 글자에서 다시 컴파일한다.

    이름이 무엇이어도 왕복이 깨지면 안 된다(깨지면 그 데이터셋의 모든 정의 변경이 막힌다).
    """
    dataset = make_dataset(api, world, "이름 왕복")
    ids = {}
    stored_names = []
    for name in ODD_NAMES:
        response = api(
            "definer",
            "POST",
            f"/api/datasets/{dataset['id']}/columns",
            json={
                "expected_version": version(api, dataset["id"]),
                "display_name": name,
                "type": "number",
            },
        )
        assert response.status_code == 201, (name, response.text)
        ids[name] = response.json()["column"]["id"]
        stored_names.append(response.json()["column"]["display_name"])  # NFC로 정리된 이름
    arguments = ", ".join(f"[{name}]" for name in stored_names)
    calc = add_formula(api, dataset["id"], "모두 더하기", f"SUM({arguments})")
    insert_rows(db, dataset["id"], [dict.fromkeys(ids.values(), 1)])
    assert view_rows(db, dataset["id"])[0][f"c_{calc['id']}"] == len(ODD_NAMES)
    # 이름을 바꿔도 뷰·수식이 깨지지 않고 수식 보기가 새 이름을 쓴다.
    first = ODD_NAMES[0]
    renamed = api(
        "definer",
        "PATCH",
        f"/api/datasets/{dataset['id']}/columns/{ids[first]}",
        json={"expected_version": version(api, dataset["id"]), "display_name": "총매출"},
    )
    assert renamed.status_code == 200
    text = api("viewer", "GET", f"/api/datasets/{dataset['id']}/formulas/{calc['id']}").json()[
        "text"
    ]
    assert "[총매출]" in text and "[총 매출 (원)]" not in text
    check = api(
        "definer",
        "POST",
        f"/api/datasets/{dataset['id']}/formulas/check",
        json={"expression": text},
    )
    assert check.json()["ok"] is True


def test_a_long_running_reader_of_the_view_makes_a_definition_change_busy_not_stuck(api, db, ds):
    add_formula(api, ds["id"], "계산", "[매출] + 1")
    reader = db.engine.connect()
    try:
        reader.execute(sa.text(f"SELECT * FROM bi_data.dv_{ds['id']}")).all()  # noqa: S608 - 열린 읽기
        started = time.monotonic()
        response = post_formula(api, ds["id"], "다른 계산", "[매출] + 2")
        elapsed = time.monotonic() - started
    finally:
        reader.rollback()
        reader.close()
    assert response.status_code == 503 and err(response)["code"] == "DEFINITION_BUSY"
    assert elapsed < 5  # lock_timeout(1초) 안에 포기한다
    columns = api("viewer", "GET", f"/api/datasets/{ds['id']}").json()["columns"]
    assert [c["display_name"] for c in columns if c["kind"] == "formula"] == ["계산"]  # 롤백됨
    assert post_formula(api, ds["id"], "다른 계산", "[매출] + 2").status_code == 201
