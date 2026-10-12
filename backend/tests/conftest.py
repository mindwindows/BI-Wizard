import pytest
from sqlalchemy import create_engine

from app.config import Settings, get_settings

# 비밀이 아닌 테스트 전용 값. 실제 DB에는 접속하지 않는다.
_BASE_ENV = {
    "POSTGRES_HOST": "db.test",
    "POSTGRES_PORT": "5432",
    "POSTGRES_DB": "testdb",
}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """개발자 환경의 값이 테스트에 섞이지 않게 관련 변수를 모두 지운다."""
    for name in (
        "APP_NAME",
        "APP_ENV",
        "APP_DEBUG",
        "APP_BASE_PATH",
        "APP_PROXY_STRIP_PREFIX",
        "BACKEND_HOST",
        "BACKEND_PORT",
        "LOG_LEVEL",
        "AUTH_STUB_ENABLED",
        # 슈퍼유저 변수는 backend가 읽지 않는다. 있어도 접속에 쓰이지 않음을 시험이 확인한다.
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_APP_PASSWORD",
        "POSTGRES_OWNER_PASSWORD",
        "SUPERSET_APP_ROOT",
        "SUPERSET_SERVICE_USER",
        "SUPERSET_SERVICE_PASSWORD",
        "SUPERSET_GUEST_ISSUER_USER",
        "SUPERSET_GUEST_ISSUER_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in _BASE_ENV.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()


@pytest.fixture
def make_settings(monkeypatch: pytest.MonkeyPatch):
    def _make(**env: str) -> Settings:
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        return Settings()  # type: ignore[call-arg]

    return _make


@pytest.fixture
def sqlite_engine():
    """DB 접속이 되는 경우의 대역(select(1)만 실행한다)."""
    engine = create_engine("sqlite://")
    yield engine
    engine.dispose()


@pytest.fixture
def broken_engine():
    """접속이 실패하는 경우의 대역(존재하지 않는 디렉터리의 SQLite 파일)."""
    engine = create_engine("sqlite:////nonexistent-dir-for-test/db.sqlite")
    yield engine
    engine.dispose()
