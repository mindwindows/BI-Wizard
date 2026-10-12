"""열 타입별 값 해석·재검증 시험(05 §1 값 표현, 06 §3, `app/entry/values.py`). DB 없이 돈다."""

from datetime import date
from decimal import Decimal

import pytest

from app.core.errors import FieldErrorCode as F
from app.entry.values import CellSpec, format_value, is_period_start, parse_cell


def spec(column_type: str, rules=None, *, required=False, base=False, unit="day") -> CellSpec:
    return CellSpec(1, column_type, required, rules, is_base=base, date_unit=unit)


def test_blank_input_is_unentered_for_every_type():
    for column_type in ("text", "number", "date", "boolean", "choice"):
        for blank in (None, "", "   ", "\t "):
            assert parse_cell(spec(column_type, {"options": ["a"]}), blank) == (None, None)


# --- number ----


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1234.50", Decimal("1234.50")),
        ("-5", Decimal("-5")),
        ("+7", Decimal("7")),
        ("0", Decimal("0")),
        (" 12.5 ", Decimal("12.5")),  # 앞뒤 공백은 지운다
        (1000, Decimal("1000")),  # JSON 정수
        (0, Decimal("0")),
        ("9" * 38, Decimal("9" * 38)),
        ("0." + "1" * 38, Decimal("0." + "1" * 38)),
    ],
)
def test_number_accepts_decimal_strings_and_json_integers(raw, expected):
    value, code = parse_cell(spec("number"), raw)
    assert code is None and value == expected


BAD_NUMBERS = [
    1.5,  # JSON 부동소수점 거부
    12345678901234567890.123,
    True,
    "1e5",
    "1E5",
    "1e-3",
    "NaN",
    "nan",
    "Infinity",
    "-Infinity",
    "inf",
    "abc",
    "1,000",
    "1 000",
    ".5",
    "5.",
    "--5",
    "0x10",
    "\uff11\uff12\uff13",  # 전각 숫자
    "9" * 39,
    "9" * 100_000,
    10**39,
    10**5000,
    -(10**5000),
    [],
    {},
]


@pytest.mark.parametrize("raw", BAD_NUMBERS, ids=[f"bad{n}" for n in range(len(BAD_NUMBERS))])
def test_number_rejects_everything_else_without_raising(raw):
    assert parse_cell(spec("number"), raw) == (None, F.BAD_FORMAT)


def test_number_decimals_range_rules():
    rules = {"min": "0", "max": "100.5", "decimals": 2}
    s = spec("number", rules)
    assert parse_cell(s, "100.50")[1] is None  # 뒤 0은 자릿수에 세지 않는다
    assert parse_cell(s, "100.5")[1] is None
    assert parse_cell(s, "0")[1] is None
    assert parse_cell(s, "1.234") == (None, F.OUT_OF_RANGE)  # 소수 자릿수 초과
    assert parse_cell(s, "-0.01") == (None, F.OUT_OF_RANGE)
    assert parse_cell(s, "100.51") == (None, F.OUT_OF_RANGE)
    assert parse_cell(spec("number", {"decimals": 0}), "5.0")[1] is None
    assert parse_cell(spec("number", {"decimals": 0}), "5.1") == (None, F.OUT_OF_RANGE)


def test_number_check_rules_false_skips_range_but_not_format():
    s = spec("number", {"max": "10"})
    assert parse_cell(s, "11", check_rules=False) == (Decimal("11"), None)
    assert parse_cell(s, "abc", check_rules=False) == (None, F.BAD_FORMAT)


# --- date ----


def test_date_accepts_iso_dates_only():
    assert parse_cell(spec("date"), "2026-03-15") == (date(2026, 3, 15), None)
    for raw in (
        "2026-3-15",
        "2026/03/15",
        "20260315",
        "2026-02-30",
        "2026-13-01",
        "2026-03-15T00:00",
        "\uff12\uff10\uff12\uff16-03-15",  # 전각 숫자
        20260315,
        1.5,
        True,
        "0000-01-01",
    ):
        assert parse_cell(spec("date"), raw) == (None, F.BAD_FORMAT), raw


@pytest.mark.parametrize(
    ("unit", "raw", "code"),
    [
        ("day", "2026-03-15", None),
        ("month", "2026-03-01", None),
        ("month", "2026-03-02", F.NOT_PERIOD_START),
        ("month", "2026-03-31", F.NOT_PERIOD_START),
        ("year", "2026-01-01", None),
        ("year", "2026-02-01", F.NOT_PERIOD_START),
        ("year", "2026-01-02", F.NOT_PERIOD_START),
    ],
)
def test_base_date_column_accepts_only_the_first_day_of_the_period(unit, raw, code):
    assert parse_cell(spec("date", base=True, unit=unit), raw)[1] == code
    # 기준 날짜 열이 아닌 날짜 열은 날짜 단위와 무관하다.
    assert parse_cell(spec("date", unit=unit), raw)[1] is None


def test_is_period_start():
    assert is_period_start(date(2026, 5, 17), "day")
    assert is_period_start(date(2026, 5, 1), "month") and not is_period_start(
        date(2026, 5, 2), "month"
    )
    assert is_period_start(date(2026, 1, 1), "year") and not is_period_start(
        date(2026, 2, 1), "year"
    )


