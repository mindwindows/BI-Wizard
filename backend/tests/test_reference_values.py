"""기준값 규칙 함수(`app/reference/values.py`)와 수식 엔진 규칙의 대조(06 §2-2, 07 §4-1·§4-2).

`reference`는 `formula`를 import할 수 없어(04 §2-2) 이름·숫자 규칙을 다시 썼다. 두 규칙이 어긋나지
않도록 같은 입력을 양쪽에 넣어 결과가 같음을 확인한다(DB 없음).
"""

from __future__ import annotations

import unicodedata
from decimal import Decimal

import pytest

from app.core.errors import FieldErrorCode
from app.formula.literals import normalize_text_constant, number_problem, text_constant_problem
from app.reference import values as rules

NAMES = [
    "전기요금",
    "전기요금_A팀",
    "a b",
    "O'Brien",
    "100%",
    "가" * 50,
    "é",
    unicodedata.normalize("NFD", "전기요금"),
    "요금[A]",
    '요금"A"',
    "요금\\A",
    "요금\nA",
    "요금\tA",
    "요금\x00A",
    "요금\u200bA",  # Cf
    "요금\u2028A",  # Zl
    "요금\u2029A",  # Zp
    "요금\ud800A",  # 서로게이트
    "요금\u00a0A",  # 줄 바꿈 없는 공백(Zs)은 서식 문자가 아니다
    "😀 요금",
    "요금\ue000A",  # Co: 수식 상수는 허용하고 항목 이름은 거부한다
    "요금\u0378A",  # Cn
]


@pytest.mark.parametrize("name", NAMES)
def test_item_name_rules_are_at_least_as_strict_as_the_formula_text_constant_rules(name):
    """수식 글자 상수로 못 쓰는 이름은 항목 이름으로도 못 쓴다(역은 `[` `]` `"`만 더 엄격)."""
    constant_problem = text_constant_problem(normalize_text_constant(name)) is not None
    if constant_problem:
        assert rules.name_has_forbidden_chars(name), repr(name)
    if rules.name_has_forbidden_chars(name) and not constant_problem:
        # 더 엄격한 곳은 대괄호·따옴표와 사용 영역(Co)·미지정(Cn) 문자뿐이다(아래 시험이 명시한다)
        assert any(ch in name for ch in '[]"') or any(
            unicodedata.category(ch) in {"Co", "Cn"} for ch in name
        ), repr(name)


@pytest.mark.parametrize(
    ("name", "why"),
    [
        ("요금\ue000A", "Co(사용자 영역)"),
        ("요금\u0378A", "Cn(미지정 코드 포인트)"),
        ("요금[A]", "대괄호(수식 문법이 이름을 다시 읽는 데 필요)"),
        ('요금"A"', "따옴표(같은 이유)"),
    ],
)
def test_reference_is_stricter_than_the_formula_constant_rules_for_these_characters(name, why):
    """reference 이름 규칙이 수식 글자 상수 규칙보다 **더 엄격한** 곳을 명시한다.

    수식 상수는 이 글자를 허용하지만(`text_constant_problem`이 None) 항목 이름으로는 거부한다.
    반대(수식 상수는 거부하는데 이름은 허용)는 위 시험이 막는다.
    """
    assert text_constant_problem(normalize_text_constant(name)) is None, why
    assert rules.name_has_forbidden_chars(name), why


NUMBERS = [
    "0",
    "1",
    "-1",
    "+1",
    "0.5",
    "1.50",
    "007",
    "9" * 38,
    "9" * 39,
    "-" + "9" * 38,
    "0." + "1" * 38,
    "0." + "1" * 39,
    "1" + "0" * 37 + ".1",  # 정수부 38 + 소수 1 = 39자리
    "12345678901234567890123456789012345678",
    "0.00000000000000000000000000000000000001",
]


