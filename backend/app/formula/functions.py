"""FU-1 함수 사전의 항목들(07 §2-2). **함수 추가 = 이 파일에 `FunctionSpec` 한 개 + `cases`.**

식 만드는 규칙
- 상수와 NULL은 `ctx.lit`만 쓴다(`literal()`·`bindparam()`·`text()` 직접 호출 금지: 시험이
  검사한다).
- 모든 숫자 결과는 `NUMERIC`이다(`char_length` 같은 정수 결과는 `CAST(… AS NUMERIC)`).
- 빈 값 전파·오류 판정은 프레임워크(`convert.py`)가 감싼다. 항목은 "정상 입력의 값 식"과 "오류 조건
  식"만 쓴다.
- 오류 조건 식은 인수가 비어 있지 않을 때만 의미가 있다(빈 값이면 조건이 NULL이거나 프레임워크가
  먼저 거른다).
"""

from __future__ import annotations

import datetime
import functools
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.sql.elements import ColumnElement

from app.ddl.reference_lookup import reference_value_subquery
from app.formula.cases import Case, err, ok, reject
from app.formula.columns import ColumnInfo
from app.formula.context import Compiled, ConvertContext, ReferenceEnv
from app.formula.errors import FormulaError, FormulaIssue, make_issue
from app.formula.literals import BOOLEAN, DATE, NUMBER, TEXT, text_constant_problem
from app.formula.nodes import Call, Col, Node, Text, call
from app.formula.registry import (
    TYPE_VARIABLE,
    ConstRule,
    ErrorRule,
    FunctionRegistry,
    FunctionSpec,
    Param,
)

_N = {"a": "number"}
_NN = {"a": "number", "b": "number"}
_NNN = {"a": "number", "b": "number", "c": "number"}
_S = {"s": "text"}
_D = {"d": "date"}


def _num(name: str) -> Param:
    return Param(name, NUMBER)


def _t(name: str, allowed: frozenset[str] | None = None) -> Param:
    return Param(name, TYPE_VARIABLE, allowed=allowed)


def _values(args: Sequence[Compiled]) -> list[ColumnElement[Any]]:
    return [a.value for a in args]


# --- 산술 연산자 ----

ADD = FunctionSpec(
    name="+",
    kind="operator",
    symbol="+",
    syntax="infix",
    level=3,
    signature=(_num("수"), _num("수")),
    returns=NUMBER,
    null_policy="propagate",
    native_null=True,
    to_sql=lambda ctx, a: a[0].value + a[1].value,
    sqlite=True,
    excel_diff="빈 칸을 0으로 보지 않고 결과도 빈 값이 됩니다.",
    help_ko="두 숫자를 더합니다.",
    cases=(
        ok("1 + 2", 3),
        ok("1.5 + 2.25", "3.75"),
        ok("[a] + [b]", 5, cols=_NN, row={"a": 2, "b": 3}),
        ok("[a] + [b]", None, cols=_NN, row={"a": 2}, note="한쪽이 비면 결과도 빈 값"),
        ok("[a] + 1", None, cols=_N, row={}, note="열 값이 없음"),
        reject('1 + "a"', "ARG_TYPE"),
        reject("TRUE + 1", "ARG_TYPE"),
    ),
)

SUBTRACT = FunctionSpec(
    name="-",
    kind="operator",
    symbol="-",
    syntax="infix",
    level=3,
    signature=(_num("수"), _num("수")),
    returns=NUMBER,
    null_policy="propagate",
    native_null=True,
    to_sql=lambda ctx, a: a[0].value - a[1].value,
    sqlite=True,
    excel_diff="빈 칸을 0으로 보지 않고 결과도 빈 값이 됩니다.",
    help_ko="앞의 숫자에서 뒤의 숫자를 뺍니다.",
    cases=(
        ok("5 - 3", 2),
        ok("3 - 5", -2),
        ok("[a] - [b]", 1, cols=_NN, row={"a": 4, "b": 3}),
        ok("[a] - [b]", None, cols=_NN, row={"b": 3}),
        reject('"a" - 1', "ARG_TYPE"),
    ),
)

MULTIPLY = FunctionSpec(
    name="*",
    kind="operator",
    symbol="*",
    syntax="infix",
    level=4,
    signature=(_num("수"), _num("수")),
    returns=NUMBER,
    null_policy="propagate",
    native_null=True,
    to_sql=lambda ctx, a: a[0].value * a[1].value,
    sqlite=True,
    excel_diff="빈 칸을 0으로 보지 않고 결과도 빈 값이 됩니다.",
    help_ko="두 숫자를 곱합니다.",
    cases=(
        ok("2 * 3", 6),
        ok("0.5 * 4", 2),
        ok("[a] * [b]", 12, cols=_NN, row={"a": 3, "b": 4}),
        ok("[a] * [b]", None, cols=_NN, row={"a": 3}),
        reject('2 * "3"', "ARG_TYPE"),
    ),
)


def _divisor_is_zero(ctx: ConvertContext, a: Sequence[Compiled]) -> ColumnElement[Any]:
    return a[1].value == ctx.lit.number(0)


DIVIDE = FunctionSpec(
    name="/",
    kind="operator",
    symbol="/",
    syntax="infix",
    level=4,
    signature=(_num("수"), _num("수")),
    returns=NUMBER,
    null_policy="propagate",
    native_null=True,
    error_when=(ErrorRule("E1", _divisor_is_zero),),
    self_guarded=True,
    to_sql=lambda ctx, a: (
        a[0].value / sa.func.nullif(a[1].value, ctx.lit.number(0), type_=sa.Numeric())
    ),
    excel_diff="엑셀은 0으로 나누면 #DIV/0!가 되고, 여기서는 오류 칸(빈 값 + 점검 표시)이 됩니다.",
    help_ko="앞의 숫자를 뒤의 숫자로 나눕니다. 0으로 나누면 오류 칸이 됩니다"
    "(IFERROR로 대체값을 줄 수 있습니다).",
    cases=(
        ok("10 / 4", "2.5"),
        ok("[a] / [b]", "2.5", cols=_NN, row={"a": 10, "b": 4}),
        ok(
            "[a] / [b]",
            None,
            cols=_NN,
            row={"a": 10},
            note="나누는 수가 비면 결과도 빈 값(오류 아님)",
        ),
        ok("[a] / [b]", None, cols=_NN, row={"b": 0}, note="인수 빈 값이 자기 조건보다 먼저"),
        err("[a] / [b]", "E1", cols=_NN, row={"a": 1, "b": 0}),
        err("[a] / ([b] - [c])", "E1", cols=_NNN, row={"a": 1, "b": 2, "c": 2}),
        reject("1 / 0", "CONSTANT_ERROR", note="상수 부분식 오류는 C0가 거부"),
        reject("0 / 0", "CONSTANT_ERROR"),
        reject("5 / (3 - 3)", "CONSTANT_ERROR"),
        reject('1 / "a"', "ARG_TYPE"),
    ),
)

