"""`REF` 차분 시험 묶음(07 §6 "REF 전용 묶음", 03b 32-4): 수식·행·기준값과 **파이썬 독립 기대값**.

독립 기대값은 SQL·SQLAlchemy·변환기를 쓰지 않는다: 파이썬 `Decimal`과 사전 `{(항목, 연도): 값}`,
행의 `date.year`만으로 행별 (값, 셀 오류)를 계산한다. 규칙은 07 문서의 문장을 그대로 옮긴 것이다.

- 연도 일치: 그 행의 기준 날짜의 연도와 **같은 연도** 값만 쓴다. 없으면 빈 값 + `E4`(이월 없음).
- 오류 우선: 인수의 오류(`E4`)가 자기 조건(`E1` 0으로 나눔)보다 먼저다. 빈 값은 전파한다.
- `IF`는 고른 쪽의 오류만 반영하고 조건의 오류가 먼저다. `IFERROR`는 오류 칸이면 대체값(과 그
  오류)을 쓴다.
"""

from __future__ import annotations

import datetime
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_UP, ROUND_UP, Decimal, localcontext
from typing import Any, NamedTuple

D = datetime.date

# 기준값: 항목 -> {연도: 값}. 1900/9999(CHECK 경계), 0, 음수, 아주 작은 값, 38자리, 값 0개 항목.
ITEMS: dict[str, dict[int, str]] = {
    "단가": {
        1900: "1.5",
        2023: "10",
        2024: "12.25",
        2025: "0",
        2026: "-3.75",
        9999: "99.5",
    },
    "공제": {2024: "100.125", 2026: "0.0000001", 2023: "1"},
    "빈항목": {},
    "큰값": {2024: "12345678901234567890123456789012345678", 2026: "-1"},
}

# 날짜 단위별 행(기준 날짜 열은 기간 첫날 CHECK와 유일 인덱스가 있어 단위마다 가능한 날짜가 다르다).
# CHECK 범위 밖 연도(1, 1899)와 9999, 윤일, 연말·연초 경계를 모두 넣는다.
DATES: dict[str, tuple[datetime.date, ...]] = {
    "day": (
        D(1, 1, 1),
        D(1899, 12, 31),
        D(1900, 1, 1),
        D(2023, 12, 31),
        D(2024, 1, 1),
        D(2024, 2, 29),
        D(2024, 12, 31),
        D(2025, 1, 1),
        D(2025, 6, 15),
        D(2026, 12, 31),
        D(2027, 1, 1),
        D(9999, 1, 1),
        D(9999, 12, 31),
    ),
    "month": (
        D(1, 1, 1),
        D(1899, 12, 1),
        D(1900, 1, 1),
        D(2023, 12, 1),
        D(2024, 1, 1),
        D(2024, 2, 1),
        D(2025, 1, 1),
        D(2025, 12, 1),
        D(2026, 12, 1),
        D(2027, 1, 1),
        D(9999, 1, 1),
        D(9999, 12, 1),
    ),
    "year": (
        D(1, 1, 1),
        D(1899, 1, 1),
        D(1900, 1, 1),
        D(2023, 1, 1),
        D(2024, 1, 1),
        D(2025, 1, 1),
        D(2026, 1, 1),
        D(2027, 1, 1),
        D(9999, 1, 1),
    ),
}
# 숫자 열 `x` 값의 변형(빈 값 포함). 데이터셋마다 행에 돌려 가며 배정해 날짜 x 값을 모두 만난다.
X_VALUES: tuple[Decimal | None, ...] = (
    None,
    Decimal(0),
    Decimal(1),
    Decimal("-2.5"),
    Decimal(10**30),
)
DATASETS_PER_UNIT = len(X_VALUES)


class Row(NamedTuple):
    date: datetime.date
    x: Decimal | None


class V(NamedTuple):
    """한 칸의 기대 (값, 셀 오류 코드). 값이 있으면 오류가 없다."""

    value: Any
    err: str | None


Oracle = Callable[[Row], V]


def lookup(items: dict[str, dict[int, str]], name: str, day: datetime.date) -> V:
    value = items[name].get(day.year)  # 그 연도 값만. 이월하지 않는다.
    return V(Decimal(value), None) if value is not None else V(None, "E4")


# --- 독립 기대값 도구(인수 오류 우선 > 빈 값 전파 > 자기 오류) ----


def call(fn: Callable[..., Any], args: list[V], own: Callable[..., str | None] | None = None) -> V:
    for arg in args:
        if arg.err is not None:
            return V(None, arg.err)
    if any(arg.value is None for arg in args):
        return V(None, None)
    values = [arg.value for arg in args]
    if own is not None and (code := own(*values)):
        return V(None, code)
    with localcontext() as context:
        context.prec = 400
        return V(fn(*values), None)


