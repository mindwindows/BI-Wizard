"""backend 시작 자가 점검(04 §2-1 core, 03b 3-6 BY3, 15-2): 거부, 재시도, 앱 시작 연결, /health."""

from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Column, Identity, Integer, MetaData, Sequence, Table
from sqlalchemy.exc import OperationalError
from sqlalchemy.schema import CreateSequence, CreateTable, DropSequence, DropTable

from app.core import startup_check as sc
from app.core.startup_check import (
    FORBIDDEN_ROLE_ATTRIBUTES,
    StartupCheckError,
    StartupReport,
    check_bi_data_objects,
    check_role_attributes,
    check_standard_conforming_strings,
    check_static_tables,
    collect_report,
    forbidden_attributes,
    missing_static_columns,
    run_startup_checks,
    unexpected_dynamic_objects,
)
from app.main import create_app
from tests.conftest import pg_unavailable

REAL_RUN_STARTUP_CHECKS = run_startup_checks  # conftest의 자동 대역이 되돌려지기 전의 실제 함수

ATTRIBUTE_LABELS = {
    "rolsuper": "SUPERUSER",
    "rolcreaterole": "CREATEROLE",
    "rolcreatedb": "CREATEDB",
    "rolreplication": "REPLICATION",
    "rolbypassrls": "BYPASSRLS",
}


class FakeResult:
    def __init__(self, row=None, scalar=None):
        self._row, self._scalar = row, scalar

    def first(self):
        return self._row

    def scalar_one(self):
        return self._scalar


class FakeConn:
    def __init__(self, result: FakeResult):
        self.result = result

    def execute(self, statement):
        return self.result


def role_row(**flags):
    values = {key: False for key, _ in FORBIDDEN_ROLE_ATTRIBUTES}
    values.update(flags)
    return SimpleNamespace(_mapping={"rolname": "bi_app", **values})


# --- 속성 판정 ----


def test_five_forbidden_attributes_are_exactly_the_required_ones():
    assert dict(FORBIDDEN_ROLE_ATTRIBUTES) == ATTRIBUTE_LABELS


def test_clean_role_passes():
    check_role_attributes(FakeConn(FakeResult(row=role_row())))
    assert forbidden_attributes({key: False for key in ATTRIBUTE_LABELS}) == []


@pytest.mark.parametrize("attribute", list(ATTRIBUTE_LABELS))
def test_each_forbidden_attribute_refuses_start(attribute):
    with pytest.raises(StartupCheckError) as error:
        check_role_attributes(FakeConn(FakeResult(row=role_row(**{attribute: True}))))
    message = str(error.value)
    assert ATTRIBUTE_LABELS[attribute] in message and "bi_app" in message
    for other_label in set(ATTRIBUTE_LABELS.values()) - {ATTRIBUTE_LABELS[attribute]}:
        assert other_label not in message  # 문제인 속성만 이름을 댄다.


def test_all_attributes_are_listed_together():
    flags = {key: True for key in ATTRIBUTE_LABELS}
    with pytest.raises(StartupCheckError) as error:
        check_role_attributes(FakeConn(FakeResult(row=role_row(**flags))))
    assert all(label in str(error.value) for label in ATTRIBUTE_LABELS.values())


def test_unknown_attribute_value_is_refused():
    assert forbidden_attributes({"rolsuper": None}) == list(ATTRIBUTE_LABELS.values())


def test_missing_role_row_is_refused():
    with pytest.raises(StartupCheckError):
        check_role_attributes(FakeConn(FakeResult(row=None)))


@pytest.mark.parametrize(("value", "ok"), [("on", True), ("off", False), ("", False)])
def test_standard_conforming_strings(value, ok):
    conn = FakeConn(FakeResult(scalar=value))
    if ok:
        check_standard_conforming_strings(conn)
    else:
        with pytest.raises(StartupCheckError, match="standard_conforming_strings"):
            check_standard_conforming_strings(conn)


# --- bi_data 객체 종류 (순수 판정) ----


def relation(oid, name, kind, identity=False):
    return (oid, name, kind, identity)


def row_type(oid, name, relid, kind="c"):
    return (oid, name, kind, relid, 0, "C")


def array_type(oid, name, element):
    return (oid, "_" + name, "b", 0, element, "A")


