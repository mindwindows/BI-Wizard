"""인증 스텁(05 §2-6 DV1~DV3, `bi-review` 7-5): 켜짐/꺼짐, 쿠키, 등록·비활성 판정, 시작 거부."""

from urllib.parse import quote

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.access import service
from app.auth.guard import DEV_STUB_PATHS, PUBLIC_PATHS
from app.auth.stub import STUB_COOKIE, StubIdentityAdapter
from app.config import Settings
from app.main import DEV_ROUTERS, create_app, register_routers
from tests.api_helpers import make_caller
from tests.conftest import Db
from tests.test_auth import _flatten, structural_violations

DEV_OPERATIONS = [
    ("GET", "/api/dev/stub-users"),
    ("PUT", "/api/dev/stub-user"),
    ("DELETE", "/api/dev/stub-user"),
]


def err(response) -> dict:
    return response.json()["error"]


# --- 꺼짐: 경로 자체가 없고 쿠키는 무시된다 ----


def test_stub_off_has_no_dev_routes_and_no_adapter(make_settings, db: Db, world):
    app = create_app(make_settings(), engine=db.engine)
    assert app.state.identity_adapter is None
    assert not any(path.startswith("/api/dev") for path in app.openapi()["paths"])
    with TestClient(app) as client:
        call = make_caller(client)
        for method, path in DEV_OPERATIONS:
            response = call("admin", method, path, json={"login_id": "admin"})
            assert response.status_code == 404, (method, path)
        # 스텁 쿠키가 있어도 신원으로 쓰지 않는다: 운영 어댑터가 없으면 모두 401(fail-closed).
        for login in ("admin", "viewer", None):
            response = call(login, "GET", "/api/me")
            assert response.status_code == 401 and err(response)["code"] == "UNAUTHENTICATED"


def test_stub_off_by_default_even_when_app_env_is_local(make_settings, db: Db, world):
    app = create_app(make_settings(APP_ENV="local"), engine=db.engine)
    assert app.state.identity_adapter is None


# --- 켜짐 ----


@pytest.fixture
def stub_client(stub_settings: Settings, db: Db, world):
    with TestClient(create_app(stub_settings, engine=db.engine)) as client:
        yield client, make_caller(client)


def test_stub_on_registers_adapter_and_dev_routes(stub_settings, db: Db):
    app = create_app(stub_settings, engine=db.engine)
    assert isinstance(app.state.identity_adapter, StubIdentityAdapter)
    paths = set(app.openapi()["paths"])
    assert DEV_STUB_PATHS <= paths


def test_dv1_lists_users_without_login(stub_client, world):
    _, call = stub_client
    response = call(None, "GET", "/api/dev/stub-users")
    assert response.status_code == 200
    body = response.json()
    assert body["current"] is None
    assert {u["login_id"] for u in body["items"]} == set(world.ids)
    admin = next(u for u in body["items"] if u["login_id"] == "admin")
    assert admin == {"login_id": "admin", "display_name": "관리자", "is_admin": True}
    assert set(body) == {"items", "current"}


def test_dv2_sets_httponly_cookie_and_dv1_reports_current(stub_client, world):
    client, call = stub_client
    response = call(None, "PUT", "/api/dev/stub-user", json={"login_id": "definer"})
    assert response.status_code == 204 and response.content == b""
    set_cookie = response.headers["set-cookie"]
    assert set_cookie.startswith(f"{STUB_COOKIE}=definer;")
    assert (
        "HttpOnly" in set_cookie and "Path=/" in set_cookie and "samesite=lax" in set_cookie.lower()
    )
    # 같은 클라이언트(쿠키 유지)로 이어서 요청하면 그 사용자로 인식된다.
    assert client.get("/api/me").json()["display_name"] == "정의 담당자"
    assert client.get("/api/dev/stub-users").json()["current"] == "definer"


def test_dv1_current_is_the_cookie_value_even_when_not_registered(stub_client, world):
    """05 DV1: `current`는 쿠키의 로그인 ID 그대로다(등록 여부와 무관)."""
    _, call = stub_client
    response = call("ghost-id", "GET", "/api/dev/stub-users")
    assert response.status_code == 200
    body = response.json()
    assert body["current"] == "ghost-id"
    assert "ghost-id" not in {u["login_id"] for u in body["items"]}
    # 한글·특수 문자는 인코딩된 쿠키에서 복원해 그대로 돌려준다.
    assert call("홍 길동/1", "GET", "/api/dev/stub-users").json()["current"] == "홍 길동/1"
    # 쿠키가 없으면 null.
    assert call(None, "GET", "/api/dev/stub-users").json()["current"] is None


def test_dv2_unknown_login_is_404_and_sets_no_cookie(stub_client):
    _, call = stub_client
    response = call(None, "PUT", "/api/dev/stub-user", json={"login_id": "nobody"})
    assert response.status_code == 404 and err(response)["code"] == "NOT_FOUND"
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize(
    "body", [{}, {"login_id": ""}, {"login_id": "a" * 201}, {"login_id": "x", "y": 1}]
)
def test_dv2_validates_body(stub_client, body):
    _, call = stub_client
    assert call(None, "PUT", "/api/dev/stub-user", json=body).status_code == 422


def test_dv2_allows_inactive_user_so_the_block_can_be_tested(stub_client, world):
    client, call = stub_client
    assert call(None, "PUT", "/api/dev/stub-user", json={"login_id": "inactive"}).status_code == 204
    response = client.get("/api/me")
    assert response.status_code == 403 and err(response)["code"] == "USER_INACTIVE"


