"""기준값 API 시험(05 §2-8 R1~R5): 권한, 응답 모양, 판정 순서, 값 규칙, 중복, 정정, 감사.

SQLite와 실제 PostgreSQL(`pg`) 두 변형으로 돈다(38자리 값·락 시험은 PostgreSQL 변형만).
"""

from __future__ import annotations

import ast
import unicodedata
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.reference import service
from tests.audit_helpers import Ctx, audit_rows, audit_rows_of, failing_audit_insert, failing_commit
from tests.reference_helpers import (
    add_item,
    add_value,
    api_add_item,
    api_add_value,
    api_update_value,
    item_rows,
    value_rows,
)

ITEMS = "/api/reference-items"
ITEM_KEYS = {
    "id",
    "name",
    "description",
    "value_count",
    "year_min",
    "year_max",
    "created_by",
    "created_at",
}
VALUE_KEYS = {"id", "item_id", "year", "value", "created_by", "created_at"}
ALL_ROLES = ("admin", "definer", "entry", "other", "viewer")
NON_ADMIN = ("definer", "entry", "other", "viewer")


def exact_digits(ctx: Ctx) -> None:
    """SQLite의 숫자는 쓴 자릿수를 보존하지 못한다(소수 10자리로 돌려줌). 자릿수 단정은 PG만."""
    if ctx.db.kind != "pg":
        pytest.skip("SQLite는 쓴 자릿수를 보존하지 못한다(PostgreSQL 변형이 단정한다)")


def err(response) -> dict[str, Any]:
    return response.json()["error"]


def field_codes(response) -> dict[str, str]:
    return {f["field"]: f["code"] for f in err(response)["details"]["fields"]}


# --- 권한 ----


@pytest.mark.parametrize("login", ALL_ROLES)
def test_everyone_can_read_items_and_values(ctx: Ctx, login):
    item = add_item(ctx.db, "전기요금", ctx.uid("admin"))
    add_value(ctx.db, item, 2026, "12.5", ctx.uid("admin"))
    listing = ctx.call(login, "GET", ITEMS)
    assert listing.status_code == 200 and listing.json()["total"] == 1
    values = ctx.call(login, "GET", f"{ITEMS}/{item}/values")
    assert values.status_code == 200
    assert Decimal(values.json()["items"][0]["value"]) == Decimal("12.5")


@pytest.mark.parametrize("login", NON_ADMIN)
def test_non_admin_cannot_write_and_nothing_changes(ctx: Ctx, login):
    item = add_item(ctx.db, "전기요금", ctx.uid("admin"))
    value = add_value(ctx.db, item, 2026, "12.5", ctx.uid("admin"))
    assert api_add_item(ctx.call, "새 항목", login=login).status_code == 403
    assert api_add_value(ctx.call, item, 2027, "1", login=login).status_code == 403
    assert api_update_value(ctx.call, item, value, "99", login=login).status_code == 403
    assert len(item_rows(ctx.db)) == 1 and len(value_rows(ctx.db)) == 1
    assert value_rows(ctx.db)[0]["number_value"] == Decimal("12.5")
    assert audit_rows(ctx.db) == []


def test_permission_check_comes_before_body_validation(ctx: Ctx):
    """403이 422보다 먼저다: 권한 없는 사용자는 입력 오류의 내용을 알 수 없다."""
    item = add_item(ctx.db, "전기요금", ctx.uid("admin"))
    value = add_value(ctx.db, item, 2026, "12.5", ctx.uid("admin"))
    for call in (
        lambda: ctx.call("viewer", "POST", ITEMS, json={"name": 3, "extra": 1}),
        lambda: ctx.call("viewer", "POST", f"{ITEMS}/{item}/values", json={"year": "x"}),
        lambda: ctx.call("viewer", "PATCH", f"{ITEMS}/{item}/values/{value}", json={"year": 1}),
        lambda: ctx.call("inactive", "POST", ITEMS, json={}),
    ):
        assert call().status_code == 403


