"""열 검증 규칙(`rules`)·태그의 정리와 검사(05 §1 Column, 06 §3-2). DB와 무관한 순수 함수.

`rules`는 jsonb로 저장하며 열 형별 모양이 정해져 있다.
- number: `{min?, max?, decimals?}`  min·max는 십진 문자열로 저장한다(05 §1: number 값 표현과 같다).
  입력은 십진 문자열 또는 JSON 정수만 받는다(JSON 부동소수점은 거부, `parse_decimal`).
- text: `{max_length?}`
- date: `{min?, max?}`  `YYYY-MM-DD`
- choice: `{options}`  목록 필수, 중복·빈 값 불가
- boolean: 규칙 없음
위반은 (필드, 필드 코드) 목록으로 돌려준다(`VALIDATION_ERROR`의 `details.fields`). 필수·범위는 앱이
검사하는 값 규칙이고 DB 제약이 아니다(06 §3-2 A안). 규칙을 바꿔도 기존 값은 지우지 않는다.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal
from typing import Any

from app.core.errors import FieldErrorCode
from app.core.text import has_control_chars, normalize_text

# 05 §1 이름 규칙·06 §3-3.
DATASET_NAME_MAX = 100
COLUMN_NAME_MAX = 100
TAG_MAX = 50
RESERVED_COLUMN_NAMES = frozenset({"team", "팀", "row_id", "행 번호"})
FORBIDDEN_NAME_CHARS = frozenset('[]"')

NUMBER_DECIMALS_MAX = 10
NUMBER_DIGITS_MAX = 38  # numeric 38자리(07 §4-1)
TEXT_MAX_LENGTH_LIMIT = 10_000
CHOICE_OPTIONS_MAX = 100
CHOICE_OPTION_LENGTH_MAX = 100

Problem = tuple[str, str]  # (필드, 필드 코드)

_DATE_TEXT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def column_name_problem(name: str) -> str | None:
    """정리된(NFC·공백 제거) 열 표시 이름의 문제 코드. 정상이면 None."""
    if not name:
        return FieldErrorCode.REQUIRED
    if len(name) > COLUMN_NAME_MAX:
        return FieldErrorCode.TOO_LONG
    if has_control_chars(name) or any(ch in FORBIDDEN_NAME_CHARS for ch in name):
        return FieldErrorCode.BAD_FORMAT
    if name.casefold() in RESERVED_COLUMN_NAMES:
        return FieldErrorCode.RESERVED
    return None


def clean_tag(value: Any) -> tuple[str | None, str | None]:
    """태그를 정리한다: (정리된 값 또는 None, 문제 코드). 빈 글자는 태그 없음(None)이다."""
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, FieldErrorCode.BAD_FORMAT
    tag = normalize_text(value)
    if tag == "":
        return None, None
    if len(tag) > TAG_MAX:
        return None, FieldErrorCode.TOO_LONG
    if '"' in tag or has_control_chars(tag):
        return None, FieldErrorCode.BAD_FORMAT
    return tag, None


# 십진 표기: 부호(선택) + 정수부 + 소수부(선택). 지수 표기·NaN·무한·공백·`.5`·`5.`는 아니다.
_DECIMAL_TEXT = re.compile(r"[+-]?[0-9]+(?:\.[0-9]+)?")
# 38자리 숫자 + 부호 + 소수점이 들어가는 글자 길이. 이보다 길면 `Decimal`로 바꾸기 전에 거부한다.
_DECIMAL_TEXT_MAX = NUMBER_DIGITS_MAX + 2
# 38자리 정수가 들어가는 비트 수(10^38 < 2^127). 이보다 큰 정수는 `str()`로 바꾸기 전에 거부한다.
_INT_BITS_MAX = 127


def parse_decimal(value: Any) -> Decimal | None:
    """십진 문자열 또는 JSON 정수를 유한 `Decimal`로. 아니면 None (05 §1: number는 십진 문자열).

    JSON 부동소수점 숫자(`1.5`)는 거부한다: 2진 근사가 섞여 값이 달라질 수 있기 때문이다. 불린,
    지수 표기, NaN·무한, 38자리 초과도 None이다. 길이·크기는 `str()`·`Decimal` 변환 **전에** 확인해
    아주 큰 정수(파이썬의 4300자리 변환 제한)가 예외로 새지 않는다.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        if value.bit_length() > _INT_BITS_MAX:
            return None
        text = str(value)
    elif isinstance(value, str):
        if len(value) > _DECIMAL_TEXT_MAX or _DECIMAL_TEXT.fullmatch(value) is None:
            return None
        text = value
    else:  # float 등
        return None
    number = Decimal(text)
    digits = number.as_tuple()
    exponent = digits.exponent if isinstance(digits.exponent, int) else 0
    if len(digits.digits) + max(exponent, 0) > NUMBER_DIGITS_MAX or -exponent > NUMBER_DIGITS_MAX:
        return None
    return number


def _decimal_text(number: Decimal) -> str:
    if number == 0:
        return "0"
    return format(number.normalize(), "f")


