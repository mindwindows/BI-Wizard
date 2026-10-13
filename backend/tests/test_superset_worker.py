"""동기화 작업(상태 기계·큐·서킷 브레이커·시작 대조·복구) 시험. DB(sqlite, pg)와 가짜 Superset을
쓴다."""

import logging
import time

import httpx
import pytest
import sqlalchemy as sa

from app.config import Settings
from app.db_metadata import superset_datasets, teams
from app.superset.constants import SYNC_DEBOUNCE_SECONDS
from app.superset.errors import summarize
from app.superset.runtime import build_superset_services
from tests.conftest import Db
from tests.fake_superset import new_fake
from tests.superset_helpers import ISSUER, SERVICE, SUPERSET_ENV, Clock, settled


@pytest.fixture
def fake():
    return new_fake()


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def superset_settings(make_settings) -> Settings:
    return make_settings(AUTH_STUB_ENABLED="true", APP_ENV="test", **SUPERSET_ENV)


@pytest.fixture
def services(superset_settings, fake, clock, db: Db):
    built = build_superset_services(
        superset_settings,
        transport=fake.transport,
        clock=clock,
        health_interval=0.02,
        retry_interval=0.05,
    )
    assert built is not None
    built.sync.bind(db.engine)
    yield built
    built.stop()


@pytest.fixture
def sync(services):
    return services.sync


def make_dataset(db: Db, fake, *, team="영업팀", name="월간", labels=("매출", "비용")):
    team_id = db.add_team(f"t{len(db.rows(teams)) + 1}", team)
    owner = db.add_user(f"owner{team_id}")
    dataset_id = db.add_dataset(team_id, name, owner)
    column_ids = [db.add_column(dataset_id, label, position=i) for i, label in enumerate(labels)]
    fake.views[dataset_id] = ["team", "row_id", *(f"c_{cid}" for cid in column_ids)]
    return dataset_id, team_id, column_ids


def row(db: Db, dataset_id: int):
    rows = [r for r in db.rows(superset_datasets) if r["dataset_id"] == dataset_id]
    return rows[0] if rows else None


def test_request_only_marks_pending_and_queues_without_calling_superset(db, fake, sync):
    dataset_id, _, _ = make_dataset(db, fake)
    fake.slow = True  # Superset이 응답하지 않아도 요청 처리는 영향이 없다
    sync.request_dataset_sync(dataset_id)
    assert fake.calls == []  # 요청 처리 중에는 Superset을 부르지 않는다(P4)
    current = row(db, dataset_id)
    assert current["sync_status"] == "pending"
    assert current["display_name"] == "[영업팀] 월간"
    assert current["superset_dataset_id"] is None
    assert sync.pending_ids() == [dataset_id]


def test_queue_merges_duplicate_requests(db, fake, sync):
    dataset_id, _, _ = make_dataset(db, fake)
    for _ in range(5):
        sync.request_dataset_sync(dataset_id)
    assert sync.pending_ids() == [dataset_id]
    assert sync.drain() == 1
    assert len(fake.datasets) == 1


def test_drain_registers_and_records_status(db, fake, sync):
    dataset_id, _, column_ids = make_dataset(db, fake)
    sync.request_dataset_sync(dataset_id)
    sync.drain()
    current = row(db, dataset_id)
    assert current["sync_status"] == "registered"
    assert current["superset_dataset_id"] == 1
    assert current["synced_at"] is not None and current["last_error"] is None
    labels = {c["column_name"]: c["verbose_name"] for c in fake.datasets[1]["columns"]}
    assert labels == {
        "team": "팀",
        "row_id": "행 번호",
        f"c_{column_ids[0]}": "매출",
        f"c_{column_ids[1]}": "비용",
    }


