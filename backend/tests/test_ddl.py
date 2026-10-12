"""런타임 동적 DDL(`app/ddl`, `bi-review` 7-4): 허용 목록 게이트, 정적 검사, 실제 PostgreSQL 동작.

앞부분은 DB 없이, `test_pg_*`는 tmpfs 시험 DB(`bi_app` 연결)에서 실행한다.
"""

import ast
import itertools
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import Column, MetaData, Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError
from sqlalchemy.schema import (
    AddConstraint,
    CreateIndex,
    CreateSchema,
    CreateSequence,
    CreateTable,
    DropConstraint,
    DropIndex,
    DropTable,
)

from app import ddl
from app.config import get_settings
from app.core.startup_check import check_bi_data_objects, check_static_tables
from app.db_metadata import DYNAMIC_SCHEMA

BACKEND = Path(__file__).resolve().parent.parent
APP = BACKEND / "app"
_numbers = itertools.count(9001)


def new_number() -> int:
    return next(_numbers)


# --- 정적 검사: 런타임 DDL은 ddl 모듈에만, text()/exec_driver_sql 금지 ----

# `bi-review` 7-4: 이 이름들은 app/ddl 밖에서 쓰면 안 된다(런타임 DDL은 한 모듈에만).
DDL_ONLY_NAMES = {
    "CreateTable",
    "DropTable",
    "CreateIndex",
    "DropIndex",
    "AddConstraint",
    "DropConstraint",
    "CreateView",
    "DropView",
    "CreateSequence",
    "DropSequence",
    "CreateSchema",
    "DropSchema",
    "Operations",
    "MigrationContext",
}
BANNED_EVERYWHERE = {"exec_driver_sql", "literal_binds"}
# 07 §4-1: 수식 상수를 SQL 글자로 렌더하는 `literal_binds`는 **리터럴 렌더러 접점 한 곳**만 예외다.
# 그 파일에는 `compile_kwargs={"literal_binds": True}` 한 줄(문자열 키)만 있어야 한다.
LITERAL_RENDERER = APP / "formula" / "literals.py"


def _sources(under: Path) -> list[Path]:
    return sorted(p for p in under.rglob("*.py") if "__pycache__" not in p.parts)


def raw_sql_findings(tree: ast.AST) -> list[str]:
    """`text()` 호출·가져오기, `exec_driver_sql`, `literal_binds` 사용."""
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("sqlalchemy"):
            found += [f"import {a.name}" for a in node.names if a.name == "text"]
        if isinstance(node, ast.Attribute):
            if node.attr in BANNED_EVERYWHERE:
                found.append(node.attr)
            if (
                node.attr == "text"
                and isinstance(node.value, ast.Name)
                and node.value.id in {"sa", "sqlalchemy"}
            ):
                found.append(f"{node.value.id}.text")
        if isinstance(node, ast.keyword) and node.arg in BANNED_EVERYWHERE:
            found.append(node.arg)
        if isinstance(node, ast.Name) and node.id in BANNED_EVERYWHERE:
            found.append(node.id)
        # `compile_kwargs={"literal_binds": True}`처럼 사전 키로 쓰는 경우도 같은 규칙으로 잡는다.
        if isinstance(node, ast.Constant) and node.value == "literal_binds":
            found.append("literal_binds")
    return found


def ddl_name_findings(tree: ast.AST) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            found += [a.name for a in node.names if a.name in DDL_ONLY_NAMES]
        if isinstance(node, ast.Name) and node.id in DDL_ONLY_NAMES:
            found.append(node.id)
        if isinstance(node, ast.Attribute) and node.attr in DDL_ONLY_NAMES:
            found.append(node.attr)
    return found


def test_app_code_has_no_raw_sql_text_anywhere():
    for path in _sources(APP):
        findings = raw_sql_findings(ast.parse(path.read_text(encoding="utf-8")))
        if path == LITERAL_RENDERER:
            continue  # 아래 시험이 이 한 곳의 예외를 정확히 고정한다
        assert findings == [], path