NEGATE = FunctionSpec(
    name="neg",
    kind="operator",
    symbol="-",
    syntax="prefix",
    level=5,
    signature=(_num("수"),),
    returns=NUMBER,
    null_policy="propagate",
    native_null=True,
    to_sql=lambda ctx, a: -a[0].value,
    sqlite=True,
    excel_diff="같음",
    help_ko="숫자의 부호를 바꿉니다(-5). 앞에 붙은 +는 아무 일도 하지 않습니다.",
    cases=(
        ok("-5", -5),
        ok("--3", 3),
        ok("-[a]", -2, cols=_N, row={"a": 2}),
        ok("-[a]", None, cols=_N, row={}),
        ok("+4", 4),
        reject('-"a"', "ARG_TYPE"),
    ),
)


# --- 비교 ----


def _compare_equal(ctx: ConvertContext, a: Sequence[Compiled]) -> ColumnElement[Any]:
    if a[0].type == TEXT:
        return sa.func.lower(a[0].value) == sa.func.lower(a[1].value)
    return a[0].value == a[1].value


def _compare_not_equal(ctx: ConvertContext, a: Sequence[Compiled]) -> ColumnElement[Any]:
    if a[0].type == TEXT:
        return sa.func.lower(a[0].value) != sa.func.lower(a[1].value)
    return a[0].value != a[1].value


EQUAL = FunctionSpec(
    name="=",
    kind="operator",
    symbol="=",
    syntax="infix",
    level=1,
    signature=(_t("값"), _t("값")),
    returns=BOOLEAN,
    null_policy="propagate",
    native_null=True,
    to_sql=_compare_equal,
    sqlite=True,
    excel_diff="글자는 대문자·소문자를 구별하지 않습니다. 빈 칸과 비교하면 결과가 빈 값이 됩니다.",
    help_ko="두 값이 같으면 참입니다. 숫자·글자·날짜·참/거짓 중 같은 종류끼리만 비교합니다.",
    cases=(
        ok("1 = 1.0", True),
        ok("1 = 2", False),
        ok('"ABC" = "abc"', True, note="글자 비교는 대소문자 무시"),
        ok('"가" = "나"', False),
        ok("TRUE = FALSE", False),
        ok("[a] = [b]", True, cols=_NN, row={"a": 3, "b": 3}),
        ok("[a] = [b]", None, cols=_NN, row={"a": 3}),
        ok("[s] = [s]", None, cols=_S, row={}),
        reject('1 = "1"', "TYPE_MISMATCH", note="숫자와 글자는 자동 변환 없음"),
        reject('DATE(2026, 1, 1) = "2026-01-01"', "TYPE_MISMATCH", note="날짜-글자 직접 비교 거부"),
    ),
)

NOT_EQUAL = FunctionSpec(
    name="<>",
    kind="operator",
    symbol="<>",
    syntax="infix",
    level=1,
    signature=(_t("값"), _t("값")),
    returns=BOOLEAN,
    null_policy="propagate",
    native_null=True,
    to_sql=_compare_not_equal,
    sqlite=True,
    excel_diff="글자는 대문자·소문자를 구별하지 않습니다. 빈 칸과 비교하면 결과가 빈 값이 됩니다.",
    help_ko="두 값이 다르면 참입니다.",
    cases=(
        ok("1 <> 2", True),
        ok('"ABC" <> "abc"', False),
        ok("[a] <> [b]", True, cols=_NN, row={"a": 1, "b": 2}),
        ok("[a] <> [b]", None, cols=_NN, row={"b": 2}),
        reject('1 <> "a"', "TYPE_MISMATCH"),
    ),
)

_ORDERED = frozenset({NUMBER, DATE})


def _ordered(name: str, symbol: str, operation: Any, word: str) -> FunctionSpec:
    return FunctionSpec(
        name=name,
        kind="operator",
        symbol=symbol,
        syntax="infix",
        level=1,
        signature=(_t("값", _ORDERED), _t("값", _ORDERED)),
        returns=BOOLEAN,
        null_policy="propagate",
        native_null=True,
        to_sql=lambda ctx, a: operation(a[0].value, a[1].value),
        sqlite=True,
        excel_diff="글자의 크기 비교는 지원하지 않습니다(DB 정렬 규칙에 따라 달라지기 때문입니다).",
        help_ko=f"앞의 값이 뒤의 값보다 {word} 참입니다. 숫자끼리 또는 날짜끼리만 비교합니다.",
        cases=(
            ok(f"1 {symbol} 2", operation(1, 2)),
            ok(f"2 {symbol} 2", operation(2, 2)),
            ok(f"3 {symbol} 2", operation(3, 2)),
            ok(f"[a] {symbol} [b]", operation(5, 7), cols=_NN, row={"a": 5, "b": 7}),
            ok(f"[a] {symbol} [b]", None, cols=_NN, row={"a": 5}),
            ok(
                f"[d] {symbol} [e]",
                operation(1, 2),
                cols={"d": "date", "e": "date"},
                row={"d": datetime.date(2026, 1, 1), "e": datetime.date(2026, 1, 2)},
            ),
            reject(f'"a" {symbol} "b"', "ARG_TYPE", note="글자 크기 비교는 FU-1 제외"),
            reject(f"1 {symbol} TRUE", "ARG_TYPE"),
        ),
    )


LESS = _ordered("<", "<", lambda x, y: x < y, "작으면")
LESS_EQUAL = _ordered("<=", "<=", lambda x, y: x <= y, "작거나 같으면")
GREATER = _ordered(">", ">", lambda x, y: x > y, "크면")
GREATER_EQUAL = _ordered(">=", ">=", lambda x, y: x >= y, "크거나 같으면")


# --- 글자 이어 붙이기 ----

CONCAT = FunctionSpec(
    name="&",
    kind="operator",
    symbol="&",
    syntax="infix",
    level=2,
    signature=(Param("글자", TEXT), Param("글자", TEXT)),
    returns=TEXT,
    null_policy="propagate",
    native_null=True,
    to_sql=lambda ctx, a: a[0].value.concat(a[1].value),
    sqlite=True,
    excel_diff="숫자를 글자로 자동 변환하지 않습니다(글자끼리만 이어 붙입니다). "
    "빈 칸이 있으면 결과도 빈 값입니다.",
    help_ko="두 글자를 이어 붙입니다.",
    cases=(
        ok('"가" & "나"', "가나"),
        ok('"a" & "" & "b"', "ab"),
        ok("[s] & [s]", "xx", cols=_S, row={"s": "x"}),
        ok('[s] & "x"', None, cols=_S, row={}),
        reject('"a" & 1', "ARG_TYPE", note="숫자를 글자로 자동 변환하지 않음"),
    ),
)


