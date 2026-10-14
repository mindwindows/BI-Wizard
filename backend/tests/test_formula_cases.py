"""함수 사전 `cases` 실행(07 §2-1, §3 K6·K7): SQLite 평가, PostgreSQL 컴파일, 프레임워크 의미 규칙.

- `sqlite=True`인 함수만 쓰는 사례는 SQLite에서 **평가**한다(값·오류 코드·빈 값). SQLite가 못 하는
  함수
  (`make_date`, `regexp_replace`, `btrim`, `least` 등)가 들어간 사례는 평가를 PostgreSQL 시험으로
  넘기되,
  PostgreSQL 방언으로 컴파일되고 모든 상수가 `CAST(… AS 형)`으로 렌더되는지는 여기서 검사한다.
- 같은 사례 데이터를 2단계가 실제 PostgreSQL에서 그대로 실행한다(`tests/formula_runner.py`,
  `test_formula_pg.py`).
"""

import re
from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.formula import (
    CompileResult,
    FunctionSpec,
    build_default_registry,
    compile_formula,
    get_default_registry,
    render_literal_sql,
)
from app.formula.cases import ERROR, OK, REJECT, Case, err, ok, reject
from app.formula.literals import NUMBER
from app.formula.registry import ErrorRule, Param
from tests.formula_helpers import SqliteProbe
from tests.formula_runner import case_columns, case_env, case_sources, evaluate_case

REGISTRY = get_default_registry()
ALL_CASES = [
    (spec.name, index, case) for spec in REGISTRY.specs() for index, case in enumerate(spec.cases)
]
TOLERANCE = Decimal("1E-9")


def _case_id(item) -> str:
    name, index, case = item
    return f"{name}#{index}:{case.expression}"


def _sqlite_capable(case: Case) -> bool:
    """사례가 쓰는 함수가 모두 SQLite에서 평가 가능한가(정적 컴파일로 알아낸다)."""
    columns = case_columns(case)
    result = compile_formula(
        case.expression, columns, registry=REGISTRY, build_sql=False, env=case_env(case, columns)
    )
    if not result.ok:  # 거부 사례
        return True
    return all(REGISTRY.get(name).sqlite for name in result.functions_used)


@pytest.fixture(scope="module")
def sqlite_connection():
    engine = sa.create_engine("sqlite://")
    with engine.connect() as connection:
        yield connection
    engine.dispose()


@pytest.mark.parametrize("item", ALL_CASES, ids=_case_id)
def test_cases_evaluate_on_sqlite_when_the_functions_allow_it(item, sqlite_connection):
    _name, _index, case = item
    if case.expect == REJECT and case.error == "CONSTANT_ERROR":
        columns = case_columns(case)
        probe = SqliteProbe()
        try:
            result = compile_formula(
                case.expression,
                columns,
                registry=REGISTRY,
                const_probe=probe,
                env=case_env(case, columns),
            )
        finally:
            probe.close()
        codes = [issue.code for issue in result.issues]
        if "CONSTANT_PROBE_FAILED" in codes:
            pytest.skip("상수 조건을 SQLite가 평가하지 못한다(PostgreSQL 시험으로 넘긴다)")
        assert not result.ok and "CONSTANT_ERROR" in codes
        return
    if case.expect == REJECT:
        columns = case_columns(case)
        result = compile_formula(
            case.expression,
            columns,
            registry=REGISTRY,
            build_sql=False,
            env=case_env(case, columns),
        )
        assert not result.ok
        assert case.error in [issue.code for issue in result.issues], result.issues
        return
    if not _sqlite_capable(case):
        pytest.skip("PostgreSQL 전용 함수가 들어 있다(2단계 PostgreSQL 시험이 평가한다)")
    evaluate_case(sqlite_connection, case, typed_cast=False, tolerance=TOLERANCE, registry=REGISTRY)


def test_enough_cases_are_evaluated_on_sqlite():
    evaluated = [c for _n, _i, c in ALL_CASES if c.expect != REJECT and _sqlite_capable(c)]
    assert len(evaluated) >= 60
    kinds = {c.expect for c in evaluated}
    assert kinds == {OK}, "SQLite로 평가 가능한 오류 사례는 아래 NOZERO 시험이 따로 맡는다"
    assert len(ALL_CASES) >= 200


# --- PostgreSQL 컴파일: 모든 사례, 모든 상수는 CAST ----

_STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")
_BARE_NUMBER = re.compile(r"(?<![\w.$])\d+(?:\.\d+)?(?:[eE][+-]?\d+)?(?![\w.])")


