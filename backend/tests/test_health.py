import pytest
from fastapi.testclient import TestClient

from app.main import create_app

BASE = "/bi-wizard"


def _client(make_settings, engine, **env):
    settings = make_settings(**env)
    return TestClient(create_app(settings, engine=engine))


@pytest.mark.parametrize(
    ("strip", "paths"),
    [
        # false: 프록시가 접두를 유지한 채 전달 -> backend는 ${APP_BASE_PATH}/api/... 로 받는다.
        ("false", [f"{BASE}/api/health", "/api/health"]),
        # true: 프록시가 접두를 떼고 전달 -> backend는 /api/... 로 받는다.
        ("true", ["/api/health", f"{BASE}/api/health"]),
    ],
)
def test_health_both_proxy_modes(make_settings, sqlite_engine, strip, paths):
    with _client(
        make_settings, sqlite_engine, APP_BASE_PATH=BASE, APP_PROXY_STRIP_PREFIX=strip
    ) as client:
        for path in paths:
            response = client.get(path)
            assert response.status_code == 200, path
            assert response.json()["status"] == "ok"


def test_health_without_base_path(make_settings, sqlite_engine):
    with _client(make_settings, sqlite_engine) as client:
        assert client.get("/api/health").status_code == 200


@pytest.mark.parametrize("strip", ["false", "true"])
def test_health_db_up(make_settings, sqlite_engine, strip):
    with _client(
        make_settings, sqlite_engine, APP_BASE_PATH=BASE, APP_PROXY_STRIP_PREFIX=strip
    ) as client:
        for path in (f"{BASE}/api/health/db", "/api/health/db"):
            response = client.get(path)
            assert response.status_code == 200, path
            assert response.json() == {"status": "ok", "database": "up"}


def test_health_db_down_returns_503_without_details(make_settings, broken_engine):
    with _client(make_settings, broken_engine, APP_BASE_PATH=BASE) as client:
        response = client.get(f"{BASE}/api/health/db")
        assert response.status_code == 503
        assert response.json() == {"status": "error", "database": "down"}
        # /health는 DB와 무관하게 응답한다.
        assert client.get(f"{BASE}/api/health").status_code == 200


def test_no_unprefixed_or_azure_routes(make_settings, sqlite_engine):
    with _client(make_settings, sqlite_engine, APP_BASE_PATH=BASE) as client:
        assert client.get("/health").status_code == 404
        assert client.get("/api/health/azure-openai").status_code == 404


def test_docs_only_in_debug(make_settings, sqlite_engine):
    with _client(make_settings, sqlite_engine, APP_BASE_PATH=BASE) as client:
        assert client.get("/api/openapi.json").status_code == 404
    with _client(make_settings, sqlite_engine, APP_BASE_PATH=BASE, APP_DEBUG="true") as client:
        assert client.get("/api/openapi.json").status_code == 200


# --- H1 새 필드(시작 자가 점검이 채운 메모리 값, 05 §2-6) ---------------------------------------


def test_health_exposes_startup_report_fields(make_settings, sqlite_engine):
    with _client(make_settings, sqlite_engine) as client:
        body = client.get("/api/health").json()
    assert body == {
        "status": "ok",
        "app": "BI-Wizard",
        "views": 0,
        "views_failed_count": 0,
        "public_create": None,
        "db_timezone": None,
    }


def test_health_fields_are_counts_booleans_and_timezone_only(make_settings, sqlite_engine):
    from app.core.startup_check import StartupReport

    with _client(make_settings, sqlite_engine) as client:
        client.app.state.startup_report = StartupReport(
            views=4, views_failed_count=2, public_create=False, db_timezone="Asia/Seoul"
        )
        response = client.get("/api/health")
    assert response.status_code == 200  # 뷰 실패가 있어도 200(Docker healthcheck 유지)
    body = response.json()
    assert (body["views"], body["views_failed_count"]) == (4, 2)
    assert body["public_create"] is False and body["db_timezone"] == "Asia/Seoul"
    assert set(body) == {
        "status",
        "app",
        "views",
        "views_failed_count",
        "public_create",
        "db_timezone",
    }


def test_health_does_not_touch_the_database(make_settings, broken_engine):
    """새 필드도 메모리 값이다: DB가 죽어 있어도 /health는 200이고 값을 돌려준다."""
    from app.core.startup_check import StartupReport

    with _client(make_settings, broken_engine) as client:
        client.app.state.startup_report = StartupReport(public_create=False, db_timezone="UTC")
        response = client.get("/api/health")
        assert response.status_code == 200 and response.json()["db_timezone"] == "UTC"
        assert client.get("/api/health/db").status_code == 503
