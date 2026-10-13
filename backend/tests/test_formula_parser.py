"""수식 파서(lark, 07 §1).

문법, 우선순위, 따옴표, 열 이름, 위치가 있는 오류, 상한을 확인한다. DB 없이 실행한다.
"""

import unicodedata
from decimal import Decimal

import pytest

from app.formula import FormulaError, parse_expression
from app.formula.nodes import (
    MAX_AST_DEPTH,
    Bool,
    Call,
    Col,
    ColName,
    Num,
    Text,
    ast_from_json,
    ast_hash,
    ast_to_json,
)
from app.formula.parser import MAX_EXPRESSION_LENGTH


def sexp(node) -> str:
    """AST를 짧은 글자로: 숫자 1, 글자 "x", 열 [이름], 호출 (이름 인수…)."""
    if isinstance(node, Num):
        return format(node.value, "f")
    if isinstance(node, Text):
        return '"' + node.value + '"'
    if isinstance(node, Bool):
        return "TRUE" if node.value else "FALSE"
    if isinstance(node, ColName):
        return f"[{node.name}]"
    if isinstance(node, Col):
        return f"#{node.column_id}"
    assert isinstance(node, Call)
    return "(" + " ".join([node.name, *map(sexp, node.args)]) + ")"


def parsed(text: str) -> str:
    return sexp(parse_expression(text))


def error_of(text: str):
    with pytest.raises(FormulaError) as info:
        parse_expression(text)
    assert len(info.value.issues) == 1
    return info.value.issues[0]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1 + 2 * 3", "(+ 1 (* 2 3))"),
        ("1 * 2 + 3", "(+ (* 1 2) 3)"),
        ("(1 + 2) * 3", "(* (+ 1 2) 3)"),
        ("1 - 2 - 3", "(- (- 1 2) 3)"),
        ("8 / 4 / 2", "(/ (/ 8 4) 2)"),
        ("-2 * 3", "(* (neg 2) 3)"),
        ("-(1 + 2)", "(neg (+ 1 2))"),
        ("--1", "(neg (neg 1))"),
        ("2 - -3", "(- 2 (neg 3))"),
        ("+4", "4"),
        ("+-4", "(neg 4)"),
        ("1 + 2 & 3", "(& (+ 1 2) 3)"),
        ('"a" & "b" & "c"', '(& (& "a" "b") "c")'),
        ("1 & 2 = 3", "(= (& 1 2) 3)"),
        ("1 < 2 = TRUE", "(= (< 1 2) TRUE)"),
        ("1 + 2 < 3 * 4", "(< (+ 1 2) (* 3 4))"),
        ("[a] <> [b]", "(<> [a] [b])"),
        ("1 <= 2", "(<= 1 2)"),
        ("1 >= 2", "(>= 1 2)"),
        ("1 > 2", "(> 1 2)"),
        ("1=1", "(= 1 1)"),
    ],
)
def test_precedence_and_associativity(text, expected):
    """비교 < & < + - < * / < 부호. 같은 단계는 왼쪽부터 묶는다."""
    assert parsed(text) == expected


def test_comparison_operators_are_split_correctly():
    assert parsed("1<2") == "(< 1 2)"
    assert parsed("1<>2") == "(<> 1 2)"
    assert parsed("1<=2") == "(<= 1 2)"
    assert parsed("1>=2") == "(>= 1 2)"


@pytest.mark.parametrize(
    ("text", "value"),
    [('"abc"', "abc"), ('""', ""), ('"a""b"', 'a"b'), ('""""', '"'), ('"""a"""', '"a"'),
     ('"가나다 라"', "가나다 라"), ('"O\'Brien"', "O'Brien"), ('"a;b--c"', "a;b--c")],
)  # fmt: skip
def test_string_literals_and_doubled_quotes(text, value):
    node = parse_expression(text)
    assert isinstance(node, Text)
    assert node.value == value


def test_string_constants_are_nfc_normalized_but_positions_are_of_the_original():
    nfd = unicodedata.normalize("NFD", "한글")
    assert len(nfd) > len("한글")
    node = parse_expression(f'"{nfd}" & "x"')
    assert isinstance(node, Call)
    assert node.args[0].value == "한글"  # NFC
    # 위치는 원문(정규화 전) 기준이다.
    assert (node.args[0].start, node.args[0].end) == (0, len(nfd) + 2)
    assert node.args[1].start == len(nfd) + 2 + len(" & ")


