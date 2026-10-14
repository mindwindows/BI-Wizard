"""차분(differential) 시험 행렬 생성기(07 §6, 04 §8): 함수 사전에서 수식 조합을 **자동으로** 만든다.

DB를 모른다. 사전의 항목(연산자 포함)마다 인수 구성 x 값 변형 x 출처를 만든다.

- 출처(인수 하나가 어디서 오는가): `const`(수식 안의 상수), `col`(원본 열 값), `calc`(원본 열을
  그대로 돌려주는
  계산 열을 참조해 식이 펼쳐지는 경우).
- 값 변형: 숫자 {0, 1, -1, 0.1, 0.5, 1.5, 2.5, -2.5, 1E-7, 10**30, 38자리, 긴 소수 3종},
  글자 {빈 문자열, 한글,
  `O'Brien`, 대소문자 혼합, 앞뒤·안쪽 연속 공백, NFC/NFD 쌍, 200자, `%` 포함}, 참거짓, 날짜 {윤일,
  월말, 0001-01-01, 9999-12-31}, 빈 값(열 값에서만 생긴다).
- 인수 두 개까지는 전수(모든 출처·값 조합), 세 개 이상은 쌍별(모든 인수 쌍의 모든 선택 조합을 한 번
  이상 포함)이다.
- 사전에 항목이 늘면 이 생성기가 읽어 자동으로 행렬이 커진다(시험이 항목별 수식이 있는지 확인한다).
"""

from __future__ import annotations

import datetime
import itertools
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.formula import get_default_registry
from app.formula.registry import TYPE_VARIABLE, TYPES, FunctionSpec, Param

NUMBERS: tuple[Decimal, ...] = (
    Decimal(0),
    Decimal(1),
    Decimal(-1),
    Decimal("0.1"),
    Decimal("0.5"),
    Decimal("1.5"),
    Decimal("2.5"),
    Decimal("-2.5"),
    Decimal("1E-7"),
    Decimal(10**30),
    Decimal("12345678901234567890123456789012345678"),  # 38자리
    Decimal("123456789012.1234567895"),  # 정수부 12자리 + 소수 10자리(끝이 5인 반올림 경계)
    Decimal("-123456789012.1234567895"),
    Decimal("0.12345678901234567890123456789012345678"),  # 소수 38자리
)
_NFC = "é"  # é
_NFD = "é"  # e + 결합 악센트(같은 글자의 다른 표현)
TEXTS: tuple[str, ...] = (
    "",
    "한글",
    "O'Brien",
    "AbC dEf",
    " 앞뒤 ",
    "안  쪽   공백",
    _NFC,
    _NFD,
    "가" * 200,
    "100%",
)
BOOLEANS: tuple[bool, ...] = (True, False)
DATES: tuple[datetime.date, ...] = (
    datetime.date(2024, 2, 29),
    datetime.date(2023, 1, 31),
    datetime.date(1, 1, 1),
    datetime.date(9999, 12, 31),
)
VARIANTS: dict[str, tuple[Any, ...]] = {
    "number": NUMBERS,
    "text": TEXTS,
    "boolean": BOOLEANS,
    "date": DATES,
}
CONST_INTEGERS = (-10, -1, 0, 1, 2, 5, 10)  # 정수 상수 인수(예: ROUND 자릿수 -10~10)
TAGS = ("합계",)  # SUMTAG 시험용 태그

CONST, COL, CALC = "const", "col", "calc"
MAX_FORMULAS_PER_DATASET = 250


# --- 수식 글자 만들기 ----


def literal_text(kind: str, value: Any) -> str:
    """상수 값을 수식 글자로(날짜는 `DATE(연, 월, 일)`)."""
    if kind == "number":
        return format(value, "f") if value >= 0 else f"({format(value, 'f')})"
    if kind == "text":
        return '"' + value.replace('"', '""') + '"'
    if kind == "boolean":
        return "TRUE" if value else "FALSE"
    if kind == "date":
        return f"DATE({value.year}, {value.month}, {value.day})"
    raise ValueError(kind)


@dataclass(frozen=True)
class Arg:
    """인수 하나의 선택: 출처와 (const일 때) 값."""

    source: str
    value: Any = None


@dataclass(frozen=True)
class Combo:
    """수식 하나: 사전 항목, 인수 형(고정된 T), 인수 선택, 수식 글자."""

    spec_name: str
    arg_types: tuple[str, ...]
    args: tuple[Arg, ...]
    expression: str
    constant_error: str | None = (
        None  # 사전 `error_when` 규칙으로 C0가 거부해야 하면 그 코드(E1~E3)
    )


@dataclass
class Group:
    """같은 열·행 구성을 쓰는 수식 묶음(한 데이터셋 한 개 분량 이하로 나눈다)."""

    spec_name: str
    arg_types: tuple[str, ...]
    combos: list[Combo] = field(default_factory=list)
    rows: list[tuple[Any, ...]] = field(default_factory=list)  # 인수 위치별 열 값(없으면 None)
    tags: bool = False  # SUMTAG 묶음: 같은 태그의 숫자 열을 쓴다


