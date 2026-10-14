"""데이터셋 보관·복구 시험, 실제 PostgreSQL 필요(05 §2-2 B7·B8, 06 §5, `03b` 30-1).

- 불변: 보관·복구 전후로 `dv_`/`de_` 뷰 정의, `ds_` 행, `bi_data` 객체 목록(번호 포함), 정의 해시·
  버전이 같고, 보관·복구 요청이 보낸 SQL에 `CREATE`·`ALTER`·`DROP`·`bi_data`가 0건이며 `ddl` 함수와
  정의 변경 훅이 불리지 않는다. 읽기 전용 계정은 보관 뒤에도 뷰를 읽는다(공개 유지).
- 시작 대조: 보관된 데이터셋의 뷰도 대조·재생성하고 보관 상태·버전은 그대로다.
- 동시성: 동시 보관 2건은 감사 1건, 보관 커밋을 기다린 쓰기(C2 C3 C4 B4 B5 B6)는
  `DATASET_ARCHIVED`, 먼저 행 잠금을 잡은 쓰기가 끝난 뒤 보관이 진행, 교착 0건.
- 마이그레이션 downgrade: 보관 행이나 보관·복구 감사 행이 있으면 거부하고 아무것도 바꾸지 않는다.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event
from sqlalchemy.orm import Session

from app import audit, ddl
from app.auth.models import CurrentUser
from app.config import get_settings
from app.core.db_errors import sqlstate
from app.core.errors import AppError
from app.core.ports import DefinitionHooks, PlainRowView
from app.dataset import definition, service
from app.db_metadata import audit_log, dataset_columns, datasets, formulas
from app.entry import repo as entry_repo
from app.entry import service as entry_service
from app.main import create_app
from migrations.roundtrip import take_snapshot
from tests.audit_helpers import Ctx, audit_rows, audit_rows_of
from tests.conftest import Db
from tests.formula_api_helpers import add_column, add_formula, insert_rows, make_dataset
from tests.test_dataset_concurrency import Worker, wait_for_lock_waiter
from tests.test_entry_concurrency import PasteRow

BACKEND = Path(__file__).resolve().parent.parent


@pytest.fixture
def db(pg_app_engine, pg_owner_engine, clean_pg):
    yield Db("pg", pg_app_engine, pg_owner_engine)


def archive(call, dataset_id, login="definer"):
    return call(login, "POST", f"/api/datasets/{dataset_id}/archive")


def restore(call, dataset_id, login="definer"):
    return call(login, "POST", f"/api/datasets/{dataset_id}/restore")


# --- 불변: 뷰·행·객체·해시·SQL·ddl·훅 ----


@pytest.fixture
def populated(ctx: Ctx, db: Db, world):
    """데이터셋 하나: 숫자 열 2개, 계산 열 1개(뷰 dv_·de_ 있음), 행 3개."""
    dataset = make_dataset(ctx.call, world, "불변 시험")
    sales = add_column(ctx.call, dataset["id"], "매출")["id"]
    cost = add_column(ctx.call, dataset["id"], "비용")["id"]
    add_formula(ctx.call, dataset["id"], "비율", "[매출] / [비용]")
    insert_rows(db, dataset["id"], [{sales: 10, cost: 4}, {sales: 1, cost: 0}, {sales: None}])
    return {"id": dataset["id"], "sales": sales, "cost": cost}


def fingerprint(db: Db, dataset_id: int) -> dict[str, Any]:
    """뷰 정의 해시·`ds_` 행 해시·`bi_data` 객체 목록(번호 포함)·정의 해시·버전·열·수식."""
    with db.writer.connect() as conn:
        views = {
            kind: conn.execute(
                sa.text(
                    "SELECT oid::bigint, md5(pg_get_viewdef(oid)) FROM pg_class "
                    "WHERE oid = to_regclass(:name)"
                ),
                {"name": f"bi_data.{kind}_{dataset_id}"},
            ).one()
            for kind in ("dv", "de")
        }
        rows = conn.execute(
            sa.text(
                "SELECT md5(coalesce(string_agg(t::text, '|' ORDER BY row_id), '')) "  # noqa: S608
                f"FROM bi_data.ds_{dataset_id} t"
            )
        ).scalar_one()
        objects = conn.execute(
            sa.text(
                "SELECT c.relname, c.relkind, c.oid::bigint FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'bi_data' "
                "ORDER BY 1"
            )
        ).all()
        dataset = conn.execute(
            sa.select(
                datasets.c.def_hash, datasets.c.def_version, datasets.c.name, datasets.c.team_id
            ).where(datasets.c.id == dataset_id)
        ).one()
        columns = conn.execute(
            sa.select(dataset_columns).where(dataset_columns.c.dataset_id == dataset_id)
        ).all()
        formula_rows = conn.execute(sa.select(formulas)).all()
    return {
        "views": {k: tuple(v) for k, v in views.items()},
        "rows": rows,
        "objects": [tuple(o) for o in objects],
        "dataset": tuple(dataset),
        "columns": [tuple(c) for c in columns],
        "formulas": [tuple(f) for f in formula_rows],
    }


FORBIDDEN_STATEMENT = re.compile(r"^\s*(CREATE|ALTER|DROP|TRUNCATE|GRANT|REVOKE)\b", re.IGNORECASE)


class StatementLog:
    """`before_cursor_execute`로 엔진이 서버에 보낸 SQL을 모은다."""

    def __init__(self, engine: Engine) -> None:
        self.engine, self.statements = engine, []

    def __enter__(self) -> StatementLog:
        event.listen(self.engine, "before_cursor_execute", self._on_execute)
        return self

    def __exit__(self, *exc: object) -> None:
        event.remove(self.engine, "before_cursor_execute", self._on_execute)

    def _on_execute(self, conn, cursor, statement, parameters, context, executemany) -> None:
        self.statements.append(statement)


class DdlCalls:
    """`ddl` 모듈의 공개 함수와 `run_ddl` 호출 횟수를 센다(0이어야 하는 경로의 확인용)."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.count = 0
        names = (
            "create_dataset_table",
            "add_raw_column",
            "add_period_rules",
            "drop_period_rules",
            "create_view",
            "drop_view",
            "run_ddl",
        )
        for name in names:
            self._wrap(monkeypatch, ddl, name)
        from app.ddl import dynamic

        self._wrap(monkeypatch, dynamic, "run_ddl")

    def _wrap(self, monkeypatch: pytest.MonkeyPatch, module: Any, name: str) -> None:
        original = getattr(module, name)

        def counted(*args: Any, **kwargs: Any) -> Any:
            self.count += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(module, name, counted)