def test_anonymous_and_unregistered_are_rejected(ctx: Ctx):
    assert ctx.call(None, "GET", ITEMS).status_code == 401
    assert ctx.call("stranger", "GET", ITEMS).status_code == 403
    assert ctx.call(None, "POST", ITEMS, json={"name": "x"}).status_code == 401


def test_there_is_no_delete_or_rename_or_description_route(ctx: Ctx):
    """항목 삭제·이름 변경·설명 수정 엔드포인트는 없다(후속)."""
    item = add_item(ctx.db, "전기요금", ctx.uid("admin"))
    value = add_value(ctx.db, item, 2026, 1, ctx.uid("admin"))
    for method, path in (
        ("DELETE", f"{ITEMS}/{item}"),
        ("PATCH", f"{ITEMS}/{item}"),
        ("PUT", f"{ITEMS}/{item}"),
        ("DELETE", f"{ITEMS}/{item}/values/{value}"),
        ("PUT", f"{ITEMS}/{item}/values/{value}"),
    ):
        assert ctx.call("admin", method, path, json={}).status_code in {404, 405}, (method, path)


# --- R2 항목 추가 ----


def test_create_item_returns_the_contract_shape(ctx: Ctx):
    response = api_add_item(ctx.call, "전기요금_A팀", "A팀 전기 단가(원/kWh)")
    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == ITEM_KEYS
    assert body["name"] == "전기요금_A팀" and body["description"] == "A팀 전기 단가(원/kWh)"
    assert (body["value_count"], body["year_min"], body["year_max"]) == (0, None, None)
    assert body["created_by"] == {"id": ctx.uid("admin"), "display_name": "관리자"}
    assert body["created_at"].endswith("+09:00")


def test_item_name_is_normalized_and_description_blank_becomes_null(ctx: Ctx):
    nfd = unicodedata.normalize("NFD", "전기요금")
    response = api_add_item(ctx.call, f"  {nfd}  ", "   ")
    assert response.status_code == 201
    assert response.json()["name"] == "전기요금" and response.json()["description"] is None
    assert [r["name"] for r in item_rows(ctx.db)] == ["전기요금"]


def test_duplicate_item_name_is_409_with_field_name_and_nfc_equal_names_collide(ctx: Ctx):
    assert api_add_item(ctx.call, "전기요금").status_code == 201
    for name in ("전기요금", unicodedata.normalize("NFD", "전기요금")):
        response = api_add_item(ctx.call, name)
        assert (response.status_code, err(response)["code"]) == (409, "ALREADY_EXISTS")
        assert err(response)["details"]["field"] == "name"
    assert len(item_rows(ctx.db)) == 1
    assert len(audit_rows_of(ctx.db, "reference.create")) == 1  # 실패한 호출은 기록이 없다


def test_item_names_differing_only_in_case_are_separate_items(ctx: Ctx):
    """알려진 한계(06 §2-2): 비교는 정확히 일치라 대소문자만 다른 이름은 별개 항목이다."""
    assert api_add_item(ctx.call, "Tariff").status_code == 201
    assert api_add_item(ctx.call, "tariff").status_code == 201


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("", "REQUIRED"),
        ("   ", "REQUIRED"),
        ("가" * 51, "TOO_LONG"),
        ("요금[A]", "BAD_FORMAT"),
        ('요금"A"', "BAD_FORMAT"),
        ("요금\\A", "BAD_FORMAT"),
        ("요금\nA", "BAD_FORMAT"),
        ("요금\x00A", "BAD_FORMAT"),
        ("요금\u200bA", "BAD_FORMAT"),  # 서식 문자(Cf)
        ("요금\u2028A", "BAD_FORMAT"),  # 줄 구분(Zl)
        ("요금\u2029A", "BAD_FORMAT"),  # 문단 구분(Zp)
    ],
)
def test_item_name_rules(ctx: Ctx, name, code):
    response = ctx.call("admin", "POST", ITEMS, json={"name": name})
    assert (response.status_code, err(response)["code"]) == (422, "VALIDATION_ERROR")
    assert field_codes(response) == {"name": code}
    assert item_rows(ctx.db) == [] and audit_rows(ctx.db) == []