def test_literal_binds_exception_is_exactly_the_one_renderer_line():
    findings = raw_sql_findings(ast.parse(LITERAL_RENDERER.read_text(encoding="utf-8")))
    assert findings == ["literal_binds"]  # 한 번뿐이고 다른 금지 항목(text 등)은 없다


def test_runtime_ddl_lives_only_in_the_ddl_module():
    for path in _sources(APP):
        if "ddl" in path.relative_to(APP).parts[:1]:
            continue
        assert ddl_name_findings(ast.parse(path.read_text(encoding="utf-8"))) == [], path


def string_assembly_findings(tree: ast.AST, *, allow_fstrings: bool) -> list[str]:
    """문자열 조립 흔적: `.format()`, 문자열 `+`·`%`, 예외 메시지 밖의 f-string."""
    inside_raise = {
        id(child)
        for node in ast.walk(tree)
        if isinstance(node, ast.Raise)
        for child in ast.walk(node)
    }
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "format":
            found.append(f"format 줄 {node.lineno}")
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add | ast.Mod):
            operands = (node.left, node.right)
            if any(isinstance(o, ast.Constant) and isinstance(o.value, str) for o in operands):
                found.append(f"문자열 연산 줄 {node.lineno}")
        if isinstance(node, ast.JoinedStr) and not allow_fstrings and id(node) not in inside_raise:
            found.append(f"f-string 줄 {node.lineno}")
    return found


