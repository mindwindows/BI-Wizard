"""뷰 DDL 도중 PostgreSQL이 교착 희생자로 고른 경우(40P01)의 정의 변경 경로 시험(실제 PG 필요).

1e 실측에서 Superset `refresh`와 포털 뷰 DDL이 같은 뷰를 반대 순서로 잠그다 교착하는 일이 있었다. 이
시험은 **진짜 교착**을 만든다(주입이 아니다):

- 요청(A)은 `datasets` 행을 `FOR NO KEY UPDATE`로 잡은 채 `dv_<번호>`에 `CREATE OR REPLACE VIEW`를
  한다.
- 다른 연결(B)은 슈퍼유저로 접속해 `dv_<번호>`에 `ACCESS EXCLUSIVE`를 쥔 채(`ALTER VIEW`)
  반대 순서로 `datasets` 행 `FOR UPDATE`를 기다린다(Superset `refresh`가 뷰를 잠근 채 포털 행을
  기다리는 모양).
- B는 `deadlock_timeout`을 길게 둬(세션 설정, 슈퍼유저만 가능) 교착 검사가 A 쪽에서만 돈다. 그래서
  A가 항상 희생자다. A의 `lock_timeout`은 1초 `deadlock_timeout`보다 먼저 끝나지 않도록 시험에서만
  늘린다(같은 값이면 어느 오류가 먼저일지 정해져 있지 않다).

기대: 응답 503 `DEFINITION_BUSY`, 트랜잭션 롤백(정의·열·뷰·해시가 이전 상태, 동기화 요청 없음), 같은
요청을 다시 보내면 정상 처리.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine

from app import ddl
from app.core.db_errors import sqlstate
from app.dataset import definition
from app.db_metadata import DYNAMIC_SCHEMA, datasets
from tests.conftest import Db
from tests.formula_api_helpers import (
    add_column,
    dataset_hash,
    err,
    make_dataset,
    version,
)

B_NAME = "bf1e-deadlock-b"
WAIT_SECONDS = 15.0


@pytest.fixture
def db(pg_app_engine, pg_owner_engine, clean_pg):
    yield Db("pg", pg_app_engine, pg_owner_engine)


@pytest.fixture
def admin(pg_env):
    values = pg_env.values
    if not values.get("POSTGRES_USER") or not values.get("POSTGRES_PASSWORD"):
        pytest.fail("시험 DB 관리자 접속 정보가 없다(POSTGRES_USER/POSTGRES_PASSWORD)")
    engine = create_engine(
        pg_env.url(values["POSTGRES_USER"], values["POSTGRES_PASSWORD"]),
        poolclass=sa.pool.NullPool,
    )
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        assert conn.execute(sa.text("SHOW fsync")).scalar_one() == "off"  # tmpfs 시험 DB 확인
        timeout = conn.execute(sa.text("SHOW deadlock_timeout")).scalar_one()
        if timeout != "1s":
            pytest.fail(
                f"시험 DB의 deadlock_timeout은 1s여야 한다(실제 {timeout}): 교착 시험이 가정한다"
            )
    yield engine
    engine.dispose()


class Opponent(threading.Thread):
    """B: 뷰 잠금을 쥔 채 `datasets` 행을 기다리다(반대 순서) A가 롤백하면 풀려 끝난다."""

    def __init__(self, admin: sa.Engine, dataset_id: int) -> None:
        super().__init__(daemon=True)
        self.admin = admin
        self.dataset_id = dataset_id
        self.view_locked = threading.Event()
        self.error: BaseException | None = None
        self.got_row_lock_after: float | None = None

    def run(self) -> None:
        try:
            with self.admin.connect() as conn:
                conn.execute(sa.text(f"SET LOCAL application_name = '{B_NAME}'"))
                conn.execute(sa.text("SET LOCAL deadlock_timeout = '60s'"))
                # 뷰 하나만 ACCESS EXCLUSIVE로 잡는다(LOCK TABLE은 뷰의 원본 표까지 잠근다).
                conn.execute(
                    sa.text(
                        f"ALTER VIEW {DYNAMIC_SCHEMA}.dv_{self.dataset_id} "
                        "SET (security_barrier = false)"
                    )
                )
                self.view_locked.set()
                started = time.monotonic()
                conn.execute(
                    sa.select(datasets.c.id)
                    .where(datasets.c.id == self.dataset_id)
                    .with_for_update()
                ).all()  # A가 쥔 행: A가 롤백해야 풀린다
                self.got_row_lock_after = time.monotonic() - started
                conn.rollback()
        except BaseException as exc:
            self.error = exc
            self.view_locked.set()


def b_is_waiting_on_a_lock(admin: sa.Engine) -> bool:
    with admin.connect() as conn:
        waiting = conn.execute(
            sa.text(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE application_name = :name AND wait_event_type = 'Lock'"
            ),
            {"name": B_NAME},
        ).scalar_one()
    return waiting == 1


class DeadlockTrap:
    """A가 뷰 DDL에 닿는 순간(행 잠금을 쥔 뒤) B를 붙여 진짜 교착을 만든다(DDL은 실제 실행)."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, admin: sa.Engine, dataset_id: int) -> None:
        self.admin = admin
        self.dataset_id = dataset_id
        self.armed = True
        self.opponent: Opponent | None = None
        self.states: list[str | None] = []
        real_create_view = ddl.create_view
        real_translate = definition.translate_db_error
        real_lock_timeout = definition.set_lock_timeout

        def create_view(conn: Any, kind: str, dataset: int, *args: Any, **kwargs: Any) -> Any:
            if self.armed and kind == "dv" and dataset == self.dataset_id:
                self.armed = False
                self.attach_opponent()
            return real_create_view(conn, kind, dataset, *args, **kwargs)

        def translate(session: Any, error: Any) -> Any:
            self.states.append(sqlstate(error))
            return real_translate(session, error)

        def lock_timeout(session: Any, timeout: str = "") -> None:
            real_lock_timeout(session, "20000ms")  # deadlock_timeout(1초)보다 먼저 끝나지 않게

        monkeypatch.setattr(ddl, "create_view", create_view)
        monkeypatch.setattr(definition, "translate_db_error", translate)
        monkeypatch.setattr(definition, "set_lock_timeout", lock_timeout)

    def attach_opponent(self) -> None:
        opponent = Opponent(self.admin, self.dataset_id)
        self.opponent = opponent
        opponent.start()
        assert opponent.view_locked.wait(WAIT_SECONDS), "B가 뷰 잠금을 잡지 못했다"
        assert opponent.error is None, opponent.error
        deadline = time.monotonic() + WAIT_SECONDS
        while not b_is_waiting_on_a_lock(self.admin):
            assert time.monotonic() < deadline, "B가 datasets 행 잠금을 기다리는 상태가 되지 않았다"
            time.sleep(0.02)

    def finish(self) -> None:
        assert self.opponent is not None, "교착 함정이 작동하지 않았다"
        self.opponent.join(WAIT_SECONDS)
        assert not self.opponent.is_alive(), "A가 롤백했는데도 B가 풀리지 않았다"
        assert self.opponent.error is None, self.opponent.error


