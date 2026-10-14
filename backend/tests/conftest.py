import os
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, delete, event, insert, update
from sqlalchemy.engine import URL
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

from app import ddl
from app.config import Settings, get_settings
from app.core.startup_check import StartupReport
from app.dataset.hashing import structure_hash
from app.db import build_database_url, create_db_engine
from app.db_metadata import (
    DYNAMIC_SCHEMA,
    audit_log,
    dataset_columns,
    datasets,
    formula_deps,
    formulas,
    metadata,
    reference_items,
    reference_values,
    superset_dashboards,
    superset_datasets,
    team_members,
    teams,
    users,
)
from app.main import create_app
from tests.api_helpers import World, build_world, make_caller


# SQLite 변형의 한계: SQLite는 `INTEGER PRIMARY KEY`만 자동 번호(rowid)가 된다. 운영 DDL의
# `row_id`는 `BIGINT … IDENTITY`라 SQLite에서는 번호가 붙지 않으므로, 이 시험 도구에서만
# SQLite의 BIGINT를 INTEGER로 만든다. 운영 PostgreSQL DDL은 바뀌지 않는다(`pg` 변형과
# test_ddl.py가 확인).
@compiles(sa.BigInteger, "sqlite")
def _sqlite_bigint_as_integer(type_, compiler, **kw):
    return "INTEGER"


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

# CI 전용 시험 옵션(03b 17-1 결정 7): `REQUIRE_PG=1`이면 PostgreSQL 시험 환경이 없을 때 `pg` 변형을
# 건너뛰지 않고 **실패**시킨다(건너뛰어서 통과처럼 보이는 일을 막는다). 시험을 실행하는 환경에서만
# 읽으며 `.env`·`.env.example`·compose에는 넣지 않는다. 미설정이면 기존처럼 건너뛴다.
REQUIRE_PG_NAME = "REQUIRE_PG"
_REQUIRE_PG = os.environ.get(REQUIRE_PG_NAME, "") == "1"


def require_pg_enabled(environ: Mapping[str, str]) -> bool:
    """`REQUIRE_PG=1`로 켜졌는가(정확히 문자열 "1"만 켠다)."""
    return environ.get(REQUIRE_PG_NAME, "") == "1"


def pg_unavailable(reason: str, *, require: bool | None = None) -> None:
    """PG 시험을 할 수 없을 때 `REQUIRE_PG=1`이면 실패, 아니면 건너뛴다(항상 예외를 올린다)."""
    if _REQUIRE_PG if require is None else require:
        pytest.fail(f"{reason} (REQUIRE_PG=1이라 건너뛰지 않고 실패로 처리한다)", pytrace=False)
    pytest.skip(reason)


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
        pg_unavailable("PostgreSQL 시험 환경이 없다(POSTGRES_* 환경변수, tmpfs 시험 DB 필요)")
    env = PgEnv(dict(_PG_ENV))
    try:
        owner = create_engine(
            env.url("bi_owner", env.values["POSTGRES_OWNER_PASSWORD"]), poolclass=sa.pool.NullPool
        )
        with owner.connect() as conn:
            fsync = conn.execute(sa.select(sa.func.current_setting("fsync"))).scalar_one()
    except Exception as exc:
        pg_unavailable(f"PostgreSQL 시험 DB에 접속하지 못했다({type(exc).__name__})")
    if fsync != "off":
        pg_unavailable("tmpfs 시험 DB(compose profile test, fsync=off)가 아니다")
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


def drop_dynamic_tables(engine: Engine) -> None:
    """`bi_data`의 `dv_*`·`de_*` 뷰와 `ds_*` 표를 모두 지운다(시험 정리 전용: schema 소유자로 실행).

    뷰가 표에 의존하므로 뷰를 먼저 지운다.
    """
    with engine.begin() as conn:
        inspector = sa.inspect(conn)
        for name in inspector.get_view_names(schema=DYNAMIC_SCHEMA):
            conn.execute(sa.schema.DropView(sa.Table(name, sa.MetaData(), schema=DYNAMIC_SCHEMA)))
        for name in inspector.get_table_names(schema=DYNAMIC_SCHEMA):
            sa.Table(name, sa.MetaData(), schema=DYNAMIC_SCHEMA).drop(conn)


