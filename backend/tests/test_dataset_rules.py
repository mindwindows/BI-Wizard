"""열 이름·태그·검증 규칙 정리(05 §1, 06 §3-2·§3-3)와 구조 해시. DB 없이 실행."""

import pytest

from app.core.errors import FieldErrorCode as F
from app.dataset import rules
from app.dataset.hashing import structure_hash

# --- 열 이름 ----


@pytest.mark.parametrize(
    ("name", "problem"),
    [
        ("매출", None),
        ("판매 수량 (개)", None),
        ("a" * 100, None),
        ("a" * 101, F.TOO_LONG),
        ("", F.REQUIRED),
        ("합계[원]", F.BAD_FORMAT),
        ("합계]", F.BAD_FORMAT),
        ('"따옴표"', F.BAD_FORMAT),
        ("줄\n바꿈", F.BAD_FORMAT),
        ("탭\t", F.BAD_FORMAT),
        ("보이지​않는", F.BAD_FORMAT),  # 서식 문자(Cf)
        ("team", F.RESERVED),
        ("팀", F.RESERVED),
        ("row_id", F.RESERVED),
        ("행 번호", F.RESERVED),
        ("TEAM", F.RESERVED),  # 대소문자를 구분하지 않는다
        ("Row_ID", F.RESERVED),
        ("teams", None),
        ("팀명", None),
        ("행번호", None),
    ],
)
def test_column_name_problem(name, problem):
    assert rules.column_name_problem(name) == problem


# --- 태그 ----


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, (None, None)),
        ("", (None, None)),
        ("   ", (None, None)),
        (" 매출 ", ("매출", None)),
        ("a" * 50, ("a" * 50, None)),
        ("a" * 51, (None, F.TOO_LONG)),
        ('x"y', (None, F.BAD_FORMAT)),
        ("x\ny", (None, F.BAD_FORMAT)),
        (5, (None, F.BAD_FORMAT)),
    ],
)
def test_clean_tag(value, expected):
    assert rules.clean_tag(value) == expected


def test_tag_is_nfc_normalized():
    assert rules.clean_tag("한")[0] == "한"


# --- rules ----


def norm(column_type, value):
    return rules.normalize_rules(column_type, value)


def test_empty_rules_become_none_for_every_type_but_choice():
    for column_type in ("text", "number", "date", "boolean"):
        assert norm(column_type, None) == (None, [])
        assert norm(column_type, {}) == (None, [])


def test_number_rules_are_stored_as_decimal_strings():
    out, problems = norm("number", {"min": 0, "max": "1000.50", "decimals": 2})
    assert problems == []
    assert out == {"min": "0", "max": "1000.5", "decimals": 2}
    assert norm("number", {"min": "1.5"}) == ({"min": "1.5"}, [])
    assert norm("number", {"min": "-5.50"}) == ({"min": "-5.5"}, [])  # 서버가 정규화한다
    assert norm("number", {"min": 1000}) == ({"min": "1000"}, [])  # JSON 정수는 허용
    assert norm("number", {"min": "-0"}) == ({"min": "0"}, [])
    assert norm("number", {"min": None, "max": None}) == (None, [])


@pytest.mark.parametrize(
    ("value", "field", "code"),
    [
        ({"min": "abc"}, "rules.min", F.BAD_FORMAT),
        ({"max": True}, "rules.max", F.BAD_FORMAT),
        ({"min": "NaN"}, "rules.min", F.BAD_FORMAT),
        ({"max": "Infinity"}, "rules.max", F.BAD_FORMAT),
        ({"min": " 1"}, "rules.min", F.BAD_FORMAT),
        ({"min": "1" * 39}, "rules.min", F.BAD_FORMAT),
        ({"min": "1e5"}, "rules.min", F.BAD_FORMAT),  # 지수 표기
        ({"min": ".5"}, "rules.min", F.BAD_FORMAT),
        ({"min": "5."}, "rules.min", F.BAD_FORMAT),
        ({"min": "1,000"}, "rules.min", F.BAD_FORMAT),
        # JSON 부동소수점은 거부한다(05 §1 십진 문자열, 2진 근사 배제).
        ({"min": 1.5}, "rules.min", F.BAD_FORMAT),
        ({"max": 0.1234567890123456789}, "rules.max", F.BAD_FORMAT),
        ({"max": 12345678901234567890.0}, "rules.max", F.BAD_FORMAT),
        ({"max": 1e400}, "rules.max", F.BAD_FORMAT),
        # 아주 큰 정수·긴 글자는 변환 전에 거부해 예외로 새지 않는다(파이썬 4300자리 변환 제한).
        ({"min": 10**5000}, "rules.min", F.BAD_FORMAT),
        ({"min": -(10**5000)}, "rules.min", F.BAD_FORMAT),
        ({"min": 10**39}, "rules.min", F.BAD_FORMAT),
        ({"min": "9" * 5000}, "rules.min", F.BAD_FORMAT),
        ({"min": 5, "max": 4}, "rules.max", F.OUT_OF_RANGE),
        ({"decimals": -1}, "rules.decimals", F.OUT_OF_RANGE),
        ({"decimals": 11}, "rules.decimals", F.OUT_OF_RANGE),
        ({"decimals": 1.5}, "rules.decimals", F.BAD_FORMAT),
        ({"decimals": True}, "rules.decimals", F.BAD_FORMAT),
        ({"unknown": 1}, "rules.unknown", F.BAD_FORMAT),
        ({"max_length": 5}, "rules.max_length", F.BAD_FORMAT),
    ],
)
def test_number_rule_problems(value, field, code):
    _, problems = norm("number", value)
    assert (field, code) in problems