def view_columns(db: Db, dataset_id: int) -> list[str]:
    inspector = sa.inspect(db.engine)
    return [c["name"] for c in inspector.get_columns(f"dv_{dataset_id}", schema=DYNAMIC_SCHEMA)]


def dataset_columns(api: Any, dataset_id: int) -> list[int]:
    response = api("definer", "GET", f"/api/datasets/{dataset_id}")
    assert response.status_code == 200, response.text
    return [c["id"] for c in response.json()["columns"]]


def formula_rows(db: Db) -> int:
    from app.db_metadata import formulas

    with db.writer.connect() as conn:
        return conn.execute(sa.select(sa.func.count()).select_from(formulas)).scalar_one()


REQUESTS = {
    "raw_column": lambda api, dataset_id, expected: api(
        "definer",
        "POST",
        f"/api/datasets/{dataset_id}/columns",
        json={"expected_version": expected, "display_name": "새 열", "type": "number"},
    ),
    "formula": lambda api, dataset_id, expected: api(
        "definer",
        "POST",
        f"/api/datasets/{dataset_id}/formulas",
        json={"expected_version": expected, "display_name": "계산", "expression": "[매출] + 1"},
    ),
}


@pytest.mark.parametrize("kind", sorted(REQUESTS))
def test_real_deadlock_in_view_ddl_is_503_definition_busy_rolls_back_and_the_retry_works(
    api, db, world, admin, sync, monkeypatch, kind
):
    dataset = make_dataset(api, world, "교착 시험")
    dataset_id = dataset["id"]
    add_column(api, dataset_id, "매출")
    before = {
        "version": version(api, dataset_id),
        "hash": dataset_hash(db, dataset_id),
        "columns": dataset_columns(api, dataset_id),
        "view": view_columns(db, dataset_id),
        "formulas": formula_rows(db),
        "sync_requests": list(sync.dataset_requests),
    }
    trap = DeadlockTrap(monkeypatch, admin, dataset_id)

    started = time.monotonic()
    response = REQUESTS[kind](api, dataset_id, before["version"])
    elapsed = time.monotonic() - started
    trap.finish()

    # 진짜 교착이었다: PostgreSQL이 A를 희생자로 골랐고(40P01) 잠금 대기 초과(55P03)가 아니다.
    assert trap.states == ["40P01"], trap.states
    assert elapsed >= 0.9  # deadlock_timeout(1초)을 기다린 뒤에 검출됐다
    # 응답은 재시도 가능한 503 DEFINITION_BUSY다.
    assert response.status_code == 503, response.text
    error = err(response)
    assert error["code"] == "DEFINITION_BUSY"
    assert error["details"]["retry_after"] >= 1
    # 트랜잭션이 롤백돼 정의·뷰가 이전 상태로 남는다.
    assert version(api, dataset_id) == before["version"]
    assert dataset_hash(db, dataset_id) == before["hash"]
    assert dataset_columns(api, dataset_id) == before["columns"]
    assert view_columns(db, dataset_id) == before["view"]
    assert formula_rows(db) == before["formulas"]
    assert (
        sync.dataset_requests == before["sync_requests"]
    )  # 롤백된 변경은 Superset에 알리지 않는다
    # B는 A의 롤백 뒤에야 행 잠금을 얻었다(잠금이 풀린 증거).
    assert trap.opponent is not None and trap.opponent.got_row_lock_after is not None

    # 같은 요청을 그대로 다시 보내면 정상 처리된다(함정은 한 번만 작동한다).
    retry = REQUESTS[kind](api, dataset_id, before["version"])
    assert retry.status_code == 201, retry.text
    assert version(api, dataset_id) == before["version"] + 1
    assert len(dataset_columns(api, dataset_id)) == len(before["columns"]) + 1
    assert len(view_columns(db, dataset_id)) == len(before["view"]) + 1
    assert dataset_hash(db, dataset_id) != before["hash"]
    assert sync.dataset_requests[len(before["sync_requests"]) :] == [dataset_id]
    assert trap.states == ["40P01"]  # 재시도에서는 오류가 없었다
    assert formula_rows(db) == before["formulas"] + (1 if kind == "formula" else 0)