def _integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def parse_iso_date(value: Any) -> date | None:
    if not isinstance(value, str) or _DATE_TEXT.fullmatch(value) is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _unknown_keys(rules: dict[str, Any], allowed: set[str]) -> list[Problem]:
    return [(f"rules.{key}", FieldErrorCode.BAD_FORMAT) for key in rules if key not in allowed]


def _number_rules(rules: dict[str, Any]) -> tuple[dict[str, Any], list[Problem]]:
    problems = _unknown_keys(rules, {"min", "max", "decimals"})
    out: dict[str, Any] = {}
    bounds: dict[str, Decimal] = {}
    for key in ("min", "max"):
        if key in rules and rules[key] is not None:
            number = parse_decimal(rules[key])
            if number is None:
                problems.append((f"rules.{key}", FieldErrorCode.BAD_FORMAT))
            else:
                bounds[key] = number
                out[key] = _decimal_text(number)
    if "min" in bounds and "max" in bounds and bounds["min"] > bounds["max"]:
        problems.append(("rules.max", FieldErrorCode.OUT_OF_RANGE))
    if "decimals" in rules and rules["decimals"] is not None:
        decimals = _integer(rules["decimals"])
        if decimals is None:
            problems.append(("rules.decimals", FieldErrorCode.BAD_FORMAT))
        elif not 0 <= decimals <= NUMBER_DECIMALS_MAX:
            problems.append(("rules.decimals", FieldErrorCode.OUT_OF_RANGE))
        else:
            out["decimals"] = decimals
    return out, problems


def _text_rules(rules: dict[str, Any]) -> tuple[dict[str, Any], list[Problem]]:
    problems = _unknown_keys(rules, {"max_length"})
    out: dict[str, Any] = {}
    if "max_length" in rules and rules["max_length"] is not None:
        length = _integer(rules["max_length"])
        if length is None:
            problems.append(("rules.max_length", FieldErrorCode.BAD_FORMAT))
        elif not 1 <= length <= TEXT_MAX_LENGTH_LIMIT:
            problems.append(("rules.max_length", FieldErrorCode.OUT_OF_RANGE))
        else:
            out["max_length"] = length
    return out, problems


def _date_rules(rules: dict[str, Any]) -> tuple[dict[str, Any], list[Problem]]:
    problems = _unknown_keys(rules, {"min", "max"})
    out: dict[str, Any] = {}
    parsed: dict[str, date] = {}
    for key in ("min", "max"):
        if key in rules and rules[key] is not None:
            day = parse_iso_date(rules[key])
            if day is None:
                problems.append((f"rules.{key}", FieldErrorCode.BAD_FORMAT))
            else:
                parsed[key] = day
                out[key] = day.isoformat()
    if "min" in parsed and "max" in parsed and parsed["min"] > parsed["max"]:
        problems.append(("rules.max", FieldErrorCode.OUT_OF_RANGE))
    return out, problems


def _choice_rules(rules: dict[str, Any]) -> tuple[dict[str, Any], list[Problem]]:
    problems = _unknown_keys(rules, {"options"})
    raw = rules.get("options")
    if raw is None:
        problems.append(("rules.options", FieldErrorCode.REQUIRED))
        return {}, problems
    if not isinstance(raw, list):
        problems.append(("rules.options", FieldErrorCode.BAD_FORMAT))
        return {}, problems
    if not raw:
        problems.append(("rules.options", FieldErrorCode.REQUIRED))
        return {}, problems
    if len(raw) > CHOICE_OPTIONS_MAX:
        problems.append(("rules.options", FieldErrorCode.TOO_LONG))
        return {}, problems
    options: list[str] = []
    for index, item in enumerate(raw):
        field = f"rules.options.{index}"
        if not isinstance(item, str):
            problems.append((field, FieldErrorCode.BAD_FORMAT))
            continue
        option = unicodedata.normalize("NFC", item).strip()
        if not option:
            problems.append((field, FieldErrorCode.REQUIRED))
        elif len(option) > CHOICE_OPTION_LENGTH_MAX:
            problems.append((field, FieldErrorCode.TOO_LONG))
        elif has_control_chars(option):
            problems.append((field, FieldErrorCode.BAD_FORMAT))
        elif option in options:
            problems.append((field, FieldErrorCode.BAD_FORMAT))  # 중복
        else:
            options.append(option)
    return ({"options": options} if not problems else {}), problems


_RULE_BUILDERS = {
    "number": _number_rules,
    "text": _text_rules,
    "date": _date_rules,
    "choice": _choice_rules,
}


def normalize_rules(
    column_type: str, rules: dict[str, Any] | None
) -> tuple[dict[str, Any] | None, list[Problem]]:
    """열 형에 맞게 `rules`를 검사하고 저장 모양으로 정리한다. 규칙이 비면 None.

    choice는 선택 목록이 필수다. boolean에는 규칙이 없다(키가 있으면 위반).
    """
    if rules is None:
        rules = {}
    if column_type == "choice":
        out, problems = _choice_rules(rules)
        return (out or None), problems
    builder = _RULE_BUILDERS.get(column_type)
    if builder is None:  # boolean 또는 알 수 없는 형: 규칙 키가 하나라도 있으면 위반
        return None, [(f"rules.{key}", FieldErrorCode.BAD_FORMAT) for key in rules]
    out, problems = builder(rules)
    return (out or None), problems