def test_item_name_of_exactly_50_characters_and_description_200_are_accepted(ctx: Ctx):
    response = api_add_item(ctx.call, "가" * 50, "나" * 200)
    assert response.status_code == 201
    over = ctx.call("admin", "POST", ITEMS, json={"name": "x", "description": "나" * 201})
    assert (over.status_code, field_codes(over)) == (422, {"description": "TOO_LONG"})


@pytest.mark.parametrize(
    "body",
    [{}, {"name": None}, {"name": 5}, {"name": "x", "description": 5}, {"name": "x", "extra": 1}],
)
def test_malformed_create_bodies_are_422(ctx: Ctx, body):
    response = ctx.call("admin", "POST", ITEMS, json=body)
    assert (response.status_code, err(response)["code"]) == (422, "VALIDATION_ERROR")


def test_every_name_the_api_accepts_is_a_valid_formula_text_constant(ctx: Ctx):
    """`REF("이름")`의 글자 상수로 쓸 수 있어야 한다(07 §4-2): 수식 엔진의 규칙으로 대조한다."""
    from app.formula.literals import normalize_text_constant, text_constant_problem

    for name in ("전기요금_A팀", "a b", "100%", "O'Brien", "요금-2026", "가" * 50, "é"):
        assert api_add_item(ctx.call, name).status_code == 201, name
        stored = unicodedata.normalize("NFC", name)
        assert text_constant_problem(normalize_text_constant(stored)) is None


# --- R1·R3 목록 ----


def test_list_items_shows_counts_and_year_range_and_pages(ctx: Ctx):
    admin = ctx.uid("admin")
    empty = add_item(ctx.db, "나", admin)
    full = add_item(ctx.db, "가", admin, "설명")
    add_value(ctx.db, full, 2024, 1, admin)
    add_value(ctx.db, full, 2026, 3, admin)
    add_value(ctx.db, full, 2025, 2, admin)
    body = ctx.call("viewer", "GET", ITEMS).json()
    assert set(body) == {"items", "total", "limit", "offset"} and body["total"] == 2
    by_name = {i["name"]: i for i in body["items"]}
    assert (by_name["가"]["value_count"], by_name["가"]["year_min"], by_name["가"]["year_max"]) == (
        3,
        2024,
        2026,
    )
    assert by_name["가"]["description"] == "설명"
    assert (by_name["나"]["value_count"], by_name["나"]["year_min"]) == (0, None)
    assert {i["id"] for i in body["items"]} == {empty, full}
    page = ctx.call("viewer", "GET", ITEMS, params={"limit": 1, "offset": 1}).json()
    assert page["total"] == 2 and len(page["items"]) == 1 and page["limit"] == 1


def test_list_items_is_sorted_by_name_in_korean_order_on_postgresql(ctx: Ctx):
    if ctx.db.kind != "pg":
        pytest.skip("한글 가나다순 collation은 PostgreSQL 변형만 단정한다")
    admin = ctx.uid("admin")
    for name in ("하늘", "가스", "나비", "다람쥐"):
        add_item(ctx.db, name, admin)
    names = [i["name"] for i in ctx.call("viewer", "GET", ITEMS).json()["items"]]
    assert names == ["가스", "나비", "다람쥐", "하늘"]


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"offset": -1}, {"limit": "x"}])
def test_list_query_bounds_are_422(ctx: Ctx, params):
    response = ctx.call("viewer", "GET", ITEMS, params=params)
    assert (response.status_code, err(response)["code"]) == (422, "VALIDATION_ERROR")