def test_dv3_clears_cookie(stub_client):
    client, call = stub_client
    call(None, "PUT", "/api/dev/stub-user", json={"login_id": "admin"})
    assert client.get("/api/me").status_code == 200
    response = client.delete("/api/dev/stub-user")
    assert response.status_code == 204
    assert (
        STUB_COOKIE in response.headers["set-cookie"]
        and "Max-Age=0" in response.headers["set-cookie"]
    )
    assert client.get("/api/me").status_code == 401


def test_cookie_path_follows_base_path(make_settings, db: Db, world):
    settings = make_settings(AUTH_STUB_ENABLED="true", APP_ENV="test", APP_BASE_PATH="/bi-wizard")
    with TestClient(create_app(settings, engine=db.engine)) as client:
        response = client.put("/bi-wizard/api/dev/stub-user", json={"login_id": "admin"})
        assert "Path=/bi-wizard" in response.headers["set-cookie"]


@pytest.mark.parametrize("login_id", ["김 철수", "a@b.c", "한글;id", 'q"uote', "x%y", "a/b", "ünï"])
def test_cookie_round_trips_any_login_id(stub_settings, db: Db, login_id):
    db.add_user(login_id, "특수 문자 사용자")
    with TestClient(create_app(stub_settings, engine=db.engine)) as client:
        assert client.put("/api/dev/stub-user", json={"login_id": login_id}).status_code == 204
        assert client.get("/api/me").json()["display_name"] == "특수 문자 사용자"


# --- 신원 판정: 쿠키 없음 / 미등록 / 비활성 ----


def test_identity_states(stub_client, world):
    _, call = stub_client
    no_cookie = call(None, "GET", "/api/me")
    assert no_cookie.status_code == 401 and err(no_cookie)["code"] == "UNAUTHENTICATED"
    stranger = call("stranger", "GET", "/api/me")
    assert stranger.status_code == 403 and err(stranger)["code"] == "USER_NOT_REGISTERED"
    inactive = call("inactive", "GET", "/api/me")
    assert inactive.status_code == 403 and err(inactive)["code"] == "USER_INACTIVE"
    assert call("viewer", "GET", "/api/me").status_code == 200


def test_empty_or_oversized_cookie_is_no_identity(stub_client):
    client, _ = stub_client
    client.cookies.clear()
    client.cookies.set(STUB_COOKIE, "")
    assert client.get("/api/me").status_code == 401
    client.cookies.clear()
    client.cookies.set(STUB_COOKIE, quote("a" * 201, safe=""))
    assert client.get("/api/me").status_code == 401


def test_cookie_value_is_not_trusted_as_sql(stub_client):
    """로그인 ID는 값으로만 쓰인다(바인딩). 주입 문자열은 그냥 미등록 사용자다."""
    _, call = stub_client
    response = call("' OR '1'='1", "GET", "/api/me")
    assert response.status_code == 403 and err(response)["code"] == "USER_NOT_REGISTERED"


# --- 시작 거부(fail-closed) ----


@pytest.mark.parametrize("app_env", ["production", "staging", "Local", ""])
def test_stub_on_with_disallowed_app_env_refuses_settings(make_settings, app_env):
    with pytest.raises(ValueError):
        make_settings(AUTH_STUB_ENABLED="true", APP_ENV=app_env)


def test_stub_on_without_explicit_app_env_refuses_settings(make_settings):
    with pytest.raises(ValueError):
        make_settings(AUTH_STUB_ENABLED="true")


def test_create_app_rechecks_even_if_settings_validation_was_bypassed(db: Db):
    """Settings 검증을 우회해 만든 객체여도 어댑터 연결 단계에서 한 번 더 거부한다."""
    bypassed = Settings.model_construct(
        auth_stub_enabled=True,
        app_env="production",
        app_name="x",
        app_base_path="",
        app_debug=False,
        log_level="INFO",
    )
    with pytest.raises(ValueError):
        create_app(bypassed, engine=db.engine)


# --- 조립 구조 ----


def test_dev_router_with_other_path_is_refused():
    leaky = APIRouter()

    @leaky.get("/dev/other")
    def other() -> dict:
        return {}

    from fastapi import FastAPI

    with pytest.raises(RuntimeError, match="공개 라우터"):
        register_routers(FastAPI(), public=(), protected=(), dev=(leaky,))


def test_only_dev_paths_are_open_without_current_user(stub_settings, db: Db):
    app = create_app(stub_settings, engine=db.engine)
    violations = structural_violations(app)
    assert {v.removeprefix("current_user 없음: ") for v in violations} == DEV_STUB_PATHS
    assert len(violations) == 3  # DV1, DV2, DV3
    assert DEV_STUB_PATHS.isdisjoint(PUBLIC_PATHS)
    paths = {getattr(r, "path", None) for r in _flatten(app.routes)}
    assert DEV_STUB_PATHS <= paths and DEV_ROUTERS


# --- 시드 + 신원 통합 ----


def test_seeded_users_work_with_stub_login(stub_settings, db: Db):
    with Session(db.engine) as session:  # 시드도 앱 계정(bi_app) 권한으로 실행한다.
        service.seed_stub_data(session)
    with TestClient(create_app(stub_settings, engine=db.engine)) as client:
        call = make_caller(client)
        multi = call("stub-multi", "GET", "/api/me").json()
        assert sorted((m["team_code"], m["role"]) for m in multi["memberships"]) == [
            ("stub_a", "entry"),
            ("stub_b", "definer"),
        ]
        assert call("stub-admin", "GET", "/api/me").json()["is_admin"] is True
        assert err(call("stub-inactive", "GET", "/api/me"))["code"] == "USER_INACTIVE"
        assert call("stub-viewer", "GET", "/api/me").json()["memberships"] == []