# --- 조건·논리 ----


def _if(ctx: ConvertContext, a: Sequence[Compiled]) -> Compiled:
    condition, when_true, when_false = a
    lit = ctx.lit
    value = sa.case(
        (lit.boolean(True), when_true.value),
        (lit.boolean(False), when_false.value),
        value=condition.value,
    )  # 조건이 비면 어느 갈래도 맞지 않아 NULL
    error = None
    if when_true.error is not None or when_false.error is not None:
        chosen_error = sa.case(
            (
                lit.boolean(True),
                when_true.error if when_true.error is not None else ctx.null("smallint"),
            ),
            (
                lit.boolean(False),
                when_false.error if when_false.error is not None else ctx.null("smallint"),
            ),
            value=condition.value,
        )
        error = chosen_error
    if condition.error is not None:
        error = condition.error if error is None else sa.func.coalesce(condition.error, error)
    return Compiled(value, error, when_true.type)


IF = FunctionSpec(
    name="IF",
    signature=(Param("조건", BOOLEAN), _t("참일 때"), _t("거짓일 때")),
    returns=TYPE_VARIABLE,
    null_policy="custom",
    to_sql_custom=_if,
    sqlite=True,
    excel_diff="조건이 빈 값이면 결과도 빈 값입니다(엑셀은 빈 조건을 거짓으로 봅니다). "
    "고른 쪽의 오류만 반영됩니다.",
    help_ko="IF(조건, 참일 때, 거짓일 때): 조건이 참이면 두 번째, 거짓이면 세 번째 값을 씁니다. "
    "두 값은 같은 종류여야 합니다.",
    cases=(
        ok("IF(TRUE, 1, 2)", 1),
        ok("IF(FALSE, 1, 2)", 2),
        ok('IF([a] > 0, "양수", "아님")', "양수", cols=_N, row={"a": 5}),
        ok('IF([a] > 0, "양수", "아님")', "아님", cols=_N, row={"a": -5}),
        ok("IF([c], 1, 2)", None, cols={"c": "boolean"}, row={}, note="조건이 비면 결과도 빈 값"),
        ok("IF([b] = 0, 0, [a] / [b])", 0, cols=_NN, row={"a": 1, "b": 0}, note="고른 쪽만 평가"),
        ok("IF([b] = 0, 0, [a] / [b])", "5", cols=_NN, row={"a": 10, "b": 2}),
        err(
            "IF([b] > 0, 1, [a] / [b])", "E1", cols=_NN, row={"a": 1, "b": 0}, note="고른 쪽의 오류"
        ),
        ok("IF([b] > 0, 1, [a] / [b])", 1, cols=_NN, row={"a": 1, "b": 3}),
        reject("IF(1, 2, 3)", "ARG_TYPE"),
        reject('IF(TRUE, 1, "a")', "TYPE_MISMATCH"),
    ),
)


def _all_true(ctx: ConvertContext, a: Sequence[Compiled]) -> ColumnElement[Any]:
    return sa.and_(*_values(a))


def _any_true(ctx: ConvertContext, a: Sequence[Compiled]) -> ColumnElement[Any]:
    return sa.or_(*_values(a))


_BOOL_COLS = {"p": "boolean", "q": "boolean"}

AND = FunctionSpec(
    name="AND",
    signature=(Param("조건", BOOLEAN), Param("조건", BOOLEAN), Param("조건", BOOLEAN, repeat=True)),
    returns=BOOLEAN,
    null_policy="propagate",
    to_sql=_all_true,
    sqlite=True,
    excel_diff="하나라도 빈 값이면 결과도 빈 값입니다(엑셀은 빈 칸을 무시합니다).",
    help_ko="모든 조건이 참이면 참입니다. 조건은 2개 이상 쓸 수 있습니다.",
    cases=(
        ok("AND(TRUE, TRUE)", True),
        ok("AND(TRUE, FALSE)", False),
        ok("AND([a] > 0, [b] > 0, [c] > 0)", True, cols=_NNN, row={"a": 1, "b": 1, "c": 1}),
        ok(
            "AND([p], [q])",
            None,
            cols=_BOOL_COLS,
            row={"q": False},
            note="하나가 비면 거짓이 있어도 빈 값",
        ),
        reject("AND(TRUE)", "ARG_COUNT"),
        reject("AND(1, TRUE)", "ARG_TYPE"),
    ),
)

OR = FunctionSpec(
    name="OR",
    signature=(Param("조건", BOOLEAN), Param("조건", BOOLEAN), Param("조건", BOOLEAN, repeat=True)),
    returns=BOOLEAN,
    null_policy="propagate",
    to_sql=_any_true,
    sqlite=True,
    excel_diff="하나라도 빈 값이면 결과도 빈 값입니다(엑셀은 빈 칸을 무시합니다).",
    help_ko="조건 중 하나라도 참이면 참입니다. 조건은 2개 이상 쓸 수 있습니다.",
    cases=(
        ok("OR(FALSE, TRUE)", True),
        ok("OR(FALSE, FALSE, FALSE)", False),
        ok(
            "OR([p], [q])",
            None,
            cols=_BOOL_COLS,
            row={"q": True},
            note="하나가 비면 참이 있어도 빈 값",
        ),
        reject("OR(TRUE)", "ARG_COUNT"),
        reject('OR("a", TRUE)', "ARG_TYPE"),
    ),
)

NOT = FunctionSpec(
    name="NOT",
    signature=(Param("조건", BOOLEAN),),
    returns=BOOLEAN,
    null_policy="propagate",
    native_null=True,
    to_sql=lambda ctx, a: sa.not_(a[0].value),
    sqlite=True,
    excel_diff="같음(빈 값이면 결과도 빈 값).",
    help_ko="참이면 거짓, 거짓이면 참으로 바꿉니다.",
    cases=(
        ok("NOT(TRUE)", False),
        ok("NOT(1 > 2)", True),
        ok("NOT([p])", None, cols=_BOOL_COLS, row={}),
        reject("NOT(1)", "ARG_TYPE"),
        reject("NOT(TRUE, FALSE)", "ARG_COUNT"),
    ),
)


def _iferror(ctx: ConvertContext, a: Sequence[Compiled]) -> Compiled:
    primary, fallback = a
    if primary.error is None:  # 오류가 날 수 없으면 대체값은 쓰일 일이 없다
        return Compiled(primary.value, None, primary.type)
    failed = primary.error.is_not(None)
    value = sa.case((failed, fallback.value), else_=primary.value)
    error = sa.case((failed, fallback.error)) if fallback.error is not None else None
    return Compiled(value, error, primary.type)