def test_archive_and_restore_leave_every_view_row_and_hash_untouched(
    ctx: Ctx, db: Db, sync, populated, monkeypatch, pg_readonly_engine
):
    dataset_id = populated["id"]
    before = fingerprint(db, dataset_id)
    assert before["objects"], "bi_data에 객체가 있어야 의미 있는 비교다"
    audit_before = len(audit_rows(db))
    requests_before = (list(sync.dataset_requests), list(sync.team_requests))
    ctx.boom_armed["on"] = True  # 정의 변경 훅이 불리면 500: 불리지 않는다는 확인
    calls = DdlCalls(monkeypatch)
    with StatementLog(db.engine) as log:
        archived = archive(ctx.call, dataset_id)
        archived_state = fingerprint(db, dataset_id)
        with (
            pg_readonly_engine.connect() as conn
        ):  # 보관 뒤에도 읽기 전용 계정이 뷰를 읽는다(공개 유지)
            readable = conn.execute(
                sa.text(f"SELECT count(*) FROM bi_data.dv_{dataset_id}")  # noqa: S608
            ).scalar_one()
        restored = restore(ctx.call, dataset_id)
    ctx.boom_armed["on"] = False
    assert archived.status_code == 200 and restored.status_code == 200
    assert readable == 3
    # 불변 단정: 뷰 정의 해시와 oid(다시 만들지 않았다), ds_ 행 해시, 객체 목록, 정의 해시·버전
    assert archived_state == before
    assert fingerprint(db, dataset_id) == before
    # SQL: CREATE·ALTER·DROP 0건, bi_data를 건드리는 문장 0건, 필요한 문장은 있다
    assert [s for s in log.statements if FORBIDDEN_STATEMENT.match(s)] == []
    assert [s for s in log.statements if "bi_data" in s] == []
    joined = "\n".join(log.statements)
    assert "FOR NO KEY UPDATE" in joined and "UPDATE datasets SET status" in joined
    assert "INSERT INTO audit_log" in joined
    assert calls.count == 0  # ddl 함수 호출 0건
    # 정의 변경 훅(boom)·감사 1건씩·동기 요청 0건
    assert len(audit_rows(db)) == audit_before + 2
    assert (sync.dataset_requests, sync.team_requests) == requests_before


