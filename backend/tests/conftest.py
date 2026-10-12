import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, delete, insert
from sqlalchemy.engine import URL
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings
from app.core.startup_check import StartupReport
from app.db import build_database_url, create_db_engine
from app.db_metadata import metadata, team_members, teams, users
from app.main import create_app
from tests.api_helpers import World, build_world, make_caller

# 비밀이 아닌 테스트 전용 값. 실제 DB에는 접속하지 않는다.
_BASE_ENV = {
    "POSTGRES_HOST": "db.test",
    "POSTGRES_PORT": "5432",
    "POSTGRES_DB": "testdb",
}

# PostgreSQL 시험(`pg` 변형)용 접속 정보. 자동 정리 fixture가 환경변수를 지우기 전에, 시험을 실행한
# 셸의 값을 모듈 로딩 때 한 번 읽어 둔다. 없으면 `pg` 시험은 건너뛴다
# (예: `docker build --target test`).
# 사용법은 skills/permission-management/SKILL.md의 "검증 방법".
_PG_ENV_NAMES = (
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_APP_PASSWORD",
    "POSTGRES_OWNER_PASSWORD",
    "POSTGRES_READONLY_PASSWORD",
)
_PG_ENV = {name: os.environ.get(name, "") for name in _PG_ENV_NAMES}
_PG_REQUIRED = (
    "POSTGRES_HOST",
    "POSTGRES_DB",
    "POSTGRES_APP_PASSWORD",
    "POSTGRES_OWNER_PASSWORD",
    "POSTGRES_READONLY_PASSWORD",
)
_BACKEND = Path(__file__).resolve().parent.parent


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


@pytest.fixture(autouse=True)
def _fake_startup_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    """앱 시작 자가 점검(PostgreSQL 전용)을 SQLite 시험 엔진에서는 건너뛴다.

    실제 점검은 `tests/test_startup_check.py`가 직접 호출해 시험하고, 앱 시작에 연결되어 있음은
    그 파일의 시험이 이 대역을 되돌려 확인한다.
    """
    monkeypatch.setattr("app.main.run_startup_checks", lambda engine: StartupReport())


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


# --- 실제 PostgreSQL (`pg` 변형) ----


