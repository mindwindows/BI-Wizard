"""감사 `details`에 비밀값·행 값·수식 원문·규칙 값·로그인 ID가 없다는 단정(03b 29-2, 06 §2-1 ③).

실제 값을 일부러 심고(로그인 ID, 셀 값, 수식 상수, 규칙 값, 선택 목록 값, 대시보드 uuid 외의 문자열)
기록 대상 행위를 모두 일으킨 뒤 감사 행 전체를 직렬화해 심은 값이 하나도 없음을 확인한다.
SQLite와 실제 PostgreSQL 두 변형으로 돈다.
"""

from __future__ import annotations

import json
from typing import Any

import sqlalchemy as sa

from app.audit.actions import ACTIONS
from app.cli import main as cli_main
from app.db_metadata import dataset_columns
from tests.audit_helpers import Ctx, audit_rows
from tests.formula_api_helpers import add_column, add_formula, make_dataset, put_formula, version

LOGIN_SECRET = "login-leak-9931"
CELL_SECRETS = ("12345678", "23456789", "셀비밀값")
FORMULA_SECRETS = ("7919.5", "424242", "수식상수비밀")
RULE_SECRETS = ("9876543", "98765432", "옵션비밀1", "옵션비밀2", "규칙길이비밀")
ALL_SECRETS = (LOGIN_SECRET, *CELL_SECRETS, *FORMULA_SECRETS, *RULE_SECRETS)