def test_values_are_listed_by_year_descending_with_the_contract_shape(ctx: Ctx):
    exact_digits(ctx)
    admin = ctx.uid("admin")
    item = add_item(ctx.db, "전기요금", admin)
    for year, value in ((2024, "1.50"), (2026, "3"), (2025, "2.25")):
        add_value(ctx.db, item, year, value, admin)
    body = ctx.call("viewer", "GET", f"{ITEMS}/{item}/values").json()
    assert [(v["year"], v["value"]) for v in body["items"]] == [
        (2026, "3"),
        (2025, "2.25"),
        (2024, "1.50"),
    ]
    assert all(set(v) == VALUE_KEYS for v in body["items"]) and body["total"] == 3
    assert all(v["item_id"] == item for v in body["items"])


def test_values_of_a_missing_item_is_404(ctx: Ctx):
    response = ctx.call("viewer", "GET", f"{ITEMS}/9999/values")
    assert (response.status_code, err(response)["code"]) == (404, "NOT_FOUND")


# --- R4 연도 값 추가 ----


def test_add_value_returns_the_contract_shape_and_keeps_the_written_digits(ctx: Ctx):
    exact_digits(ctx)
    item = api_add_item(ctx.call, "전기요금").json()["id"]
    response = api_add_value(ctx.call, item, 2026, "1234.50")
    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == VALUE_KEYS
    assert (body["item_id"], body["year"], body["value"]) == (item, 2026, "1234.50")
    assert body["created_by"] == {"id": ctx.uid("admin"), "display_name": "관리자"}
    assert value_rows(ctx.db)[0]["number_value"] == Decimal("1234.50")


@pytest.mark.parametrize("text", ["-3", "+3", "0", "0.000001", "007", "-0.5"])
def test_add_value_accepts_plain_decimal_text(ctx: Ctx, text):
    item = add_item(ctx.db, "x", ctx.uid("admin"))
    assert api_add_value(ctx.call, item, 2026, text).status_code == 201


def test_duplicate_item_and_year_is_409_with_a_hint_to_use_correction(ctx: Ctx):
    item = api_add_item(ctx.call, "전기요금").json()["id"]
    assert api_add_value(ctx.call, item, 2026, "1").status_code == 201
    response = api_add_value(ctx.call, item, 2026, "2")
    assert (response.status_code, err(response)["code"]) == (409, "ALREADY_EXISTS")
    assert err(response)["details"]["field"] == "year" and "정정" in err(response)["message"]
    assert [r["number_value"] for r in value_rows(ctx.db)] == [Decimal("1")]
    assert len(audit_rows_of(ctx.db, "reference_value.add")) == 1


def test_same_year_in_different_items_is_allowed(ctx: Ctx):
    first = add_item(ctx.db, "가", ctx.uid("admin"))
    second = add_item(ctx.db, "나", ctx.uid("admin"))
    assert api_add_value(ctx.call, first, 2026, "1").status_code == 201
    assert api_add_value(ctx.call, second, 2026, "1").status_code == 201


