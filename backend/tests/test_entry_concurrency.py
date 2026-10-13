"""입력 그리드 동시성·잠금 시험(06 §5, 03c X-24). 실제 PostgreSQL(tmpfs 시험 DB, `bi_app`) 필요.

SQLite 변형은 없다(`FOR SHARE`·`lock_timeout`·교착·`rowcount` 동작은 PostgreSQL 쪽이다).
확인하는 것:
- pg8000의 `rowcount`/`RETURNING`/`ON CONFLICT DO NOTHING` 동작(03b 미검증 항목, 사실 기록)
- 같은 칸 동시 수정 → 한쪽만 이기고 다른 쪽 `CELL_CONFLICT`
- 같은 기간 동시 INSERT → 한쪽만 이기고 다른 쪽 `PERIOD_CONFLICT` (끝나기를 기다린 뒤 판정)
- 붙여넣기 두 건 교차 갱신에서 교착 없음(고정 순서), 락 대기 초과·교착은 `WRITE_BUSY`
- 행 쓰기는 `datasets` 행을 `FOR SHARE`로 잡아 정의 변경과 서로 기다린다: 기준 날짜 열 지정·
  날짜 단위 변경과 INSERT 경쟁에서 `DATASET_HAS_ROWS`/`DEFINITION_VERSION_MISMATCH`이고 500이 아니다
- 실제 행 쓰기 경로로 다시 확인한 `FOR SHARE` 굶음 관찰값
"""

import threading
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.db_errors import is_lock_conflict, sqlstate
from app.core.errors import AppError
from app.core.ports import DefinitionHooks, PlainRowView
from app.core.startup_check import check_bi_data_objects, check_static_tables
from app.dataset import service as dataset_service
from app.dataset.definition import ROW_WRITE_LOCK_TIMEOUT
from app.db_metadata import datasets
from app.entry import repo as entry_repo
from app.entry import service as entry_service
from tests.conftest import Db
from tests.test_dataset_concurrency import (
    Worker,
    add_column_call,
    blocking_hooks,
    wait_for_lock_waiter,
)

ROW_LOCK_SECONDS = 3.0  # entry 락 대기 한도(ROW_WRITE_LOCK_TIMEOUT)와 같은 값(아래 시험이 확인한다)


@pytest.fixture
def pg(pg_app_engine: Engine, pg_owner_engine: Engine, clean_pg) -> Db:
    return Db("pg", pg_app_engine, pg_owner_engine)


@dataclass
class Fx:
    id: int
    period: int  # 날짜 열 번호
    base: bool  # 기준 날짜 열로 지정했는가
    sales: int
    note: int
    user: int


def make(pg: Db, *, base: bool = True, unit: str = "month") -> Fx:
    user = pg.add_user("entry", "입력자")
    team = pg.add_team("team_a", "A팀")
    pg.add_member(team, user, "entry")
    dataset = pg.add_dataset(team, "동시 입력", user, date_unit=unit)
    period = pg.add_column(dataset, "기간", "date", position=0)
    sales = pg.add_column(dataset, "매출", "number", position=1)
    note = pg.add_column(dataset, "비고", "text", position=2)
    fx = Fx(dataset, period, base, sales, note, user)
    if base:
        with Session(pg.engine) as session:
            dataset_service.update_dataset(
                session,
                DefinitionHooks(),
                dataset,
                expected_version=1,
                name=None,
                date_unit=None,
                base_given=True,
                base_date_column_id=period,
            )
    return fx


def current_version(pg: Db, fx: Fx) -> int:
    with Session(pg.engine) as session:
        return int(session.execute(sa.select(datasets.c.def_version)).scalar_one())


def create(pg: Db, fx: Fx, cells: dict[int, Any], version: int | None = None):
    with Session(pg.engine) as session:
        return entry_service.create_row(
            session,
            fx.id,
            expected_version=version or current_version(pg, fx),
            cells={str(k): v for k, v in cells.items()},
            row_view=PlainRowView(),
        )


class Change:
    def __init__(self, column_id: int, expected: Any, value: Any) -> None:
        self.column_id, self.expected, self.value = column_id, expected, value


