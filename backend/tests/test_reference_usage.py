"""정정 영향 조회 시험(05 §2-8 R6): `GET /reference-items/{id}/usage`.

저장된 수식 AST를 파이썬으로 훑어 `REF("이름")`을 쓰는 데이터셋(활성·보관 모두)을 이름순으로
돌려준다. 관리자 전용, 항목이 없으면 404, 쓰는 곳이 없으면 빈 목록, 200개에서 자른다.
SQLite·PostgreSQL 두 변형으로 돈다(AST를 직접 심어 수식 엔진 없이 조회 경로만 본다).
"""

from __future__ import annotations

import unicodedata
from typing import Any

import pytest

from app.formula import usage
from tests.audit_helpers import Ctx
from tests.reference_helpers import add_item


def ref_ast(name: str) -> dict[str, Any]:
    return {"t": "call", "n": "REF", "a": [{"t": "text", "v": name}]}


def times_two(inner: dict[str, Any]) -> dict[str, Any]:
    return {"t": "call", "n": "*", "a": [inner, {"t": "num", "v": "2"}]}


def make_dataset(ctx: Ctx, name: str, *formulas: tuple[str, dict[str, Any], str]) -> int:
    """데이터셋 하나와 계산 열(이름, AST, 보관용 원문)들을 직접 만든다."""
    dataset_id = ctx.db.add_dataset(ctx.world.team_a, name, ctx.uid("definer"))
    for index, (column_name, ast, expression) in enumerate(formulas):
        ctx.db.add_formula_column(
            dataset_id, column_name, ast, expression=expression, position=index
        )
    return dataset_id


def usage_of(ctx: Ctx, item: int, login: str = "admin"):
    return ctx.call(login, "GET", f"/api/reference-items/{item}/usage")


def test_lists_datasets_using_the_item_by_name_with_column_counts(ctx: Ctx):
    item = add_item(ctx.db, "전기요금", ctx.uid("admin"))
    other = add_item(ctx.db, "수도요금", ctx.uid("admin"))
    a = make_dataset(
        ctx,
        "나 데이터셋",
        ("요금 하나", ref_ast("전기요금"), 'REF("전기요금")'),
        ("요금 둘", times_two(ref_ast("전기요금")), 'REF("전기요금") * 2'),
        ("다른 항목", ref_ast("수도요금"), 'REF("수도요금")'),
    )
    b = make_dataset(ctx, "가 데이터셋", ("요금", ref_ast("전기요금"), 'REF("전기요금")'))
    make_dataset(ctx, "다 데이터셋", ("수도", ref_ast("수도요금"), 'REF("수도요금")'))
    make_dataset(ctx, "라 데이터셋")  # 수식이 없다
    response = usage_of(ctx, item)
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"items", "total", "truncated"}
    assert (body["total"], body["truncated"]) == (2, False)
    assert [i["dataset_id"] for i in body["items"]] == [b, a]  # 데이터셋 이름순(가, 나)
    first = body["items"][0]
    assert set(first) == {
        "dataset_id",
        "dataset_name",
        "team_id",
        "team_name",
        "status",
        "column_count",
    }
    assert (first["dataset_name"], first["team_id"], first["team_name"]) == (
        "가 데이터셋",
        ctx.world.team_a,
        "A팀",
    )
    assert [i["column_count"] for i in body["items"]] == [1, 2]
    assert [i["dataset_id"] for i in usage_of(ctx, other).json()["items"]] == [
        a,
        usage_id(ctx, "다 데이터셋"),
    ]


def usage_id(ctx: Ctx, name: str) -> int:
    from app.db_metadata import datasets

    rows = ctx.db.rows(datasets, datasets.c.id)
    return next(r["id"] for r in rows if r["name"] == name)