def walk(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            yield "key", key
            yield from walk(child)
    elif isinstance(value, list | tuple):
        raise AssertionError(f"details에 배열이 있다: {value!r}")  # 스칼라와 changes만 허용
    else:
        yield "value", value


def run_workload(ctx: Ctx) -> None:
    call = ctx.call
    # 로그인 ID 비밀: 사용자 등록(user.create)과 그 사용자가 하는 변경
    assert (
        call(
            "admin",
            "POST",
            "/api/users",
            json={"login_id": LOGIN_SECRET, "display_name": "비밀 로그인 사용자", "is_admin": True},
        ).status_code
        == 201
    )
    call("admin", "PATCH", f"/api/teams/{ctx.world.team_a}", json={"name": "A팀 개명"})
    # 데이터셋·열(규칙 값 비밀)·수식(상수 비밀)·셀 값(비밀)
    dataset = make_dataset(call, ctx.world, "비밀 시험")
    ds = dataset["id"]
    sales = add_column(call, ds, "매출", "number", rules={"min": "9876543", "max": "98765432"})
    memo = add_column(call, ds, "메모", "text", rules={"max_length": 99})
    kind = add_column(call, ds, "구분", "choice", rules={"options": ["옵션비밀1", "옵션비밀2"]})
    call(
        "definer",
        "PATCH",
        f"/api/datasets/{ds}/columns/{memo['id']}",
        json={"expected_version": version(call, ds), "rules": {"max_length": 77}},
    )
    call(
        "definer",
        "PATCH",
        f"/api/datasets/{ds}/columns/{kind['id']}",
        json={"expected_version": version(call, ds), "rules": {"options": ["규칙길이비밀"]}},
    )
    call(
        "definer",
        "PATCH",
        f"/api/datasets/{ds}",
        json={"expected_version": version(call, ds), "name": "비밀 시험 개명"},
    )
    formula = add_formula(call, ds, "계산", "[매출] * 7919.5 + 424242")
    put_formula(call, ds, formula["id"], "[매출] * 7919.5 + 424242 + 1")
    cells = {str(sales["id"]): CELL_SECRETS[0], str(memo["id"]): CELL_SECRETS[2]}
    assert (
        call(
            "definer",
            "POST",
            f"/api/datasets/{ds}/rows",
            json={"expected_version": version(call, ds), "cells": cells},
        ).status_code
        == 201
    )
    call(
        "definer",
        "POST",
        f"/api/datasets/{ds}/rows/paste",
        json={
            "expected_version": version(call, ds),
            "column_ids": [sales["id"]],
            "rows": [{"row_id": None, "values": [CELL_SECRETS[1]]}],
        },
    )
    call("definer", "POST", f"/api/datasets/{ds}/formulas/preview", json={"expression": "[매출]"})
    call("definer", "POST", f"/api/datasets/{ds}/archive")  # FU-2b: 보관·복구도 비밀이 없다
    call("definer", "POST", f"/api/datasets/{ds}/restore")
    call(
        "admin",
        "PUT",
        f"/api/teams/{ctx.world.team_b}/members/{ctx.uid('viewer')}",
        json={"role": "entry"},
    )
    call("admin", "DELETE", f"/api/teams/{ctx.world.team_b}/members/{ctx.uid('viewer')}")
    dash = call(
        "admin",
        "POST",
        "/api/dashboards",
        json={
            "name": "비밀 없는 대시보드",
            "embedded_uuid": "abcdefab-cdef-abcd-efab-cdefabcdefab",
        },
    ).json()
    call("admin", "PATCH", f"/api/dashboards/{dash['id']}", json={"is_active": False})
    call("admin", "POST", f"/api/dashboards/{dash['id']}/guest-token")
    call("admin", "POST", "/api/teams", json={"code": "team_new", "name": "새 팀"})
    call("admin", "PATCH", f"/api/users/{ctx.uid('viewer')}", json={"display_name": "새 이름"})
    # 서버 명령도 로그인 ID를 남기지 않는다
    assert (
        cli_main(
            ["create-admin", "--login-id", LOGIN_SECRET + "-cli", "--display-name", "명령 관리자"],
            settings=ctx_settings(ctx),
            engine=ctx.db.engine,
        )
        == 0
    )


def ctx_settings(ctx: Ctx):
    from app.config import Settings

    return Settings()  # type: ignore[call-arg]


def test_no_secret_row_value_formula_rule_or_login_id_reaches_the_audit_log(ctx: Ctx):
    run_workload(ctx)
    rows = audit_rows(ctx.db)
    actions = {r["action"] for r in rows}
    # 이 작업이 17개 행위 모두 일으켰는지 확인한다(빈 검사가 되지 않게)
    assert actions == set(ACTIONS), set(ACTIONS) - actions
    text = json.dumps(rows, ensure_ascii=False, default=str)
    for secret in ALL_SECRETS:
        assert secret not in text, secret
    # 실제 셀·규칙 값이 DB 안에 있다는 것도 확인한다(심은 값이 정말 쓰였다)
    with ctx.db.writer.connect() as conn:
        stored = json.dumps(
            list(conn.execute(sa.select(dataset_columns.c.rules)).scalars()),
            ensure_ascii=False,
        )
    assert "9876543" in stored and "규칙길이비밀" in stored


def test_details_hold_only_allowed_keys_and_flat_scalars(ctx: Ctx):
    run_workload(ctx)
    for row in audit_rows(ctx.db):
        spec = ACTIONS[row["action"]]
        assert set(row["details"]) == set(spec.detail_keys), row["action"]
        for key, value in row["details"].items():
            if key == "changes":
                for field, pair in value.items():
                    assert set(pair) == {"from", "to"} and field in (spec.changes or {})
                    for scalar in pair.values():
                        assert scalar is None or isinstance(scalar, str | int | bool)
                continue
            assert value is None or isinstance(value, str | int | bool), (row["action"], key)
        for kind, value in walk(row["details"]):
            if kind == "key":
                lowered = str(value).lower()
                for forbidden in ("password", "token", "secret", "login", "expression", "rls"):
                    assert forbidden not in lowered, (row["action"], value)
            elif isinstance(value, str):
                assert len(value) <= 100


def test_every_name_in_details_is_a_display_name_or_code_not_a_login_id(ctx: Ctx):
    """target_name은 표시 이름이다: 사용자 행위는 login_id가 아니라 display_name이 남는다."""
    run_workload(ctx)
    created = [r for r in audit_rows(ctx.db) if r["action"] == "user.create"]
    assert [r["details"]["target_name"] for r in created] == ["비밀 로그인 사용자"]
    boot = [r for r in audit_rows(ctx.db) if r["action"] == "user.bootstrap_admin"]
    assert [r["details"]["target_name"] for r in boot] == ["명령 관리자"]
