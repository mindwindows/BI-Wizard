"""수식 보기 `text`(07 §9).

AST에서 현재 열 이름으로 풀어 쓴 글자다. 이름 변경에 깨지지 않고 다시 읽어도 같은 AST가 나온다.
"""

from decimal import Decimal

import pytest

from app.formula import (
    ColumnInfo,
    ast_from_json,
    compile_formula,
    get_default_registry,
    render_text,
)
from app.formula.cases import REJECT
from app.formula.nodes import Call, Col, Num, ast_to_json
from tests.formula_helpers import standard_columns
from tests.formula_runner import case_columns


def ast_of(expression, columns):
    result = compile_formula(expression, columns, build_sql=False)
    assert result.ok, [i.as_dict() for i in result.issues]
    return result.ast


@pytest.mark.parametrize(
    ("source", "canonical"),
    [
        ("(1+2)*3", "(1 + 2) * 3"),
        ("1+(2*3)", "1 + 2 * 3"),
        ("1-(2-3)", "1 - (2 - 3)"),
        ("(1-2)-3", "1 - 2 - 3"),
        ("8/(4/2)", "8 / (4 / 2)"),
        ("(8/4)/2", "8 / 4 / 2"),
        ("-(1+2)", "-(1 + 2)"),
        ("--1", "--1"),
        ("2--3", "2 - -3"),
        ("-2*3", "-2 * 3"),
        ("-(2*3)", "-(2 * 3)"),
        ("(1<2)=TRUE", "1 < 2 = TRUE"),
        ("1<(2=TRUE)", "1 < (2 = TRUE)"),
        ('("a"&"b")&"c"', '"a" & "b" & "c"'),
        ('"a"&("b"&"c")', '"a" & ("b" & "c")'),
        ("(1+2)&(3*4)", "1 + 2 & 3 * 4"),
        ("round( [매출] ,2)", "ROUND([매출], 2)"),
        ('IF(true,"a""b","c")', 'IF(TRUE, "a""b", "c")'),
        ("1.50 + .5 + 007", "1.50 + 0.5 + 7"),
        ("SUM([매출],[비용],-1)", "SUM([매출], [비용], -1)"),
        ("ABS((1+2))", "ABS(1 + 2)"),
        ("((([매출])))", "[매출]"),
        ("+4", "4"),
        ('SUMTAG("매출")', 'SUMTAG("매출")'),
    ],
)  # fmt: skip
def test_canonical_text(source, canonical):
    columns = [*standard_columns(), ColumnInfo(20, "x", "number", tag="매출")]
    ast = ast_of(source, columns) if "SUMTAG" in source or "[" in source else _parse_only(source)
    assert render_text(ast, columns) == canonical


def _parse_only(source):
    from app.formula import parse_expression

    return parse_expression(source)


def test_text_reads_back_to_the_same_ast_for_every_valid_case_expression():
    registry = get_default_registry()
    checked = 0
    for spec in registry.specs():
        for case in spec.cases:
            if case.expect == REJECT:
                continue
            columns = case_columns(case)
            ast = ast_of(case.expression, columns)
            text = render_text(ast, columns)
            again = ast_of(text, columns)
            assert again == ast, (case.expression, text)
            assert ast_to_json(again) == ast_to_json(ast)
            assert render_text(again, columns) == text  # 정규 형태는 고정점
            checked += 1
    assert checked > 150


def test_text_follows_column_renames_without_changing_the_stored_ast():
    before = standard_columns()
    ast = ast_of("[매출] - [비용]", before)
    stored = ast_to_json(ast)
    renamed = [
        ColumnInfo(c.id, "수입" if c.id == 1 else c.name, c.type, c.kind, c.tag, c.formula)
        for c in before
    ]
    assert render_text(ast, before) == "[매출] - [비용]"
    assert render_text(ast, renamed) == "[수입] - [비용]"
    assert ast_to_json(ast) == stored  # 저장된 AST는 열 번호라 그대로다
    # 저장된 JSON에서 복원한 AST(위치 없음)도 같은 글자를 만든다
    assert render_text(ast_from_json(stored), renamed) == "[수입] - [비용]"
    # 바뀐 이름으로 쓴 수식은 같은 AST다
    assert ast_of("[수입] - [비용]", renamed) == ast
    assert compile_formula("[매출] - [비용]", renamed).issues[0].code == "UNKNOWN_COLUMN"


def test_text_for_a_formula_that_references_another_formula_keeps_the_reference():
    base = standard_columns()
    profit = ColumnInfo(
        10, "이익", "number", kind="formula", formula=ast_of("[매출] - [비용]", base)
    )
    columns = [*base, profit]
    ast = ast_of("ROUND([이익] / [매출], 2)", columns)
    assert render_text(ast, columns) == "ROUND([이익] / [매출], 2)"  # 펼치지 않는다


def test_text_requires_known_columns_and_safe_names():
    ast = Call(name="+", args=(Col(column_id=99), Num(value=Decimal(1))))
    with pytest.raises(KeyError):
        render_text(ast, standard_columns())
    unsafe = [ColumnInfo(1, 'a"b', "number")]
    with pytest.raises(ValueError, match="제어 문자"):
        render_text(Col(column_id=1), unsafe)
    with pytest.raises(ValueError):
        render_text(Col(column_id=1), [ColumnInfo(1, "a]b", "number")])
    with pytest.raises(ValueError):
        render_text(Col(column_id=1), [ColumnInfo(1, "a\nb", "number")])


def test_unknown_operator_or_function_names_render_as_plain_calls():
    assert render_text(Call(name="MYFN", args=(Num(value=Decimal(1)),)), []) == "MYFN(1)"