def test_the_instrumentation_does_see_ddl_when_a_column_is_added(
    ctx: Ctx, db: Db, populated, monkeypatch
):
    """대조군: 같은 도구가 정의 변경(B5)에서는 CREATE/ALTER와 ddl 호출을 잡는다."""
    calls = DdlCalls(monkeypatch)
    with StatementLog(db.engine) as log:
        add_column(ctx.call, populated["id"], "비고", "text")
    assert calls.count > 0
    assert any(FORBIDDEN_STATEMENT.match(s) for s in log.statements)


def test_viewdef_and_row_hash_do_not_change_across_repeated_archive_and_restore(
    ctx: Ctx, db: Db, populated
):
    before = fingerprint(db, populated["id"])
    for _ in range(3):
        assert archive(ctx.call, populated["id"]).status_code == 200
        assert restore(ctx.call, populated["id"]).status_code == 200
    assert fingerprint(db, populated["id"]) == before


# --- 시작 대조에 보관 포함 ----


def test_startup_check_covers_archived_datasets_views(ctx: Ctx, db: Db, world, sync, stub_settings):
    first = make_dataset(ctx.call, world, "활성")["id"]
    second = make_dataset(ctx.call, world, "보관")["id"]
    for dataset_id in (first, second):
        add_column(ctx.call, dataset_id, "값")
        add_formula(ctx.call, dataset_id, "두배", "[값] * 2")
    assert archive(ctx.call, second).status_code == 200
    state = fingerprint(db, second)
    with db.writer.begin() as conn:  # 보관된 데이터셋의 de_ 뷰가 없어졌고 해시도 낡았다
        conn.execute(sa.schema.DropView(sa.Table(f"de_{second}", sa.MetaData(), schema="bi_data")))
        conn.execute(sa.update(datasets).where(datasets.c.id == second).values(def_hash="stale"))
    audit_before = audit_rows(db)
    with TestClient(create_app(stub_settings, engine=db.engine, dataset_sync=sync)) as client:
        health = client.get("/api/health").json()
    assert health["views"] == 2 and health["views_failed_count"] == 0  # 보관 데이터셋도 센다
    assert f"de_{second}" in sa.inspect(db.engine).get_view_names(schema="bi_data")
    recovered = fingerprint(db, second)
    assert recovered["dataset"] == state["dataset"]  # def_hash 복구, 버전·이름·팀 그대로
    assert recovered["rows"] == state["rows"]
    assert status_of(db, second) == "archived"  # 대조는 보관 상태를 바꾸지 않는다
    assert audit_rows(db) == audit_before  # 시작 대조는 감사 대상이 아니다


# --- 동시성 ----


@pytest.fixture
def pg(db: Db) -> Db:
    return db


@pytest.fixture
def fx(pg: Db):
    """정의 담당자 한 명의 팀과 데이터셋: 날짜 열(기준)·숫자 열·행 하나."""
    user = pg.add_user("definer", "정의 담당자")
    team = pg.add_team("team_a", "A팀")
    pg.add_member(team, user, "definer")
    dataset = pg.add_dataset(team, "동시 보관", user, date_unit="month")
    period = pg.add_column(dataset, "기간", "date", position=0)
    sales = pg.add_column(dataset, "매출", "number", position=1)
    pg.add_rows(dataset, 1)
    actor = CurrentUser(id=user, display_name="정의 담당자", is_active=True, is_admin=False)
    return {"id": dataset, "period": period, "sales": sales, "user": user, "actor": actor}


def def_version(pg: Db, dataset_id: int) -> int:
    with pg.writer.connect() as conn:
        return conn.execute(
            sa.select(datasets.c.def_version).where(datasets.c.id == dataset_id)
        ).scalar_one()


