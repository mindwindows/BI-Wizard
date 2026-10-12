"""`current_user`(fail-closed), 권한 판정, 라우터 조립 규칙(공개 경로 밖은 모두 인증 필요)."""

import re
from typing import Annotated

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth import CurrentUser, CurrentUserDep, Identity, Membership, UserRecord
from app.auth.guard import PUBLIC_PATHS
from app.auth.permissions import can_define, can_enter, is_admin, require_admin
from app.main import create_app, register_routers


class FakeAdapter:
    def __init__(self, login_id: str | None):
        self.login_id = login_id

    def identify(self, request):
        return Identity(self.login_id) if self.login_id else None


class FakeReader:
    def __init__(self, users: dict[str, CurrentUser]):
        self.users = users

    def find_by_login_id(self, request, login_id):
        user = self.users.get(login_id)
        return UserRecord(user) if user else None


def _user(**kw) -> CurrentUser:
    base = dict(id=1, display_name="홍길동", is_active=True, is_admin=False, memberships=())
    base.update(kw)
    return CurrentUser(**base)


def _protected_router() -> APIRouter:
    router = APIRouter()

    @router.get("/_t/me")
    def me(user: CurrentUserDep) -> dict:
        return {"id": user.id}

    @router.get("/_t/admin")
    def admin(user: Annotated[CurrentUser, Depends(require_admin)]) -> dict:
        return {"id": user.id}

    @router.post("/_t/write")
    def write() -> dict:  # current_user를 직접 쓰지 않아도 라우터 조립이 붙여 준다.
        return {"ok": True}

    return router


@pytest.fixture
def app(make_settings, sqlite_engine) -> FastAPI:
    app = create_app(make_settings(), engine=sqlite_engine)
    register_routers(app, public=(), protected=(_protected_router(),))
    return app


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def _code(response) -> str:
    return response.json()["error"]["code"]


# --- fail-closed ---------------------------------------------------------------------------


@pytest.mark.parametrize(("method", "path"), [("get", "/api/_t/me"), ("post", "/api/_t/write")])
def test_no_adapter_is_401(client, method, path):
    response = getattr(client, method)(path)
    assert response.status_code == 401
    assert _code(response) == "UNAUTHENTICATED"


def test_adapter_without_reader_is_401(app, client):
    app.state.identity_adapter = FakeAdapter("kim")
    assert client.get("/api/_t/me").status_code == 401


def test_reader_without_adapter_is_401(app, client):
    app.state.user_reader = FakeReader({"kim": _user()})
    assert client.get("/api/_t/me").status_code == 401


def test_no_identity_is_401(app, client):
    app.state.identity_adapter = FakeAdapter(None)
    app.state.user_reader = FakeReader({"kim": _user()})
    assert _code(client.get("/api/_t/me")) == "UNAUTHENTICATED"


def test_adapter_exception_is_401_not_500(app, client):
    class Broken:
        def identify(self, request):
            raise RuntimeError("secret detail")

    app.state.identity_adapter = Broken()
    app.state.user_reader = FakeReader({})
    response = client.get("/api/_t/me")
    assert response.status_code == 401
    assert "secret detail" not in response.text


def test_reader_exception_is_401(app, client):
    class Broken:
        def find_by_login_id(self, request, login_id):
            raise RuntimeError("db down")

    app.state.identity_adapter = FakeAdapter("kim")
    app.state.user_reader = Broken()
    assert client.get("/api/_t/me").status_code == 401


# --- 등록 상태 ---------------------------------------------------------------------------------


def test_unregistered_user_is_403(app, client):
    app.state.identity_adapter = FakeAdapter("stranger")
    app.state.user_reader = FakeReader({"kim": _user()})
    response = client.get("/api/_t/me")
    assert response.status_code == 403
    assert _code(response) == "USER_NOT_REGISTERED"


def test_inactive_user_is_403(app, client):
    app.state.identity_adapter = FakeAdapter("kim")
    app.state.user_reader = FakeReader({"kim": _user(is_active=False)})
    response = client.get("/api/_t/me")
    assert response.status_code == 403
    assert _code(response) == "USER_INACTIVE"


def test_active_user_passes_including_write_route(app, client):
    app.state.identity_adapter = FakeAdapter("kim")
    app.state.user_reader = FakeReader({"kim": _user(id=7)})
    assert client.get("/api/_t/me").json() == {"id": 7}
    assert client.post("/api/_t/write").status_code == 200


def test_require_admin(app, client):
    app.state.identity_adapter = FakeAdapter("kim")
    app.state.user_reader = FakeReader({"kim": _user()})
    response = client.get("/api/_t/admin")
    assert response.status_code == 403
    assert _code(response) == "FORBIDDEN"
    app.state.user_reader = FakeReader({"kim": _user(is_admin=True)})
    assert client.get("/api/_t/admin").status_code == 200