def update(pg: Db, fx: Fx, row_id: int, changes: list[Change], version: int | None = None):
    with Session(pg.engine) as session:
        return entry_service.update_row(
            session,
            fx.id,
            row_id,
            expected_version=version or current_version(pg, fx),
            changes=changes,
            row_view=PlainRowView(),
        )


class PasteRow:
    def __init__(self, row_id: int | None, values: list, expected: list | None = None) -> None:
        self.row_id, self.values, self.expected = row_id, values, expected


def paste(pg: Db, fx: Fx, column_ids: list[int], rows: list[PasteRow], version: int | None = None):
    with Session(pg.engine) as session:
        return entry_service.paste_rows(
            session,
            fx.id,
            expected_version=version or current_version(pg, fx),
            column_ids=column_ids,
            rows=rows,
        )


def stored_values(pg: Db, fx: Fx, column_id: int) -> list[Any]:
    tbl = sa.Table(f"ds_{fx.id}", sa.MetaData(), autoload_with=pg.engine, schema="bi_data")
    with pg.engine.connect() as conn:
        rows = conn.execute(sa.select(tbl).order_by(tbl.c.row_id)).mappings().all()
        return [r[f"c_{column_id}"] for r in rows]


def run_together(calls: list, *, timeout: float = 20) -> list[Worker]:
    barrier = threading.Barrier(len(calls))

    def wrap(call):
        def go():
            barrier.wait(timeout=5)
            return call()

        return Worker(go)

    workers = [wrap(call) for call in calls]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=timeout)
    assert not any(w.is_alive() for w in workers), "교착 또는 무한 대기"
    return workers


def codes(workers: list[Worker]) -> list[str]:
    out = []
    for worker in workers:
        if worker.error is None:
            out.append("OK")
        elif isinstance(worker.error, AppError):
            out.append(worker.error.code)
        else:
            out.append(f"{type(worker.error).__name__}:{sqlstate(worker.error)}")
    return out


@pytest.fixture
def hold_inserts(monkeypatch: pytest.MonkeyPatch):
    """이름이 `holder`·`holder2`인 스레드의 행 INSERT를 끝낸 뒤 커밋 전에 멈춰 세운다(락을 쥔 채).

    `(holder가 멈춤, 풀어 주기, holder2가 멈춤)` 이벤트를 돌려준다.
    """
    entered, entered2, release = threading.Event(), threading.Event(), threading.Event()
    original = entry_repo.insert_row

    def wrapper(*args, **kwargs):
        result = original(*args, **kwargs)
        name = threading.current_thread().name
        if name in {"holder", "holder2"}:
            (entered if name == "holder" else entered2).set()
            assert release.wait(timeout=20), "시험이 락 보유자를 풀어 주지 않았다"
        return result

    monkeypatch.setattr(entry_repo, "insert_row", wrapper)
    return entered, release, entered2


def named(name: str, call) -> Worker:
    worker = Worker(call)
    worker.name = name
    return worker


# --- pg8000 사실 확인 ----