@pytest.mark.parametrize(
    ("year", "value", "expected"),
    [
        (1899, "1", {"year": "OUT_OF_RANGE"}),
        (10000, "1", {"year": "OUT_OF_RANGE"}),
        (20266, "1", {"year": "OUT_OF_RANGE"}),
        (0, "1", {"year": "OUT_OF_RANGE"}),
        (-5, "1", {"year": "OUT_OF_RANGE"}),
        (2026, "", {"value": "REQUIRED"}),
        (2026, "  ", {"value": "REQUIRED"}),
        (2026, "abc", {"value": "BAD_FORMAT"}),
        (2026, "1e3", {"value": "BAD_FORMAT"}),
        (2026, "NaN", {"value": "BAD_FORMAT"}),
        (2026, "Infinity", {"value": "BAD_FORMAT"}),
        (2026, "-Infinity", {"value": "BAD_FORMAT"}),
        (2026, "1,000", {"value": "BAD_FORMAT"}),
        (2026, ".5", {"value": "BAD_FORMAT"}),
        (2026, "5.", {"value": "BAD_FORMAT"}),
        (2026, "1_0", {"value": "BAD_FORMAT"}),
        (2026, "1" * 39, {"value": "OUT_OF_RANGE"}),
        (2026, "0." + "1" * 39, {"value": "OUT_OF_RANGE"}),
        (1899, "x", {"year": "OUT_OF_RANGE", "value": "BAD_FORMAT"}),
    ],
)
def test_add_value_rule_errors_are_422_and_write_nothing(ctx: Ctx, year, value, expected):
    item = add_item(ctx.db, "x", ctx.uid("admin"))
    response = api_add_value(ctx.call, item, year, value)
    assert (response.status_code, err(response)["code"]) == (422, "VALIDATION_ERROR")
    assert field_codes(response) == expected
    assert value_rows(ctx.db) == [] and audit_rows(ctx.db) == []


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"year": 2026, "value": 12.5}, "BAD_FORMAT"),  # JSON 숫자 값은 형식 오류(05 R4)
        ({"year": 2026, "value": 12}, "BAD_FORMAT"),
        ({"year": "2026", "value": "1"}, "BAD_FORMAT"),
        ({"year": 2026.0, "value": "1"}, "BAD_FORMAT"),
        ({"year": True, "value": "1"}, "BAD_FORMAT"),
        ({"year": None, "value": "1"}, "BAD_FORMAT"),
        ({"value": "1"}, "REQUIRED"),
        ({"year": 2026}, "REQUIRED"),
    ],
)
def test_add_value_shape_errors_come_from_the_body_schema(ctx: Ctx, body, code):
    item = add_item(ctx.db, "x", ctx.uid("admin"))
    response = ctx.call("admin", "POST", f"{ITEMS}/{item}/values", json=body)
    assert (response.status_code, err(response)["code"]) == (422, "VALIDATION_ERROR")
    assert code in field_codes(response).values()


def test_add_value_judgement_order_is_404_then_422_then_409(ctx: Ctx):
    admin = ctx.uid("admin")
    item = add_item(ctx.db, "x", admin)
    add_value(ctx.db, item, 2026, 1, admin)
    # 항목이 없으면 값 규칙이 틀려도 404가 먼저다(본문 형태가 맞을 때)
    missing = api_add_value(ctx.call, 9999, 2026, "abc")
    assert (missing.status_code, err(missing)["code"]) == (404, "NOT_FOUND")
    # 같은 연도 + 값 규칙 위반이면 422가 409보다 먼저다
    both = api_add_value(ctx.call, item, 2026, "abc")
    assert (both.status_code, err(both)["code"]) == (422, "VALIDATION_ERROR")
    dup = api_add_value(ctx.call, item, 2026, "5")
    assert (dup.status_code, err(dup)["code"]) == (409, "ALREADY_EXISTS")
    # 본문 형태 오류(Pydantic)는 항목 404보다 먼저다
    shape = ctx.call("admin", "POST", f"{ITEMS}/9999/values", json={"year": "x", "value": "1"})
    assert (shape.status_code, err(shape)["code"]) == (422, "VALIDATION_ERROR")


def test_add_value_to_unknown_item_is_404(ctx: Ctx):
    response = api_add_value(ctx.call, 9999, 2026, "1")
    assert (response.status_code, err(response)["code"]) == (404, "NOT_FOUND")


def test_38_digit_values_round_trip_on_postgresql(ctx: Ctx):
    if ctx.db.kind != "pg":
        pytest.skip("SQLite는 38자리 정밀도를 보존하지 못한다")
    item = add_item(ctx.db, "x", ctx.uid("admin"))
    for year, text in ((2020, "1" * 38), (2021, "0." + "5" * 38), (2022, "-" + "9" * 38)):
        response = api_add_value(ctx.call, item, year, text)
        assert response.status_code == 201, response.text
        assert response.json()["value"] == text


# --- R5 정정 ----


def seed_value(ctx: Ctx, value: str = "12.5", year: int = 2026) -> tuple[int, int]:
    item = add_item(ctx.db, "전기요금", ctx.uid("admin"))
    return item, add_value(ctx.db, item, year, value, ctx.uid("admin"))