IFERROR = FunctionSpec(
    name="IFERROR",
    signature=(_t("값"), _t("대체값")),
    returns=TYPE_VARIABLE,
    null_policy="custom",
    to_sql_custom=_iferror,
    sqlite=True,
    excel_diff="오류 칸일 때만 대체값을 씁니다. 빈 값은 오류가 아니므로 그대로 빈 값입니다.",
    help_ko="IFERROR(값, 대체값): 값이 오류 칸(예: 0으로 나눔)이면 대체값을, "
    "아니면 값을 그대로 씁니다.",
    cases=(
        ok("IFERROR(10, 0)", 10),
        ok("IFERROR([a] / [b], 0)", 0, cols=_NN, row={"a": 1, "b": 0}),
        ok("IFERROR([a] / [b], 0)", "2", cols=_NN, row={"a": 4, "b": 2}),
        ok(
            "IFERROR([a] / [b], 0)",
            None,
            cols=_NN,
            row={"b": 0},
            note="빈 값은 오류가 아니라 그대로",
        ),
        err(
            "IFERROR([a] / [b], [a] / [c])",
            "E1",
            cols=_NNN,
            row={"a": 1, "b": 0, "c": 0},
            note="대체값의 오류는 그대로 반영",
        ),
        reject("IFERROR(1 / 0, 0)", "CONSTANT_ERROR"),
        reject('IFERROR(1, "a")', "TYPE_MISMATCH"),
    ),
)


# --- 반올림·절댓값 ----

_DIGITS = ConstRule("integer", -10, 10)
_ROUND_CASES_COLS = {"a": "number"}


def _digits(args: Sequence[Compiled]) -> int:
    return int(args[1].const)


def _round(ctx: ConvertContext, a: Sequence[Compiled]) -> ColumnElement[Any]:
    return sa.func.round(a[0].value, ctx.lit.integer(_digits(a)))


def _round_down(ctx: ConvertContext, a: Sequence[Compiled]) -> ColumnElement[Any]:
    return sa.func.trunc(a[0].value, ctx.lit.integer(_digits(a)))


def _round_up(ctx: ConvertContext, a: Sequence[Compiled]) -> ColumnElement[Any]:
    # 나눗셈은 PostgreSQL이 몫을 유효숫자 약 16자리까지만 계산해 큰 값에서 틀릴 수 있다(07 §10-1,
    # reviewer M3). 그래서 곱셈만 쓴다: ceil(|x| * 10^n) * 10^-n. 두 상수(10^n, 10^-n)는 `Decimal`로
    # 정확히 표현되고 numeric 곱셈은 정확하며, 결과의 소수 자릿수는 n(n < 0이면 0)이다.
    n = _digits(a)
    up = ctx.lit.number(Decimal(10) ** n)
    down = ctx.lit.number(Decimal(10) ** -n)
    x = a[0].value
    return sa.func.sign(x) * (sa.func.ceil(sa.func.abs(x) * up) * down)


def _rounding(
    name: str, to_sql: Any, help_text: str, diff: str, cases: tuple[Case, ...]
) -> FunctionSpec:
    return FunctionSpec(
        name=name,
        signature=(_num("수"), Param("자릿수", NUMBER, const=_DIGITS)),
        returns=NUMBER,
        null_policy="propagate",
        native_null=True,
        to_sql=to_sql,
        excel_diff=diff,
        help_ko=help_text,
        cases=(
            *cases,
            ok(f"{name}([a], 1)", None, cols=_N, row={}),
            reject(f"{name}(1.5, [a])", "CONST_REQUIRED", cols=_N, note="자릿수는 직접 쓴 수만"),
            reject(f"{name}(1.5, 11)", "CONST_RANGE"),
            reject(f"{name}(1.5, -11)", "CONST_RANGE"),
            reject(f"{name}(1.5, 0.5)", "CONST_RANGE", note="자릿수는 정수"),
            reject(f'{name}("a", 0)', "ARG_TYPE"),
        ),
    )


ROUND = _rounding(
    "ROUND",
    _round,
    "ROUND(수, 자릿수): 지정한 소수 자릿수에서 반올림합니다(0.5는 0에서 먼 쪽으로). "
    "자릿수는 -10~10 사이의 직접 쓴 정수입니다.",
    "자릿수는 숫자를 직접 써야 합니다(열·계산식 불가). 반올림은 0에서 먼 쪽입니다.",
    (
        ok("ROUND(2.5, 0)", 3),
        ok("ROUND(-2.5, 0)", -3),
        ok("ROUND(1.005, 2)", "1.01"),
        ok("ROUND(1234.567, -2)", 1200),
        ok("ROUND([a], 1)", "2.3", cols=_N, row={"a": "2.25"}),
        ok(
            "ROUND(123456789012.1234567895, 9)",
            "123456789012.123456790",
            note="정수부 12자리 + 소수 10자리, 0.5는 0에서 먼 쪽",
        ),
        ok("ROUND(-123456789012.1234567895, 9)", "-123456789012.123456790"),
    ),
)
ROUNDUP = _rounding(
    "ROUNDUP",
    _round_up,
    "ROUNDUP(수, 자릿수): 지정한 소수 자릿수까지 0에서 먼 쪽으로 올립니다.",
    "자릿수는 숫자를 직접 써야 합니다. 0에서 먼 쪽으로 올림합니다(엑셀과 같음).",
    (
        ok("ROUNDUP(2.1, 0)", 3),
        ok("ROUNDUP(-2.1, 0)", -3),
        ok("ROUNDUP(1.001, 2)", "1.01"),
        ok("ROUNDUP(1.00, 2)", "1.00"),
        ok("ROUNDUP(1201, -2)", 1300),
        ok("ROUNDUP([a], 0)", 3, cols=_N, row={"a": "2.01"}),
        ok(
            "ROUNDUP(123456789012.1234567890, 10)",
            "123456789012.1234567890",
            note="이미 그 자릿수면 그대로(나눗셈을 쓰면 긴 소수에서 틀렸다)",
        ),
        ok("ROUNDUP(123456789012.1234567891, 10)", "123456789012.1234567891"),
        ok("ROUNDUP(123456789012.1234567891, 9)", "123456789012.123456790"),
        ok("ROUNDUP(-1234567890123456789012.123456789012345, 2)", "-1234567890123456789012.13"),
        ok("ROUNDUP(99999999999999999999.9999999999, 10)", "99999999999999999999.9999999999"),
    ),
)
ROUNDDOWN = _rounding(
    "ROUNDDOWN",
    _round_down,
    "ROUNDDOWN(수, 자릿수): 지정한 소수 자릿수 아래를 0 쪽으로 버립니다.",
    "자릿수는 숫자를 직접 써야 합니다. 0 쪽으로 버림합니다(엑셀과 같음).",
    (
        ok("ROUNDDOWN(2.9, 0)", 2),
        ok("ROUNDDOWN(-2.9, 0)", -2),
        ok("ROUNDDOWN(1.999, 2)", "1.99"),
        ok("ROUNDDOWN(1299, -2)", 1200),
        ok("ROUNDDOWN([a], 0)", 2, cols=_N, row={"a": "2.99"}),
        ok("ROUNDDOWN(-123456789012.1234567895, 9)", "-123456789012.123456789"),
        ok("ROUNDDOWN(1234567890123456789012.123456789012345, 2)", "1234567890123456789012.12"),
    ),
)

