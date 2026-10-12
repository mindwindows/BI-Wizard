"""런타임 동적 DDL 실행: `bi_data`의 `ds_<번호>` 원본 표(04 §2-1 ddl, 06 §3, `bi-review` 7-4).

규칙(이 모듈이 지킨다):
- 런타임 DDL은 **이 모듈에만** 있다. `bi_app` 계정의 연결로만 실행하며(호출한 쪽이 연결을 준다)
  피해는 `bi_data` schema로 한정된다.
- SQLAlchemy 내장 DDL 구문(`CreateTable`·`CreateIndex`·`DropIndex`·`AddConstraint`·
  `DropConstraint`)과 Alembic `Operations`(열 추가, NULL 허용 변경)만 쓴다. `text()`·
  `exec_driver_sql`·문자열 조립은 없다(AST 시험이 확인한다).
- 객체 종류 허용 목록은 표·뷰·인덱스·제약이다. 함수·시퀀스·타입·권한 부여는 만들지 않는다. 표에 딸려
  만들어지는 `row_id`의 Identity 시퀀스만 예외다(AP-10). `run_ddl`이 구문 종류·schema·이름을
  실행 전에 확인하고 규칙 밖이면 `DdlNotAllowedError`/`DdlNameError`로 거부한다.
- 이름은 번호 기반 규칙 함수(`names.py`)로만 만든다. 사용자 글자는 식별자에 쓰지 않는다.
- 트랜잭션은 호출한 쪽이 정한다(등록 + `ds_` 생성은 한 트랜잭션, 06 §3-5). 실패하면 호출한 쪽이
  롤백해 등록 행까지 되돌린다. 이 모듈은 커밋하지 않는다.
- 기간 규칙(기준 날짜 열): `NOT NULL` + CHECK(기간 첫날) + 유일 인덱스. CHECK 식의 단위 글자는 고정
  집합(`day`·`month`·`year`)에서만 온다.
- 생성 뒤 재읽기 비교(글자 상수가 들어가는 `dv_` 뷰의 완화책 ③)는 1d 몫이다. 여기서는 만든 표·열이
  실제로 있는지만 다시 읽어 확인한다.
"""

from __future__ import annotations

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Connection,
    Date,
    DateTime,
    Identity,
    Index,
    MetaData,
    Numeric,
    PrimaryKeyConstraint,
    Sequence,
    Table,
    Text,
    cast,
    func,
    inspect,
    literal,
)
from sqlalchemy.schema import (
    AddConstraint,
    CreateIndex,
    CreateTable,
    DropConstraint,
    DropIndex,
    ExecutableDDLElement,
)
from sqlalchemy.types import TypeEngine

from app.db_metadata import COLUMN_TYPES, DATE_UNITS
from app.ddl.names import (
    DYNAMIC_SCHEMA,
    DdlNotAllowedError,
    DdlVerificationError,
    check_dynamic_name,
    column_name,
    dataset_table_name,
    period_check_name,
    period_index_name,
)

# 원본 열 형 -> PostgreSQL 형(06 §3-1). choice는 선택 목록 값 자체를 text로 저장한다.
_COLUMN_SQL_TYPES: dict[str, type[TypeEngine]] = {
    "text": Text,
    "number": Numeric,
    "date": Date,
    "boolean": Boolean,
    "choice": Text,
}
assert set(_COLUMN_SQL_TYPES) == set(COLUMN_TYPES)  # noqa: S101 - 형 목록이 어긋나면 import에서 실패

# 실행을 허용하는 SQLAlchemy DDL 구문. 뷰(`CreateView`)는 1d에서 formula 단위와 함께 더한다.
ALLOWED_DDL_ELEMENTS = (CreateTable, CreateIndex, DropIndex, AddConstraint, DropConstraint)


# --- 허용 목록 게이트 ----