def test_correction_returns_new_and_previous_value_and_changes_only_the_number(ctx: Ctx):
    exact_digits(ctx)
    item, value_id = seed_value(ctx)
    before = value_rows(ctx.db)[0]
    response = api_update_value(ctx.call, item, value_id, "13.75")
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"value", "previous_value", "changed"}
    assert body["changed"] is True and body["previous_value"] == "12.5"
    assert set(body["value"]) == VALUE_KEYS
    assert (body["value"]["id"], body["value"]["year"], body["value"]["value"]) == (
        value_id,
        2026,
        "13.75",
    )
    after = value_rows(ctx.db)[0]
    assert after["number_value"] == Decimal("13.75")
    for column in ("id", "item_id", "year", "created_by", "created_at"):
        assert after[column] == before[column], column  # 처음 입력의 기록은 정정해도 그대로다
    assert body["value"]["created_by"]["id"] == before["created_by"]


def test_correcting_to_a_numerically_equal_value_is_200_changed_false_and_writes_nothing(ctx: Ctx):
    exact_digits(ctx)
    item, value_id = seed_value(ctx, "1.0")
    before = value_rows(ctx.db)
    for text in ("1.0", "1.00", "1", "+1", "01.000"):
        response = api_update_value(ctx.call, item, value_id, text)
        assert response.status_code == 200, text
        body = response.json()
        assert body["changed"] is False and body["previous_value"] == "1.0", text
        assert body["value"]["value"] == "1.0"
    assert value_rows(ctx.db) == before  # 자릿수도 그대로(1.0이 1.00으로 바뀌지 않는다)
    assert audit_rows_of(ctx.db, "reference_value.update") == []


def test_the_last_write_wins_and_each_correction_records_before_and_after(ctx: Ctx):
    exact_digits(ctx)
    item, value_id = seed_value(ctx, "10")
    api_update_value(ctx.call, item, value_id, "20")
    api_update_value(ctx.call, item, value_id, "30")
    rows = audit_rows_of(ctx.db, "reference_value.update")
    assert [(r["details"]["value_from"], r["details"]["value_to"]) for r in rows] == [
        ("10", "20"),
        ("20", "30"),
    ]
    assert value_rows(ctx.db)[0]["number_value"] == Decimal("30")


@pytest.mark.parametrize("extra", [{"year": 2027}, {"item_id": 2}, {"year": 2026, "item_id": 1}])
def test_correction_body_with_year_or_item_id_is_read_only_422(ctx: Ctx, extra):
    item, value_id = seed_value(ctx)
    response = ctx.call(
        "admin", "PATCH", f"{ITEMS}/{item}/values/{value_id}", json={"value": "1", **extra}
    )
    assert (response.status_code, err(response)["code"]) == (422, "VALIDATION_ERROR")
    assert set(field_codes(response).values()) == {"READ_ONLY"}
    assert set(field_codes(response)) == set(extra)
    assert value_rows(ctx.db)[0]["number_value"] == Decimal("12.5")


@pytest.mark.parametrize(
    ("value", "code"),
    [("", "REQUIRED"), ("abc", "BAD_FORMAT"), ("NaN", "BAD_FORMAT"), ("1" * 39, "OUT_OF_RANGE")],
)
def test_correction_value_rule_errors_are_422(ctx: Ctx, value, code):
    item, value_id = seed_value(ctx)
    response = api_update_value(ctx.call, item, value_id, value)
    assert (response.status_code, field_codes(response)) == (422, {"value": code})
    assert value_rows(ctx.db)[0]["number_value"] == Decimal("12.5")
    assert audit_rows_of(ctx.db, "reference_value.update") == []


