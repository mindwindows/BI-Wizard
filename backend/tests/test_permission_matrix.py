"""권한 매트릭스 자동 시험(05 §4, 03b 3-6 BY4): 엔드포인트와 역할의 곱.
A1~A9, B1~B8, C1~C4, D1~D10, E1~E6, F1, R1~R6(FU-3), DV1~DV3.

역할: 관리자, 정의 담당자(A팀), 입력자(A팀), 다른 팀 구성원(B팀), 비소속 읽기, 비활성, 인증 없음.
- 읽기(reader): 인증된 활성 사용자 누구나(타 팀 포함).
- 관리자(admin): `users.is_admin`만.
- 정의(definer): **그 데이터셋 팀의 정의 담당자**만. 관리자라도 팀 소속 정의 담당자가 아니면 거부
  (06 §4-1)하므로 `admin`·`entry`·`other`·`viewer`는 모두 403이다.
- 입력(enter): **그 데이터셋 팀의 입력자 또는 정의 담당자**. 관리자도 그 팀 소속이 아니면 거부.
"""

import uuid
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.auth.guard import PUBLIC_PATHS
from app.db_metadata import (
    DYNAMIC_SCHEMA,
    audit_log,
    dataset_columns,
    datasets,
    formula_deps,
    formulas,
    reference_items,
    reference_values,
    superset_dashboards,
    superset_datasets,
    team_members,
    teams,
    users,
)
from app.main import create_app
from tests.api_helpers import World, make_caller
from tests.conftest import Db
from tests.reference_helpers import add_item, add_value

ROLES = ["admin", "definer", "entry", "other", "viewer", "inactive", None]
READERS = {"admin", "definer", "entry", "other", "viewer"}  # 인증된 활성 사용자

# 누가 성공하는가: 읽기 / 관리자 / 그 데이터셋 팀의 정의 담당자
READER, ADMIN, DEFINER, ENTER = "reader", "admin", "definer", "enter"


def allowed_roles(who: str) -> set[str]:
    return {
        READER: READERS,
        ADMIN: {"admin"},
        DEFINER: {"definer"},
        ENTER: {"definer", "entry"},
    }[who]


# 보관 상태 기대 결과(FU-2b, 05 §2-2): 데이터셋이 `archived`일 때 허용된 역할의 같은 요청이
# - REJECTED: 409 `DATASET_ARCHIVED`(정의·입력 쓰기 B4 B5 B6 C2 C3 C4 D4 D5, 버전 비교보다 앞)
# - SAME: 보관과 무관하게 평소와 같은 성공 코드(읽기·검사·미리보기·D10·E·A 전체, B7 B8, B2)
REJECTED, SAME = "rejected", "same"

