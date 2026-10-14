"""감사 기록 훅 시험(04 §5-1 "시험 단정" 5가지): 행위 17개 각각에 대해

① 성공 = 감사 행 정확히 1건, `details` 키가 허용 목록과 같고 값이 기대와 같음
② 변경 없음 = 0건
③ 대표 오류 = 0건
④ 롤백(훅·DDL 실패 주입, 커밋 실패 주입) = 0건이고 변경도 없음
⑤ 감사 INSERT 실패 주입 = 변경도 롤백

SQLite와 실제 PostgreSQL(`pg`) 두 변형으로 돈다. API로 부르는 16개는 아래 시나리오 표가, 서버 명령
`create-admin`(`user.bootstrap_admin`)은 마지막 절이 맡는다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest
import sqlalchemy as sa

from app.audit.actions import ACTIONS
from app.cli import EXIT_DB, EXIT_INPUT, EXIT_OK
from app.cli import main as cli_main
from app.db_metadata import formulas
from tests.audit_helpers import (
    Ctx,
    audit_rows,
    failing_audit_insert,
    failing_commit,
    static_snapshot,
)
from tests.conftest import Db
from tests.formula_api_helpers import add_column, add_formula, make_dataset, put_formula, version

NEW_UUID = "aaaaaaaa-1111-2222-3333-444444444444"
DASHBOARD_UUID = "11111111-2222-3333-4444-555555555555"


def error_of(response) -> dict[str, Any]:
    return response.json()["error"]


# --- 시나리오 표 ----


@dataclass(frozen=True)
class Scenario:
    action: str
    actor: str  # 로그인 ID(= 역할 이름)
    setup: Callable[[Ctx], None]
    act: Callable[[Ctx], Any]  # 성공해야 하는 변경 요청
    expect: Callable[[Ctx, Any], tuple[int, str, dict[str, Any]]]  # (대상 번호, 대상 이름, details)
    error: Callable[[Ctx], tuple[Any, int, str]]  # (응답, 상태, 오류 코드)
    noop: Callable[[Ctx], Any] | None = None  # 바뀐 것이 없는 요청(2xx여야 한다)
    success_status: int = 200
    uses_hook: bool = False  # 정의 변경 진입점(훅·DDL)을 지나는가


def nothing(ctx: Ctx) -> None:
    return None


def setup_dataset(ctx: Ctx) -> None:
    """A팀 데이터셋 하나와 숫자 열 '매출' 하나(정의 담당자가 API로 만든다)."""
    dataset = make_dataset(ctx.call, ctx.world, "기존 데이터셋")
    column = add_column(ctx.call, dataset["id"], "매출", "number")
    ctx.vars.update(ds=dataset["id"], col=column["id"])


def setup_formula(ctx: Ctx) -> None:
    setup_dataset(ctx)
    column = add_formula(ctx.call, ctx.vars["ds"], "합계", "[매출] * 2")
    ctx.vars["calc"] = column["id"]


def stored_hash(ctx: Ctx, column_id: int) -> str:
    with ctx.db.writer.connect() as conn:
        return conn.execute(
            sa.select(formulas.c.ast_hash).where(formulas.c.column_id == column_id)
        ).scalar_one()


def ds_version(ctx: Ctx) -> int:
    return version(ctx.call, ctx.vars["ds"])


def setup_dashboard(ctx: Ctx) -> None:
    response = ctx.call(
        "admin", "POST", "/api/dashboards", json={"name": "월간", "embedded_uuid": DASHBOARD_UUID}
    )
    assert response.status_code == 201, response.text
    ctx.vars["dash"] = response.json()["id"]


# 1. dataset.create
def act_dataset_create(ctx: Ctx):
    return ctx.call(
        "definer",
        "POST",
        "/api/datasets",
        json={"team_id": ctx.world.team_a, "name": "새 데이터셋", "date_unit": "month"},
    )


def expect_dataset_create(ctx: Ctx, response):
    return (
        response.json()["id"],
        "새 데이터셋",
        {"team_id": ctx.world.team_a, "date_unit": "month", "def_version": 1},
    )


def error_dataset_create(ctx: Ctx):
    act_dataset_create(ctx)
    return act_dataset_create(ctx), 409, "ALREADY_EXISTS"


# 2. dataset.update
def act_dataset_update(ctx: Ctx):
    return ctx.call(
        "definer",
        "PATCH",
        f"/api/datasets/{ctx.vars['ds']}",
        json={"expected_version": ds_version(ctx), "name": "바뀐 이름"},
    )


def expect_dataset_update(ctx: Ctx, response):
    return (
        ctx.vars["ds"],
        "바뀐 이름",
        {
            "team_id": ctx.world.team_a,
            "changes": {"name": {"from": "기존 데이터셋", "to": "바뀐 이름"}},
            "def_version": response.json()["def_version"],
        },
    )


def noop_dataset_update(ctx: Ctx):
    return ctx.call(
        "definer",
        "PATCH",
        f"/api/datasets/{ctx.vars['ds']}",
        json={"expected_version": ds_version(ctx), "name": "기존 데이터셋"},
    )


def error_dataset_update(ctx: Ctx):
    response = ctx.call(
        "definer",
        "PATCH",
        f"/api/datasets/{ctx.vars['ds']}",
        json={"expected_version": ds_version(ctx) + 9, "name": "아무 이름"},
    )
    return response, 409, "DEFINITION_VERSION_MISMATCH"


# 2-1. dataset.archive (FU-2b: 정의 버전을 올리지 않으므로 details에 def_version이 없다)
def act_dataset_archive(ctx: Ctx):
    return ctx.call("definer", "POST", f"/api/datasets/{ctx.vars['ds']}/archive")


def expect_dataset_archive(ctx: Ctx, response):
    return ctx.vars["ds"], "기존 데이터셋", {"team_id": ctx.world.team_a}


def error_dataset_archive(ctx: Ctx):
    return ctx.call("definer", "POST", "/api/datasets/999999/archive"), 404, "NOT_FOUND"


# 2-2. dataset.restore
def setup_archived_dataset(ctx: Ctx) -> None:
    setup_dataset(ctx)
    assert act_dataset_archive(ctx).status_code == 200


def act_dataset_restore(ctx: Ctx):
    return ctx.call("definer", "POST", f"/api/datasets/{ctx.vars['ds']}/restore")


def error_dataset_restore(ctx: Ctx):
    return ctx.call("definer", "POST", "/api/datasets/999999/restore"), 404, "NOT_FOUND"


# 3. column.add
def act_column_add(ctx: Ctx):
    return ctx.call(
        "definer",
        "POST",
        f"/api/datasets/{ctx.vars['ds']}/columns",
        json={
            "expected_version": ds_version(ctx),
            "display_name": "비고",
            "type": "text",
            "required": True,
        },
    )


def expect_column_add(ctx: Ctx, response):
    return (
        ctx.vars["ds"],
        "기존 데이터셋",
        {
            "column_id": response.json()["column"]["id"],
            "column_name": "비고",
            "column_type": "text",
            "required": True,
            "def_version": response.json()["def_version"],
        },
    )


def error_column_add(ctx: Ctx):
    response = ctx.call(
        "definer",
        "POST",
        f"/api/datasets/{ctx.vars['ds']}/columns",
        json={"expected_version": ds_version(ctx), "display_name": "매출", "type": "number"},
    )
    return response, 409, "ALREADY_EXISTS"


# 4. column.update (검증 규칙 값은 details에 없다: rules_changed 불리언만)
RULES_MIN = "9876543"


def act_column_update(ctx: Ctx):
    return ctx.call(
        "definer",
        "PATCH",
        f"/api/datasets/{ctx.vars['ds']}/columns/{ctx.vars['col']}",
        json={
            "expected_version": ds_version(ctx),
            "display_name": "매출액",
            "required": True,
            "tag": "금액",
            "position": 3,
            "rules": {"min": RULES_MIN},
        },
    )


def expect_column_update(ctx: Ctx, response):
    return (
        ctx.vars["ds"],
        "기존 데이터셋",
        {
            "column_id": ctx.vars["col"],
            "column_name": "매출액",
            "changes": {
                "display_name": {"from": "매출", "to": "매출액"},
                "required": {"from": False, "to": True},
                "tag": {"from": None, "to": "금액"},
                "position": {"from": 0, "to": 3},
            },
            "rules_changed": True,
            "def_version": response.json()["def_version"],
        },
    )


def noop_column_update(ctx: Ctx):
    return ctx.call(
        "definer",
        "PATCH",
        f"/api/datasets/{ctx.vars['ds']}/columns/{ctx.vars['col']}",
        json={"expected_version": ds_version(ctx), "display_name": "매출", "required": False},
    )


def error_column_update(ctx: Ctx):
    response = ctx.call(
        "definer",
        "PATCH",
        f"/api/datasets/{ctx.vars['ds']}/columns/{ctx.vars['col']}",
        json={"expected_version": ds_version(ctx), "type": "text"},
    )
    return response, 422, "COLUMN_LOCKED"


# 5. formula_column.add (수식 원문은 details에 없다: 열 번호와 ast_hash만)
def act_formula_add(ctx: Ctx):
    return ctx.call(
        "definer",
        "POST",
        f"/api/datasets/{ctx.vars['ds']}/formulas",
        json={
            "expected_version": ds_version(ctx),
            "display_name": "합계",
            "expression": "[매출] * 2",
        },
    )


def expect_formula_add(ctx: Ctx, response):
    column_id = response.json()["column"]["id"]
    return (
        ctx.vars["ds"],
        "기존 데이터셋",
        {
            "column_id": column_id,
            "column_name": "합계",
            "result_type": "number",
            "ast_hash": stored_hash(ctx, column_id),
            "def_version": response.json()["def_version"],
        },
    )


def error_formula_add(ctx: Ctx):
    response = ctx.call(
        "definer",
        "POST",
        f"/api/datasets/{ctx.vars['ds']}/formulas",
        json={
            "expected_version": ds_version(ctx),
            "display_name": "나쁜 수식",
            "expression": "[없는 열] + 1",
        },
    )
    return response, 422, "FORMULA_INVALID"


# 6. formula_column.update
def act_formula_update(ctx: Ctx):
    ctx.vars["hash_from"] = stored_hash(ctx, ctx.vars["calc"])
    return put_formula(ctx.call, ctx.vars["ds"], ctx.vars["calc"], "[매출] + 1000")


def expect_formula_update(ctx: Ctx, response):
    return (
        ctx.vars["ds"],
        "기존 데이터셋",
        {
            "column_id": ctx.vars["calc"],
            "column_name": "합계",
            "result_type": "number",
            "result_type_changed": False,
            "ast_hash_from": ctx.vars["hash_from"],
            "ast_hash": stored_hash(ctx, ctx.vars["calc"]),
            "def_version": response.json()["def_version"],
        },
    )


def noop_formula_update(ctx: Ctx):
    return put_formula(ctx.call, ctx.vars["ds"], ctx.vars["calc"], "[매출] * 2")  # 같은 수식


def error_formula_update(ctx: Ctx):
    response = put_formula(ctx.call, ctx.vars["ds"], 999999, "[매출] + 1")
    return response, 404, "NOT_FOUND"


# 7. team.create
def act_team_create(ctx: Ctx):
    return ctx.call("admin", "POST", "/api/teams", json={"code": "team_c", "name": "C팀"})


def expect_team_create(ctx: Ctx, response):
    return response.json()["id"], "C팀", {"code": "team_c"}


def error_team_create(ctx: Ctx):
    response = ctx.call("admin", "POST", "/api/teams", json={"code": "team_a", "name": "다른 이름"})
    return response, 409, "ALREADY_EXISTS"


# 8. team.update (한 호출에서 여러 필드를 바꿔도 1건에 changes로 함께 담는다)
def act_team_update(ctx: Ctx):
    return ctx.call(
        "admin",
        "PATCH",
        f"/api/teams/{ctx.world.team_b}",
        json={"name": "바뀐 B팀", "is_active": False},
    )


def expect_team_update(ctx: Ctx, response):
    return (
        ctx.world.team_b,
        "바뀐 B팀",
        {
            "changes": {
                "name": {"from": "B팀", "to": "바뀐 B팀"},
                "is_active": {"from": True, "to": False},
            }
        },
    )


def noop_team_update(ctx: Ctx):
    return ctx.call(
        "admin",
        "PATCH",
        f"/api/teams/{ctx.world.team_b}",
        json={"name": "B팀", "is_active": True},  # 값이 같다
    )


def error_team_update(ctx: Ctx):
    response = ctx.call(
        "admin", "PATCH", f"/api/teams/{ctx.world.team_b}", json={"name": "A팀"}
    )  # 다른 팀과 같은 이름
    return response, 409, "ALREADY_EXISTS"


# 9. member.set (새 소속이면 role_from이 null)
def act_member_set(ctx: Ctx):
    return ctx.call(
        "admin",
        "PUT",
        f"/api/teams/{ctx.world.team_b}/members/{ctx.uid('viewer')}",
        json={"role": "entry"},
    )


def expect_member_set(ctx: Ctx, response):
    return (
        ctx.world.team_b,
        "B팀",
        {"user_id": ctx.uid("viewer"), "role": "entry", "role_from": None},
    )


def noop_member_set(ctx: Ctx):
    # 이미 B팀 입력자인 사용자에게 같은 역할
    return ctx.call(
        "admin",
        "PUT",
        f"/api/teams/{ctx.world.team_b}/members/{ctx.uid('other')}",
        json={"role": "entry"},
    )


def error_member_set(ctx: Ctx):
    response = ctx.call(
        "admin",
        "PUT",
        f"/api/teams/{ctx.world.team_b}/members/{ctx.uid('inactive')}",
        json={"role": "entry"},
    )
    return response, 409, "TARGET_INACTIVE"


# 10. member.remove
def act_member_remove(ctx: Ctx):
    return ctx.call("admin", "DELETE", f"/api/teams/{ctx.world.team_a}/members/{ctx.uid('entry')}")


def expect_member_remove(ctx: Ctx, response):
    return ctx.world.team_a, "A팀", {"user_id": ctx.uid("entry"), "role_from": "entry"}


def error_member_remove(ctx: Ctx):
    response = ctx.call(
        "admin", "DELETE", f"/api/teams/{ctx.world.team_b}/members/{ctx.uid('entry')}"
    )  # 그 팀 소속이 아니다
    return response, 404, "NOT_FOUND"


# 11. user.create (로그인 ID는 어디에도 남지 않는다)
SECRET_LOGIN = "login-must-not-leak-4417"


def act_user_create(ctx: Ctx):
    return ctx.call(
        "admin",
        "POST",
        "/api/users",
        json={"login_id": SECRET_LOGIN, "display_name": "새 사용자", "is_admin": False},
    )


def expect_user_create(ctx: Ctx, response):
    return response.json()["id"], "새 사용자", {"is_admin": False}


def error_user_create(ctx: Ctx):
    response = ctx.call(
        "admin", "POST", "/api/users", json={"login_id": "viewer", "display_name": "중복"}
    )
    return response, 409, "ALREADY_EXISTS"


# 12. user.update (표시 이름 값은 target_name에만, changes에는 불리언만)
def act_user_update(ctx: Ctx):
    return ctx.call(
        "admin",
        "PATCH",
        f"/api/users/{ctx.uid('viewer')}",
        json={"is_admin": True, "display_name": "바뀐 표시 이름"},
    )


def expect_user_update(ctx: Ctx, response):
    return (
        ctx.uid("viewer"),
        "바뀐 표시 이름",
        {
            "changes": {"is_admin": {"from": False, "to": True}},
            "display_name_changed": True,
        },
    )


def noop_user_update(ctx: Ctx):
    return ctx.call(
        "admin",
        "PATCH",
        f"/api/users/{ctx.uid('viewer')}",
        json={"display_name": "비소속 읽기", "is_admin": False, "is_active": True},
    )


def error_user_update(ctx: Ctx):
    response = ctx.call(
        "admin", "PATCH", f"/api/users/{ctx.uid('admin')}", json={"is_admin": False}
    )  # 마지막 활성 관리자
    return response, 409, "LAST_ADMIN"


# 14. dashboard.create
def act_dashboard_create(ctx: Ctx):
    return ctx.call(
        "admin", "POST", "/api/dashboards", json={"name": "월간 현황", "embedded_uuid": NEW_UUID}
    )


def expect_dashboard_create(ctx: Ctx, response):
    return response.json()["id"], "월간 현황", {"embedded_uuid": NEW_UUID}


def error_dashboard_create(ctx: Ctx):
    setup_dashboard(ctx)
    response = ctx.call(
        "admin", "POST", "/api/dashboards", json={"name": "중복", "embedded_uuid": DASHBOARD_UUID}
    )
    return response, 409, "ALREADY_EXISTS"


# 15. dashboard.update (is_active true -> false가 "연결 해제")
def act_dashboard_update(ctx: Ctx):
    return ctx.call(
        "admin",
        "PATCH",
        f"/api/dashboards/{ctx.vars['dash']}",
        json={"name": "새 이름", "is_active": False},
    )


def expect_dashboard_update(ctx: Ctx, response):
    return (
        ctx.vars["dash"],
        "새 이름",
        {
            "changes": {
                "name": {"from": "월간", "to": "새 이름"},
                "is_active": {"from": True, "to": False},
            }
        },
    )


def noop_dashboard_update(ctx: Ctx):
    return ctx.call(
        "admin",
        "PATCH",
        f"/api/dashboards/{ctx.vars['dash']}",
        json={"name": "월간", "is_active": True},
    )


def error_dashboard_update(ctx: Ctx):
    response = ctx.call("admin", "PATCH", "/api/dashboards/999999", json={"name": "없는 대상"})
    return response, 404, "NOT_FOUND"


SCENARIOS = [
    Scenario(
        "dataset.create",
        "definer",
        nothing,
        act_dataset_create,
        expect_dataset_create,
        error_dataset_create,
        success_status=201,
        uses_hook=True,
    ),
    Scenario(
        "dataset.update",
        "definer",
        setup_dataset,
        act_dataset_update,
        expect_dataset_update,
        error_dataset_update,
        noop=noop_dataset_update,
        uses_hook=True,
    ),
    Scenario(
        "dataset.archive",
        "definer",
        setup_dataset,
        act_dataset_archive,
        expect_dataset_archive,
        error_dataset_archive,
    ),
    Scenario(
        "dataset.restore",
        "definer",
        setup_archived_dataset,
        act_dataset_restore,
        expect_dataset_archive,
        error_dataset_restore,
    ),
    Scenario(
        "column.add",
        "definer",
        setup_dataset,
        act_column_add,
        expect_column_add,
        error_column_add,
        success_status=201,
        uses_hook=True,
    ),
    Scenario(
        "column.update",
        "definer",
        setup_dataset,
        act_column_update,
        expect_column_update,
        error_column_update,
        noop=noop_column_update,
        uses_hook=True,
    ),
    Scenario(
        "formula_column.add",
        "definer",
        setup_dataset,
        act_formula_add,
        expect_formula_add,
        error_formula_add,
        success_status=201,
        uses_hook=True,
    ),
    Scenario(
        "formula_column.update",
        "definer",
        setup_formula,
        act_formula_update,
        expect_formula_update,
        error_formula_update,
        noop=noop_formula_update,
        uses_hook=True,
    ),
    Scenario(
        "team.create",
        "admin",
        nothing,
        act_team_create,
        expect_team_create,
        error_team_create,
        success_status=201,
    ),
    Scenario(
        "team.update",
        "admin",
        nothing,
        act_team_update,
        expect_team_update,
        error_team_update,
        noop=noop_team_update,
    ),
    Scenario(
        "member.set",
        "admin",
        nothing,
        act_member_set,
        expect_member_set,
        error_member_set,
        noop=noop_member_set,
    ),
    Scenario(
        "member.remove",
        "admin",
        nothing,
        act_member_remove,
        expect_member_remove,
        error_member_remove,
        success_status=204,
    ),
    Scenario(
        "user.create",
        "admin",
        nothing,
        act_user_create,
        expect_user_create,
        error_user_create,
        success_status=201,
    ),
    Scenario(
        "user.update",
        "admin",
        nothing,
        act_user_update,
        expect_user_update,
        error_user_update,
        noop=noop_user_update,
    ),
    Scenario(
        "dashboard.create",
        "admin",
        nothing,
        act_dashboard_create,
        expect_dashboard_create,
        error_dashboard_create,
        success_status=201,
    ),
    Scenario(
        "dashboard.update",
        "admin",
        setup_dashboard,
        act_dashboard_update,
        expect_dashboard_update,
        error_dashboard_update,
        noop=noop_dashboard_update,
    ),
]
BY_ACTION = {s.action: s for s in SCENARIOS}
ids = [s.action for s in SCENARIOS]
scenarios = pytest.mark.parametrize("scn", SCENARIOS, ids=ids)


def test_scenario_table_covers_every_api_action_except_the_server_command():
    """17개 중 서버 명령(`user.bootstrap_admin`)만 아래 CLI 절이 맡고 나머지 16개는 이 표에 있다."""
    assert set(BY_ACTION) == set(ACTIONS) - {"user.bootstrap_admin"}
    assert len(ACTIONS) == 17


# --- ① 성공: 정확히 1건 ----


@scenarios
def test_success_records_exactly_one_row_with_the_allowed_keys(ctx: Ctx, scn: Scenario):
    scn.setup(ctx)
    before = audit_rows(ctx.db)
    response = scn.act(ctx)
    assert response.status_code == scn.success_status, response.text
    after = audit_rows(ctx.db)
    assert after[: len(before)] == before  # 기존 행은 그대로(추가 전용)
    [row] = after[len(before) :]  # 정확히 1건
    target_id, target_name, details = scn.expect(ctx, response)
    spec = ACTIONS[scn.action]
    assert row["action"] == scn.action
    assert (row["target_type"], row["target_id"]) == (spec.target_type, target_id)
    assert (row["actor_source"], row["actor_user_id"]) == ("user", ctx.uid(scn.actor))
    assert row["occurred_at"] is not None
    # details 키는 허용 목록과 정확히 같고(target_name 포함) 값은 기대와 같다
    assert set(row["details"]) == set(spec.detail_keys)
    assert row["details"] == {"target_name": target_name, **details}


# --- ② 변경 없음: 0건 ----


@pytest.mark.parametrize(
    "scn", [s for s in SCENARIOS if s.noop], ids=[s.action for s in SCENARIOS if s.noop]
)
def test_unchanged_request_records_nothing(ctx: Ctx, scn: Scenario):
    scn.setup(ctx)
    before_audit, before_state = audit_rows(ctx.db), static_snapshot(ctx.db)
    response = scn.noop(ctx)  # type: ignore[misc]
    assert response.status_code == 200, response.text
    assert audit_rows(ctx.db) == before_audit
    assert static_snapshot(ctx.db) == before_state


# --- ③ 대표 오류: 0건 ----


@scenarios
def test_representative_error_records_nothing(ctx: Ctx, scn: Scenario):
    scn.setup(ctx)
    before_audit = audit_rows(ctx.db)
    response, status, code = scn.error(ctx)
    assert response.status_code == status, response.text
    assert error_of(response)["code"] == code
    # error()가 먼저 성공 요청을 한 번 하는 시나리오(중복 만들기)는 그 1건만 늘었다
    new = audit_rows(ctx.db)[len(before_audit) :]
    assert all(r["action"] == scn.action for r in new) and len(new) <= 1


@scenarios
def test_unauthorized_caller_records_nothing(ctx: Ctx, scn: Scenario):
    """권한이 없는 호출자의 같은 요청은 403이고 감사 행도 없다."""
    scn.setup(ctx)
    before = audit_rows(ctx.db)
    # 비활성 사용자는 어느 행위에서든 모든 요청이 거부된다(USER_INACTIVE).
    original = ctx.call

    def as_inactive(login, method, path, **kw):
        # 읽기(GET)는 준비용이라 그대로 두고, 변경 요청만 비활성 사용자로 보낸다.
        return original(login if method == "GET" else "inactive", method, path, **kw)

    ctx.call = as_inactive
    try:
        response = scn.act(ctx)
    finally:
        ctx.call = original
    assert response.status_code == 403
    assert audit_rows(ctx.db) == before


# --- ④ 롤백: 커밋 실패·훅 실패를 주입하면 0건이고 변경도 없다 ----


@scenarios
def test_commit_failure_rolls_back_the_change_and_the_audit_row(
    ctx: Ctx, scn: Scenario, monkeypatch
):
    scn.setup(ctx)
    before_audit, before_state = audit_rows(ctx.db), static_snapshot(ctx.db)
    with failing_commit(monkeypatch):
        response = scn.act(ctx)
    assert response.status_code == 500, response.text
    assert error_of(response)["code"] == "INTERNAL_ERROR"
    assert audit_rows(ctx.db) == before_audit
    assert static_snapshot(ctx.db) == before_state
    # 주입을 풀고 같은 요청을 하면 성공하고 정확히 1건이다(요청 자체가 잘못된 것이 아니었다)
    response = scn.act(ctx)
    assert response.status_code == scn.success_status, response.text
    assert len(audit_rows(ctx.db)) == len(before_audit) + 1


@pytest.mark.parametrize(
    "scn", [s for s in SCENARIOS if s.uses_hook], ids=[s.action for s in SCENARIOS if s.uses_hook]
)
def test_definition_hook_failure_rolls_back_the_change_and_the_audit_row(ctx: Ctx, scn: Scenario):
    """정의 변경 훅(뷰·DDL을 만드는 자리)이 실패하면 열·원본 표·감사 행이 모두 되돌려진다."""
    scn.setup(ctx)
    before_audit, before_state = audit_rows(ctx.db), static_snapshot(ctx.db)
    ctx.boom_armed["on"] = True
    response = scn.act(ctx)
    ctx.boom_armed["on"] = False
    assert response.status_code == 500, response.text
    assert audit_rows(ctx.db) == before_audit
    assert static_snapshot(ctx.db) == before_state
    response = scn.act(ctx)
    assert response.status_code == scn.success_status, response.text
    assert len(audit_rows(ctx.db)) == len(before_audit) + 1


# --- ⑤ 감사 INSERT 실패: 변경도 롤백 ----


@scenarios
def test_audit_insert_failure_rolls_back_the_change_too(ctx: Ctx, scn: Scenario, monkeypatch):
    scn.setup(ctx)
    before_audit, before_state = audit_rows(ctx.db), static_snapshot(ctx.db)
    with failing_audit_insert(monkeypatch):
        response = scn.act(ctx)
    assert response.status_code == 500, response.text
    assert audit_rows(ctx.db) == before_audit
    assert static_snapshot(ctx.db) == before_state  # 감사 없는 변경은 없다


# --- 호출당 1건: 여러 필드·여러 표를 건드려도 1건 ----


def test_a_call_that_changes_many_fields_and_tables_records_one_row(ctx: Ctx):
    """D4는 열 INSERT·수식·의존·뷰 재생성·def_hash를 한 트랜잭션에서 하지만 감사는 1건."""
    setup_dataset(ctx)
    before = audit_rows(ctx.db)
    response = act_formula_add(ctx)
    assert response.status_code == 201
    new = audit_rows(ctx.db)[len(before) :]
    assert [r["action"] for r in new] == ["formula_column.add"]
    # A4: 이름과 활성을 함께 바꿔도 1건(changes에 둘 다)
    before = audit_rows(ctx.db)
    act_team_update(ctx)
    new = audit_rows(ctx.db)[len(before) :]
    assert len(new) == 1 and set(new[0]["details"]["changes"]) == {"name", "is_active"}


def test_definition_change_inside_hooks_records_nothing_on_its_own(ctx: Ctx):
    """formula 훅 안의 결과 형·태그 갱신 같은 내부 호출은 따로 기록하지 않는다(D5도 1건)."""
    setup_formula(ctx)
    before = audit_rows(ctx.db)
    # 결과 형이 number -> text로 바뀌는 수식(&는 글자 연결)
    response = put_formula(ctx.call, ctx.vars["ds"], ctx.vars["calc"], '"값: " & "가"')
    assert response.status_code == 200, response.text
    assert response.json()["result_type_changed"] is True
    [row] = audit_rows(ctx.db)[len(before) :]
    assert row["action"] == "formula_column.update"
    assert row["details"]["result_type"] == "text"
    assert row["details"]["result_type_changed"] is True


def test_archive_and_restore_repeats_record_nothing(ctx: Ctx):
    """B7·B8: 이미 같은 상태인 재요청은 200이고 감사 0건·상태 불변이다(04 §5-1 2번)."""
    setup_dataset(ctx)
    ds = ctx.vars["ds"]
    before = audit_rows(ctx.db)
    # 활성에서 복구 = 같은 상태
    assert ctx.call("definer", "POST", f"/api/datasets/{ds}/restore").status_code == 200
    assert audit_rows(ctx.db) == before
    assert ctx.call("definer", "POST", f"/api/datasets/{ds}/archive").status_code == 200
    after_archive = audit_rows(ctx.db)
    assert [r["action"] for r in after_archive[len(before) :]] == ["dataset.archive"]
    state = static_snapshot(ctx.db)
    again = ctx.call("definer", "POST", f"/api/datasets/{ds}/archive")
    assert again.status_code == 200 and again.json()["status"] == "archived"
    assert audit_rows(ctx.db) == after_archive and static_snapshot(ctx.db) == state
    assert ctx.call("definer", "POST", f"/api/datasets/{ds}/restore").status_code == 200
    rows = audit_rows(ctx.db)[len(before) :]
    assert [r["action"] for r in rows] == ["dataset.archive", "dataset.restore"]


def test_member_set_role_change_records_the_previous_role(ctx: Ctx):
    """A8: 역할 변경이면 role_from이 이전 역할이고, 같은 역할 재요청은 0건이다."""
    path = f"/api/teams/{ctx.world.team_a}/members/{ctx.uid('entry')}"
    before = audit_rows(ctx.db)
    assert ctx.call("admin", "PUT", path, json={"role": "definer"}).status_code == 200
    assert ctx.call("admin", "PUT", path, json={"role": "definer"}).status_code == 200
    assert ctx.call("admin", "PUT", path, json={"role": "entry"}).status_code == 200
    rows = audit_rows(ctx.db)[len(before) :]
    assert [(r["details"]["role_from"], r["details"]["role"]) for r in rows] == [
        ("entry", "definer"),
        ("definer", "entry"),
    ]


def test_empty_body_patch_records_nothing(ctx: Ctx):
    """A4·A7의 빈 본문 PATCH는 200이고 감사 행이 없다."""
    before = audit_rows(ctx.db)
    assert ctx.call("admin", "PATCH", f"/api/teams/{ctx.world.team_a}", json={}).status_code == 200
    assert ctx.call("admin", "PATCH", f"/api/users/{ctx.uid('viewer')}", json={}).status_code == 200
    assert audit_rows(ctx.db) == before


def test_user_update_with_only_a_display_name_change_keeps_the_name_out_of_changes(ctx: Ctx):
    before = audit_rows(ctx.db)
    response = ctx.call(
        "admin", "PATCH", f"/api/users/{ctx.uid('viewer')}", json={"display_name": "이름만 바뀜"}
    )
    assert response.status_code == 200
    [row] = audit_rows(ctx.db)[len(before) :]
    assert row["details"] == {
        "target_name": "이름만 바뀜",
        "changes": {},
        "display_name_changed": True,
    }


def test_dashboard_unlink_and_relink_are_recorded_as_is_active_changes(ctx: Ctx):
    setup_dashboard(ctx)
    path = f"/api/dashboards/{ctx.vars['dash']}"
    before = audit_rows(ctx.db)
    ctx.call("admin", "PATCH", path, json={"is_active": False})
    ctx.call("admin", "PATCH", path, json={"is_active": True})
    rows = audit_rows(ctx.db)[len(before) :]
    assert [r["details"]["changes"] for r in rows] == [
        {"is_active": {"from": True, "to": False}},
        {"is_active": {"from": False, "to": True}},
    ]


def test_events_that_are_not_recorded_leave_no_audit_row(ctx: Ctx):
    """기록하지 않기로 한 것(04 §5-1): 조회, 행 값 입력, 입장권 발급, 동기화 접수, 시험용 시드."""
    setup_dashboard(ctx)
    setup_dataset(ctx)
    before = audit_rows(ctx.db)
    ds = ctx.vars["ds"]
    for login, method, path, body in (
        ("admin", "GET", "/api/users", None),
        ("viewer", "GET", f"/api/datasets/{ds}", None),
        ("viewer", "GET", f"/api/datasets/{ds}/rows", None),
        ("admin", "GET", "/api/dashboards", None),
        ("admin", "POST", "/api/superset/sync", {"dataset_ids": [ds]}),
        ("viewer", "POST", f"/api/dashboards/{ctx.vars['dash']}/guest-token", None),
        (
            "definer",
            "POST",
            f"/api/datasets/{ds}/rows",
            {"expected_version": ds_version(ctx), "cells": {str(ctx.vars["col"]): "5"}},
        ),
        ("definer", "POST", f"/api/datasets/{ds}/formulas/check", {"expression": "[매출] + 1"}),
    ):
        kwargs = {"json": body} if body is not None else {}
        response = ctx.call(login, method, path, **kwargs)
        assert response.status_code != 500, (path, response.text)
    assert audit_rows(ctx.db) == before


# --- 서버 명령 create-admin (user.bootstrap_admin) ----


def run_admin(db: Db, settings, login="boss", name="총괄 관리자") -> int:
    return cli_main(
        ["create-admin", "--login-id", login, "--display-name", name],
        settings=settings,
        engine=db.engine,
    )


def test_cli_create_admin_records_one_row_with_no_actor(db: Db, make_settings):
    settings = make_settings()
    assert run_admin(db, settings) == EXIT_OK
    [row] = audit_rows(db)
    user = db.rows(sa.table("users", sa.column("id"), sa.column("login_id")))[0]
    assert row["action"] == "user.bootstrap_admin"
    assert (row["actor_source"], row["actor_user_id"]) == ("cli", None)  # 행위자를 비운다
    assert (row["target_type"], row["target_id"]) == ("user", user["id"])
    assert row["details"] == {"target_name": "총괄 관리자", "is_admin": True}
    assert set(row["details"]) == set(ACTIONS["user.bootstrap_admin"].detail_keys)
    assert "boss" not in str(row["details"])  # 로그인 ID는 남지 않는다


def test_cli_create_admin_is_idempotent_and_records_only_the_real_transition(db: Db, make_settings):
    settings = make_settings()
    assert run_admin(db, settings) == EXIT_OK
    assert run_admin(db, settings, name="다른 이름") == EXIT_OK  # 이미 활성 관리자: 변경 없음
    assert len(audit_rows(db)) == 1


def test_cli_create_admin_refusal_records_nothing(db: Db, make_settings):
    db.add_user("boss", "기존", is_admin=False)
    assert run_admin(db, make_settings()) == EXIT_INPUT
    assert audit_rows(db) == []


def test_cli_commit_failure_rolls_back_the_user_and_the_audit_row(
    db: Db, make_settings, monkeypatch
):
    before = static_snapshot(db)
    with failing_commit(monkeypatch):
        assert run_admin(db, make_settings()) == EXIT_DB
    assert audit_rows(db) == [] and static_snapshot(db) == before
    assert run_admin(db, make_settings()) == EXIT_OK
    assert len(audit_rows(db)) == 1


def test_cli_audit_insert_failure_rolls_back_the_user(db: Db, make_settings, monkeypatch):
    before = static_snapshot(db)
    with failing_audit_insert(monkeypatch):
        assert run_admin(db, make_settings()) == EXIT_DB
    assert audit_rows(db) == [] and static_snapshot(db) == before


def test_seed_stub_users_is_not_recorded(db: Db, stub_settings):
    assert cli_main(["seed-stub-users"], settings=stub_settings, engine=db.engine) == EXIT_OK
    assert audit_rows(db) == []
    assert len(db.rows(sa.table("users", sa.column("id")))) == 6