def test_empty_schema_is_fine():
    assert unexpected_dynamic_objects([], [], []) == []


def test_tables_views_indexes_identity_sequence_and_their_types_are_allowed():
    relations = [
        relation(10, "ds_1", "r"),
        relation(11, "ds_1_pkey", "i"),
        relation(12, "ds_1_row_id_seq", "S", identity=True),
        relation(13, "dv_1", "v"),
    ]
    types = [
        row_type(20, "ds_1", 10),
        array_type(21, "ds_1", 20),
        row_type(22, "dv_1", 13),
        array_type(23, "dv_1", 22),
    ]
    assert unexpected_dynamic_objects(relations, types, []) == []


def test_standalone_sequence_function_enum_and_matview_are_refused():
    relations = [
        relation(10, "ds_1", "r"),
        relation(14, "free_seq", "S", identity=False),
        relation(15, "mv_1", "m"),
        relation(16, "ft_1", "f"),
    ]
    types = [row_type(20, "ds_1", 10), (30, "mood", "e", 0, 0, "E")]
    found = unexpected_dynamic_objects(relations, types, ["evil_fn"])
    assert "시퀀스 free_seq" in found
    assert "구체화 뷰 mv_1" in found
    assert "외부 표 ft_1" in found
    assert "타입 mood" in found
    assert "함수 evil_fn" in found
    assert len(found) == 5


def test_serial_style_sequence_is_not_allowed_only_identity():
    assert unexpected_dynamic_objects([relation(1, "s", "S", identity=False)], [], []) == [
        "시퀀스 s"
    ]


def test_missing_static_columns():
    expected = {"users": {"id", "login_id"}, "teams": {"id"}}
    assert (
        missing_static_columns(expected, {"users": {"id", "login_id"}, "teams": {"id", "x"}}) == []
    )
    assert missing_static_columns(expected, {"users": {"id"}, "teams": None}) == [
        "표 teams",
        "열 users.login_id",
    ]


# --- 재시도와 시작 연결 ----


class FlakyEngine:
    """connect()가 처음 `failures`번은 연결 오류를 낸다."""

    def __init__(self, failures: int, error: Exception | None = None):
        self.failures, self.calls, self.error = failures, 0, error

    def connect(self):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error or OperationalError(
                "SELECT 1", {}, Exception("connection refused host=db")
            )
        return self

    def __enter__(self):
        return object()

    def __exit__(self, *exc):
        return False


def _stub_other_checks(monkeypatch, *, public_create: bool):
    for name in (
        "check_role_attributes",
        "check_standard_conforming_strings",
        "check_bi_data_objects",
        "check_static_tables",
    ):
        monkeypatch.setattr(sc, name, lambda conn: None)
    monkeypatch.setattr(sc, "read_public_create", lambda conn: public_create)
    monkeypatch.setattr(sc, "read_db_timezone", lambda conn: "Asia/Seoul")


def test_public_create_true_refuses_start(monkeypatch):
    """`bi_app`이 public에 CREATE 권한이 있으면 경고가 아니라 시작 거부다(03b 17-1 결정 5)."""
    _stub_other_checks(monkeypatch, public_create=True)
    with pytest.raises(StartupCheckError, match="public") as error:
        collect_report(object())
    assert "시작하지 않는다" in str(error.value)


def test_public_create_false_passes_and_is_reported(monkeypatch):
    _stub_other_checks(monkeypatch, public_create=False)
    report = collect_report(object())
    assert report.public_create is False and report.db_timezone == "Asia/Seoul"


def test_public_create_refusal_is_not_retried(monkeypatch):
    _stub_other_checks(monkeypatch, public_create=True)
    engine = FlakyEngine(failures=0)
    with pytest.raises(StartupCheckError, match="public"):
        run_startup_checks(engine, attempts=5, sleep=lambda _: pytest.fail("재시도하면 안 된다"))
    assert engine.calls == 1


def test_app_start_is_refused_when_public_create_is_true(make_settings, sqlite_engine, monkeypatch):
    monkeypatch.setattr("app.main.run_startup_checks", REAL_RUN_STARTUP_CHECKS)
    _stub_other_checks(monkeypatch, public_create=True)
    app = create_app(make_settings(), engine=sqlite_engine)
    with pytest.raises(StartupCheckError, match="public"):
        with TestClient(app):
            pytest.fail("public CREATE 권한이 있으면 요청을 받기 전에 중단되어야 한다")