# (ID, 메서드, 경로 템플릿, 경로 만들기, 본문 만들기, 성공 코드, 누가 성공, 보관 상태 기대 결과)
Endpoint = tuple[str, str, str, Callable[[World], str], Callable[[World], Any], int, str, str]
ENDPOINTS: list[Endpoint] = [
    ("A1", "GET", "/api/me", lambda w: "/api/me", lambda w: None, 200, READER, SAME),
    ("A2", "GET", "/api/teams", lambda w: "/api/teams", lambda w: None, 200, READER, SAME),
    (
        "A3",
        "POST",
        "/api/teams",
        lambda w: "/api/teams",
        lambda w: {"code": "new_team", "name": "새 팀"},
        201,
        ADMIN,
        SAME,
    ),
    (
        "A4",
        "PATCH",
        "/api/teams/{team_id}",
        lambda w: f"/api/teams/{w.team_b}",
        lambda w: {"name": "바뀐 B팀"},
        200,
        ADMIN,
        SAME,
    ),
    ("A5", "GET", "/api/users", lambda w: "/api/users", lambda w: None, 200, ADMIN, SAME),
    (
        "A6",
        "POST",
        "/api/users",
        lambda w: "/api/users",
        lambda w: {"login_id": "fresh", "display_name": "새 사용자"},
        201,
        ADMIN,
        SAME,
    ),
    (
        "A7",
        "PATCH",
        "/api/users/{user_id}",
        lambda w: f"/api/users/{w.ids['viewer']}",
        lambda w: {"display_name": "바뀐 이름"},
        200,
        ADMIN,
        SAME,
    ),
    (
        "A8",
        "PUT",
        "/api/teams/{team_id}/members/{user_id}",
        lambda w: f"/api/teams/{w.team_b}/members/{w.ids['viewer']}",
        lambda w: {"role": "entry"},
        200,
        ADMIN,
        SAME,
    ),
    (
        "A9",
        "DELETE",
        "/api/teams/{team_id}/members/{user_id}",
        lambda w: f"/api/teams/{w.team_a}/members/{w.ids['entry']}",
        lambda w: None,
        204,
        ADMIN,
        SAME,
    ),
    ("B1", "GET", "/api/datasets", lambda w: "/api/datasets", lambda w: None, 200, READER, SAME),
    (
        "B2",
        "POST",
        "/api/datasets",
        lambda w: "/api/datasets",
        lambda w: {"team_id": w.team_a, "name": "새 데이터셋", "date_unit": "month"},
        201,
        DEFINER,
        SAME,
    ),
    (
        "B3",
        "GET",
        "/api/datasets/{dataset_id}",
        lambda w: f"/api/datasets/{w.dataset_id}",
        lambda w: None,
        200,
        READER,
        SAME,
    ),
    (
        "B4",
        "PATCH",
        "/api/datasets/{dataset_id}",
        lambda w: f"/api/datasets/{w.dataset_id}",
        lambda w: {"expected_version": 1, "name": "바뀐 이름"},
        200,
        DEFINER,
        REJECTED,
    ),
    (
        "B5",
        "POST",
        "/api/datasets/{dataset_id}/columns",
        lambda w: f"/api/datasets/{w.dataset_id}/columns",
        lambda w: {"expected_version": 1, "display_name": "새 열", "type": "text"},
        201,
        DEFINER,
        REJECTED,
    ),
    (
        "B6",
        "PATCH",
        "/api/datasets/{dataset_id}/columns/{col_id}",
        lambda w: f"/api/datasets/{w.dataset_id}/columns/{w.column_id}",
        lambda w: {"expected_version": 1, "display_name": "바뀐 열"},
        200,
        DEFINER,
        REJECTED,
    ),
    (
        "B7",
        "POST",
        "/api/datasets/{dataset_id}/archive",
        lambda w: f"/api/datasets/{w.dataset_id}/archive",
        lambda w: None,
        200,
        DEFINER,
        SAME,  # 이미 보관이면 200(아무것도 바꾸지 않음)
    ),
    (
        "B8",
        "POST",
        "/api/datasets/{dataset_id}/restore",
        lambda w: f"/api/datasets/{w.dataset_id}/restore",
        lambda w: None,
        200,
        DEFINER,
        SAME,  # 보관 상태에서 복구하면 활성이 되어 200
    ),
    (
        "C1",
        "GET",
        "/api/datasets/{dataset_id}/rows",
        lambda w: f"/api/datasets/{w.dataset_id}/rows",
        lambda w: None,
        200,
        READER,
        SAME,
    ),
    (
        "C2",
        "POST",
        "/api/datasets/{dataset_id}/rows",
        lambda w: f"/api/datasets/{w.dataset_id}/rows",
        lambda w: {"expected_version": 1, "cells": {str(w.column_id): "5"}},
        201,
        ENTER,
        REJECTED,
    ),
    (
        "C3",
        "PATCH",
        "/api/datasets/{dataset_id}/rows/{row_id}",
        lambda w: f"/api/datasets/{w.dataset_id}/rows/{w.row_id}",
        lambda w: {
            "expected_version": 1,
            "changes": [{"column_id": w.column_id, "expected": None, "value": "7"}],
        },
        200,
        ENTER,
        REJECTED,
    ),
    (
        "C4",
        "POST",
        "/api/datasets/{dataset_id}/rows/paste",
        lambda w: f"/api/datasets/{w.dataset_id}/rows/paste",
        lambda w: {
            "expected_version": 1,
            "column_ids": [w.column_id],
            "rows": [{"row_id": None, "values": ["3"]}],
        },
        200,
        ENTER,
        REJECTED,
    ),
    (
        "D1",
        "GET",
        "/api/formulas/functions",
        lambda w: "/api/formulas/functions",
        lambda w: None,
        200,
        READER,
        SAME,
    ),
    (
        "D2",
        "POST",
        "/api/datasets/{dataset_id}/formulas/check",
        lambda w: f"/api/datasets/{w.dataset_id}/formulas/check",
        lambda w: {"expression": "[기존 열] + 1"},
        200,
        DEFINER,
        SAME,
    ),
    (
        "D3",
        "POST",
        "/api/datasets/{dataset_id}/formulas/preview",
        lambda w: f"/api/datasets/{w.dataset_id}/formulas/preview",
        lambda w: {"expression": "[기존 열] + 1"},
        200,
        DEFINER,
        SAME,
    ),
    (
        "D4",
        "POST",
        "/api/datasets/{dataset_id}/formulas",
        lambda w: f"/api/datasets/{w.dataset_id}/formulas",
        lambda w: {"expected_version": 1, "display_name": "새 계산", "expression": "[기존 열] * 2"},
        201,
        DEFINER,
        REJECTED,
    ),
    (
        "D5",
        "PUT",
        "/api/datasets/{dataset_id}/formulas/{col_id}",
        lambda w: f"/api/datasets/{w.dataset_id}/formulas/{w.formula_id}",
        lambda w: {"expected_version": 1, "expression": "[기존 열] + 2"},
        200,
        DEFINER,
        REJECTED,
    ),
    (
        "D6",
        "GET",
        "/api/datasets/{dataset_id}/formulas/{col_id}",
        lambda w: f"/api/datasets/{w.dataset_id}/formulas/{w.formula_id}",
        lambda w: None,
        200,
        READER,
        SAME,
    ),
    (
        "D7",
        "GET",
        "/api/checks/formula-errors",
        lambda w: "/api/checks/formula-errors",
        lambda w: None,
        200,
        READER,
        SAME,
    ),
    (
        "D8",
        "GET",
        "/api/datasets/{dataset_id}/formula-errors",
        lambda w: f"/api/datasets/{w.dataset_id}/formula-errors",
        lambda w: None,
        200,
        READER,
        SAME,
    ),
    (
        "D9",
        "GET",
        "/api/checks/views",
        lambda w: "/api/checks/views",
        lambda w: None,
        200,
        ADMIN,
        SAME,
    ),
    (
        "D10",
        "POST",
        "/api/checks/views/retry",
        lambda w: "/api/checks/views/retry",
        lambda w: {},
        200,
        ADMIN,
        SAME,
    ),
    (
        "E1",
        "GET",
        "/api/superset/datasets",
        lambda w: "/api/superset/datasets",
        lambda w: None,
        200,
        READER,
        SAME,
    ),
    (
        "E2",
        "POST",
        "/api/superset/sync",
        lambda w: "/api/superset/sync",
        lambda w: {"dataset_ids": [w.dataset_id]},
        202,
        ADMIN,
        SAME,
    ),
    (
        "E3",
        "GET",
        "/api/dashboards",
        lambda w: "/api/dashboards",
        lambda w: None,
        200,
        READER,
        SAME,
    ),
    (
        "E4",
        "POST",
        "/api/dashboards",
        lambda w: "/api/dashboards",
        lambda w: {"name": "새 대시보드", "embedded_uuid": "aaaaaaaa-1111-2222-3333-444444444444"},
        201,
        ADMIN,
        SAME,
    ),
    (
        "E5",
        "PATCH",
        "/api/dashboards/{dashboard_id}",
        lambda w: f"/api/dashboards/{w.dashboard_id}",
        lambda w: {"name": "바뀐 이름"},
        200,
        ADMIN,
        SAME,
    ),
    # 이 매트릭스의 앱에는 Superset 접속 설정이 없어 권한을 통과한 읽기 사용자는 503(연동 미설정)을
    # 받는다. 실제 발급 200과 속도 제한은 test_superset_api.py가 가짜 Superset으로 확인한다.
    (
        "E6",
        "POST",
        "/api/dashboards/{dashboard_id}/guest-token",
        lambda w: f"/api/dashboards/{w.dashboard_id}/guest-token",
        lambda w: None,
        503,
        READER,
        SAME,
    ),
    # F1(FU-2a): 감사 기록 조회는 관리자 전용이다(05 §4, 06 §4-1). 권한 검사가 쿼리 검증보다 먼저다.
    ("F1", "GET", "/api/audit-logs", lambda w: "/api/audit-logs", lambda w: None, 200, ADMIN, SAME),
    # R1~R6(FU-3, 05 §2-8): 기준값 읽기는 모두, 추가·정정·영향 조회(R6)는 관리자 전용이다.
    # 데이터셋과 무관하므로 보관 상태에서도 평소와 같다. 403이 본문 검증(422)보다 먼저다.
    (
        "R1",
        "GET",
        "/api/reference-items",
        lambda w: "/api/reference-items",
        lambda w: None,
        200,
        READER,
        SAME,
    ),
    (
        "R2",
        "POST",
        "/api/reference-items",
        lambda w: "/api/reference-items",
        lambda w: {"name": "새 항목", "description": "설명"},
        201,
        ADMIN,
        SAME,
    ),
    (
        "R3",
        "GET",
        "/api/reference-items/{item_id}/values",
        lambda w: f"/api/reference-items/{w.reference_item_id}/values",
        lambda w: None,
        200,
        READER,
        SAME,
    ),
    (
        "R4",
        "POST",
        "/api/reference-items/{item_id}/values",
        lambda w: f"/api/reference-items/{w.reference_item_id}/values",
        lambda w: {"year": 2030, "value": "1.5"},
        201,
        ADMIN,
        SAME,
    ),
    (
        "R5",
        "PATCH",
        "/api/reference-items/{item_id}/values/{value_id}",
        lambda w: f"/api/reference-items/{w.reference_item_id}/values/{w.reference_value_id}",
        lambda w: {"value": "99"},
        200,
        ADMIN,
        SAME,
    ),
    (
        "R6",
        "GET",
        "/api/reference-items/{item_id}/usage",
        lambda w: f"/api/reference-items/{w.reference_item_id}/usage",
        lambda w: None,
        200,
        ADMIN,
        SAME,
    ),
]


