"""정적 표 DB 권한·제약 시험(06 §2 매트릭스, 03b 3-6 BY4). 실제 PostgreSQL(tmpfs 시험 DB) 필요.

0003·0004·0005 적용 뒤 `bi_app`이 허용된 동작만 할 수 있고 `bi_readonly`가 정적 표를 읽을 수
없음을 확인한다.
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
from app.db_metadata import (
    dataset_columns,
    datasets,
    formula_deps,
    formulas,
    team_members,
    teams,
    users,
)

INSUFFICIENT_PRIVILEGE = "42501"
CHECK_VIOLATION = "23514"
UNIQUE_VIOLATION = "23505"
FOREIGN_KEY_VIOLATION = "23503"

TABLES = {
    "users": users,
    "teams": teams,
    "team_members": team_members,
    "datasets": datasets,
    "dataset_columns": dataset_columns,
    "formulas": formulas,
    "formula_deps": formula_deps,
}
# bi_app의 표 단위 권한(has_table_privilege). UPDATE는 열 단위라 표 단위로는 없다.
TABLE_PRIVILEGES = {
    "users": {"SELECT", "INSERT"},
    "teams": {"SELECT", "INSERT"},
    "team_members": {"SELECT", "INSERT", "DELETE"},
    # 0004: 삭제는 FU-1에 없다(DELETE 없음). UPDATE는 열 단위다.
    "datasets": {"SELECT", "INSERT"},
    "dataset_columns": {"SELECT", "INSERT"},
    # 0005: formulas는 DELETE 없음, formula_deps는 의존 목록을 다시 쓰므로 DELETE가 있다.
    "formulas": {"SELECT", "INSERT"},
    "formula_deps": {"SELECT", "INSERT", "DELETE"},
}
ALL_PRIVILEGES = {"SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"}
# bi_app이 UPDATE할 수 있는 열(06 §2). 나머지 열은 불변이다.
UPDATABLE = {
    "users": {"display_name", "is_admin", "is_active"},
    "teams": {"name", "is_active"},
    "team_members": {"role"},
    # team_id·created_by·created_at·id 불변(팀 열이 뷰에 상수로 들어간다), dataset_id·kind·id 불변.
    # dataset_columns.type은 계산 열 결과 형이 바뀔 때 갱신해야 해서 허용한다(원본 열은 앱 규칙).
    "datasets": {"name", "date_unit", "base_date_column_id", "status", "def_version", "def_hash"},
    "dataset_columns": {"display_name", "type", "required", "rules", "tag", "position"},
    # column_id는 불변(수식은 열에 붙박이). formula_deps는 행을 지우고 다시 넣는다(UPDATE 없음).
    "formulas": {"expression", "ast", "ast_hash"},
    "formula_deps": set(),
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


def test_immutable_columns_are_exactly_the_ones_without_update_privilege():
    """06 §2: 불변 열의 목록을 시험에 못 박는다(DB가 불변을 강제하는 열)."""
    all_columns = {name: {c.name for c in table.c} for name, table in TABLES.items()}
    immutable = {name: all_columns[name] - UPDATABLE[name] for name in TABLES}
    assert immutable["datasets"] == {"id", "team_id", "created_by", "created_at"}
    assert immutable["dataset_columns"] == {"id", "dataset_id", "kind"}
    assert immutable["users"] == {"id", "login_id", "created_at"}
    assert immutable["teams"] == {"id", "code", "created_at"}
    assert immutable["team_members"] == {"team_id", "user_id"}
    assert immutable["formulas"] == {"column_id"}
    assert immutable["formula_deps"] == {"column_id", "depends_on_column_id"}


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


def _prepare_datasets(owner: Engine) -> dict[str, int]:
    """팀·사용자와 데이터셋 둘, 첫 데이터셋의 열 둘(둘째 데이터셋의 열 하나)을 만든다."""
    ids = _prepare(owner)
    with owner.begin() as c:
        first = c.execute(
            insert(datasets)
            .values(
                team_id=ids["team"],
                name="D1",
                date_unit="month",
                created_by=ids["user"],
                def_hash="h",
            )
            .returning(datasets.c.id)
        ).scalar_one()
        second = c.execute(
            insert(datasets)
            .values(
                team_id=ids["team"],
                name="D2",
                date_unit="day",
                created_by=ids["user"],
                def_hash="h",
            )
            .returning(datasets.c.id)
        ).scalar_one()

        def column(dataset_id, name, column_type="date", kind="raw", **extra):
            return c.execute(
                insert(dataset_columns)
                .values(
                    dataset_id=dataset_id,
                    display_name=name,
                    type=column_type,
                    kind=kind,
                    position=0,
                    **extra,
                )
                .returning(dataset_columns.c.id)
            ).scalar_one()

        col = column(first, "C1")
        col2 = column(first, "C2", "number")
        other_col = column(second, "C1")
    return {**ids, "ds": first, "ds2": second, "col": col, "col2": col2, "other_col": other_col}


def test_bi_app_allowed_dataset_operations(pg_owner_engine, pg_app_engine, clean_pg):
    ids = _prepare_datasets(pg_owner_engine)
    with pg_app_engine.begin() as c:
        new_dataset = c.execute(
            insert(datasets)
            .values(
                team_id=ids["team"],
                name="D3",
                date_unit="year",
                created_by=ids["user"],
                def_hash="h",
            )
            .returning(datasets.c.id)
        ).scalar_one()
        # 허용된 열만 UPDATE(기준 날짜 열은 같은 데이터셋의 열이어야 한다).
        c.execute(
            update(datasets)
            .where(datasets.c.id == ids["ds"])
            .values(
                name="새 이름",
                date_unit="year",
                base_date_column_id=ids["col"],
                status="active",
                def_version=2,
                def_hash="h2",
            )
        )
        column_id = c.execute(
            insert(dataset_columns)
            .values(
                dataset_id=new_dataset,
                display_name="A",
                type="choice",
                kind="raw",
                required=True,
                rules={"options": ["가", "나"]},
                tag=None,
                position=0,
            )
            .returning(dataset_columns.c.id)
        ).scalar_one()
        c.execute(
            update(dataset_columns)
            .where(dataset_columns.c.id == column_id)
            .values(
                display_name="B",
                type="text",
                required=False,
                rules={"max_length": 3},
                tag="t",
                position=4,
            )
        )
        # 정의 변경 직렬화 잠금과 행 쓰기 잠금은 열 단위 UPDATE 권한만으로 실행된다(06 §5).
        c.execute(select(datasets.c.id).with_for_update(key_share=True)).all()
        c.execute(select(datasets.c.id).with_for_update(read=True)).all()
    row = _read_dataset(pg_owner_engine, ids["ds"])
    assert (row["name"], row["date_unit"], row["base_date_column_id"], row["def_version"]) == (
        "새 이름",
        "year",
        ids["col"],
        2,
    )


def _read_dataset(engine: Engine, dataset_id: int):
    with engine.connect() as c:
        return c.execute(select(datasets).where(datasets.c.id == dataset_id)).mappings().one()


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


# 0004 표의 거부: 불변 열(team_id·created_by·created_at·id, dataset_id·kind·id)과 DELETE.
DENIED_DATASETS = [
    pytest.param(
        lambda i: update(datasets).where(datasets.c.id == i["ds"]).values(team_id=i["team"]),
        id="datasets.team_id",
    ),
    pytest.param(
        lambda i: update(datasets).where(datasets.c.id == i["ds"]).values(created_by=i["user"]),
        id="datasets.created_by",
    ),
    pytest.param(
        lambda i: update(datasets).where(datasets.c.id == i["ds"]).values(created_at=func.now()),
        id="datasets.created_at",
    ),
    pytest.param(lambda i: update(datasets).values(id=999), id="datasets.id"),
    pytest.param(lambda i: delete(datasets).where(datasets.c.id == i["ds2"]), id="datasets.delete"),
    pytest.param(
        lambda i: (
            update(dataset_columns)
            .where(dataset_columns.c.id == i["col"])
            .values(dataset_id=i["ds2"])
        ),
        id="dataset_columns.dataset_id",
    ),
    pytest.param(
        lambda i: (
            update(dataset_columns).where(dataset_columns.c.id == i["col"]).values(kind="formula")
        ),
        id="dataset_columns.kind",
    ),
    pytest.param(lambda i: update(dataset_columns).values(id=999), id="dataset_columns.id"),
    pytest.param(
        lambda i: delete(dataset_columns).where(dataset_columns.c.id == i["col"]),
        id="dataset_columns.delete",
    ),
]


@pytest.mark.parametrize("make_statement", DENIED_DATASETS)
def test_bi_app_denied_dataset_operations(pg_owner_engine, pg_app_engine, clean_pg, make_statement):
    ids = _prepare_datasets(pg_owner_engine)
    with pytest.raises(DBAPIError) as error, pg_app_engine.begin() as c:
        c.execute(make_statement(ids))
    assert sqlstate(error.value) == INSUFFICIENT_PRIVILEGE


def _prepare_formulas(owner: Engine) -> dict[str, int]:
    """계산 열 둘(수식 하나)과 원본 열 둘을 가진 데이터셋을 만든다."""
    ids = _prepare_datasets(owner)
    with owner.begin() as c:
        calc = c.execute(
            insert(dataset_columns)
            .values(
                dataset_id=ids["ds"],
                display_name="계산",
                type="number",
                kind="formula",
                position=1,
            )
            .returning(dataset_columns.c.id)
        ).scalar_one()
        c.execute(
            insert(formulas).values(
                column_id=calc, expression="[C2]", ast={"t": "col", "id": ids["col2"]}, ast_hash="h"
            )
        )
        c.execute(insert(formula_deps).values(column_id=calc, depends_on_column_id=ids["col2"]))
    return {**ids, "calc": calc}


DENIED_FORMULAS = [
    pytest.param(
        lambda i: update(formulas).where(formulas.c.column_id == i["calc"]).values(column_id=999),
        id="formulas.column_id",
    ),
    pytest.param(
        lambda i: delete(formulas).where(formulas.c.column_id == i["calc"]), id="formulas.delete"
    ),
    pytest.param(
        lambda i: update(formula_deps).values(depends_on_column_id=i["col"]),
        id="formula_deps.update",
    ),
]


@pytest.mark.parametrize("make_statement", DENIED_FORMULAS)
def test_bi_app_denied_formula_operations(pg_owner_engine, pg_app_engine, clean_pg, make_statement):
    ids = _prepare_formulas(pg_owner_engine)
    with pytest.raises(DBAPIError) as error, pg_app_engine.begin() as c:
        c.execute(make_statement(ids))
    assert sqlstate(error.value) == INSUFFICIENT_PRIVILEGE


def test_bi_app_allowed_formula_operations(pg_owner_engine, pg_app_engine, clean_pg):
    ids = _prepare_formulas(pg_owner_engine)
    with pg_app_engine.begin() as c:
        other = c.execute(
            insert(dataset_columns)
            .values(
                dataset_id=ids["ds2"], display_name="계산2", type="text", kind="formula", position=1
            )
            .returning(dataset_columns.c.id)
        ).scalar_one()
        c.execute(
            insert(formulas).values(
                column_id=other, expression='"a"', ast={"t": "text", "v": "a"}, ast_hash="h2"
            )
        )
        c.execute(
            update(formulas)
            .where(formulas.c.column_id == ids["calc"])
            .values(expression="[C2] + 1", ast={"t": "num", "v": "1"}, ast_hash="h3")
        )
        c.execute(delete(formula_deps).where(formula_deps.c.column_id == ids["calc"]))
        c.execute(
            insert(formula_deps).values(column_id=ids["calc"], depends_on_column_id=ids["col"])
        )
        # 잠금 읽기 없이 SELECT만으로 읽을 수 있다.
        assert c.execute(select(func.count()).select_from(formulas)).scalar_one() == 2


def test_formula_constraints(pg_owner_engine, pg_app_engine, clean_pg):
    ids = _prepare_formulas(pg_owner_engine)
    # 자기 자신을 가리키는 의존: CHECK
    with pytest.raises(DBAPIError) as error, pg_app_engine.begin() as c:
        c.execute(
            insert(formula_deps).values(column_id=ids["calc"], depends_on_column_id=ids["calc"])
        )
    assert sqlstate(error.value) == CHECK_VIOLATION
    # 열 하나에 수식 하나: 기본키
    with pytest.raises(DBAPIError) as error, pg_app_engine.begin() as c:
        c.execute(
            insert(formulas).values(
                column_id=ids["calc"], expression="x", ast={"t": "num", "v": "1"}, ast_hash="h"
            )
        )
    assert sqlstate(error.value) == UNIQUE_VIOLATION
    # 중복 의존: 기본키
    with pytest.raises(DBAPIError) as error, pg_app_engine.begin() as c:
        c.execute(
            insert(formula_deps).values(column_id=ids["calc"], depends_on_column_id=ids["col2"])
        )
    assert sqlstate(error.value) == UNIQUE_VIOLATION
    # 없는 열을 가리키는 수식·의존: 외래키
    with pytest.raises(DBAPIError) as error, pg_app_engine.begin() as c:
        c.execute(
            insert(formulas).values(
                column_id=999999, expression="x", ast={"t": "num", "v": "1"}, ast_hash="h"
            )
        )
    assert sqlstate(error.value) == FOREIGN_KEY_VIOLATION
    with pytest.raises(DBAPIError) as error, pg_app_engine.begin() as c:
        c.execute(insert(formula_deps).values(column_id=ids["calc"], depends_on_column_id=999999))
    assert sqlstate(error.value) == FOREIGN_KEY_VIOLATION
    # ast는 NOT NULL
    with pytest.raises(DBAPIError) as error, pg_app_engine.begin() as c:
        c.execute(
            insert(formulas).values(
                column_id=ids["col"], expression="x", ast=sa.null(), ast_hash="h"
            )
        )
    assert sqlstate(error.value) == "23502"


def test_bi_app_cannot_truncate_or_alter_static_tables(pg_app_engine, clean_pg):
    for table in ("datasets", "dataset_columns", "formulas", "formula_deps"):
        with pytest.raises(DBAPIError) as error, pg_app_engine.begin() as c:
            c.execute(sa.schema.DDL(f"TRUNCATE TABLE {table}"))
        assert sqlstate(error.value) == INSUFFICIENT_PRIVILEGE
    with pytest.raises(DBAPIError) as error, pg_app_engine.begin() as c:
        c.execute(sa.schema.DDL("ALTER TABLE datasets ADD COLUMN evil text"))
    assert sqlstate(error.value) == INSUFFICIENT_PRIVILEGE


def test_bi_readonly_cannot_read_static_tables(pg_owner_engine, pg_readonly_engine, clean_pg):
    _prepare(pg_owner_engine)
    for table in (users, teams, team_members, formulas, formula_deps):
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


def test_dataset_constraints(pg_owner_engine, pg_app_engine, clean_pg):
    ids = _prepare_datasets(pg_owner_engine)

    def fails(statement, code, name):
        with pytest.raises(DBAPIError) as error, pg_app_engine.begin() as c:
            c.execute(statement)
        assert sqlstate(error.value) == code and name in str(error.value.orig), error.value

    def new_dataset(**values):
        base = dict(team_id=ids["team"], name="N", date_unit="day", created_by=ids["user"])
        return insert(datasets).values(**{**base, "def_hash": "h", **values})

    def new_column(**values):
        base = dict(dataset_id=ids["ds"], display_name="N", type="text", kind="raw", position=0)
        return insert(dataset_columns).values(**{**base, **values})

    # 팀 안 데이터셋 이름 유일(다른 팀은 같은 이름 가능, 아래 두 번째 팀으로 확인)
    fails(new_dataset(name="D1"), UNIQUE_VIOLATION, "uq_datasets_team_id_name")
    fails(new_dataset(date_unit="week"), CHECK_VIOLATION, "ck_datasets_date_unit")
    fails(new_dataset(status="archived"), CHECK_VIOLATION, "ck_datasets_status")
    fails(new_dataset(team_id=99999), FOREIGN_KEY_VIOLATION, "fk_datasets_team_id_teams")
    fails(new_dataset(created_by=99999), FOREIGN_KEY_VIOLATION, "fk_datasets_created_by_users")
    # 열: 데이터셋 안 표시 이름 유일, 열거 CHECK, 계산 열은 필수·선택 목록 형이 아님
    fails(
        new_column(display_name="C1"),
        UNIQUE_VIOLATION,
        "uq_dataset_columns_dataset_id_display_name",
    )
    fails(new_column(type="reference"), CHECK_VIOLATION, "ck_dataset_columns_type")
    fails(new_column(kind="query"), CHECK_VIOLATION, "ck_dataset_columns_kind")
    fails(
        new_column(kind="formula", required=True),
        CHECK_VIOLATION,
        "ck_dataset_columns_formula_shape",
    )
    fails(
        new_column(kind="formula", type="choice"),
        CHECK_VIOLATION,
        "ck_dataset_columns_formula_shape",
    )
    fails(
        new_column(dataset_id=99999),
        FOREIGN_KEY_VIOLATION,
        "fk_dataset_columns_dataset_id_datasets",
    )
    with pg_app_engine.begin() as c:  # 원본 열은 필수·선택 목록 가능, 계산 열은 선택 목록 아닌 형
        c.execute(new_column(display_name="필수", required=True))
        c.execute(new_column(display_name="선택", type="choice", rules={"options": ["a"]}))
        c.execute(new_column(display_name="계산", kind="formula", type="number"))
    # 같은 이름은 다른 데이터셋에서 가능하다.
    with pg_app_engine.begin() as c:
        c.execute(new_column(dataset_id=ids["ds2"], display_name="C2"))
        team2 = c.execute(
            insert(teams).values(code="t9", name="T9").returning(teams.c.id)
        ).scalar_one()
        c.execute(new_dataset(team_id=team2, name="D1"))


def test_base_date_column_must_belong_to_the_same_dataset(pg_owner_engine, pg_app_engine, clean_pg):
    """복합 FK: 다른 데이터셋의 열을 기준 날짜 열로 지정할 수 없다(NULL은 허용)."""
    ids = _prepare_datasets(pg_owner_engine)

    def set_base(value):
        return update(datasets).where(datasets.c.id == ids["ds"]).values(base_date_column_id=value)

    with pytest.raises(DBAPIError) as error, pg_app_engine.begin() as c:
        c.execute(set_base(ids["other_col"]))
    assert sqlstate(error.value) == FOREIGN_KEY_VIOLATION
    assert "fk_datasets_id_dataset_columns" in str(error.value.orig)
    with pytest.raises(DBAPIError) as error, pg_app_engine.begin() as c:
        c.execute(set_base(99999))
    assert sqlstate(error.value) == FOREIGN_KEY_VIOLATION
    with pg_app_engine.begin() as c:
        c.execute(set_base(ids["col"]))
        c.execute(set_base(None))


def test_rules_column_stores_sql_null_and_jsonb(pg_owner_engine, pg_app_engine, clean_pg):
    ids = _prepare_datasets(pg_owner_engine)
    with pg_app_engine.begin() as c:
        c.execute(
            update(dataset_columns)
            .where(dataset_columns.c.id == ids["col"])
            .values(rules={"min": "0", "options": ["가"]})
        )
        c.execute(
            update(dataset_columns)
            .where(dataset_columns.c.id == ids["col2"])
            .values(rules=sa.null())
        )
    with pg_owner_engine.connect() as c:
        rows = {
            r.id: r.rules for r in c.execute(select(dataset_columns.c.id, dataset_columns.c.rules))
        }
        assert rows[ids["col"]] == {"min": "0", "options": ["가"]} and rows[ids["col2"]] is None
        kind = c.execute(
            select(sa.func.jsonb_typeof(dataset_columns.c.rules)).where(
                dataset_columns.c.id == ids["col"]
            )
        ).scalar_one()
        assert kind == "object"


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
