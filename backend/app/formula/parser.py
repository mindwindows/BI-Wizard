"""수식 글자 -> AST(07 §1 1단계). `lark`(MIT) LALR 문법으로 직접 작성했다(엑셀 수식 라이브러리
불사용).

문법 **[제안, 승인]**
- 열 `[열 이름]`(안에 `[` `]` `"` 불가), 글자 `"…"`(안의 `"`는 `""`), 숫자 `1234.5`·`.5`,
  `TRUE`/`FALSE`,
  함수 `NAME(…)`. 문법은 함수 이름을 모른다(사전이 해석한다). 날짜 상수와 `NULL` 상수는 없다.
  `%`·`^` 없음.
- 우선순위(낮음 -> 높음): 비교 `= <> < <= > >=` < `&` < `+ -` < `* /` < 부호(`+`는 버리고 `-`는
  `neg`).
  같은 단계는 왼쪽부터 묶는다.
- 공백·탭·줄바꿈은 무시한다. 함수 이름과 `TRUE`/`FALSE`는 대소문자를 구별하지 않는다(대문자로 저장).

위치(`start`·`end`)는 **입력 원문**의 코드포인트 번호다. 글자 상수와 열 이름은 파싱 뒤에 NFC로
정규화하므로
정규화가 위치를 옮기지 않는다. 오류는 `FormulaError`(쉬운 말 문구, 위치 포함)이며 문법 오류는 첫
건에서
멈춘다. 상한: 수식 2,000자, AST 깊이 `nodes.MAX_AST_DEPTH`.
"""

from __future__ import annotations

import unicodedata
from decimal import Decimal
from functools import lru_cache

from lark import Lark, Token, Transformer
from lark.exceptions import UnexpectedCharacters, UnexpectedEOF, UnexpectedInput, UnexpectedToken

from app.formula.errors import FormulaError, FormulaIssue, make_issue
from app.formula.nodes import NEG_NAME, Bool, ColName, Node, Num, Text, call

MAX_EXPRESSION_LENGTH = 2000  # 07 §4-2 [제안]

_GRAMMAR = r"""
?start: cmp
?cmp: cmp CMP concat -> binop
    | concat
?concat: concat AMP sum -> binop
    | sum
?sum: sum ADD product -> binop
    | sum SUB product -> binop
    | product
?product: product MUL unary -> binop
    | product DIV unary -> binop
    | unary
?unary: ADD unary -> pos
    | SUB unary -> neg
    | atom
?atom: NUMBER -> number
    | STRING -> string
    | COLREF -> colref
    | NAME LPAR [args] RPAR -> call
    | NAME -> name
    | LPAR cmp RPAR -> paren
args: cmp (COMMA cmp)*

CMP: "<>" | "<=" | ">=" | "=" | "<" | ">"
AMP: "&"
ADD: "+"
SUB: "-"
MUL: "*"
DIV: "/"
COMMA: ","
LPAR: "("
RPAR: ")"
NUMBER: /\d+(\.\d+)?|\.\d+/
STRING: /"(?:[^"]|"")*"/
COLREF: /\[[^\[\]"]*\]/
NAME: /[^\W\d][\w.]*/
%ignore /[ \t\r\n]+/
"""


class _Builder(Transformer):
    """파서가 규칙을 줄일 때마다 바로 AST를 만든다(재귀 없음)."""

    def binop(self, items):
        left, op, right = items
        return call(str(op), (left, right), start=left.start, end=right.end)

    def pos(self, items):
        return items[1]  # 단항 +는 버린다

    def neg(self, items):
        sign, operand = items
        return call(NEG_NAME, (operand,), start=sign.start_pos, end=operand.end)

    def number(self, items):
        token = items[0]
        return Num(value=Decimal(str(token)), start=token.start_pos, end=token.end_pos)

    def string(self, items):
        token = items[0]
        raw = str(token)[1:-1].replace('""', '"')
        return Text(
            value=unicodedata.normalize("NFC", raw), start=token.start_pos, end=token.end_pos
        )

    def colref(self, items):
        token = items[0]
        name = unicodedata.normalize("NFC", str(token)[1:-1])
        return ColName(name=name, start=token.start_pos, end=token.end_pos)

    def name(self, items):
        token = items[0]
        upper = str(token).upper()
        if upper in ("TRUE", "FALSE"):
            return Bool(value=upper == "TRUE", start=token.start_pos, end=token.end_pos)
        raise FormulaError(make_issue("BARE_NAME", token.start_pos, token.end_pos, name=str(token)))

    def paren(self, items):
        return items[1]

    def args(self, items):
        return [item for item in items if not isinstance(item, Token)]

    def call(self, items):
        name_token, _lpar, *rest = items
        close = rest[-1]
        args = rest[0] if len(rest) == 2 else []
        return call(
            str(name_token).upper(),
            tuple(args),
            start=name_token.start_pos,
            end=close.end_pos,
        )