def test_resync_after_definition_change_keeps_one_dataset(db, fake, sync):
    dataset_id, _, column_ids = make_dataset(db, fake)
    sync.request_dataset_sync(dataset_id)
    sync.drain()
    ids_before = [c["id"] for c in fake.datasets[1]["columns"]]
    new_column = db.add_column(dataset_id, "이익", position=5)  # 정의 변경(열 추가)
    fake.views[dataset_id].append(f"c_{new_column}")
    sync.request_dataset_sync(dataset_id)
    assert row(db, dataset_id)["sync_status"] == "pending"
    sync.drain()
    assert row(db, dataset_id)["sync_status"] == "registered"
    assert len(fake.datasets) == 1
    assert [c["id"] for c in fake.datasets[1]["columns"]][: 3 + 1] == ids_before
    assert len(fake.datasets[1]["columns"]) == 5
    labels = {c["column_name"]: c["verbose_name"] for c in fake.datasets[1]["columns"]}
    assert labels[f"c_{new_column}"] == "이익" and labels[f"c_{column_ids[0]}"] == "매출"


def test_superset_down_marks_failed_with_safe_reason_then_recovers_without_duplicates(
    db, fake, sync, caplog
):
    caplog.set_level(logging.DEBUG)
    dataset_id, _, _ = make_dataset(db, fake)
    fake.up = False
    sync.request_dataset_sync(dataset_id)
    sync.drain()
    current = row(db, dataset_id)
    assert current["sync_status"] == "failed"
    assert current["last_error"] == summarize("UNAVAILABLE_CONNECT")
    for secret in (SERVICE[1], ISSUER[1], "superset:8088", "SELECT", "http"):
        assert secret not in current["last_error"]
    fake.up = True
    assert sync.requeue_unavailable() == 1  # 연결 문제로 실패한 것만 자동 재시도한다
    sync.drain()
    assert row(db, dataset_id)["sync_status"] == "registered"
    assert len(fake.datasets) == 1
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert SERVICE[1] not in text and "superset:8088" not in text


def test_non_connection_failures_are_not_auto_retried(db, fake, sync):
    dataset_id, _, _ = make_dataset(db, fake)
    sync.request_dataset_sync(dataset_id)
    sync.drain()
    fake.foreign_datasets.add(1)
    sync.request_dataset_sync(dataset_id)
    sync.drain()
    assert row(db, dataset_id)["last_error"] == summarize("NOT_OWNER")
    assert sync.requeue_unavailable() == 0  # 사람이 보고 다시 시도해야 한다(E2)


def test_circuit_breaker_stops_calling_superset_after_consecutive_failures(db, fake, sync, clock):
    ids = [make_dataset(db, fake, team=f"팀{i}", name=f"데이터{i}")[0] for i in range(5)]
    fake.up = False
    for dataset_id in ids:
        sync.request_dataset_sync(dataset_id)
    sync.drain()
    assert len(fake.calls) == 3  # 연속 3회 실패 뒤에는 Superset을 부르지 않는다
    for dataset_id in ids:
        assert row(db, dataset_id)["last_error"] == summarize("UNAVAILABLE_CONNECT")
    # 쿨다운이 지나고 Superset이 돌아오면 다시 시도해 복구한다.
    clock.advance(31)
    fake.up = True
    sync.requeue_unavailable()
    sync.drain()
    assert all(row(db, i)["sync_status"] == "registered" for i in ids)
    assert len(fake.datasets) == 5


def test_local_internal_error_does_not_consume_the_half_open_probe(
    db, fake, sync, clock, monkeypatch
):
    dataset_id, _, _ = make_dataset(db, fake)
    for _ in range(3):
        sync._breaker.record_failure()
    clock.advance(31)  # 반열림: 시험 호출 한 건

    def boom(*args, **kwargs):
        raise RuntimeError("local failure")

    monkeypatch.setattr("app.superset.worker.sync_dataset", boom)
    sync.request_dataset_sync(dataset_id)
    sync.drain()
    assert row(db, dataset_id)["last_error"] == summarize("INTERNAL")
    assert sync._breaker.is_open  # 성공으로 닫히지 않았다
    assert sync._breaker.allow()  # 시험 호출 자리가 풀렸다
    assert fake.calls == []


