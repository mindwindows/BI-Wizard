"""`current_user`(fail-closed), 권한 판정, 라우터 조립 규칙(공개 경로 밖은 모두 인증 필요)."""

import logging
import re
from typing import Annotated

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.routing import Mount

from app.auth import CurrentUser, CurrentUserDep, Identity, Membership, UserRecord, current_user
from app.auth.guard import PUBLIC_PATHS
from app.auth.permissions import can_define, can_enter, is_admin, require_admin
from app.main import PROTECTED_ROUTERS, PUBLIC_ROUTERS, create_app, register_routers


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


# --- fail-closed ----


@pytest.mark.parametrize(("method", "path"), [("get", "/api/_t/me"), ("post", "/api/_t/write")])
def test_no_adapter_is_401(client, method, path):
    response = getattr(client, method)(path)
    assert response.status_code == 401
    assert _code(response) == "UNAUTHENTICATED"


def test_adapter_without_reader_is_401(app, client):
    app.state.identity_adapter = FakeAdapter("kim")
    app.state.user_reader = None
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


def test_lookup_failure_is_logged_without_identity_or_exception_detail(app, client, caplog):
    """DB 오류도 401로 닫되 로그에는 예외 클래스 이름과 request_id만 남긴다."""

    class Boom(Exception):
        pass

    class Broken:
        def find_by_login_id(self, request, login_id):
            raise Boom(f"SELECT ... WHERE login_id = '{login_id}' [parameters: ('{login_id}',)]")

    app.state.identity_adapter = FakeAdapter("secret.login.id")
    app.state.user_reader = Broken()
    with caplog.at_level(logging.DEBUG):
        response = client.get("/api/_t/me")
    assert response.status_code == 401
    records = [r for r in caplog.records if r.name == "app.auth.current_user"]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.ERROR
    assert record.exc_info is None
    assert "인증 조회 실패(401로 닫음)" in record.getMessage()
    assert "Boom" in record.getMessage()
    assert response.headers["X-Request-ID"] in record.getMessage()
    for leaked in ("secret.login.id", "SELECT", "parameters", "Traceback"):
        assert leaked not in caplog.text


# --- DB 장애는 503 (03b 17-1 결정 2): 로그아웃(401)과 구분하되 접근은 닫혀 있다 ----


def _db_errors():
    from sqlalchemy.exc import InterfaceError, OperationalError
    from sqlalchemy.exc import TimeoutError as PoolTimeoutError

    sql = "SELECT users.id FROM users WHERE users.login_id = %s"
    return [
        OperationalError(sql, ("secret.login.id",), Exception("connection refused")),
        InterfaceError(sql, ("secret.login.id",), Exception("closed")),
        PoolTimeoutError("QueuePool limit of size 5 overflow 0 reached"),
        ConnectionRefusedError("[Errno 111] secret.login.id"),
    ]


@pytest.mark.parametrize("error", _db_errors(), ids=lambda e: type(e).__name__)
def test_db_failure_in_user_lookup_is_503_not_401(app, client, caplog, error):
    class Down:
        def find_by_login_id(self, request, login_id):
            raise error

    app.state.identity_adapter = FakeAdapter("secret.login.id")
    app.state.user_reader = Down()
    with caplog.at_level(logging.DEBUG):
        response = client.get("/api/_t/me")
    assert response.status_code == 503
    assert _code(response) == "SERVICE_UNAVAILABLE"
    assert response.json()["error"]["details"] == {}
    # 로그: 클래스 이름과 request_id만. login_id, SQL, 파라미터, 트레이스백 없음.
    records = [r for r in caplog.records if r.name == "app.auth.current_user"]
    assert len(records) == 1 and records[0].exc_info is None
    assert type(error).__name__ in records[0].getMessage()
    assert response.headers["X-Request-ID"] in records[0].getMessage()
    for leaked in ("secret.login.id", "SELECT", "users", "parameters", "Traceback", "refused"):
        assert leaked not in caplog.text
        assert leaked not in response.text


def test_db_failure_does_not_open_access_for_write_routes(app, client):
    class Down:
        def find_by_login_id(self, request, login_id):
            raise _db_errors()[0]

    app.state.identity_adapter = FakeAdapter("kim")
    app.state.user_reader = Down()
    for method, path in (
        ("get", "/api/_t/me"),
        ("post", "/api/_t/write"),
        ("get", "/api/_t/admin"),
    ):
        response = getattr(client, method)(path)
        assert (response.status_code, _code(response)) == (503, "SERVICE_UNAVAILABLE"), path