@pytest.fixture
def mworld(db: Db, world: World) -> World:
    """매트릭스용 세계: 기본 세계에 A팀 데이터셋(정의 버전 1)과 원본 열 하나를 더한다."""
    dataset_id = db.add_dataset(world.team_a, "기존 데이터셋", world.ids["definer"])
    column_id = db.add_column(dataset_id, "기존 열", "number")
    db.add_rows(dataset_id, 1)  # C3 대상 행 하나(row_id 1, 빈 칸)
    # D5·D6 대상 계산 열 하나(`[기존 열] + 1`을 저장된 AST로 직접 만든다. 뷰는 만들지 않는다).
    ast = {
        "t": "call",
        "n": "+",
        "a": [{"t": "col", "id": column_id}, {"t": "num", "v": "1"}],
    }
    formula_id = db.add_formula_column(
        dataset_id, "계산 열", ast, expression="[기존 열] + 1", position=1, deps=(column_id,)
    )
    reference_item_id = add_item(db, "기존 항목", world.ids["admin"])  # R3~R6 대상
    reference_value_id = add_value(db, reference_item_id, 2026, "12.5", world.ids["admin"])
    with db.writer.begin() as conn:  # E5·E6 대상: 연결된 대시보드 하나
        dashboard_id = conn.execute(
            sa.insert(superset_dashboards)
            .values(
                name="기존 대시보드",
                embedded_uuid=uuid.UUID("11111111-2222-3333-4444-555555555555"),
            )
            .returning(superset_dashboards.c.id)
        ).scalar_one()
    return replace(
        world,
        dataset_id=dataset_id,
        column_id=column_id,
        row_id=1,
        formula_id=formula_id,
        dashboard_id=dashboard_id,
        reference_item_id=reference_item_id,
        reference_value_id=reference_value_id,
    )