def test_change_during_processing_keeps_pending_and_runs_again(db, fake, sync):
    dataset_id, _, _ = make_dataset(db, fake)
    sync.request_dataset_sync(dataset_id)

    def interrupt(call):
        sync.request_dataset_sync(dataset_id)  # 처리 도중 정의가 또 바뀌었다
        return httpx.Response(200, json={"id": 1, "result": {}})

    fake.respond_once(lambda c: c.method == "PUT" and c.path == "/api/v1/dataset/1", interrupt)
    assert sync.process_next(force=True) is True
    assert fake.inject == []  # 끼어들기가 실제로 실행됐다
    assert row(db, dataset_id)["sync_status"] == "pending"  # 낡은 결과를 registered로 쓰지 않는다
    assert sync.pending_ids() == [dataset_id]
    sync.drain()
    assert row(db, dataset_id)["sync_status"] == "registered"
    assert len(fake.datasets) == 1


def test_team_rename_updates_every_dataset_of_the_team_only(db, fake, sync):
    first, team_id, _ = make_dataset(db, fake, team="영업팀", name="월간")
    owner = db.add_user("owner_x")
    second = db.add_dataset(team_id, "주간", owner)
    fake.views[second] = ["team", "row_id"]
    other, _, _ = make_dataset(db, fake, team="인사팀", name="월간")
    for dataset_id in (first, second, other):
        sync.request_dataset_sync(dataset_id)
    sync.drain()
    ids_before = {d: row(db, d)["superset_dataset_id"] for d in (first, second, other)}
    with db.writer.begin() as conn:
        conn.execute(sa.update(teams).where(teams.c.id == team_id).values(name="영업1팀"))
    sync.request_team_sync(team_id)  # 팀 단위 요청
    assert set(sync.pending_ids()) == {first, second}
    sync.drain()
    assert {"[영업1팀] 월간", "[영업1팀] 주간", "[인사팀] 월간"} == {
        d["table_name"] for d in fake.datasets.values()
    }
    assert {d: row(db, d)["superset_dataset_id"] for d in (first, second, other)} == ids_before
    assert row(db, first)["display_name"] == "[영업1팀] 월간"


def test_missing_dataset_is_skipped_quietly(db, fake, sync):
    sync.request_dataset_sync(9999)
    assert sync.drain() == 1
    assert fake.calls == [] and db.rows(superset_datasets) == []


def test_requests_without_bound_engine_do_not_raise(superset_settings, fake, clock):
    unbound = build_superset_services(superset_settings, transport=fake.transport, clock=clock)
    assert unbound is not None
    unbound.sync.request_dataset_sync(1)
    unbound.sync.request_team_sync(1)
    assert unbound.sync.pending_ids() == [1]
    unbound.stop()


# --- 시작 대조(결정 E ①) ----


def test_reconcile_queues_missing_pending_failed_and_drifted_registered_only(db, fake, sync):
    a, _, _ = make_dataset(db, fake, team="가", name="등록 없음")
    b, _, _ = make_dataset(db, fake, team="나", name="정상")
    c, _, _ = make_dataset(db, fake, team="다", name="열 변경 누락")
    d, _, _ = make_dataset(db, fake, team="라", name="실패")
    for dataset_id in (b, c, d):
        sync.request_dataset_sync(dataset_id)
    sync.drain()
    with db.writer.begin() as conn:  # d는 이전 실행에서 실패한 상태
        conn.execute(
            sa.update(superset_datasets)
            .where(superset_datasets.c.dataset_id == d)
            .values(sync_status="failed", last_error=summarize("NOT_OWNER"))
        )
    # c: 커밋 직후 크래시로 Superset에 열 변경이 반영되지 않았다(정의에는 열이 하나 더 있다).
    new_column = db.add_column(c, "이익", position=9)
    fake.views[c].append(f"c_{new_column}")
    puts_before = fake.count("PUT", "/api/v1/dataset/")
    assert sync.reconcile_all() == 3
    assert set(sync.pending_ids()) == {a, c, d}  # 정상인 b는 넣지 않는다
    assert fake.count("PUT", "/api/v1/dataset/") == puts_before  # 대조는 읽기만 한다
    sync.drain()
    assert all(row(db, i)["sync_status"] == "registered" for i in (a, b, c, d))
    assert len(fake.datasets) == 4


