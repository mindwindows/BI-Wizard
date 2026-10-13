"""감사 기록의 PostgreSQL 전용 시험: 행위자 `users` 행 잠금 영향, 경쟁에서의 "실제 전이 한 건씩",
직렬화 크기가 DB와 같은지, 시작 점검. 실제 PostgreSQL(tmpfs 시험 DB) 필요.

06 §5 "감사 INSERT 위치": 감사 INSERT가 거는 새 잠금은 행위자 `users` 행의 `FOR KEY SHARE`(FK 확인)
하나뿐이고, 이는 `users` 행을 바꾸는 쪽의 `FOR NO KEY UPDATE`(키가 아닌 열의 UPDATE)와 충돌하지
않는다고 추정했다. 아래 첫 시험이 동시 실행으로 이것을 확인한다(반대로 `FOR UPDATE`는 막는다는 것도
보여 줘 시험이 막힘을 알아챌 수 있음을 확인한다).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from itertools import pairwise
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

from app.access import repo as access_repo
from app.access import service as access_service
from app.audit import record
from app.audit import service as audit_service
from app.audit.actions import ACTIONS
from app.auth.models import CurrentUser
from app.core.errors import AppError
from app.core.startup_check import StartupCheckError, check_static_tables
from app.db_metadata import audit_log, metadata, team_members, users
from app.superset import service as superset_service
from tests.audit_helpers import audit_rows
from tests.conftest import Db
from tests.test_audit_record import sample


@pytest.fixture
def pg(pg_app_engine: Engine, pg_owner_engine: Engine, clean_pg) -> Db:
    return Db("pg", pg_app_engine, pg_owner_engine)


class Worker(threading.Thread):
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


def actor_of(user_id: int) -> CurrentUser:
    return CurrentUser(id=user_id, display_name="관리자", is_active=True, is_admin=True)


# --- 행위자 users 행 잠금 영향 ----


def test_audit_insert_does_not_wait_for_a_concurrent_update_of_the_actors_user_row(pg: Db):
    """행위자 행을 NO KEY UPDATE로 잠그고 고치는 중(미커밋)이어도 감사 INSERT는 기다리지 않는다."""
    admin = pg.add_user("admin", "관리자", is_admin=True)
    other = pg.add_user("other-admin", "다른 관리자", is_admin=True)
    holder = Session(pg.engine)
    # LAST_ADMIN 보호가 쓰는 잠금: 활성 관리자 전체(행위자 포함)를 FOR NO KEY UPDATE로 잡는다
    _target, admins = access_repo.lock_target_and_active_admins(holder, admin)
    assert sorted(admins) == sorted([admin, other])
    access_repo.update_user(holder, admin, {"display_name": "고치는 중", "is_admin": True})

    def create_team() -> dict[str, Any]:
        with Session(pg.engine) as session:
            return access_service.create_team(
                session, actor_of(admin), code="new_team", name="새 팀"
            )

    worker = Worker(create_team)
    worker.start()
    worker.join(timeout=5)
    assert not worker.is_alive(), "감사 INSERT가 행위자 행의 변경을 기다린다(새 대기가 생겼다)"
    assert worker.error is None and worker.elapsed < 4
    holder.commit()
    holder.close()
    [row] = audit_rows(pg)
    assert (row["action"], row["actor_user_id"]) == ("team.create", admin)


def test_changing_the_actors_user_row_does_not_wait_for_an_open_audit_insert(pg: Db):
    """반대 방향: 감사 INSERT가 열려 있는 동안(KEY SHARE 보유) 행위자 행을 고쳐도 안 기다린다."""
    admin = pg.add_user("admin", "관리자", is_admin=True)
    pg.add_user("other-admin", "다른 관리자", is_admin=True)
    inserting = Session(pg.engine)
    record(
        inserting,
        actor=actor_of(admin),
        action="team.create",
        target_id=1,
        target_name="n",
        details={"code": "c"},
    )  # 커밋하지 않는다: users(admin) 행에 KEY SHARE가 걸려 있다

    def rename_actor() -> None:
        with Session(pg.engine) as session:
            access_service.update_user(
                session,
                actor_of(admin),
                admin,
                display_name="바뀐 이름",
                is_admin=None,
                is_active=None,
            )

    worker = Worker(rename_actor)
    worker.start()
    worker.join(timeout=5)
    assert not worker.is_alive(), "행위자 행 변경이 열려 있는 감사 INSERT를 기다린다"
    assert worker.error is None
    inserting.rollback()
    inserting.close()
    # rename_actor 자신의 user.update 기록만 남았고(행위자 = admin), 롤백한 team.create는 없다
    assert [r["action"] for r in audit_rows(pg)] == ["user.update"]


def test_the_test_can_detect_blocking_a_for_update_lock_does_wait(pg: Db):
    """시험의 감도 확인: 키까지 잠그는 FOR UPDATE는 감사 INSERT(KEY SHARE)를 기다리게 한다."""
    admin = pg.add_user("admin", "관리자", is_admin=True)
    holder = pg.writer.connect()
    transaction = holder.begin()
    holder.execute(select(users.c.id).where(users.c.id == admin).with_for_update())
    done = threading.Event()

    def insert_audit() -> None:
        with Session(pg.engine) as session:
            record(
                session,
                actor=actor_of(admin),
                action="team.create",
                target_id=1,
                target_name="n",
                details={"code": "c"},
            )
            session.commit()
        done.set()

    worker = Worker(insert_audit)
    worker.start()
    assert not done.wait(timeout=1.0), "FOR UPDATE는 KEY SHARE와 충돌해야 한다(관찰이 달라졌다)"
    transaction.rollback()
    holder.close()
    worker.join(timeout=10)
    assert done.is_set() and worker.error is None


def test_audit_rows_do_not_block_each_other(pg: Db):
    """audit_log에는 행 잠금·유일 제약이 없어 동시 INSERT가 서로 기다리지 않는다."""
    admin = pg.add_user("admin", "관리자", is_admin=True)
    barrier = threading.Barrier(8)

    def insert_one(n: int) -> None:
        with Session(pg.engine) as session:
            barrier.wait(timeout=5)
            record(
                session,
                actor=actor_of(admin),
                action="team.create",
                target_id=n,
                target_name=f"팀{n}",
                details={"code": f"t{n}"},
            )
            session.commit()

    workers = [Worker(lambda n=n: insert_one(n)) for n in range(1, 9)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)
    assert all(not w.is_alive() and w.error is None for w in workers)
    rows = audit_rows(pg)
    assert sorted(r["target_id"] for r in rows) == list(range(1, 9))
    assert len({r["id"] for r in rows}) == 8


# --- 경쟁: 실제로 일어난 전이마다 정확히 1건 ----


def put_member(pg: Db, actor: int, team: int, user: int, role: str) -> str:
    with Session(pg.engine) as session:
        try:
            access_service.set_member(session, actor_of(actor), team, user, role)
        except AppError as error:
            return error.code
    return "OK"


@pytest.mark.parametrize("roles", [("entry", "definer"), ("definer", "entry"), ("entry", "entry")])
def test_concurrent_new_memberships_record_each_real_transition_once(pg: Db, roles):
    """A8 동시 추가 경쟁: 진 쪽이 IntegrityError 뒤 이긴 쪽의 값을 쓰기 전 값으로 다시 읽는다."""
    admin = pg.add_user("admin", "관리자", is_admin=True)
    team = pg.add_team("team_a", "A팀")
    for round_number in range(8):
        member = pg.add_user(f"member-{round_number}", f"사용자{round_number}")
        barrier = threading.Barrier(2)

        def attempt(role: str, barrier=barrier, member=member) -> str:
            barrier.wait(timeout=5)
            return put_member(pg, admin, team, member, role)

        workers = [Worker(lambda r=r: attempt(r)) for r in roles]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=15)
        assert all(not w.is_alive() and w.error is None for w in workers)
        assert [w.result for w in workers] == ["OK", "OK"]
        rows = [
            r
            for r in audit_rows(pg)
            if r["action"] == "member.set" and r["details"]["user_id"] == member
        ]
        with pg.writer.connect() as conn:
            final = conn.execute(
                select(team_members.c.role).where(team_members.c.user_id == member)
            ).scalar_one()
        # 전이 사슬: (없음 -> 첫 역할) [-> 둘째 역할]. 같은 역할이면 전이는 하나뿐이다.
        assert rows[0]["details"]["role_from"] is None
        for previous, current in pairwise(rows):
            assert current["details"]["role_from"] == previous["details"]["role"]
        assert rows[-1]["details"]["role"] == final
        assert len(rows) == (1 if roles[0] == roles[1] else 2), [r["details"] for r in rows]


def test_concurrent_role_changes_of_an_existing_membership_form_a_chain(pg: Db):
    admin = pg.add_user("admin", "관리자", is_admin=True)
    team = pg.add_team("team_a", "A팀")
    user = pg.add_user("member", "사용자")
    pg.add_member(team, user, "entry")
    for _ in range(6):
        barrier = threading.Barrier(2)

        def attempt(role: str, barrier=barrier) -> str:
            barrier.wait(timeout=5)
            return put_member(pg, admin, team, user, role)

        workers = [Worker(lambda r=r: attempt(r)) for r in ("definer", "entry")]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=15)
        assert all(not w.is_alive() and w.error is None for w in workers)
    rows = [r["details"] for r in audit_rows(pg) if r["action"] == "member.set"]
    assert rows, "전이가 하나도 기록되지 않았다"
    assert rows[0]["role_from"] == "entry"
    for previous, current in pairwise(rows):
        assert current["role_from"] == previous["role"]  # 끊어진 사슬이 없다
        assert current["role"] != current["role_from"]  # 같은 값으로의 전이는 기록되지 않는다
    with pg.writer.connect() as conn:
        final = conn.execute(select(team_members.c.role)).scalar_one()
    assert rows[-1]["role"] == final


def test_concurrent_create_admin_records_one_bootstrap_row(pg: Db):
    for round_number in range(6):
        login = f"boss-{round_number}"
        barrier = threading.Barrier(4)

        def attempt(login=login, barrier=barrier) -> bool:
            barrier.wait(timeout=5)
            with Session(pg.engine) as session:
                return access_service.create_first_admin(
                    session, login_id=login, display_name=f"관리자 {login}"
                )

        workers = [Worker(attempt) for _ in range(4)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=15)
        assert all(not w.is_alive() and w.error is None for w in workers)
        assert sorted(w.result for w in workers) == [False, False, False, True]
        with pg.writer.connect() as conn:
            user_id = conn.execute(select(users.c.id).where(users.c.login_id == login)).scalar_one()
        rows = [
            r
            for r in audit_rows(pg)
            if r["action"] == "user.bootstrap_admin" and r["target_id"] == user_id
        ]
        assert len(rows) == 1 and rows[0]["actor_user_id"] is None


def test_concurrent_identical_dashboard_updates_record_the_transition_once(pg: Db):
    admin = pg.add_user("admin", "관리자", is_admin=True)
    created = None
    with Session(pg.engine) as session:
        created = superset_service.create_dashboard(
            session,
            actor_of(admin),
            name="월간",
            embedded_uuid="11111111-2222-3333-4444-555555555555",
        )
    for round_number in range(6):
        barrier = threading.Barrier(3)
        target = round_number % 2 == 1  # 번갈아 해제/재연결

        def attempt(barrier=barrier, target=target) -> None:
            barrier.wait(timeout=5)
            with Session(pg.engine) as session:
                superset_service.update_dashboard(
                    session, actor_of(admin), created["id"], name=None, is_active=target
                )

        workers = [Worker(attempt) for _ in range(3)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=15)
        assert all(not w.is_alive() and w.error is None for w in workers)
    rows = [
        r["details"]["changes"]["is_active"]
        for r in audit_rows(pg)
        if r["action"] == "dashboard.update"
    ]
    # 매 라운드 실제 전이는 정확히 한 번이다: false -> true -> false ... 로 이어진다
    assert rows == [{"from": bool(i % 2 == 0), "to": bool(i % 2 == 1)} for i in range(6)], rows
    for previous, current in pairwise(rows):
        assert current["from"] == previous["to"]


# --- 직렬화 크기 = DB의 details::text 크기 ----

NASTY = [
    "가나다",
    'quote " and backslash \\ and slash /',
    "줄바꿈\n탭\t캐리지\r",
    "제어문자\x01\x1f",
    "이모지 😀 𠮷",
    "유니코드 \u2028 \u00a0 \u200b",
    "x" * 100,
]


@pytest.mark.parametrize("text", NASTY)
def test_python_size_matches_the_database_size_of_details_text(pg: Db, text):
    details = {"target_name": text, "code": text}
    with pg.engine.begin() as conn:
        conn.execute(
            sa.insert(audit_log).values(
                actor_source="cli",
                action="team.create",
                target_type="team",
                target_id=1,
                details=details,
            )
        )
    with pg.writer.connect() as conn:
        db_size = conn.execute(
            select(sa.func.octet_length(sa.cast(audit_log.c.details, sa.Text)))
        ).scalar_one()
    assert audit_service._serialized_size(details) == db_size


@pytest.mark.parametrize("action", list(ACTIONS))
def test_the_longest_valid_details_are_accepted_by_the_database(pg: Db, action):
    spec = ACTIONS[action]
    full = audit_service.validate_details(action, "가" * 100, sample(spec, long=True))
    # 사용자 행위자로 실제 INSERT까지 확인한다(DB CHECK 4,000바이트 안이다)
    admin = pg.add_user("admin", "관리자", is_admin=True)
    with Session(pg.engine) as session:
        record(
            session,
            actor=actor_of(admin),
            action=action,
            target_id=1,
            target_name="가" * 100,
            details=sample(spec, long=True),
        )
        session.commit()
    [row] = audit_rows(pg)
    assert row["details"] == full
    with pg.writer.connect() as conn:
        size = conn.execute(
            select(sa.func.octet_length(sa.cast(audit_log.c.details, sa.Text)))
        ).scalar_one()
    assert size == audit_service._serialized_size(full) < 4000


# --- 시작 점검 ----


def test_startup_check_refuses_a_database_without_the_audit_table():
    """0007이 적용되지 않은 DB에서는 backend가 시작을 거부한다(새 규칙 없이 정적 MetaData로)."""
    engine = create_engine("sqlite://")
    tables = [t for t in metadata.sorted_tables if t.name != "audit_log"]
    metadata.create_all(engine, tables=tables)
    with engine.connect() as conn, pytest.raises(StartupCheckError) as error:
        check_static_tables(conn)
    assert "audit_log" in str(error.value)
    metadata.create_all(engine)
    with engine.connect() as conn:
        check_static_tables(conn)  # 표가 있으면 통과한다
    engine.dispose()


def test_startup_check_passes_on_the_real_database(pg_app_engine: Engine, pg_env):
    with pg_app_engine.connect() as conn:
        check_static_tables(conn)