def test_retries_only_connection_problems_then_succeeds(monkeypatch):
    monkeypatch.setattr(sc, "collect_report", lambda conn: StartupReport(public_create=False))
    sleeps = []
    engine = FlakyEngine(failures=3)
    report = run_startup_checks(engine, attempts=5, delay=0.5, sleep=sleeps.append)
    assert report.public_create is False and engine.calls == 4 and sleeps == [0.5, 0.5, 0.5]


def test_gives_up_after_attempts_with_clear_message(monkeypatch):
    engine = FlakyEngine(failures=99)
    sleeps = []
    with pytest.raises(StartupCheckError) as error:
        run_startup_checks(engine, attempts=3, delay=1, sleep=sleeps.append)
    assert engine.calls == 3 and sleeps == [1, 1]
    assert "migrate" in str(error.value) and "connection refused" not in str(error.value)


def test_check_failure_is_not_retried(monkeypatch):
    def refuse(conn):
        raise StartupCheckError("SUPERUSER")

    monkeypatch.setattr(sc, "collect_report", refuse)
    engine = FlakyEngine(failures=0)
    with pytest.raises(StartupCheckError, match="SUPERUSER"):
        run_startup_checks(engine, attempts=5, sleep=lambda _: pytest.fail("재시도하면 안 된다"))
    assert engine.calls == 1


def test_non_connection_error_fails_fast_without_leaking(monkeypatch):
    class Boom(Exception):
        pass

    engine = FlakyEngine(failures=5, error=Boom("password=hunter2 host=10.0.0.5"))
    with pytest.raises(StartupCheckError) as error:
        run_startup_checks(engine, attempts=5, sleep=lambda _: pytest.fail("재시도하면 안 된다"))
    assert "Boom" in str(error.value)
    assert "hunter2" not in str(error.value) and "10.0.0.5" not in str(error.value)
    assert engine.calls == 1


def test_app_start_runs_checks_and_refuses_on_failure(make_settings, sqlite_engine, monkeypatch):
    monkeypatch.setattr("app.main.run_startup_checks", REAL_RUN_STARTUP_CHECKS)

    def refuse(conn):
        raise StartupCheckError("DB 접속 역할 bi_app에 허용되지 않는 속성이 있어 시작하지 않는다")

    monkeypatch.setattr(sc, "collect_report", refuse)
    app = create_app(make_settings(), engine=sqlite_engine)
    with pytest.raises(StartupCheckError, match="시작하지 않는다"):
        with TestClient(app):
            pytest.fail("점검이 실패하면 요청을 받기 전에 시작이 중단되어야 한다")


def test_app_start_stores_report_for_health(make_settings, sqlite_engine, monkeypatch):
    monkeypatch.setattr("app.main.run_startup_checks", REAL_RUN_STARTUP_CHECKS)
    report = StartupReport(
        views=3, views_failed_count=1, public_create=False, db_timezone="Asia/Seoul"
    )
    monkeypatch.setattr(sc, "collect_report", lambda conn: report)
    with TestClient(create_app(make_settings(), engine=sqlite_engine)) as client:
        body = client.get("/api/health").json()
    assert body == {
        "status": "ok",
        "app": "BI-Wizard",
        "views": 3,
        "views_failed_count": 1,
        "public_create": False,
        "db_timezone": "Asia/Seoul",
    }


# --- 실제 PostgreSQL ----


def test_pg_bi_app_passes_all_checks(pg_app_engine):
    with pg_app_engine.connect() as conn:
        report = collect_report(conn)
    assert report.public_create is False  # bi_app은 public에 CREATE 권한이 없다.
    assert isinstance(report.db_timezone, str) and report.db_timezone
    assert (report.views, report.views_failed_count) == (0, 0)