def test_numbers_keep_their_written_scale():
    assert parse_expression("1234.5") == Num(Decimal("1234.5"))
    assert parse_expression(".5") == Num(Decimal("0.5"))
    assert format(parse_expression("0.50").value, "f") == "0.50"
    assert format(parse_expression("007").value, "f") == "7"
    assert ast_to_json(parse_expression("1.50")) == {"t": "num", "v": "1.50"}


@pytest.mark.parametrize("text", ["1e5", "1.2.3", "1,5", "0x10", "12abc"])
def test_malformed_numbers_are_syntax_errors(text):
    assert error_of(text).code in {"UNEXPECTED_TOKEN", "BAD_CHARACTER"}


def test_booleans_are_case_insensitive_and_functions_are_uppercased():
    assert parsed("true") == "TRUE"
    assert parsed("False") == "FALSE"
    assert parsed("round(1, 2)") == "(ROUND 1 2)"
    assert parsed("If(TRUE, 1, 2)") == "(IF TRUE 1 2)"
    assert parsed("TRUE()") == "(TRUE)"  # 괄호가 있으면 함수 호출이다(사전이 거부한다)


@pytest.mark.parametrize(
    "name",
    [
        "매출",
        "Net Sales",
        "a b c",
        "  앞뒤 공백  ",
        "매 출(1)",
        "순이익%",
        "a.b",
        "100",
        "-",
        "한글 English 123",
    ],
)
def test_column_references_accept_spaces_hangul_and_symbols(name):
    node = parse_expression(f"[{name}] + 1")
    assert isinstance(node, Call)
    assert node.args[0] == ColName(name=name)


def test_column_names_are_nfc_normalized():
    nfd = unicodedata.normalize("NFD", "합계")
    node = parse_expression(f"[{nfd}]")
    assert isinstance(node, ColName)
    assert node.name == "합계"


def test_whitespace_and_newlines_are_ignored():
    assert parsed("  1 +\n\t2 ") == "(+ 1 2)"
    assert parsed("ROUND(\n1 ,\r\n 2 )") == "(ROUND 1 2)"


def test_function_calls():
    assert parsed("F()") == "(F)"
    assert parsed("F(1)") == "(F 1)"
    assert parsed("F(1, F(2, 3), [a])") == "(F 1 (F 2 3) [a])"
    assert parsed("((((1))))") == "1"


@pytest.mark.parametrize(
    ("text", "code", "start", "end"),
    [
        ("", "EMPTY", 0, 0),
        ("   ", "EMPTY", 0, 3),
        ("1 +", "UNEXPECTED_END", 3, 3),
        ("(1", "UNEXPECTED_END", 2, 2),
        ("F(1,", "UNEXPECTED_END", 4, 4),
        ("1 2", "UNEXPECTED_TOKEN", 2, 3),
        ("()", "UNEXPECTED_TOKEN", 1, 2),
        ("F(1,)", "UNEXPECTED_TOKEN", 4, 5),
        ("F(,1)", "UNEXPECTED_TOKEN", 2, 3),
        ("F(1 2)", "UNEXPECTED_TOKEN", 4, 5),
        ("1 + * 2", "UNEXPECTED_TOKEN", 4, 5),
        ("1 +) 2", "UNEXPECTED_TOKEN", 3, 4),
        ('"abc', "UNCLOSED_STRING", 0, 4),
        ('1 + "abc', "UNCLOSED_STRING", 4, 8),
        ("[a", "UNCLOSED_COLUMN", 0, 2),
        ("1 + [a b", "UNCLOSED_COLUMN", 4, 8),
        ("[a[b]]", "UNCLOSED_COLUMN", 0, 6),
        ("1]", "STRAY_BRACKET", 1, 2),
        ("=1+1", "LEADING_EQUALS", 0, 1),
        ("1 != 2", "NOT_EQUALS_SYNTAX", 2, 4),
        ("1 % 2", "BAD_CHARACTER", 2, 3),
        ("2 ^ 3", "BAD_CHARACTER", 2, 3),
        ("1 +\u3000 2", "BAD_CHARACTER", 3, 4),
        ("1 + $", "BAD_CHARACTER", 4, 5),
        ("매출", "BARE_NAME", 0, 2),
        ("TODAY", "BARE_NAME", 0, 5),
        ("1 + 매출", "BARE_NAME", 4, 6),
        ("NULL", "BARE_NAME", 0, 4),  # NULL 상수는 없다(빈 값은 열 값에서만 생긴다)
        ("1 + None", "BARE_NAME", 4, 8),
        ("1 +", "UNEXPECTED_END", 3, 3),
    ],
)
def test_syntax_errors_carry_code_and_position(text, code, start, end):
    issue = error_of(text)
    assert (issue.code, issue.start, issue.end) == (code, start, end)
    assert issue.message  # 쉬운 말 문구가 있다
    assert "SQL" not in issue.message


