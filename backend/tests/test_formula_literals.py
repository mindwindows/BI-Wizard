"""리터럴 렌더러 접점(07 §4)과 X-26 주입 회귀.

상수는 전부 `CAST`로 렌더되고 위험한 글자는 거부된다. DB 없이 실행한다.
"""

import ast
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql, sqlite

from app.formula import compile_formula, render_literal_sql
from app.formula.literals import (
    LITERALS,
    MAX_NUMBER_DIGITS,
    MAX_TEXT_CONSTANT_LENGTH,
    LiteralError,
    Literals,
    number_problem,
    text_constant_problem,
)
from tests.formula_helpers import standard_columns
from tests.formula_injection_cases import (
    BACKSLASH_CASES,
    INJECTION_CASES,
    SAFE_RENDER_CASES,
    formula_of,
)

APP_FORMULA = Path(__file__).resolve().parent.parent / "app" / "formula"
lit = Literals()


def render(expression) -> str:
    return render_literal_sql(sa.select(expression.label("v")))


# --- 형별 렌더 ----


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        (lit.number(Decimal("1.50")), "CAST(1.50 AS NUMERIC)"),
        (lit.number(10**30), "CAST(1000000000000000000000000000000 AS NUMERIC)"),
        (lit.number(-3), "CAST(-3 AS NUMERIC)"),
        (lit.number(Decimal("1E-7")), "CAST(1E-7 AS NUMERIC)"),
        (lit.text("O'Brien"), "CAST('O''Brien' AS TEXT)"),
        (lit.text("100%"), "CAST('100%' AS TEXT)"),
        (lit.text("한글"), "CAST('한글' AS TEXT)"),
        (lit.text(""), "CAST('' AS TEXT)"),
        (lit.boolean(True), "CAST(true AS BOOLEAN)"),
        (lit.boolean(False), "CAST(false AS BOOLEAN)"),
        (lit.date(date(2026, 2, 28)), "CAST('2026-02-28' AS DATE)"),
        (lit.integer(10), "CAST(10 AS INTEGER)"),
        (lit.smallint(1), "CAST(1 AS SMALLINT)"),
        (lit.code("E3"), "CAST(3 AS SMALLINT)"),
        (lit.null("number"), "CAST(NULL AS NUMERIC)"),
        (lit.null("text"), "CAST(NULL AS TEXT)"),
        (lit.null("date"), "CAST(NULL AS DATE)"),
        (lit.null("boolean"), "CAST(NULL AS BOOLEAN)"),
        (lit.null("smallint"), "CAST(NULL AS SMALLINT)"),
    ],
)
def test_every_constant_renders_as_a_typed_cast(expression, expected):
    assert render(expression) == f"SELECT {expected} AS v"


def test_percent_signs_reach_the_server_unchanged_with_the_production_dialect():
    """pg8000 방언은 글자 안의 `%`를 두 배로 만들지 않는다(X-26.1: 서버에 입력 그대로 도착)."""
    assert "'a%%b'" not in render(lit.text("a%b"))
    assert "'a%b'" in render(lit.text("a%b"))


def test_renderer_dialect_is_the_production_driver_by_default():
    expression = sa.select(lit.text("x").label("v"))
    assert render_literal_sql(expression) == render_literal_sql(
        expression, postgresql.pg8000.dialect()
    )


def test_the_same_expression_runs_as_bind_and_renders_as_literal():
    expression = sa.select(lit.number(Decimal("2.5")).label("v"))
    engine = sa.create_engine("sqlite://")
    with engine.connect() as connection:
        assert connection.execute(expression).scalar_one() == 2.5  # 바인드 실행
    engine.dispose()
    assert "CAST(2.5 AS NUMERIC)" in render_literal_sql(expression, sqlite.dialect())


# --- 거부 ----


@pytest.mark.parametrize(
    "value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity"), Decimal("sNaN")]
)
def test_non_finite_numbers_are_rejected(value):
    with pytest.raises(LiteralError):
        lit.number(value)
    assert number_problem(value)


@pytest.mark.parametrize("value", ["1", 1.5, None, True, float("nan")])
def test_numbers_must_be_decimal_or_int(value):
    with pytest.raises(LiteralError):
        lit.number(value)


def test_number_digit_limit():
    assert lit.number(Decimal("9" * MAX_NUMBER_DIGITS)) is not None
    with pytest.raises(LiteralError):
        lit.number(Decimal("9" * (MAX_NUMBER_DIGITS + 1)))
    with pytest.raises(LiteralError):
        lit.number(Decimal("1E+40"))
    with pytest.raises(LiteralError):
        lit.number(Decimal("1E-39"))