def status_of(pg: Db, dataset_id: int) -> str:
    with pg.writer.connect() as conn:
        return conn.execute(
            sa.select(datasets.c.status).where(datasets.c.id == dataset_id)
        ).scalar_one()


def archive_call(pg: Db, fx, new_state="archived") -> Callable[[], bool]:
    def call():
        with Session(pg.engine) as session:
            if new_state == "archived":
                return service.archive_dataset(session, fx["actor"], fx["id"])
            return service.restore_dataset(session, fx["actor"], fx["id"])

    return call


@pytest.fixture
def hold_archive(monkeypatch: pytest.MonkeyPatch):
    """이름이 `archiver`인 스레드의 보관을 UPDATE 뒤·커밋 전에 멈춰 세운다(행 잠금을 쥔 채)."""
    entered, release = threading.Event(), threading.Event()
    original = audit.record

    def wrapper(*args: Any, **kwargs: Any):
        if threading.current_thread().name == "archiver" and kwargs.get("action") == (
            "dataset.archive"
        ):
            entered.set()
            assert release.wait(timeout=20), "시험이 락 보유자를 풀어 주지 않았다"
        return original(*args, **kwargs)

    monkeypatch.setattr(audit, "record", wrapper)
    return entered, release


def named(name: str, call: Callable[[], Any]) -> Worker:
    worker = Worker(call)
    worker.name = name
    return worker


def test_two_simultaneous_archives_record_one_audit_row(pg: Db, fx, hold_archive):
    entered, release = hold_archive
    first = named("archiver", archive_call(pg, fx))
    first.start()
    assert entered.wait(timeout=5)
    second = Worker(archive_call(pg, fx))
    second.start()
    wait_for_lock_waiter(pg.writer)  # 두 번째가 행 잠금을 기다린다
    release.set()
    first.join(timeout=10)
    second.join(timeout=10)
    assert first.error is None and second.error is None
    assert (first.result, second.result) == (True, False)  # 지는 쪽은 이미 같은 상태: 변경 없음
    assert status_of(pg, fx["id"]) == "archived"
    assert len(audit_rows_of(pg, "dataset.archive")) == 1


def write_attempts(pg: Db, fx) -> dict[str, Callable[[], Any]]:
    """보관 커밋을 기다리게 할 쓰기 6가지(C2 C3 C4 B4 B5 B6). 모두 읽은 버전을 그대로 싣는다."""
    v = def_version(pg, fx["id"])

    def create():
        with Session(pg.engine) as session:
            return entry_service.create_row(
                session,
                fx["id"],
                expected_version=v,
                cells={str(fx["period"]): "2026-01-01", str(fx["sales"]): "5"},
                row_view=PlainRowView(),
            )

    class Change:
        column_id, expected, value = fx["sales"], None, "7"

    def update():
        with Session(pg.engine) as session:
            return entry_service.update_row(
                session,
                fx["id"],
                1,
                expected_version=v,
                changes=[Change()],
                row_view=PlainRowView(),
            )

    def paste():
        with Session(pg.engine) as session:
            return entry_service.paste_rows(
                session,
                fx["id"],
                expected_version=v,
                column_ids=[fx["period"], fx["sales"]],
                rows=[PasteRow(None, ["2026-02-01", "3"])],
            )

    def rename():
        with Session(pg.engine) as session:
            return service.update_dataset(
                session,
                DefinitionHooks(),
                fx["id"],
                actor=fx["actor"],
                expected_version=v,
                name="새 이름",
                date_unit=None,
                base_given=False,
                base_date_column_id=None,
            )

    def add_col():
        with Session(pg.engine) as session:
            return service.add_column(
                session,
                DefinitionHooks(),
                fx["id"],
                actor=fx["actor"],
                expected_version=v,
                display_name="비고",
                column_type="text",
                required=False,
                raw_rules=None,
                raw_tag=None,
                position=None,
            )

    def update_col():
        with Session(pg.engine) as session:
            return service.update_column(
                session,
                DefinitionHooks(),
                fx["id"],
                fx["sales"],
                actor=fx["actor"],
                expected_version=v,
                fields={"display_name"},
                values={"display_name": "매출2"},
            )

    return {
        "C2": create,
        "C3": update,
        "C4": paste,
        "B4": rename,
        "B5": add_col,
        "B6": update_col,
    }