ABS = FunctionSpec(
    name="ABS",
    signature=(_num("수"),),
    returns=NUMBER,
    null_policy="propagate",
    native_null=True,
    to_sql=lambda ctx, a: sa.func.abs(a[0].value),
    sqlite=True,
    excel_diff="같음",
    help_ko="숫자의 절댓값(부호를 뗀 값)입니다.",
    cases=(
        ok("ABS(-3)", 3),
        ok("ABS(3.5)", "3.5"),
        ok("ABS([a])", 2, cols=_N, row={"a": -2}),
        ok("ABS([a])", None, cols=_N, row={}),
        reject('ABS("a")', "ARG_TYPE"),
        reject("ABS(1, 2)", "ARG_COUNT"),
    ),
)


# --- MIN MAX SUM ----

MIN = FunctionSpec(
    name="MIN",
    signature=(_num("수"), _num("수"), Param("수", NUMBER, repeat=True)),
    returns=NUMBER,
    null_policy="propagate",
    to_sql=lambda ctx, a: sa.func.least(*_values(a)),
    excel_diff="하나라도 빈 값이면 결과도 빈 값입니다(엑셀은 빈 칸을 건너뜁니다). "
    "2개 이상 필요합니다.",
    help_ko="숫자 중 가장 작은 값입니다. 숫자는 2개 이상 쓰며, "
    "하나라도 비어 있으면 결과도 빈 값입니다.",
    cases=(
        ok("MIN(3, 1, 2)", 1),
        ok("MIN(-1, 5)", -1),
        ok("MIN([a], [b], [c])", 1, cols=_NNN, row={"a": 3, "b": 1, "c": 2}),
        ok("MIN([a], [b])", None, cols=_NN, row={"a": 1}, note="빈 칸을 건너뛰지 않음"),
        reject("MIN(1)", "ARG_COUNT"),
        reject('MIN(1, "a")', "ARG_TYPE"),
    ),
)

MAX = FunctionSpec(
    name="MAX",
    signature=(_num("수"), _num("수"), Param("수", NUMBER, repeat=True)),
    returns=NUMBER,
    null_policy="propagate",
    to_sql=lambda ctx, a: sa.func.greatest(*_values(a)),
    excel_diff="하나라도 빈 값이면 결과도 빈 값입니다(엑셀은 빈 칸을 건너뜁니다). "
    "2개 이상 필요합니다.",
    help_ko="숫자 중 가장 큰 값입니다. 숫자는 2개 이상 쓰며, "
    "하나라도 비어 있으면 결과도 빈 값입니다.",
    cases=(
        ok("MAX(3, 1, 2)", 3),
        ok("MAX(-1, -5)", -1),
        ok("MAX([a], [b], [c])", 3, cols=_NNN, row={"a": 3, "b": 1, "c": 2}),
        ok("MAX([a], [b])", None, cols=_NN, row={"b": 1}, note="빈 칸을 건너뛰지 않음"),
        reject("MAX(1)", "ARG_COUNT"),
        reject('MAX(1, "a")', "ARG_TYPE"),
    ),
)

SUM = FunctionSpec(
    name="SUM",
    signature=(_num("수"), Param("수", NUMBER, repeat=True)),
    returns=NUMBER,
    null_policy="propagate",
    native_null=True,
    to_sql=lambda ctx, a: functools.reduce(lambda x, y: x + y, _values(a)),
    sqlite=True,
    excel_diff="하나라도 빈 값이면 결과도 빈 값입니다(엑셀은 빈 칸을 건너뜁니다).",
    help_ko="숫자를 모두 더합니다. 하나라도 비어 있으면 결과도 빈 값입니다.",
    cases=(
        ok("SUM(1, 2, 3)", 6),
        ok("SUM(5)", 5),
        ok("SUM([a], [b], [c])", 6, cols=_NNN, row={"a": 1, "b": 2, "c": 3}),
        ok(
            "SUM([a], [b], [c])",
            None,
            cols=_NNN,
            row={"a": 1, "c": 3},
            note="빈 칸을 건너뛰지 않음",
        ),
        reject("SUM()", "ARG_COUNT"),
        reject('SUM(1, "a")', "ARG_TYPE"),
    ),
)


_MAX_TAG_LENGTH = 50  # 06 §3-3: 열 태그 길이 상한


def _rewrite_sumtag(node: Call, columns_with_tag: Any) -> Node:
    """`SUMTAG("태그")`를 같은 태그 숫자 열 전부의 `SUM(…)`으로 바꿔 쓴다.

    열은 번호 순이고, 나중에 생긴 열도 자동으로 포함된다.
    """
    if len(node.args) != 1 or not isinstance(node.args[0], Text):
        return node  # 인수 오류는 일반 형 검사가 알려 준다
    if len(node.args[0].value) > _MAX_TAG_LENGTH:
        return node  # 태그 길이 상한 위반은 상수 규칙(CONST_RANGE)이 알려 준다
    tag = node.args[0].value
    columns = columns_with_tag(tag)
    if not columns:
        raise FormulaError(make_issue("TAG_EMPTY", node.start, node.end, tag=tag))
    refs = tuple(Col(column_id=c.id, start=node.start, end=node.end) for c in columns)
    return call("SUM", refs, start=node.start, end=node.end)


_TAGGED = {"a": "number", "b": "number", "c": "number"}
_TAGS = {"a": "매출", "b": "매출", "c": "비용"}