def test_the_helper_really_needs_the_opposite_lock_order(api, db, world, admin, monkeypatch):
    """대조군: B가 `datasets` 행을 기다리지 않으면 교착 없이 A가 B를 기다렸다 성공한다."""
    dataset = make_dataset(api, world, "대조군")
    dataset_id = dataset["id"]
    add_column(api, dataset_id, "매출")
    release = threading.Event()
    holding = threading.Event()

    def hold_view_briefly() -> None:
        with admin.connect() as conn:
            conn.execute(
                sa.text(
                    f"ALTER VIEW {DYNAMIC_SCHEMA}.dv_{dataset_id} SET (security_barrier = false)"
                )
            )
            holding.set()
            release.wait(WAIT_SECONDS)
            conn.rollback()

    states: list[str | None] = []
    real_translate = definition.translate_db_error

    def translate(session: Any, error: Any) -> Any:
        states.append(sqlstate(error))
        return real_translate(session, error)

    monkeypatch.setattr(definition, "translate_db_error", translate)
    real_create_view = ddl.create_view
    armed = [True]

    def create_view(conn: Any, kind: str, dataset: int, *args: Any, **kwargs: Any) -> Any:
        if armed[0] and kind == "dv":
            armed[0] = False
            thread = threading.Thread(target=hold_view_briefly, daemon=True)
            thread.start()
            assert holding.wait(WAIT_SECONDS)
            threading.Timer(0.3, release.set).start()  # 0.3초 뒤 B가 풀린다(교착 없음)
        return real_create_view(conn, kind, dataset, *args, **kwargs)

    monkeypatch.setattr(ddl, "create_view", create_view)
    response = REQUESTS["raw_column"](api, dataset_id, version(api, dataset_id))
    assert response.status_code == 201, response.text
    assert states == []
