"""입력 그리드 API 시험(05 §2-3 C1~C4, 06 §3·§5). SQLite와 실제 PostgreSQL(`pg`) 두 변형으로 돈다.

SQLite 변형과 `pg` 변형의 차이(DB 없이 도는 쪽의 한계):
- SQLite는 `numeric`을 실수로 저장해 숫자 칸의 소수 자릿수(`"1234.50"`)를 보존하지 못한다. 그
  단정은 `pg` 변형에서만 한다(`on_pg`).
- 기준 날짜 열의 NOT NULL·기간 첫날 CHECK는 SQLite가 지원하지 않는다(앱 검증이 같은 규칙을 먼저
  막는다). 기간 **유일 인덱스**는 SQLite 변형에서도 실제로 만들어 기간 충돌 경로를 시험한다.
- 락(`FOR SHARE`)·`lock_timeout`·교착은 SQLite에 없다. 동시성 시험은
  `test_entry_concurrency.py`(pg)다.
"""

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pytest
import sqlalchemy as sa

from app.core.errors import ErrorCode
from app.core.ports import ComputedRow, PlainRowView
from app.db_metadata import DYNAMIC_SCHEMA, dataset_columns
from app.entry import service as entry_service
from tests.api_helpers import World
from tests.conftest import Db
from tests.test_dataset_api import custom_client, err, make_column, make_dataset


@dataclass
class Ds:
    id: int
    base: int | None
    period: int  # 기간(기준 날짜) 열 번호 (기준 날짜 열이 없어도 날짜 열은 있다)
    sales: int  # 숫자, 0~1,000,000, 소수 2자리
    region: int  # 선택 목록 서울/부산, 필수
    note: int  # 글자, 최대 10자
    done: int  # 예/아니오


def build(api, world: World, *, unit: str = "month", with_base: bool = True) -> Ds:
    dataset = make_dataset(api, world, name=f"입력 시험 {unit} {with_base}", unit=unit)
    period = make_column(api, dataset, "기간", "date")["id"]
    sales = make_column(
        api, dataset, "매출", "number", rules={"min": 0, "max": 1000000, "decimals": 2}
    )["id"]
    region = make_column(
        api, dataset, "지역", "choice", required=True, rules={"options": ["서울", "부산"]}
    )["id"]
    note = make_column(api, dataset, "비고", "text", rules={"max_length": 10})["id"]
    done = make_column(api, dataset, "확인", "boolean")["id"]
    if with_base:
        response = api(
            "definer",
            "PATCH",
            f"/api/datasets/{dataset['id']}",
            json={"expected_version": dataset["def_version"], "base_date_column_id": period},
        )
        assert response.status_code == 200, response.text
    return Ds(dataset["id"], period if with_base else None, period, sales, region, note, done)


def version(api, ds: Ds) -> int:
    return api("viewer", "GET", f"/api/datasets/{ds.id}").json()["def_version"]


def rows_url(ds: Ds, suffix: str = "") -> str:
    return f"/api/datasets/{ds.id}/rows{suffix}"


def post_row(api, ds: Ds, cells: dict[int, Any], who: str = "entry", **extra):
    body = {
        "expected_version": version(api, ds),
        "cells": {str(k): v for k, v in cells.items()},
    }
    return api(who, "POST", rows_url(ds), json={**body, **extra})


def good(ds: Ds, period: str = "2026-01-01", **over: Any) -> dict[int, Any]:
    cells: dict[int, Any] = {ds.period: period, ds.sales: "100", ds.region: "서울"}
    cells.update({ds.__dict__[k]: v for k, v in over.items()})
    return cells


def patch_row(api, ds: Ds, row_id: int, changes: list[dict], who: str = "entry", **extra):
    body = {"expected_version": version(api, ds), "changes": changes}
    return api(who, "PATCH", rows_url(ds, f"/{row_id}"), json={**body, **extra})


def change(column_id: int, expected: Any, value: Any) -> dict:
    return {"column_id": column_id, "expected": expected, "value": value}


def paste(api, ds: Ds, column_ids: list[int], rows: list[dict], who: str = "entry", **extra):
    body = {"expected_version": version(api, ds), "column_ids": column_ids, "rows": rows}
    return api(who, "POST", rows_url(ds, "/paste"), json={**body, **extra})


def new_row(*values: Any) -> dict:
    return {"row_id": None, "values": list(values)}


def old_row(row_id: int, expected: list, values: list) -> dict:
    return {"row_id": row_id, "expected": expected, "values": values}


def stored(db: Db, ds: Ds) -> list[dict[str, Any]]:
    """원본 표의 행을 `row_id` 순으로(DB에 실제로 들어간 값)."""
    tbl = sa.Table(f"ds_{ds.id}", sa.MetaData(), autoload_with=db.engine, schema=DYNAMIC_SCHEMA)
    with db.engine.connect() as conn:
        return [dict(r) for r in conn.execute(sa.select(tbl).order_by(tbl.c.row_id)).mappings()]


def cell(row: dict, column_id: int) -> Any:
    return row["cells"][str(column_id)]