def test_pg8000_rowcount_returning_and_on_conflict_facts(pg):
    """03b 미검증 항목: pg8000 `rowcount`와 `INSERT … ON CONFLICT DO NOTHING RETURNING`.

    관찰한 사실을 단정으로 고정한다 (pg8000 + SQLAlchemy 2, PostgreSQL 16.10):
    - UPDATE의 `rowcount`는 맞은 행 수다(가드 불일치 0, 일치 1, 여러 행 N).
    - `ON CONFLICT DO NOTHING RETURNING`은 넣었으면 그 행을, 충돌로 건너뛰었으면 **행이 없다**
      (`scalar()`가 None). 충돌해도 트랜잭션은 중단되지 않는다.
    - `RETURNING`의 값 형이 맞고, 숫자 칸 가드(`IS NOT DISTINCT FROM`)는 NULL과 값 모두 맞는다.
    """
    fx = make(pg)
    with Session(pg.engine) as session:
        context = dataset_service.read_row_context(session, fx.id)
        tbl = entry_repo.dynamic_table(context)
        first = entry_repo.insert_row(
            session,
            tbl,
            {fx.period: _date("2026-01-01"), fx.sales: Decimal("10.50")},
            skip_period_conflict=True,
        )
        again = entry_repo.insert_row(
            session,
            tbl,
            {fx.period: _date("2026-01-01"), fx.sales: Decimal("1")},
            skip_period_conflict=True,
        )
        second = entry_repo.insert_row(
            session, tbl, {fx.period: _date("2026-02-01")}, skip_period_conflict=True
        )
        assert isinstance(first, int) and again is None and isinstance(second, int)
        # 충돌(건너뜀) 뒤에도 같은 트랜잭션을 계속 쓸 수 있다.
        assert entry_repo.count_rows(session, tbl) == 2
        # rowcount
        miss = entry_repo.update_guarded(
            session, tbl, first, {fx.sales: (Decimal("99"), Decimal("1"))}
        )
        hit = entry_repo.update_guarded(
            session, tbl, first, {fx.sales: (Decimal("10.5"), Decimal("11"))}
        )
        null_guard = entry_repo.update_guarded(
            session, tbl, second, {fx.sales: (None, Decimal("5"))}
        )
        null_miss = entry_repo.update_guarded(
            session, tbl, second, {fx.sales: (None, Decimal("6"))}
        )
        already = entry_repo.update_guarded(
            session, tbl, second, {fx.sales: (Decimal("0"), Decimal("5"))}
        )
        gone = entry_repo.update_guarded(session, tbl, 99999, {fx.sales: (None, Decimal("1"))})
        assert (miss, hit, null_guard, null_miss, already, gone) == (0, 1, 1, 0, 1, 0)
        session.rollback()
    print(
        "[pg8000] rowcount: 불일치=0, 일치=1, NULL 가드 일치=1/불일치=0, 이미 같은 값=1, "
        "없는 행=0; ON CONFLICT DO NOTHING RETURNING: 충돌이면 행 없음(None), 트랜잭션 유지"
    )


def _date(text: str):
    from datetime import date

    return date.fromisoformat(text)


def test_row_writes_do_not_add_objects_the_startup_check_rejects(pg):
    """행 읽기·쓰기는 DML이라 `bi_data`에 새 객체를 만들지 않는다(시작 자가 점검과 충돌 없음)."""
    fx = make(pg)
    paste(
        pg,
        fx,
        [fx.period, fx.sales],
        [PasteRow(None, [f"2026-{m:02d}-01", str(m)]) for m in range(1, 7)],
    )
    with pg.engine.connect() as conn:
        check_bi_data_objects(conn)
        check_static_tables(conn)
    # bi_app은 자기가 만든 ds_*의 소유자라 DML이 되고, 읽기 전용 계정은 읽기만 된다.
    assert len(stored_values(pg, fx, fx.period)) == 6


# --- 같은 칸 / 같은 기간 ----


def test_same_cell_updated_concurrently_one_wins_the_other_conflicts(pg):
    fx = make(pg)
    row, _ = create(pg, fx, {fx.period: "2026-01-01", fx.sales: "50"})
    for round_number in range(5):
        current = stored_values(pg, fx, fx.sales)[0]
        results = run_together(
            [
                lambda c=current: update(pg, fx, row["row_id"], [Change(fx.sales, str(c), "60")]),
                lambda c=current: update(pg, fx, row["row_id"], [Change(fx.sales, str(c), "70")]),
            ]
        )
        assert sorted(codes(results)) == ["CELL_CONFLICT", "OK"], (round_number, codes(results))
        winner = next(w for w in results if w.error is None)
        loser = next(w for w in results if w.error is not None)
        [item] = loser.error.details["conflicts"]
        assert item["row_id"] == row["row_id"] and item["column_id"] == fx.sales
        final = stored_values(pg, fx, fx.sales)[0]
        assert Decimal(item["current"]) == final  # 충돌 응답은 이긴 쪽의 값을 알려 준다
        assert final == Decimal(winner.result[0]["cells"][str(fx.sales)])
        # 다음 라운드를 위해 값을 고정한다.
        update(pg, fx, row["row_id"], [Change(fx.sales, str(final), "50")])


def test_different_cells_of_one_row_do_not_conflict(pg):
    fx = make(pg)
    row, _ = create(pg, fx, {fx.period: "2026-01-01"})
    results = run_together(
        [
            lambda: update(pg, fx, row["row_id"], [Change(fx.sales, None, "1")]),
            lambda: update(pg, fx, row["row_id"], [Change(fx.note, None, "메모")]),
        ]
    )
    assert codes(results) == ["OK", "OK"]
    assert stored_values(pg, fx, fx.sales) == [Decimal(1)]
    assert stored_values(pg, fx, fx.note) == ["메모"]


