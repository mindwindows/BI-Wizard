import pytest
from sqlalchemy import create_engine

from app.config import Settings, get_settings

# 비밀이 아닌 테스트 전용 값. 실제 DB에는 접속하지 않는다.
_BASE_ENV = {
    "POSTGRES_HOST": "db.test",
    "POSTGRES_PORT": "5432",
    "POSTGRES_DB": "testdb",
    "POSTGRES_USER": "tester",
    "POSTGRES_PASSWORD": "test-password",
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