@pytest.mark.parametrize(
    "value",
    [
        "a\\b",
        "\x00",
        "a\nb",
        "a\tb",
        "a\rb",
        "\x7f",
        "\u200b",
        "\u202e",
        "\ufeff",
        "\u2028",
        "\u2029",
        "\ud800",
        "x" * (MAX_TEXT_CONSTANT_LENGTH + 1),
    ],
)
def test_text_constants_with_dangerous_or_invisible_characters_are_rejected(value):
    assert text_constant_problem(value)
    with pytest.raises(LiteralError):
        lit.text(value)


def test_text_must_be_nfc_and_a_string():
    nfd = unicodedata.normalize("NFD", "한글")
    with pytest.raises(LiteralError, match="NFC"):
        lit.text(nfd)
    assert lit.text(unicodedata.normalize("NFC", nfd)) is not None
    for bad in (1, None, b"x"):
        with pytest.raises(LiteralError):
            lit.text(bad)


def test_other_types_are_checked():
    with pytest.raises(LiteralError):
        lit.date(datetime(2026, 1, 1))  # datetime은 날짜가 아니다
    with pytest.raises(LiteralError):
        lit.boolean(1)
    with pytest.raises(LiteralError):
        lit.integer(True)
    with pytest.raises(LiteralError):
        lit.integer("1")
    with pytest.raises(LiteralError):
        lit.null("blob")


def test_text_constant_boundaries_accept_normal_punctuation():
    for value in [
        "O'Brien",
        'say "hi"',
        "100% $$ ; -- /* */",
        "a b\u00a0c",
        "x" * MAX_TEXT_CONSTANT_LENGTH,
        "😀",
    ]:
        assert text_constant_problem(value) is None, value


# --- render_literal_sql의 바인드 재검사 ----


def test_render_rejects_binds_that_did_not_come_from_the_renderer():
    for foreign in (sa.literal("x"), sa.literal(1), sa.bindparam("lit", "x"), sa.bindparam("p", 1)):
        statement = sa.select(foreign.label("v"))
        with pytest.raises(LiteralError):
            render_literal_sql(statement)


def test_render_rechecks_values_even_if_the_expression_was_altered_after_building():
    expression = lit.text("fine")
    statement = sa.select(expression.label("v"))
    names = [name for name in statement.compile().params]
    tampered = statement.params({names[0]: "x\\'; DELETE FROM t; --"})
    with pytest.raises(LiteralError, match="역슬래시"):
        render_literal_sql(tampered)
    number = sa.select(lit.number(1).label("v"))
    (name,) = number.compile().params
    with pytest.raises(LiteralError):
        render_literal_sql(number.params({name: Decimal("NaN")}))
    with pytest.raises(LiteralError):
        render_literal_sql(number.params({name: "1; DROP TABLE t"}))


def test_render_applies_to_every_dialect_the_same_way():
    statement = sa.select(lit.text("x").label("v"))
    assert "CAST('x' AS TEXT)" in render_literal_sql(statement, sqlite.dialect())


# --- X-26 주입 사례 10종 + 역슬래시 사례 ----


def _string_literal_body(sql: str) -> str:
    match = re.fullmatch(r"SELECT CAST\(('(?:[^']|'')*') AS TEXT\) AS v", sql)
    assert match, sql
    return match.group(1)[1:-1].replace("''", "'")


@pytest.mark.parametrize("name", list(SAFE_RENDER_CASES))
def test_injection_attempts_without_backslash_pass_c0_and_render_as_one_literal(name):
    text = SAFE_RENDER_CASES[name]
    result = compile_formula(formula_of(text), standard_columns())
    assert result.ok, result.issues
    rendered = render(result.value)
    assert _string_literal_body(rendered) == text  # 라운드트립: 글자 상수 하나가 입력 그대로
    outside = re.sub(r"'(?:[^']|'')*'", "''", rendered)
    assert ";" not in outside and "--" not in outside and "DROP" not in outside.upper()
    assert outside == "SELECT CAST('' AS TEXT) AS v"  # 리터럴 밖에는 고정 구조뿐


@pytest.mark.parametrize("name", list(BACKSLASH_CASES))
def test_backslash_inputs_are_rejected_by_c0_with_the_constant_position(name):
    text = BACKSLASH_CASES[name]
    expression = formula_of(text)
    result = compile_formula(expression, standard_columns())
    (issue,) = result.issues
    assert (issue.code, issue.start, issue.end) == ("TEXT_CONSTANT_INVALID", 0, len(expression))
    assert "역슬래시" in issue.message
    with pytest.raises(LiteralError):  # 완화책 ②는 렌더러 입력 검사에도 있다
        LITERALS.text(text)