def test_adapter_failure_stays_401_even_if_it_is_a_db_error(app, client):
    """신원 어댑터 자체의 예외는 DB 장애로 보지 않고 기존대로 401 fail-closed다."""

    class Broken:
        def identify(self, request):
            raise _db_errors()[0]

    app.state.identity_adapter = Broken()
    app.state.user_reader = FakeReader({})
    assert client.get("/api/_t/me").status_code == 401


def test_non_db_reader_failure_stays_401(app, client):
    class Broken:
        def find_by_login_id(self, request, login_id):
            raise ValueError("알 수 없는 팀 역할")

    app.state.identity_adapter = FakeAdapter("kim")
    app.state.user_reader = Broken()
    assert client.get("/api/_t/me").status_code == 401


def test_every_protected_route_is_503_when_db_is_down(make_settings, broken_engine, caplog):
    """실제 DB 조회기(DbUserReader)가 연결에 실패하면 /api/me 외 모든 보호 경로도 같다."""
    from urllib.parse import quote

    from app.auth.stub import STUB_COOKIE

    settings = make_settings(AUTH_STUB_ENABLED="true", APP_ENV="test")
    app = create_app(settings, engine=broken_engine)
    checked = []
    with TestClient(app) as client, caplog.at_level(logging.DEBUG):
        client.cookies.set(STUB_COOKIE, quote("secret.login.id", safe=""))
        for path, operations in app.openapi()["paths"].items():
            if path in PUBLIC_PATHS or path.startswith("/api/dev/"):
                continue
            for method in operations:
                url = _PATH_PARAM.sub("1", path)
                response = client.request(method, url)
                checked.append(f"{method.upper()} {path}")
                assert response.status_code == 503, (method, path)
                assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert "GET /api/me" in checked and len(checked) >= 9
    assert "secret.login.id" not in caplog.text


# --- 등록 상태 ----


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


# --- 권한 판정 ----


def test_permission_functions():
    definer = Membership(1, "a", "A팀", True, "definer")
    entry = Membership(2, "b", "B팀", True, "entry")
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


# --- 라우터 조립 구조 시험 ----

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


ACCESS_PATHS = {
    "/api/me",
    "/api/teams",
    "/api/teams/{team_id}",
    "/api/teams/{team_id}/members/{user_id}",
    "/api/users",
    "/api/users/{user_id}",
}


DATASET_PATHS = {
    "/api/datasets",
    "/api/datasets/{dataset_id}",
    "/api/datasets/{dataset_id}/archive",
    "/api/datasets/{dataset_id}/restore",
    "/api/datasets/{dataset_id}/columns",
    "/api/datasets/{dataset_id}/columns/{col_id}",
}


ENTRY_PATHS = {
    "/api/datasets/{dataset_id}/rows",
    "/api/datasets/{dataset_id}/rows/{row_id}",
    "/api/datasets/{dataset_id}/rows/paste",
}


FORMULA_PATHS = {
    "/api/formulas/functions",
    "/api/datasets/{dataset_id}/formulas",
    "/api/datasets/{dataset_id}/formulas/check",
    "/api/datasets/{dataset_id}/formulas/preview",
    "/api/datasets/{dataset_id}/formulas/{col_id}",
    "/api/datasets/{dataset_id}/formula-errors",
    "/api/checks/formula-errors",
    "/api/checks/views",
    "/api/checks/views/retry",
}

SUPERSET_PATHS = {
    "/api/superset/datasets",
    "/api/superset/sync",
    "/api/dashboards",
    "/api/dashboards/{dashboard_id}",
    "/api/dashboards/{dashboard_id}/guest-token",
}
AUDIT_PATHS = {"/api/audit-logs"}  # F1(FU-2a): 읽기 전용 한 경로뿐이다(수정·삭제·내보내기 없음)


def test_real_app_routes_are_public_health_plus_access_dataset_entry_formula_and_superset(
    make_settings, sqlite_engine
):
    """경로는 공개 2개와 A1~A9·B1~B6·C1~C4·D1~D10·E1~E6·F1뿐이다. 스텁이 꺼지면 /dev/*가 없다."""
    app = create_app(make_settings(), engine=sqlite_engine)
    assert set(app.openapi()["paths"]) == (
        PUBLIC_PATHS
        | ACCESS_PATHS
        | DATASET_PATHS
        | ENTRY_PATHS
        | FORMULA_PATHS
        | SUPERSET_PATHS
        | AUDIT_PATHS
    )
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