# --- 상수 오류 기대값(사전의 `error_when`으로 설명되는 거부, 07 §3) ----
# 인수가 모두 수식 안 상수이면 C0가 `CONSTANT_ERROR`로 거부한다(DB 오류 조건을 상수로 평가).
# 어떤 조합이 거부돼야 하는지를 DB와 변환기를 쓰지 않고 파이썬으로 따로 계산해(독립 기대값)
# 거부된 수식의 집합이 정확히 같은지 대조한다. 사전에 `error_when`이 있는 항목이 늘면
# `CONSTANT_ERROR_ORACLE`에 더해야 한다(시험이 확인한다).


def _truncate(value: Decimal) -> int:
    return int(value)  # 0 쪽으로 버림


def _divide_by_zero(values: Sequence[Any]) -> str | None:
    return "E1" if values[1] == 0 else None  # 나누는 수가 0


def _bad_slice_length(values: Sequence[Any]) -> str | None:
    n = values[1]
    return "E2" if (n < 0 or n > 10000) else None  # 개수가 0 미만이거나 10000 초과


def _date_out_of_range(values: Sequence[Any]) -> str | None:
    year, month, day = (_truncate(v) for v in values)
    carry = (month - 1) // 12
    year, month = year + carry, month - 12 * carry
    if not -100000 <= day <= 100000 or not 1 <= year <= 9999:
        return "E3"
    try:
        datetime.date(year, month, 1) + datetime.timedelta(days=day - 1)
    except OverflowError:
        return "E3"
    return None


CONSTANT_ERROR_ORACLE = {
    "/": _divide_by_zero,
    "LEFT": _bad_slice_length,
    "RIGHT": _bad_slice_length,
    "DATE": _date_out_of_range,
}
# 거부 코드는 C0의 `CONSTANT_ERROR` 하나뿐이다(다른 코드가 나오면 행렬이나 변환기가 잘못된 것).
EXPECTED_REJECTION_CODES = frozenset({"CONSTANT_ERROR"})


def constant_error(spec_name: str, args: Sequence[Arg]) -> str | None:
    """인수가 모두 상수이고 사전 규칙의 오류 조건이 참이면 그 셀 오류 코드(E1~E3), 아니면 None."""
    rule = CONSTANT_ERROR_ORACLE.get(spec_name)
    if rule is None or any(arg.source != CONST for arg in args):
        return None
    return rule([arg.value for arg in args])


# --- 쌍별 조합 ----


def pairwise(domains: Sequence[Sequence[Any]]) -> list[tuple[Any, ...]]:
    """모든 두 위치의 모든 값 쌍을 한 번 이상 포함하는 조합 목록(탐욕법, 결정적)."""
    n = len(domains)
    if n == 0:
        return [()]
    if n == 1:
        return [(v,) for v in domains[0]]

    def key(p: int, cp: int, q: int, cq: int) -> tuple[int, int, int, int]:
        return (p, cp, q, cq) if p < q else (q, cq, p, cp)

    uncovered = {
        (i, a, j, b)
        for i, j in itertools.combinations(range(n), 2)
        for a in range(len(domains[i]))
        for b in range(len(domains[j]))
    }
    rows: list[tuple[Any, ...]] = []
    while uncovered:
        i, a, j, b = min(uncovered)  # 아직 덮이지 않은 쌍 하나로 시작해 항상 진행한다
        chosen = {i: a, j: b}
        for position in range(n):
            if position in chosen:
                continue
            best, best_gain = 0, -1
            for candidate in range(len(domains[position])):
                gain = sum(
                    key(position, candidate, other, value) in uncovered
                    for other, value in chosen.items()
                )
                if gain > best_gain:
                    best, best_gain = candidate, gain
            chosen[position] = best
        for p, q in itertools.combinations(range(n), 2):
            uncovered.discard(key(p, chosen[p], q, chosen[q]))
        rows.append(tuple(domains[p][chosen[p]] for p in range(n)))
    return rows


def _combine(domains: Sequence[Sequence[Any]]) -> list[tuple[Any, ...]]:
    """인수 두 개까지는 전수, 세 개 이상은 쌍별."""
    if len(domains) <= 2:
        return list(itertools.product(*domains))
    return pairwise(domains)


# --- 인수 구성 ----


def _arity_options(spec: FunctionSpec) -> list[int]:
    low = spec.min_args
    high = spec.max_args
    if high is None:  # 반복 인수가 있는 항목: 최소, +1, +2개
        return [low, low + 1, low + 2]
    return list(range(low, high + 1))