@pytest.mark.parametrize("which", ["C2", "C3", "C4", "B4", "B5", "B6"])
def test_a_write_that_waited_for_the_archive_commit_gets_dataset_archived(
    pg: Db, fx, hold_archive, which
):
    """보관 커밋을 기다린 쓰기는 커밋 뒤 갱신된 행을 읽어 버전 비교 전에 `DATASET_ARCHIVED`다."""
    entered, release = hold_archive
    attempt = write_attempts(pg, fx)[which]
    holder = named("archiver", archive_call(pg, fx))
    holder.start()
    assert entered.wait(timeout=5)
    writer = Worker(attempt)
    writer.start()
    wait_for_lock_waiter(pg.writer)
    assert writer.is_alive()  # 보관 커밋 전이라 기다리고 있다
    release.set()
    holder.join(timeout=10)
    writer.join(timeout=10)
    assert holder.error is None and holder.result is True
    assert isinstance(writer.error, AppError), writer.error
    assert (writer.error.code, writer.error.status_code) == ("DATASET_ARCHIVED", 409)
    assert writer.error.details == {"status": "archived"}
    assert status_of(pg, fx["id"]) == "archived"
    # 쓰기는 아무것도 바꾸지 않았다: 버전 그대로, 행 1개 그대로
    assert def_version(pg, fx["id"]) == 1


def test_a_row_write_holding_the_share_lock_finishes_before_the_archive_proceeds(
    pg: Db, fx, monkeypatch
):
    """먼저 `FOR SHARE`를 잡은 입력은 끝나고 보관이 뒤이어 진행한다(양쪽 모두 성공)."""
    entered, release = threading.Event(), threading.Event()
    original = entry_repo.insert_row

    def wrapper(*args: Any, **kwargs: Any):
        result = original(*args, **kwargs)
        if threading.current_thread().name == "holder":
            entered.set()
            assert release.wait(timeout=20)
        return result

    monkeypatch.setattr(entry_repo, "insert_row", wrapper)
    holder = named("holder", write_attempts(pg, fx)["C2"])
    holder.start()
    assert entered.wait(timeout=5)
    archiver = Worker(archive_call(pg, fx))
    archiver.start()
    wait_for_lock_waiter(pg.writer)
    assert archiver.is_alive()  # 입력이 끝나기를 기다린다
    release.set()
    holder.join(timeout=10)
    archiver.join(timeout=10)
    assert holder.error is None and archiver.error is None
    assert archiver.result is True and status_of(pg, fx["id"]) == "archived"
    with pg.writer.connect() as conn:
        count = conn.execute(sa.text(f"SELECT count(*) FROM bi_data.ds_{fx['id']}")).scalar_one()  # noqa: S608
    assert count == 2  # 기존 행 + 방금 입력한 행


def deadlock_count(pg: Db) -> int:
    with pg.writer.connect() as conn:
        return conn.execute(
            sa.text("SELECT deadlocks FROM pg_stat_database WHERE datname = current_database()")
        ).scalar_one()


