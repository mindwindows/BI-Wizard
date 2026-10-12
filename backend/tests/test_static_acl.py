"""정적 표 DB 권한·제약 시험(06 §2 매트릭스, 03b 3-6 BY4). 실제 PostgreSQL(tmpfs 시험 DB) 필요.

0003 적용 뒤 `bi_app`이 허용된 동작만 할 수 있고 `bi_readonly`가 정적 표를 읽을 수 없음을 확인한다.
권한 판정은 `has_table_privilege`/`has_column_privilege`로 전부 대조하고, 대표 동작은 실제로 실행해
거부 코드(42501)와 제약 위반 코드(23xxx)를 확인한다.
"""

import threading

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, delete, func, insert, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.access import repo, service
from app.core.errors import AppError
from app.db_metadata import team_members, teams, users

INSUFFICIENT_PRIVILEGE = "42501"
CHECK_VIOLATION = "23514"
UNIQUE_VIOLATION = "23505"
FOREIGN_KEY_VIOLATION = "23503"

TABLES = {"users": users, "teams": teams, "team_members": team_members}
# bi_app의 표 단위 권한(has_table_privilege). UPDATE는 열 단위라 표 단위로는 없다.
TABLE_PRIVILEGES = {
    "users": {"SELECT", "INSERT"},
    "teams": {"SELECT", "INSERT"},
    "team_members": {"SELECT", "INSERT", "DELETE"},
}
ALL_PRIVILEGES = {"SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"}
# bi_app이 UPDATE할 수 있는 열(06 §2). 나머지 열은 불변이다.
UPDATABLE = {
    "users": {"display_name", "is_admin", "is_active"},
    "teams": {"name", "is_active"},
    "team_members": {"role"},
}


def sqlstate(error: DBAPIError) -> str:
    # pg8000은 23505(유일 위반)만 IntegrityError로, 나머지(권한 42501, 제약 23514·23503)는 모두
    # ProgrammingError로 올린다. 그래서 예외 클래스가 아니라 SQLSTATE로 구분한다.
    return str(error.orig.args[0].get("C"))  # pg8000: 첫 인자가 오류 필드 사전


def privilege(conn, role: str, table: str, privilege_name: str) -> bool:
    return bool(
        conn.execute(select(func.has_table_privilege(role, table, privilege_name))).scalar()
    )


def column_privilege(conn, role: str, table: str, column: str, privilege_name: str) -> bool:
    return bool(
        conn.execute(
            select(func.has_column_privilege(role, table, column, privilege_name))
        ).scalar()
    )


@pytest.fixture
def conn(pg_owner_engine: Engine, clean_pg):
    with pg_owner_engine.connect() as connection:
        yield connection


# --- 카탈로그 대조 매트릭스 ----


@pytest.mark.parametrize("table", TABLES)
def test_bi_app_table_privileges_are_exactly_the_granted_ones(conn, table):
    for name in ALL_PRIVILEGES:
        assert privilege(conn, "bi_app", table, name) is (name in TABLE_PRIVILEGES[table]), name


@pytest.mark.parametrize("table", TABLES)
def test_bi_app_column_update_privileges_are_exactly_the_mutable_columns(conn, table):
    for col in TABLES[table].c:
        expected = col.name in UPDATABLE[table]
        assert column_privilege(conn, "bi_app", table, col.name, "UPDATE") is expected, col.name
        # 모든 열을 읽고 쓸(INSERT) 수 있다. 시퀀스 권한은 필요 없다(IDENTITY).
        assert column_privilege(conn, "bi_app", table, col.name, "SELECT")


@pytest.mark.parametrize("table", TABLES)
def test_bi_readonly_has_no_privilege_on_static_tables(conn, table):
    for name in ALL_PRIVILEGES:
        assert privilege(conn, "bi_readonly", table, name) is False, name
    for col in TABLES[table].c:
        for name in ("SELECT", "INSERT", "UPDATE", "REFERENCES"):
            assert column_privilege(conn, "bi_readonly", table, col.name, name) is False


@pytest.mark.parametrize("table", TABLES)
def test_public_has_no_privilege_on_static_tables(conn, table):
    """PUBLIC(모든 역할) 권한이 없다: 임의의 새 역할이 읽을 수 없다."""
    acl = conn.execute(
        select(sa.cast(sa.column("relacl"), sa.Text))
        .select_from(sa.table("pg_class", schema="pg_catalog"))
        .where(
            sa.column("relname") == table,
            sa.column("relnamespace") == sa.func.to_regnamespace("public"),
        )
    ).scalar_one()
    assert not any(part.startswith("=") for part in acl.strip("{}").split(","))


def test_bi_app_cannot_create_in_public_or_alter_versions(conn):
    assert (
        bool(conn.execute(select(func.has_schema_privilege("bi_app", "public", "CREATE"))).scalar())
        is False
    )
    assert privilege(conn, "bi_app", "alembic_version", "SELECT") is False
    assert privilege(conn, "bi_app", "alembic_version", "INSERT") is False