def test_same_period_inserted_concurrently_one_wins(pg):
    fx = make(pg)
    for month in ("01", "02", "03"):
        results = run_together(
            [
                lambda m=month, n=n: create(pg, fx, {fx.period: f"2026-{m}-01", fx.sales: str(n)})
                for n in range(4)
            ]
        )
        assert sorted(codes(results)) == [
            "OK",
            "PERIOD_CONFLICT",
            "PERIOD_CONFLICT",
            "PERIOD_CONFLICT",
        ]
        winner = next(w for w in results if w.error is None).result[0]["row_id"]
        for loser in (w for w in results if w.error is not None):
            [item] = loser.error.details["conflicts"]
            assert item["row_id"] == winner and item["column_id"] == fx.period
    assert len(stored_values(pg, fx, fx.period)) == 3


def test_insert_waits_for_the_uncommitted_same_period_then_conflicts(pg, hold_inserts):
    entered, release, _ = hold_inserts
    fx = make(pg)
    holder = named("holder", lambda: create(pg, fx, {fx.period: "2026-01-01"}))
    holder.start()
    assert entered.wait(timeout=10)
    waiter = named("waiter", lambda: create(pg, fx, {fx.period: "2026-01-01"}))
    waiter.start()
    wait_for_lock_waiter(pg.engine)
    assert waiter.is_alive(), "같은 기간 INSERT는 앞 트랜잭션이 끝나기를 기다려야 한다"
    release.set()
    holder.join(timeout=10)
    waiter.join(timeout=10)
    assert holder.error is None
    assert isinstance(waiter.error, AppError) and waiter.error.code == "PERIOD_CONFLICT"
    assert len(stored_values(pg, fx, fx.period)) == 1


def test_lock_wait_over_the_limit_is_write_busy(pg, hold_inserts):
    """같은 기간을 먼저 넣은 트랜잭션이 한도(3초)를 넘겨 쥐고 있으면 503 `WRITE_BUSY`."""
    assert ROW_WRITE_LOCK_TIMEOUT == "3000ms"
    entered, release, _ = hold_inserts
    fx = make(pg)
    holder = named("holder", lambda: create(pg, fx, {fx.period: "2026-01-01"}))
    holder.start()
    assert entered.wait(timeout=10)
    waiter = named("waiter", lambda: create(pg, fx, {fx.period: "2026-01-01"}))
    waiter.start()
    waiter.join(timeout=15)
    assert not waiter.is_alive()
    assert isinstance(waiter.error, AppError)
    assert (waiter.error.code, waiter.error.status_code) == ("WRITE_BUSY", 503)
    assert waiter.error.details == {"retry_after": 2}
    assert ROW_LOCK_SECONDS * 0.8 <= waiter.elapsed < ROW_LOCK_SECONDS + 3
    release.set()
    holder.join(timeout=10)
    assert holder.error is None
    # 대기자의 변경은 남지 않았고, 락이 풀린 뒤에는 다시 시도하면 기간 충돌로 정리된다.
    assert len(stored_values(pg, fx, fx.period)) == 1
    with pytest.raises(AppError) as again:
        create(pg, fx, {fx.period: "2026-01-01"})
    assert again.value.code == "PERIOD_CONFLICT"


# --- 붙여넣기 교차 ----