def test_mixed_archive_restore_and_writes_never_deadlock(pg: Db, fx, monkeypatch):
    """보관·복구·행 입력·열 추가를 동시에 섞어도 교착이 없고 오류는 정해진 코드뿐이다."""
    allowed = {"DATASET_ARCHIVED", "DEFINITION_VERSION_MISMATCH", "DEFINITION_BUSY", "WRITE_BUSY"}
    iterations = 40  # 시간이 아니라 횟수로 끝낸다(느린 장비에서도 같은 양을 돈다)
    errors: list[str] = []
    counts = {"archive": 0, "restore": 0, "row": 0, "column": 0, "rejected": 0}
    lock = threading.Lock()
    deadlocks_before = deadlock_count(pg)
    conflicts: list[str | None] = []
    for module in (definition, entry_service):
        original = module.is_lock_conflict

        def recording(exc: BaseException, _original=original) -> bool:
            result = _original(exc)
            if result:
                with lock:
                    conflicts.append(sqlstate(exc))
            return result

        monkeypatch.setattr(module, "is_lock_conflict", recording)

    def loop(kind: str, n: int) -> Callable[[], None]:
        def run() -> None:
            for i in range(1, iterations + 1):
                try:
                    with Session(pg.engine) as session:
                        v = def_version_in(session, fx["id"])
                        if kind == "archive":
                            service.archive_dataset(session, fx["actor"], fx["id"])
                        elif kind == "restore":
                            service.restore_dataset(session, fx["actor"], fx["id"])
                        elif kind == "row":
                            entry_service.create_row(
                                session,
                                fx["id"],
                                expected_version=v,
                                cells={
                                    str(
                                        fx["period"]
                                    ): f"{2000 + n * 100 + i // 12}-{i % 12 + 1:02d}-01"
                                },
                                row_view=PlainRowView(),
                            )
                        else:
                            service.add_column(
                                session,
                                DefinitionHooks(),
                                fx["id"],
                                actor=fx["actor"],
                                expected_version=v,
                                display_name=f"열{n}-{i}",
                                column_type="text",
                                required=False,
                                raw_rules=None,
                                raw_tag=None,
                                position=None,
                            )
                    with lock:
                        counts[kind] += 1
                except AppError as error:
                    with lock:
                        if error.code not in allowed:
                            errors.append(error.code)
                        counts["rejected"] += error.code == "DATASET_ARCHIVED"
                except Exception as error:
                    with lock:
                        errors.append(type(error).__name__)

        return run

    plan = [("archive", 1), ("restore", 1), ("row", 1), ("row", 2), ("column", 1), ("column", 2)]
    workers = [Worker(loop(kind, n)) for kind, n in plan]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=30)
    assert not any(w.is_alive() for w in workers), "교착 또는 무한 대기"
    assert errors == []
    assert "40P01" not in conflicts  # 교착(deadlock_detected)으로 끝난 요청이 없다
    assert deadlock_count(pg) == deadlocks_before  # PostgreSQL이 교착을 감지한 적이 없다
    assert counts["archive"] + counts["restore"] > 0
    assert status_of(pg, fx["id"]) in {"active", "archived"}
    # 감사 행 수 = 실제로 바뀐 전이 수(archive·restore가 번갈아 한 건씩, 차이는 최대 1)
    archived_n = len(audit_rows_of(pg, "dataset.archive"))
    restored_n = len(audit_rows_of(pg, "dataset.restore"))
    assert 0 <= archived_n - restored_n <= 1
    assert (archived_n - restored_n == 1) == (status_of(pg, fx["id"]) == "archived")


def def_version_in(session: Session, dataset_id: int) -> int:
    value = session.execute(
        sa.select(datasets.c.def_version).where(datasets.c.id == dataset_id)
    ).scalar_one()
    session.rollback()
    return value


# --- 마이그레이션 downgrade 거부 ----


def _constraint_defs(pg_owner_engine: Engine) -> dict[str, str]:
    with pg_owner_engine.connect() as conn:
        return dict(
            conn.execute(
                sa.text(
                    "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conname IN ('ck_datasets_status', 'ck_audit_log_action')"
                )
            ).all()
        )


def _revision(pg_owner_engine: Engine) -> str:
    with pg_owner_engine.connect() as conn:
        return conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()


@pytest.fixture
def migration_env(pg_env, pg_owner_engine, clean_pg):
    config = Config(str(BACKEND / "alembic.ini"))
    with pytest.MonkeyPatch.context() as mp:
        pg_env.apply(mp)
        # 0008의 downgrade 시험은 0008이 맨 위일 때의 동작이다(0009는 test_reference_migration_pg).
        # 시험 DB는 비어 있어(`clean_pg`) 0009 downgrade의 사전 점검을 통과한다.
        command.downgrade(config, "0008")
        yield config
        command.upgrade(config, "head")  # 어떤 결과로 끝나도 head로 되돌려 다음 시험이 쓴다
    get_settings.cache_clear()