def test_reconcile_recreates_dataset_deleted_in_superset(db, fake, sync):
    dataset_id, _, _ = make_dataset(db, fake)
    sync.request_dataset_sync(dataset_id)
    sync.drain()
    del fake.datasets[1]  # 관리자가 Superset에서 지웠다
    assert sync.reconcile_all() == 1
    sync.drain()
    current = row(db, dataset_id)
    assert current["sync_status"] == "registered" and current["superset_dataset_id"] == 2


def test_reconcile_with_superset_down_raises_unavailable_for_a_later_retry(db, fake, sync):
    from app.superset.errors import SupersetUnavailable

    dataset_id, _, _ = make_dataset(db, fake)
    sync.request_dataset_sync(dataset_id)
    sync.drain()
    fake.up = False
    with pytest.raises(SupersetUnavailable):
        sync.reconcile_all()


# --- 작업 루프(주 스레드에서 한 단계씩 돌려 확인한다) ----


class StopWhen:
    """`threading.Event` 대역: 조건이 참이 되거나 반복 한도에 닿으면 멈춘다."""

    def __init__(self, condition, limit=2000):
        self.condition = condition
        self.limit = limit
        self.iterations = 0

    def is_set(self):
        self.iterations += 1
        return self.iterations > self.limit or bool(self.condition())

    def wait(self, timeout=None):
        time.sleep(min(timeout or 0, 0.005))
        return self.is_set()

    def set(self):
        self.limit = 0

    def clear(self):
        pass


def run_loop(sync, until):
    stop = StopWhen(until)
    sync._stop = stop
    sync._loop()
    assert stop.iterations <= stop.limit, "조건이 반복 한도 안에 참이 되지 않았다"


@pytest.fixture
def loop_sync(superset_settings, fake, db: Db):
    """실제 시계로 타이머가 흐르는 동기화 부품(루프는 주 스레드에서 돌린다)."""
    built = build_superset_services(
        superset_settings,
        transport=fake.transport,
        health_interval=0.01,
        retry_interval=0.02,
        breaker_cooldown=0.05,
        poll_seconds=0.005,
        debounce_seconds=0.0,  # 이 부품을 쓰는 시험은 지연 없이 바로 처리되길 기대한다
    )
    assert built is not None
    built.sync.bind(db.engine)
    yield built.sync
    built.stop()


def test_loop_waits_for_health_then_reconciles_and_registers(db, fake, loop_sync):
    dataset_id, _, _ = make_dataset(db, fake)
    fake.health_ok = False
    run_loop(loop_sync, lambda: fake.count("GET", "/health") >= 3)
    assert row(db, dataset_id) is None  # 준비 전에는 아무것도 하지 않는다
    assert fake.count("POST", "/api/v1/security/login") == 0
    assert loop_sync.startup_pending is True
    fake.health_ok = True
    run_loop(
        loop_sync,
        lambda: (r := row(db, dataset_id)) is not None and r["sync_status"] == "registered",
    )
    assert loop_sync.startup_pending is False
    assert len(fake.datasets) == 1


def test_loop_gives_up_waiting_for_health_after_the_max_wait_but_keeps_retrying(
    superset_settings, fake, db
):
    built = build_superset_services(
        superset_settings,
        transport=fake.transport,
        health_interval=0.01,
        health_max_wait=0.03,
        retry_interval=0.02,
        poll_seconds=0.005,
        debounce_seconds=0.0,
    )
    assert built is not None
    built.sync.bind(db.engine)
    fake.health_ok = False
    run_loop(built.sync, lambda: not built.sync.startup_pending)
    assert built.sync.startup_pending is False  # 포기한 뒤에는 주기 재시도가 이어서 처리한다
    built.stop()


