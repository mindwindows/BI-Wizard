"""정의 변경 동시성 시험(06 §5, 03c X-24, 07 §8). 실제 PostgreSQL(tmpfs 시험 DB) 필요.

확인하는 것:
- 같은 `expected_version`으로 동시에 정의를 바꾸면 한쪽만 이기고 다른 쪽은 409
  `DEFINITION_VERSION_MISMATCH`(`details.current_version`)다.
- 락 대기가 `lock_timeout`(코드 상수 1초)을 넘으면 503 `DEFINITION_BUSY`이고 트랜잭션이 정리된다.
- `FOR NO KEY UPDATE` 한 가지 잠금은 읽기와 FK 자식 INSERT(`FOR KEY SHARE`)를 막지 않는다. 행 쓰기가
  쓸 `FOR SHARE`는 정의 변경을 기다리고, 정의 변경도 `FOR SHARE` 보유자를 기다린다.
- `FOR SHARE`가 이어지는 굶음 시나리오에서도 정의 변경은 무한정 기다리지 않고 한도 안에 끝난다.
"""

import threading
import time
from collections.abc import Callable
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.auth.models import CurrentUser
from app.core.db_errors import sqlstate
from app.core.errors import AppError
from app.core.ports import DefinitionHooks
from app.dataset import definition, repo, service
from app.db_metadata import dataset_columns, datasets
from tests.conftest import Db

LOCK_TIMEOUT_SECONDS = 1.0  # definition.DEFINITION_LOCK_TIMEOUT 과 같은 값(아래 시험이 확인한다)


@pytest.fixture
def pg(pg_app_engine: Engine, pg_owner_engine: Engine, clean_pg) -> Db:
    return Db("pg", pg_app_engine, pg_owner_engine)


@pytest.fixture
def dataset_id(pg: Db) -> int:
    user = pg.add_user("definer", "정의 담당자")
    team = pg.add_team("team_a", "A팀")
    pg.add_member(team, user, "definer")
    return pg.add_dataset(team, "동시성", user)


class Worker(threading.Thread):
    """함수를 다른 스레드에서 실행하고 결과나 예외를 보관한다."""

    def __init__(self, target: Callable[[], Any]) -> None:
        super().__init__(daemon=True)
        self._target_fn = target
        self.result: Any = None
        self.error: BaseException | None = None
        self.elapsed = 0.0

    def run(self) -> None:
        started = time.monotonic()
        try:
            self.result = self._target_fn()
        except BaseException as error:
            self.error = error
        finally:
            self.elapsed = time.monotonic() - started