# --- 권한 판정 -------------------------------------------------------------------------------


def test_permission_functions():
    definer = Membership(1, "a", "A팀", "definer")
    entry = Membership(2, "b", "B팀", "entry")
    user = _user(memberships=(definer, entry))
    assert can_define(user, 1) and not can_define(user, 2) and not can_define(user, 3)
    assert can_enter(user, 1) and can_enter(user, 2) and not can_enter(user, 3)
    assert not is_admin(user)
    # 관리자라도 팀 소속이 아니면 정의·입력 불가(06 §4-1).
    admin = _user(is_admin=True)
    assert is_admin(admin) and not can_define(admin, 1) and not can_enter(admin, 1)
    # 비활성은 어떤 권한도 없다.
    inactive = _user(is_active=False, is_admin=True, memberships=(definer,))
    assert not is_admin(inactive) and not can_define(inactive, 1) and not can_enter(inactive, 1)


# --- 라우터 조립 구조 시험 --------------------------------------------------------------------

_PATH_PARAM = re.compile(r"\{[^}]+\}")


def paths_open_without_auth(client: TestClient) -> list[str]:
    """OpenAPI의 모든 (메서드, 경로)를 인증 없이 호출해 401이 아닌 것을 돌려준다(공개 경로 제외).

    `current_user`가 먼저 실행되므로 본문·쿼리 검증 오류(422)보다 401이 앞선다.
    """
    opened = []
    for path, operations in client.app.openapi()["paths"].items():
        for method in operations:
            if method.upper() not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                continue
            url = _PATH_PARAM.sub("1", path)
            if url in PUBLIC_PATHS:
                continue
            response = client.request(method, url)
            if response.status_code != 401:
                opened.append(f"{method.upper()} {path} -> {response.status_code}")
    return opened


def test_every_non_public_route_requires_auth(make_settings, sqlite_engine):
    app = create_app(make_settings(), engine=sqlite_engine)
    # 실제 앱에 보호 라우터가 추가되면 이 시험이 자동으로 그 경로를 훑는다.
    register_routers(app, public=(), protected=(_protected_router(),))
    with TestClient(app) as client:
        assert paths_open_without_auth(client) == []
        # 훑기가 비어 있지 않음을 확인한다.
        assert "/api/_t/write" in app.openapi()["paths"]


def test_real_app_has_only_public_routes_for_now(make_settings, sqlite_engine):
    app = create_app(make_settings(), engine=sqlite_engine)
    assert set(app.openapi()["paths"]) == PUBLIC_PATHS
    with TestClient(app) as client:
        assert paths_open_without_auth(client) == []


def test_structure_check_detects_route_missing_current_user(make_settings, sqlite_engine):
    """인증 의존이 빠진 라우트를 실제로 잡아내는지(검사 자체의 시험)."""
    app = create_app(make_settings(), engine=sqlite_engine)
    stray = APIRouter()

    @stray.post("/stray/{item_id}")
    def stray_write(item_id: int) -> dict:
        return {}

    app.include_router(stray, prefix="/api")
    with TestClient(app) as client:
        assert len(paths_open_without_auth(client)) == 1
        assert "/api/stray/{item_id}" in paths_open_without_auth(client)[0]


def test_nested_dependency_counts_as_protected(make_settings, sqlite_engine):
    app = create_app(make_settings(), engine=sqlite_engine)

    def via_helper(user: CurrentUserDep) -> CurrentUser:
        return user

    router = APIRouter()

    @router.get("/nested")
    def nested(user: Annotated[CurrentUser, Depends(via_helper)]) -> dict:
        return {}

    app.include_router(router, prefix="/api")
    with TestClient(app) as client:
        assert paths_open_without_auth(client) == []


def test_public_paths_are_exactly_health(make_settings, sqlite_engine):
    assert PUBLIC_PATHS == {"/api/health", "/api/health/db"}


def test_public_paths_work_without_auth(make_settings, sqlite_engine):
    with TestClient(create_app(make_settings(), engine=sqlite_engine)) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/health/db").status_code == 200


def test_assembly_refuses_business_router_in_public_list():
    leaky = APIRouter()

    @leaky.post("/leaky")
    def leaky_write() -> dict:
        return {}

    with pytest.raises(RuntimeError, match="공개 라우터"):
        register_routers(FastAPI(), public=(leaky,), protected=())


def test_protected_router_without_explicit_dependency_is_guarded(client):
    # /api/_t/write 는 함수 안에서 current_user를 쓰지 않지만 조립이 붙인다.
    assert client.post("/api/_t/write").status_code == 401