def _check_table(table: Table) -> None:
    if table.schema != DYNAMIC_SCHEMA:
        raise DdlNotAllowedError("동적 DDL은 bi_data schema에서만 실행한다.")
    check_dynamic_name(table.name, "table")
    for col in table.columns:
        check_dynamic_name(col.name, "column")
        # 표에 딸려 만들어지는 `row_id`의 Identity(AP-10) 외의 시퀀스·서버 기본값은 만들지 않는다.
        if col.computed is not None:
            raise DdlNotAllowedError("계산(생성) 열은 만들지 않는다.")
        if isinstance(col.default, Sequence):
            raise DdlNotAllowedError("독립 시퀀스는 만들지 않는다.")
        if col.server_default is not None and not (
            isinstance(col.server_default, Identity) and col.name == "row_id"
        ):
            raise DdlNotAllowedError("서버 기본값은 만들지 않는다(row_id의 Identity만 예외).")
    for constraint in table.constraints:
        # 표를 만들 때 함께 만들 수 있는 제약은 기본키와 이름 규칙에 맞는 CHECK뿐이다. 외래키·유일
        # 제약은 허용 목록 밖이다(유일성은 번호 규칙 인덱스 `ux_ds_<번호>_period`가 맡는다).
        if not isinstance(constraint, PrimaryKeyConstraint | CheckConstraint):
            raise DdlNotAllowedError("표 생성에는 기본키와 CHECK 제약만 허용한다.")
        if constraint.name is not None:
            check_dynamic_name(constraint.name)


def _check_element(element: ExecutableDDLElement) -> None:
    if not isinstance(element, ALLOWED_DDL_ELEMENTS):
        raise DdlNotAllowedError(f"허용되지 않는 DDL 구문: {type(element).__name__}")
    target = element.element  # type: ignore[attr-defined]
    if isinstance(element, CreateTable):
        _check_table(target)
        return
    table = target.table
    if table is None:
        raise DdlNotAllowedError("대상 표가 없는 DDL은 실행하지 않는다.")
    if table.schema != DYNAMIC_SCHEMA:
        raise DdlNotAllowedError("동적 DDL은 bi_data schema에서만 실행한다.")
    check_dynamic_name(table.name, "table")
    if isinstance(element, CreateIndex | DropIndex):
        check_dynamic_name(target.name, "index")
    else:
        if not isinstance(target, CheckConstraint):
            raise DdlNotAllowedError("제약은 CHECK만 추가·삭제한다.")
        check_dynamic_name(target.name, "constraint")


def run_ddl(conn: Connection, element: ExecutableDDLElement) -> None:
    """허용 목록을 확인하고 DDL 구문을 실행한다. 규칙 밖이면 실행 전에 거부한다."""
    _check_element(element)
    conn.execute(element)


# --- 정의 만들기 ----


def _sql_type(column_type: str) -> TypeEngine:
    factory = _COLUMN_SQL_TYPES.get(column_type)
    if factory is None:
        raise DdlNotAllowedError(f"허용되지 않는 열 형: {column_type!r}")
    return factory()


def _described_table(dataset_id: int, *columns: Column) -> Table:
    """실행할 DDL이 가리킬 표 설명(생성하지 않는다)."""
    return Table(
        dataset_table_name(dataset_id),
        MetaData(),
        Column("row_id", BigInteger, primary_key=True),
        *columns,
        schema=DYNAMIC_SCHEMA,
    )


def _existing_columns(conn: Connection, dataset_id: int) -> dict[str, str]:
    inspector = inspect(conn)  # 새 Inspector라 같은 트랜잭션의 미커밋 DDL도 보인다.
    return {
        c["name"]: str(c["type"]).lower()
        for c in inspector.get_columns(dataset_table_name(dataset_id), schema=DYNAMIC_SCHEMA)
    }


