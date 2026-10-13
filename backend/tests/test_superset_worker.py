"""동기화 작업(상태 기계·큐·서킷 브레이커·시작 대조·복구) 시험. DB(sqlite, pg)와 가짜 Superset을
쓴다."""

import logging
import time

import httpx
import pytest
import sqlalchemy as sa

from app.config import Settings
from app.db_metadata import superset_datasets, teams
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


def test_change_during_processing_keeps_pending_and_runs_again(db, fake, sync):
    dataset_id, _, _ = make_dataset(db, fake)
    sync.request_dataset_sync(dataset_id)

    def interrupt(call):
        sync.request_dataset_sync(dataset_id)  # 처리 도중 정의가 또 바뀌었다
        return httpx.Response(200, json={"id": 1, "result": {}})

    fake.respond_once(lambda c: c.method == "PUT" and c.path == "/api/v1/dataset/1", interrupt)
    sync.process_next()
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


def test_loop_survives_unexpected_errors(db, fake, loop_sync, monkeypatch):
    dataset_id, _, _ = make_dataset(db, fake)
    calls = {"n": 0}
    original = loop_sync._process

    def flaky(dataset_id_):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom with secret password=hunter2")
        original(dataset_id_)

    monkeypatch.setattr(loop_sync, "_process", flaky)
    loop_sync.request_dataset_sync(dataset_id)
    loop_sync._enqueue([dataset_id])
    run_loop(loop_sync, lambda: calls["n"] >= 1)
    loop_sync.request_dataset_sync(dataset_id)
    run_loop(
        loop_sync,
        lambda: (r := row(db, dataset_id)) is not None and r["sync_status"] == "registered",
    )


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