def test_loop_recovers_failed_unavailable_datasets_on_its_own(db, fake, loop_sync):
    dataset_id, _, _ = make_dataset(db, fake)
    fake.up = False
    loop_sync.request_dataset_sync(dataset_id)
    run_loop(
        loop_sync,
        lambda: (r := row(db, dataset_id)) is not None and r["sync_status"] == "failed",
    )
    fake.up = True  # 모의 서버를 다시 올린다
    run_loop(loop_sync, lambda: row(db, dataset_id)["sync_status"] == "registered")
    assert len(fake.datasets) == 1  # 중복 등록 없음


def test_loop_survives_unexpected_errors(db, fake, loop_sync, monkeypatch, caplog):
    dataset_id, _, _ = make_dataset(db, fake)
    calls = {"n": 0}
    original = loop_sync._process

    def flaky(dataset_id_):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom with secret password=hunter2")
        original(dataset_id_)

    monkeypatch.setattr(loop_sync, "_process", flaky)
    caplog.set_level(logging.DEBUG)
    loop_sync.request_dataset_sync(dataset_id)
    loop_sync._enqueue([dataset_id])
    run_loop(loop_sync, lambda: calls["n"] >= 1)
    loop_sync.request_dataset_sync(dataset_id)
    run_loop(
        loop_sync,
        lambda: (r := row(db, dataset_id)) is not None and r["sync_status"] == "registered",
    )
    assert "RuntimeError" in caplog.text  # 클래스 이름만 남는다
    for forbidden in ("secret", "hunter2", "boom", "http://", "https://", "Traceback"):
        assert forbidden not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


def test_thread_stops_cleanly_and_start_is_idempotent(loop_sync):
    loop_sync.start()
    loop_sync.start()
    loop_sync.stop()
    loop_sync.stop()


def test_real_thread_registers_in_the_background(db, fake, loop_sync):
    """실제 작업 스레드(SQLite는 연결 하나를 스레드가 공유하므로 PostgreSQL 변형에서만 돈다)."""
    if db.kind == "sqlite":
        pytest.skip("SQLite 시험 DB는 연결 하나를 스레드 사이에 공유한다(PostgreSQL 변형에서 확인)")
    dataset_id, _, _ = make_dataset(db, fake)
    loop_sync.start()
    try:
        loop_sync.request_dataset_sync(dataset_id)
        assert settled(
            lambda: (r := row(db, dataset_id)) is not None and r["sync_status"] == "registered"
        )
    finally:
        loop_sync.stop()


# --- 디바운스(not_before): 같은 데이터셋의 요청은 지연 안에 모여 Superset 호출 한 번이 된다 ----

DEBOUNCE = SYNC_DEBOUNCE_SECONDS


def mutating_calls(fake) -> int:
    return sum(
        1
        for c in fake.calls
        if c.method in ("POST", "PUT") and c.path.startswith("/api/v1/dataset")
    )


def test_a_burst_of_requests_inside_the_delay_is_one_superset_sync(db, fake, sync, clock):
    burst, _, _ = make_dataset(db, fake, team="가", name="연타")
    single, _, _ = make_dataset(db, fake, team="나", name="한 번")
    sync.request_dataset_sync(single)
    clock.advance(DEBOUNCE)
    assert sync.process_next() is True
    per_sync = mutating_calls(fake)  # 한 번의 동기화가 보내는 쓰기 호출 수
    assert per_sync > 0
    fake.calls.clear()
    for _ in range(20):  # 지연 안에 20번 연달아 요청
        sync.request_dataset_sync(burst)
        clock.advance(0.1)
    assert sync.pending_ids() == [burst]
    assert sync.process_next() is False and fake.calls == []  # 지연 중에는 Superset을 부르지 않는다
    assert row(db, burst)["sync_status"] == "pending"
    clock.advance(DEBOUNCE)
    assert sync.process_next() is True
    assert sync.process_next() is False
    assert mutating_calls(fake) == per_sync  # 20건이 한 번의 동기화로 합쳐졌다
    assert row(db, burst)["sync_status"] == "registered"
    assert len(fake.datasets) == 2