def create_dataset_table(conn: Connection, dataset_id: int) -> None:
    """원본 표 `ds_<번호>`를 만든다: `row_id`(bigint identity, PK)만 있다. 열은 `add_raw_column`."""
    table = Table(
        dataset_table_name(dataset_id),
        MetaData(),
        Column("row_id", BigInteger, Identity(always=False), primary_key=True),
        schema=DYNAMIC_SCHEMA,
    )
    run_ddl(conn, CreateTable(table))
    if "row_id" not in _existing_columns(conn, dataset_id):
        raise DdlVerificationError("만든 원본 표에서 row_id를 다시 읽지 못했다.")


def add_raw_column(conn: Connection, dataset_id: int, column_id: int, column_type: str) -> None:
    """원본 표에 열 `c_<번호>`를 더한다(NULL 허용: 빈 칸이 미입력)."""
    name = check_dynamic_name(column_name(column_id), "column")
    table_name = check_dynamic_name(dataset_table_name(dataset_id), "table")
    sql_type = _sql_type(column_type)
    operations = Operations(MigrationContext.configure(conn))
    operations.add_column(table_name, Column(name, sql_type, nullable=True), schema=DYNAMIC_SCHEMA)
    if name not in _existing_columns(conn, dataset_id):
        raise DdlVerificationError("추가한 열을 다시 읽지 못했다.")


def _period_check_expression(column: Column, date_unit: str):
    if date_unit not in DATE_UNITS:
        raise DdlNotAllowedError(f"허용되지 않는 날짜 단위: {date_unit!r}")
    # `date` 열이 기간 첫날인지: timestamp 변환을 거쳐 세션 시간대에 의존하지 않는다(06 §3-1).
    truncated = func.date_trunc(literal(date_unit, Text), cast(column, DateTime))
    return cast(truncated, Date) == column


def add_period_rules(conn: Connection, dataset_id: int, column_id: int, date_unit: str) -> None:
    """기준 날짜 열 규칙을 건다: `NOT NULL` + 기간 첫날 CHECK + 기간 유일 인덱스(06 §3-1).

    호출한 쪽이 행이 0개임을 확인했다(`DATASET_HAS_ROWS`). 열은 이미 있는 `date` 원본 열이다.
    """
    name = check_dynamic_name(column_name(column_id), "column")
    column = Column(name, Date)
    table = _described_table(dataset_id, column)
    check_dynamic_name(table.name, "table")
    check = CheckConstraint(
        _period_check_expression(table.c[name], date_unit),
        name=check_dynamic_name(period_check_name(dataset_id), "constraint"),
    )
    table.append_constraint(check)
    operations = Operations(MigrationContext.configure(conn))
    operations.alter_column(
        table.name, name, existing_type=Date(), nullable=False, schema=DYNAMIC_SCHEMA
    )
    run_ddl(conn, AddConstraint(check))
    index = Index(
        check_dynamic_name(period_index_name(dataset_id), "index"), table.c[name], unique=True
    )
    run_ddl(conn, CreateIndex(index))


def drop_period_rules(conn: Connection, dataset_id: int, column_id: int) -> None:
    """`add_period_rules`가 건 규칙을 풀고 열을 다시 NULL 허용으로 되돌린다."""
    name = check_dynamic_name(column_name(column_id), "column")
    column = Column(name, Date)
    table = _described_table(dataset_id, column)
    check_dynamic_name(table.name, "table")
    check = CheckConstraint(
        column.is_not(None), name=check_dynamic_name(period_check_name(dataset_id), "constraint")
    )
    table.append_constraint(check)
    index = Index(
        check_dynamic_name(period_index_name(dataset_id), "index"), table.c[name], unique=True
    )
    run_ddl(conn, DropIndex(index))
    run_ddl(conn, DropConstraint(check))
    operations = Operations(MigrationContext.configure(conn))
    operations.alter_column(
        table.name, name, existing_type=Date(), nullable=True, schema=DYNAMIC_SCHEMA
    )