def test_all_ten_injection_cases_and_six_backslash_cases_are_defined():
    assert list(INJECTION_CASES) == [f"P{i}" for i in range(1, 11)]
    assert len(BACKSLASH_CASES) == 6
    assert len(SAFE_RENDER_CASES) == 6
    assert len({*INJECTION_CASES.values()}) == 10


def test_tampered_stored_ast_with_backslash_is_rejected_at_compile_time():
    """저장소가 오염돼 역슬래시가 든 AST가 나와도 컴파일(C0)이 다시 거부한다."""
    from app.formula.nodes import Call, Text

    tainted = Call(name="&", args=(Text(value="a"), Text(value="b\\'; DROP TABLE t; --")))
    from app.formula import ColumnInfo

    column = ColumnInfo(1, "오염", "text", kind="formula", formula=tainted)
    result = compile_formula("[오염]", [column])
    assert [i.code for i in result.issues] == ["REF_FORMULA_INVALID"]


def test_non_nfc_text_in_stored_ast_is_normalized_before_rendering():
    from app.formula import ColumnInfo
    from app.formula.nodes import Text

    nfd = unicodedata.normalize("NFD", "한글")
    column = ColumnInfo(1, "비정규", "text", kind="formula", formula=Text(value=nfd))
    result = compile_formula("[비정규] & [비정규]", [column])
    assert result.ok
    assert unicodedata.normalize("NFC", nfd) in render(result.value)


# --- 코드 검사: 상수는 렌더러를 거친다 ----

_BANNED_ATTRIBUTES = {"literal", "bindparam", "literal_column", "text", "null", "true", "false",
                      "literal_binds", "exec_driver_sql"}  # fmt: skip
_SQLALCHEMY_NAMES = {"sa", "sqlalchemy"}


def _formula_sources():
    return sorted(p for p in APP_FORMULA.glob("*.py") if p.name != "literals.py")


def _direct_constant_constructions(tree: ast.AST) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in _BANNED_ATTRIBUTES:
            if isinstance(node.value, ast.Name) and node.value.id in _SQLALCHEMY_NAMES:
                found.append(f"{node.value.id}.{node.attr}")
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("sqlalchemy"):
            found += [
                f"from {node.module} import {a.name}"
                for a in node.names
                if a.name in _BANNED_ATTRIBUTES
            ]
        if isinstance(node, ast.Constant) and node.value in {"literal_binds"}:
            found.append("literal_binds")
        if isinstance(node, ast.Name) and node.id in {"exec_driver_sql", "literal_binds"}:
            found.append(node.id)
    return found


def test_formula_code_never_builds_constants_or_raw_sql_outside_the_renderer():
    sources = _formula_sources()
    assert {p.name for p in sources} >= {"functions.py", "convert.py", "analyze.py", "api.py"}
    for path in sources:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert _direct_constant_constructions(tree) == [], path.name


def test_detector_finds_forbidden_constructions():
    snippets = (
        "sa.literal(1)",
        "sa.text('x')",
        "sa.null()",
        "sa.true()",
        "sa.bindparam('a', 1)",
        "from sqlalchemy import literal",
        "sa.literal_column('1')",
        "{'literal_binds': True}",
    )
    for snippet in snippets:
        assert _direct_constant_constructions(ast.parse(snippet)), snippet
    assert not _direct_constant_constructions(ast.parse("lit.text('x'); ctx.lit.null('number')"))


def test_formula_modules_do_not_assemble_sql_strings():
    """변환·사전 코드에 문자열 조립으로 SQL을 만드는 흔적(`+`, `%`, `.format`)이 없다."""
    from tests.test_ddl import string_assembly_findings

    for name in ("convert.py", "literals.py"):
        tree = ast.parse((APP_FORMULA / name).read_text(encoding="utf-8"))
        findings = string_assembly_findings(tree, allow_fstrings=True)
        assert findings == [], (name, findings)


def test_the_renderer_is_the_only_place_that_renders_literals():
    source = (APP_FORMULA / "literals.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    constants = [
        n for n in ast.walk(tree) if isinstance(n, ast.Constant) and n.value == "literal_binds"
    ]
    assert len(constants) == 1
    assert (
        sum(1 for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "bindparam")
        == 1
    )