def _type_bindings(spec: FunctionSpec, arity: int) -> Iterator[tuple[str, ...]]:
    """인수 위치별 구체 형. `T` 인수는 허용 형 안에서 모두 같은 형으로 묶인다."""
    params = [spec.param_for(i) for i in range(arity)]
    variables = [p for p in params if p.type == TYPE_VARIABLE]
    if not variables:
        yield tuple(p.type for p in params)
        return
    allowed = set(TYPES)
    for p in variables:
        allowed &= set(p.allowed or TYPES)
    for bound in sorted(allowed):
        yield tuple(bound if p.type == TYPE_VARIABLE else p.type for p in params)


def _domain(param: Param, kind: str) -> list[Arg]:
    """인수 하나가 고를 수 있는 선택(출처 x 값)."""
    if param.const is not None:  # 직접 쓴 상수만
        if param.const.kind == "integer":
            low = param.const.min if param.const.min is not None else -10
            high = param.const.max if param.const.max is not None else 10
            return [Arg(CONST, v) for v in CONST_INTEGERS if low <= v <= high]
        return [Arg(CONST, tag) for tag in TAGS]
    return [Arg(CONST, v) for v in VARIANTS[kind]] + [Arg(COL), Arg(CALC)]


def render_expression(
    spec: FunctionSpec, arg_types: tuple[str, ...], args: Sequence[Arg], names: Sequence[str]
) -> str:
    """인수 선택으로 수식 글자를 만든다. `names[i]`는 i번째 인수의 원본 열 이름이다."""
    parts: list[str] = []
    for index, (kind, arg) in enumerate(zip(arg_types, args, strict=True)):
        if arg.source == CONST:
            if (
                spec.param_for(index).const is not None
                and spec.param_for(index).const.kind == "integer"
            ):
                parts.append(literal_text("number", Decimal(arg.value)))
            else:
                parts.append(literal_text(kind, arg.value))
        elif arg.source == COL:
            parts.append(f"[{names[index]}]")
        else:
            parts.append(f"[{names[index]} 계산]")
    if spec.kind == "operator" and spec.syntax == "infix":
        return f"({parts[0]}) {spec.symbol} ({parts[1]})"
    if spec.kind == "operator" and spec.syntax == "prefix":
        return f"{spec.symbol}({parts[0]})"
    return f"{spec.name}({', '.join(parts)})"


def column_names(arity: int) -> list[str]:
    return [f"입력{i + 1}" for i in range(arity)]


def spec_groups(spec: FunctionSpec) -> list[Group]:
    """사전 항목 하나의 수식 묶음들. 행·열 구성은 묶음마다 같다."""
    groups: list[Group] = []
    if spec.rewrite is not None:  # SUMTAG: 태그 열 목록을 컴파일 때 펼친다(열 값은 행으로)
        group = Group(spec.name, ("number", "number", "number"), tags=True)
        group.rows = pairwise([(*NUMBERS, None)] * 3)
        for tag in TAGS:
            group.combos.append(
                Combo(spec.name, ("text",), (Arg(CONST, tag),), f'{spec.name}("{tag}")')
            )
        return [group]
    for arity in _arity_options(spec):
        for arg_types in _type_bindings(spec, arity):
            params = [spec.param_for(i) for i in range(arity)]
            domains = [_domain(p, k) for p, k in zip(params, arg_types, strict=True)]
            names = column_names(arity)
            group = Group(spec.name, arg_types)
            # 행: 열 값을 가질 수 있는 위치(상수 전용 인수 제외)의 값 변형 x 빈 값
            row_domains = [
                (*VARIANTS[k], None) if p.const is None else (None,)
                for p, k in zip(params, arg_types, strict=True)
            ]
            group.rows = _combine(row_domains)
            for choice in _combine(domains):
                expression = render_expression(spec, arg_types, choice, names)
                group.combos.append(
                    Combo(
                        spec.name,
                        arg_types,
                        tuple(choice),
                        expression,
                        constant_error(spec.name, choice),
                    )
                )
            groups.append(group)
    return groups


def chunks(group: Group, size: int = MAX_FORMULAS_PER_DATASET) -> Iterator[Group]:
    for start in range(0, len(group.combos), size):
        yield Group(
            group.spec_name,
            group.arg_types,
            group.combos[start : start + size],
            group.rows,
            group.tags,
        )


def all_groups() -> list[Group]:
    """사전의 모든 항목(연산자 포함)의 수식 묶음. 사전이 커지면 자동으로 커진다."""
    result: list[Group] = []
    for spec in get_default_registry().specs():
        if spec.precheck is not None:
            continue  # 환경 함수(`REF`): 전용 묶음(tests/reference_bundle.py)이 맡는다
        for group in spec_groups(spec):
            result.extend(chunks(group))
    return result


def total_formulas(groups: Sequence[Group]) -> int:
    return sum(len(g.combos) for g in groups)


def expected_rejections(groups: Sequence[Group]) -> dict[tuple[str, str], str]:
    """C0가 거부해야 하는 수식: (사전 항목 이름, 수식) -> 설명하는 셀 오류 코드."""
    return {
        (g.spec_name, c.expression): c.constant_error
        for g in groups
        for c in g.combos
        if c.constant_error is not None
    }