def test_archived_datasets_are_included_and_the_status_is_shown(ctx: Ctx):
    item = add_item(ctx.db, "전기요금", ctx.uid("admin"))
    active = make_dataset(ctx, "활성", ("요금", ref_ast("전기요금"), 'REF("전기요금")'))
    archived = make_dataset(ctx, "보관", ("요금", ref_ast("전기요금"), 'REF("전기요금")'))
    from sqlalchemy import update

    from app.db_metadata import datasets

    with ctx.db.writer.begin() as conn:
        conn.execute(update(datasets).where(datasets.c.id == archived).values(status="archived"))
    items = usage_of(ctx, item).json()["items"]
    assert {(i["dataset_id"], i["status"]) for i in items} == {
        (active, "active"),
        (archived, "archived"),
    }


def test_no_usage_gives_an_empty_list(ctx: Ctx):
    item = add_item(ctx.db, "전기요금", ctx.uid("admin"))
    assert usage_of(ctx, item).json() == {"items": [], "total": 0, "truncated": False}


def test_only_real_ref_calls_with_the_exact_name_count(ctx: Ctx):
    """원문에 REF가 든 행이어도 AST가 `REF("이름")` 호출이 아니면 세지 않는다."""
    item = add_item(ctx.db, "tariff", ctx.uid("admin"))
    make_dataset(
        ctx,
        "글자 상수",  # 원문에 REF가 들어 있지만 글자 상수일 뿐이다
        ("글자", {"t": "text", "v": "REF tariff"}, '"REF tariff"'),
    )
    make_dataset(
        ctx,
        "다른 이름",
        ("공백", ref_ast("tariff "), 'REF("tariff ")'),  # 공백이 다르면 다른 항목이다
        ("대소문자", ref_ast("Tariff"), 'REF("Tariff")'),  # 이름은 대소문자도 구별한다
    )
    make_dataset(ctx, "다른 함수", ("값", {"t": "call", "n": "ABS", "a": [ref_ast("수도")]}, "x"))
    real = make_dataset(ctx, "진짜", ("요금", times_two(times_two(ref_ast("tariff"))), "ref"))
    assert [i["dataset_id"] for i in usage_of(ctx, item).json()["items"]] == [real]


def test_a_broken_stored_formula_is_skipped_not_fatal(ctx: Ctx):
    item = add_item(ctx.db, "전기요금", ctx.uid("admin"))
    make_dataset(ctx, "깨진", ("요금", {"t": "call", "n": "REF"}, 'REF("전기요금")'))
    ok = make_dataset(ctx, "정상", ("요금", ref_ast("전기요금"), 'REF("전기요금")'))
    assert [i["dataset_id"] for i in usage_of(ctx, item).json()["items"]] == [ok]


def test_nfd_ast_value_matches_the_nfc_item(ctx: Ctx):
    item = add_item(ctx.db, "전기요금", ctx.uid("admin"))
    nfd = unicodedata.normalize("NFD", "전기요금")
    ds = make_dataset(ctx, "NFD", ("요금", ref_ast(nfd), "REF"))
    assert [i["dataset_id"] for i in usage_of(ctx, item).json()["items"]] == [ds]


def test_result_is_cut_at_the_limit_and_marked_truncated(ctx: Ctx, monkeypatch):
    item = add_item(ctx.db, "전기요금", ctx.uid("admin"))
    monkeypatch.setattr(usage, "USAGE_LIMIT", 3)
    for index in range(5):
        make_dataset(ctx, f"데이터셋 {index}", ("요금", ref_ast("전기요금"), 'REF("전기요금")'))
    body = usage_of(ctx, item).json()
    assert (len(body["items"]), body["total"], body["truncated"]) == (3, 5, True)


def test_usage_limit_constant_is_200():
    assert usage.USAGE_LIMIT == 200


def test_missing_item_is_404_and_only_admins_may_ask(ctx: Ctx):
    item = add_item(ctx.db, "전기요금", ctx.uid("admin"))
    response = usage_of(ctx, 9999)
    assert (response.status_code, response.json()["error"]["code"]) == (404, "NOT_FOUND")
    for login in ("definer", "entry", "other", "viewer"):
        denied = usage_of(ctx, item, login)
        assert (denied.status_code, denied.json()["error"]["code"]) == (403, "FORBIDDEN")
    assert usage_of(ctx, item, "inactive").status_code == 403
    assert usage_of(ctx, item, None).status_code == 401  # type: ignore[arg-type]
    assert pytest is not None