def test_the_delay_window_starts_at_the_first_request_and_is_not_extended(db, fake, sync, clock):
    dataset_id, _, _ = make_dataset(db, fake)
    sync.request_dataset_sync(dataset_id)
    clock.advance(DEBOUNCE - 0.2)
    sync.request_dataset_sync(dataset_id)  # 창이 끝나기 직전의 요청이 창을 늘리지 않는다
    assert sync.process_next() is False
    clock.advance(0.2)
    assert sync.process_next() is True
    assert row(db, dataset_id)["sync_status"] == "registered"


def test_delays_are_independent_per_dataset(db, fake, sync, clock):
    first, _, _ = make_dataset(db, fake, team="가", name="먼저")
    second, _, _ = make_dataset(db, fake, team="나", name="나중")
    sync.request_dataset_sync(first)
    clock.advance(2.0)
    sync.request_dataset_sync(second)
    clock.advance(DEBOUNCE - 2.0)  # first의 지연만 끝났다
    assert sync.process_next() is True
    assert row(db, first)["sync_status"] == "registered"
    assert row(db, second)["sync_status"] == "pending"
    assert sync.process_next() is False and sync.pending_ids() == [second]
    clock.advance(2.0)
    assert sync.process_next() is True
    assert row(db, second)["sync_status"] == "registered"


def test_a_delayed_dataset_does_not_block_a_ready_one_behind_it(db, fake, sync, clock):
    delayed, _, _ = make_dataset(db, fake, team="가", name="지연")
    ready, _, _ = make_dataset(db, fake, team="나", name="즉시")
    sync.request_dataset_sync(delayed)
    sync._enqueue([ready])  # 지연 없는 경로(시작 대조 등)가 뒤에 넣은 항목
    assert sync.pending_ids() == [delayed, ready]  # 지연된 항목이 큐 앞에 있다
    assert sync.process_next() is True  # 앞의 지연 항목을 건너뛰고 준비된 것을 처리한다
    assert row(db, ready)["sync_status"] == "registered"
    assert row(db, delayed)["sync_status"] == "pending"
    assert sync.process_next() is False


def test_startup_reconcile_and_unavailable_retry_are_not_held_back_by_the_delay(
    db, fake, sync, clock
):
    waiting, _, _ = make_dataset(db, fake, team="가", name="디바운스 중")
    retry, _, _ = make_dataset(db, fake, team="나", name="재시도")
    sync.request_dataset_sync(retry)
    fake.up = False
    sync.drain()  # retry는 연결 문제로 failed
    fake.up = True
    sync.request_dataset_sync(waiting)
    assert sync.process_next() is False  # waiting은 아직 지연 중이다
    assert sync.requeue_unavailable() == 1  # 자동 재시도 경로: 지연 없음
    assert sync.process_next() is True
    assert row(db, retry)["sync_status"] == "registered"
    assert sync.process_next() is False  # waiting은 여전히 지연 중
    assert sync.reconcile_all() == 1  # 시작 대조 경로: 지연 중인 항목을 당겨 온다
    assert sync.process_next() is True
    assert row(db, waiting)["sync_status"] == "registered"


def test_request_during_processing_reruns_after_its_own_delay_not_immediately(
    db, fake, sync, clock
):
    dataset_id, _, _ = make_dataset(db, fake)
    sync.request_dataset_sync(dataset_id)
    clock.advance(DEBOUNCE)

    def interrupt(call):
        sync.request_dataset_sync(dataset_id)  # 처리 도중 정의가 또 바뀌었다
        return httpx.Response(200, json={"id": 1, "result": {}})

    fake.respond_once(lambda c: c.method == "PUT" and c.path == "/api/v1/dataset/1", interrupt)
    assert sync.process_next() is True
    assert fake.inject == []
    assert row(db, dataset_id)["sync_status"] == "pending"  # 세대가 바뀌어 registered로 쓰지 않는다
    assert sync.pending_ids() == [dataset_id]
    assert sync.process_next() is False  # 재큐는 새 요청의 지연을 따른다
    clock.advance(DEBOUNCE)
    assert sync.process_next() is True
    assert row(db, dataset_id)["sync_status"] == "registered"
    assert len(fake.datasets) == 1


