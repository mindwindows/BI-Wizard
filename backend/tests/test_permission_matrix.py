"""권한 매트릭스 자동 시험(05 §4, 03b 3-6 BY4): 엔드포인트와 역할의 곱.
A1~A9, B1~B6, C1~C4, DV1~DV3.

역할: 관리자, 정의 담당자(A팀), 입력자(A팀), 다른 팀 구성원(B팀), 비소속 읽기, 비활성, 인증 없음.
- 읽기(reader): 인증된 활성 사용자 누구나(타 팀 포함).
- 관리자(admin): `users.is_admin`만.
- 정의(definer): **그 데이터셋 팀의 정의 담당자**만. 관리자라도 팀 소속 정의 담당자가 아니면 거부
  (06 §4-1)하므로 `admin`·`entry`·`other`·`viewer`는 모두 403이다.
- 입력(enter): **그 데이터셋 팀의 입력자 또는 정의 담당자**. 관리자도 그 팀 소속이 아니면 거부.
"""

from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.auth.guard import PUBLIC_PATHS
from app.db_metadata import (
    DYNAMIC_SCHEMA,
    dataset_columns,
    datasets,
    team_members,
    teams,
    users,
)
from app.main import create_app
from tests.api_helpers import World, make_caller
from tests.conftest import Db

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


# (ID, 메서드, 경로 템플릿, 경로 만들기, 본문 만들기, 성공 코드, 누가 성공하는가)
Endpoint = tuple[str, str, str, Callable[[World], str], Callable[[World], Any], int, str]
ENDPOINTS: list[Endpoint] = [
    ("A1", "GET", "/api/me", lambda w: "/api/me", lambda w: None, 200, READER),
    ("A2", "GET", "/api/teams", lambda w: "/api/teams", lambda w: None, 200, READER),
    (
        "A3",
        "POST",
        "/api/teams",
        lambda w: "/api/teams",
        lambda w: {"code": "new_team", "name": "새 팀"},
        201,
        ADMIN,
    ),
    (
        "A4",
        "PATCH",
        "/api/teams/{team_id}",
        lambda w: f"/api/teams/{w.team_b}",
        lambda w: {"name": "바뀐 B팀"},
        200,
        ADMIN,
    ),
    ("A5", "GET", "/api/users", lambda w: "/api/users", lambda w: None, 200, ADMIN),
    (
        "A6",
        "POST",
        "/api/users",
        lambda w: "/api/users",
        lambda w: {"login_id": "fresh", "display_name": "새 사용자"},
        201,
        ADMIN,
    ),
    (
        "A7",
        "PATCH",
        "/api/users/{user_id}",
        lambda w: f"/api/users/{w.ids['viewer']}",
        lambda w: {"display_name": "바뀐 이름"},
        200,
        ADMIN,
    ),
    (
        "A8",
        "PUT",
        "/api/teams/{team_id}/members/{user_id}",
        lambda w: f"/api/teams/{w.team_b}/members/{w.ids['viewer']}",
        lambda w: {"role": "entry"},
        200,
        ADMIN,
    ),
    (
        "A9",
        "DELETE",
        "/api/teams/{team_id}/members/{user_id}",
        lambda w: f"/api/teams/{w.team_a}/members/{w.ids['entry']}",
        lambda w: None,
        204,
        ADMIN,
    ),
    ("B1", "GET", "/api/datasets", lambda w: "/api/datasets", lambda w: None, 200, READER),
    (
        "B2",
        "POST",
        "/api/datasets",
        lambda w: "/api/datasets",
        lambda w: {"team_id": w.team_a, "name": "새 데이터셋", "date_unit": "month"},
        201,
        DEFINER,
    ),
    (
        "B3",
        "GET",
        "/api/datasets/{dataset_id}",
        lambda w: f"/api/datasets/{w.dataset_id}",
        lambda w: None,
        200,
        READER,
    ),
    (
        "B4",
        "PATCH",
        "/api/datasets/{dataset_id}",
        lambda w: f"/api/datasets/{w.dataset_id}",
        lambda w: {"expected_version": 1, "name": "바뀐 이름"},
        200,
        DEFINER,
    ),
    (
        "B5",
        "POST",
        "/api/datasets/{dataset_id}/columns",
        lambda w: f"/api/datasets/{w.dataset_id}/columns",
        lambda w: {"expected_version": 1, "display_name": "새 열", "type": "text"},
        201,
        DEFINER,
    ),
    (
        "B6",
        "PATCH",
        "/api/datasets/{dataset_id}/columns/{col_id}",
        lambda w: f"/api/datasets/{w.dataset_id}/columns/{w.column_id}",
        lambda w: {"expected_version": 1, "display_name": "바뀐 열"},
        200,
        DEFINER,
    ),
    (
        "C1",
        "GET",
        "/api/datasets/{dataset_id}/rows",
        lambda w: f"/api/datasets/{w.dataset_id}/rows",
        lambda w: None,
        200,
        READER,
    ),
    (
        "C2",
        "POST",
        "/api/datasets/{dataset_id}/rows",
        lambda w: f"/api/datasets/{w.dataset_id}/rows",
        lambda w: {"expected_version": 1, "cells": {str(w.column_id): "5"}},
        201,
        ENTER,
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
    ),
]


@pytest.fixture
def mworld(db: Db, world: World) -> World:
    """매트릭스용 세계: 기본 세계에 A팀 데이터셋(정의 버전 1)과 원본 열 하나를 더한다."""
    dataset_id = db.add_dataset(world.team_a, "기존 데이터셋", world.ids["definer"])
    column_id = db.add_column(dataset_id, "기존 열", "number")
    db.add_rows(dataset_id, 1)  # C3 대상 행 하나(row_id 1, 빈 칸)
    return replace(world, dataset_id=dataset_id, column_id=column_id, row_id=1)


@pytest.mark.parametrize("role", ROLES, ids=lambda r: r or "anonymous")
@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=lambda e: e[0])
def test_endpoint_by_role(api, db: Db, mworld: World, endpoint: Endpoint, role):
    _, method, _template, make_path, make_body, success, who = endpoint
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
        dynamic,
    )


def test_denied_requests_do_not_change_data(api, db: Db, mworld: World):
    """403은 응답만이 아니라 실제로 아무것도 바뀌지 않았다는 뜻이어야 한다."""
    before = _snapshot(db)
    for _id, method, _template, make_path, make_body, _code, who in ENDPOINTS:
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