@pytest.mark.parametrize("role", ROLES, ids=lambda r: r or "anonymous")
@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=lambda e: e[0])
def test_endpoint_by_role(api, db: Db, mworld: World, endpoint: Endpoint, role):
    _, method, _template, make_path, make_body, success, who, _archived = endpoint
    body = make_body(mworld)
    response = api(role, method, make_path(mworld), **({"json": body} if body is not None else {}))
    if role is None:
        assert (response.status_code, response.json()["error"]["code"]) == (401, "UNAUTHENTICATED")
    elif role == "inactive":
        assert (response.status_code, response.json()["error"]["code"]) == (403, "USER_INACTIVE")
    elif role in allowed_roles(who):
        assert response.status_code == success, response.text
    else:
        assert (response.status_code, response.json()["error"]["code"]) == (403, "FORBIDDEN")


def archive_in_db(db: Db, dataset_id: int) -> None:
    """API를 거치지 않고 `status`만 보관으로 바꾼다(보관 상태의 다른 라우트 동작만 보려는 준비)."""
    with db.writer.begin() as conn:
        conn.execute(
            sa.update(datasets).where(datasets.c.id == dataset_id).values(status="archived")
        )


@pytest.mark.parametrize("role", ROLES, ids=lambda r: r or "anonymous")
@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=lambda e: e[0])
def test_endpoint_by_role_when_the_dataset_is_archived(api, db: Db, mworld: World, endpoint, role):
    """모든 쓰기 라우트 순회(FU-2b): 보관이면 B4 B5 B6 C2 C3 C4 D4 D5가 409 `DATASET_ARCHIVED`다.

    권한 판정(401·403)이 먼저라 허용되지 않은 역할은 보관 여부와 관계없이 평소와 같고, 허용된
    역할만 보관 상태 기대 결과를 받는다. 나머지 라우트는 보관과 무관하게 평소와 같다.
    """
    _, method, _template, make_path, make_body, success, who, archived = endpoint
    archive_in_db(db, mworld.dataset_id)
    body = make_body(mworld)
    kwargs = {"json": body} if body is not None else {}
    response = api(role, method, make_path(mworld), **kwargs)
    if role is None:
        assert (response.status_code, response.json()["error"]["code"]) == (401, "UNAUTHENTICATED")
    elif role == "inactive":
        assert (response.status_code, response.json()["error"]["code"]) == (403, "USER_INACTIVE")
    elif role not in allowed_roles(who):
        assert (response.status_code, response.json()["error"]["code"]) == (403, "FORBIDDEN")
    elif archived == REJECTED:
        error = response.json()["error"]
        assert (response.status_code, error["code"]) == (409, "DATASET_ARCHIVED"), response.text
        assert error["details"] == {"status": "archived"}
        # 버전이 틀려도 같은 코드다(보관 판정이 버전 비교보다 앞)
        assert isinstance(body, dict) and "expected_version" in body
        stale = api(role, method, make_path(mworld), json={**body, "expected_version": 99})
        assert (stale.status_code, stale.json()["error"]["code"]) == (409, "DATASET_ARCHIVED")
    else:
        assert response.status_code == success, response.text


