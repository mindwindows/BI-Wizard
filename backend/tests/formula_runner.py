"""함수 사전 `cases`를 실행하는 공통 도구(1단계 SQLite/컴파일 시험과 2단계 PostgreSQL 시험이 함께
쓴다).

- `case_columns(case)`: 사례의 열 선언 -> `ColumnInfo`(번호는 선언 순서대로 1부터, 태그 포함).
- `case_sources(case, columns, typed_cast)`: 열 값 -> 바인드 식(표 없이 한 행을 흉내 낸다).
  PostgreSQL은 값을
  `CAST`로 형을 고정하고, SQLite는 날짜 `CAST`가 문자열을 깨뜨리므로 형 있는 바인드만 쓴다.
- `evaluate_case(connection, case, ...)`: 사례를 컴파일·실행해 기대와 비교한다(실패 시
  AssertionError).
- `make_probe(connection)`: C0의 상수 부분식 검사용 `ConstProbe`(상수 SELECT).
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

import sqlalchemy as sa

from app.formula import (
    LITERALS,
    ColumnInfo,
    FunctionRegistry,
    compile_formula,
    get_default_registry,
    render_literal_sql,
)
from app.formula.cases import ERROR, OK, REJECT, Case

_SQL_TYPES = {
    "number": sa.Numeric,
    "text": sa.Text,
    "choice": sa.Text,
    "boolean": sa.Boolean,
    "date": sa.Date,
}


def case_columns(case: Case) -> list[ColumnInfo]:
    return [
        ColumnInfo(index, name, column_type, tag=case.tags.get(name))
        for index, (name, column_type) in enumerate(case.cols.items(), start=1)
    ]


def _typed_value(column_type: str, value: Any) -> Any:
    if value is None:
        return None
    if column_type == "number":
        return Decimal(str(value))
    return value


def case_sources(
    case: Case,
    columns: Sequence[ColumnInfo],
    *,
    typed_cast: bool,
    via_literals: bool = False,
) -> dict[int, Any]:
    """열 값을 식으로 만든다.

    `via_literals`면 렌더러(`Literals`)를 거치므로 뷰와 같은 리터럴 렌더도 가능하다.
    """
    sources: dict[int, Any] = {}
    for column in columns:
        type_ = _SQL_TYPES[column.type]()
        kind = "text" if column.type == "choice" else column.type
        value = _typed_value(column.type, case.row.get(column.name))
        if via_literals:
            sources[column.id] = LITERALS.null(kind) if value is None else _literal(kind, value)
            continue
        if value is None:
            expression = sa.cast(sa.null(), type_)
        else:
            expression = sa.bindparam(f"v{column.id}", value, type_=type_)
            if typed_cast:
                expression = sa.cast(expression, type_)
        sources[column.id] = expression
    return sources


def _literal(kind: str, value: Any) -> Any:
    return getattr(LITERALS, "number" if kind == "number" else kind)(value)


def make_probe(connection: sa.Connection):
    """상수 SELECT 한 번으로 조건 식 목록을 평가한다(읽기만 한다)."""

    def probe(conditions: Sequence[Any]) -> list[Any]:
        statement = sa.select(
            *[sa.cast(c, sa.Boolean).label(f"p{i}") for i, c in enumerate(conditions)]
        )
        return list(connection.execute(statement).one())

    return probe


def values_equal(actual: Any, expected: Any, *, tolerance: Decimal | None = None) -> bool:
    if expected is None or actual is None:
        return expected is None and actual is None
    if isinstance(expected, bool) or isinstance(actual, bool):
        return bool(actual) == bool(expected) and isinstance(actual, bool | int)
    if isinstance(expected, datetime.date):
        return str(actual) == str(expected)
    if isinstance(expected, str) and not _is_number_text(expected):
        return actual == expected
    left, right = Decimal(str(actual)), Decimal(str(expected))
    if tolerance is not None:
        return abs(left - right) <= tolerance
    return left == right


def _is_number_text(value: str) -> bool:
    try:
        Decimal(value)
    except Exception:
        return False
    return True


def execute_case(
    connection: sa.Connection,
    case: Case,
    *,
    typed_cast: bool,
    registry: FunctionRegistry | None = None,
    use_probe: bool = True,
):
    """사례를 컴파일하고 (결과, 값, 오류 코드)를 돌려준다. 거부 사례는 값 대신 결과만 쓴다."""
    registry = registry or get_default_registry()
    columns = case_columns(case)
    result = compile_formula(
        case.expression,
        columns,
        registry=registry,
        source_columns=case_sources(case, columns, typed_cast=typed_cast),
        const_probe=make_probe(connection) if use_probe else None,
    )
    if not result.ok or case.expect == REJECT:
        return result, None, None
    error = result.error if result.error is not None else sa.cast(sa.null(), sa.SmallInteger())
    row = connection.execute(sa.select(result.value.label("v"), error.label("e"))).one()
    return result, row.v, row.e


def evaluate_case(
    connection: sa.Connection,
    case: Case,
    *,
    typed_cast: bool,
    tolerance: Decimal | None = None,
    registry: FunctionRegistry | None = None,
) -> None:
    """사례를 실행해 기대와 다르면 `AssertionError`."""
    from app.formula import CELL_ERROR_BY_NUMBER

    result, value, error = execute_case(connection, case, typed_cast=typed_cast, registry=registry)
    label = f"{case.expression!r} {dict(case.row)}"
    if case.expect == REJECT:
        codes = [issue.code for issue in result.issues]
        assert not result.ok, f"거부돼야 하는데 통과했다: {label}"
        assert case.error in codes, f"{label}: 기대 {case.error}, 실제 {codes}"
        return
    assert result.ok, f"{label}: 컴파일 실패 {[i.as_dict() for i in result.issues]}"
    if case.expect == ERROR:
        assert error is not None, f"{label}: 오류 칸이어야 하는데 오류 없음(값 {value!r})"
        assert CELL_ERROR_BY_NUMBER[int(error)] == case.error, f"{label}: 오류 {error}"
        assert value is None, f"{label}: 오류 칸의 값은 빈 값이어야 한다({value!r})"
        return
    assert case.expect == OK
    assert error is None, f"{label}: 오류 없어야 하는데 {CELL_ERROR_BY_NUMBER.get(int(error))}"
    assert values_equal(value, case.value, tolerance=tolerance), (
        f"{label}: 기대 {case.value!r}, 실제 {value!r}"
    )


def run_cases_on(
    connection: sa.Connection, *, registry: FunctionRegistry | None = None
) -> tuple[int, list[str]]:
    """사전의 모든 사례를 이 연결(PostgreSQL)에서 실행한다. (사례 수, 실패 설명 목록)."""
    registry = registry or get_default_registry()
    failures: list[str] = []
    total = 0
    for spec in registry.specs():
        for case in spec.cases:
            total += 1
            try:
                evaluate_case(connection, case, typed_cast=True, registry=registry)
            except Exception as exc:
                connection.rollback()
                failures.append(f"{spec.name} | {case.expression} {dict(case.row)} | {exc}"[:400])
    return total, failures


def _typed_row(connection: sa.Connection, value: Any, error: Any, *, literal: bool) -> tuple:
    kind_of_value = sa.func.pg_typeof(value).cast(sa.Text)
    statement = sa.select(value.label("v"), error.label("e"), kind_of_value.label("t"))
    if literal:
        # 뷰와 같은 리터럴 렌더 경로(시험 전용: 렌더된 글자를 그대로 실행한다)
        row = connection.exec_driver_sql(render_literal_sql(statement)).one()
    else:
        row = connection.execute(statement).one()
    return tuple(row)


def differential_check(
    connection: sa.Connection, case: Case, *, registry: FunctionRegistry | None = None
) -> str | None:
    """미리보기(바인드)와 뷰(리터럴 렌더)의 결과·`pg_typeof`·오류 코드가 같은지. 다르면 설명."""
    registry = registry or get_default_registry()
    columns = case_columns(case)
    result = compile_formula(
        case.expression,
        columns,
        registry=registry,
        source_columns=case_sources(case, columns, typed_cast=True, via_literals=True),
        const_probe=make_probe(connection),
    )
    if not result.ok:
        return None if case.expect == REJECT else f"컴파일 실패 {result.issues}"
    error = result.error if result.error is not None else LITERALS.null("smallint")
    bound = _typed_row(connection, result.value, error, literal=False)
    rendered = _typed_row(connection, result.value, error, literal=True)
    return None if bound == rendered else f"바인드 {bound} != 리터럴 {rendered}"


def _row_subquery(row: dict[str, Any], columns: Sequence[ColumnInfo]):
    """열 값 한 행을 "표처럼" 보이게 하는 최적화 장벽 서브쿼리(`OFFSET 0`).

    열을 읽는 식이 계획 시간에 상수로 접히지 않게 해서 실제 뷰(표의 열을 읽음)와 같은 조건으로
    시험한다.
    상수는 모두 `LITERALS`를 거치므로 뷰와 같은 리터럴 렌더도 가능하다.
    """
    items = []
    for column in columns:
        kind = "text" if column.type == "choice" else column.type
        value = row.get(column.name)
        expression = LITERALS.null(kind) if value is None else _literal(kind, value)
        items.append(expression.label(column.name))
    return sa.select(*items).offset(LITERALS.integer(0)).subquery("fz")


def fuzz_check(
    connection: sa.Connection,
    expressions: Sequence[str],
    rows: Sequence[dict[str, Any]],
    columns: Sequence[ColumnInfo],
    *,
    registry: FunctionRegistry | None = None,
) -> tuple[int, int, list[str]]:
    """무작위 수식을 모든 행에서 바인드·리터럴로 실행한다. (통과, 거부, 문제 목록).

    문제: DB 예외, 바인드와 리터럴 결과 불일치, 값과 오류 코드가 동시에 있음.
    """
    registry = registry or get_default_registry()
    accepted = rejected = 0
    problems: list[str] = []
    probe = make_probe(connection)
    for expression in expressions:
        for row in rows:
            subquery = _row_subquery(row, columns)
            sources = {c.id: subquery.c[c.name] for c in columns}
            result = compile_formula(
                expression, columns, registry=registry, source_columns=sources, const_probe=probe
            )
            if not result.ok:
                rejected += 1
                break  # 수식 거부는 행과 무관하다
            error = result.error if result.error is not None else LITERALS.null("smallint")
            statement = sa.select(
                result.value.label("v"),
                error.label("e"),
                sa.func.pg_typeof(result.value).cast(sa.Text).label("t"),
            ).select_from(subquery)
            try:
                bound = tuple(connection.execute(statement).one())
                literal = tuple(connection.exec_driver_sql(render_literal_sql(statement)).one())
            except Exception as exc:
                connection.rollback()
                problems.append(f"DB 예외 {expression} {row}: {str(exc)[:160]}")
                continue
            if bound != literal:
                problems.append(f"불일치 {expression} {row}: {bound} != {literal}")
            if bound[0] is not None and bound[1] is not None:
                problems.append(f"값과 오류가 함께 있음 {expression} {row}: {bound}")
        else:
            accepted += 1
    return accepted, rejected, problems