def _constants_outside_cast(sql: str) -> list[str]:
    """`CAST(<상수> AS 형)` 밖에 있는 문자·숫자 상수와 형 없는 NULL을 찾는다."""
    found: list[str] = []
    for match in _STRING_LITERAL.finditer(sql):
        if not sql[: match.start()].endswith("CAST("):
            found.append(match.group())
    without_strings = _STRING_LITERAL.sub("''", sql)
    for match in _BARE_NUMBER.finditer(without_strings):
        if not without_strings[: match.start()].endswith(("CAST(", "CAST(-")):
            found.append(match.group())
    for match in re.finditer(r"\bNULL\b", without_strings):
        before = without_strings[: match.start()]
        if not (before.endswith("CAST(") or before.endswith("IS ") or before.endswith("IS NOT ")):
            found.append("NULL")
    for match in re.finditer(r"\b(true|false)\b", without_strings, flags=re.IGNORECASE):
        if not without_strings[: match.start()].endswith("CAST("):
            found.append(match.group())
    return found


def _select_of(result: CompileResult):
    error = result.error if result.error is not None else sa.cast(sa.null(), sa.SmallInteger())
    return sa.select(result.value.label("v"), error.label("e"))


@pytest.mark.parametrize("item", ALL_CASES, ids=_case_id)
def test_every_case_compiles_for_postgresql_with_typed_constants(item):
    _name, _index, case = item
    if case.expect == REJECT and case.error != "CONSTANT_ERROR":
        return
    columns = case_columns(case)
    result = compile_formula(  # 상수 검사는 건너뜀
        case.expression, columns, registry=REGISTRY, env=case_env(case, columns)
    )
    assert result.ok, [i.as_dict() for i in result.issues]
    statement = _select_of(result)
    rendered = render_literal_sql(statement)  # pg8000 방언, 바인드 값 재검사 포함
    assert _constants_outside_cast(rendered) == [], rendered
    assert "%(" not in rendered
    # 미리보기(바인드)와 뷰(리터럴)는 같은 표현식이다: 바인드 이름은 모두 렌더러 것이다.
    bound = statement.compile(dialect=sa.dialects.postgresql.pg8000.dialect())
    assert all(name.startswith("lit_") for name in bound.params)


def test_constant_detector_finds_naked_constants():
    assert _constants_outside_cast("SELECT 1") == ["1"]
    assert _constants_outside_cast("SELECT 'a'") == ["'a'"]
    assert _constants_outside_cast("SELECT NULL") == ["NULL"]
    assert _constants_outside_cast("SELECT true") == ["true"]
    assert (
        _constants_outside_cast("SELECT CAST(1 AS NUMERIC), CAST('a' AS TEXT), c_1 IS NOT NULL")
        == []
    )
    assert _constants_outside_cast("SELECT c_12 + CAST(NULL AS DATE)") == []


# --- 프레임워크 의미 규칙(DB 종류와 무관): SQLite로 평가 가능한 시험용 함수 ----


def _nozero_registry():
    """`NOZERO(수)`: 값은 그대로, 0이면 E1.

    SQLite에서도 평가되므로 오류 의미 규칙을 DB 없이 확인할 수 있다.
    """
    spec = FunctionSpec(
        name="NOZERO",
        signature=(Param("수", NUMBER),),
        returns=NUMBER,
        null_policy="propagate",
        native_null=True,
        error_when=(ErrorRule("E1", lambda ctx, a: a[0].value == ctx.lit.number(0)),),
        to_sql=lambda ctx, a: a[0].value,
        excel_diff="시험용",
        help_ko="시험용: 0이면 오류 칸.",
        sqlite=True,
        cases=(
            ok("NOZERO(5)", 5),
            ok("NOZERO([a])", None, cols={"a": "number"}, row={}),
            err("NOZERO([a])", "E1", cols={"a": "number"}, row={"a": 0}),
        ),
    )
    registry = build_default_registry()
    registry.register(spec)
    return registry


_AB = {"a": "number", "b": "number"}

