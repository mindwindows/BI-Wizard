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
- 뷰(`dv_`·`de_`)는 `create_view`/`drop_view`로만 만든다. 만들기 전에 뷰 정의(SELECT)를 허용
  목록 규칙으로 확인한다(자기 `ds_<번호>` 한 표만 읽음, `text()`·`literal_column` 없음, 허용 목록
  `VIEW_ALLOWED_FUNCTIONS` 밖 SQL 함수 없음, 바인드 값은 숫자·글자·참거짓·날짜뿐이며 글자는 NUL·
  역슬래시·제어·서식 문자가 없어야 한다(formula 렌더러의 1차 방어와 별개인 방어 중복)).
  **서브쿼리는 `REF`의 한 가지 모양만 통과한다**(FU-3, 03b 32-3 안 B): 호출자가 넘긴
  `ReferenceLookup(항목 번호, 기준 날짜 열 번호)`로 만든 기대 모양(`reference_lookup.py`, 읽는 표는
  `public.reference_values` 하나, 항목 번호는 정수 상수, 연도는 자기 `ds_`의 기준 날짜 열에서 뽑은
  값뿐)과 컴파일 결과(정규형)가 정확히 같을 때만 허용하고 그 밖의 서브쿼리(다른 표·다른 열·비상수·
  중첩·UNION·LATERAL·열 식 밖 위치 등)는 모두 거부한다. 목록을 주지 않으면 서브쿼리는 하나도
  허용하지 않는다. 이 모듈은 `bi_data`를 만들 뿐 `public` 표를 만들거나 바꾸지 않는다(읽기 식만).
  상수의 SQL 글자 렌더는 호출한 쪽이 넘기는 `render`(formula의 `render_literal_sql` 접점)만 쓰므로
  이 모듈은 `literal_binds`를 직접 쓰지 않는다(`CreateView`가 내부에서 같은 렌더러로 그린다).
  렌더 글자와 `CreateView`가 그리는 정의의 대조는 **어떤 DB 문장도 실행하기 전에** 한다.
- 완화책 ③(07 §4-3): 뷰를 만든 뒤 같은 트랜잭션에서 (가) 뷰를 `LIMIT 0`으로 읽어 열 이름·개수가
  기대와 같은지, (나) 호출한 쪽이 넘긴 글자 상수 확인 SELECT를 같은 렌더러로 실행해 입력과 같은지
  비교한다. (나)의 `RenderedSelect`는 렌더된 글자가 `SELECT CAST('…' AS TEXT) AS k<n>, …` 모양이고
  값이 입력 상수와 같을 때만 **실행 전에** 통과시킨다(임의 글자를 돌려주는 render 함수는 실행되지
  않는다). 어긋나면 `DdlVerificationError`를 올리고 호출한 쪽이 트랜잭션을 롤백한다.