def test_pg_public_create_grant_refuses_start(pg_env, pg_app_engine):
    """실제 DB: 슈퍼유저가 임시로 public CREATE를 주면 시작 점검이 거부하고, 회수하면 통과한다."""
    user, password = pg_env.values["POSTGRES_USER"], pg_env.values["POSTGRES_PASSWORD"]
    if not (user and password):
        pg_unavailable("슈퍼유저 접속 정보(POSTGRES_USER/PASSWORD)가 없다")
    admin = sa.create_engine(pg_env.url(user, password), poolclass=sa.pool.NullPool)
    try:
        with admin.begin() as conn:
            conn.execute(sa.text("GRANT CREATE ON SCHEMA public TO bi_app"))
        try:
            with pytest.raises(StartupCheckError, match="public"):
                run_startup_checks(pg_app_engine, attempts=1)
        finally:
            with admin.begin() as conn:
                conn.execute(sa.text("REVOKE CREATE ON SCHEMA public FROM bi_app"))
        assert run_startup_checks(pg_app_engine, attempts=1).public_create is False
    finally:
        admin.dispose()


def test_pg_run_startup_checks_from_engine(pg_app_engine):
    assert run_startup_checks(pg_app_engine, attempts=1).public_create is False


def test_pg_individual_checks_pass(pg_app_engine):
    with pg_app_engine.connect() as conn:
        check_role_attributes(conn)
        check_standard_conforming_strings(conn)
        check_bi_data_objects(conn)
        check_static_tables(conn)


def test_pg_superuser_connection_is_refused(pg_env):
    """이미지 슈퍼유저로 접속하면 SUPERUSER 등 속성 때문에 거부된다(실제 pg_roles 질의 확인)."""
    user, password = pg_env.values["POSTGRES_USER"], pg_env.values["POSTGRES_PASSWORD"]
    if not (user and password):
        pg_unavailable("슈퍼유저 접속 정보(POSTGRES_USER/PASSWORD)가 없다")
    engine = sa.create_engine(pg_env.url(user, password), poolclass=sa.pool.NullPool)
    try:
        with engine.connect() as conn, pytest.raises(StartupCheckError) as error:
            check_role_attributes(conn)
        message = str(error.value)
        for label in ("SUPERUSER", "CREATEROLE", "CREATEDB", "REPLICATION", "BYPASSRLS"):
            assert label in message
        assert password not in message
    finally:
        engine.dispose()


def test_pg_bi_owner_is_not_refused_by_attributes_but_is_not_the_runtime_account(pg_owner_engine):
    # 속성 검사는 최소 권한만 본다. 접속 계정 이름 상수(bi_app)는 app/db.py가 보장한다.
    with pg_owner_engine.connect() as conn:
        check_role_attributes(conn)


def _dynamic_table(name: str) -> Table:
    return Table(
        name,
        MetaData(),
        Column("row_id", Integer, Identity(), primary_key=True),
        schema="bi_data",
    )


def test_pg_identity_table_is_allowed_but_standalone_sequence_is_refused(pg_app_engine):
    table = _dynamic_table("ds_9001")
    sequence = Sequence("free_seq_9001", schema="bi_data")
    with pg_app_engine.begin() as conn:
        conn.execute(CreateTable(table))
    try:
        with pg_app_engine.connect() as conn:
            check_bi_data_objects(conn)  # 표 + 열이 소유한 Identity 시퀀스 + 기본키 인덱스: 통과
        with pg_app_engine.begin() as conn:
            conn.execute(CreateSequence(sequence))
        try:
            with pg_app_engine.connect() as conn, pytest.raises(StartupCheckError) as error:
                check_bi_data_objects(conn)
            assert "free_seq_9001" in str(error.value)
        finally:
            with pg_app_engine.begin() as conn:
                conn.execute(DropSequence(sequence))
    finally:
        with pg_app_engine.begin() as conn:
            conn.execute(DropTable(table))
    with pg_app_engine.connect() as conn:
        check_bi_data_objects(conn)


def test_pg_health_values_come_from_startup_report(make_settings, pg_app_engine, monkeypatch):
    monkeypatch.setattr("app.main.run_startup_checks", REAL_RUN_STARTUP_CHECKS)
    with TestClient(create_app(make_settings(), engine=pg_app_engine)) as client:
        body = client.get("/api/health").json()
    assert body["public_create"] is False and body["db_timezone"]
    assert (body["views"], body["views_failed_count"]) == (0, 0)