def test_pastes_updating_the_same_rows_never_deadlock(pg):
    """두 붙여넣기가 같은 행을 서로 다른 순서로 적어도 서버가 `row_id` 순으로 잡아 교착이 없다."""
    fx = make(pg)
    ids = [
        create(pg, fx, {fx.period: f"2026-{m:02d}-01", fx.sales: "1"})[0]["row_id"]
        for m in range(1, 9)
    ]
    cols = [fx.sales]
    for round_number in range(15):
        before = [str(v) for v in stored_values(pg, fx, fx.sales)]
        asc = [PasteRow(r, [f"{10 + round_number}"], [b]) for r, b in zip(ids, before, strict=True)]
        desc = [
            PasteRow(r, [f"{50 + round_number}"], [b])
            for r, b in reversed(list(zip(ids, before, strict=True)))
        ]
        results = run_together(
            [
                lambda a=asc: paste(pg, fx, cols, a),
                lambda d=desc: paste(pg, fx, cols, d),
            ]
        )
        # 같은 칸을 같은 이전 값 기준으로 덮으므로 한쪽만 이기고, 교착·WRITE_BUSY는 없다.
        assert sorted(codes(results)) == ["OK", "PASTE_CONFLICT"], (round_number, codes(results))
        values = {Decimal(v) for v in stored_values(pg, fx, fx.sales)}
        assert len(values) == 1  # 한쪽 붙여넣기가 통째로 반영됐다(섞이지 않음)
        for r in ids:
            update(pg, fx, r, [Change(fx.sales, str(next(iter(values))), "1")])


def test_pastes_inserting_overlapping_new_periods_never_deadlock(pg):
    fx = make(pg)
    cols = [fx.period, fx.sales]
    first = [PasteRow(None, [f"2026-{m:02d}-01", "1"]) for m in (1, 2, 3, 4)]
    second = [PasteRow(None, [f"2026-{m:02d}-01", "2"]) for m in (4, 3, 2, 1)]  # 반대로 적음
    results = run_together(
        [lambda: paste(pg, fx, cols, first), lambda: paste(pg, fx, cols, second)]
    )
    assert sorted(codes(results)) == ["OK", "PASTE_CONFLICT"], codes(results)
    assert len(stored_values(pg, fx, fx.period)) == 4
    assert len({str(v) for v in stored_values(pg, fx, fx.sales)}) == 1  # 한쪽만 반영


def test_paste_is_all_or_nothing_even_after_some_rows_were_written(pg):
    fx = make(pg)
    a, _ = create(pg, fx, {fx.period: "2026-01-01", fx.sales: "1"})
    b, _ = create(pg, fx, {fx.period: "2026-02-01", fx.sales: "2"})
    update(pg, fx, b["row_id"], [Change(fx.sales, "2", "22")])  # 화면이 모르는 변경
    before = (stored_values(pg, fx, fx.sales), stored_values(pg, fx, fx.period))
    rows = [
        PasteRow(a["row_id"], ["100"], ["1"]),  # 정상: 먼저 갱신된다
        PasteRow(b["row_id"], ["200"], ["2"]),  # 충돌
        PasteRow(None, ["2026-03-01", "3"]),  # 정상: 삽입된다
        PasteRow(None, ["2026-01-01", "4"]),  # 기간 충돌
    ]
    # 새 행은 값 목록이 다르므로 열 목록을 맞춘다.
    cols = [fx.sales]
    rows = [rows[0], rows[1]]
    with pytest.raises(AppError) as error:
        paste(pg, fx, cols, rows)
    assert error.value.code == "PASTE_CONFLICT"
    assert (stored_values(pg, fx, fx.sales), stored_values(pg, fx, fx.period)) == before
    cols = [fx.period, fx.sales]
    mixed = [
        PasteRow(a["row_id"], ["2026-01-01", "100"], ["2026-01-01", "1"]),
        PasteRow(None, ["2026-03-01", "3"]),
        PasteRow(None, ["2026-01-01", "4"]),
    ]
    with pytest.raises(AppError) as error:
        paste(pg, fx, cols, mixed)
    assert error.value.code == "PASTE_CONFLICT"
    assert [c["kind"] for c in error.value.details["conflicts"]] == ["period"]
    assert (stored_values(pg, fx, fx.sales), stored_values(pg, fx, fx.period)) == before


# --- 오류 변환 ----


def test_real_deadlock_is_a_lock_conflict(pg):
    """서로 반대 순서로 행을 갱신하면 PostgreSQL이 교착을 끊는다(40P01): 순서를 고정하는 이유."""
    fx = make(pg, base=False)
    rows = [create(pg, fx, {fx.sales: "1"})[0]["row_id"] for _ in range(2)]
    with Session(pg.engine) as session:
        context = dataset_service.read_row_context(session, fx.id)
    tbl = entry_repo.dynamic_table(context)
    step = threading.Barrier(2)

    def go(first: int, second: int):
        def run():
            with Session(pg.engine) as session:
                entry_repo.update_guarded(session, tbl, first, {fx.sales: (Decimal(1), Decimal(2))})
                step.wait(timeout=5)
                entry_repo.update_guarded(
                    session, tbl, second, {fx.sales: (Decimal(1), Decimal(2))}
                )
                session.commit()

        return run

    workers = run_together([go(rows[0], rows[1]), go(rows[1], rows[0])])
    errors = [w.error for w in workers if w.error is not None]
    assert len(errors) == 1 and sqlstate(errors[0]) == "40P01" and is_lock_conflict(errors[0])