SUMTAG = FunctionSpec(
    name="SUMTAG",
    signature=(Param("태그", TEXT, const=ConstRule("text", max_length=_MAX_TAG_LENGTH)),),
    returns=NUMBER,
    null_policy="propagate",
    rewrite=_rewrite_sumtag,
    sqlite=True,
    excel_diff="엑셀에는 없는 이름입니다. 같은 태그가 붙은 숫자 열을 모두 더하며(SUMIF 대응), "
    "새 열도 자동으로 포함됩니다.",
    help_ko=(
        'SUMTAG("태그"): 같은 데이터셋에서 그 태그가 붙은 숫자 열을 모두 더합니다. '
        "하나라도 비어 있으면 결과도 빈 값입니다."
    ),
    cases=(
        ok('SUMTAG("매출")', 3, cols=_TAGGED, tags=_TAGS, row={"a": 1, "b": 2, "c": 100}),
        ok('SUMTAG("비용")', 100, cols=_TAGGED, tags=_TAGS, row={"a": 1, "b": 2, "c": 100}),
        ok(
            'SUMTAG("매출")',
            None,
            cols=_TAGGED,
            tags=_TAGS,
            row={"a": 1, "c": 100},
            note="태그 열 하나가 비면 SUM과 같이 빈 값",
        ),
        reject('SUMTAG("없는태그")', "TAG_EMPTY", cols=_TAGGED, tags=_TAGS),
        reject("SUMTAG(1)", "ARG_TYPE"),
        reject('SUMTAG("매출" & "x")', "CONST_REQUIRED", cols=_TAGGED, tags=_TAGS),
        reject('SUMTAG("a", "b")', "ARG_COUNT"),
    ),
)


# --- 글자 ----


def _left_right_bad_length(ctx: ConvertContext, a: Sequence[Compiled]) -> ColumnElement[Any]:
    n = a[1].value
    return sa.or_(n < ctx.lit.number(0), n > ctx.lit.number(10000))


def _slice(function: Any) -> Any:
    def to_sql(ctx: ConvertContext, a: Sequence[Compiled]) -> ColumnElement[Any]:
        return function(a[0].value, sa.cast(sa.func.trunc(a[1].value), sa.Integer))

    return to_sql


def _slicing(name: str, function: Any, help_text: str, cases: tuple[Case, ...]) -> FunctionSpec:
    return FunctionSpec(
        name=name,
        signature=(Param("글자", TEXT), _num("개수")),
        returns=TEXT,
        null_policy="propagate",
        native_null=True,
        error_when=(ErrorRule("E2", _left_right_bad_length),),
        to_sql=_slice(function),
        excel_diff="개수의 소수 부분은 버립니다. 개수가 0 미만이거나 10000 초과면 "
        "오류 칸이 됩니다.",
        help_ko=help_text,
        cases=(
            *cases,
            ok(f"{name}([s], 2)", None, cols=_S, row={}),
            ok(
                f"{name}([s], [a])",
                None,
                cols={**_S, **_N},
                row={"a": -1},
                note="빈 값이 자기 조건보다 먼저",
            ),
            err(f"{name}([s], [a])", "E2", cols={**_S, **_N}, row={"s": "abc", "a": -1}),
            err(f"{name}([s], [a])", "E2", cols={**_S, **_N}, row={"s": "abc", "a": 10001}),
            ok(f"{name}([s], [a])", "abc", cols={**_S, **_N}, row={"s": "abc", "a": 10000}),
            reject(f'{name}("a", -1)', "CONSTANT_ERROR"),
            reject(f"{name}(1, 2)", "ARG_TYPE"),
            reject(f'{name}("a", "b")', "ARG_TYPE"),
        ),
    )


LEFT = _slicing(
    "LEFT",
    sa.func.left,
    "LEFT(글자, 개수): 글자의 앞에서 개수만큼 가져옵니다(개수의 소수는 버림).",
    (
        ok('LEFT("가나다라", 2)', "가나"),
        ok('LEFT("abc", 2.9)', "ab"),
        ok('LEFT("abc", 0)', ""),
        ok('LEFT("abc", 10)', "abc"),
    ),
)
RIGHT = _slicing(
    "RIGHT",
    sa.func.right,
    "RIGHT(글자, 개수): 글자의 뒤에서 개수만큼 가져옵니다(개수의 소수는 버림).",
    (
        ok('RIGHT("가나다라", 2)', "다라"),
        ok('RIGHT("abc", 2.9)', "bc"),
        ok('RIGHT("abc", 0)', ""),
        ok('RIGHT("abc", 10)', "abc"),
    ),
)

LEN = FunctionSpec(
    name="LEN",
    signature=(Param("글자", TEXT),),
    returns=NUMBER,
    null_policy="propagate",
    native_null=True,
    to_sql=lambda ctx, a: sa.cast(sa.func.char_length(a[0].value), sa.Numeric),
    excel_diff="글자 수는 코드포인트 수입니다(입력은 NFC로 정규화됩니다).",
    help_ko="글자의 길이(글자 수)입니다.",
    cases=(
        ok('LEN("가나다")', 3),
        ok('LEN("")', 0),
        ok('LEN(" a ")', 3),
        ok("LEN([s])", 2, cols=_S, row={"s": "ab"}),
        ok("LEN([s])", None, cols=_S, row={}),
        reject("LEN(1)", "ARG_TYPE"),
    ),
)


def _trim(ctx: ConvertContext, a: Sequence[Compiled]) -> ColumnElement[Any]:
    lit = ctx.lit
    squeezed = sa.func.regexp_replace(a[0].value, lit.text(" +"), lit.text(" "), lit.text("g"))
    return sa.func.btrim(squeezed)


TRIM = FunctionSpec(
    name="TRIM",
    signature=(Param("글자", TEXT),),
    returns=TEXT,
    null_policy="propagate",
    native_null=True,
    to_sql=_trim,
    excel_diff="앞뒤 공백을 지우고 안쪽의 연속된 공백도 하나로 줄입니다(엑셀과 같음).",
    help_ko="글자의 앞뒤 공백을 지우고, 안쪽의 여러 공백은 하나로 줄입니다.",
    cases=(
        ok('TRIM("  a  b  ")', "a b"),
        ok('TRIM("가")', "가"),
        ok('TRIM("   ")', ""),
        ok("TRIM([s])", "x y", cols=_S, row={"s": " x   y "}),
        ok("TRIM([s])", None, cols=_S, row={}),
        reject("TRIM(1)", "ARG_TYPE"),
    ),
)


# --- 날짜 ----


def _extract(part: str) -> Any:
    return lambda ctx, a: sa.cast(sa.extract(part, a[0].value), sa.Numeric)


_DATE_1 = datetime.date(2026, 3, 15)
_DATE_COLS = {"d": "date"}