def test_bi_app_is_not_owner_of_static_tables(conn):
    owners = conn.execute(
        select(sa.column("tablename"), sa.column("tableowner"))
        .select_from(sa.table("pg_tables", schema="pg_catalog"))
        .where(sa.column("schemaname") == "public", sa.column("tablename").in_(list(TABLES)))
    ).all()
    assert {r.tablename: r.tableowner for r in owners} == {name: "bi_owner" for name in TABLES}


# --- 실제 실행: 허용되는 동작 ----


def _prepare(owner: Engine) -> dict[str, int]:
    with owner.begin() as c:
        uid = c.execute(
            insert(users).values(login_id="u1", display_name="U1").returning(users.c.id)
        ).scalar_one()
        tid = c.execute(
            insert(teams).values(code="t1", name="T1").returning(teams.c.id)
        ).scalar_one()
        c.execute(insert(team_members).values(team_id=tid, user_id=uid, role="entry"))
    return {"user": uid, "team": tid}


def test_bi_app_allowed_operations(pg_owner_engine, pg_app_engine, clean_pg):
    ids = _prepare(pg_owner_engine)
    with pg_app_engine.begin() as c:
        new_user = c.execute(
            insert(users).values(login_id="u2", display_name="U2").returning(users.c.id)
        ).scalar_one()
        c.execute(
            update(users)
            .where(users.c.id == ids["user"])
            .values(display_name="새 이름", is_admin=True, is_active=False)
        )
        new_team = c.execute(
            insert(teams).values(code="t2", name="T2").returning(teams.c.id)
        ).scalar_one()
        c.execute(
            update(teams).where(teams.c.id == ids["team"]).values(name="새 팀", is_active=False)
        )
        c.execute(insert(team_members).values(team_id=new_team, user_id=new_user, role="definer"))
        c.execute(
            update(team_members)
            .where(team_members.c.team_id == ids["team"], team_members.c.user_id == ids["user"])
            .values(role="definer")
        )
        # 잠금 읽기는 열 단위 UPDATE 권한만으로 실행된다(LAST_ADMIN 보호가 쓴다).
        c.execute(select(users.c.id).with_for_update(key_share=True)).all()
        c.execute(select(teams.c.id).with_for_update(key_share=True)).all()
        deleted = c.execute(
            delete(team_members)
            .where(team_members.c.team_id == new_team, team_members.c.user_id == new_user)
            .returning(team_members.c.user_id)
        ).all()
        assert len(deleted) == 1


# --- 실제 실행: 거부되는 동작 ----

DENIED = [
    pytest.param(
        lambda i: update(users).where(users.c.id == i["user"]).values(login_id="x"),
        id="users.login_id",
    ),
    pytest.param(
        lambda i: update(users).where(users.c.id == i["user"]).values(created_at=func.now()),
        id="users.created_at",
    ),
    pytest.param(lambda i: update(users).values(id=999), id="users.id"),
    pytest.param(lambda i: delete(users).where(users.c.id == i["user"]), id="users.delete"),
    pytest.param(
        lambda i: update(teams).where(teams.c.id == i["team"]).values(code="x"), id="teams.code"
    ),
    pytest.param(lambda i: update(teams).values(id=999), id="teams.id"),
    pytest.param(lambda i: delete(teams).where(teams.c.id == i["team"]), id="teams.delete"),
    pytest.param(
        lambda i: update(team_members).values(team_id=i["team"]), id="team_members.team_id"
    ),
    pytest.param(
        lambda i: update(team_members).values(user_id=i["user"]), id="team_members.user_id"
    ),
]


@pytest.mark.parametrize("make_statement", DENIED)
def test_bi_app_denied_operations(pg_owner_engine, pg_app_engine, clean_pg, make_statement):
    ids = _prepare(pg_owner_engine)
    with pytest.raises(DBAPIError) as error, pg_app_engine.begin() as c:
        c.execute(make_statement(ids))
    assert sqlstate(error.value) == INSUFFICIENT_PRIVILEGE


def test_bi_readonly_cannot_read_static_tables(pg_owner_engine, pg_readonly_engine, clean_pg):
    _prepare(pg_owner_engine)
    for table in (users, teams, team_members):
        with pytest.raises(DBAPIError) as error, pg_readonly_engine.connect() as c:
            c.execute(select(table))
        assert sqlstate(error.value) == INSUFFICIENT_PRIVILEGE, table.name


# --- DB 제약 ----


@pytest.mark.parametrize("code", ["Bad", "has space", "a" * 33, "", "팀", "x-y"])
def test_team_code_check_constraint(pg_app_engine, clean_pg, code):
    with pytest.raises(DBAPIError) as error, pg_app_engine.begin() as c:
        c.execute(insert(teams).values(code=code, name="n"))
    assert sqlstate(error.value) == CHECK_VIOLATION
    assert "ck_teams_code_format" in str(error.value.orig)


