"""계산 열의 표시 형식 `rules`(B6, 03b 33-2) 시험. SQLite와 실제 PostgreSQL 두 변형으로 돈다.

허용 키는 `display_decimals`(정수 0~10, 불리언 거부)·`display_thousands`(불리언)뿐이다. 보낸 객체가
저장 값 전체를 대체하고 `{}`는 지우며 `null`은 바꾸지 않는다. 숫자가 아닌 결과 열의 값은 422다.
"""

from __future__ import annotations

import json

import pytest
import sqlalchemy as sa

from app.db_metadata import dataset_columns
from tests.audit_helpers import Ctx, audit_rows_of
from tests.formula_api_helpers import (
    add_column,
    add_formula,
    err,
    make_dataset,
    put_formula,
    version,
)


@pytest.fixture
def fx(ctx: Ctx) -> dict[str, int]:
    dataset = make_dataset(ctx.call, ctx.world, "표시 형식")
    sales = add_column(ctx.call, dataset["id"], "매출")["id"]
    name = add_column(ctx.call, dataset["id"], "이름", "text")["id"]
    calc = add_formula(ctx.call, dataset["id"], "합계", "[매출] * 2")["id"]
    return {"ds": dataset["id"], "sales": sales, "name": name, "calc": calc}


def patch(ctx: Ctx, fx: dict[str, int], column: str, **body):
    return ctx.call(
        "definer",
        "PATCH",
        f"/api/datasets/{fx['ds']}/columns/{fx[column]}",
        json={"expected_version": version(ctx.call, fx["ds"]), **body},
    )


def stored_rules(ctx: Ctx, column_id: int):
    with ctx.db.writer.connect() as conn:
        raw = conn.execute(
            sa.select(dataset_columns.c.rules).where(dataset_columns.c.id == column_id)
        ).scalar_one()
    return json.loads(raw) if isinstance(raw, str) else raw


def fields(response) -> dict[str, str]:
    return {f["field"]: f["code"] for f in err(response)["details"]["fields"]}


def test_allowed_keys_are_saved_and_returned_for_a_formula_column(ctx, fx):
    response = patch(ctx, fx, "calc", rules={"display_decimals": 2, "display_thousands": False})
    assert response.status_code == 200, response.text
    expected = {"display_decimals": 2, "display_thousands": False}
    assert response.json()["column"]["rules"] == expected
    assert stored_rules(ctx, fx["calc"]) == expected
    detail = ctx.call("viewer", "GET", f"/api/datasets/{fx['ds']}").json()
    assert {c["id"]: c["rules"] for c in detail["columns"]}[fx["calc"]] == expected
    # 처음 만든 계산 열은 rules가 null이다
    other = add_formula(ctx.call, fx["ds"], "다른 합계", "[매출] + 1")
    assert other["rules"] is None
    bounds = [0, 10]
    for decimals in bounds:
        ok = patch(ctx, fx, "calc", rules={"display_decimals": decimals})
        assert ok.status_code == 200 and ok.json()["column"]["rules"] == {
            "display_decimals": decimals
        }


def test_sent_object_replaces_empty_object_clears_and_null_keeps(ctx, fx):
    patch(ctx, fx, "calc", rules={"display_decimals": 3, "display_thousands": False})
    # 전체 대체: 보내지 않은 키는 사라진다
    replaced = patch(ctx, fx, "calc", rules={"display_thousands": True})
    assert replaced.json()["column"]["rules"] == {"display_thousands": True}
    # null은 변경 없음(버전도 그대로)
    before = version(ctx.call, fx["ds"])
    kept = patch(ctx, fx, "calc", rules=None)
    assert kept.status_code == 200 and kept.json()["def_version"] == before
    assert stored_rules(ctx, fx["calc"]) == {"display_thousands": True}
    # 같은 값을 다시 보내도 변경 없음
    same = patch(ctx, fx, "calc", rules={"display_thousands": True})
    assert same.json()["def_version"] == before
    # {}는 설정을 지운다
    cleared = patch(ctx, fx, "calc", rules={})
    assert cleared.status_code == 200 and cleared.json()["column"]["rules"] is None
    assert cleared.json()["def_version"] == before + 1
    assert stored_rules(ctx, fx["calc"]) is None


@pytest.mark.parametrize(
    ("rules", "field", "code"),
    [
        ({"display_decimals": 11}, "rules.display_decimals", "OUT_OF_RANGE"),
        ({"display_decimals": -1}, "rules.display_decimals", "OUT_OF_RANGE"),
        ({"display_decimals": True}, "rules.display_decimals", "BAD_FORMAT"),
        ({"display_decimals": False}, "rules.display_decimals", "BAD_FORMAT"),
        ({"display_decimals": 1.5}, "rules.display_decimals", "BAD_FORMAT"),
        ({"display_decimals": "2"}, "rules.display_decimals", "BAD_FORMAT"),
        ({"display_thousands": 1}, "rules.display_thousands", "BAD_FORMAT"),
        ({"display_thousands": "yes"}, "rules.display_thousands", "BAD_FORMAT"),
        ({"decimals": 2}, "rules.decimals", "BAD_FORMAT"),
        ({"min": "1"}, "rules.min", "BAD_FORMAT"),
        ({"surprise": True}, "rules.surprise", "BAD_FORMAT"),
    ],
)
def test_invalid_display_rules_are_422_and_change_nothing(ctx, fx, rules, field, code):
    patch(ctx, fx, "calc", rules={"display_decimals": 4})
    before = version(ctx.call, fx["ds"])
    response = patch(ctx, fx, "calc", rules=rules)
    assert response.status_code == 422 and err(response)["code"] == "VALIDATION_ERROR"
    assert fields(response) == {field: code}
    assert version(ctx.call, fx["ds"]) == before
    assert stored_rules(ctx, fx["calc"]) == {"display_decimals": 4}