def _round(mode: str, digits: int) -> Callable[[Decimal], Decimal]:
    def apply(value: Decimal) -> Decimal:
        return value.quantize(Decimal(1).scaleb(-digits), rounding=mode)

    return apply


@dataclass(frozen=True)
class Formula:
    expression: str
    oracle: Callable[[dict[str, dict[int, str]]], Oracle]
    approx: bool = False  # 나눗셈 결과는 PostgreSQL이 자릿수를 정하므로 상대 오차로 비교한다
    note: str = ""


def _build() -> list[Formula]:
    def ref(name: str):
        return lambda items: lambda r: lookup(items, name, r.date)

    def x(items):
        return lambda r: V(r.x, None)

    def num(text: str):
        return lambda items: lambda r: V(Decimal(text), None)

    def year(items):
        return lambda r: V(Decimal(r.date.year), None)

    def fn(function, *parts, own=None):
        def make(items):
            built = [part(items) for part in parts]
            return lambda r: call(function, [b(r) for b in built], own)

        return make

    def add(a, b):
        return fn(lambda p, q: p + q, a, b)

    def mul(a, b):
        return fn(lambda p, q: p * q, a, b)

    def div(a, b):
        return fn(lambda p, q: p / q, a, b, own=lambda p, q: "E1" if q == 0 else None)

    def cmp(op, a, b):
        return fn(op, a, b)

    def if_(cond, yes, no):
        def make(items):
            c, a, b = cond(items), yes(items), no(items)

            def oracle(r: Row) -> V:
                cv = c(r)
                chosen = a(r) if cv.value is True else b(r) if cv.value is False else V(None, None)
                if cv.err is not None:
                    return V(None, cv.err)
                return chosen

            return oracle

        return make

    def iferror(primary, fallback):
        def make(items):
            p, f = primary(items), fallback(items)
            return lambda r: f(r) if p(r).err is not None else p(r)

        return make

    gt = lambda p, q: p > q  # noqa: E731
    ref_u, ref_d, ref_e, ref_b = ref("단가"), ref("공제"), ref("빈항목"), ref("큰값")
    formulas = [
        Formula('REF("단가")', ref_u),
        Formula('REF("공제")', ref_d),
        Formula('REF("빈항목")', ref_e, note="값이 하나도 없는 항목"),
        Formula('REF("큰값")', ref_b, note="38자리"),
        Formula('REF("큰값") + 1', add(ref_b, num("1"))),
        Formula('REF("단가") + REF("단가")', add(ref_u, ref_u), note="같은 항목 두 번"),
        Formula('REF("단가") - REF("공제")', fn(lambda p, q: p - q, ref_u, ref_d), note="항목 둘"),
        Formula('[x] * REF("단가")', mul(x, ref_u)),
        Formula('REF("단가") * [x]', mul(ref_u, x)),
        Formula('REF("단가") * REF("공제") * [x]', mul(mul(ref_u, ref_d), x)),
        Formula('[x] + REF("단가") * 2', add(x, mul(ref_u, num("2")))),
        Formula('-REF("단가")', fn(lambda p: -p, ref_u)),
        Formula('REF("단가") / [x]', div(ref_u, x), approx=True, note="x=0이면 E1, E4가 먼저"),
        Formula('[x] / REF("단가")', div(x, ref_u), approx=True, note="단가 0이면 E1"),
        Formula('ROUND(REF("단가"), 1)', fn(_round(ROUND_HALF_UP, 1), ref_u)),
        Formula('ROUND(REF("공제") * 3, 2)', fn(_round(ROUND_HALF_UP, 2), mul(ref_d, num("3")))),
        Formula('ROUNDUP(REF("단가"), 0)', fn(_round(ROUND_UP, 0), ref_u)),
        Formula('ROUNDDOWN(REF("단가"), 0)', fn(_round(ROUND_DOWN, 0), ref_u)),
        Formula('ROUND([x] * REF("단가"), 0)', fn(_round(ROUND_HALF_UP, 0), mul(x, ref_u))),
        Formula('ABS(REF("단가"))', fn(abs, ref_u)),
        Formula('SUM(REF("단가"), REF("공제"))', add(ref_u, ref_d)),
        Formula(
            'SUM(REF("단가"), REF("단가"), REF("공제"))',
            fn(lambda p, q, s: p + q + s, ref_u, ref_u, ref_d),
        ),
        Formula('MIN(REF("단가"), REF("공제"))', fn(min, ref_u, ref_d)),
        Formula('MAX(REF("단가"), [x])', fn(max, ref_u, x)),
        Formula('IF([x] > 0, REF("단가"), REF("공제"))', if_(cmp(gt, x, num("0")), ref_u, ref_d)),
        Formula(
            'IF([x] = 0, 0, REF("단가"))',
            if_(cmp(lambda p, q: p == q, x, num("0")), num("0"), ref_u),
        ),
        Formula(
            'IF(REF("단가") = 0, 1, REF("공제"))',
            if_(cmp(lambda p, q: p == q, ref_u, num("0")), num("1"), ref_d),
        ),
        Formula('IF(REF("단가") > 5, 1, 0)', if_(cmp(gt, ref_u, num("5")), num("1"), num("0"))),
        Formula('IFERROR(REF("단가"), 0)', iferror(ref_u, num("0")), note="E4를 대체"),
        Formula('IFERROR(REF("단가"), REF("공제"))', iferror(ref_u, ref_d), note="대체값의 E4"),
        Formula('IFERROR([x] / REF("단가"), 0)', iferror(div(x, ref_u), num("0")), approx=True),
        Formula('REF("단가") >= [x]', cmp(lambda p, q: p >= q, ref_u, x), note="참거짓 결과"),
        Formula('REF("단가") = REF("단가")', cmp(lambda p, q: p == q, ref_u, ref_u)),
        Formula(
            'AND(REF("단가") > 0, [x] > 0)',
            fn(lambda p, q: p and q, cmp(gt, ref_u, num("0")), cmp(gt, x, num("0"))),
        ),
        Formula('NOT(REF("단가") > 0)', fn(lambda p: not p, cmp(gt, ref_u, num("0")))),
        Formula('REF("단가") + YEAR([일자])', add(ref_u, year)),
        Formula(
            f'REF("{unicodedata.normalize("NFD", "단가")}")',
            ref_u,
            note="NFD로 쓴 이름도 NFC 항목과 일치",
        ),
    ]
    return formulas


