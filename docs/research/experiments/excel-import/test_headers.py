"""headers.py 시제품의 사례표 시험. 사용: python test_headers.py  (pytest 불필요, 실패하면 종료 코드 1)

사례는 설계 문서 날짜 해석 표의 근거다. 합성 사례이며 실제 회사 파일의 머리글 분포가 아니다.
"""

import sys
from datetime import date, datetime

from headers import assign_years, parse_period_header, suggest_year

D = date
CASES = [
    # (설명, 값, 옵션, 기대 결과(날짜 또는 사유 코드))
    ("진짜 날짜 셀", datetime(2026, 1, 1), {}, D(2026, 1, 1)),
    ("진짜 날짜 셀(월 중간 -> 첫날로)", datetime(2026, 3, 17), {}, D(2026, 3, 1)),
    ("진짜 날짜 셀, 연 단위", datetime(2026, 5, 1), {"unit": "year"}, D(2026, 1, 1)),
    ("엑셀 일련번호 46023(=2026-01-01)", 46023, {}, D(2026, 1, 1)),
    ("숫자 3 + 연도 힌트", 3, {"year_hint": 2026}, D(2026, 3, 1)),
    ("숫자 3, 연도 힌트 없음", 3, {}, "NEEDS_YEAR"),
    ("숫자 2026, 연 단위", 2026, {"unit": "year"}, D(2026, 1, 1)),
    ("소수 3.5", 3.5, {}, "BAD_FORMAT"),
    ("1월 + 연도 힌트", "1월", {"year_hint": 2026}, D(2026, 1, 1)),
    ("12월 + 공백", " 12 월 ", {"year_hint": 2026}, D(2026, 12, 1)),
    ("1월, 힌트 없음", "1월", {}, "NEEDS_YEAR"),
    ("13월", "13월", {"year_hint": 2026}, "BAD_FORMAT"),
    ("2026년 1월", "2026년 1월", {}, D(2026, 1, 1)),
    ("2026년1월", "2026년1월", {}, D(2026, 1, 1)),
    ("26년 3월", "26년 3월", {}, D(2026, 3, 1)),
    ("2026-01", "2026-01", {}, D(2026, 1, 1)),
    ("2026.01", "2026.01", {}, D(2026, 1, 1)),
    ("2026/1", "2026/1", {}, D(2026, 1, 1)),
    ("2026-01-15 (월 단위)", "2026-01-15", {}, D(2026, 1, 1)),
    ("2026-01 (일 단위)", "2026-01", {"unit": "day"}, "UNIT_MISMATCH"),
    ("01/2026", "01/2026", {}, D(2026, 1, 1)),
    ("Jan-26", "Jan-26", {}, D(2026, 1, 1)),
    ("Jan 2026", "Jan 2026", {}, D(2026, 1, 1)),
    ("January 2026", "January 2026", {}, D(2026, 1, 1)),
    ("Sept-2026 (Sep로 인식)", "Sept-2026", {}, D(2026, 9, 1)),
    ("Jan + 힌트", "Jan", {"year_hint": 2026}, D(2026, 1, 1)),
    ("Foo-26", "Foo-26", {}, "BAD_FORMAT"),
    ("26.1 (연월/월일 구분 불가)", "26.1", {}, "AMBIGUOUS"),
    ("1/26", "1/26", {}, "AMBIGUOUS"),
    ("괄호 주석 1월(잠정)", "1월(잠정)", {"year_hint": 2026}, D(2026, 1, 1)),
    ("2026년 (연 단위)", "2026년", {"unit": "year"}, D(2026, 1, 1)),
    ("2026 (글자, 월 단위)", "2026", {}, "BAD_FORMAT"),
    ("전각 숫자 ２０２６-０１", "２０２６-０１", {}, D(2026, 1, 1)),
    ("빈 칸", None, {}, "EMPTY"),
    ("공백", "  ", {}, "EMPTY"),
    ("불리언", True, {}, "BAD_FORMAT"),
    ("합계", "합계", {}, "BAD_FORMAT"),
    ("분기 1Q", "2026 1Q", {}, "BAD_FORMAT"),
    ("1899년", "1899-01", {}, "OUT_OF_RANGE"),
]


def main() -> int:
    fails = 0
    print("| # | 설명 | 입력 | 결과 | 기대 | 판정 |")
    print("| --- | --- | --- | --- | --- | --- |")
    for i, (desc, value, opt, expected) in enumerate(CASES, 1):
        got, reason = parse_period_header(value, **opt)
        actual = got if got is not None else reason
        ok = actual == expected
        fails += not ok
        shown = value.isoformat() if hasattr(value, "isoformat") else repr(value)
        print(f"| {i} | {desc} | `{shown}` | {actual} | {expected} | {'OK' if ok else 'FAIL'} |")
    # assign_years / suggest_year
    checks = [
        ("assign_years 12개월 연속", assign_years(list(range(1, 13)), 2026)[-1] == D(2026, 12, 1)),
        ("assign_years 연도 넘김(11,12,1,2)", assign_years([11, 12, 1, 2], 2025) == [D(2025, 11, 1), D(2025, 12, 1), D(2026, 1, 1), D(2026, 2, 1)]),
        ("suggest_year 시트 이름", suggest_year("2026", [])[0] == 2026),
        ("suggest_year 제목 셀", suggest_year("Sheet1", ["○○팀 2025년 월별 실적"]) == (2025, "title")),
        ("suggest_year 후보 둘이면 모호", suggest_year("Sheet1", ["2024~2026 실적"])[0] is None),
        ("suggest_year 없음", suggest_year("Sheet1", ["월별 실적"]) == (None, "NOT_FOUND")),
        ("suggest_year 숫자 일부(12026)는 연도 아님", suggest_year("x", ["코드 120261"])[0] is None),
    ]
    for desc, ok in checks:
        fails += not ok
        print(f"| - | {desc} | | | | {'OK' if ok else 'FAIL'} |")
    total = len(CASES) + len(checks)
    print(f"\n통과 {total - fails}/{total}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