@pytest.mark.parametrize("text", NUMBERS)
def test_value_digit_limit_matches_the_formula_number_rule(text):
    """38자리(정수부+소수부) 한도는 수식 숫자 상수 규칙(`number_problem`)과 같다."""
    value, code = rules.parse_value(text)
    expected = number_problem(Decimal(text))
    assert (code == FieldErrorCode.OUT_OF_RANGE) == (expected is not None), text
    assert (value is not None) == (expected is None), text
    if value is not None:
        assert value == Decimal(text)


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("", FieldErrorCode.REQUIRED),
        ("   ", FieldErrorCode.REQUIRED),
        ("abc", FieldErrorCode.BAD_FORMAT),
        ("1e3", FieldErrorCode.BAD_FORMAT),
        ("1E3", FieldErrorCode.BAD_FORMAT),
        ("NaN", FieldErrorCode.BAD_FORMAT),
        ("nan", FieldErrorCode.BAD_FORMAT),
        ("Infinity", FieldErrorCode.BAD_FORMAT),
        ("-inf", FieldErrorCode.BAD_FORMAT),
        (".5", FieldErrorCode.BAD_FORMAT),
        ("5.", FieldErrorCode.BAD_FORMAT),
        ("1,000", FieldErrorCode.BAD_FORMAT),
        ("1 000", FieldErrorCode.BAD_FORMAT),
        ("--1", FieldErrorCode.BAD_FORMAT),
        ("\uff11\uff12", FieldErrorCode.BAD_FORMAT),  # 전각 숫자
        ("\u0663", FieldErrorCode.BAD_FORMAT),  # 아라비아 숫자
        ("1" * 500, FieldErrorCode.BAD_FORMAT),  # 변환 전에 길이로 거른다
    ],
)
def test_value_format_codes(text, code):
    assert rules.parse_value(text) == (None, code)


def test_value_keeps_the_written_digits_and_surrounding_spaces_are_ignored():
    value, code = rules.parse_value("  1234.50 ")
    assert code is None and rules.decimal_text(value) == "1234.50"
    assert rules.decimal_text(Decimal("1E-7")) == "0.0000001"  # 지수 표기 없음
    assert rules.decimal_text(Decimal("1E+3")) == "1000"


@pytest.mark.parametrize(
    ("year", "problem"),
    [(1899, "OUT_OF_RANGE"), (1900, None), (2026, None), (9999, None), (10000, "OUT_OF_RANGE")],
)
def test_year_range_matches_the_check_constraint(year, problem):
    assert rules.year_problem(year) == problem


def test_limits_come_from_db_metadata_constants():
    from app.db_metadata import (
        REFERENCE_DESCRIPTION_MAX_LENGTH,
        REFERENCE_NAME_MAX_LENGTH,
        REFERENCE_YEAR_MAX,
        REFERENCE_YEAR_MIN,
    )

    assert (rules.NAME_MAX_LENGTH, rules.DESCRIPTION_MAX_LENGTH) == (
        REFERENCE_NAME_MAX_LENGTH,
        REFERENCE_DESCRIPTION_MAX_LENGTH,
    )
    assert (rules.YEAR_MIN, rules.YEAR_MAX) == (REFERENCE_YEAR_MIN, REFERENCE_YEAR_MAX)
    assert (rules.NAME_MAX_LENGTH, rules.DESCRIPTION_MAX_LENGTH) == (50, 200)
    assert (rules.YEAR_MIN, rules.YEAR_MAX) == (1900, 9999)
    # 함수 사전의 REF 인수 길이 상한도 같은 50자다(항목 이름이 곧 REF("…")의 인수다)
    from app.formula.functions import REF_MAX_NAME_LENGTH

    assert REF_MAX_NAME_LENGTH == rules.NAME_MAX_LENGTH


def test_core_metadata_matches_the_dictionary_cell_error_for_missing_values():
    from app.formula.errors import CELL_ERROR_BY_NUMBER, CELL_ERROR_MESSAGES_KO

    assert CELL_ERROR_BY_NUMBER[4] == "E4"
    assert "기준값" in CELL_ERROR_MESSAGES_KO["E4"] and "연도" in CELL_ERROR_MESSAGES_KO["E4"]