def test_write_wrapper_maps_lock_errors_to_write_busy_and_rolls_back(pg):
    for state in ("55P03", "40P01"):
        error = DBAPIError("stmt", {}, Exception({"C": state}))
        with Session(pg.engine) as session:
            with pytest.raises(AppError) as raised, entry_service._row_write(session):
                raise error
            assert (raised.value.code, raised.value.status_code) == ("WRITE_BUSY", 503)
            assert raised.value.details == {"retry_after": 2}
    other = DBAPIError("stmt", {}, Exception({"C": "23505"}))
    with Session(pg.engine) as session:
        with pytest.raises(DBAPIError), entry_service._row_write(session):
            raise other


# --- 행 쓰기 ↔ 정의 변경 ----


def test_row_write_holds_for_share_on_the_dataset_and_writes_do_not_block_each_other(
    pg, hold_inserts
):
    entered, release, _ = hold_inserts
    fx = make(pg)
    holder = named("holder", lambda: create(pg, fx, {fx.period: "2026-01-01"}))
    holder.start()
    assert entered.wait(timeout=10)
    try:
        # 다른 행 쓰기는 기다리지 않는다(FOR SHARE끼리 호환).
        started = time.monotonic()
        create(pg, fx, {fx.period: "2026-02-01"})
        assert time.monotonic() - started < 1.0
        # 정의 변경용 잠금(FOR NO KEY UPDATE)은 바로 얻지 못한다 = 행 쓰기가 FOR SHARE를 쥐고 있다.
        with pytest.raises(DBAPIError) as error, Session(pg.engine) as session:
            session.execute(
                sa.select(datasets.c.id)
                .where(datasets.c.id == fx.id)
                .with_for_update(key_share=True, nowait=True)
            )
        assert sqlstate(error.value) == "55P03"
    finally:
        release.set()
        holder.join(timeout=10)
    assert holder.error is None


def test_setting_the_base_column_after_a_racing_insert_is_dataset_has_rows(pg, hold_inserts):
    """기준 날짜 열 지정의 "행이 0개" 확인과 INSERT 경쟁: INSERT가 끝난 뒤에야 확인이 실행된다."""
    entered, release, _ = hold_inserts
    fx = make(pg, base=False)
    holder = named("holder", lambda: create(pg, fx, {fx.sales: "5", fx.period: "2026-01-15"}))
    holder.start()
    assert entered.wait(timeout=10)

    def set_base():
        with Session(pg.engine) as session:
            return dataset_service.update_dataset(
                session,
                DefinitionHooks(),
                fx.id,
                expected_version=1,
                name=None,
                date_unit=None,
                base_given=True,
                base_date_column_id=fx.period,
            )

    definer = named("definer", set_base)
    definer.start()
    wait_for_lock_waiter(pg.engine)
    assert definer.is_alive(), "정의 변경은 진행 중인 행 쓰기(FOR SHARE)를 기다려야 한다"
    release.set()
    holder.join(timeout=10)
    definer.join(timeout=10)
    assert holder.error is None
    assert isinstance(definer.error, AppError) and definer.error.code == "DATASET_HAS_ROWS"
    assert definer.error.status_code == 422
    assert len(stored_values(pg, fx, fx.sales)) == 1


def test_changing_the_date_unit_after_a_racing_insert_is_dataset_has_rows(pg, hold_inserts):
    entered, release, _ = hold_inserts
    fx = make(pg, base=True, unit="month")
    holder = named("holder", lambda: create(pg, fx, {fx.period: "2026-03-01"}))
    holder.start()
    assert entered.wait(timeout=10)

    def change_unit():
        with Session(pg.engine) as session:
            return dataset_service.update_dataset(
                session,
                DefinitionHooks(),
                fx.id,
                expected_version=current_version(pg, fx),
                name=None,
                date_unit="day",
                base_given=False,
                base_date_column_id=None,
            )

    definer = named("definer", change_unit)
    definer.start()
    wait_for_lock_waiter(pg.engine)
    release.set()
    holder.join(timeout=10)
    definer.join(timeout=10)
    assert isinstance(definer.error, AppError) and definer.error.code == "DATASET_HAS_ROWS"
    assert len(stored_values(pg, fx, fx.period)) == 1


