"""기준값 항목 이름·연도·값 규칙(06 §2-2, 05 R2·R4·R5). DB와 무관한 순수 함수.

`reference`는 `formula`·`dataset`을 import하지 않는다(04 §2-2 층 규칙). 그래서 수식 엔진의 글자
상수 규칙(07 §4-2)과 숫자 규칙(07 §4-1 `number_problem`)을 **같은 규칙으로 다시 쓰고**, 두 규칙이
어긋나지 않는지는 시험(`tests/test_reference_values.py`)이 같은 입력으로 대조한다.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal

from app.core.errors import FieldErrorCode
from app.db_metadata import (
    REFERENCE_DESCRIPTION_MAX_LENGTH,
    REFERENCE_NAME_MAX_LENGTH,
    REFERENCE_YEAR_MAX,
    REFERENCE_YEAR_MIN,
)

NAME_MAX_LENGTH = REFERENCE_NAME_MAX_LENGTH
DESCRIPTION_MAX_LENGTH = REFERENCE_DESCRIPTION_MAX_LENGTH
YEAR_MIN = REFERENCE_YEAR_MIN
YEAR_MAX = REFERENCE_YEAR_MAX
VALUE_DIGITS_MAX = 38  # 07 §4-1 `number_problem`과 같은 자릿수 한도

# 이름에 못 쓰는 문자: 수식 `REF("…")`의 글자 상수 규칙(07 §4-2)과 수식 문법이 이름을 그대로
# 다시 읽는 데 필요한 금지(`[` `]` `"`)를 합친 것. NUL·서로게이트·제어(Cc)·서식(Cf)·
# 줄/문단 구분(Zl·Zp)과 역슬래시도 거부한다.
_FORBIDDEN_NAME_CHARS = frozenset('[]"\\')
_FORBIDDEN_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})

# 십진 표기: 부호(선택) + 정수부 + 소수부(선택). 지수·NaN·무한·공백·`.5`·`5.`는 아니다.
_DECIMAL_TEXT = re.compile(r"[+-]?[0-9]+(?:\.[0-9]+)?")
_DECIMAL_TEXT_MAX = 200  # 변환 전에 아주 긴 글자를 거른다(자릿수 검사는 변환 뒤)


def name_has_forbidden_chars(name: str) -> bool:
    """항목 이름에 `[` `]` `"` 역슬래시나 눈에 안 보이는·제어 문자가 있으면 True."""
    return any(
        ch in _FORBIDDEN_NAME_CHARS or unicodedata.category(ch) in _FORBIDDEN_CATEGORIES
        for ch in name
    )


def parse_value(raw: str) -> tuple[Decimal | None, str | None]:
    """기준값 글자를 유한 `Decimal`로: (값, 필드 코드).

    코드는 `REQUIRED`·`BAD_FORMAT`·`OUT_OF_RANGE`.

    - 빈 글자·공백뿐 -> `REQUIRED`
    - 십진 표기가 아님(지수·NaN·무한·문자 섞임) -> `BAD_FORMAT`
    - 38자리(정수부+소수부) 초과 -> `OUT_OF_RANGE`
    """
    text = raw.strip()
    if text == "":
        return None, FieldErrorCode.REQUIRED
    if len(text) > _DECIMAL_TEXT_MAX or _DECIMAL_TEXT.fullmatch(text) is None:
        return None, FieldErrorCode.BAD_FORMAT
    number = Decimal(text)
    _sign, digits, exponent = number.as_tuple()
    if not isinstance(exponent, int):  # 유한한 십진 표기라 일어나지 않는다
        return None, FieldErrorCode.BAD_FORMAT
    if len(digits) > VALUE_DIGITS_MAX or -exponent > VALUE_DIGITS_MAX:
        return None, FieldErrorCode.OUT_OF_RANGE
    return number, None


def year_problem(year: int) -> str | None:
    """연도가 1900~9999 밖이면 `OUT_OF_RANGE`(`ck_reference_values_year`와 같은 범위)."""
    if not YEAR_MIN <= year <= YEAR_MAX:
        return FieldErrorCode.OUT_OF_RANGE
    return None


def decimal_text(value: Decimal) -> str:
    """응답·감사에 쓰는 십진 문자열(지수 표기 없음, 쓴 자릿수 그대로: `1234.50`)."""
    return format(value, "f")