- 표·열 생성 뒤에는 만든 표·열이 실제로 있는지 다시 읽어 확인한다.
"""

from __future__ import annotations

import datetime
import re
import unicodedata
from collections.abc import Callable
from collections.abc import Sequence as SequenceABC
from decimal import Decimal
from typing import Any

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
    Select,
    Sequence,
    Table,
    Text,
    cast,
    func,
    inspect,
    literal,
    select,
)
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.schema import (
    AddConstraint,
    CreateIndex,
    CreateTable,
    CreateView,
    DropConstraint,
    DropIndex,
    DropView,
    ExecutableDDLElement,
)
from sqlalchemy.sql import visitors
from sqlalchemy.sql.base import Executable
from sqlalchemy.sql.elements import (
    BindParameter,
    Cast,
    ClauseElement,
    ColumnClause,
    Extract,
    Label,
    TextClause,
)
from sqlalchemy.sql.functions import FunctionElement
from sqlalchemy.sql.operators import custom_op
from sqlalchemy.sql.selectable import ScalarSelect
from sqlalchemy.types import TypeEngine

from app.core.db_errors import sqlstate
from app.db_metadata import COLUMN_TYPES, DATE_UNITS
from app.ddl.names import (
    DYNAMIC_SCHEMA,
    DdlExecutionError,
    DdlNameError,
    DdlNotAllowedError,
    DdlVerificationError,
    check_dynamic_name,
    column_name,
    dataset_table_name,
    error_view_name,
    period_check_name,
    period_index_name,
    view_name,
)
from app.ddl.reference_lookup import ReferenceLookup, expected_lookup_key, lookup_key

# 원본 열 형 -> PostgreSQL 형(06 §3-1). choice는 선택 목록 값 자체를 text로 저장한다.
_COLUMN_SQL_TYPES: dict[str, type[TypeEngine]] = {
    "text": Text,
    "number": Numeric,
    "date": Date,
    "boolean": Boolean,
    "choice": Text,
}
assert set(_COLUMN_SQL_TYPES) == set(COLUMN_TYPES)  # noqa: S101 - 형 목록이 어긋나면 import에서 실패

# 실행을 허용하는 SQLAlchemy DDL 구문. 뷰는 `create_view`/`drop_view`가 정의를 확인한 뒤에만
# 실행한다.
ALLOWED_DDL_ELEMENTS = (
    CreateTable,
    CreateIndex,
    DropIndex,
    AddConstraint,
    DropConstraint,
    CreateView,
    DropView,
)

# 뷰 종류 -> (이름 규칙 함수). `dv`는 값 뷰, `de`는 오류 판정 보조 뷰(07 §3-1).
VIEW_KINDS = {"dv": view_name, "de": error_view_name}
# 뷰 정의 안 바인드 값으로 허용하는 파이썬 형(상수는 모두 formula의 리터럴 렌더러가 만든다).
_ALLOWED_BIND_TYPES = (Decimal, str, bool, int, datetime.date)

Renderer = Callable[[ClauseElement, Dialect], str]

# 뷰 정의에서 부를 수 있는 SQL 함수의 허용 목록(소문자). `pg_sleep`·시스템 함수·사용자 함수는
# 목록 밖이라 뷰 게이트가 실행 전에 거부한다(reviewer R1). 변환기·사전이 새 SQL 함수를 쓰려면
# 검토한 뒤 여기에 더한다.
VIEW_ALLOWED_FUNCTIONS = frozenset(
    {
        "abs", "btrim", "ceil", "char_length", "coalesce", "date_part", "extract", "floor",
        "greatest", "least", "left", "length", "lower", "make_date", "mod", "nullif",
        "regexp_replace", "right", "round", "sign", "trunc",
    }
)  # fmt: skip

# `EXTRACT(<field> FROM …)`의 field는 SQL 글자 그대로 렌더되므로 고정 집합만 통과시킨다(formula는
# year·month만 쓴다).
VIEW_ALLOWED_EXTRACT_FIELDS = frozenset({"year", "month", "day"})
# 숫자 상수의 자릿수 한도(formula의 `MAX_NUMBER_DIGITS`와 같은 값을 일부러 따로 둔 방어 중복).
_MAX_NUMBER_DIGITS = 38
# `str(Decimal)`이 만드는 형태: 평범한 숫자 또는 지수 표기(`1E+30`, `1E-8`; 10의 거듭제곱 상수가
# 이렇게 렌더된다).
_PLAIN_DECIMAL = re.compile(r"-?\d+(\.\d+)?(E[+-]\d+)?")

# 글자 상수에서 게이트가 한 번 더 거르는 문자 범주(NUL은 Cc). formula 렌더러의 1차 방어와 같은
# 규칙을 일부러 따로 둔 방어 중복이다(07 §4-2, reviewer M2).
_REJECTED_TEXT_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Zl", "Zp"})


# --- 허용 목록 게이트 ----


def _text_bind_problem(value: str) -> str | None:
    """글자 바인드 값에 NUL·역슬래시·제어·서식·줄/문단 구분 문자가 있으면 이유(없으면 None)."""
    if "\\" in value:
        return "역슬래시"
    for char in value:
        if unicodedata.category(char) in _REJECTED_TEXT_CATEGORIES:
            return "제어·서식 문자"
    return None


def _number_bind_problem(value: Decimal | int) -> bool:
    """숫자 바인드가 렌더돼도 안전한 값인지(유한, 38자리 이내, 알려진 숫자 모양)."""
    if isinstance(value, int):
        return abs(value) >= 10**_MAX_NUMBER_DIGITS
    if not value.is_finite() or not _PLAIN_DECIMAL.fullmatch(str(value)):
        return True
    _sign, digits, exponent = value.as_tuple()
    if not isinstance(exponent, int) or exponent < -_MAX_NUMBER_DIGITS:
        return True
    return len(digits) > _MAX_NUMBER_DIGITS or len(digits) + exponent > _MAX_NUMBER_DIGITS


def _check_bind_value(value: object) -> None:
    if value is not None and not isinstance(value, _ALLOWED_BIND_TYPES):
        raise DdlNotAllowedError("뷰 정의의 상수는 숫자·글자·참거짓·날짜여야 한다.")
    if isinstance(value, str) and _text_bind_problem(value) is not None:
        raise DdlNotAllowedError("뷰 정의의 글자 상수에 쓸 수 없는 문자가 있다.")
    if (
        isinstance(value, Decimal | int)
        and not isinstance(value, bool)
        and _number_bind_problem(value)
    ):
        raise DdlNotAllowedError("뷰 정의의 숫자 상수가 허용 범위·모양 밖이다.")


def _check_node_parts(node: object) -> None:
    """렌더러가 값을 그대로 글자로 옮기는 SQLAlchemy 부품을 거른다(뷰 정의·확인 질의 공통).

    - 사용자 정의 연산자(`col.op("…")`): 연산자 글자가 그대로 렌더된다.
    - `EXTRACT`의 field: 고정 집합만 허용한다.
    - callable 바인드: `.value`는 None인데 렌더는 호출 결과(`effective_value`)를 쓴다.
    """
    for attribute in ("operator", "modifier"):
        if isinstance(getattr(node, attribute, None), custom_op):
            raise DdlNotAllowedError("뷰 정의에 사용자 정의 연산자를 쓸 수 없다.")
    if isinstance(node, Extract) and node.field not in VIEW_ALLOWED_EXTRACT_FIELDS:
        raise DdlNotAllowedError("뷰 정의의 EXTRACT 단위가 허용 목록 밖이다.")
    if isinstance(node, BindParameter) and node.callable is not None:
        raise DdlNotAllowedError("뷰 정의에 호출형(callable) 상수를 쓸 수 없다.")


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


def _check_reference_subqueries(
    selectable: Select, dataset_id: int, references: SequenceABC[ReferenceLookup]
) -> set[int]:
    """뷰 정의 안의 서브쿼리를 확인한다. 통과한 서브쿼리 `Select`의 `id` 집합을 돌려준다.

    허용하는 것은 **`REF`의 한 가지 모양**(`reference_lookup.py`)과 정규형(컴파일 글자·상수 값)이
    정확히 같고, 호출자가 넘긴 `(항목 번호, 기준 날짜 열 번호)` 목록에 있는 서브쿼리뿐이다. 그 밖의
    서브쿼리(다른 표·다른 열·비상수 항목 번호·다른 연도 식·중첩·JOIN·`UNION`·`LATERAL`·파생 표·
    CTE·함수 호출 등)는 모양이 달라 전부 거부된다. 서브쿼리는 바깥 SELECT의 **열 식 안**에서만 쓸 수
    있다(WHERE·ORDER BY·FROM 등 다른 자리는 거부).
    """
    allowed = {expected_lookup_key(dataset_id, lookup) for lookup in references}
    in_columns = {
        id(node) for column in selectable.selected_columns for node in visitors.iterate(column)
    }
    matched: set[int] = set()
    for node in visitors.iterate(selectable):
        if not isinstance(node, ScalarSelect):
            continue
        if id(node) not in in_columns:
            raise DdlNotAllowedError("뷰 정의의 서브쿼리는 열 식 안에서만 쓸 수 있다.")
        inner = node.element
        if not isinstance(inner, Select) or lookup_key(inner) not in allowed:
            raise DdlNotAllowedError("뷰 정의에 허용된 기준값 조회 모양이 아닌 서브쿼리가 있다.")
        matched.add(id(inner))
    return matched


def _check_view_select(
    selectable: object, dataset_id: int, references: SequenceABC[ReferenceLookup] = ()
) -> list[str]:
    """뷰 정의 SELECT를 확인하고 출력 열 이름 목록을 돌려준다(허용 목록 밖이면 거부).

    `references`는 이 뷰의 `REF` 서브쿼리가 쓸 수 있는 (항목 번호, 기준 날짜 열 번호) 목록이다.
    비어 있으면 서브쿼리는 하나도 허용하지 않는다.
    """
    if not isinstance(selectable, Select):
        raise DdlNotAllowedError("뷰 정의는 SELECT여야 한다.")
    matched = _check_reference_subqueries(selectable, dataset_id, references)
    for node in visitors.iterate(selectable):
        _check_node_parts(node)
        if isinstance(node, Select):
            if node is not selectable and id(node) not in matched:
                raise DdlNotAllowedError("뷰 정의에 서브쿼리를 쓸 수 없다.")
        elif isinstance(node, TextClause):
            raise DdlNotAllowedError("뷰 정의에 text()를 쓸 수 없다.")
        elif isinstance(node, ColumnClause) and node.is_literal:
            raise DdlNotAllowedError("뷰 정의에 literal_column을 쓸 수 없다.")
        elif isinstance(node, FunctionElement):
            if node.packagenames or str(node.name).lower() not in VIEW_ALLOWED_FUNCTIONS:
                raise DdlNotAllowedError("뷰 정의에 허용 목록 밖 SQL 함수를 쓸 수 없다.")
        elif isinstance(node, BindParameter):
            _check_bind_value(node.effective_value)
    froms = selectable.get_final_froms()
    if len(froms) != 1:
        raise DdlNotAllowedError("뷰는 자기 원본 표 하나만 읽는다.")
    source = froms[0]
    expected_table = dataset_table_name(dataset_id)
    if getattr(source, "schema", None) != DYNAMIC_SCHEMA or getattr(source, "name", "") != (
        expected_table
    ):
        raise DdlNotAllowedError("뷰는 자기 원본 표(bi_data.ds_<번호>)만 읽는다.")
    names = [str(c.name) for c in selectable.selected_columns]
    if len(set(names)) != len(names):
        raise DdlNameError("뷰 출력 열 이름이 겹친다.")
    for name in names:
        check_dynamic_name(name, "column")
    return names


def _check_view_target(view: Table, kind: str | None = None) -> None:
    if view.schema != DYNAMIC_SCHEMA:
        raise DdlNotAllowedError("동적 DDL은 bi_data schema에서만 실행한다.")
    check_dynamic_name(view.name, "view")
    if kind is not None and view.name[: len(kind)] != kind:
        raise DdlNameError("뷰 종류와 이름이 맞지 않는다.")


def _check_element(
    element: ExecutableDDLElement, references: SequenceABC[ReferenceLookup] = ()
) -> None:
    if not isinstance(element, ALLOWED_DDL_ELEMENTS):
        raise DdlNotAllowedError(f"허용되지 않는 DDL 구문: {type(element).__name__}")
    if isinstance(element, CreateView):
        if element.temporary or element.materialized:
            raise DdlNotAllowedError("임시·구체화 뷰는 만들지 않는다.")
        _check_view_target(element.table)
        _check_view_select(element.selectable, int(element.table.name.split("_", 1)[1]), references)
        return
    if isinstance(element, DropView):
        if element.materialized:
            raise DdlNotAllowedError("구체화 뷰는 다루지 않는다.")
        _check_view_target(element.element)
        return
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


def run_ddl(
    conn: Connection,
    element: ExecutableDDLElement,
    *,
    references: SequenceABC[ReferenceLookup] = (),
) -> None:
    """허용 목록을 확인하고 DDL 구문을 실행한다. 규칙 밖이면 실행 전에 거부한다.

    `references`는 `CreateView`의 `REF` 서브쿼리 허용 목록이다(그 밖의 구문에는 쓰이지 않는다).
    """
    _check_element(element, references)
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


# --- 뷰 (07 §8, 06 §3-4) ----


_ECHO_LABEL = re.compile(r"k\d+")
# 렌더된 확인 질의의 허용 모양 한 칸: `CAST('…' AS TEXT) AS k<n>` (따옴표는 `''`로만 들어간다)
_ECHO_ITEM = re.compile(r"CAST\('((?:[^']|'')*)' AS TEXT\) AS (k\d+)")
_ECHO_PREFIX = "SELECT "


def _echo_columns(statement: Select) -> list[tuple[str, str]]:
    """확인 질의의 (열 이름, 글자 상수) 목록. 열 모양은 `CAST(글자 상수 AS TEXT) AS k<n>`."""
    columns: list[tuple[str, str]] = []
    for column in statement.selected_columns:
        cast_ = getattr(column, "element", None)
        bind = getattr(cast_, "clause", None)
        if (
            not isinstance(column, Label)
            or not isinstance(cast_, Cast)
            or not isinstance(cast_.type, Text)
            or not isinstance(bind, BindParameter)
            or not isinstance(bind.value, str)
            or not _ECHO_LABEL.fullmatch(str(column.name))
        ):
            raise DdlNotAllowedError("확인 질의의 열은 CAST(글자 상수 AS TEXT) AS k<n>이어야 한다.")
        columns.append((str(column.name), bind.value))
    return columns


def _check_echo_select(statement: object) -> Select:
    """완화책 ③ 확인 질의 모양 확인: FROM 없이 `CAST(글자 상수 AS TEXT)` 열만 있는 SELECT."""
    if not isinstance(statement, Select) or statement.get_final_froms():
        raise DdlNotAllowedError("확인 질의는 FROM 없는 SELECT여야 한다.")
    for node in visitors.iterate(statement):
        _check_node_parts(node)
        if isinstance(node, Select | Label | Cast):
            continue
        if isinstance(node, BindParameter) and isinstance(node.effective_value, str):
            _check_bind_value(node.effective_value)
            continue
        raise DdlNotAllowedError("확인 질의는 글자 상수만 담을 수 있다.")
    if not _echo_columns(statement):
        raise DdlNotAllowedError("확인 질의에 열이 없다.")
    return statement


def _decode_echo_literal(body: str, *, backslash_escapes: bool) -> str:
    """렌더된 글자 상수 한 칸의 안쪽을 값으로 되돌린다(따옴표 두 개는 하나로)."""
    out: list[str] = []
    i = 0
    while i < len(body):
        pair = body[i : i + 2]
        if pair == "''":
            out.append("'")
            i += 2
        elif backslash_escapes and pair == "\\\\":
            out.append("\\")
            i += 2
        elif backslash_escapes and body[i] == "\\":
            raise DdlNotAllowedError("렌더된 확인 질의에 짝 없는 역슬래시가 있다.")
        else:
            out.append(body[i])
            i += 1
    return "".join(out)


def check_rendered_echo(rendered: str, statement: Select, dialect: Dialect) -> str:
    """렌더된 확인 질의가 허용된 모양이고 값이 입력 상수와 같은지 **실행 전에** 확인한다.

    허용 모양은 FROM 없는 `SELECT CAST('…' AS TEXT) AS k0, CAST('…' AS TEXT) AS k1, …` 뿐이며,
    각 칸을 값으로 되돌린 것이 입력 상수와 열 순서까지 같아야 한다. 아니면 `DdlNotAllowedError`로
    거부하고 DB에는 아무것도 보내지 않는다.
    """
    expected = _echo_columns(statement)
    if not rendered.startswith(_ECHO_PREFIX):
        raise DdlNotAllowedError("렌더된 확인 질의가 허용된 모양이 아니다.")
    escapes = bool(getattr(dialect, "_backslash_escapes", False))
    position = len(_ECHO_PREFIX)
    actual: list[tuple[str, str]] = []
    while True:
        match = _ECHO_ITEM.match(rendered, position)
        if match is None:
            raise DdlNotAllowedError("렌더된 확인 질의가 허용된 모양이 아니다.")
        value = _decode_echo_literal(match.group(1), backslash_escapes=escapes)
        actual.append((match.group(2), value))
        position = match.end()
        if position == len(rendered):
            break
        if not rendered.startswith(", ", position):
            raise DdlNotAllowedError("렌더된 확인 질의가 허용된 모양이 아니다.")
        position += 2
    if actual != expected:
        raise DdlNotAllowedError("렌더된 확인 질의의 상수가 입력과 다르다.")
    return rendered


class RenderedSelect(Executable, ClauseElement):
    """SELECT를 호출한 쪽의 렌더러(`render_literal_sql`)로 그린 글자로 실행하는 확인 질의.

    완화책 ③의 확인 질의(글자 상수만 담은 SELECT)를 뷰 정의와 **같은 렌더러**로 실행해, 렌더된
    글자가 입력과 같은지 비교한다. 이 모듈은 상수를 직접 렌더하지 않고 넘겨받은 렌더러만 부른다.
    렌더러가 돌려준 글자는 실행 전에 `check_rendered_echo`로 모양과 값을 확인하므로 렌더 함수가
    임의 SQL을 돌려줘도 실행되지 않는다. `dialect`를 주면 그 방언으로 렌더·확인하고, 없으면 실행하는
    연결의 방언을 쓴다.
    """

    inherit_cache = False
    is_dml = False

    def __init__(
        self, selectable: Select, render: Renderer, dialect: Dialect | None = None
    ) -> None:
        self.selectable = _check_echo_select(selectable)
        self.render = render
        self.dialect = dialect


@compiles(RenderedSelect)
def _compile_rendered_select(element: RenderedSelect, compiler: Any, **_kw: Any) -> str:
    dialect = element.dialect or compiler.dialect
    rendered = element.render(element.selectable, dialect)
    return check_rendered_echo(rendered, element.selectable, dialect)


def _execute_view_statement(
    conn: Connection, statement: Any, references: SequenceABC[ReferenceLookup] = ()
) -> Any:
    """뷰 정의·확인 질의를 실행한다. 문장에 사용자 상수가 들어 있으므로 DB 오류는 SQL 없이 올린다.

    잠금 대기 초과·교착(재시도 가능)과 열 형 변경 거부(42P16, 지우고 다시 만들기로 처리)는
    호출한 쪽이 원래 오류로 판단해야 하므로 그대로 올린다. 그 오류는 호출한 쪽이 업무 오류로
    바꾸거나 SQLSTATE만 기록한다.
    """
    try:
        if isinstance(statement, ExecutableDDLElement):
            run_ddl(conn, statement, references=references)
            return None
        return conn.execute(statement)
    except DBAPIError as error:
        code = sqlstate(error)
        if code in _PASS_THROUGH_SQLSTATES:
            raise
        raise DdlExecutionError(code) from None


_PASS_THROUGH_SQLSTATES = frozenset({"55P03", "40P01", "42P16"})


def view_column_names(conn: Connection, kind: str, dataset_id: int) -> list[str] | None:
    """뷰의 출력 열 이름(순서대로). 뷰가 없으면 None."""
    name = check_dynamic_name(VIEW_KINDS[kind](dataset_id), "view")
    inspector = inspect(conn)  # 새 Inspector라 같은 트랜잭션의 미커밋 DDL도 보인다.
    if name not in inspector.get_view_names(schema=DYNAMIC_SCHEMA):
        return None
    return [c["name"] for c in inspector.get_columns(name, schema=DYNAMIC_SCHEMA)]


def _view_table(kind: str, dataset_id: int, names: SequenceABC[str] = ()) -> Table:
    view = Table(
        check_dynamic_name(VIEW_KINDS[kind](dataset_id), "view"),
        MetaData(),
        *[Column(check_dynamic_name(n, "column"), Text) for n in names],
        schema=DYNAMIC_SCHEMA,
    )
    return view


def drop_view(conn: Connection, kind: str, dataset_id: int) -> None:
    """뷰를 지운다(`CASCADE` 없음: 이 뷰에 의존하는 객체가 있으면 실패한다)."""
    _execute_view_statement(conn, DropView(_view_table(kind, dataset_id)))


def _create_view_statement(
    kind: str, dataset_id: int, selectable: Select, *, or_replace: bool
) -> CreateView:
    name = check_dynamic_name(VIEW_KINDS[kind](dataset_id), "view")
    return CreateView(selectable, name, schema=DYNAMIC_SCHEMA, or_replace=or_replace)


def create_view(
    conn: Connection,
    kind: str,
    dataset_id: int,
    selectable: Select,
    *,
    render: Renderer,
    echo: SequenceABC[tuple[Select, tuple[Any, ...]]] = (),
    references: SequenceABC[ReferenceLookup] = (),
) -> bool:
    """`dv_<번호>`/`de_<번호>`를 만들거나 바꾼다. 방식을 바꿨으면(지우고 다시 만듦) True.

    `references`: 이 뷰의 `REF` 서브쿼리가 쓸 수 있는 (항목 번호, 기준 날짜 열 번호) 목록(없으면
    서브쿼리 불허). 서브쿼리는 `reference_lookup.py`의 한 가지 모양과 정규형이 같아야 한다.

    - 뷰가 없으면 `CREATE VIEW`. 있고 기존 열이 새 열의 앞부분(이름·순서 같음)이면
      `CREATE OR REPLACE VIEW`(끝에 열 추가만 가능, X-11), 열 제거·순서·이름·형 변경이면
      `DROP VIEW` + `CREATE VIEW`(의존 객체가 있으면 실패하고, `CASCADE`는 쓰지 않는다).
    - 정의 SELECT는 먼저 `render`로 렌더해 상수 값을 검증한다(규칙 위반이면 렌더러의 예외가
      올라간다).
    - 만든 뒤 완화책 ③: 열 이름·개수와 `echo`(확인 SELECT, 기대 값)를 확인한다. 어긋나면
      `DdlVerificationError`이며 호출한 쪽이 롤백한다.
    """
    if kind not in VIEW_KINDS:
        raise DdlNotAllowedError(f"허용되지 않는 뷰 종류: {kind!r}")
    expected = _check_view_select(selectable, dataset_id, references)
    dialect = conn.dialect
    rendered = render(selectable, dialect)  # 상수 검증 + 같은 렌더러로 그린 정의 글자
    # 렌더러가 그린 정의 글자가 실제 `CREATE VIEW`에 그대로 들어가는지 **실행 전에** 대조한다.
    for or_replace in (False, True):
        statement = _create_view_statement(kind, dataset_id, selectable, or_replace=or_replace)
        compiled = str(statement.compile(dialect=dialect))
        # 머리말(`CREATE [OR REPLACE] VIEW <schema>.<이름>`)은 검증된 식별자뿐이라 ` AS `가 없다.
        # 그래서 첫 ` AS `가 정의의 시작이고, 그 뒤 전부가 렌더 글자와 **정확히** 같아야 한다.
        head, separator, definition = compiled.partition(" AS ")
        if not head or not separator or definition != rendered:
            raise DdlVerificationError("뷰 정의의 상수 렌더가 검증한 글자와 다르다.")
    existing = view_column_names(conn, kind, dataset_id)
    rebuilt = False
    if existing is None:
        _execute_view_statement(
            conn,
            _create_view_statement(kind, dataset_id, selectable, or_replace=False),
            references,
        )
    elif expected[: len(existing)] == existing:
        try:
            with conn.begin_nested():
                _execute_view_statement(
                    conn,
                    _create_view_statement(kind, dataset_id, selectable, or_replace=True),
                    references,
                )
        except DBAPIError as error:
            if sqlstate(error) != _INVALID_TABLE_DEFINITION:
                raise
            # 열 형이 바뀌었다(예: 계산 열의 결과 형). 지우고 다시 만든다.
            drop_view(conn, kind, dataset_id)
            _execute_view_statement(
                conn,
                _create_view_statement(kind, dataset_id, selectable, or_replace=False),
                references,
            )
            rebuilt = True
    else:
        drop_view(conn, kind, dataset_id)
        _execute_view_statement(
            conn,
            _create_view_statement(kind, dataset_id, selectable, or_replace=False),
            references,
        )
        rebuilt = True
    _verify_view(conn, kind, dataset_id, expected, render, echo)
    return rebuilt


_INVALID_TABLE_DEFINITION = "42P16"


def _verify_view(
    conn: Connection,
    kind: str,
    dataset_id: int,
    expected: list[str],
    render: Renderer,
    echo: SequenceABC[tuple[Select, tuple[Any, ...]]],
) -> None:
    """완화책 ③ (가) 뷰를 LIMIT 0으로 읽어 열 이름·개수 확인 (나) 글자 상수 확인 SELECT."""
    actual = view_column_names(conn, kind, dataset_id)  # 카탈로그가 말하는 열(더 있어도 잡는다)
    if actual != expected:
        raise DdlVerificationError("만든 뷰의 열이 기대와 다르다.")
    view = _view_table(kind, dataset_id, expected)
    result = _execute_view_statement(conn, select(*view.c).limit(0))
    if list(result.keys()) != expected:
        raise DdlVerificationError("만든 뷰에서 읽은 열이 기대와 다르다.")
    for statement, values in echo:
        row = _execute_view_statement(conn, RenderedSelect(statement, render)).one()
        if tuple(row) != tuple(values):
            raise DdlVerificationError("뷰 정의의 글자 상수를 다시 읽은 값이 입력과 다르다.")