SEMANTIC_CASES = [
    # 오류 칸: 값은 빈 값 + 오류 코드, 빈 값은 오류가 아니다
    err("NOZERO([a])", "E1", cols=_AB, row={"a": 0}),
    ok("NOZERO([a])", 5, cols=_AB, row={"a": 5}),
    ok("NOZERO([a])", None, cols=_AB, row={}),
    # 인수 오류는 바깥 식에 전파된다
    err("NOZERO([a]) + 1", "E1", cols=_AB, row={"a": 0}),
    err("1 + NOZERO([a])", "E1", cols=_AB, row={"a": 0}),
    err("ABS(NOZERO([a]))", "E1", cols=_AB, row={"a": 0}),
    err("-NOZERO([a])", "E1", cols=_AB, row={"a": 0}),
    err("NOZERO([a]) > 0", "E1", cols=_AB, row={"a": 0}),
    err("NOZERO(NOZERO([a]))", "E1", cols=_AB, row={"a": 0}),
    err("SUM(1, NOZERO([a]), 2)", "E1", cols=_AB, row={"a": 0}),
    err("AND(NOZERO([a]) > 0, [b] > 0)", "E1", cols=_AB, row={"a": 0, "b": 1}),
    # 인수 오류 > 인수 빈 값: 한 인수가 오류면 다른 인수가 비어 있어도 오류 칸
    err("NOZERO([a]) + [b]", "E1", cols=_AB, row={"a": 0}),
    err("[b] + NOZERO([a])", "E1", cols=_AB, row={"a": 0}),
    ok("NOZERO([a]) + [b]", None, cols=_AB, row={"b": 1}, note="오류가 아니라 빈 값"),
    # IF: 고른 쪽만
    err("IF([a] > 0, NOZERO([b]), 9)", "E1", cols=_AB, row={"a": 1, "b": 0}),
    ok("IF([a] > 0, NOZERO([b]), 9)", 9, cols=_AB, row={"a": -1, "b": 0}),
    ok("IF([a] > 0, 9, NOZERO([b]))", 9, cols=_AB, row={"a": 1, "b": 0}),
    err("IF([a] > 0, 9, NOZERO([b]))", "E1", cols=_AB, row={"a": -1, "b": 0}),
    err("IF(NOZERO([a]) > 0, 1, 2)", "E1", cols=_AB, row={"a": 0}),
    ok(
        "IF([a] > 0, NOZERO([b]), 9)",
        None,
        cols=_AB,
        row={"b": 0},
        note="조건이 비면 빈 값, 오류 아님",
    ),
    # IFERROR: 오류 칸이면 대체값, 빈 값은 그대로, 대체값의 오류는 반영
    ok("IFERROR(NOZERO([a]), 7)", 7, cols=_AB, row={"a": 0}),
    ok("IFERROR(NOZERO([a]), 7)", 2, cols=_AB, row={"a": 2}),
    ok("IFERROR(NOZERO([a]), 7)", None, cols=_AB, row={}),
    ok("IFERROR(NOZERO([a]) + 1, 0)", 0, cols=_AB, row={"a": 0}),
    ok("IFERROR(NOZERO([a]) + 1, 0)", 3, cols=_AB, row={"a": 2}),
    err("IFERROR(NOZERO([a]), NOZERO([b]))", "E1", cols=_AB, row={"a": 0, "b": 0}),
    ok("IFERROR(NOZERO([a]), NOZERO([b]))", 3, cols=_AB, row={"a": 0, "b": 3}),
    ok(
        "IFERROR(NOZERO([a]), NOZERO([b]))",
        4,
        cols=_AB,
        row={"a": 4, "b": 0},
        note="안 쓰는 대체값 오류는 무시",
    ),
    ok("IFERROR(IFERROR(NOZERO([a]), NOZERO([b])), 8)", 8, cols=_AB, row={"a": 0, "b": 0}),
    # 오류가 없는 식은 오류 식이 없다
    ok("IFERROR([a] + 1, 0)", 2, cols=_AB, row={"a": 1}),
]


@pytest.mark.parametrize("case", SEMANTIC_CASES, ids=lambda c: f"{c.expression}|{dict(c.row)}")
def test_error_and_null_semantics_on_sqlite(case, sqlite_connection):
    evaluate_case(
        sqlite_connection, case, typed_cast=False, tolerance=TOLERANCE, registry=_nozero_registry()
    )


def test_expressions_that_cannot_fail_have_no_error_expression():
    registry = _nozero_registry()
    for expression in ("[a] + 1", "IFERROR(NOZERO([a]), 0)", "IF([a] > 0, 1, 2)", "SUM([a], [b])"):
        result = compile_formula(
            expression, case_columns(Case(expression, cols=_AB)), registry=registry
        )
        assert result.ok and result.error is None, expression
    for expression in ("NOZERO([a])", "NOZERO([a]) + 1", "IF([a] > 0, NOZERO([b]), 1)"):
        result = compile_formula(
            expression, case_columns(Case(expression, cols=_AB)), registry=registry
        )
        assert result.ok and result.error is not None, expression


def test_value_expression_does_not_leak_error_information():
    """값 식(`dv_`)에는 오류 코드가 없다. 오류는 오류 식(`de_`)에서만 나온다."""
    registry = _nozero_registry()
    result = compile_formula("NOZERO([a]) + 1", case_columns(Case("", cols=_AB)), registry=registry)
    assert "smallint" not in render_literal_sql(sa.select(result.value)).lower()
    assert "SMALLINT" in render_literal_sql(sa.select(result.error))