# 정적 구조 검사. FastAPI 0.143은 `include_router`를 `_IncludedRouter`로 지연 포함해
# `app.routes`에 APIRoute가 바로 나오지 않는다(상위 라우터 의존성도 요청 때 합쳐진다). 그래서
# (1) `app.routes`를 `_IncludedRouter.effective_candidates()`로 펼쳐 유효 경로와 의존성 트리를
# 훑고(비공개 API라 FastAPI를 올리면 이 시험이 먼저 깨진다 = 의도), (2) 같은 검사를
# `PUBLIC_ROUTERS`/`PROTECTED_ROUTERS` 목록으로 새 앱을 조립해 한 번 더 돌린다.
# 펼치기가 아무것도 못 찾는 경우를 막으려고 개수 하한도 확인한다.

# 개발 전용(app_debug=True)으로만 열리는 문서 경로. 공개 경로가 아니며 운영에서는 없어야 한다.
DEBUG_ONLY_PATHS = frozenset({"/api/docs", "/api/openapi.json", "/docs/oauth2-redirect"})


def _flatten(routes):
    for route in routes:
        if hasattr(route, "effective_candidates"):
            yield from _flatten(route.effective_candidates())
        else:
            yield route


def _has_current_user(dependant) -> bool:
    return any(dep.call is current_user or _has_current_user(dep) for dep in dependant.dependencies)


def structural_violations(app: FastAPI) -> list[str]:
    """`PUBLIC_PATHS`·`DEBUG_ONLY_PATHS` 밖에서 current_user가 없는 라우트, Mount 등을 돌려준다."""
    violations = []
    for route in _flatten(app.routes):
        original = getattr(route, "original_route", route)
        path = getattr(route, "path", None)
        if isinstance(original, Mount) or not (
            isinstance(original, APIRoute) or path in DEBUG_ONLY_PATHS
        ):
            violations.append(f"허용되지 않는 라우트 종류: {type(original).__name__} {path}")
        elif isinstance(original, APIRoute) and path not in PUBLIC_PATHS:
            if route.dependant is None or not _has_current_user(route.dependant):
                violations.append(f"current_user 없음: {path}")
    return violations


def test_structure_every_non_public_api_route_has_current_user(make_settings, sqlite_engine):
    app = create_app(make_settings(), engine=sqlite_engine)
    register_routers(app, public=(), protected=(_protected_router(),))
    assert structural_violations(app) == []
    paths = {getattr(r, "path", None) for r in _flatten(app.routes)}
    assert {"/api/_t/me", "/api/_t/write", "/api/health"} <= paths  # 펼치기가 비어 있지 않음


def test_structure_real_router_lists(make_settings, sqlite_engine):
    """실제 PUBLIC_ROUTERS/PROTECTED_ROUTERS로 조립한 앱도 같은 규칙을 지킨다."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    register_routers(app, public=PUBLIC_ROUTERS, protected=PROTECTED_ROUTERS)
    assert structural_violations(app) == []
    effective = {r.path for r in _flatten(app.routes) if isinstance(r.original_route, APIRoute)}
    expected = {
        f"/api{route.path}"
        for router in (*PUBLIC_ROUTERS, *PROTECTED_ROUTERS)
        for route in router.routes
    }
    assert effective == expected


def test_structure_check_detects_missing_current_user_and_mount(make_settings, sqlite_engine):
    app = create_app(make_settings(), engine=sqlite_engine)
    stray = APIRouter()

    @stray.get("/stray")
    def stray_read() -> dict:
        return {}

    app.include_router(stray, prefix="/api")
    assert structural_violations(app) == ["current_user 없음: /api/stray"]

    app.mount("/static", FastAPI())
    violations = structural_violations(app)
    assert any("Mount" in v for v in violations)


def test_structure_check_detects_include_in_schema_false_route(make_settings, sqlite_engine):
    app = create_app(make_settings(), engine=sqlite_engine)
    hidden = APIRouter()

    @hidden.get("/hidden", include_in_schema=False)
    def hidden_read() -> dict:
        return {}

    app.include_router(hidden, prefix="/api")
    assert structural_violations(app) == ["current_user 없음: /api/hidden"]


def test_docs_only_in_debug(make_settings, sqlite_engine):
    """`/api/docs`·`/api/openapi.json`은 개발 전용(app_debug)이다. 운영에서는 없어야 한다."""
    prod = create_app(make_settings(APP_DEBUG="false"), engine=sqlite_engine)
    assert {getattr(r, "path", None) for r in _flatten(prod.routes)}.isdisjoint(DEBUG_ONLY_PATHS)
    with TestClient(prod) as client:
        for path in ("/api/docs", "/api/openapi.json"):
            assert client.get(path).status_code == 404
    dev = create_app(make_settings(APP_DEBUG="true"), engine=sqlite_engine)
    assert structural_violations(dev) == []
    assert DEBUG_ONLY_PATHS & {getattr(r, "path", None) for r in dev.routes}
    assert not DEBUG_ONLY_PATHS & PUBLIC_PATHS


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