def test_the_ddl_module_does_not_assemble_sql_strings():
    """이름은 `names.py` 규칙 함수만 f-string으로 만들고, 그 밖에서는 예외 메시지에서만 쓴다."""
    for path in _sources(APP / "ddl"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        findings = string_assembly_findings(tree, allow_fstrings=path.name == "names.py")
        assert findings == [], (path, findings)


def test_string_assembly_detector():
    assert string_assembly_findings(ast.parse('x = f"a{b}"\n'), allow_fstrings=False)
    assert not string_assembly_findings(ast.parse('raise E(f"a{b}")\n'), allow_fstrings=False)
    assert string_assembly_findings(ast.parse('x = "a{}".format(b)\n'), allow_fstrings=True)
    assert string_assembly_findings(ast.parse('x = "a" + b\n'), allow_fstrings=True)
    assert string_assembly_findings(ast.parse('x = "a%s" % b\n'), allow_fstrings=True)
    assert not string_assembly_findings(ast.parse("x = a + b\n"), allow_fstrings=False)


def test_static_detectors_catch_what_they_should():
    assert raw_sql_findings(ast.parse("from sqlalchemy import text\n"))
    assert raw_sql_findings(ast.parse("import sqlalchemy as sa\nsa.text('x')\n"))
    assert raw_sql_findings(ast.parse("conn.exec_driver_sql('x')\n"))
    assert raw_sql_findings(ast.parse("f(literal_binds=True)\n"))
    assert raw_sql_findings(ast.parse('f(compile_kwargs={"literal_binds": True})\n'))
    assert not raw_sql_findings(ast.parse("from sqlalchemy import Text\nx = Text()\n"))
    assert ddl_name_findings(ast.parse("from sqlalchemy.schema import CreateTable\n"))
    assert ddl_name_findings(ast.parse("schema.DropView(v)\n"))
    assert not ddl_name_findings(ast.parse("select(1)\n"))


# --- 허용 목록 게이트 ----


class RecordingConnection:
    def __init__(self) -> None:
        self.executed: list[object] = []

    def execute(self, element: object) -> None:
        self.executed.append(element)


def _table(name: str = "ds_1", schema: str | None = DYNAMIC_SCHEMA, *columns: Column) -> Table:
    return Table(name, MetaData(), *columns, schema=schema)


def test_gate_runs_allowed_ddl_on_valid_names():
    conn = RecordingConnection()
    table = _table("ds_1", DYNAMIC_SCHEMA, Column("row_id", sa.BigInteger, primary_key=True))
    ddl.run_ddl(conn, CreateTable(table))
    assert len(conn.executed) == 1


@pytest.mark.parametrize(
    "make_element",
    [
        pytest.param(lambda: CreateSequence(sa.Sequence("seq_1", schema="bi_data")), id="sequence"),
        pytest.param(lambda: CreateSchema("evil"), id="schema"),
        pytest.param(lambda: DropTable(_table()), id="drop-table"),
        pytest.param(lambda: sa.DDL("DROP TABLE public.users"), id="raw-ddl"),
        pytest.param(lambda: CreateTable(_table("ds_1", "public")), id="create-in-public"),
        pytest.param(lambda: CreateTable(_table("ds_1", None)), id="create-without-schema"),
        pytest.param(lambda: CreateTable(_table("evil")), id="create-bad-table-name"),
        pytest.param(lambda: CreateTable(_table("ds_01")), id="create-leading-zero"),
        pytest.param(
            lambda: CreateTable(_table("ds_1", DYNAMIC_SCHEMA, Column("매출", sa.Text))),
            id="create-bad-column-name",
        ),
        pytest.param(
            lambda: CreateTable(
                _table(
                    "ds_1",
                    DYNAMIC_SCHEMA,
                    Column("row_id", sa.BigInteger, sa.Sequence("s"), primary_key=True),
                )
            ),
            id="create-with-independent-sequence",
        ),
        pytest.param(
            lambda: CreateTable(
                _table(
                    "ds_1",
                    DYNAMIC_SCHEMA,
                    Column("c_1", sa.Text, server_default=sa.text("now()::text")),
                )
            ),
            id="create-with-server-default",
        ),
        pytest.param(
            lambda: CreateTable(
                _table(
                    "ds_1",
                    DYNAMIC_SCHEMA,
                    Column("c_1", sa.Text),
                    sa.CheckConstraint("true", name="my_constraint"),
                )
            ),
            id="create-bad-constraint-name",
        ),
        pytest.param(
            lambda: CreateTable(
                _table(
                    "ds_1",
                    DYNAMIC_SCHEMA,
                    Column("row_id", sa.BigInteger, primary_key=True),
                    Column("c_1", sa.Integer, sa.Computed("row_id * 2")),
                )
            ),
            id="create-with-computed-column",
        ),
        pytest.param(
            lambda: CreateTable(
                _table(
                    "ds_1",
                    DYNAMIC_SCHEMA,
                    Column("row_id", sa.BigInteger, primary_key=True),
                    Column("c_1", sa.BigInteger, sa.ForeignKey("bi_data.ds_2.row_id")),
                )
            ),
            id="create-with-foreign-key",
        ),
        pytest.param(
            lambda: CreateTable(
                _table(
                    "ds_1",
                    DYNAMIC_SCHEMA,
                    Column("row_id", sa.BigInteger, primary_key=True),
                    Column("c_1", sa.Text, unique=True),
                )
            ),
            id="create-with-unique-column",
        ),
        pytest.param(
            lambda: CreateTable(
                _table(
                    "ds_1",
                    DYNAMIC_SCHEMA,
                    Column("row_id", sa.BigInteger, primary_key=True),
                    Column("c_1", sa.Text),
                    sa.UniqueConstraint("c_1", name="ck_ds_1_period"),
                )
            ),
            id="create-with-unique-constraint",
        ),
    ],
)
def test_gate_refuses_everything_outside_the_allow_list(make_element):
    conn = RecordingConnection()
    with pytest.raises((ddl.DdlNotAllowedError, ddl.DdlNameError)):
        ddl.run_ddl(conn, make_element())
    assert conn.executed == []  # 실행 전에 거부한다


def test_gate_checks_index_and_constraint_names_and_kinds():
    conn = RecordingConnection()
    table = _table("ds_1", DYNAMIC_SCHEMA, Column("c_1", sa.Date))
    good_index = sa.Index("ux_ds_1_period", table.c.c_1, unique=True)
    ddl.run_ddl(conn, CreateIndex(good_index))
    ddl.run_ddl(conn, DropIndex(good_index))
    good_check = sa.CheckConstraint(table.c.c_1.is_not(None), name="ck_ds_1_period")
    table.append_constraint(good_check)
    ddl.run_ddl(conn, AddConstraint(good_check))
    ddl.run_ddl(conn, DropConstraint(good_check))
    assert len(conn.executed) == 4

    bad_index = sa.Index("my_index", table.c.c_1)
    with pytest.raises(ddl.DdlNameError):
        ddl.run_ddl(conn, CreateIndex(bad_index))
    unique = sa.UniqueConstraint(table.c.c_1, name="ck_ds_1_period")
    table.append_constraint(unique)
    with pytest.raises(ddl.DdlNotAllowedError):  # CHECK 외의 제약은 만들지 않는다
        ddl.run_ddl(conn, AddConstraint(unique))
    other = _table("users", "public", Column("c_1", sa.Date))
    with pytest.raises((ddl.DdlNotAllowedError, ddl.DdlNameError)):
        ddl.run_ddl(conn, CreateIndex(sa.Index("ux_ds_1_period", other.c.c_1)))
    assert len(conn.executed) == 4


def test_create_table_allows_primary_key_and_named_check_only():
    conn = RecordingConnection()
    table = _table(
        "ds_1",
        DYNAMIC_SCHEMA,
        Column("row_id", sa.BigInteger, primary_key=True),
        Column("c_1", sa.Date),
    )
    table.append_constraint(sa.CheckConstraint("c_1 IS NOT NULL", name="ck_ds_1_period"))
    ddl.run_ddl(conn, CreateTable(table))
    assert len(conn.executed) == 1


def test_every_ddl_helper_checks_all_the_names_it_uses(monkeypatch):
    """`add_raw_column`·`add_period_rules`·`drop_period_rules`도 이름 불변식을 거친다."""
    from app.ddl import dynamic

    seen: list[tuple[str, str | None]] = []
    real = dynamic.check_dynamic_name

    def recording(name, kind=None):
        seen.append((name, kind))
        return real(name, kind)

    class FakeOperations:
        def __init__(self, _context) -> None:
            pass

        def add_column(self, *args, **kwargs) -> None:
            pass

        def alter_column(self, *args, **kwargs) -> None:
            pass

    monkeypatch.setattr(dynamic, "check_dynamic_name", recording)
    monkeypatch.setattr(dynamic, "Operations", FakeOperations)
    monkeypatch.setattr(dynamic.MigrationContext, "configure", staticmethod(lambda conn: None))
    monkeypatch.setattr(dynamic, "_existing_columns", lambda conn, dataset_id: {"c_7": "date"})
    conn = RecordingConnection()
    dynamic.add_raw_column(conn, 3, 7, "date")
    assert {("ds_3", "table"), ("c_7", "column")} <= set(seen)
    seen.clear()
    dynamic.add_period_rules(conn, 3, 7, "month")
    assert {
        ("ds_3", "table"),
        ("c_7", "column"),
        ("ck_ds_3_period", "constraint"),
        ("ux_ds_3_period", "index"),
    } <= set(seen)
    seen.clear()
    dynamic.drop_period_rules(conn, 3, 7)
    assert {
        ("ds_3", "table"),
        ("c_7", "column"),
        ("ck_ds_3_period", "constraint"),
        ("ux_ds_3_period", "index"),
    } <= set(seen)


def test_unsupported_column_type_and_date_unit_are_refused_before_any_ddl():
    conn = RecordingConnection()
    with pytest.raises(ddl.DdlNotAllowedError):
        ddl.add_raw_column(conn, 1, 1, "reference")  # type: ignore[arg-type]
    with pytest.raises(ddl.DdlNotAllowedError):
        ddl.add_period_rules(conn, 1, 1, "week")  # type: ignore[arg-type]
    with pytest.raises(ddl.DdlNameError):
        ddl.add_raw_column(conn, 0, 1, "text")  # type: ignore[arg-type]
    with pytest.raises(ddl.DdlNameError):
        ddl.create_dataset_table(conn, "1; DROP TABLE users")  # type: ignore[arg-type]
    assert conn.executed == []


def test_created_table_ddl_is_bigint_identity_primary_key():
    table = Table(
        "ds_5",
        MetaData(),
        Column("row_id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
        schema=DYNAMIC_SCHEMA,
    )
    sql = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    assert "bi_data.ds_5" in sql
    assert "row_id BIGINT GENERATED BY DEFAULT AS IDENTITY" in sql
    assert "PRIMARY KEY (row_id)" in sql


# --- 실제 PostgreSQL (`bi_app` 연결) ----


def columns_of(conn, number):
    return {
        c["name"]: c for c in sa.inspect(conn).get_columns(f"ds_{number}", schema=DYNAMIC_SCHEMA)
    }


def sqlstate_of(error: DBAPIError) -> str:
    return str(error.orig.args[0].get("C"))


def test_pg_create_table_has_identity_pk_owned_by_bi_app_and_readable_by_readonly(
    pg_app_engine, pg_readonly_engine, pg_owner_engine, clean_pg
):
    number = new_number()
    with pg_app_engine.begin() as conn:
        ddl.create_dataset_table(conn, number)
    with pg_app_engine.connect() as conn:
        cols = columns_of(conn, number)
        assert list(cols) == ["row_id"]
        assert "bigint" in str(cols["row_id"]["type"]).lower()
        assert cols["row_id"].get("identity") is not None
        assert sa.inspect(conn).get_pk_constraint(f"ds_{number}", schema=DYNAMIC_SCHEMA)[
            "constrained_columns"
        ] == ["row_id"]
    table = sa.table(f"ds_{number}", sa.column("row_id"), schema=DYNAMIC_SCHEMA)
    with pg_app_engine.begin() as conn:
        conn.execute(sa.insert(table).values({}))  # 기본값으로 row_id가 붙는다
        conn.execute(sa.insert(table).values(row_id=100))  # 명시 값도 허용(BY DEFAULT)
    with pg_app_engine.connect() as conn:
        assert [r[0] for r in conn.execute(sa.select(table.c.row_id).order_by(table.c.row_id))] == [
            1,
            100,
        ]
    with pg_owner_engine.connect() as conn:
        owner = conn.execute(
            sa.select(sa.column("tableowner"))
            .select_from(sa.table("pg_tables", schema="pg_catalog"))
            .where(
                sa.column("schemaname") == DYNAMIC_SCHEMA, sa.column("tablename") == f"ds_{number}"
            )
        ).scalar_one()
    assert owner == "bi_app"
    # bi_readonly는 기본 권한으로 SELECT만 가능하다(0002).
    with pg_readonly_engine.connect() as conn:
        assert conn.execute(sa.select(sa.func.count()).select_from(table)).scalar_one() == 2
    with pytest.raises(DBAPIError) as error, pg_readonly_engine.begin() as conn:
        conn.execute(sa.insert(table).values(row_id=7))
    # 읽기 전용 트랜잭션(25006)이 먼저 막고, 풀려도 INSERT 권한이 없다(42501).
    assert sqlstate_of(error.value) in {"25006", "42501"}


def test_pg_privileges_on_a_created_table_are_select_only_for_readonly(
    pg_app_engine, pg_owner_engine, clean_pg
):
    """`bi_readonly`는 기본 권한으로 SELECT만 받고 PUBLIC에는 아무 권한도 없다(0002, X-15)."""
    number = new_number()
    with pg_app_engine.begin() as conn:
        ddl.create_dataset_table(conn, number)
    name = f"{DYNAMIC_SCHEMA}.ds_{number}"
    with pg_owner_engine.connect() as conn:

        def has(role: str, privilege: str) -> bool:
            return bool(
                conn.execute(sa.select(sa.func.has_table_privilege(role, name, privilege))).scalar()
            )

        assert has("bi_readonly", "SELECT") is True
        for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
            assert has("bi_readonly", privilege) is False, privilege
        acl = conn.execute(
            sa.select(sa.cast(sa.column("relacl"), sa.Text))
            .select_from(sa.table("pg_class", schema="pg_catalog"))
            .where(sa.column("oid") == sa.func.to_regclass(name))
        ).scalar_one()
    assert not any(part.startswith("=") for part in acl.strip("{}").split(","))  # PUBLIC 없음


@pytest.mark.parametrize(
    ("column_type", "pg_type"),
    [
        ("text", "text"),
        ("number", "numeric"),
        ("date", "date"),
        ("boolean", "boolean"),
        ("choice", "text"),
    ],
)
def test_pg_add_raw_column_types(pg_app_engine, clean_pg, column_type, pg_type):
    number = new_number()
    with pg_app_engine.begin() as conn:
        ddl.create_dataset_table(conn, number)
        ddl.add_raw_column(conn, number, 41, column_type)
    with pg_app_engine.connect() as conn:
        col = columns_of(conn, number)["c_41"]
    assert str(col["type"]).lower() == pg_type
    assert col["nullable"] is True  # 빈 칸은 NULL(미입력)


def test_pg_added_columns_accept_null_and_values(pg_app_engine, clean_pg):
    number = new_number()
    with pg_app_engine.begin() as conn:
        ddl.create_dataset_table(conn, number)
        ddl.add_raw_column(conn, number, 1, "number")
        ddl.add_raw_column(conn, number, 2, "text")
    table = sa.table(
        f"ds_{number}",
        sa.column("row_id"),
        sa.column("c_1"),
        sa.column("c_2"),
        schema=DYNAMIC_SCHEMA,
    )
    with pg_app_engine.begin() as conn:
        conn.execute(sa.insert(table).values(row_id=1, c_1=None, c_2=None))
        conn.execute(sa.insert(table).values(row_id=2, c_1=12.5, c_2="값"))
        assert conn.execute(sa.select(table.c.c_1).where(table.c.row_id == 1)).scalar_one() is None


def test_pg_rollback_leaves_no_table_or_column(pg_app_engine, clean_pg):
    """등록 + 표 생성 원자성의 바탕: 같은 트랜잭션에서 실패하면 만든 표와 열이 모두 사라진다."""
    number = new_number()
    with pytest.raises(RuntimeError), pg_app_engine.begin() as conn:
        ddl.create_dataset_table(conn, number)
        ddl.add_raw_column(conn, number, 1, "text")
        assert "c_1" in columns_of(conn, number)
        raise RuntimeError("등록 단계에서 실패")
    assert not sa.inspect(pg_app_engine).has_table(f"ds_{number}", schema=DYNAMIC_SCHEMA)


def test_pg_duplicate_table_or_column_fails_loudly(pg_app_engine, clean_pg):
    number = new_number()
    with pg_app_engine.begin() as conn:
        ddl.create_dataset_table(conn, number)
        ddl.add_raw_column(conn, number, 1, "text")
    with pytest.raises(DBAPIError), pg_app_engine.begin() as conn:
        ddl.create_dataset_table(conn, number)
    with pytest.raises(DBAPIError), pg_app_engine.begin() as conn:
        ddl.add_raw_column(conn, number, 1, "text")


def _period_table(number):
    return sa.table(
        f"ds_{number}", sa.column("row_id"), sa.column("c_7", sa.Date), schema=DYNAMIC_SCHEMA
    )


def _prepare_period(engine, unit):
    number = new_number()
    with engine.begin() as conn:
        ddl.create_dataset_table(conn, number)
        ddl.add_raw_column(conn, number, 7, "date")
        ddl.add_period_rules(conn, number, 7, unit)
    return number


def _insert_fails(engine, number, value, state, constraint=None):
    table = _period_table(number)
    with pytest.raises(DBAPIError) as error, engine.begin() as conn:
        conn.execute(sa.insert(table).values(c_7=value))
    assert sqlstate_of(error.value) == state
    if constraint:
        assert constraint in str(error.value.orig)


def test_pg_month_period_rules(pg_app_engine, clean_pg):
    from datetime import date

    number = _prepare_period(pg_app_engine, "month")
    table = _period_table(number)
    with pg_app_engine.begin() as conn:
        conn.execute(sa.insert(table).values(c_7=date(2026, 3, 1)))
    _insert_fails(pg_app_engine, number, date(2026, 3, 15), "23514", f"ck_ds_{number}_period")
    _insert_fails(pg_app_engine, number, date(2026, 3, 1), "23505", f"ux_ds_{number}_period")
    _insert_fails(pg_app_engine, number, None, "23502")  # NOT NULL
    with pg_app_engine.begin() as conn:
        conn.execute(sa.insert(table).values(c_7=date(2026, 4, 1)))  # 다른 기간은 가능


def test_pg_year_and_day_period_rules(pg_app_engine, clean_pg):
    from datetime import date

    year = _prepare_period(pg_app_engine, "year")
    with pg_app_engine.begin() as conn:
        conn.execute(sa.insert(_period_table(year)).values(c_7=date(2026, 1, 1)))
    _insert_fails(pg_app_engine, year, date(2026, 2, 1), "23514")
    _insert_fails(pg_app_engine, year, date(2026, 1, 1), "23505")
    day = _prepare_period(pg_app_engine, "day")
    with pg_app_engine.begin() as conn:
        for d in (date(2026, 3, 15), date(2026, 3, 16)):
            conn.execute(sa.insert(_period_table(day)).values(c_7=d))
    _insert_fails(pg_app_engine, day, date(2026, 3, 15), "23505")


def test_pg_period_rule_does_not_depend_on_session_time_zone(pg_app_engine, clean_pg):
    """첫날 판정은 timestamp 변환을 거쳐 세션 시간대와 무관하다(06 §3-1)."""
    from datetime import date

    number = _prepare_period(pg_app_engine, "month")
    with pg_app_engine.begin() as conn:
        conn.execute(sa.select(sa.func.set_config("TimeZone", "Pacific/Kiritimati", True)))
        conn.execute(sa.insert(_period_table(number)).values(c_7=date(2026, 3, 1)))
        conn.execute(sa.select(sa.func.set_config("TimeZone", "Etc/GMT+12", True)))
        conn.execute(sa.insert(_period_table(number)).values(c_7=date(2026, 4, 1)))


def test_pg_period_rules_objects_are_named_by_the_rule(pg_app_engine, clean_pg):
    number = _prepare_period(pg_app_engine, "month")
    with pg_app_engine.connect() as conn:
        inspector = sa.inspect(conn)
        indexes = {
            i["name"]: i for i in inspector.get_indexes(f"ds_{number}", schema=DYNAMIC_SCHEMA)
        }
        checks = [
            c["name"]
            for c in inspector.get_check_constraints(f"ds_{number}", schema=DYNAMIC_SCHEMA)
        ]
        assert indexes[f"ux_ds_{number}_period"]["unique"] is True
        assert indexes[f"ux_ds_{number}_period"]["column_names"] == ["c_7"]
        assert checks == [f"ck_ds_{number}_period"]
        assert columns_of(conn, number)["c_7"]["nullable"] is False


def test_pg_drop_period_rules_restores_a_plain_nullable_column(pg_app_engine, clean_pg):
    from datetime import date

    number = _prepare_period(pg_app_engine, "month")
    with pg_app_engine.begin() as conn:
        ddl.drop_period_rules(conn, number, 7)
    with pg_app_engine.connect() as conn:
        inspector = sa.inspect(conn)
        assert inspector.get_check_constraints(f"ds_{number}", schema=DYNAMIC_SCHEMA) == []
        names = [i["name"] for i in inspector.get_indexes(f"ds_{number}", schema=DYNAMIC_SCHEMA)]
        assert f"ux_ds_{number}_period" not in names
        assert columns_of(conn, number)["c_7"]["nullable"] is True
    with pg_app_engine.begin() as conn:  # 이제 비어 있어도, 중복·첫날 아님도 허용
        table = _period_table(number)
        for d in (date(2026, 3, 15), date(2026, 3, 15), None):
            conn.execute(sa.insert(table).values(c_7=d))
    # 다시 걸 수는 없다(이미 중복이 있다): 행 0개일 때만 부른다는 규칙을 DB도 확인해 준다.
    with pytest.raises(DBAPIError), pg_app_engine.begin() as conn:
        ddl.add_period_rules(conn, number, 7, "month")


def test_pg_period_rules_can_be_replaced_with_another_unit(pg_app_engine, clean_pg):
    from datetime import date

    number = _prepare_period(pg_app_engine, "month")
    with pg_app_engine.begin() as conn:
        ddl.drop_period_rules(conn, number, 7)
        ddl.add_period_rules(conn, number, 7, "year")
    _insert_fails(pg_app_engine, number, date(2026, 3, 1), "23514")
    with pg_app_engine.begin() as conn:
        conn.execute(sa.insert(_period_table(number)).values(c_7=date(2026, 1, 1)))


def test_pg_add_period_rules_fails_and_rolls_back_when_rows_have_null(pg_app_engine, clean_pg):
    number = new_number()
    with pg_app_engine.begin() as conn:
        ddl.create_dataset_table(conn, number)
        ddl.add_raw_column(conn, number, 7, "date")
        conn.execute(sa.insert(_period_table(number)).values(row_id=1))  # c_7 = NULL
    with pytest.raises(DBAPIError), pg_app_engine.begin() as conn:
        ddl.add_period_rules(conn, number, 7, "month")
    with pg_app_engine.connect() as conn:  # 부분 적용이 남지 않았다
        assert sa.inspect(conn).get_check_constraints(f"ds_{number}", schema=DYNAMIC_SCHEMA) == []
        assert columns_of(conn, number)["c_7"]["nullable"] is True


def test_pg_bi_app_cannot_create_outside_bi_data(pg_app_engine, clean_pg):
    """`bi_app`은 `public`에 CREATE할 수 없다(06 §4-2). 동적 DDL은 어떤 경우에도 bi_data 안이다."""
    stray = Table("stray_ds_1", MetaData(), Column("a", sa.Integer))
    with pytest.raises(DBAPIError) as error, pg_app_engine.begin() as conn:
        conn.execute(CreateTable(stray))
    assert sqlstate_of(error.value) == "42501"
    with pytest.raises(DBAPIError) as error, pg_app_engine.begin() as conn:
        conn.execute(CreateSchema("evil_schema"))
    assert sqlstate_of(error.value) == "42501"
    # 게이트도 같은 요청을 실행 전에 거부한다.
    with pytest.raises(ddl.DdlNotAllowedError):
        ddl.run_ddl(RecordingConnection(), CreateTable(stray))


def test_pg_startup_check_accepts_everything_the_ddl_module_creates(pg_app_engine, clean_pg):
    """시작 자가 점검의 객체 종류 검사가 새 객체(표, Identity 시퀀스, 인덱스, 제약)를 허용한다."""
    number = _prepare_period(pg_app_engine, "month")
    with pg_app_engine.begin() as conn:
        ddl.add_raw_column(conn, number, 8, "number")
    with pg_app_engine.connect() as conn:
        check_bi_data_objects(conn)
        check_static_tables(conn)


def test_pg_alembic_check_ignores_dynamic_objects(pg_env, pg_app_engine, clean_pg):
    """`ds_*`가 있는 DB에서도 `alembic check`는 성공한다(동적 객체를 삭제 후보로 보지 않는다)."""
    number = _prepare_period(pg_app_engine, "month")
    assert number
    with pytest.MonkeyPatch.context() as mp:
        pg_env.apply(mp)
        command.check(Config(str(BACKEND / "alembic.ini")))
    get_settings.cache_clear()


def test_pg_downgrade_0004_keeps_dynamic_objects_and_upgrade_restores(
    pg_env, pg_app_engine, pg_owner_engine, clean_pg
):
    """0004를 내려도 `bi_data`의 `ds_*`는 남고(06 §6), 다시 올리면 정적 표가 돌아온다."""
    number = _prepare_period(pg_app_engine, "month")
    config = Config(str(BACKEND / "alembic.ini"))
    with pytest.MonkeyPatch.context() as mp:
        pg_env.apply(mp)
        try:
            command.downgrade(config, "0003")
            inspector = sa.inspect(pg_owner_engine)
            assert not inspector.has_table("datasets")
            assert not inspector.has_table("dataset_columns")
            assert inspector.has_table(f"ds_{number}", schema=DYNAMIC_SCHEMA)
        finally:
            command.upgrade(config, "head")
    get_settings.cache_clear()
    inspector = sa.inspect(pg_owner_engine)
    assert inspector.has_table("datasets") and inspector.has_table("dataset_columns")
    assert inspector.has_table(f"ds_{number}", schema=DYNAMIC_SCHEMA)