FORMULAS: list[Formula] = _build()

# 계산 열을 참조하는 수식(앞의 두 계산 열을 먼저 저장한 뒤 만든다: 펼침).
PRELIM: list[Formula] = [
    Formula('[x] * REF("단가")', FORMULAS[7].oracle, note="계산 열 `요금`"),
    Formula('REF("단가")', FORMULAS[0].oracle, note="계산 열 `단가열`"),
]
PRELIM_NAMES = ("요금", "단가열")


def _build_nested() -> list[Formula]:
    def oracle_of(index: int):
        return PRELIM[index].oracle

    def plus_one(items):
        base = oracle_of(0)(items)
        return lambda r: call(lambda p: p + 1, [base(r)])

    def times_two(items):
        base = oracle_of(1)(items)
        return lambda r: call(lambda p: p * 2, [base(r)])

    def guarded(items):
        base = oracle_of(0)(items)
        return lambda r: V(Decimal(0), None) if base(r).err else base(r)

    return [
        Formula("[요금] + 1", plus_one, note="REF 열을 참조(펼침)"),
        Formula("[단가열] * 2", times_two),
        Formula("IFERROR([요금], 0)", guarded),
    ]


NESTED: list[Formula] = _build_nested()

# C0가 거부해야 하는 `REF` 수식(기준 날짜 열이 있는 데이터셋에서): 코드.
REJECTED: dict[str, str] = {
    'REF("없는 항목")': "REF_UNKNOWN",
    'REF("단가 ")': "REF_UNKNOWN",  # 이름은 정확히 일치한다(공백 포함)
    'REF("단가2")': "REF_UNKNOWN",
    "REF()": "ARG_COUNT",
    'REF("단가", 2024)': "ARG_COUNT",  # 고정 연도 인수는 이번 범위 밖
    'REF("단가", "공제")': "ARG_COUNT",
    "REF(1)": "ARG_TYPE",
    "REF(TRUE)": "ARG_TYPE",
    "REF([x])": "ARG_TYPE",
    "REF([일자])": "ARG_TYPE",
    'REF("단" & "가")': "CONST_REQUIRED",
    "REF([요금])": "ARG_TYPE",
}
# 기준 날짜 열이 없는 데이터셋에서는 정상 이름도 거부된다.
REJECTED_WITHOUT_BASE_DATE: dict[str, str] = {'REF("단가")': "BASE_DATE_REQUIRED"}


def rows_for(unit: str, shift: int) -> list[Row]:
    """데이터셋 하나의 행: 날짜마다 `x` 값을 돌려 가며 배정한다(`shift`만큼 어긋나게)."""
    dates = DATES[unit]
    return [Row(day, X_VALUES[(index + shift) % len(X_VALUES)]) for index, day in enumerate(dates)]


def values_match(actual: Any, expected: Any, *, approx: bool) -> bool:
    """DB 값(`Decimal`·`bool`·None)과 기대 값 비교. 나눗셈은 상대 오차 1E-12."""
    if expected is None or actual is None:
        return expected is None and actual is None
    if isinstance(expected, bool) or isinstance(actual, bool):
        return actual is expected
    if approx:
        with localcontext() as context:
            context.prec = 200
            scale = max(abs(expected), abs(actual), Decimal(1))
            return abs(actual - expected) <= scale * Decimal("1E-12")
    return Decimal(actual) == expected