def test_insert_waiting_for_a_definition_change_gets_version_mismatch(pg):
    fx = make(pg)
    version = current_version(pg, fx)
    entered, release = threading.Event(), threading.Event()
    definer = Worker(
        add_column_call(
            pg.engine, fx.id, "새 열", blocking_hooks(entered, release, wait=15), version
        )
    )
    definer.start()
    assert entered.wait(timeout=5)
    writer = Worker(lambda: create(pg, fx, {fx.period: "2026-01-01"}, version=version))
    writer.start()
    wait_for_lock_waiter(pg.engine)
    assert writer.is_alive(), "행 쓰기(FOR SHARE)는 진행 중인 정의 변경을 기다려야 한다"
    release.set()
    definer.join(timeout=10)
    writer.join(timeout=10)
    assert definer.error is None
    assert isinstance(writer.error, AppError)
    assert (writer.error.code, writer.error.status_code) == ("DEFINITION_VERSION_MISMATCH", 409)
    assert writer.error.details == {"current_version": version + 1}
    assert stored_values(pg, fx, fx.period) == []  # 쓰지 않았다


def test_insert_waiting_longer_than_the_limit_for_a_definition_change_is_write_busy(pg):
    fx = make(pg)
    version = current_version(pg, fx)
    entered, release = threading.Event(), threading.Event()
    definer = Worker(
        add_column_call(
            pg.engine, fx.id, "새 열", blocking_hooks(entered, release, wait=15), version
        )
    )
    definer.start()
    assert entered.wait(timeout=5)
    writer = Worker(lambda: create(pg, fx, {fx.period: "2026-01-01"}, version=version))
    writer.start()
    writer.join(timeout=15)
    assert isinstance(writer.error, AppError) and writer.error.code == "WRITE_BUSY"
    assert ROW_LOCK_SECONDS * 0.8 <= writer.elapsed < ROW_LOCK_SECONDS + 3
    release.set()
    definer.join(timeout=10)
    assert definer.error is None


def test_definition_change_waits_for_a_row_write_then_proceeds(pg, hold_inserts):
    entered, release, _ = hold_inserts
    fx = make(pg)
    holder = named("holder", lambda: create(pg, fx, {fx.period: "2026-01-01"}))
    holder.start()
    assert entered.wait(timeout=10)
    version = current_version(pg, fx)
    definer = Worker(add_column_call(pg.engine, fx.id, "열 하나", DefinitionHooks(), version))
    definer.start()
    wait_for_lock_waiter(pg.engine)
    assert definer.is_alive()
    release.set()
    holder.join(timeout=10)
    definer.join(timeout=10)
    assert holder.error is None and definer.error is None
    assert definer.result.def_version == version + 1


# --- 굶음: 실제 행 쓰기 경로 ----