def test_error_messages_use_plain_language_and_name_the_problem():
    assert "닫는 괄호" in error_of("(1").message
    assert "<>" in error_of("1 != 2").message
    assert "[매출]" in error_of("매출").message
    assert "큰따옴표" in error_of('"abc').message
    assert "연산자" in error_of("1 2").message


def test_bad_character_message_shows_invisible_characters_as_code_points():
    assert "U+3000" in error_of("1 +\u3000 2").message


def test_length_limit():
    ok = "1" + "+1" * ((MAX_EXPRESSION_LENGTH - 1) // 2)
    assert len(ok) <= MAX_EXPRESSION_LENGTH
    # 항이 많은 덧셈은 왼쪽으로 깊게 묶이므로 깊이 상한(TOO_DEEP)이 먼저 막는다.
    assert error_of(ok).code == "TOO_DEEP"
    assert "SUM" in error_of(ok).message  # 대안 안내
    long_text = '"' + "가" * MAX_EXPRESSION_LENGTH + '"'
    issue = error_of(long_text)
    assert (issue.code, issue.start, issue.end) == ("TOO_LONG", 0, len(long_text))
    assert parse_expression('"' + "가" * 1990 + '"')  # 상한 안은 통과


def test_depth_limit_stops_deep_nesting_without_recursion_errors():
    deep_calls = "ABS(" * (MAX_AST_DEPTH + 1) + "1" + ")" * (MAX_AST_DEPTH + 1)
    assert error_of(deep_calls).code == "TOO_DEEP"
    ok_calls = "ABS(" * (MAX_AST_DEPTH - 1) + "1" + ")" * (MAX_AST_DEPTH - 1)
    assert parse_expression(ok_calls).depth == MAX_AST_DEPTH
    # 1,000단계 부호/괄호도 재귀 오류 없이 거부한다.
    assert error_of("-" * 1500 + "1").code == "TOO_DEEP"
    # 괄호는 AST 깊이를 늘리지 않는다(재귀 없이 파싱된다).
    assert parse_expression("(" * 900 + "1" + ")" * 900) == Num(Decimal(1))


def test_forty_term_sum_is_the_documented_limit_of_a_plus_chain():
    chain = " + ".join(["1"] * MAX_AST_DEPTH)  # 깊이 40
    assert parse_expression(chain).depth == MAX_AST_DEPTH
    assert error_of(" + ".join(["1"] * (MAX_AST_DEPTH + 1))).code == "TOO_DEEP"


def test_positions_of_nodes():
    node = parse_expression("ROUND([a] + 1, 2) * 3")
    assert isinstance(node, Call)
    assert (node.start, node.end) == (0, 21)
    round_call, three = node.args
    assert (round_call.start, round_call.end) == (0, 17)
    assert (three.start, three.end) == (20, 21)
    plus = round_call.args[0]
    assert (plus.start, plus.end) == (6, 13)


def test_ast_equality_ignores_positions_and_whitespace():
    assert parse_expression("1+2") == parse_expression("  1  +  2 ")
    assert parse_expression("(1+2)") == parse_expression("1+2")
    assert parse_expression("1+2") != parse_expression("2+1")


def test_json_roundtrip_and_hash():
    node = parse_expression('IF(TRUE, "a""b", -1.50)')
    restored = ast_from_json(ast_to_json(node))
    assert restored == node
    assert ast_hash(restored) == ast_hash(node)
    assert ast_hash(parse_expression("1+2")) != ast_hash(parse_expression("1+3"))
    assert len(ast_hash(node)) == 64


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        {"t": "weird"},
        {"t": "num", "v": 1},
        {"t": "num", "v": "NaN"},
        {"t": "num", "v": "Infinity"},
        {"t": "text", "v": 1},
        {"t": "bool", "v": "true"},
        {"t": "col", "id": 0},
        {"t": "col", "id": True},
        {"t": "col", "id": "1"},
        {"t": "call", "n": "IF", "a": "x"},
        {"t": "call", "a": []},
    ],
)
def test_ast_from_json_rejects_malformed_documents(data):
    with pytest.raises(ValueError):
        ast_from_json(data)


def test_ast_from_json_limits_depth():
    data = {"t": "num", "v": "1"}
    for _ in range(MAX_AST_DEPTH + 5):
        data = {"t": "call", "n": "ABS", "a": [data]}
    with pytest.raises(ValueError):
        ast_from_json(data)
