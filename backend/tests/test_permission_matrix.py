"""권한 매트릭스 자동 시험(05 §4, 03b 3-6 BY4): 엔드포인트와 역할의 곱. 1a 범위(A1~A9, DV1~DV3).

역할: 관리자, 정의 담당자, 입력자, 다른 팀 구성원, 비소속 읽기, 비활성, 인증 없음.
1a 엔드포인트는 팀 범위 판정이 없다(관리자 전용 또는 인증된 읽기)라 정의 담당자·입력자·
다른 팀 구성원·비소속 읽기는 같은 결과여야 한다. 팀 범위 판정은 1b 이후 엔드포인트가 더한다.
"""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.guard import PUBLIC_PATHS
from app.main import create_app
from tests.api_helpers import World, make_caller
from tests.conftest import Db

ROLES = ["admin", "definer", "entry", "other", "viewer", "inactive", None]
READERS = {"admin", "definer", "entry", "other", "viewer"}  # 인증된 활성 사용자

# (ID, 메서드, 경로 템플릿, 경로 만들기, 본문 만들기, 관리자 성공 코드, 관리자 전용 여부)
Endpoint = tuple[str, str, str, Callable[[World], str], Callable[[World], Any], int, bool]
ENDPOINTS: list[Endpoint] = [
    ("A1", "GET", "/api/me", lambda w: "/api/me", lambda w: None, 200, False),
    ("A2", "GET", "/api/teams", lambda w: "/api/teams", lambda w: None, 200, False),
    (
        "A3",
        "POST",
        "/api/teams",
        lambda w: "/api/teams",
        lambda w: {"code": "new_team", "name": "새 팀"},
        201,
        True,
    ),
    (
        "A4",
        "PATCH",
        "/api/teams/{team_id}",
        lambda w: f"/api/teams/{w.team_b}",
        lambda w: {"name": "바뀐 B팀"},
        200,
        True,
    ),
    ("A5", "GET", "/api/users", lambda w: "/api/users", lambda w: None, 200, True),
    (
        "A6",
        "POST",
        "/api/users",
        lambda w: "/api/users",
        lambda w: {"login_id": "fresh", "display_name": "새 사용자"},
        201,
        True,
    ),
    (
        "A7",
        "PATCH",
        "/api/users/{user_id}",
        lambda w: f"/api/users/{w.ids['viewer']}",
        lambda w: {"display_name": "바뀐 이름"},
        200,
        True,
    ),
    (
        "A8",
        "PUT",
        "/api/teams/{team_id}/members/{user_id}",
        lambda w: f"/api/teams/{w.team_b}/members/{w.ids['viewer']}",
        lambda w: {"role": "entry"},
        200,
        True,
    ),
    (
        "A9",
        "DELETE",
        "/api/teams/{team_id}/members/{user_id}",
        lambda w: f"/api/teams/{w.team_a}/members/{w.ids['entry']}",
        lambda w: None,
        204,
        True,
    ),
]


@pytest.mark.parametrize("role", ROLES, ids=lambda r: r or "anonymous")
@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=lambda e: e[0])
def test_endpoint_by_role(api, db: Db, world: World, endpoint: Endpoint, role):
    _, method, _template, make_path, make_body, admin_success, admin_only = endpoint
    body = make_body(world)
    response = api(role, method, make_path(world), **({"json": body} if body is not None else {}))
    if role is None:
        assert (response.status_code, response.json()["error"]["code"]) == (401, "UNAUTHENTICATED")
    elif role == "inactive":
        assert (response.status_code, response.json()["error"]["code"]) == (403, "USER_INACTIVE")
    elif admin_only and role != "admin":
        assert (response.status_code, response.json()["error"]["code"]) == (403, "FORBIDDEN")
    else:
        assert role in READERS or role == "admin"
        assert response.status_code == admin_success


def test_admin_only_endpoints_do_not_change_data_for_non_admins(api, db: Db, world: World):
    """403은 응답만이 아니라 실제로 아무것도 바뀌지 않았다는 뜻이어야 한다."""
    from app.db_metadata import team_members, teams, users

    def snapshot():
        return (db.rows(users, users.c.id), db.rows(teams, teams.c.id), db.rows(team_members))

    before = snapshot()
    for _id, method, _template, make_path, make_body, _code, admin_only in ENDPOINTS:
        if not admin_only:
            continue
        body = make_body(world)
        for role in ("definer", "entry", "other", "viewer", "inactive", None):
            api(role, method, make_path(world), **({"json": body} if body is not None else {}))
    assert snapshot() == before


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