def test_correction_body_shape_errors(ctx: Ctx):
    item, value_id = seed_value(ctx)
    path = f"{ITEMS}/{item}/values/{value_id}"
    for body in ({}, {"value": 13}, {"value": None}, {"value": "1", "other": 1}):
        response = ctx.call("admin", "PATCH", path, json=body)
        assert (response.status_code, err(response)["code"]) == (422, "VALIDATION_ERROR"), body


def test_correction_404_cases_come_before_the_value_rule_and_the_same_value_shortcut(ctx: Ctx):
    item, value_id = seed_value(ctx)
    other_item = add_item(ctx.db, "다른 항목", ctx.uid("admin"))
    other_value = add_value(ctx.db, other_item, 2026, "7", ctx.uid("admin"))
    for path in (
        f"{ITEMS}/9999/values/{value_id}",  # 항목 없음
        f"{ITEMS}/{item}/values/9999",  # 값 없음
        f"{ITEMS}/{item}/values/{other_value}",  # 값이 그 항목 소속이 아님
        f"{ITEMS}/{other_item}/values/{value_id}",
    ):
        for value in ("abc", "12.5", "99"):
            response = ctx.call("admin", "PATCH", path, json={"value": value})
            assert (response.status_code, err(response)["code"]) == (404, "NOT_FOUND"), path
    assert {r["number_value"] for r in value_rows(ctx.db)} == {Decimal("12.5"), Decimal("7")}


def test_correction_of_a_used_year_changes_the_value_the_list_shows(ctx: Ctx):
    exact_digits(ctx)
    item, value_id = seed_value(ctx)
    api_update_value(ctx.call, item, value_id, "99.5")
    values = ctx.call("viewer", "GET", f"{ITEMS}/{item}/values").json()["items"]
    assert [(v["year"], v["value"]) for v in values] == [(2026, "99.5")]


# --- 감사 ----


def test_add_and_correction_each_record_exactly_one_row_with_the_allowed_keys(ctx: Ctx):
    exact_digits(ctx)
    item_response = api_add_item(ctx.call, "전기요금_A팀", "설명 텍스트")
    item = item_response.json()["id"]
    added = api_add_value(ctx.call, item, 2026, "12.50").json()
    api_update_value(ctx.call, item, added["id"], "13.00")
    create = audit_rows_of(ctx.db, "reference.create")
    add = audit_rows_of(ctx.db, "reference_value.add")
    update = audit_rows_of(ctx.db, "reference_value.update")
    assert (len(create), len(add), len(update)) == (1, 1, 1)
    assert len(audit_rows(ctx.db)) == 3
    for row in (*create, *add, *update):
        assert (row["target_type"], row["target_id"]) == ("reference", item)
        assert (row["actor_source"], row["actor_user_id"]) == ("user", ctx.uid("admin"))
    assert create[0]["details"] == {"target_name": "전기요금_A팀", "description_length": 6}
    assert add[0]["details"] == {"target_name": "전기요금_A팀", "year": 2026, "value": "12.50"}
    assert update[0]["details"] == {
        "target_name": "전기요금_A팀",
        "year": 2026,
        "value_from": "12.50",
        "value_to": "13.00",
    }
    assert "설명 텍스트" not in str([r["details"] for r in create])  # 설명 원문은 기록하지 않는다


def test_no_description_records_zero_length(ctx: Ctx):
    api_add_item(ctx.call, "x")
    assert audit_rows_of(ctx.db, "reference.create")[0]["details"]["description_length"] == 0