def clear_static_tables(engine: Engine) -> None:
    drop_dynamic_tables(engine)
    with engine.begin() as conn:
        conn.execute(delete(audit_log))  # users를 가리키는 외래키가 있어 먼저 지운다(bi_owner 전용)
        conn.execute(delete(reference_values))  # 값 -> 항목 -> 사용자 순(외래키)
        conn.execute(delete(reference_items))
        conn.execute(delete(superset_datasets))
        conn.execute(delete(superset_dashboards))
        conn.execute(update(datasets).values(base_date_column_id=None))  # 순환 FK 해제
        conn.execute(delete(formula_deps))
        conn.execute(delete(formulas))
        conn.execute(delete(dataset_columns))
        conn.execute(delete(datasets))
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
    # SQLite 시험 변형에서 기준 날짜 열 규칙 DDL(PostgreSQL 전용)을 대신한 호출 기록.
    period_calls: list[tuple[str, int, int]] = field(default_factory=list)

    def add_dataset(
        self, team_id: int, name: str, created_by: int, *, date_unit: str = "day"
    ) -> int:
        """데이터셋 행과 원본 표를 직접 만든다(API를 거치지 않는 시험 준비용)."""
        with self.writer.begin() as conn:
            dataset_id = conn.execute(
                insert(datasets)
                .values(
                    team_id=team_id,
                    name=name,
                    date_unit=date_unit,
                    created_by=created_by,
                    def_hash=structure_hash([]),
                )
                .returning(datasets.c.id)
            ).scalar_one()
        with self.engine.begin() as conn:
            ddl.create_dataset_table(conn, dataset_id)
        return dataset_id

    def add_column(
        self,
        dataset_id: int,
        display_name: str,
        column_type: str = "number",
        *,
        required: bool = False,
        position: int = 0,
    ) -> int:
        with self.writer.begin() as conn:
            column_id = conn.execute(
                insert(dataset_columns)
                .values(
                    dataset_id=dataset_id,
                    display_name=display_name,
                    type=column_type,
                    kind="raw",
                    required=required,
                    position=position,
                )
                .returning(dataset_columns.c.id)
            ).scalar_one()
        with self.engine.begin() as conn:
            ddl.add_raw_column(conn, dataset_id, column_id, column_type)
        return column_id

    def add_formula_column(
        self,
        dataset_id: int,
        display_name: str,
        ast: dict[str, Any],
        *,
        expression: str = "",
        column_type: str = "number",
        position: int = 0,
        deps: tuple[int, ...] = (),
        tag: str | None = None,
    ) -> int:
        """계산 열의 정의 행·수식·의존을 직접 만든다(훅을 거치지 않으므로 뷰는 없다)."""
        with self.writer.begin() as conn:
            column_id = conn.execute(
                insert(dataset_columns)
                .values(
                    dataset_id=dataset_id,
                    display_name=display_name,
                    type=column_type,
                    kind="formula",
                    position=position,
                    tag=tag,
                )
                .returning(dataset_columns.c.id)
            ).scalar_one()
            conn.execute(
                insert(formulas).values(
                    column_id=column_id, expression=expression, ast=ast, ast_hash="test"
                )
            )
            for dep in deps:
                conn.execute(
                    insert(formula_deps).values(column_id=column_id, depends_on_column_id=dep)
                )
        return column_id

    def add_rows(self, dataset_id: int, count: int = 1) -> None:
        """원본 표에 빈 행을 넣는다(`row_id`만)."""
        rows = sa.table(
            ddl.dataset_table_name(dataset_id), sa.column("row_id"), schema=DYNAMIC_SCHEMA
        )
        with self.engine.begin() as conn:
            for _ in range(count):  # row_id는 자동 번호(1부터)다. 번호를 직접 넣지 않는다.
                conn.execute(insert(rows))

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

        # 동적 객체 schema를 흉내 낸다: 연결마다 메모리 DB를 `bi_data`로 붙인다(원본 표 생성·열 추가
        # DDL이 SQLite에서도 동작). 기준 날짜 열 규칙(NOT NULL 변경·CHECK·유일 인덱스)은 SQLite가
        # 지원하지 않아 아래에서 호출 기록으로 대신한다. 실제 동작은 `pg` 변형과 test_ddl.py가 본다.
        @event.listens_for(engine, "connect")
        def _attach(dbapi_connection, _record) -> None:
            dbapi_connection.execute(f"ATTACH DATABASE ':memory:' AS {DYNAMIC_SCHEMA}")

        metadata.create_all(engine)
        sqlite_db = Db("sqlite", engine, engine)
        # 시험 안의 `monkeypatch`와 같은 인스턴스를 써서 되돌리는 순서가 꼬이지 않게 한다.
        patch = request.getfixturevalue("monkeypatch")

        def _period_index(dataset_id: int, column_id: int) -> sa.Index:
            tbl = sa.Table(
                ddl.dataset_table_name(dataset_id),
                sa.MetaData(),
                sa.Column(ddl.column_name(column_id), sa.Date),
                schema=DYNAMIC_SCHEMA,
            )
            return sa.Index(
                ddl.period_index_name(dataset_id), tbl.c[ddl.column_name(column_id)], unique=True
            )

        # SQLite 변형의 한계: NOT NULL 변경과 기간 첫날 CHECK는 지원되지 않아 호출 기록으로
        # 대신한다. 기간 유일 인덱스(`ux_ds_<번호>_period`)만은 실제로 만들어, 같은 기간 충돌
        # (`PERIOD_CONFLICT`)과 `INSERT … ON CONFLICT DO NOTHING` 경로를 DB 없이도 시험한다.
        # NULL 거부·첫날 강제는 `pg` 변형만 본다.
        def _add_period_rules(conn, dataset_id: int, column_id: int, unit: str) -> None:
            sqlite_db.period_calls.append((f"add:{unit}", dataset_id, column_id))
            conn.execute(sa.schema.CreateIndex(_period_index(dataset_id, column_id)))

        def _drop_period_rules(conn, dataset_id: int, column_id: int) -> None:
            sqlite_db.period_calls.append(("drop", dataset_id, column_id))
            conn.execute(sa.schema.DropIndex(_period_index(dataset_id, column_id)))

        patch.setattr(ddl, "add_period_rules", _add_period_rules)
        patch.setattr(ddl, "drop_period_rules", _drop_period_rules)
        yield sqlite_db
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