# --- 빈 값 전파 (K7) ----


@pytest.mark.parametrize(
    "expression",
    [
        "[a] + [b]",
        "[a] - [b]",
        "[a] * [b]",
        "-[a]",
        "ABS([a])",
        "SUM([a], [b])",
        "SUM([a], 1, [b])",
        "[a] > [b]",
        "[a] = [b]",
        "[a] <> [b]",
        "[a] <= [b]",
        "[a] >= [b]",
        "[a] < [b]",
        "AND([a] > 0, [b] > 0)",
        "OR([a] > 0, [b] > 0)",
        "NOT([a] > 0)",
        "IF([a] > 0, [a], [b])",
        "IF(TRUE, [a], [b])",
    ],
)
def test_any_empty_input_gives_an_empty_result_on_sqlite(expression, sqlite_connection):
    """어느 인수가 비어도 결과가 빈 값이다(0·거짓이 되지 않는다). 빈 칸 하나씩 모든 조합."""
    for row in ({}, {"a": 3}, {"b": 3}):
        used = [name for name in ("a", "b") if f"[{name}]" in expression]
        if all(name in row for name in used):
            continue
        if expression.startswith(("IF(TRUE", "IF([a] > 0, [a], [b])")) and "a" in row:
            continue  # 고른 갈래의 값이 있으면 빈 값이 아닐 수 있다(아래 별도 시험)
        case = ok(expression, None, cols=_AB, row=row)
        evaluate_case(sqlite_connection, case, typed_cast=False, tolerance=TOLERANCE)


def test_if_only_depends_on_the_chosen_branch_and_condition():
    columns_row = [
        (ok("IF([a] > 0, [a], [b])", 3, cols=_AB, row={"a": 3})),  # b가 비어 있어도 고른 갈래의 값
        (ok("IF([a] > 0, [a], [b])", None, cols=_AB, row={"a": -1})),  # 고른 갈래(b)가 비어 있음
        (ok("IF(TRUE, [a], [b])", 3, cols=_AB, row={"a": 3})),
    ]
    engine = sa.create_engine("sqlite://")
    with engine.connect() as connection:
        for case in columns_row:
            evaluate_case(connection, case, typed_cast=False, tolerance=TOLERANCE)
    engine.dispose()


def test_min_max_sum_sumtag_guard_every_argument_against_null_skipping():
    """PostgreSQL의 `least`/`greatest`는 NULL을 건너뛴다.

    그래서 모든 인수의 `IS NULL` 감싸기가 있어야 한다.
    """
    columns = [Case("", cols={"a": "number", "b": "number", "c": "number"})]
    cols = case_columns(columns[0])
    for name in ("MIN", "MAX"):
        result = compile_formula(f"{name}([a], [b], [c])", cols)
        sql = render_literal_sql(sa.select(result.value))
        assert len(re.findall(r"c_[123] IS NULL", sql)) == 3, sql
        assert ("least(" if name == "MIN" else "greatest(") in sql
    # SUM은 `+`가 NULL을 전파하므로 감싸기 없이 더하기만 있다
    sql = render_literal_sql(sa.select(compile_formula("SUM([a], [b], [c])", cols).value))
    assert "IS NULL" not in sql and sql.count("+") == 2


def test_text_comparison_lowercases_both_sides_and_other_types_do_not():
    cols = case_columns(Case("", cols={"s": "text", "n": "number"}))
    text_sql = render_literal_sql(sa.select(compile_formula('[s] = "ABC"', cols).value))
    assert text_sql.count("lower(") == 2
    other_sql = render_literal_sql(sa.select(compile_formula("[n] = 1", cols).value))
    assert "lower(" not in other_sql


def test_division_uses_nullif_and_never_a_bare_division():
    cols = case_columns(Case("", cols=_AB))
    sql = render_literal_sql(sa.select(compile_formula("[a] / [b]", cols).value))
    assert "nullif(c_2, CAST(0 AS NUMERIC))" in sql


def test_all_numbers_are_cast_to_numeric_including_integer_looking_ones():
    cols = case_columns(Case("", cols=_AB))
    sql = render_literal_sql(
        sa.select(compile_formula("[a] * 1000000000000000000000000000000", cols).value)
    )
    assert "CAST(1000000000000000000000000000000 AS NUMERIC)" in sql
    assert _constants_outside_cast(sql) == []


def test_sources_helper_builds_typed_bind_expressions():
    case = ok("[a]", 1, cols={"a": "number", "d": "date"}, row={"a": 1})
    sources = case_sources(case, case_columns(case), typed_cast=True)
    assert set(sources) == {1, 2}
    assert ERROR == "error" and OK == "value"
    assert reject("x", "Y").expect == REJECT
