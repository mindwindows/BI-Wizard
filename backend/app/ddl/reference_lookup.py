"""기준값 조회 서브쿼리의 **한 가지 모양**(06 §3-4 `REF` 서브쿼리, 07 §3-2, 03b 32-3 안 B).

`REF("이름")`을 쓰는 계산 열의 뷰 식은 상관 스칼라 서브쿼리 하나를 품는다.

    (SELECT rv.number_value FROM public.reference_values AS rv
      WHERE rv.item_id = CAST(<정수 상수> AS INTEGER)
        AND rv.year = CAST(EXTRACT(year FROM bi_data.ds_<번호>.c_<기준열>) AS INTEGER))

이 모양을 만드는 함수(`reference_value_subquery`)는 **변환기(formula)와 뷰 게이트
(`dynamic.py`)가 같이
쓴다**: 변환기는 상수 렌더러가 만든 항목 번호 상수로, 게이트는 호출자가 넘긴
`ReferenceLookup(항목 번호, 기준 날짜 열 번호)`로 기대 모양을 다시 만들어 **컴파일 결과(글자와 상수
값)가 정확히 같은 서브쿼리만** 통과시킨다(정규형 비교). 규칙을 걸러내는 방식이 아니라
허용 모양 하나와
같은지 비교하는 방식이라, 모양에서 한 군데만 달라져도(다른 표·다른 열·비상수 항목 번호·다른 연도 식·
중첩·JOIN·UNION 등) 거부된다.

- 읽는 표는 `public.reference_values` 하나, 읽는 열은 `number_value`(값)·`item_id`·`year`뿐이다.
- 항목 번호는 파이썬 `int` 상수다(바인드 또는 리터럴 렌더). `item_id`(integer)와 `NUMERIC` 상수를
  비교하면 열에 캐스트가 걸려 인덱스를 못 쓰므로 `CAST(… AS INTEGER)`다(PostgreSQL 16.10 실측).
- 연도는 자기 `ds_<번호>`의 기준 날짜 열에서만 뽑는다. 다른 데이터셋의 열은 기대 모양이 아니다.
"""

from __future__ import annotations

from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import pg8000
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import ScalarSelect, Select

from app.ddl.names import DYNAMIC_SCHEMA, check_dynamic_name, column_name, dataset_table_name

REFERENCE_SCHEMA = "public"
REFERENCE_TABLE = "reference_values"
ITEM_ID_MAX = 2**31 - 1  # PostgreSQL integer 범위

# 서브쿼리가 읽는 가벼운 표 설명(열 이름은 `app/db_metadata.py`의 `reference_values`와 같다. 시험이
# 대조한다). `public`을 명시해야 뷰 정의가 검색 경로에 의존하지 않는다.
_REFERENCE_VALUES = sa.table(
    REFERENCE_TABLE,
    sa.column("item_id", sa.Integer),
    sa.column("year", sa.Integer),
    sa.column("number_value", sa.Numeric),
    schema=REFERENCE_SCHEMA,
)


@dataclass(frozen=True)
class ReferenceLookup:
    """뷰에 들어가는 기준값 조회 하나: (항목 번호, 기준 날짜 열 번호)."""

    item_id: int
    base_column_id: int

    def __post_init__(self) -> None:
        for name, value in (
            ("항목 번호", self.item_id),
            ("기준 날짜 열 번호", self.base_column_id),
        ):
            if type(value) is not int or value < 1:
                raise ValueError(f"{name}는 양의 정수여야 한다.")
        if self.item_id > ITEM_ID_MAX:
            raise ValueError("항목 번호가 integer 범위를 넘는다.")


def reference_value_subquery(item_id: ColumnElement, base_date: ColumnElement) -> ScalarSelect:
    """`REF`의 서브쿼리 한 가지 모양. `item_id`는 `CAST(상수 AS INTEGER)`, `base_date`는 `ds` 열."""
    rv = _REFERENCE_VALUES.alias("rv")
    return (
        sa.select(rv.c.number_value)
        .where(
            rv.c.item_id == item_id,
            rv.c.year == sa.cast(sa.extract("year", base_date), sa.Integer),
        )
        .scalar_subquery()
    )


def _dialect() -> Dialect:
    return pg8000.dialect()


def lookup_key(select: Select) -> tuple[str, tuple[object, ...]]:
    """서브쿼리의 정규형: (바인드 자리표시자로 쓴 SQL 글자, 상수 값 순서). 비교 전용이다."""
    compiled = select.compile(dialect=_dialect())
    names = compiled.positiontup or []
    return str(compiled), tuple(
        (type(compiled.params[name]), compiled.params[name]) for name in names
    )


def expected_lookup_key(dataset_id: int, lookup: ReferenceLookup) -> tuple[str, tuple[object, ...]]:
    """호출자가 넘긴 (항목 번호, 기준 날짜 열 번호)로 만든 기대 모양의 정규형."""
    ds = sa.table(
        check_dynamic_name(dataset_table_name(dataset_id), "table"),
        sa.column(check_dynamic_name(column_name(lookup.base_column_id), "column"), sa.Date),
        schema=DYNAMIC_SCHEMA,
    )
    base_date = ds.c[column_name(lookup.base_column_id)]
    item = sa.cast(
        sa.bindparam("ref_item", lookup.item_id, type_=sa.Integer, unique=True), sa.Integer
    )
    subquery = reference_value_subquery(item, base_date)
    assert isinstance(subquery.element, Select)  # noqa: S101 - 우리가 만든 식이다
    return lookup_key(subquery.element)