def test_continuous_row_writes_overtake_a_waiting_definition_change(pg, hold_inserts):
    """1b 굶음 관찰을 실제 행 쓰기 경로(`create_row`의 `FOR SHARE`)로 다시 확인한다.

    행 쓰기 H1이 쥔 동안 정의 변경 D가 기다리고, 그 사이 새 행 쓰기 H2가 들어온다. **관찰
    (PostgreSQL 16.10): H2는 D를 앞질러 즉시 끝난다.** D는 정의 변경 `lock_timeout`(1초)에서 503
    `DEFINITION_BUSY`로 끝난다. 행 쓰기가 계속 이어지면 정의 변경(열 추가 등)은 "다시 시도"만 반복할
    수 있다(무한 대기는 없다). 관찰이 달라지면 이 단정이 깨진다.
    """
    entered, release, entered2 = hold_inserts
    fx = make(pg)
    version = current_version(pg, fx)
    h1 = named("holder", lambda: create(pg, fx, {fx.period: "2026-01-01"}))
    h1.start()
    assert entered.wait(timeout=10)
    definer = Worker(
        add_column_call(pg.engine, fx.id, "굶는 정의 변경", DefinitionHooks(), version)
    )
    definer.start()
    wait_for_lock_waiter(pg.engine)  # D가 실제로 H1을 기다리기 시작한 뒤
    h2 = named("holder2", lambda: create(pg, fx, {fx.period: "2026-02-01"}, version=version))
    h2.start()
    # H2가 FOR SHARE를 얻었는가. 느린 CI에서 거짓 실패하지 않게 여유를 두되(5초), D가 한도(1초)로
    # 끝나기를 기다렸다가 얻은 경우(= D 뒤에 줄 섬)는 앞지르기로 세지 않는다.
    overtook = entered2.wait(timeout=5) and definer.is_alive()
    definer.join(timeout=10)  # H1·H2가 쥔 채로 D의 lock_timeout을 기다린다
    release.set()
    h1.join(timeout=10)
    h2.join(timeout=10)
    assert not definer.is_alive(), "정의 변경이 한도를 넘어 계속 기다린다"
    assert h1.error is None and h2.error is None, codes([h1, h2])
    assert overtook, "관찰이 달라졌다: H2가 D 뒤에 줄을 섰다"
    assert isinstance(definer.error, AppError) and definer.error.code == "DEFINITION_BUSY"
    print(
        f"[starvation/entry] 뒤 행 쓰기(H2)가 정의 변경(D)을 앞질러 FOR SHARE를 얻음={overtook}, "
        f"D=DEFINITION_BUSY, 대기 {definer.elapsed:.2f}s"
    )
    assert len(stored_values(pg, fx, fx.period)) == 2


# --- 느린 본문이 연결 풀을 붙들지 않는다 ----


def test_slow_paste_bodies_do_not_exhaust_the_connection_pool(pg, make_settings):
    """권한 검사 뒤 본문을 읽는 동안 DB 연결을 쥐지 않는다(풀은 `POOL_SIZE`+`POOL_MAX_OVERFLOW`).

    청크를 천천히 보내는 붙여넣기 요청을 풀 최대치보다 많이(최대치 + 3개) 걸어 둔 채로
    `/api/me`와 `/api/health/db`가 제때 응답해야 한다. 권한 검사가 연 트랜잭션을 돌려주지 않으면
    풀 최대치 요청이 연결을 모두 쥐어 다른 요청이 풀 대기(기본 30초)에 빠진다.
    """
    import asyncio
    from urllib.parse import quote

    import httpx

    from app.auth.stub import STUB_COOKIE
    from app.db import POOL_MAX_OVERFLOW, POOL_SIZE
    from app.main import create_app

    fx = make(pg)
    settings = make_settings(AUTH_STUB_ENABLED="true", APP_ENV="test")
    app = create_app(settings, engine=pg.engine)
    release = asyncio.Event
    slow_count = POOL_SIZE + POOL_MAX_OVERFLOW + 3
    cookies = {STUB_COOKIE: quote("entry", safe="")}

    async def run() -> None:
        gate = release()
        started = 0

        async def slow_body():
            nonlocal started
            started += 1
            yield b'{"expected_version": 1, '
            await gate.wait()
            yield b'"column_ids": [], "rows": []}'

        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://t", cookies=cookies
            ) as client:
                slow = [
                    asyncio.create_task(
                        client.post(
                            f"/api/datasets/{fx.id}/rows/paste",
                            content=slow_body(),
                            headers={"content-type": "application/json"},
                        )
                    )
                    for _ in range(slow_count)
                ]
                try:
                    deadline = asyncio.get_running_loop().time() + 10
                    while started < slow_count and asyncio.get_running_loop().time() < deadline:
                        await asyncio.sleep(0.05)
                    await asyncio.sleep(0.5)  # 권한 검사를 지나 본문을 기다리는 상태가 되게 한다
                    assert started == slow_count
                    for path in ("/api/me", "/api/health/db"):
                        response = await asyncio.wait_for(client.get(path), timeout=5)
                        assert response.status_code == 200, (path, response.text)
                finally:
                    gate.set()
                    await asyncio.gather(*slow, return_exceptions=True)

    asyncio.run(run())