def test_audit_rows_roll_back_with_a_failed_commit_and_a_failed_audit_insert_rolls_back_the_change(
    ctx: Ctx, monkeypatch
):
    item = add_item(ctx.db, "x", ctx.uid("admin"))
    value_id = add_value(ctx.db, item, 2026, 1, ctx.uid("admin"))
    with failing_commit(monkeypatch):
        assert api_add_item(ctx.call, "새 항목").status_code == 500
        assert api_add_value(ctx.call, item, 2027, "1").status_code == 500
        assert api_update_value(ctx.call, item, value_id, "2").status_code == 500
    assert audit_rows(ctx.db) == [] and len(item_rows(ctx.db)) == 1 and len(value_rows(ctx.db)) == 1
    assert value_rows(ctx.db)[0]["number_value"] == Decimal("1")
    with failing_audit_insert(monkeypatch):
        assert api_add_item(ctx.call, "새 항목").status_code == 500
        assert api_add_value(ctx.call, item, 2027, "1").status_code == 500
        assert api_update_value(ctx.call, item, value_id, "2").status_code == 500
    assert audit_rows(ctx.db) == [] and len(item_rows(ctx.db)) == 1 and len(value_rows(ctx.db)) == 1
    assert value_rows(ctx.db)[0]["number_value"] == Decimal("1")  # 변경도 함께 롤백됐다


def test_reads_and_failed_requests_leave_no_audit_rows(ctx: Ctx):
    item, value_id = seed_value(ctx)
    ctx.call("viewer", "GET", ITEMS)
    ctx.call("viewer", "GET", f"{ITEMS}/{item}/values")
    ctx.call("admin", "GET", f"{ITEMS}/{item}/usage")
    api_add_value(ctx.call, item, 2026, "5")  # 409
    api_add_value(ctx.call, item, 1800, "5")  # 422
    api_update_value(ctx.call, item, value_id, "abc")  # 422
    api_update_value(ctx.call, item, 9999, "1")  # 404
    assert audit_rows(ctx.db) == []


def test_audit_log_api_filters_the_reference_history_of_one_item(ctx: Ctx):
    exact_digits(ctx)
    item = api_add_item(ctx.call, "전기요금").json()["id"]
    other = api_add_item(ctx.call, "수도요금").json()["id"]
    value_id = api_add_value(ctx.call, item, 2026, "1").json()["id"]
    api_update_value(ctx.call, item, value_id, "2")
    api_add_value(ctx.call, other, 2026, "9")
    body = ctx.call(
        "admin",
        "GET",
        "/api/audit-logs",
        params={"target_type": "reference", "target_id": item},
    ).json()
    assert [r["action"] for r in body["items"]] == [
        "reference_value.update",
        "reference_value.add",
        "reference.create",
    ]
    assert body["items"][0]["details"]["value_from"] == "1"
    only = ctx.call("admin", "GET", "/api/audit-logs", params={"action": "reference.create"})
    assert only.json()["total"] == 2


# --- 모듈 경계 ----

APP = Path(__file__).resolve().parent.parent / "app"


def _imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found |= {f"{node.module}.{alias.name}" for alias in node.names}
    return found


def test_reference_module_does_not_import_formula_dataset_entry_or_superset():
    """04 §2-2 층 규칙: `reference`는 core·auth·audit·db_metadata만 쓴다."""
    forbidden = ("app.formula", "app.dataset", "app.entry", "app.superset", "app.ddl")
    for path in (APP / "reference").glob("*.py"):
        bad = [m for m in _imports(path) if m.startswith(forbidden)]
        assert bad == [], (path.name, bad)


def test_reference_module_has_no_raw_sql():
    """SQL은 SQLAlchemy 표현식만: `text()`·`exec_driver_sql`·`delete()`가 없다(DELETE 권한 없음)."""
    for path in (APP / "reference").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", "") or getattr(node.func, "attr", "")
                assert name not in {"text", "delete", "exec_driver_sql"}, (path.name, name)


def test_write_lock_timeout_equals_the_row_write_lock_timeout():
    from app.dataset.definition import ROW_WRITE_LOCK_TIMEOUT

    assert service.WRITE_LOCK_TIMEOUT == ROW_WRITE_LOCK_TIMEOUT  # 06 §5: 행 쓰기와 같은 값


def test_service_write_functions_require_an_actor():
    """쓰기 service는 행위자(`CurrentUser`)를 필수로 받는다(감사 없는 쓰기 경로가 없다)."""
    import inspect

    for name in ("create_item", "add_value", "update_value"):
        assert "actor" in inspect.signature(getattr(service, name)).parameters