YEAR = FunctionSpec(
    name="YEAR",
    signature=(Param("날짜", DATE),),
    returns=NUMBER,
    null_policy="propagate",
    native_null=True,
    to_sql=_extract("year"),
    sqlite=True,
    excel_diff="같음",
    help_ko="날짜의 연도입니다.",
    cases=(
        ok("YEAR([d])", 2026, cols=_DATE_COLS, row={"d": _DATE_1}),
        ok("YEAR([d])", None, cols=_DATE_COLS, row={}),
        ok("YEAR([d])", 2024, cols=_DATE_COLS, row={"d": datetime.date(2024, 2, 29)}),
        reject("YEAR(2026)", "ARG_TYPE"),
        reject('YEAR("2026-01-01")', "ARG_TYPE"),
    ),
)
MONTH = FunctionSpec(
    name="MONTH",
    signature=(Param("날짜", DATE),),
    returns=NUMBER,
    null_policy="propagate",
    native_null=True,
    to_sql=_extract("month"),
    sqlite=True,
    excel_diff="같음",
    help_ko="날짜의 월(1~12)입니다.",
    cases=(
        ok("MONTH([d])", 3, cols=_DATE_COLS, row={"d": _DATE_1}),
        ok("MONTH([d])", None, cols=_DATE_COLS, row={}),
        ok("MONTH([d])", 12, cols=_DATE_COLS, row={"d": datetime.date(2026, 12, 31)}),
        reject("MONTH(3)", "ARG_TYPE"),
    ),
)

_DATE_MAX_DAYS = (datetime.date.max - datetime.date.min).days
_DAY_LIMIT = 100_000


class _DateParts:
    """`DATE(연, 월, 일)`의 계산 조각. 엑셀처럼 월·일이 넘치면 이월한다(소수는 0 쪽으로 버림).

    PostgreSQL은 **상수 부분식**을 계획 시간에 미리 계산하고, 그 식이 `CASE`의 쓰이지 않는 갈래에
    있어도
    오류가 나면 쿼리 전체가 실패한다(07 §3). 인수 일부만 상수일 때(`DATE(0, 1, [일])`)를 위해
    `make_date`와
    정수 변환에 들어가는 연·일을 **범위 안으로 가둔 값**(`safe_year`, `safe_day`)으로 만든다. 범위
    밖이면 어차피
    오류 조건이 참이라 값은 쓰이지 않는다.
    """

    def __init__(self, ctx: ConvertContext, a: Sequence[Compiled]) -> None:
        lit = ctx.lit
        one, twelve = lit.number(1), lit.number(12)
        self.ctx = ctx
        self.day = sa.func.trunc(a[2].value)
        months = sa.func.trunc(a[1].value)
        carry = sa.func.floor((months - one) / twelve)
        self.year = sa.func.trunc(a[0].value) + carry
        self.month = months - twelve * carry  # 1~12
        self.year_ok = sa.and_(self.year >= lit.number(1), self.year <= lit.number(9999))
        self.day_ok = sa.and_(
            self.day >= lit.number(-_DAY_LIMIT), self.day <= lit.number(_DAY_LIMIT)
        )
        # 범위를 벗어난 것만 바꾼다. 빈 값(NULL)은 그대로 둬야 결과가 빈 값이 된다(`coalesce`로
        # NULL을 "정상"으로 본다).
        yes = lit.boolean(True)
        year_bad = sa.not_(sa.func.coalesce(self.year_ok, yes))
        day_bad = sa.not_(sa.func.coalesce(self.day_ok, yes))
        safe_year = sa.case((year_bad, lit.number(2000)), else_=self.year)
        self.safe_days = sa.case((day_bad, lit.number(0)), else_=self.day - one)
        self.first = sa.func.make_date(
            sa.cast(safe_year, sa.Integer),
            sa.cast(self.month, sa.Integer),
            lit.integer(1),
            type_=sa.Date(),
        )
        self.offset_days = self.first - lit.date(datetime.date.min) + self.safe_days

    def value(self) -> ColumnElement[Any]:
        return self.first + sa.cast(self.safe_days, sa.Integer)

    def out_of_range(self) -> ColumnElement[Any]:
        lit = self.ctx.lit
        yes, no = lit.boolean(True), lit.boolean(False)
        return sa.case(
            (sa.not_(self.day_ok), yes),
            (sa.not_(self.year_ok), yes),
            (
                sa.or_(
                    self.offset_days < lit.number(0), self.offset_days > lit.number(_DATE_MAX_DAYS)
                ),
                yes,
            ),
            else_=no,
        )


DATE_FN = FunctionSpec(
    name="DATE",
    signature=(_num("연"), _num("월"), _num("일")),
    returns=DATE,
    null_policy="propagate",
    native_null=True,
    error_when=(ErrorRule("E3", lambda ctx, a: _DateParts(ctx, a).out_of_range()),),
    to_sql=lambda ctx, a: _DateParts(ctx, a).value(),
    excel_diff="월·일이 넘치면 엑셀처럼 이월합니다(2월 30일 -> 3월 2일). 소수는 버립니다. "
    "결과가 0001-01-01~9999-12-31을 벗어나면 오류 칸이 됩니다.",
    help_ko="DATE(연, 월, 일): 날짜를 만듭니다. 월이나 일이 넘치면 다음 달·해로 넘어갑니다"
    "(DATE(2026, 13, 1)은 2027-01-01).",
    cases=(
        ok("DATE(2024, 2, 29)", datetime.date(2024, 2, 29)),
        ok("DATE(2023, 2, 30)", datetime.date(2023, 3, 2), note="2월 30일 -> 3월 2일"),
        ok("DATE(2024, 13, 1)", datetime.date(2025, 1, 1)),
        ok("DATE(2024, 0, 1)", datetime.date(2023, 12, 1)),
        ok("DATE(2024, -1, 1)", datetime.date(2023, 11, 1)),
        ok("DATE(2024, 1, 0)", datetime.date(2023, 12, 31)),
        ok("DATE(2024.9, 1.9, 1.9)", datetime.date(2024, 1, 1), note="소수는 버림"),
        ok("DATE(1, 1, 1)", datetime.date(1, 1, 1)),
        ok("DATE(9999, 12, 31)", datetime.date(9999, 12, 31)),
        ok(
            "DATE([a], [b], [c])",
            datetime.date(2026, 3, 15),
            cols=_NNN,
            row={"a": 2026, "b": 3, "c": 15},
        ),
        ok("DATE([a], 1, 1)", None, cols=_N, row={}),
        ok(
            "DATE([a], [b], 99999999)",
            None,
            cols=_NN,
            row={"a": 2026},
            note="인수 빈 값이 자기 조건보다 먼저",
        ),
        err("DATE([a], 1, 1)", "E3", cols=_N, row={"a": 0}),
        err("DATE([a], 1, 1)", "E3", cols=_N, row={"a": 10000}),
        err("DATE(2026, 1, [a])", "E3", cols=_N, row={"a": 100001}),
        err("DATE(2026, 1, [a])", "E3", cols=_N, row={"a": -100001}),
        err("DATE(9999, 12, [a])", "E3", cols=_N, row={"a": 32}),
        err("DATE(1, 1, [a])", "E3", cols=_N, row={"a": 0}),
        reject("DATE(0, 1, 1)", "CONSTANT_ERROR"),
        reject("DATE(2026, 1, 200000)", "CONSTANT_ERROR"),
        reject('DATE("2026", 1, 1)', "ARG_TYPE"),
        reject("DATE(2026, 1)", "ARG_COUNT"),
    ),
)