def test_team_code_trailing_newline_is_rejected_by_db(pg_app_engine, clean_pg):
    with pytest.raises(DBAPIError) as error, pg_app_engine.begin() as c:
        c.execute(insert(teams).values(code="abc\n", name="n"))
    assert sqlstate(error.value) == CHECK_VIOLATION


def test_unique_and_role_constraints(pg_owner_engine, pg_app_engine, clean_pg):
    ids = _prepare(pg_owner_engine)

    def fails(statement, code, name):
        with pytest.raises(DBAPIError) as error, pg_app_engine.begin() as c:
            c.execute(statement)
        assert sqlstate(error.value) == code and name in str(error.value.orig)

    fails(
        insert(users).values(login_id="u1", display_name="x"), UNIQUE_VIOLATION, "uq_users_login_id"
    )
    fails(insert(teams).values(code="t1", name="other"), UNIQUE_VIOLATION, "uq_teams_code")
    fails(insert(teams).values(code="other", name="T1"), UNIQUE_VIOLATION, "uq_teams_name")
    fails(
        insert(team_members).values(team_id=ids["team"], user_id=ids["user"], role="definer"),
        UNIQUE_VIOLATION,
        "pk_team_members",
    )
    fails(update(team_members).values(role="owner"), CHECK_VIOLATION, "ck_team_members_role")
    fails(
        insert(team_members).values(team_id=99999, user_id=ids["user"], role="entry"),
        FOREIGN_KEY_VIOLATION,
        "fk_team_members_team_id_teams",
    )


def test_not_null_defaults(pg_app_engine, clean_pg):
    with pg_app_engine.begin() as c:
        row = c.execute(
            insert(users)
            .values(login_id="d", display_name="d")
            .returning(users.c.is_admin, users.c.is_active, users.c.created_at)
        ).one()
    assert row.is_admin is False and row.is_active is True and row.created_at is not None


# --- LAST_ADMIN 경쟁 안전(실제 행 잠금) ----


def _last_admin_code(engine: Engine, user_id: int, **changes) -> str:
    with Session(engine) as session:
        try:
            service.update_user(
                session,
                user_id,
                display_name=None,
                is_admin=changes.get("is_admin"),
                is_active=changes.get("is_active"),
            )
        except AppError as error:
            return error.code
    return "OK"


def _active_admin_count(engine: Engine) -> int:
    with engine.connect() as c:
        return c.execute(
            select(func.count()).select_from(users).where(users.c.is_admin, users.c.is_active)
        ).scalar_one()


def test_last_admin_guard_waits_for_a_concurrent_demotion_and_then_refuses(
    pg_owner_engine, pg_app_engine, clean_pg
):
    """한 요청이 관리자 행을 잠근 동안 다른 요청은 기다리고, 먼저 끝난 변경을 다시 읽어 거부한다."""
    a = _add_admin(pg_owner_engine, "admin-a")
    b = _add_admin(pg_owner_engine, "admin-b")
    holder = Session(pg_app_engine)
    _target, admins = repo.lock_target_and_active_admins(holder, b)
    assert sorted(admins) == sorted([a, b])
    outcome: dict[str, str] = {}
    worker = threading.Thread(
        target=lambda: outcome.setdefault(
            "code", _last_admin_code(pg_app_engine, a, is_admin=False)
        )
    )
    worker.start()
    worker.join(timeout=1.0)
    assert worker.is_alive(), "잠금을 기다려야 한다(기다리지 않으면 경쟁 구멍이다)"
    repo.update_user(holder, b, {"is_admin": False})
    holder.commit()
    holder.close()
    worker.join(timeout=10)
    assert not worker.is_alive()
    assert outcome["code"] == "LAST_ADMIN"
    assert _active_admin_count(pg_app_engine) == 1


def _demote_concurrently(engine: Engine, user_ids: list[int]) -> list[str]:
    results: list[str] = []
    barrier = threading.Barrier(len(user_ids))

    def demote(user_id: int) -> None:
        barrier.wait()
        results.append(_last_admin_code(engine, user_id, is_admin=False))

    threads = [threading.Thread(target=demote, args=(i,)) for i in user_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert not any(t.is_alive() for t in threads), "교착"
    return results


@pytest.mark.parametrize("count", [2, 3])
def test_concurrent_demotions_never_leave_zero_admins_and_do_not_deadlock(
    pg_owner_engine, pg_app_engine, clean_pg, count
):
    for round_number in range(5):
        ids = [_add_admin(pg_owner_engine, f"adm-{round_number}-{i}") for i in range(count)]
        results = _demote_concurrently(pg_app_engine, ids)
        assert sorted(results) == sorted(["OK"] * (count - 1) + ["LAST_ADMIN"]), results
        assert _active_admin_count(pg_app_engine) == 1
        with pg_owner_engine.begin() as c:
            c.execute(delete(team_members))
            c.execute(delete(users))


def _add_admin(owner: Engine, login_id: str) -> int:
    with owner.begin() as c:
        return c.execute(
            insert(users)
            .values(login_id=login_id, display_name=login_id, is_admin=True)
            .returning(users.c.id)
        ).scalar_one()