def test_team_rename_requests_are_delayed_per_dataset(db, fake, sync, clock):
    first, team_id, _ = make_dataset(db, fake, team="영업팀", name="월간")
    sync.request_team_sync(team_id)
    assert sync.pending_ids() == [first]
    assert sync.process_next() is False
    clock.advance(DEBOUNCE)
    assert sync.process_next() is True


def test_drain_skips_the_delay_for_tests_and_diagnostics(db, fake, sync, clock):
    dataset_id, _, _ = make_dataset(db, fake)
    sync.request_dataset_sync(dataset_id)
    assert sync.process_next() is False
    assert sync.drain() == 1
    assert row(db, dataset_id)["sync_status"] == "registered"


def test_loop_honors_the_delay_with_an_injected_clock(db, fake, superset_settings, clock):
    built = build_superset_services(
        superset_settings,
        transport=fake.transport,
        clock=clock,
        poll_seconds=0.001,
        retry_interval=10_000.0,
    )
    assert built is not None
    sync = built.sync
    sync.bind(db.engine)
    sync._startup_pending = False  # 시작 대조는 지연을 당기므로 이 시험에서는 끈다
    dataset_id, _, _ = make_dataset(db, fake)
    sync.request_dataset_sync(dataset_id)
    seen_before_delay: list[int] = []

    def condition():
        clock.advance(0.5)  # 루프가 한 바퀴 돌 때마다 시간이 0.5초 간다
        if clock() < 1000.0 + DEBOUNCE:
            seen_before_delay.append(len(fake.calls))
        r = row(db, dataset_id)
        return r is not None and r["sync_status"] == "registered"

    run_loop(sync, condition)
    assert seen_before_delay and set(seen_before_delay) == {0}  # 지연이 끝나기 전에는 호출 0건
    assert clock() >= 1000.0 + DEBOUNCE
    built.stop()


def test_real_thread_start_reconcile_registers_before_the_delay_ends(db, fake, superset_settings):
    """실제 스레드: 시작 대조가 지연 중인 항목을 당겨 오므로 3초를 기다리지 않고 등록된다."""
    if db.kind == "sqlite":
        pytest.skip("SQLite 시험 DB는 연결 하나를 스레드 사이에 공유한다(PostgreSQL 변형에서 확인)")
    built = build_superset_services(
        superset_settings,
        transport=fake.transport,
        health_interval=0.01,
        retry_interval=10_000.0,
        poll_seconds=0.005,
    )
    assert built is not None
    built.sync.bind(db.engine)
    dataset_id, _, _ = make_dataset(db, fake)
    built.sync.request_dataset_sync(dataset_id)
    started = time.monotonic()
    built.sync.start()
    try:
        assert settled(
            lambda: (r := row(db, dataset_id)) is not None and r["sync_status"] == "registered",
            timeout=SYNC_DEBOUNCE_SECONDS - 0.5,
        )
        assert time.monotonic() - started < SYNC_DEBOUNCE_SECONDS
    finally:
        built.stop()


def test_real_thread_stops_promptly_with_a_delayed_item_and_it_stays_pending(
    db, fake, superset_settings
):
    if db.kind == "sqlite":
        pytest.skip("SQLite 시험 DB는 연결 하나를 스레드 사이에 공유한다(PostgreSQL 변형에서 확인)")
    built = build_superset_services(
        superset_settings,
        transport=fake.transport,
        health_interval=0.01,
        retry_interval=10_000.0,
        poll_seconds=0.005,
    )
    assert built is not None
    built.sync.bind(db.engine)
    built.sync._startup_pending = False
    dataset_id, _, _ = make_dataset(db, fake)
    built.sync.start()
    built.sync.request_dataset_sync(dataset_id)
    time.sleep(0.2)  # 스레드가 지연 항목을 보고도 처리하지 않는 것을 확인할 시간
    started = time.monotonic()
    built.stop()
    assert time.monotonic() - started < 2.0  # 지연 때문에 종료가 막히지 않는다
    assert row(db, dataset_id)["sync_status"] == "pending"  # 다음 시작 대조가 처리한다
    assert fake.count("POST", "/api/v1/dataset/") == 0