def test_rejected_routes_change_nothing_while_archived(api, db: Db, mworld: World):
    """보관 중 거부된 쓰기는 응답만이 아니라 정말 아무것도 바꾸지 않았다(감사 기록 포함)."""
    archive_in_db(db, mworld.dataset_id)
    before = _snapshot(db)
    for _id, method, _t, make_path, make_body, _code, who, archived in ENDPOINTS:
        if archived != REJECTED:
            continue
        role = "entry" if who == ENTER else "definer"
        body = make_body(mworld)
        assert api(role, method, make_path(mworld), json=body).status_code == 409, _id
    assert _snapshot(db) == before


def _snapshot(db: Db):
    inspector = sa.inspect(db.engine)
    dynamic = {
        name: sorted(c["name"] for c in inspector.get_columns(name, schema=DYNAMIC_SCHEMA))
        for name in inspector.get_table_names(schema=DYNAMIC_SCHEMA)
    }
    return (
        db.rows(users, users.c.id),
        db.rows(teams, teams.c.id),
        db.rows(team_members),
        db.rows(datasets, datasets.c.id),
        db.rows(dataset_columns, dataset_columns.c.id),
        db.rows(formulas, formulas.c.column_id),
        db.rows(formula_deps, formula_deps.c.column_id, formula_deps.c.depends_on_column_id),
        db.rows(superset_datasets, superset_datasets.c.dataset_id),
        db.rows(superset_dashboards, superset_dashboards.c.id),
        db.rows(reference_items, reference_items.c.id),
        db.rows(reference_values, reference_values.c.id),
        db.rows(audit_log, audit_log.c.id),  # 거부된 요청은 감사 기록도 남기지 않는다
        dynamic,
    )