def wait_for_lock_waiter(engine: Engine, timeout: float = 10.0) -> None:
    """`pg_locks`에서 잠금을 얻지 못한 요청(`granted = false`)이 생길 때까지 폴링한다.

    고정 `sleep`으로 "정의 변경 D가 대기 중"이라고 가정하지 않기 위한 동기화다.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with engine.connect() as conn:
            waiting = conn.execute(sa.text("SELECT count(*) FROM pg_locks WHERE NOT granted"))
            if waiting.scalar_one() > 0:
                return
        time.sleep(0.02)
    raise AssertionError("잠금 대기자가 나타나지 않았다(pg_locks)")


def blocking_hooks(entered: threading.Event, release: threading.Event, wait: float):
    """정의 변경 안(락을 잡은 상태)에서 멈춰 서는 훅."""
    hooks = DefinitionHooks()

    def hook(session: Session, dataset: int) -> None:
        entered.set()
        assert release.wait(timeout=wait), "시험이 락 보유자를 풀어 주지 않았다"

    hooks.register(hook)
    return hooks


def creator_of(session: Session, dataset: int) -> CurrentUser:
    """데이터셋을 만든 사용자를 행위자로 쓴다(감사 기록의 행위자 FK가 실제 사용자여야 한다)."""
    user_id = session.execute(
        sa.select(datasets.c.created_by).where(datasets.c.id == dataset)
    ).scalar_one()
    session.rollback()  # 읽기 트랜잭션을 닫아 이어지는 정의 변경이 처음부터 시작하게 한다
    return CurrentUser(id=user_id, display_name="정의 담당자", is_active=True, is_admin=False)


def add_column_call(engine: Engine, dataset: int, name: str, hooks: DefinitionHooks, version=1):
    def call():
        with Session(engine) as session:
            return service.add_column(
                session,
                hooks,
                dataset,
                actor=creator_of(session, dataset),
                expected_version=version,
                display_name=name,
                column_type="text",
                required=False,
                raw_rules=None,
                raw_tag=None,
                position=None,
            )

    return call


def column_names(pg: Db, dataset: int) -> list[str]:
    return [r["display_name"] for r in pg.rows(dataset_columns) if r["dataset_id"] == dataset]


def test_lock_timeout_constant_matches_the_documented_value():
    assert definition.DEFINITION_LOCK_TIMEOUT == "1000ms"


def test_second_concurrent_change_with_the_same_version_gets_version_mismatch(pg, dataset_id):
    entered, release = threading.Event(), threading.Event()
    first = Worker(
        add_column_call(
            pg.engine, dataset_id, "먼저", blocking_hooks(entered, release, wait=10), version=1
        )
    )
    first.start()
    assert entered.wait(timeout=5), "첫 정의 변경이 락을 잡지 못했다"
    second = Worker(add_column_call(pg.engine, dataset_id, "나중", DefinitionHooks(), version=1))
    second.start()
    time.sleep(0.3)  # lock_timeout(1초)보다 짧게 두 번째가 기다리게 한다
    assert second.is_alive(), "두 번째는 행 잠금을 기다려야 한다"
    release.set()
    first.join(timeout=10)
    second.join(timeout=10)
    assert first.error is None and first.result.def_version == 2
    assert isinstance(second.error, AppError)
    assert second.error.code == "DEFINITION_VERSION_MISMATCH" and second.error.status_code == 409
    assert second.error.details == {"current_version": 2}
    assert column_names(pg, dataset_id) == ["먼저"]
    with pg.engine.connect() as conn:
        assert {
            c["name"] for c in sa.inspect(conn).get_columns(f"ds_{dataset_id}", schema="bi_data")
        } == {
            "row_id",
            f"c_{first.result.column['id']}",
        }
        row = conn.execute(sa.select(datasets.c.def_version).where(datasets.c.id == dataset_id))
        assert row.scalar_one() == 2


def test_many_concurrent_changes_exactly_one_wins_per_version(pg, dataset_id):
    barrier = threading.Barrier(4)

    def attempt(n: int):
        def call():
            barrier.wait(timeout=5)
            return add_column_call(pg.engine, dataset_id, f"열{n}", DefinitionHooks(), 1)()

        return Worker(call)

    workers = [attempt(n) for n in range(4)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=15)
    assert not any(w.is_alive() for w in workers), "교착"
    winners = [w for w in workers if w.error is None]
    losers = [w for w in workers if w.error is not None]
    assert len(winners) == 1 and len(losers) == 3
    for loser in losers:
        assert isinstance(loser.error, AppError)
        assert loser.error.code in {"DEFINITION_VERSION_MISMATCH", "DEFINITION_BUSY"}
    assert len(column_names(pg, dataset_id)) == 1


def test_lock_wait_over_the_timeout_is_definition_busy_and_cleans_up(pg, dataset_id):
    entered, release = threading.Event(), threading.Event()
    holder = Worker(
        add_column_call(
            pg.engine, dataset_id, "보유자", blocking_hooks(entered, release, wait=15), version=1
        )
    )
    holder.start()
    assert entered.wait(timeout=5)
    waiter = Worker(add_column_call(pg.engine, dataset_id, "대기자", DefinitionHooks(), version=1))
    waiter.start()
    waiter.join(timeout=10)
    assert not waiter.is_alive()
    assert isinstance(waiter.error, AppError)
    assert waiter.error.code == "DEFINITION_BUSY" and waiter.error.status_code == 503
    assert waiter.error.details == {"retry_after": 2}
    assert LOCK_TIMEOUT_SECONDS * 0.8 <= waiter.elapsed < LOCK_TIMEOUT_SECONDS + 3
    release.set()
    holder.join(timeout=10)
    assert holder.error is None
    assert column_names(pg, dataset_id) == ["보유자"]  # 대기자의 변경은 남지 않았다
    # 락이 풀린 뒤에는 다시 시도하면 된다.
    again = add_column_call(pg.engine, dataset_id, "대기자", DefinitionHooks(), version=2)()
    assert again.def_version == 3


def test_definition_change_lock_does_not_block_readers_or_fk_children(pg, dataset_id):
    entered, release = threading.Event(), threading.Event()
    holder = Worker(
        add_column_call(
            pg.engine, dataset_id, "보유자", blocking_hooks(entered, release, wait=15), version=1
        )
    )
    holder.start()
    assert entered.wait(timeout=5)
    user = CurrentUser(id=1, display_name="열람", is_active=True, is_admin=False)
    try:
        started = time.monotonic()
        with Session(pg.engine) as session:
            detail = service.get_dataset_detail(session, user, dataset_id)  # 평범한 읽기
            listing, total = service.list_datasets(session, user, team_id=None, limit=50, offset=0)
            assert repo.get_dataset(session, dataset_id) is not None
            # FOR KEY SHARE(FK 자식 INSERT가 부모 행에 거는 잠금)도 막히지 않는다.
            key_share = sa.select(datasets.c.id).where(datasets.c.id == dataset_id)
            assert session.execute(key_share.with_for_update(read=True, key_share=True)).first()
            session.rollback()
        # 실제 FK 자식 INSERT: 같은 데이터셋의 열 정의 행을 다른 트랜잭션이 넣는다.
        with pg.writer.begin() as conn:
            conn.execute(
                sa.insert(dataset_columns).values(
                    dataset_id=dataset_id, display_name="자식", type="text", kind="raw", position=9
                )
            )
        assert time.monotonic() - started < 0.8, "읽기가 정의 변경을 기다렸다"
        assert detail["def_version"] == 1 and total == 1 and len(listing) == 1
    finally:
        release.set()
        holder.join(timeout=10)
    assert holder.error is None


def test_for_share_row_write_lock_waits_for_a_definition_change(pg, dataset_id):
    """행 쓰기(1c)의 `FOR SHARE`는 정의 변경(`FOR NO KEY UPDATE`)과 서로 기다린다(06 §5)."""
    entered, release = threading.Event(), threading.Event()
    holder = Worker(
        add_column_call(
            pg.engine, dataset_id, "보유자", blocking_hooks(entered, release, wait=15), version=1
        )
    )
    holder.start()
    assert entered.wait(timeout=5)
    try:
        with pytest.raises(DBAPIError) as error, Session(pg.engine) as session:
            definition.set_lock_timeout(session)
            session.execute(
                sa.select(datasets.c.id)
                .where(datasets.c.id == dataset_id)
                .with_for_update(read=True)
            )
        assert sqlstate(error.value) == "55P03"  # lock_not_available: 한도 안에 풀리지 않았다
    finally:
        release.set()
        holder.join(timeout=10)


def test_definition_change_waits_for_for_share_holders_then_proceeds(pg, dataset_id):
    holder = Session(pg.engine)
    holder.execute(
        sa.select(datasets.c.id).where(datasets.c.id == dataset_id).with_for_update(read=True)
    )  # 행 쓰기 하나가 FOR SHARE를 쥐고 있다
    worker = Worker(add_column_call(pg.engine, dataset_id, "정의 변경", DefinitionHooks(), 1))
    worker.start()
    time.sleep(0.3)
    assert worker.is_alive(), "FOR SHARE 보유자를 기다려야 한다"
    holder.commit()
    holder.close()
    worker.join(timeout=10)
    assert worker.error is None and worker.result.def_version == 2


def test_continuous_for_share_holders_overtake_a_waiting_definition_change(pg, dataset_id):
    """굶음 시나리오(06 §5): 관찰한 사실을 단정으로 고정한다 (PostgreSQL 16.10 관찰).

    H1이 FOR SHARE를 쥔 동안 정의 변경 D(`FOR NO KEY UPDATE`)가 기다리고, 그 사이 두 번째
    보유자 H2가 FOR SHARE를 요청한다. **관찰: H2는 D 뒤에 줄 서지 않고 D를 앞질러 즉시 얻는다**
    (공유 잠금끼리는 서로 호환이라 대기열을 지키지 않는다). 그래서 행 쓰기가 끊이지 않으면
    정의 변경은 굶을 수 있고, D는 `lock_timeout`(1초)에서 503 `DEFINITION_BUSY`로 끝난다
    (무한 대기는 없다).

    관찰이 달라지면(다른 PostgreSQL 버전 등) 이 단정이 깨져 Skill의 서술(`dataset-definition`
    4절, `data-entry`)을 다시 확인하게 한다. H2 스레드의 오류는 무시하지 않는다: 오류가 있으면
    잠금 대기 초과(55P03, 줄 서서 기다렸다는 뜻)인지 구분해 실패 메시지에 남긴다.
    """
    h1, h2 = Session(pg.engine), Session(pg.engine)
    share = sa.select(datasets.c.id).where(datasets.c.id == dataset_id).with_for_update(read=True)
    h1.execute(share)
    worker = Worker(add_column_call(pg.engine, dataset_id, "정의 변경", DefinitionHooks(), 1))
    worker.start()
    wait_for_lock_waiter(pg.engine)  # D가 실제로 H1을 기다리기 시작한 뒤

    def second_holder():
        h2.execute(sa.select(sa.func.set_config("lock_timeout", "400ms", True)))
        h2.execute(share)

    h2_thread = Worker(second_holder)
    h2_thread.start()
    h2_thread.join(timeout=5)
    assert not h2_thread.is_alive(), "H2 스레드가 끝나지 않았다"
    h1.commit()
    h1.close()
    worker.join(timeout=10)
    h2.rollback()
    h2.close()
    assert not worker.is_alive(), "정의 변경이 한도를 넘어 계속 기다린다(굶음 + 무한 대기)"
    if h2_thread.error is not None:
        state = sqlstate(h2_thread.error) if isinstance(h2_thread.error, DBAPIError) else None
        pytest.fail(
            f"H2가 D 뒤에 줄을 섰다(관찰이 달라짐, sqlstate={state}): "
            f"{type(h2_thread.error).__name__} - Skill의 굶음 서술을 갱신하라"
        )
    assert isinstance(worker.error, AppError) and worker.error.code == "DEFINITION_BUSY"
    assert LOCK_TIMEOUT_SECONDS * 0.8 <= worker.elapsed < LOCK_TIMEOUT_SECONDS + 3
    print(
        f"[starvation] H2가 D를 앞질러 FOR SHARE를 얻음=True, D=DEFINITION_BUSY, "
        f"대기 {worker.elapsed:.2f}s"
    )
    # 보유자가 모두 풀린 뒤에는 정의 변경이 된다.
    ok = add_column_call(pg.engine, dataset_id, "마무리", DefinitionHooks(), 1)()
    assert ok.def_version == 2


def test_rename_in_progress_makes_fk_child_inserts_wait_until_commit(pg, dataset_id):
    """관찰(PostgreSQL 16.10): 이름 변경(B4) 중에는 FK 자식 INSERT가 커밋까지 **기다린다**.

    `datasets.name`은 `UNIQUE(team_id, name)`에 들어 있다. PostgreSQL은 유일 인덱스에 들어 있는
    열을 바꾸는 UPDATE를 (FK가 그 인덱스를 참조하든 말든) 키 변경으로 보고 `FOR UPDATE` 수준의
    행 잠금을 걸어, 자식 INSERT가 부모 행에 거는 `FOR KEY SHARE`와 충돌한다. 열 추가
    (`def_version`·`def_hash`만 바꿈)는 `FOR NO KEY UPDATE`라 막지 않는다(위 시험). 그래서
    이름 변경 트랜잭션이 짧으면 자식 INSERT가 잠깐 기다릴 뿐이지만, 정의 변경 훅이 길어지면
    (1d 뷰 재생성) 그만큼 기다린다.
    """
    entered, release = threading.Event(), threading.Event()

    def rename():
        with Session(pg.engine) as session:
            return service.update_dataset(
                session,
                blocking_hooks(entered, release, wait=15),
                dataset_id,
                actor=creator_of(session, dataset_id),
                expected_version=1,
                name="바뀐 이름",
                date_unit=None,
                base_given=False,
                base_date_column_id=None,
            )

    def child_insert():
        with pg.writer.begin() as conn:
            conn.execute(
                sa.insert(dataset_columns).values(
                    dataset_id=dataset_id, display_name="자식", type="text", kind="raw", position=9
                )
            )

    holder = Worker(rename)
    holder.start()
    assert entered.wait(timeout=5), "이름 변경이 락을 잡지 못했다"
    child = Worker(child_insert)
    child.start()
    time.sleep(0.5)
    assert child.is_alive(), "관찰이 달라졌다: 자식 INSERT가 이름 변경을 기다리지 않았다"
    release.set()
    child.join(timeout=10)
    holder.join(timeout=10)
    assert child.error is None and holder.error is None
    assert holder.result == (True, 2)
    assert child.elapsed >= 0.5


def test_concurrent_creation_of_the_same_name_yields_one_dataset_and_one_table(pg):
    user = pg.add_user("definer", "정의 담당자")
    team = pg.add_team("team_a", "A팀")
    pg.add_member(team, user, "definer")
    current = CurrentUser(id=user, display_name="정의 담당자", is_active=True, is_admin=False)
    for round_number in range(3):
        barrier = threading.Barrier(3)

        def attempt(barrier=barrier, round_number=round_number):
            barrier.wait(timeout=5)
            with Session(pg.engine) as session:
                return service.create_dataset(
                    session,
                    DefinitionHooks(),
                    current,
                    team_id=team,
                    name=f"같은 이름 {round_number}",
                    date_unit="day",
                )

        workers = [Worker(attempt) for _ in range(3)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=15)
        assert not any(w.is_alive() for w in workers), "교착"
        winners = [w for w in workers if w.error is None]
        assert len(winners) == 1, [type(w.error).__name__ for w in workers]
        for loser in (w for w in workers if w.error is not None):
            assert isinstance(loser.error, AppError)
            assert loser.error.code == "ALREADY_EXISTS", loser.error.code
        ids = [r["id"] for r in pg.rows(datasets) if r["name"] == f"같은 이름 {round_number}"]
        assert ids == [winners[0].result]
        tables = set(sa.inspect(pg.engine).get_table_names(schema="bi_data"))
        assert f"ds_{winners[0].result}" in tables
    # 진 쪽이 만들다 만 표가 남지 않았다: 표 수 = 데이터셋 수.
    assert len(sa.inspect(pg.engine).get_table_names(schema="bi_data")) == len(pg.rows(datasets))