def seed_dataset(pg_owner_engine: Engine, *, status: str = "active") -> int:
    with pg_owner_engine.begin() as conn:
        user = conn.execute(
            sa.text("INSERT INTO users (login_id, display_name) VALUES ('u', 'u') RETURNING id")
        ).scalar_one()
        team = conn.execute(
            sa.text("INSERT INTO teams (code, name) VALUES ('t', 't') RETURNING id")
        ).scalar_one()
        return conn.execute(
            sa.text(
                "INSERT INTO datasets (team_id, name, date_unit, status, def_hash, created_by) "
                "VALUES (:t, 'd', 'day', :s, 'h', :u) RETURNING id"
            ),
            {"t": team, "s": status, "u": user},
        ).scalar_one()


def seed_audit(pg_owner_engine: Engine, action: str) -> None:
    with pg_owner_engine.begin() as conn:
        conn.execute(
            sa.insert(audit_log).values(
                actor_source="cli", action=action, target_type="dataset", target_id=1, details={}
            )
        )


def test_downgrade_refuses_while_an_archived_dataset_exists_and_changes_nothing(
    migration_env, pg_owner_engine
):
    seed_dataset(pg_owner_engine, status="archived")
    before = _constraint_defs(pg_owner_engine)
    with pytest.raises(Exception, match="보관된 데이터셋이 있습니다") as error:
        command.downgrade(migration_env, "0007")
    assert "아무것도 바꾸지 않았습니다" in str(error.value)
    assert _revision(pg_owner_engine) == "0008"
    assert _constraint_defs(pg_owner_engine) == before
    assert "'archived'" in before["ck_datasets_status"]
    with pg_owner_engine.connect() as conn:
        assert conn.execute(sa.select(datasets.c.status)).scalar_one() == "archived"


@pytest.mark.parametrize("action", ["dataset.archive", "dataset.restore"])
def test_downgrade_refuses_while_archive_audit_rows_exist_even_if_no_dataset_is_archived(
    migration_env, pg_owner_engine, action
):
    seed_dataset(pg_owner_engine)  # 활성만 있다
    seed_audit(pg_owner_engine, action)
    before = _constraint_defs(pg_owner_engine)
    with pytest.raises(Exception, match="감사 기록이 있습니다"):
        command.downgrade(migration_env, "0007")
    assert _revision(pg_owner_engine) == "0008"
    assert _constraint_defs(pg_owner_engine) == before
    with pg_owner_engine.connect() as conn:
        assert conn.execute(sa.select(sa.func.count()).select_from(audit_log)).scalar_one() == 1


def test_downgrade_succeeds_without_such_rows_and_restores_the_old_checks(
    migration_env, pg_owner_engine
):
    seed_dataset(pg_owner_engine)
    seed_audit(pg_owner_engine, "dataset.create")  # 옛 15개 행위의 감사 행은 있어도 된다
    at_0008 = take_snapshot(pg_owner_engine)
    command.downgrade(migration_env, "0007")
    assert _revision(pg_owner_engine) == "0007"
    at_0007 = take_snapshot(pg_owner_engine)
    # GRANT는 바뀌지 않는다: 권한(표·열·기본 권한)과 표 구조는 같고 CHECK 정의만 다르다
    for key in ("roles", "memberships", "schemas", "relations", "column_acl", "default_acl"):
        assert at_0007[key] == at_0008[key], key
    changed = set()
    for table, info in at_0008["public_tables"].items():
        old_checks = {n: d for n, d in at_0007["public_tables"][table]["checks"]}
        changed |= {(table, n) for n, d in info["checks"] if old_checks.get(n) != d}
    assert changed == {("datasets", "ck_datasets_status"), ("audit_log", "ck_audit_log_action")}
    defs = _constraint_defs(pg_owner_engine)
    assert "'archived'" not in defs["ck_datasets_status"]
    assert "dataset.archive" not in defs["ck_audit_log_action"]
    assert defs["ck_audit_log_action"].count("::text") == 15
    command.upgrade(migration_env, "0008")
    defs = _constraint_defs(pg_owner_engine)
    assert "'archived'" in defs["ck_datasets_status"]
    assert defs["ck_audit_log_action"].count("::text") == 17
    assert take_snapshot(pg_owner_engine) == at_0008  # 올리면 0008과 완전히 같다