@lru_cache(maxsize=1)
def _parser() -> Lark:
    return Lark(_GRAMMAR, parser="lalr", transformer=_Builder(), maybe_placeholders=False)


_TOKEN_NAMES_KO = {
    "RPAR": "닫는 괄호 )",
    "LPAR": "여는 괄호 (",
    "COMMA": "쉼표(,)",
    "CMP": "비교 기호",
    "AMP": "&",
    "ADD": "+",
    "SUB": "-",
    "MUL": "*",
    "DIV": "/",
    "NUMBER": "숫자",
    "STRING": "글자 상수",
    "COLREF": "열 이름",
    "NAME": "이름",
}
_VALUE_TOKENS = {"NUMBER", "STRING", "COLREF", "NAME", "LPAR"}


def _unexpected_token_hint(token_type: str) -> str:
    if token_type in _VALUE_TOKENS:
        return "값과 값 사이에는 연산자(+ - * / & 등)나 쉼표가 필요합니다."
    if token_type in ("RPAR", "COMMA"):
        return "괄호의 짝이나 빠진 값이 없는지 확인하세요."
    return "연산자 앞뒤에는 값이 있어야 합니다."


def _translate(error: UnexpectedInput, text: str) -> FormulaIssue:
    """lark 오류를 쉬운 말 문구와 위치로 바꾼다."""
    length = len(text)
    if isinstance(error, UnexpectedCharacters):
        pos = error.pos_in_stream if error.pos_in_stream is not None else 0
        char = text[pos]
        if char == '"':
            return make_issue("UNCLOSED_STRING", pos, length)
        if char == "[":
            return make_issue("UNCLOSED_COLUMN", pos, length)
        if char == "]":
            return make_issue("STRAY_BRACKET", pos, pos + 1)
        if char == "!" and text[pos + 1 : pos + 2] == "=":
            return make_issue("NOT_EQUALS_SYNTAX", pos, pos + 2)
        shown = repr(char) if char.isprintable() and not char.isspace() else f"U+{ord(char):04X}"
        return make_issue("BAD_CHARACTER", pos, pos + 1, char=shown)
    if isinstance(error, UnexpectedToken):
        token = error.token
        if token.type == "$END":
            return make_issue("UNEXPECTED_END", length, length)
        start = token.start_pos if token.start_pos is not None else 0
        end = token.end_pos if token.end_pos is not None else start + 1
        if token.type == "CMP" and text[:start].strip() == "" and str(token) == "=":
            return make_issue("LEADING_EQUALS", start, end)
        shown = _TOKEN_NAMES_KO.get(token.type, str(token))
        return make_issue(
            "UNEXPECTED_TOKEN", start, end, token=shown, hint=_unexpected_token_hint(token.type)
        )
    if isinstance(error, UnexpectedEOF):
        return make_issue("UNEXPECTED_END", length, length)
    return make_issue("UNEXPECTED_END", length, length)


def parse_expression(text: str) -> Node:
    """수식 글자를 AST로 바꾼다. 열은 아직 이름(`ColName`)이다. 실패하면 `FormulaError`."""
    if not isinstance(text, str):
        raise TypeError("수식은 글자여야 한다.")
    if len(text) > MAX_EXPRESSION_LENGTH:
        raise FormulaError(
            make_issue("TOO_LONG", 0, len(text), max=MAX_EXPRESSION_LENGTH, length=len(text))
        )
    if not text.strip():
        raise FormulaError(make_issue("EMPTY", 0, len(text)))
    try:
        tree = _parser().parse(text)
    except UnexpectedInput as exc:
        raise FormulaError(_translate(exc, text)) from None
    if not isinstance(tree, Node):  # 문법이 항상 노드를 돌려주므로 방어용
        raise FormulaError(make_issue("EMPTY", 0, len(text)))
    return tree
