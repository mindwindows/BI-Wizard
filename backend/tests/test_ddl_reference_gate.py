"""뷰 게이트의 `REF` 서브쿼리 허용 범위 시험(06 §3-4, 03b 32-3 안 B): DB 없이 실행한다.

게이트(`app/ddl/dynamic.py`의 `_check_view_select`)는 서브쿼리를 **한 가지 모양**만 통과시킨다:
호출자가 넘긴 `ReferenceLookup(항목 번호, 기준 날짜 열 번호)`로 만든 기대 모양과 컴파일 결과(글자와
상수 값)가 정확히 같을 때. 이 파일은

- 양성 대조: 정상 모양과 그 조합(여러 개, 같은 모양 반복, 허용 함수로 감싸기)은 통과한다.
- 부정 시험: 모양을 한 군데씩 깨뜨린 서브쿼리(다른 표·schema·열, 항목 번호의 비정수·비상수·불일치,
  연도 식 변경, 중첩, 여러 개 중 하나만 틀림, UNION·LATERAL·CTE·JOIN·파생 표·정렬·제한·잠금·집계·
  윈도, 허용 밖 함수, 열 식 밖의 위치, `text()`·`literal_column`)는 모두 거부된다.

를 확인한다. 거부는 DB 문장이 실행되기 전이다(`run_ddl`에 연결 대신 `None`을 줘도 거부가 먼저다).
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.schema import CreateView

from app.ddl import DdlError, ReferenceLookup, reference_value_subquery
from app.ddl.dynamic import _check_view_select, run_ddl
from app.ddl.reference_lookup import expected_lookup_key, lookup_key

DATASET = 5
DS = sa.table(
    "ds_5",
    sa.column("row_id", sa.BigInteger),
    sa.column("c_1", sa.Date),
    sa.column("c_2", sa.Numeric),
    sa.column("c_4", sa.Date),
    schema="bi_data",
)
OTHER_DS = sa.table("ds_6", sa.column("c_1", sa.Date), schema="bi_data")
RV = sa.table(
    "reference_values",
    sa.column("id", sa.Integer),
    sa.column("item_id", sa.Integer),
    sa.column("year", sa.Integer),
    sa.column("number_value", sa.Numeric),
    sa.column("created_by", sa.Integer),
    schema="public",
).alias("rv")
LOOKUP = ReferenceLookup(7, 1)
# 정규형 비교에서 거부될 때의 메시지. 거부 사례는 `match=SHAPE`로 다른 선행 검사(text·사용자
# 연산자·함수 목록)에 걸려 정규형 비교까지 가지 않은 것이 아님을 보인다(그 검사들은 비교 뒤에 온다).
SHAPE = "허용된 기준값 조회 모양"
COLUMN_ONLY = "열 식 안에서만"


def item(value: object = 7) -> sa.ColumnElement:
    """`CAST(<정수 상수> AS INTEGER)`: 상수 렌더러가 만드는 항목 번호와 같은 모양."""
    return sa.cast(sa.bindparam("lit", value, type_=sa.Integer, unique=True), sa.Integer)


def good_sub(item_number: int = 7, base=DS.c.c_1) -> sa.ColumnElement:
    return reference_value_subquery(item(item_number), base)


def year_of(column=DS.c.c_1, field: str = "year") -> sa.ColumnElement:
    return sa.cast(sa.extract(field, column), sa.Integer)


def inner(*conditions, columns=None, rv=RV):
    """모양을 바꿔 보기 위한 서브쿼리 조립(기본은 정상 모양의 한 갈래)."""
    return sa.select(*(columns or [rv.c.number_value])).where(*conditions)


def view_of(*expressions, froms=(DS,)) -> sa.Select:
    columns = [DS.c.row_id.label("row_id")]
    columns += [e.label(f"c_{10 + i}") for i, e in enumerate(expressions)]
    return sa.select(*columns).select_from(*froms)


def check(select: sa.Select, references=(LOOKUP,)) -> list[str]:
    return _check_view_select(select, DATASET, list(references))


# --- 양성 대조 ----


def test_the_expected_shape_passes_and_returns_the_output_column_names():
    assert check(view_of(good_sub())) == ["row_id", "c_10"]


def test_the_shape_the_converter_builds_has_the_same_normal_form_as_the_gates_expectation():
    sub = good_sub()
    assert lookup_key(sub.element) == expected_lookup_key(DATASET, LOOKUP)


def test_several_lookups_the_same_lookup_twice_and_wrapped_by_allowed_functions_pass():
    other = ReferenceLookup(9, 4)
    both = view_of(
        good_sub(),
        good_sub(),  # 같은 모양 반복(숙주 수식에서 같은 REF가 여러 번 나온다)
        good_sub(9, DS.c.c_4),
        sa.func.round(good_sub(), 2),
        sa.case((good_sub().is_(None), 4)),  # 오류 식 `CASE WHEN (서브쿼리) IS NULL THEN 4`
        good_sub() * good_sub(9, DS.c.c_4),
    )
    assert len(check(both, [LOOKUP, other])) == 7


def test_the_error_expression_shape_passes():
    de = sa.select(DS.c.row_id, sa.case((good_sub().is_(None), sa.literal(4))).label("e_3"))
    assert check(de.select_from(DS)) == ["row_id", "e_3"]


# --- 부정 시험: 허용 목록(호출자가 넘긴 번호) ----


def test_without_any_declared_lookup_every_subquery_is_rejected():
    with pytest.raises(DdlError, match=SHAPE):
        check(view_of(good_sub()), references=())


@pytest.mark.parametrize(
    "references",
    [
        [ReferenceLookup(8, 1)],  # 항목 번호가 호출자가 넘긴 값과 다름
        [ReferenceLookup(7, 2)],  # 기준 날짜 열 번호가 다름
        [ReferenceLookup(70, 10)],
    ],
)
def test_a_subquery_that_differs_from_the_declared_lookup_is_rejected(references):
    with pytest.raises(DdlError, match=SHAPE):
        check(view_of(good_sub()), references)


def test_one_wrong_subquery_among_valid_ones_rejects_the_whole_view():
    with pytest.raises(DdlError, match=SHAPE):
        check(view_of(good_sub(), good_sub(8), good_sub()))  # 8번은 선언되지 않았다


def test_the_base_column_must_belong_to_the_dataset_that_owns_the_view():
    """다른 데이터셋의 기준 날짜 열로 연도를 뽑는 서브쿼리는 기대 모양이 아니다."""
    with pytest.raises(DdlError, match=SHAPE):
        check(view_of(good_sub(7, OTHER_DS.c.c_1)))


def test_the_declared_lookup_is_validated_before_use():
    for bad in ((0, 1), (-1, 1), (7, 0), (True, 1), (7, True), (2**31, 1), ("7", 1)):
        with pytest.raises((ValueError, TypeError)):
            ReferenceLookup(*bad)  # type: ignore[arg-type]


# --- 부정 시험: 표·schema·열 ----


def _where_ok(rv=RV):
    return [rv.c.item_id == item(), rv.c.year == year_of()]


def other_table(table):
    return inner(
        table.c.item_id == item(), table.c.year == year_of(), columns=[table.c.number_value]
    )


def _t(name: str, schema: str | None, *columns: str) -> sa.Alias:
    return sa.table(name, *[sa.column(c) for c in columns], schema=schema).alias("rv")


@pytest.mark.parametrize(
    "sub",
    [
        # 다른 표·다른 schema (reference_values가 아닌 모든 것)
        pytest.param(
            other_table(_t("users", "public", "item_id", "year", "number_value")), id="users"
        ),
        pytest.param(
            other_table(_t("reference_items", "public", "item_id", "year", "number_value")),
            id="reference_items",
        ),
        pytest.param(
            other_table(_t("datasets", "public", "item_id", "year", "number_value")), id="datasets"
        ),
        pytest.param(
            other_table(_t("audit_log", "public", "item_id", "year", "number_value")),
            id="audit_log",
        ),
        pytest.param(
            other_table(_t("ds_6", "bi_data", "item_id", "year", "number_value")), id="other-ds"
        ),
        pytest.param(
            other_table(_t("dv_5", "bi_data", "item_id", "year", "number_value")), id="own-dv"
        ),
        # schema 한정 누락(검색 경로에 의존하는 `reference_values`)
        pytest.param(
            other_table(_t("reference_values", None, "item_id", "year", "number_value")),
            id="no-schema",
        ),
        pytest.param(
            other_table(_t("reference_values", "bi_data", "item_id", "year", "number_value")),
            id="wrong-schema",
        ),
        # 다른 열을 읽음: id, year, created_by, 여러 열, 상수 열
        pytest.param(inner(*_where_ok(), columns=[RV.c.id]), id="col-id"),
        pytest.param(inner(*_where_ok(), columns=[RV.c.year]), id="col-year"),
        pytest.param(inner(*_where_ok(), columns=[RV.c.created_by]), id="col-created_by"),
        pytest.param(inner(*_where_ok(), columns=[RV.c.number_value, RV.c.id]), id="two-columns"),
        pytest.param(inner(*_where_ok(), columns=[sa.literal(1)]), id="const-column"),
        pytest.param(inner(*_where_ok(), columns=[RV.c.number_value + 1]), id="expr-column"),
    ],
)
def test_other_tables_schemas_and_columns_are_rejected(sub):
    with pytest.raises(DdlError, match=SHAPE):
        check(view_of(sub.scalar_subquery()))


def test_selecting_all_columns_of_the_table_is_rejected():
    star = sa.select(RV).where(*_where_ok()).scalar_subquery()
    with pytest.raises(DdlError, match=SHAPE):
        check(view_of(star))


# --- 부정 시험: 항목 번호 `item_id` ----


@pytest.mark.parametrize(
    "item_side",
    [
        pytest.param(sa.literal(7), id="plain-bind-no-cast"),
        pytest.param(
            sa.cast(sa.bindparam("lit", 7, type_=sa.Integer, unique=True), sa.Numeric),
            id="numeric-cast",
        ),
        pytest.param(
            sa.cast(sa.bindparam("lit", 7, type_=sa.Integer, unique=True), sa.BigInteger),
            id="bigint-cast",
        ),
        pytest.param(
            sa.cast(sa.bindparam("lit", "7", type_=sa.Text, unique=True), sa.Text), id="text"
        ),
        pytest.param(
            sa.cast(sa.bindparam("lit", 7.0, type_=sa.Float, unique=True), sa.Integer),
            id="float-bind",
        ),
        pytest.param(
            sa.cast(sa.bindparam("lit", True, type_=sa.Boolean, unique=True), sa.Integer),
            id="bool-bind",
        ),
        pytest.param(
            sa.cast(sa.bindparam("lit", None, type_=sa.Integer, unique=True), sa.Integer), id="null"
        ),
        pytest.param(sa.cast(sa.null(), sa.Integer), id="null-literal"),
        pytest.param(RV.c.id, id="column"),
        pytest.param(RV.c.item_id, id="itself"),
        pytest.param(DS.c.row_id, id="outer-column"),
        pytest.param(item() + 0, id="expression"),
        pytest.param(sa.func.abs(item()), id="function"),
        pytest.param(sa.cast(sa.func.coalesce(item(), item()), sa.Integer), id="coalesce"),
        pytest.param(sa.select(sa.literal(7)).scalar_subquery(), id="scalar-subquery"),
    ],
)
def test_item_id_must_be_an_integer_constant_cast_to_integer(item_side):
    sub = inner(RV.c.item_id == item_side, RV.c.year == year_of()).scalar_subquery()
    with pytest.raises(DdlError, match=SHAPE):
        check(view_of(sub))


def test_item_id_from_a_bind_value_that_is_not_the_declared_number_is_rejected():
    for value in (8, 0, -7, 2**31 - 1):
        with pytest.raises(DdlError, match=SHAPE):
            check(view_of(good_sub(value)))


def test_changing_the_comparison_operator_or_swapping_sides_is_rejected():
    for cond in (RV.c.item_id != item(), RV.c.item_id > item(), RV.c.item_id.in_([item()])):
        sub = inner(cond, RV.c.year == year_of()).scalar_subquery()
        with pytest.raises(DdlError, match=SHAPE):
            check(view_of(sub))


# --- 부정 시험: 연도 조건 ----


@pytest.mark.parametrize(
    "year_side",
    [
        pytest.param(sa.cast(sa.literal(2026), sa.Integer), id="constant"),
        pytest.param(year_of(DS.c.c_1, "month"), id="month"),
        pytest.param(year_of(DS.c.c_1, "day"), id="day"),
        pytest.param(year_of(DS.c.c_2), id="other-column-c_2"),
        pytest.param(year_of(DS.c.c_4), id="other-date-column-c_4"),
        pytest.param(year_of(DS.c.row_id), id="row_id"),
        pytest.param(year_of(OTHER_DS.c.c_1), id="other-dataset-column"),
        pytest.param(year_of(sa.func.now()), id="now"),
        pytest.param(sa.cast(sa.extract("year", DS.c.c_1), sa.Numeric), id="numeric-cast"),
        pytest.param(sa.extract("year", DS.c.c_1), id="no-cast"),
        pytest.param(year_of(DS.c.c_1) + 1, id="plus-one"),
        pytest.param(RV.c.year, id="itself"),
        pytest.param(RV.c.id, id="id"),
        pytest.param(sa.func.abs(year_of()), id="function"),
        pytest.param(sa.case((DS.c.c_1.is_not(None), year_of()), else_=year_of()), id="case"),
        pytest.param(sa.select(sa.literal(2026)).scalar_subquery(), id="nested-subquery"),
        pytest.param(sa.cast(sa.func.date_part("year", DS.c.c_1), sa.Integer), id="date_part"),
    ],
)
def test_year_must_come_only_from_the_base_date_column_of_its_own_ds(year_side):
    sub = inner(RV.c.item_id == item(), RV.c.year == year_side).scalar_subquery()
    with pytest.raises(DdlError, match=SHAPE):
        check(view_of(sub))


def test_missing_or_extra_conditions_are_rejected():
    for conditions in (
        [RV.c.item_id == item()],
        [RV.c.year == year_of()],
        [],
        [RV.c.item_id == item(), RV.c.year == year_of(), RV.c.id == 1],
        [RV.c.item_id == item(), RV.c.item_id == item(), RV.c.year == year_of()],
        [sa.or_(RV.c.item_id == item(), RV.c.year == year_of())],
        [RV.c.item_id == item(), sa.false(), RV.c.year == year_of()],
    ):
        with pytest.raises(DdlError, match=SHAPE):
            check(view_of(inner(*conditions).scalar_subquery()))


# --- 부정 시험: 구조(중첩·집합·JOIN 등) ----


def _base():
    return inner(*_where_ok())


@pytest.mark.parametrize(
    "build",
    [
        pytest.param(lambda: _base().order_by(RV.c.year), id="order-by"),
        pytest.param(lambda: _base().limit(1), id="limit"),
        pytest.param(lambda: _base().offset(1), id="offset"),
        pytest.param(lambda: _base().distinct(), id="distinct"),
        pytest.param(lambda: _base().group_by(RV.c.number_value), id="group-by"),
        pytest.param(lambda: _base().group_by(RV.c.number_value).having(sa.true()), id="having"),
        pytest.param(lambda: _base().with_for_update(), id="for-update"),
        pytest.param(lambda: _base().with_for_update(read=True), id="for-share"),
        pytest.param(
            lambda: inner(*_where_ok(), columns=[sa.func.sum(RV.c.number_value)]), id="aggregate"
        ),
        pytest.param(
            lambda: inner(
                *_where_ok(), columns=[sa.func.max(RV.c.number_value).over(partition_by=RV.c.year)]
            ),
            id="window",
        ),
        pytest.param(
            lambda: (
                sa.select(RV.c.number_value)
                .select_from(
                    RV.join(
                        sa.table("users", sa.column("id"), schema="public"),
                        RV.c.created_by == sa.column("id"),
                    )
                )
                .where(*_where_ok())
            ),
            id="join",
        ),
        pytest.param(
            lambda: (
                sa.select(RV.c.number_value)
                .select_from(
                    RV.outerjoin(
                        _t("reference_items", "public", "id"), RV.c.item_id == sa.column("id")
                    )
                )
                .where(*_where_ok())
            ),
            id="left-join-same-family",
        ),
        pytest.param(
            lambda: sa.select(sa.column("number_value")).select_from(
                sa.select(RV.c.number_value).where(*_where_ok()).subquery("d")
            ),
            id="derived-table",
        ),
        pytest.param(
            lambda: sa.select(sa.column("number_value")).select_from(
                sa.select(RV.c.number_value).where(*_where_ok()).cte("c")
            ),
            id="cte",
        ),
        pytest.param(
            lambda: sa.select(sa.column("number_value")).select_from(
                sa.select(RV.c.number_value).where(*_where_ok()).lateral("l")
            ),
            id="lateral-in-subquery",
        ),
        pytest.param(
            lambda: sa.union(_base(), _base()),
            id="union",
        ),
        pytest.param(
            lambda: sa.union_all(_base(), _base()),
            id="union-all",
        ),
        pytest.param(lambda: sa.intersect(_base(), _base()), id="intersect"),
        pytest.param(lambda: sa.except_(_base(), _base()), id="except"),
    ],
)
def test_structural_variations_of_the_subquery_are_rejected(build):
    built = build()
    sub = built.scalar_subquery()
    with pytest.raises(DdlError, match=SHAPE):
        check(view_of(sub))


def test_a_nested_subquery_inside_the_subquery_is_rejected():
    nested = sa.select(RV.c.number_value).where(
        RV.c.item_id == item(),
        RV.c.year == sa.select(year_of()).scalar_subquery(),
    )
    with pytest.raises(DdlError, match=SHAPE):
        check(view_of(nested.scalar_subquery()))
    deeper = sa.select(good_sub().label("x")).scalar_subquery()  # 정상 서브쿼리를 한 겹 더 감쌈
    with pytest.raises(DdlError, match=SHAPE):
        check(view_of(deeper))


def test_text_and_literal_column_inside_the_subquery_are_rejected():
    for sub in (
        inner(sa.text("1 = 1"), *_where_ok()),
        inner(RV.c.item_id == sa.text("7"), RV.c.year == year_of()),
        inner(RV.c.item_id == item(), RV.c.year == sa.literal_column("2026")),
        sa.select(sa.literal_column("number_value")).select_from(RV).where(*_where_ok()),
    ):
        with pytest.raises(DdlError, match=SHAPE):
            check(view_of(sub.scalar_subquery()))


def test_a_forbidden_function_inside_the_subquery_is_rejected():
    sleepy = inner(*_where_ok(), columns=[sa.func.pg_sleep(1)])
    with pytest.raises(DdlError, match=SHAPE):
        check(view_of(sleepy.scalar_subquery()))
    version = inner(
        RV.c.item_id == item(), RV.c.year == sa.cast(sa.func.pg_backend_pid(), sa.Integer)
    )
    with pytest.raises(DdlError, match=SHAPE):
        check(view_of(version.scalar_subquery()))


def test_custom_operators_and_callable_binds_inside_the_subquery_are_rejected():
    custom = inner(RV.c.item_id.op("= 7 OR 1 =")(item()), RV.c.year == year_of())
    with pytest.raises(DdlError, match=SHAPE):
        check(view_of(custom.scalar_subquery()))
    callable_item = sa.cast(sa.bindparam("lit", callable_=lambda: 7, type_=sa.Integer), sa.Integer)
    with pytest.raises(DdlError, match="호출형"):  # 정규형 비교 전에 상수 검사가 먼저 거부한다
        check(
            view_of(inner(RV.c.item_id == callable_item, RV.c.year == year_of()).scalar_subquery())
        )


# --- 부정 시험: 서브쿼리가 놓이는 자리 ----


def test_a_correct_subquery_outside_the_column_list_is_rejected():
    """모양이 정상이어도 열 식 밖(WHERE·ORDER BY·GROUP BY·FROM·IN·EXISTS)이면 거부한다."""
    good = good_sub()
    outer = sa.select(DS.c.row_id).select_from(DS)
    for select in (
        outer.where(good.is_not(None)),
        outer.order_by(good),
        outer.group_by(good),
        outer.having(good.is_not(None)).group_by(DS.c.row_id),
        sa.select(DS.c.row_id).select_from(DS).where(DS.c.row_id.in_([good])),
    ):
        with pytest.raises(DdlError, match=COLUMN_ONLY):
            check(select)
    exists = sa.select(DS.c.row_id).select_from(DS).where(sa.exists(inner(*_where_ok())))
    with pytest.raises(DdlError, match=COLUMN_ONLY):
        check(exists)


def test_a_correct_subquery_as_a_derived_table_or_cte_of_the_view_is_rejected():
    body = sa.select(good_sub().label("v"), DS.c.row_id).select_from(DS)
    for source in (body.subquery("s"), body.cte("c"), body.lateral("l")):
        select = sa.select(source.c.row_id).select_from(source)
        with pytest.raises(DdlError, match=COLUMN_ONLY):
            check(select)


def test_a_view_over_two_tables_is_still_rejected_even_with_a_correct_subquery():
    other = sa.table("ds_9", sa.column("row_id"), schema="bi_data")
    with pytest.raises(DdlError, match="자기 원본 표 하나만"):
        check(view_of(good_sub(), froms=(DS, other)))
    with pytest.raises(DdlError, match="자기 원본 표"):
        check(view_of(good_sub(), froms=(OTHER_DS,)))


def test_a_view_that_is_itself_a_union_is_rejected():
    union = sa.union_all(view_of(good_sub()), view_of(good_sub()))
    with pytest.raises(DdlError, match="SELECT여야"):
        check(union)  # type: ignore[arg-type]


def test_literal_column_and_text_in_the_outer_view_are_still_rejected():
    for expression, reason in (
        (sa.literal_column("1").label("x"), "literal_column"),
        (sa.text("1"), r"text\(\)"),
    ):
        with pytest.raises(DdlError, match=reason):
            check(sa.select(DS.c.row_id, expression).select_from(DS))


# --- `run_ddl`도 같은 게이트(실행 전에 거부, 연결 없이도) ----


def test_run_ddl_applies_the_same_gate_before_touching_the_database():
    view = view_of(good_sub())
    statement = CreateView(view, "dv_5", schema="bi_data")
    with pytest.raises(DdlError, match=SHAPE):
        run_ddl(None, statement)  # type: ignore[arg-type]  # 선언된 조회가 없으면 DB 전에 거부
    with pytest.raises(DdlError, match=SHAPE):
        run_ddl(None, statement, references=[ReferenceLookup(8, 1)])  # type: ignore[arg-type]