def num(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


def field_map(response) -> dict[str, str]:
    return {f["field"]: f["code"] for f in err(response)["details"]["fields"]}


def cell_codes(response) -> set[tuple[int, int, str]]:
    return {
        (f["row_index"], f["column_id"], f["code"])
        for f in err(response)["details"]["fields"]
        if "row_index" in f
    }


@pytest.fixture
def ds(api, world: World) -> Ds:
    return build(api, world)


# --- C1 행 조회 ----


def test_c1_empty_dataset(api, world, ds):
    response = api("viewer", "GET", rows_url(ds))
    assert response.status_code == 200
    assert response.json() == {
        "def_version": version(api, ds),
        "items": [],
        "total": 0,
        "limit": 50,
        "offset": 0,
    }


def test_c1_row_shape_and_value_representation(api, db: Db, world, ds):
    created = post_row(
        api,
        ds,
        {
            ds.period: "2026-03-01",
            ds.sales: "1234.50",
            ds.region: "서울",
            ds.note: "안녕",
            ds.done: True,
        },
    )
    assert created.status_code == 201, created.text
    row = api("viewer", "GET", rows_url(ds)).json()["items"][0]
    assert set(row) == {"row_id", "cells", "errors"}
    assert row["errors"] == {}
    assert set(row["cells"]) == {str(c) for c in (ds.period, ds.sales, ds.region, ds.note, ds.done)}
    assert cell(row, ds.period) == "2026-03-01"
    assert num(cell(row, ds.sales)) == Decimal("1234.50")
    if db.kind == "pg":
        assert cell(row, ds.sales) == "1234.50"  # 십진 문자열, 자릿수 보존(05 §1)
    assert cell(row, ds.region) == "서울" and cell(row, ds.note) == "안녕"
    assert cell(row, ds.done) is True


def test_c1_unentered_cells_are_null(api, world, ds):
    post_row(api, ds, good(ds))
    row = api("viewer", "GET", rows_url(ds)).json()["items"][0]
    assert cell(row, ds.note) is None and cell(row, ds.done) is None


def test_c1_order_is_by_period_and_paged(api, world, ds):
    for month in ("03", "01", "02", "05", "04"):
        assert post_row(api, ds, good(ds, f"2026-{month}-01")).status_code == 201
    asc = api("viewer", "GET", rows_url(ds)).json()
    assert [cell(r, ds.period) for r in asc["items"]] == [f"2026-0{m}-01" for m in (1, 2, 3, 4, 5)]
    assert asc["total"] == 5
    desc = api("viewer", "GET", rows_url(ds) + "?order=desc&limit=2&offset=1").json()
    assert [cell(r, ds.period) for r in desc["items"]] == ["2026-04-01", "2026-03-01"]
    assert (desc["total"], desc["limit"], desc["offset"]) == (5, 2, 1)
    assert api("viewer", "GET", rows_url(ds) + "?offset=9").json()["items"] == []


def test_c1_without_base_column_order_is_by_row_id(api, world):
    plain = build(api, world, with_base=False)
    for month in ("03", "01", "02"):
        assert post_row(api, plain, good(plain, f"2026-{month}-05")).status_code == 201
    asc = api("viewer", "GET", rows_url(plain)).json()["items"]
    assert [cell(r, plain.period) for r in asc] == ["2026-03-05", "2026-01-05", "2026-02-05"]
    desc = api("viewer", "GET", rows_url(plain) + "?order=desc").json()["items"]
    assert [r["row_id"] for r in desc] == sorted((r["row_id"] for r in asc), reverse=True)


@pytest.mark.parametrize("query", ["order=up", "limit=0", "limit=201", "offset=-1", "limit=x"])
def test_c1_rejects_bad_query(api, world, ds, query):
    response = api("viewer", "GET", rows_url(ds) + "?" + query)
    assert response.status_code == 422 and err(response)["code"] == "VALIDATION_ERROR"


def test_c1_unknown_dataset_is_404(api, world):
    response = api("viewer", "GET", "/api/datasets/99999/rows")
    assert (response.status_code, err(response)["code"]) == (404, "NOT_FOUND")


# --- C2 새 행 ----


def test_c2_creates_a_row(api, db: Db, world, ds):
    response = post_row(api, ds, good(ds))
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["def_version"] == version(api, ds)
    row = body["row"]
    assert row["errors"] == {} and cell(row, ds.region) == "서울"
    assert num(cell(row, ds.sales)) == Decimal(100)
    assert len(stored(db, ds)) == 1 and stored(db, ds)[0]["row_id"] == row["row_id"]


def test_c2_definer_may_enter_too(api, world, ds):
    assert post_row(api, ds, good(ds), who="definer").status_code == 201


def test_c2_blank_values_become_null_and_text_is_nfc(api, db: Db, world, ds):
    import unicodedata

    nfd = unicodedata.normalize("NFD", "가나")
    response = post_row(api, ds, good(ds) | {ds.note: f" {nfd} ", ds.sales: "  "})
    assert response.status_code == 201, response.text
    row = response.json()["row"]
    assert cell(row, ds.note) == "가나" and unicodedata.is_normalized("NFC", cell(row, ds.note))
    assert cell(row, ds.sales) is None


def test_c2_required_columns_including_the_base_date_column(api, db: Db, world, ds):
    assert db.kind in {"sqlite", "pg"}
    response = post_row(api, ds, {ds.sales: "5"})  # 기간(기준 날짜 열, required=false)과 지역 누락
    assert response.status_code == 422
    assert field_map(response) == {
        f"cells.{ds.period}": "REQUIRED",
        f"cells.{ds.region}": "REQUIRED",
    }
    blank = post_row(api, ds, good(ds) | {ds.region: "  ", ds.period: None})
    assert field_map(blank) == {f"cells.{ds.period}": "REQUIRED", f"cells.{ds.region}": "REQUIRED"}
    assert stored(db, ds) == []  # 아무것도 쓰지 않았다


def test_c2_collects_every_field_problem_in_one_response(api, db: Db, world, ds):
    response = post_row(
        api,
        ds,
        {
            ds.period: "2026-03-15",  # 월 단위인데 첫날이 아님
            ds.sales: "-1",
            ds.region: "대구",
            ds.note: "가" * 11,
            ds.done: "maybe",
        },
    )
    assert response.status_code == 422
    assert field_map(response) == {
        f"cells.{ds.period}": "NOT_PERIOD_START",
        f"cells.{ds.sales}": "OUT_OF_RANGE",
        f"cells.{ds.region}": "NOT_IN_OPTIONS",
        f"cells.{ds.note}": "TOO_LONG",
        f"cells.{ds.done}": "BAD_FORMAT",
    }
    assert stored(db, ds) == []
    for item in err(response)["details"]["fields"]:
        assert item["message"]  # 한국어 사용자 문구
        assert "대구" not in json.dumps(item, ensure_ascii=False)  # 입력 값을 되돌려 쓰지 않는다


@pytest.mark.parametrize("value", ["1e3", "abc", "NaN", "Infinity", "1,000", "1.234", 1.5])
def test_c2_bad_numbers(api, world, ds, value):
    response = post_row(api, ds, good(ds) | {ds.sales: value})
    assert response.status_code == 422
    expected = "OUT_OF_RANGE" if value == "1.234" else "BAD_FORMAT"
    assert field_map(response)[f"cells.{ds.sales}"] == expected


def test_c2_json_float_literal_in_the_request_is_rejected(api, world, ds):
    body = (
        f'{{"expected_version": {version(api, ds)}, "cells": '
        f'{{"{ds.period}": "2026-01-01", "{ds.region}": "서울", "{ds.sales}": 12.5}}}}'
    )
    response = api(
        "entry", "POST", rows_url(ds), content=body, headers={"content-type": "application/json"}
    )
    assert response.status_code == 422
    assert field_map(response) == {f"cells.{ds.sales}": "BAD_FORMAT"}


@pytest.mark.parametrize("kind", ["formula", "unknown", "leading-zero", "negative"])
def test_c2_formula_unknown_and_malformed_keys(api, db: Db, world, ds, kind):
    formula_id = _add_formula_column(db, ds)
    key, code = {
        "formula": (str(formula_id), "READ_ONLY"),
        "unknown": ("99999", "BAD_FORMAT"),
        "leading-zero": (f"0{ds.sales}", "BAD_FORMAT"),
        "negative": ("-1", "BAD_FORMAT"),
    }[kind]
    shown = key if key.isdigit() else "invalid"  # 숫자가 아닌 키는 응답에 되돌려 쓰지 않는다
    cells = {str(k): v for k, v in good(ds).items()}
    response = api(
        "entry",
        "POST",
        rows_url(ds),
        json={"expected_version": version(api, ds), "cells": {**cells, key: "1"}},
    )
    assert response.status_code == 422 and field_map(response) == {f"cells.{shown}": code}
    assert stored(db, ds) == []


def test_c2_unknown_text_key_is_not_echoed_back(api, db: Db, world, ds):
    secret = "비밀-키-" + "x" * 100
    cells = {str(k): v for k, v in good(ds).items()}
    response = api(
        "entry",
        "POST",
        rows_url(ds),
        json={"expected_version": version(api, ds), "cells": {**cells, secret: "1"}},
    )
    assert response.status_code == 422
    assert field_map(response) == {"cells.invalid": "BAD_FORMAT"}
    assert "비밀-키" not in response.text
    assert stored(db, ds) == []


def test_c2_period_conflict(api, db: Db, world, ds):
    first = post_row(api, ds, good(ds)).json()["row"]
    response = post_row(api, ds, good(ds))
    assert response.status_code == 409
    body = err(response)
    assert body["code"] == "PERIOD_CONFLICT"
    assert body["details"]["conflicts"] == [
        {"row_id": first["row_id"], "column_id": ds.base, "current": "2026-01-01"}
    ]
    assert len(stored(db, ds)) == 1


def test_c2_same_period_is_allowed_without_a_base_column(api, world):
    plain = build(api, world, with_base=False)
    assert post_row(api, plain, good(plain)).status_code == 201
    assert post_row(api, plain, good(plain)).status_code == 201


def test_c2_definition_version_mismatch(api, db: Db, world, ds):
    response = post_row(api, ds, good(ds), expected_version=1)
    assert response.status_code == 409
    body = err(response)
    assert body["code"] == "DEFINITION_VERSION_MISMATCH"
    assert body["details"] == {"current_version": version(api, ds)}
    assert stored(db, ds) == []


def test_c2_body_shape_errors(api, world, ds):
    url = rows_url(ds)
    v = version(api, ds)
    assert api("entry", "POST", url, json={"cells": {}}).status_code == 422  # 버전 없음
    assert api("entry", "POST", url, json={"expected_version": v}).status_code == 422
    assert (
        api("entry", "POST", url, json={"expected_version": v, "cells": {}, "x": 1}).status_code
        == 422
    )
    assert api("entry", "POST", url, json={"expected_version": 0, "cells": {}}).status_code == 422
    assert (
        api(
            "entry", "POST", "/api/datasets/99999/rows", json={"expected_version": 1, "cells": {}}
        ).status_code
        == 404
    )


def test_c4_chunked_body_over_the_limit_is_413_without_content_length(api, db: Db, world, ds):
    """Content-Length 없는 청크 전송도 1MiB를 넘으면 JSON 413이고 아무것도 쓰지 않는다."""
    chunk = b" " * 65_536

    def body():
        yield b'{"expected_version": 1, "column_ids": [], "rows": []'
        for _ in range(20):  # 1.25MiB
            yield chunk
        yield b"}"

    response = api(
        "entry",
        "POST",
        rows_url(ds, "/paste"),
        content=body(),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413
    assert "content-length" not in response.request.headers
    assert err(response)["details"] == {"limit": 1_048_576}
    assert response.headers["content-type"].startswith("application/json")
    assert stored(db, ds) == []


def test_c2_dataset_without_required_columns_accepts_an_empty_row(api, world):
    dataset = make_dataset(api, world, name="필수 없음")
    column = make_column(api, dataset, "메모", "text")
    response = api(
        "entry",
        "POST",
        f"/api/datasets/{dataset['id']}/rows",
        json={"expected_version": dataset["def_version"], "cells": {}},
    )
    assert (
        response.status_code == 201 and response.json()["row"]["cells"][str(column["id"])] is None
    )


# --- C3 칸 수정 ----


@pytest.fixture
def row(api, world, ds) -> dict:
    response = post_row(api, ds, good(ds) | {ds.sales: "50"})
    assert response.status_code == 201
    return response.json()["row"]


def test_c3_changes_cells_and_returns_the_row(api, db: Db, world, ds, row):
    response = patch_row(
        api,
        ds,
        row["row_id"],
        [change(ds.sales, "50", "75.5"), change(ds.note, None, "메모")],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["def_version"] == version(api, ds)
    assert num(cell(body["row"], ds.sales)) == Decimal("75.5")
    assert cell(body["row"], ds.note) == "메모"
    assert cell(body["row"], ds.region) == "서울"  # 건드리지 않은 칸
    assert len(stored(db, ds)) == 1


def test_c3_expected_compares_values_not_spelling(api, world, ds, row):
    response = patch_row(api, ds, row["row_id"], [change(ds.sales, "50.00", "51")])
    assert response.status_code == 200, response.text


def test_c3_conflict_on_a_cell_reports_current_value_and_changes_nothing(
    api, db: Db, world, ds, row
):
    other = patch_row(api, ds, row["row_id"], [change(ds.sales, "50", "60")], who="definer")
    assert other.status_code == 200
    before = stored(db, ds)
    response = patch_row(
        api, ds, row["row_id"], [change(ds.sales, "50", "70"), change(ds.note, None, "내 메모")]
    )
    assert response.status_code == 409
    body = err(response)
    assert body["code"] == "CELL_CONFLICT"
    assert body["details"]["conflicts"] == [
        {
            "row_id": row["row_id"],
            "column_id": ds.sales,
            "current": body["details"]["conflicts"][0]["current"],
        }
    ]
    assert num(body["details"]["conflicts"][0]["current"]) == Decimal(60)
    assert stored(db, ds) == before  # 충돌 없는 비고 칸도 반영되지 않았다(전체 취소)


def test_c3_every_changed_cell_is_a_guard(api, db: Db, world, ds, row):
    patch_row(api, ds, row["row_id"], [change(ds.note, None, "남이 씀")], who="definer")
    response = patch_row(
        api,
        ds,
        row["row_id"],
        [change(ds.sales, "50", "70"), change(ds.note, None, "내 메모")],  # 비고만 충돌
    )
    assert response.status_code == 409
    conflicts = err(response)["details"]["conflicts"]
    assert [c["column_id"] for c in conflicts] == [ds.note] and conflicts[0]["current"] == "남이 씀"
    assert num(cell(api("viewer", "GET", rows_url(ds)).json()["items"][0], ds.sales)) == Decimal(50)


def test_c3_same_value_is_success(api, db: Db, world, ds, row):
    # 다른 사람이 이미 같은 값으로 바꿔 둠: 내 기대값은 낡았지만 목표 값과 같으므로 성공.
    patch_row(api, ds, row["row_id"], [change(ds.sales, "50", "60")], who="definer")
    response = patch_row(api, ds, row["row_id"], [change(ds.sales, "50", "60")])
    assert response.status_code == 200
    assert num(cell(response.json()["row"], ds.sales)) == Decimal(60)
    # 기대값 = 목표 값 = 현재 값
    assert patch_row(api, ds, row["row_id"], [change(ds.sales, "60", "60")]).status_code == 200


def test_c3_expected_key_is_required(api, world, ds, row):
    body = {
        "expected_version": version(api, ds),
        "changes": [{"column_id": ds.sales, "value": "70"}],
    }
    response = api("entry", "PATCH", rows_url(ds, f"/{row['row_id']}"), json=body)
    assert response.status_code == 422
    assert field_map(response) == {"changes.0.expected": "REQUIRED"}
    assert num(cell(api("viewer", "GET", rows_url(ds)).json()["items"][0], ds.sales)) == Decimal(50)
    # expected: null 은 "빈 칸이었음"이라는 정상 값이다.
    assert patch_row(api, ds, row["row_id"], [change(ds.note, None, "ok")]).status_code == 200
    # value 키도 필수다.
    no_value = {
        "expected_version": version(api, ds),
        "changes": [{"column_id": ds.note, "expected": "ok"}],
    }
    assert (
        api("entry", "PATCH", rows_url(ds, f"/{row['row_id']}"), json=no_value).status_code == 422
    )
    empty = {"expected_version": version(api, ds), "changes": []}
    assert api("entry", "PATCH", rows_url(ds, f"/{row['row_id']}"), json=empty).status_code == 422


def test_c3_expected_null_when_the_cell_is_not_empty_conflicts(api, world, ds, row):
    response = patch_row(api, ds, row["row_id"], [change(ds.sales, None, "70")])
    assert response.status_code == 409 and err(response)["code"] == "CELL_CONFLICT"


def test_c3_missing_row_and_other_datasets_row(api, world, ds, row):
    response = patch_row(api, ds, 99999, [change(ds.sales, None, "1")])
    assert (response.status_code, err(response)["code"]) == (404, "ROW_NOT_FOUND")
    other = build(api, world, unit="day", with_base=False)
    # 다른 데이터셋에서 같은 번호의 행이 있어도 이 데이터셋의 표만 본다.
    post_row(api, other, good(other))
    response = patch_row(api, ds, row["row_id"] + 1000, [change(ds.sales, None, "1")])
    assert err(response)["code"] == "ROW_NOT_FOUND"


def test_c3_validation(api, db: Db, world, ds, row):
    formula_id = _add_formula_column(db, ds)
    version_now = version(api, ds)
    response = api(
        "entry",
        "PATCH",
        rows_url(ds, f"/{row['row_id']}"),
        json={
            "expected_version": version_now,
            "changes": [
                change(ds.sales, "50", "2000000"),  # 범위 밖
                change(ds.region, "서울", None),  # 필수 칸을 비움
                change(formula_id, None, "1"),  # 계산 열
                change(99999, None, "1"),  # 없는 열
                change(ds.note, None, "가" * 11),
                change(ds.note, None, "x"),  # 같은 열 두 번
                change(ds.done, None, "maybe"),
                change(ds.sales, "abc", "1"),
            ],
        },
    )
    assert response.status_code == 422
    assert field_map(response) == {
        "changes.0.value": "OUT_OF_RANGE",
        "changes.1.value": "REQUIRED",
        "changes.2.column_id": "READ_ONLY",
        "changes.3.column_id": "BAD_FORMAT",
        "changes.4.value": "TOO_LONG",
        "changes.5.column_id": "BAD_FORMAT",
        "changes.6.value": "BAD_FORMAT",
        "changes.7.column_id": "BAD_FORMAT",
    }
    assert num(cell(api("viewer", "GET", rows_url(ds)).json()["items"][0], ds.sales)) == Decimal(50)


def test_c3_unparsable_expected_is_a_format_error(api, world, ds, row):
    response = patch_row(api, ds, row["row_id"], [change(ds.sales, "abc", "1")])
    assert response.status_code == 422 and field_map(response) == {
        "changes.0.expected": "BAD_FORMAT"
    }


def test_c3_an_unchanged_value_that_breaks_a_newer_rule_is_not_an_error(api, world, ds, row):
    # 규칙을 바꾸기 전에 들어간 값은 그대로 두고, 같은 값을 다시 보내도 오류가 아니다(06 §3-2).
    response = api(
        "definer",
        "PATCH",
        f"/api/datasets/{ds.id}/columns/{ds.sales}",
        json={"expected_version": version(api, ds), "rules": {"max": 10}},
    )
    assert response.status_code == 200
    assert patch_row(api, ds, row["row_id"], [change(ds.sales, "50", "50")]).status_code == 200
    changed = patch_row(api, ds, row["row_id"], [change(ds.sales, "50", "60")])
    assert changed.status_code == 422 and field_map(changed) == {"changes.0.value": "OUT_OF_RANGE"}


def test_c3_period_move(api, db: Db, world, ds):
    jan = post_row(api, ds, good(ds, "2026-01-01")).json()["row"]
    post_row(api, ds, good(ds, "2026-02-01"))
    conflict = patch_row(api, ds, jan["row_id"], [change(ds.period, "2026-01-01", "2026-02-01")])
    assert conflict.status_code == 409
    body = err(conflict)
    assert body["code"] == "PERIOD_CONFLICT"
    [item] = body["details"]["conflicts"]
    assert item["column_id"] == ds.base and item["current"] == "2026-02-01"
    assert item["row_id"] != jan["row_id"]
    assert cell(api("viewer", "GET", rows_url(ds)).json()["items"][0], ds.period) == "2026-01-01"
    not_first = patch_row(api, ds, jan["row_id"], [change(ds.period, "2026-01-01", "2026-03-10")])
    assert field_map(not_first) == {"changes.0.value": "NOT_PERIOD_START"}
    moved = patch_row(api, ds, jan["row_id"], [change(ds.period, "2026-01-01", "2026-03-01")])
    assert moved.status_code == 200 and cell(moved.json()["row"], ds.period) == "2026-03-01"
    cleared = patch_row(api, ds, jan["row_id"], [change(ds.period, "2026-03-01", None)])
    assert field_map(cleared) == {"changes.0.value": "REQUIRED"}


def test_c3_definition_version_mismatch(api, world, ds, row):
    response = patch_row(api, ds, row["row_id"], [change(ds.note, None, "x")], expected_version=1)
    assert response.status_code == 409 and err(response)["code"] == "DEFINITION_VERSION_MISMATCH"


# --- C4 붙여넣기 ----


def test_c4_creates_and_updates_in_one_request(api, db: Db, world, ds):
    a = post_row(api, ds, good(ds, "2026-01-01")).json()["row"]
    b = post_row(api, ds, good(ds, "2026-02-01") | {ds.sales: "20"}).json()["row"]
    cols = [ds.period, ds.sales, ds.region]
    response = paste(
        api,
        ds,
        cols,
        [
            new_row("2026-05-01", "5", "부산"),
            old_row(b["row_id"], ["2026-02-01", "20", "서울"], ["2026-02-01", "21.5", "서울"]),
            new_row("2026-04-01", "4", "서울"),
            old_row(a["row_id"], ["2026-01-01", "100", "서울"], ["2026-01-01", "100", "부산"]),
        ],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["updated"], body["created"]) == (2, 2)
    assert body["def_version"] == version(api, ds)
    created = {c["index"]: c["row_id"] for c in body["created_rows"]}
    assert set(created) == {0, 2}
    # 새 행은 기간 오름차순으로 넣는다: 4월(요청 2번째 새 행)이 5월보다 먼저 번호를 받는다.
    assert created[2] < created[0]
    items = {cell(r, ds.period): r for r in api("viewer", "GET", rows_url(ds)).json()["items"]}
    assert num(cell(items["2026-02-01"], ds.sales)) == Decimal("21.5")
    assert cell(items["2026-01-01"], ds.region) == "부산"
    assert cell(items["2026-05-01"], ds.region) == "부산" and len(items) == 4


def test_c4_without_base_column_new_rows_keep_input_order(api, world):
    plain = build(api, world, with_base=False)
    response = paste(
        api,
        plain,
        [plain.period, plain.region],
        [
            new_row("2026-03-05", "서울"),
            new_row("2026-01-05", "부산"),
            new_row("2026-02-05", "서울"),
        ],
    )
    assert response.status_code == 200, response.text
    created = response.json()["created_rows"]
    assert [c["index"] for c in created] == [0, 1, 2]
    assert [c["row_id"] for c in created] == sorted(c["row_id"] for c in created)


def test_c4_interprets_values_by_column_type(api, db: Db, world, ds):
    cols = [ds.period, ds.sales, ds.region, ds.note, ds.done]
    response = paste(
        api,
        ds,
        cols,
        [
            new_row("2026-01-01", "1234.5", "서울", " 메모 ", "TRUE"),
            new_row("2026-02-01", "7", "부산", "", "아니오"),
            new_row("2026-03-01", "", "서울", None, None),
        ],
    )
    assert response.status_code == 200, response.text
    items = api("viewer", "GET", rows_url(ds)).json()["items"]
    assert (cell(items[0], ds.note), cell(items[0], ds.done)) == ("메모", True)
    assert (cell(items[1], ds.note), cell(items[1], ds.done)) == (None, False)
    assert cell(items[2], ds.sales) is None


def test_c4_validation_errors_are_collected_with_row_and_column(api, db: Db, world, ds):
    cols = [ds.period, ds.sales, ds.region]
    response = paste(
        api,
        ds,
        cols,
        [
            new_row("2026-01-01", "abc", "서울"),
            new_row("2026-02-15", "5", "대구"),
            new_row("", "5", ""),
            new_row("2026-04-01", "7", "서울"),
        ],
    )
    assert response.status_code == 422
    assert cell_codes(response) == {
        (0, ds.sales, "BAD_FORMAT"),
        (1, ds.period, "NOT_PERIOD_START"),
        (1, ds.region, "NOT_IN_OPTIONS"),
        (2, ds.period, "REQUIRED"),
        (2, ds.region, "REQUIRED"),
    }
    assert stored(db, ds) == []


def test_c4_new_rows_need_every_required_column(api, db: Db, world, ds):
    response = paste(api, ds, [ds.sales], [new_row("5"), new_row("6")])
    assert response.status_code == 422
    assert cell_codes(response) == {
        (i, c, "REQUIRED") for i in (0, 1) for c in (ds.period, ds.region)
    }


def test_c4_shape_errors(api, db: Db, world, ds):
    cols = [ds.period, ds.sales, ds.region]
    row = post_row(api, ds, good(ds)).json()["row"]
    cases = {
        "rows.0.values": [new_row("2026-02-01", "5")],  # 길이 불일치
        "rows.0.expected": [{"row_id": row["row_id"], "values": ["2026-01-01", "1", "서울"]}],
    }
    for field, rows in cases.items():
        response = paste(api, ds, cols, rows)
        assert response.status_code == 422, response.text
        assert field in field_map(response), (field, field_map(response))
    bad_len = paste(api, ds, cols, [old_row(row["row_id"], ["a"], ["2026-01-01", "1", "서울"])])
    assert field_map(bad_len) == {"rows.0.expected": "BAD_FORMAT"}
    dup = paste(
        api,
        ds,
        cols,
        [
            old_row(row["row_id"], ["2026-01-01", "100", "서울"], ["2026-01-01", "1", "서울"]),
            old_row(row["row_id"], ["2026-01-01", "100", "서울"], ["2026-01-01", "2", "서울"]),
        ],
    )
    assert field_map(dup) == {"rows.1.row_id": "BAD_FORMAT"}
    bad_cols = paste(api, ds, [ds.sales, ds.sales, 99999], [new_row("1", "1", "1")])
    assert field_map(bad_cols) == {"column_ids.1": "BAD_FORMAT", "column_ids.2": "BAD_FORMAT"}
    assert paste(api, ds, [], [new_row()]).status_code == 422
    assert paste(api, ds, cols, []).status_code == 422
    assert stored(db, ds) == [stored(db, ds)[0]]


def test_c4_formula_column_is_read_only(api, db: Db, world, ds):
    formula_id = _add_formula_column(db, ds)
    response = paste(api, ds, [formula_id], [new_row("1")])
    assert field_map(response) == {"column_ids.0": "READ_ONLY"}


def test_c4_existing_row_period_cannot_change_but_unchanged_period_is_fine(api, db: Db, world, ds):
    row = post_row(api, ds, good(ds, "2026-01-01")).json()["row"]
    cols = [ds.period, ds.sales]
    moved = paste(
        api, ds, cols, [old_row(row["row_id"], ["2026-01-01", "100"], ["2026-02-01", "5"])]
    )
    assert moved.status_code == 422
    assert cell_codes(moved) == {(0, ds.period, "READ_ONLY")}
    same = paste(
        api, ds, cols, [old_row(row["row_id"], ["2026-01-01", "100"], ["2026-01-01", "5"])]
    )
    assert same.status_code == 200 and same.json()["updated"] == 1


def test_c4_existing_rows_cannot_be_emptied_on_required_columns(api, world, ds):
    row = post_row(api, ds, good(ds)).json()["row"]
    response = paste(api, ds, [ds.region], [old_row(row["row_id"], ["서울"], [None])])
    assert cell_codes(response) == {(0, ds.region, "REQUIRED")}


def test_c4_cell_conflicts_are_collected_and_everything_is_cancelled(api, db: Db, world, ds):
    rows = [
        post_row(api, ds, good(ds, f"2026-0{m}-01") | {ds.sales: "10"}).json()["row"]
        for m in (1, 2, 3)
    ]
    # 다른 사람이 1월·3월 매출을 먼저 바꿨다.
    patch_row(api, ds, rows[0]["row_id"], [change(ds.sales, "10", "11")], who="definer")
    patch_row(api, ds, rows[2]["row_id"], [change(ds.sales, "10", "13")], who="definer")
    before = stored(db, ds)
    cols = [ds.sales, ds.note]
    response = paste(
        api,
        ds,
        cols,
        [
            old_row(rows[0]["row_id"], ["10", None], ["90", "a"]),  # 충돌(매출)
            old_row(rows[1]["row_id"], ["10", None], ["91", "b"]),  # 정상
            old_row(rows[2]["row_id"], ["10", None], ["92", "c"]),  # 충돌(매출)
        ],
    )
    assert response.status_code == 409
    body = err(response)
    assert body["code"] == "PASTE_CONFLICT"
    conflicts = body["details"]["conflicts"]
    assert [(c["row_index"], c["row_id"], c["column_id"], c["kind"]) for c in conflicts] == [
        (0, rows[0]["row_id"], ds.sales, "cell"),
        (2, rows[2]["row_id"], ds.sales, "cell"),
    ]
    assert [num(c["current"]) for c in conflicts] == [Decimal(11), Decimal(13)]
    assert stored(db, ds) == before  # 정상이던 2번째 행도 반영되지 않았다(전부 취소)


def test_c4_period_and_missing_row_conflicts_are_reported_together(api, db: Db, world, ds):
    jan = post_row(api, ds, good(ds, "2026-01-01")).json()["row"]
    cols = [ds.period, ds.region]
    before = stored(db, ds)
    response = paste(
        api,
        ds,
        cols,
        [
            new_row("2026-01-01", "서울"),  # 이미 있는 기간
            new_row("2026-06-01", "부산"),  # 정상(그래도 취소된다)
            old_row(99999, ["2026-03-01", "서울"], ["2026-03-01", "부산"]),  # 없는 행(바뀐 칸 없음)
            new_row("2026-07-01", "서울"),
            new_row("2026-07-01", "부산"),  # 요청 안의 같은 기간 중복
        ],
    )
    assert response.status_code == 409
    conflicts = err(response)["details"]["conflicts"]
    by_index = {c["row_index"]: c for c in conflicts}
    assert by_index[0] == {
        "row_index": 0,
        "row_id": jan["row_id"],
        "column_id": ds.base,
        "kind": "period",
        "current": "2026-01-01",
    }
    assert by_index[2]["kind"] == "row_missing" and by_index[2]["row_id"] == 99999
    assert by_index[4]["kind"] == "period" and by_index[4]["current"] == "2026-07-01"
    assert set(by_index) == {0, 2, 4}
    assert stored(db, ds) == before


def test_c4_updates_written_before_a_later_conflict_are_rolled_back(api, db: Db, world, ds):
    jan = post_row(api, ds, good(ds, "2026-01-01") | {ds.sales: "1"}).json()["row"]
    post_row(api, ds, good(ds, "2026-02-01"))
    before = stored(db, ds)
    cols = [ds.period, ds.sales, ds.region]
    response = paste(
        api,
        ds,
        cols,
        [
            old_row(
                jan["row_id"], ["2026-01-01", "1", "서울"], ["2026-01-01", "999", "서울"]
            ),  # 정상 갱신
            new_row("2026-03-01", "3", "부산"),  # 정상 삽입
            new_row("2026-02-01", "4", "서울"),  # 이미 있는 기간 -> 충돌
        ],
    )
    assert response.status_code == 409 and err(response)["code"] == "PASTE_CONFLICT"
    assert [c["kind"] for c in err(response)["details"]["conflicts"]] == ["period"]
    assert stored(db, ds) == before  # 갱신도 삽입도 남지 않았다


def test_c4_unchanged_cells_are_not_guards(api, db: Db, world, ds):
    row = post_row(api, ds, good(ds) | {ds.sales: "10"}).json()["row"]
    patch_row(api, ds, row["row_id"], [change(ds.note, None, "남의 메모")], who="definer")
    # 비고 칸은 화면이 본 값(null) 그대로 붙여 넣는다 = 바꾸는 칸이 아니라서 남의 변경과
    # 충돌하지 않는다.
    response = paste(
        api,
        ds,
        [ds.sales, ds.note],
        [old_row(row["row_id"], ["10", None], ["20", None])],
    )
    assert response.status_code == 200 and response.json()["updated"] == 1
    item = api("viewer", "GET", rows_url(ds)).json()["items"][0]
    assert num(cell(item, ds.sales)) == Decimal(20) and cell(item, ds.note) == "남의 메모"


def test_c4_row_without_changes_counts_as_nothing(api, world, ds):
    row = post_row(api, ds, good(ds) | {ds.sales: "10"}).json()["row"]
    response = paste(api, ds, [ds.sales], [old_row(row["row_id"], ["10"], ["10.0"])])
    assert response.status_code == 200
    assert (response.json()["updated"], response.json()["created"]) == (0, 0)


def test_c4_expected_version_mismatch(api, db: Db, world, ds):
    response = paste(api, ds, [ds.region], [new_row("서울")], expected_version=1)
    assert response.status_code == 409 and err(response)["code"] == "DEFINITION_VERSION_MISMATCH"


def test_c4_limit_rows(api, db: Db, world):
    plain = build(api, world, with_base=False)
    cols = [plain.region]
    ok = paste(api, plain, cols, [new_row("서울") for _ in range(entry_service.PASTE_MAX_ROWS)])
    assert ok.status_code == 200, ok.text
    assert ok.json()["created"] == 5000 and len(ok.json()["created_rows"]) == 5000
    over = paste(api, plain, cols, [new_row("서울") for _ in range(5001)])
    assert over.status_code == 413
    body = err(over)
    assert body["code"] == "PAYLOAD_TOO_LARGE" and body["details"] == {"limit": 5000}
    assert len(stored(db, plain)) == 5000  # 413은 아무것도 쓰지 않았다


def test_c4_limit_bytes(api, db: Db, world, ds):
    huge = {
        "expected_version": version(api, ds),
        "column_ids": [ds.note],
        "rows": [{"row_id": None, "values": ["x" * 1000]} for _ in range(1100)],
    }
    raw = json.dumps(huge)
    assert len(raw.encode()) > 1_048_576
    response = api(
        "entry",
        "POST",
        rows_url(ds, "/paste"),
        content=raw,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413
    body = err(response)
    assert body["code"] == "PAYLOAD_TOO_LARGE" and body["details"] == {"limit": 1_048_576}
    assert response.headers["content-type"].startswith("application/json")
    assert stored(db, ds) == []


def test_c4_limit_checks_run_after_permission(api, world, ds):
    raw = json.dumps({"x": "y" * 1_100_000})
    response = api(
        "viewer",
        "POST",
        rows_url(ds, "/paste"),
        content=raw,
        headers={"content-type": "application/json"},
    )
    assert (response.status_code, err(response)["code"]) == (403, "FORBIDDEN")


def test_c4_broken_json_is_422_with_a_position(api, world, ds):
    for raw in ('{"expected_version": 1,', "not json", "", "[" * 100_000):
        response = api(
            "entry",
            "POST",
            rows_url(ds, "/paste"),
            content=raw,
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 422, raw[:20]
        [item] = err(response)["details"]["fields"]
        assert item["field"].isdigit() and item["code"] == "BAD_FORMAT"


def test_c4_body_shape_errors(api, world, ds):
    url = rows_url(ds, "/paste")
    v = version(api, ds)
    base = {"expected_version": v, "column_ids": [ds.region], "rows": [new_row("서울")]}
    for bad in (
        {**base, "extra": 1},
        {k: v_ for k, v_ in base.items() if k != "rows"},
        {**base, "column_ids": ["x"]},
        {**base, "rows": [{"row_id": "1", "values": ["서울"]}]},
        {**base, "rows": [{"row_id": None}]},
        [],
    ):
        response = api("entry", "POST", url, json=bad)
        assert response.status_code == 422, bad


# --- RowViewPort ----


def _add_formula_column(db: Db, ds: Ds) -> int:
    """계산 열(`kind=formula`) 정의 행을 직접 넣는다(수식 기능은 1d): `ds_` 표에는 열이 없다."""
    with db.writer.begin() as conn:
        return conn.execute(
            sa.insert(dataset_columns)
            .values(
                dataset_id=ds.id, display_name="계산", type="number", kind="formula", position=99
            )
            .returning(dataset_columns.c.id)
        ).scalar_one()


class FakeRowView:
    """formula 구현을 흉내 낸 포트: 행 번호마다 값과 오류 칸을 돌려준다."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, list[int], list[int]]] = []

    def read_computed(self, session, dataset_id, row_ids, column_ids):
        self.calls.append((dataset_id, list(row_ids), list(column_ids)))
        out = {}
        for row_id in row_ids:
            if row_id % 2:
                out[row_id] = ComputedRow(values={column_ids[0]: Decimal("42.50")})
            else:
                out[row_id] = ComputedRow(
                    values={column_ids[0]: None}, errors={column_ids[0]: "E1"}
                )
        return out


def test_default_row_view_has_no_computed_values_and_no_errors(api, db: Db, world, ds):
    formula_id = _add_formula_column(db, ds)
    post_row(api, ds, good(ds))
    item = api("viewer", "GET", rows_url(ds)).json()["items"][0]
    assert cell(item, formula_id) is None and item["errors"] == {}
    assert PlainRowView().read_computed(None, 1, [1], [2]) == {}


def test_row_view_port_can_be_replaced(db: Db, stub_settings, sync, world):
    view = FakeRowView()
    with custom_client(db, stub_settings, sync, row_view=view) as api:
        ds = build(api, world)
        formula_id = _add_formula_column(db, ds)
        first = post_row(api, ds, good(ds, "2026-01-01"))
        second = post_row(api, ds, good(ds, "2026-02-01"))
        for created in (first, second):
            assert created.status_code == 201
        # 쓰기 응답에도 계산 열이 실린다(같은 트랜잭션에서 읽는다).
        ids = [first.json()["row"]["row_id"], second.json()["row"]["row_id"]]
        odd, even = (first, second) if ids[0] % 2 else (second, first)
        assert num(cell(odd.json()["row"], formula_id)) == Decimal("42.5")
        assert cell(even.json()["row"], formula_id) is None
        assert even.json()["row"]["errors"] == {str(formula_id): "E1"}
        listing = api("viewer", "GET", rows_url(ds)).json()["items"]
        assert {r["row_id"]: r["errors"] for r in listing} == {
            ids[0]: {} if ids[0] % 2 else {str(formula_id): "E1"},
            ids[1]: {} if ids[1] % 2 else {str(formula_id): "E1"},
        }
        assert all(call[0] == ds.id and call[2] == [formula_id] for call in view.calls)


def test_row_view_is_not_called_when_there_are_no_computed_columns(
    db: Db, stub_settings, sync, world
):
    view = FakeRowView()
    with custom_client(db, stub_settings, sync, row_view=view) as api:
        ds = build(api, world)
        post_row(api, ds, good(ds))
        api("viewer", "GET", rows_url(ds))
    assert view.calls == []


def test_error_codes_used_here_exist_in_the_dictionary():
    for name in (
        "CELL_CONFLICT",
        "PASTE_CONFLICT",
        "PERIOD_CONFLICT",
        "WRITE_BUSY",
        "ROW_NOT_FOUND",
        "PAYLOAD_TOO_LARGE",
        "DEFINITION_VERSION_MISMATCH",
    ):
        assert hasattr(ErrorCode, name)


def test_paste_request_body_schema_is_in_openapi(make_settings, sqlite_engine):
    """원시 `Request`를 받는 붙여넣기도 OpenAPI에 본문 스키마(`PasteBody`)가 있다."""
    from app.main import create_app

    app = create_app(make_settings(), engine=sqlite_engine)
    operation = app.openapi()["paths"]["/api/datasets/{dataset_id}/rows/paste"]["post"]
    schema = operation["requestBody"]["content"]["application/json"]["schema"]
    assert set(schema["required"]) == {"expected_version", "column_ids", "rows"}
    assert "$defs" not in schema
    assert schema["properties"]["rows"]["items"]["properties"].keys() >= {"row_id", "values"}
