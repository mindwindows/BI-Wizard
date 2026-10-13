"""열 타입별 값 해석·재검증(05 §1 값 표현, 06 §3-1·§3-2). DB와 무관한 순수 함수.

`parse_cell`은 JSON 값(또는 붙여넣기의 글자)을 열 타입의 저장 값으로 바꾸고, 규칙 위반이면
필드 코드(`FieldErrorCode`)를 돌려준다. 빈 입력(`null`, 빈 글자)은 미입력(`None`)이며 필수 여부는
호출한 쪽이 판정한다.

타입별 규칙(서버가 항상 재검증하며 화면 검사는 편의다):
- text: 글자만. NFC·앞뒤 공백 제거 후 제어·서식 문자 불가(BAD_FORMAT). 길이는 `rules.max_length`,
  없으면 상수 상한 1만자(TOO_LONG).
- number: 십진 문자열 또는 JSON 정수. JSON 부동소수점·지수 표기·NaN·무한·38자리 초과는
  BAD_FORMAT. `rules.decimals`(뒤 0 제외 소수 자릿수)·`min`·`max` 위반은 OUT_OF_RANGE.
- date: `YYYY-MM-DD`(없는 날짜는 BAD_FORMAT). 기준 날짜 열은 날짜 단위가 월·연이면 기간
  첫날만(NOT_PERIOD_START). `rules.min`·`max` 위반은 OUT_OF_RANGE.
- boolean: JSON `true`/`false` 또는 글자 `true`·`false`·`1`·`0`·`y`·`n`·`yes`·`no`·`예`·
  `아니오`·`참`·`거짓`(대소문자 무시). 그 밖은 BAD_FORMAT.
- choice: `rules.options` 안의 글자(NFC·공백 제거 후 정확히 일치, 대소문자 구분). 밖이면
  NOT_IN_OPTIONS.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from app.core.errors import FieldErrorCode
from app.core.text import has_control_chars, normalize_text
from app.dataset import rules as rule_helpers

# 규칙에 `max_length`가 없는 글자 열의 상수 상한(정의 규칙의 최댓값과 같다).
TEXT_DEFAULT_MAX_LENGTH = rule_helpers.TEXT_MAX_LENGTH_LIMIT
# 아주 긴 입력을 정규화하기 전에 거르는 안전 상한(글자 수).
_RAW_TEXT_HARD_LIMIT = 2 * TEXT_DEFAULT_MAX_LENGTH

_TRUE_WORDS = frozenset({"true", "1", "y", "yes", "예", "참"})
_FALSE_WORDS = frozenset({"false", "0", "n", "no", "아니오", "거짓"})


@dataclass(frozen=True)
class CellSpec:
    """한 열의 해석 맥락. `required`는 기준 날짜 열을 이미 필수로 취급한 값이다."""

    column_id: int
    type: str
    required: bool
    rules: dict[str, Any] | None = None
    is_base: bool = False  # 기준 날짜 열인가
    date_unit: str = "day"

    @property
    def rule(self) -> dict[str, Any]:
        return self.rules or {}


Parsed = tuple[Any, str | None]  # (저장 값, 필드 코드 또는 None)

_BAD: Parsed = (None, FieldErrorCode.BAD_FORMAT)


def _blank(raw: Any) -> bool:
    return raw is None or (isinstance(raw, str) and not raw.strip())


def _parse_text(spec: CellSpec, raw: Any, check_rules: bool) -> Parsed:
    if not isinstance(raw, str):
        return _BAD
    if len(raw) > _RAW_TEXT_HARD_LIMIT:
        return None, FieldErrorCode.TOO_LONG
    text = normalize_text(raw)
    if has_control_chars(text):
        return _BAD
    limit = spec.rule.get("max_length", TEXT_DEFAULT_MAX_LENGTH) if check_rules else None
    if limit is None:
        limit = TEXT_DEFAULT_MAX_LENGTH
    if len(text) > limit:
        return None, FieldErrorCode.TOO_LONG
    return text, None


def _parse_choice(spec: CellSpec, raw: Any, check_rules: bool) -> Parsed:
    if not isinstance(raw, str):
        return _BAD
    if len(raw) > _RAW_TEXT_HARD_LIMIT:
        return None, FieldErrorCode.NOT_IN_OPTIONS if check_rules else FieldErrorCode.BAD_FORMAT
    text = normalize_text(raw)
    if has_control_chars(text):
        return _BAD
    if check_rules and text not in spec.rule.get("options", []):
        return None, FieldErrorCode.NOT_IN_OPTIONS
    return text, None


def _parse_number(spec: CellSpec, raw: Any, check_rules: bool) -> Parsed:
    if isinstance(raw, str):
        raw = raw.strip()
    number = rule_helpers.parse_decimal(raw)  # float·bool·지수·NaN·38자리 초과는 None
    if number is None:
        return _BAD
    if not check_rules:
        return number, None
    rule = spec.rule
    decimals = rule.get("decimals")
    if decimals is not None:
        exponent = number.normalize().as_tuple().exponent
        if isinstance(exponent, int) and -exponent > decimals:
            return None, FieldErrorCode.OUT_OF_RANGE
    if "min" in rule and number < Decimal(rule["min"]):
        return None, FieldErrorCode.OUT_OF_RANGE
    if "max" in rule and number > Decimal(rule["max"]):
        return None, FieldErrorCode.OUT_OF_RANGE
    return number, None


def is_period_start(day: date, date_unit: str) -> bool:
    """날짜가 날짜 단위의 기간 첫날인가(일 단위는 항상 참, 월은 1일, 연은 1월 1일)."""
    if date_unit == "month":
        return day.day == 1
    if date_unit == "year":
        return day.month == 1 and day.day == 1
    return True


def _parse_date(spec: CellSpec, raw: Any, check_rules: bool) -> Parsed:
    if isinstance(raw, str):
        raw = raw.strip()
    day = rule_helpers.parse_iso_date(raw)
    if day is None:
        return _BAD
    if not check_rules:
        return day, None
    if spec.is_base and not is_period_start(day, spec.date_unit):
        return None, FieldErrorCode.NOT_PERIOD_START
    rule = spec.rule
    if "min" in rule and day < date.fromisoformat(rule["min"]):
        return None, FieldErrorCode.OUT_OF_RANGE
    if "max" in rule and day > date.fromisoformat(rule["max"]):
        return None, FieldErrorCode.OUT_OF_RANGE
    return day, None


def _parse_boolean(spec: CellSpec, raw: Any, check_rules: bool) -> Parsed:
    if isinstance(raw, bool):
        return raw, None
    if not isinstance(raw, str) or len(raw) > 32:
        return _BAD
    word = raw.strip().casefold()
    if word in _TRUE_WORDS:
        return True, None
    if word in _FALSE_WORDS:
        return False, None
    return _BAD


_PARSERS = {
    "text": _parse_text,
    "choice": _parse_choice,
    "number": _parse_number,
    "date": _parse_date,
    "boolean": _parse_boolean,
}


def parse_cell(spec: CellSpec, raw: Any, *, check_rules: bool = True) -> Parsed:
    """칸 하나를 해석한다: (저장 값, 필드 코드). 빈 입력은 (None, None).

    `check_rules=False`는 **이전 값(`expected`)** 해석용이다: 형식만 확인하고 범위·선택 목록·
    기간 첫날은 보지 않는다(규칙을 바꾸기 전에 들어간 값도 그대로 두기 때문, 06 §3-2).
    """
    if _blank(raw):
        return None, None
    parser = _PARSERS.get(spec.type)
    if parser is None:  # 알 수 없는 형은 입력할 수 없다.
        return _BAD
    return parser(spec, raw, check_rules)


def format_value(column_type: str, value: Any) -> Any:
    """DB 값을 응답 값으로(05 §1): number 십진 문자열, date `YYYY-MM-DD`, 미입력 `null`."""
    if value is None:
        return None
    if column_type == "number":
        return format(Decimal(value), "f")
    if column_type == "date":
        return value.isoformat()
    if column_type == "boolean":
        return bool(value)
    return str(value)