def test_parse_decimal_never_raises_on_extreme_input():
    for value in (10**5000, -(10**5000), "9" * 100_000, 1e308, float("nan"), float("inf")):
        assert rules.parse_decimal(value) is None
    assert rules.parse_decimal(10**37) is not None  # 38자리
    assert rules.parse_decimal(10**38) is None  # 39자리
    assert rules.parse_decimal("0." + "1" * 38) is not None
    assert rules.parse_decimal("0." + "1" * 39) is None


def test_number_rule_boundaries():
    assert norm("number", {"decimals": 0})[1] == [] and norm("number", {"decimals": 10})[1] == []
    assert norm("number", {"min": 5, "max": 5})[1] == []
    assert norm("number", {"min": "9" * 38})[1] == []


def test_text_rules():
    assert norm("text", {"max_length": 30}) == ({"max_length": 30}, [])
    assert norm("text", {"max_length": 1})[1] == []
    assert norm("text", {"max_length": 10000})[1] == []
    for bad, code in ((0, F.OUT_OF_RANGE), (10001, F.OUT_OF_RANGE), ("5", F.BAD_FORMAT)):
        assert ("rules.max_length", code) in norm("text", {"max_length": bad})[1]
    assert norm("text", {"min": 1})[1] == [("rules.min", F.BAD_FORMAT)]


def test_date_rules():
    assert norm("date", {"min": "2020-01-01", "max": "2030-12-31"}) == (
        {"min": "2020-01-01", "max": "2030-12-31"},
        [],
    )
    assert norm("date", {"min": "2020-01-01", "max": "2020-01-01"})[1] == []
    for bad in ("2020-13-01", "2020-02-30", "20200101", "2020-1-1", 2020, "2020-01-01T00:00"):
        assert ("rules.min", F.BAD_FORMAT) in norm("date", {"min": bad})[1], bad
    assert ("rules.max", F.OUT_OF_RANGE) in norm(
        "date", {"min": "2021-01-01", "max": "2020-01-01"}
    )[1]


def test_choice_rules_require_options_and_clean_them():
    assert norm("choice", {"options": [" 서울 ", "부산"]}) == ({"options": ["서울", "부산"]}, [])
    assert norm("choice", None)[1] == [("rules.options", F.REQUIRED)]
    assert norm("choice", {})[1] == [("rules.options", F.REQUIRED)]
    assert norm("choice", {"options": []})[1] == [("rules.options", F.REQUIRED)]
    assert norm("choice", {"options": "서울"})[1] == [("rules.options", F.BAD_FORMAT)]
    assert ("rules.options.1", F.BAD_FORMAT) in norm("choice", {"options": ["a", "a"]})[1]
    assert ("rules.options.0", F.REQUIRED) in norm("choice", {"options": ["  "]})[1]
    assert ("rules.options.0", F.TOO_LONG) in norm("choice", {"options": ["x" * 101]})[1]
    assert ("rules.options.0", F.BAD_FORMAT) in norm("choice", {"options": ["a\nb"]})[1]
    assert ("rules.options.0", F.BAD_FORMAT) in norm("choice", {"options": [1]})[1]
    assert ("rules.options", F.TOO_LONG) in norm(
        "choice", {"options": [str(n) for n in range(101)]}
    )[1]
    assert norm("choice", {"options": [str(n) for n in range(100)]})[1] == []


def test_boolean_has_no_rules():
    assert norm("boolean", {"min": 1})[1] == [("rules.min", F.BAD_FORMAT)]


# --- 구조 해시 ----


def column(id, kind="raw", type="number", **extra):
    return {"id": id, "kind": kind, "type": type, **extra}


def test_structure_hash_is_stable_and_order_independent():
    first = structure_hash([column(1), column(2, type="text")])
    assert first == structure_hash([column(2, type="text"), column(1)])
    assert len(first) == 64 and int(first, 16) >= 0


def test_structure_hash_ignores_display_names_and_rules_but_not_structure():
    base = structure_hash([column(1, display_name="a", rules={"min": "1"}, position=0)])
    assert base == structure_hash([column(1, display_name="b", rules=None, position=9)])
    assert base != structure_hash([column(1, type="text")])
    assert base != structure_hash([column(1, kind="formula")])
    assert base != structure_hash([column(1), column(2)])
    assert structure_hash([]) != base