def test_denied_requests_do_not_change_data(api, db: Db, mworld: World):
    """403은 응답만이 아니라 실제로 아무것도 바뀌지 않았다는 뜻이어야 한다."""
    before = _snapshot(db)
    for _id, method, _template, make_path, make_body, _code, who, _archived in ENDPOINTS:
        if who == READER:
            continue
        body = make_body(mworld)
        humans = ("admin", "definer", "entry", "other", "viewer")
        for role in (*[r for r in humans if r not in allowed_roles(who)], "inactive", None):
            api(role, method, make_path(mworld), **({"json": body} if body is not None else {}))
    assert _snapshot(db) == before


def test_matrix_covers_every_protected_route(stub_settings, sqlite_engine):
    """앱의 모든 보호 경로가 매트릭스에 있다(새 엔드포인트를 더하면 이 시험이 알려 준다)."""
    app = create_app(stub_settings, engine=sqlite_engine)
    actual = {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
        if path not in PUBLIC_PATHS and not path.startswith("/api/dev/")
    }
    covered = {(method, template) for _id, method, template, *_ in ENDPOINTS}
    assert actual == covered, (actual - covered, covered - actual)


@pytest.mark.parametrize("role", ROLES, ids=lambda r: r or "anonymous")
def test_dev_endpoints_are_open_to_every_role_when_stub_on(api, world: World, role):
    """DV1~DV3은 신원을 고르기 전에 쓰므로 모든 역할(인증 없음 포함)에 열려 있다."""
    assert api(role, "GET", "/api/dev/stub-users").status_code == 200
    assert api(role, "PUT", "/api/dev/stub-user", json={"login_id": "viewer"}).status_code == 204
    assert api(role, "DELETE", "/api/dev/stub-user").status_code == 204


@pytest.mark.parametrize("role", ROLES, ids=lambda r: r or "anonymous")
def test_dev_endpoints_do_not_exist_when_stub_off(make_settings, db: Db, world: World, role):
    with TestClient(create_app(make_settings(), engine=db.engine)) as client:
        call = make_caller(client)
        assert call(role, "GET", "/api/dev/stub-users").status_code == 404
        assert (
            call(role, "PUT", "/api/dev/stub-user", json={"login_id": "viewer"}).status_code == 404
        )
        assert call(role, "DELETE", "/api/dev/stub-user").status_code == 404


def test_admin_flag_alone_grants_no_team_rights():
    """관리자는 팀 소속 역할이 없으면 정의·입력 권한이 없다(06 §4-1). 판정 함수 수준의 확인."""
    from app.auth import CurrentUser
    from app.auth.permissions import can_define, can_enter

    admin = CurrentUser(id=1, display_name="a", is_active=True, is_admin=True)
    assert not can_define(admin, 1) and not can_enter(admin, 1)


# B2는 팀 활성 여부를 권한 판정 뒤에 본다(03b 19-1 결정 1): 비활성 팀과 역할의 곱.
@pytest.mark.parametrize(
    ("role", "team_active", "expected"),
    [
        ("definer", True, 201),
        ("definer", False, 409),  # 정의 담당자라서 권한은 통과하고 팀 활성 확인에서 거부
        ("entry", False, 403),  # 권한 판정이 먼저
        ("admin", False, 403),
        ("other", False, 403),
        ("viewer", False, 403),
        ("inactive", False, 403),
        (None, False, 401),
    ],
)
def test_b2_matrix_with_team_activity(db: Db, stub_settings, role, team_active, expected):
    from tests.api_helpers import build_world

    world = build_world(db)
    team = world.team_a
    if not team_active:
        with db.writer.begin() as conn:
            conn.execute(sa.update(teams).where(teams.c.id == team).values(is_active=False))
    with TestClient(create_app(stub_settings, engine=db.engine)) as client:
        response = make_caller(client)(
            role,
            "POST",
            "/api/datasets",
            json={"team_id": team, "name": "새 데이터셋", "date_unit": "day"},
        )
    assert response.status_code == expected, response.text
    if expected == 409:
        assert response.json()["error"]["code"] == "TARGET_INACTIVE"
        assert response.json()["error"]["details"] == {"field": "team"}