def _reference_summary(terminalreporter) -> None:
    """`REF` 차분 묶음(FU-3, 07 §6) 요약."""
    try:
        from tests.test_reference_differential import SUMMARY
    except Exception:  # pragma: no cover - 수집 실패는 다른 곳에서 드러난다
        return
    if not SUMMARY:
        return
    terminalreporter.section("REF 차분 묶음 요약(미리보기 vs 뷰 vs 파이썬 독립 기대값)")
    for line in (
        f"수식 {SUMMARY['formulas']}개(통과 {SUMMARY['accepted']}, C0 거부 {SUMMARY['rejected']}), "
        f"데이터셋 {SUMMARY['datasets']}개, 행 {SUMMARY['rows']}개, 데이터셋당 수식 "
        f"{SUMMARY['formulas_per_dataset']}개",
        f"비교한 칸 {SUMMARY['cells']}개(정정 전 {SUMMARY['cells_before_correction']}, 빈 값 "
        f"{SUMMARY['blank_cells']}개, 오류 칸 {SUMMARY['error_cells']})",
        f"불일치 {SUMMARY['mismatches']}건, DB 예외 {SUMMARY['exceptions']}건",
    ):
        terminalreporter.write_line(line)


def pytest_terminal_summary(terminalreporter) -> None:
    """차분 시험(07 §6) 결과 요약을 항상 출력한다(`-q`에서도 보인다)."""
    _reference_summary(terminalreporter)
    try:
        from tests.test_formula_differential import SUMMARY
    except Exception:  # pragma: no cover - 수집 실패는 다른 곳에서 드러난다
        return
    if not SUMMARY:
        return
    terminalreporter.section("수식 차분 시험 요약(미리보기 vs 뷰)")
    for line in (
        f"수식 {SUMMARY['formulas']}개(통과 {SUMMARY['accepted']}, C0 거부 {SUMMARY['rejected']} "
        f"{SUMMARY['rejected_by_code']}), 데이터셋 {SUMMARY['datasets']}개",
        f"비교한 칸 {SUMMARY['cells']}개(빈 값 {SUMMARY['blank_cells']}개, 오류 칸 "
        f"{SUMMARY['error_cells']})",
        f"불일치 {SUMMARY['mismatches']}건, DB 예외 {SUMMARY['exceptions']}건",
    ):
        terminalreporter.write_line(line)


# 감사 기록 시험(tests/test_audit_*.py)이 함께 쓰는 환경 fixture. 정의는 audit_helpers에 있다.
from tests.audit_helpers import ctx  # noqa: E402, F401