def test_date_min_max_rules():
    s = spec("date", {"min": "2020-01-01", "max": "2030-12-31"})
    assert parse_cell(s, "2020-01-01")[1] is None and parse_cell(s, "2030-12-31")[1] is None
    assert parse_cell(s, "2019-12-31") == (None, F.OUT_OF_RANGE)
    assert parse_cell(s, "2031-01-01") == (None, F.OUT_OF_RANGE)
    assert parse_cell(s, "2019-12-31", check_rules=False)[1] is None


def test_date_expected_parse_skips_period_start_check():
    s = spec("date", base=True, unit="month")
    assert parse_cell(s, "2026-03-15", check_rules=False) == (date(2026, 3, 15), None)


# --- boolean ----


@pytest.mark.parametrize(
    "raw",
    [True, "true", "TRUE", "True", "1", "y", "Y", "yes", "YES", "예", "참", " true "],
)
def test_boolean_true_spellings(raw):
    assert parse_cell(spec("boolean"), raw) == (True, None)


@pytest.mark.parametrize(
    "raw", [False, "false", "FALSE", "False", "0", "n", "N", "no", "NO", "아니오", "거짓"]
)
def test_boolean_false_spellings(raw):
    assert parse_cell(spec("boolean"), raw) == (False, None)


@pytest.mark.parametrize("raw", ["maybe", "2", "t", "아니요", "x" * 1000, 1, 0, 1.0, [], {}])
def test_boolean_rejects_everything_else(raw):
    assert parse_cell(spec("boolean"), raw) == (None, F.BAD_FORMAT)


# --- choice ----


def test_choice_must_be_one_of_the_options_exactly():
    s = spec("choice", {"options": ["서울", "부산", "Busan"]})
    assert parse_cell(s, "서울") == ("서울", None)
    assert parse_cell(s, "  부산 ") == ("부산", None)  # 공백은 지운다
    assert parse_cell(s, "대구") == (None, F.NOT_IN_OPTIONS)
    assert parse_cell(s, "busan") == (None, F.NOT_IN_OPTIONS)  # 대소문자 구분
    assert parse_cell(s, 5) == (None, F.BAD_FORMAT)
    assert parse_cell(s, "대구", check_rules=False) == ("대구", None)


def test_choice_matches_after_nfc_normalization():
    decomposed = "한글"  # 이미 NFC
    import unicodedata

    nfd = unicodedata.normalize("NFD", decomposed)
    assert nfd != decomposed
    assert parse_cell(spec("choice", {"options": [decomposed]}), nfd) == (decomposed, None)


# --- text ----


def test_text_is_normalized_and_trimmed():
    import unicodedata

    nfd = unicodedata.normalize("NFD", "가나다")
    value, code = parse_cell(spec("text"), f"  {nfd}  ")
    assert code is None and value == "가나다" and unicodedata.is_normalized("NFC", value)
    assert parse_cell(spec("text"), "a\r\n") == ("a", None)  # 붙여넣기의 줄 끝은 공백처럼 지운다


@pytest.mark.parametrize("raw", ["a\x00b", "a\nb", "a\tb", "a\x1fb", "a​b", "a‮b", "a\x7fb"])
def test_text_rejects_control_and_format_characters(raw):
    assert parse_cell(spec("text"), raw) == (None, F.BAD_FORMAT)


def test_text_length_rules():
    s = spec("text", {"max_length": 5})
    assert parse_cell(s, "12345") == ("12345", None)
    assert parse_cell(s, "123456") == (None, F.TOO_LONG)
    assert parse_cell(s, "가" * 5)[1] is None and parse_cell(s, "가" * 6)[1] == F.TOO_LONG
    assert parse_cell(s, "123456", check_rules=False)[1] is None  # 이전 값은 규칙을 안 본다
    # 규칙이 없어도 상수 상한(1만자)이 있다.
    assert parse_cell(spec("text"), "a" * 10_000)[1] is None
    assert parse_cell(spec("text"), "a" * 10_001) == (None, F.TOO_LONG)
    assert parse_cell(spec("text"), "a" * 1_000_000) == (None, F.TOO_LONG)


def test_text_rejects_non_strings():
    for raw in (5, 1.5, True, [], {}):
        assert parse_cell(spec("text"), raw) == (None, F.BAD_FORMAT)


def test_unknown_type_cannot_be_entered():
    assert parse_cell(spec("reference"), "x") == (None, F.BAD_FORMAT)


# --- 응답 표현 ----


def test_format_value_follows_the_api_value_representation():
    assert format_value("number", Decimal("1234.50")) == "1234.50"
    assert format_value("number", Decimal("1E+2")) == "100"
    assert format_value("number", Decimal("-0.5")) == "-0.5"
    assert format_value("number", None) is None
    assert format_value("date", date(2026, 3, 1)) == "2026-03-01"
    assert format_value("boolean", True) is True and format_value("boolean", False) is False
    assert format_value("text", "글") == "글" and format_value("choice", "서울") == "서울"
    for column_type in ("number", "date", "boolean", "text", "choice"):
        assert format_value(column_type, None) is None