def test_non_number_formula_column_rejects_values_but_accepts_clearing(ctx, fx):
    text_calc = add_formula(ctx.call, fx["ds"], "연결", '[이름] & "님"')
    assert text_calc["type"] == "text"
    fx["text_calc"] = text_calc["id"]
    before = version(ctx.call, fx["ds"])
    response = patch(ctx, fx, "text_calc", rules={"display_decimals": 2})
    assert response.status_code == 422 and fields(response) == {"rules": "BAD_FORMAT"}
    assert version(ctx.call, fx["ds"]) == before
    assert patch(ctx, fx, "text_calc", rules={}).status_code == 200  # 지우기는 형과 무관
    assert patch(ctx, fx, "text_calc", rules=None).status_code == 200


def test_changing_the_result_type_keeps_the_saved_rules(ctx, fx):
    saved = {"display_decimals": 1, "display_thousands": False}
    assert patch(ctx, fx, "calc", rules=saved).status_code == 200
    to_text = put_formula(ctx.call, fx["ds"], fx["calc"], '[이름] & "나"')
    assert to_text.status_code == 200 and to_text.json()["result_type_changed"] is True
    assert to_text.json()["column"]["type"] == "text"
    assert to_text.json()["column"]["rules"] == saved
    assert stored_rules(ctx, fx["calc"]) == saved
    # 숫자 형으로 돌아와도 그대로다
    back = put_formula(ctx.call, fx["ds"], fx["calc"], "[매출] + 1")
    assert back.json()["column"]["type"] == "number" and back.json()["column"]["rules"] == saved
    # 숫자 아닌 형일 때 값 있는 새 설정은 거부된다(저장된 설정은 그대로)
    put_formula(ctx.call, fx["ds"], fx["calc"], '[이름] & "나"')
    assert patch(ctx, fx, "calc", rules={"display_decimals": 5}).status_code == 422
    assert stored_rules(ctx, fx["calc"]) == saved


def test_archived_dataset_answers_archived_before_version_and_validation(ctx, fx):
    assert ctx.call("definer", "POST", f"/api/datasets/{fx['ds']}/archive").status_code == 200
    bad = ctx.call(
        "definer",
        "PATCH",
        f"/api/datasets/{fx['ds']}/columns/{fx['calc']}",
        json={"expected_version": 999, "rules": {"display_decimals": 99}},
    )
    assert bad.status_code == 409 and err(bad)["code"] == "DATASET_ARCHIVED"
    assert stored_rules(ctx, fx["calc"]) is None


def test_audit_records_rules_changed_without_the_values(ctx, fx):
    before = len(audit_rows_of(ctx.db, "column.update"))
    assert patch(ctx, fx, "calc", rules={"display_decimals": 7}).status_code == 200
    rows = audit_rows_of(ctx.db, "column.update")[before:]
    assert len(rows) == 1
    details = rows[0]["details"]
    details = json.loads(details) if isinstance(details, str) else details
    assert details["rules_changed"] is True and details["changes"] == {}
    assert "display_decimals" not in json.dumps(details)
    assert "display_thousands" not in json.dumps(details) and "rules" not in details
    # null(변경 없음)과 같은 값은 기록하지 않는다
    patch(ctx, fx, "calc", rules=None)
    patch(ctx, fx, "calc", rules={"display_decimals": 7})
    assert len(audit_rows_of(ctx.db, "column.update")) == before + 1
    # 지우기도 값 없이 기록된다
    assert patch(ctx, fx, "calc", rules={}).status_code == 200
    last = audit_rows_of(ctx.db, "column.update")[-1]["details"]
    last = json.loads(last) if isinstance(last, str) else last
    assert last["rules_changed"] is True and "display" not in json.dumps(last)


def test_input_column_rules_behave_as_before(ctx, fx):
    ok = patch(ctx, fx, "sales", rules={"min": 0, "decimals": 2})
    assert ok.status_code == 200 and ok.json()["column"]["rules"] == {"min": "0", "decimals": 2}
    # 표시 형식 키는 입력 열에 없다
    rejected = patch(ctx, fx, "sales", rules={"display_decimals": 2})
    assert rejected.status_code == 422 and fields(rejected) == {
        "rules.display_decimals": "BAD_FORMAT"
    }
    # 입력 열의 null은 지금도 규칙을 지운다(계산 열의 null과 다르다)
    cleared = patch(ctx, fx, "sales", rules=None)
    assert cleared.status_code == 200 and cleared.json()["column"]["rules"] is None
    # 계산 열은 여전히 필수일 수 없다
    required = patch(ctx, fx, "calc", required=True)
    assert required.status_code == 422 and fields(required) == {"required": "BAD_FORMAT"}


def test_columns_with_equal_positions_are_listed_by_position_then_id(ctx, fx):
    ids = [fx["sales"], fx["name"], fx["calc"]]
    for key in ("calc", "name", "sales"):  # 일부러 거꾸로 맞춘다
        assert patch(ctx, fx, key, position=5).status_code == 200
    detail = ctx.call("viewer", "GET", f"/api/datasets/{fx['ds']}").json()
    listed = [c["id"] for c in detail["columns"]]
    assert listed == sorted(ids)  # 위치 번호가 같으면 열 번호 순서
    assert {c["position"] for c in detail["columns"]} == {5}