# --- 기준값 `REF("이름")` (FU-3, 07 §2-2·§3-2, 03b 32) ----
# 환경 함수(K6 원칙의 예외 한 번): 기준값 항목 이름 -> 번호와 기준 날짜 열을
# `ReferenceEnv`로 받는다.
# 인수는 직접 쓴 글자 상수 하나(항목 이름 50자 이하), 결과는 숫자다. 행의 기준 날짜와 **같은 연도**
# 값만 쓰고(이월 없음) 값이 없으면 빈 값 + 셀 오류 E4다.

REF_NAME = "REF"
REF_MAX_NAME_LENGTH = 50  # 06 §2-2: 기준값 항목 이름 길이 상한(`reference_items`와 같다)


def _ref_precheck(
    node: Call,
    targs: Sequence[Any],
    env: ReferenceEnv,
    columns: Mapping[int, ColumnInfo],
) -> list[FormulaIssue]:
    """C0: 기준 날짜 열이 없거나 이름이 없는 항목이면 오류(둘 다 해당하면 두 오류 모두)."""
    issues: list[FormulaIssue] = []
    base = columns.get(env.base_date_column_id) if env.base_date_column_id is not None else None
    if base is None or base.kind != "raw" or base.type != "date":
        issues.append(make_issue("BASE_DATE_REQUIRED", node.start, node.end))
    if len(targs) == 1 and targs[0].kind == "text":
        name = targs[0].value
        # 글자 상수 규칙을 어긴 이름은 TEXT_CONSTANT_INVALID가 이미 알렸다.
        if text_constant_problem(name) is None and name not in env.item_ids:
            from app.formula.analyze import Analysis

            suggest = Analysis._suggest(name, sorted(env.item_ids), quote="'{}'")
            issues.append(
                make_issue("REF_UNKNOWN", targs[0].start, targs[0].end, name=name, suggest=suggest)
            )
    return issues


def _ref(ctx: ConvertContext, a: Sequence[Compiled]) -> Compiled:
    """값 = 상관 스칼라 서브쿼리 하나, 오류 = 값이 없으면 4(`CASE WHEN (같은 서브쿼리) IS NULL`)."""
    env = ctx.env
    if env is None or env.base_date_column_id is None:
        raise RuntimeError("REF 변환에는 기준값 환경과 기준 날짜 열이 필요하다(구현 오류).")
    name = a[0].const
    item_id = env.item_ids[name]  # C0(precheck)가 이름을 확인했다. 없으면 KeyError(구현 오류)
    value = reference_value_subquery(
        ctx.lit.reference_id(item_id), ctx.source(env.base_date_column_id)
    )
    return Compiled(value, sa.case((value.is_(None), ctx.lit.code("E4"))), NUMBER)


_REF_COLS = {"기준일": "date"}
_REF_VALUES = {"전기요금": {2025: "10", 2026: "12.5"}}

REF = FunctionSpec(
    name=REF_NAME,
    signature=(Param("이름", TEXT, const=ConstRule("text", max_length=REF_MAX_NAME_LENGTH)),),
    returns=NUMBER,
    null_policy="custom",
    to_sql_custom=_ref,
    precheck=_ref_precheck,
    reads_row=True,
    excel_diff="엑셀에는 없는 이름입니다(엑셀의 상수 칸이나 VLOOKUP에 해당). 그 행의 기준 날짜와 "
    "같은 연도의 기준값만 쓰고 전년 값을 이어 쓰지 않습니다.",
    help_ko=(
        'REF("이름"): 기준값 화면에 등록한 항목에서, 그 행의 기준 날짜가 속한 연도의 값을 '
        "가져옵니다. "
        "그 연도 값이 없으면 빈 값이 되고 오류 E4로 점검 화면에 나옵니다. "
        "기준 날짜 열이 있는 데이터셋에서만 쓸 수 있고 결과는 숫자입니다."
    ),
    cases=(
        ok(
            'REF("전기요금")',
            "12.5",
            cols=_REF_COLS,
            row={"기준일": datetime.date(2026, 3, 1)},
            refs=_REF_VALUES,
            base="기준일",
        ),
        ok(
            'REF("전기요금")',
            "10",
            cols=_REF_COLS,
            row={"기준일": datetime.date(2025, 12, 31)},
            refs=_REF_VALUES,
            base="기준일",
            note="같은 연도 값만 쓴다(연도 경계)",
        ),
        err(
            'REF("전기요금")',
            "E4",
            cols=_REF_COLS,
            row={"기준일": datetime.date(2027, 1, 1)},
            refs=_REF_VALUES,
            base="기준일",
            note="2026년 값이 있어도 이월하지 않는다",
        ),
        reject(
            'REF("없는항목")',
            "REF_UNKNOWN",
            cols=_REF_COLS,
            refs=_REF_VALUES,
            base="기준일",
        ),
        reject('REF("전기요금")', "BASE_DATE_REQUIRED", refs=_REF_VALUES),
        reject("REF([기준일])", "CONST_REQUIRED", cols=_REF_COLS, refs=_REF_VALUES, base="기준일"),
        reject("REF()", "ARG_COUNT", cols=_REF_COLS, refs=_REF_VALUES, base="기준일"),
        reject(
            'REF("전기요금", 2026)', "ARG_COUNT", cols=_REF_COLS, refs=_REF_VALUES, base="기준일"
        ),
    ),
)


_ALL_SPECS = (
    ADD, SUBTRACT, MULTIPLY, DIVIDE, NEGATE,
    EQUAL, NOT_EQUAL, LESS, LESS_EQUAL, GREATER, GREATER_EQUAL,
    CONCAT, IF, AND, OR, NOT, IFERROR,
    ROUND, ROUNDUP, ROUNDDOWN, ABS, MIN, MAX, SUM, SUMTAG,
    LEFT, RIGHT, LEN, TRIM, YEAR, MONTH, DATE_FN,
    REF,
)  # fmt: skip


def build_default_registry() -> FunctionRegistry:
    """FU-1 함수 세트를 담은 **새** 등록부(시험이 임시 함수를 더해도 다른 곳에 새지 않는다)."""
    registry = FunctionRegistry()
    for spec in _ALL_SPECS:
        registry.register(spec)
    return registry


_DEFAULT: FunctionRegistry | None = None


def get_default_registry() -> FunctionRegistry:
    """공유 기본 등록부(읽기 전용으로 쓴다)."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = build_default_registry()
    return _DEFAULT