@dataclass(frozen=True)
class PgEnv:
    values: dict[str, str]

    def url(self, user: str, password: str) -> URL:
        return URL.create(
            "postgresql+pg8000",
            username=user,
            password=password,
            host=self.values["POSTGRES_HOST"],
            port=int(self.values["POSTGRES_PORT"] or 5432),
            database=self.values["POSTGRES_DB"],
        )

    def apply(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for name, value in self.values.items():
            if value:
                monkeypatch.setenv(name, value)
        get_settings.cache_clear()


@pytest.fixture(scope="session")
def pg_env() -> PgEnv:
    """tmpfs 시험 DB(compose profile `test`)가 준비됐는지 확인하고 head까지 올린다.

    안전장치: 시험 DB 서비스만 `fsync=off`로 뜬다. 그 밖의 DB(개발·운영)에는 표를 만들고 지우는
    시험을 실행하지 않는다.
    """
    missing = [name for name in _PG_REQUIRED if not _PG_ENV[name]]
    if missing:
        pytest.skip("PostgreSQL 시험 환경이 없다(POSTGRES_* 환경변수, tmpfs 시험 DB 필요)")
    env = PgEnv(dict(_PG_ENV))
    try:
        owner = create_engine(
            env.url("bi_owner", env.values["POSTGRES_OWNER_PASSWORD"]), poolclass=sa.pool.NullPool
        )
        with owner.connect() as conn:
            fsync = conn.execute(sa.select(sa.func.current_setting("fsync"))).scalar_one()
    except Exception as exc:
        pytest.skip(f"PostgreSQL 시험 DB에 접속하지 못했다({type(exc).__name__})")
    if fsync != "off":
        pytest.skip("tmpfs 시험 DB(compose profile test, fsync=off)가 아니라서 건너뛴다")
    with pytest.MonkeyPatch.context() as mp:
        env.apply(mp)
        command.upgrade(Config(str(_BACKEND / "alembic.ini")), "head")
    get_settings.cache_clear()
    return env


@pytest.fixture
def pg_settings(pg_env: PgEnv) -> Settings:
    """시험 DB 접속 설정. 환경변수는 이 fixture 안에서만 바꾸고 되돌린다(다른 시험에 새지 않게)."""
    with pytest.MonkeyPatch.context() as mp:
        pg_env.apply(mp)
        mp.setenv("AUTH_STUB_ENABLED", "true")
        mp.setenv("APP_ENV", "test")
        settings = Settings()  # type: ignore[call-arg]
    get_settings.cache_clear()
    return settings


@pytest.fixture
def pg_owner_engine(pg_env: PgEnv, pg_settings: Settings) -> Iterator[Engine]:
    engine = create_engine(build_database_url(pg_settings, "owner"), poolclass=sa.pool.NullPool)
    yield engine
    engine.dispose()


@pytest.fixture
def pg_app_engine(pg_settings: Settings) -> Iterator[Engine]:
    engine = create_db_engine(pg_settings)
    yield engine
    engine.dispose()


@pytest.fixture
def pg_readonly_engine(pg_env: PgEnv) -> Iterator[Engine]:
    engine = create_engine(
        pg_env.url("bi_readonly", pg_env.values["POSTGRES_READONLY_PASSWORD"]),
        poolclass=sa.pool.NullPool,
    )
    yield engine
    engine.dispose()


def clear_static_tables(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(delete(team_members))
        conn.execute(delete(teams))
        conn.execute(delete(users))


@pytest.fixture
def clean_pg(pg_owner_engine: Engine) -> Iterator[None]:
    """시험 전후로 정적 표의 행을 모두 지운다(`bi_owner`만 DELETE 권한이 있다)."""
    clear_static_tables(pg_owner_engine)
    yield
    clear_static_tables(pg_owner_engine)


# --- API 시험용 DB 변형(sqlite, pg) ----


@dataclass
class Db:
    """API 시험이 쓰는 DB 한 개. 앱은 `engine`으로 접속하고, 시험은 `writer`로 행을 심는다."""

    kind: str
    engine: Engine
    writer: Engine

    def add_user(
        self,
        login_id: str,
        display_name: str | None = None,
        *,
        is_admin: bool = False,
        is_active: bool = True,
    ) -> int:
        with self.writer.begin() as conn:
            return conn.execute(
                insert(users)
                .values(
                    login_id=login_id,
                    display_name=display_name or login_id,
                    is_admin=is_admin,
                    is_active=is_active,
                )
                .returning(users.c.id)
            ).scalar_one()

    def add_team(self, code: str, name: str | None = None, *, is_active: bool = True) -> int:
        with self.writer.begin() as conn:
            return conn.execute(
                insert(teams)
                .values(code=code, name=name or f"{code} 팀", is_active=is_active)
                .returning(teams.c.id)
            ).scalar_one()

    def add_member(self, team_id: int, user_id: int, role: str) -> None:
        with self.writer.begin() as conn:
            conn.execute(insert(team_members).values(team_id=team_id, user_id=user_id, role=role))

    def rows(self, table: sa.Table, *order: Any) -> list[dict[str, Any]]:
        with self.writer.connect() as conn:
            return [dict(r) for r in conn.execute(sa.select(table).order_by(*order)).mappings()]


@pytest.fixture(params=["sqlite", "pg"])
def db(request: pytest.FixtureRequest) -> Iterator[Db]:
    if request.param == "sqlite":
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        metadata.create_all(engine)
        yield Db("sqlite", engine, engine)
        engine.dispose()
        return
    request.getfixturevalue("clean_pg")
    yield Db(
        "pg", request.getfixturevalue("pg_app_engine"), request.getfixturevalue("pg_owner_engine")
    )


class RecordingSync:
    """`DatasetSyncPort` 대역: 요청을 기록한다."""

    def __init__(self, *, fail: bool = False) -> None:
        self.team_requests: list[int] = []
        self.dataset_requests: list[int] = []
        self.fail = fail

    def request_dataset_sync(self, dataset_id: int) -> None:
        self.dataset_requests.append(dataset_id)

    def request_team_sync(self, team_id: int) -> None:
        self.team_requests.append(team_id)
        if self.fail:
            raise RuntimeError("sync failed: secret detail")


@pytest.fixture
def sync() -> RecordingSync:
    return RecordingSync()


@pytest.fixture
def stub_settings(make_settings: Callable[..., Settings]) -> Settings:
    return make_settings(AUTH_STUB_ENABLED="true", APP_ENV="test")


@pytest.fixture
def api(db: Db, stub_settings: Settings, sync: RecordingSync) -> Iterator[Callable[..., Any]]:
    """스텁이 켜진 앱 하나. `api(로그인 ID 또는 None, 메서드, 경로, **요청 옵션)`으로 호출한다."""
    app = create_app(stub_settings, engine=db.engine, dataset_sync=sync)
    with TestClient(app) as client:
        yield make_caller(client)


@pytest.fixture
def world(db: Db) -> World:
    return build_world(db)
