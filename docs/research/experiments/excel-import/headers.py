"""머리글 날짜 해석·열 이름 매핑 제안의 시제품 (설계 검증용, 제품 코드 아님).

제품 구현은 FU에서 테스트와 함께 새로 쓴다. 여기서는 설계 문서의 규칙표가 실제로 동작하는지 확인한다.

- parse_period_header(): 머리글 값 -> 기간 첫날(date). 실패 시 (None, 사유 코드).
- suggest_year(): 시트 이름·상단 셀 글자에서 연도 후보를 찾는다(제안일 뿐, 사용자가 확정).
- assign_years(): "1월"처럼 월만 있는 머리글 열 목록에 연도를 붙인다(월이 줄어들면 다음 해).
- normalize_name(), suggest_mapping(): 엑셀 항목 이름 -> 데이터셋 열 이름 제안(문자열 규칙 / rapidfuzz 비교용).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta

EN_MONTHS = {
    m: i + 1
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    )
}
EXCEL_EPOCH = date(1899, 12, 30)  # 1900 날짜 체계(date1904 아님). 1900-02-29 오류 때문에 이 기준이 맞다.


def _first_day(y: int, m: int, d: int, unit: str) -> date | None:
    try:
        day = date(y, m, d)
    except ValueError:
        return None
    if unit == "year":
        return date(day.year, 1, 1)
    if unit == "month":
        return date(day.year, day.month, 1)
    return day


def parse_period_header(
    value, *, unit: str = "month", year_hint: int | None = None
) -> tuple[date | None, str | None]:
    """머리글 한 칸을 기간 첫날로. 반환 (날짜, None) 또는 (None, 사유 코드).

    사유: EMPTY, NEEDS_YEAR(월만 있고 연도 힌트 없음), AMBIGUOUS, BAD_FORMAT, OUT_OF_RANGE, UNIT_MISMATCH.
    unit이 day이면 일까지 있는 값만 받는다(월 머리글은 UNIT_MISMATCH).
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, "EMPTY"
    if isinstance(value, bool):
        return None, "BAD_FORMAT"
    if isinstance(value, datetime):
        return _first_day(value.year, value.month, value.day, unit), None
    if isinstance(value, date):
        return _first_day(value.year, value.month, value.day, unit), None
    if isinstance(value, (int, float)):
        n = float(value)
        if n != int(n):
            return None, "BAD_FORMAT"
        n = int(n)
        if unit == "year" and 1900 <= n <= 2200:
            return date(n, 1, 1), None
        if 1 <= n <= 12 and unit == "month":
            if year_hint is None:
                return None, "NEEDS_YEAR"
            return date(year_hint, n, 1), None
        if 20000 <= n <= 73000:  # 엑셀 일련번호(1954~2099 근방)
            d = EXCEL_EPOCH + timedelta(days=n)
            return _first_day(d.year, d.month, d.day, unit), None
        return None, "OUT_OF_RANGE"
    text = unicodedata.normalize("NFKC", str(value)).strip()
    text = re.sub(r"\s*[\(\[（].*?[\)\]）]\s*$", "", text)  # 끝의 "(잠정)" 같은 괄호 주석 제거
    # 2026년 1월 / 2026년1월 / 26년 1월
    m = re.fullmatch(r"(\d{2}|\d{4})\s*년\s*(\d{1,2})\s*월", text)
    if m:
        y = int(m[1]) + (2000 if len(m[1]) == 2 else 0)
        return _check(y, int(m[2]), 1, unit)
    # 2026년 (연 단위)
    m = re.fullmatch(r"(\d{4})\s*년?", text)
    if m and unit == "year":
        return date(int(m[1]), 1, 1), None
    # 1월
    m = re.fullmatch(r"(\d{1,2})\s*월", text)
    if m:
        if unit != "month":
            return None, "UNIT_MISMATCH"
        if year_hint is None:
            return None, "NEEDS_YEAR"
        return _check(year_hint, int(m[1]), 1, unit)
    # 2026-01 / 2026.01 / 2026/01 / 2026-01-01
    m = re.fullmatch(r"(\d{4})[-./](\d{1,2})(?:[-./](\d{1,2}))?", text)
    if m:
        d = int(m[3]) if m[3] else 1
        if unit == "day" and not m[3]:
            return None, "UNIT_MISMATCH"
        return _check(int(m[1]), int(m[2]), d, unit)
    # 01/2026
    m = re.fullmatch(r"(\d{1,2})[-./](\d{4})", text)
    if m:
        return _check(int(m[2]), int(m[1]), 1, unit)
    # Jan-26 / Jan 2026 / January 2026 / Jan-2026
    m = re.fullmatch(r"([A-Za-z]{3,9})\.?[\s\-/]*(\d{2}|\d{4})", text)
    if m and m[1][:3].lower() in EN_MONTHS:
        y = int(m[2]) + (2000 if len(m[2]) == 2 else 0)
        return _check(y, EN_MONTHS[m[1][:3].lower()], 1, unit)
    # Jan (월 이름만)
    m = re.fullmatch(r"([A-Za-z]{3,9})\.?", text)
    if m and m[1][:3].lower() in EN_MONTHS:
        if unit != "month":
            return None, "UNIT_MISMATCH"
        if year_hint is None:
            return None, "NEEDS_YEAR"
        return _check(year_hint, EN_MONTHS[m[1][:3].lower()], 1, unit)
    # 26.1 / 1/26 같은 두 자리 쌍은 연월·월일 구분이 불가능하다.
    if re.fullmatch(r"\d{1,2}[-./]\d{1,2}", text):
        return None, "AMBIGUOUS"
    return None, "BAD_FORMAT"


def _check(y: int, m: int, d: int, unit: str) -> tuple[date | None, str | None]:
    if not (1900 <= y <= 2200):
        return None, "OUT_OF_RANGE"
    day = _first_day(y, m, d, unit)
    return (day, None) if day else (None, "BAD_FORMAT")


YEAR_RE = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)")


def suggest_year(sheet_name: str, top_cells: list[str]) -> tuple[int | None, str]:
    """시트 이름 -> 상단 셀 순서로 연도 하나를 제안한다. 후보가 둘 이상이면 모호함으로 알린다."""
    for source, texts in (("sheet_name", [sheet_name]), ("title", top_cells)):
        found = {int(y) for t in texts for y in YEAR_RE.findall(t or "")}
        if len(found) == 1:
            return found.pop(), source
        if len(found) > 1:
            return None, f"{source}:AMBIGUOUS({sorted(found)})"
    return None, "NOT_FOUND"


def assign_years(months: list[int], start_year: int) -> list[date]:
    """월 번호만 있는 머리글 열 목록(왼쪽부터)에 연도를 붙인다. 월이 줄어들면 다음 해로 본다."""
    out, year, prev = [], start_year, 0
    for m in months:
        if m <= prev:
            year += 1
        out.append(date(year, m, 1))
        prev = m
    return out


# --- 열 이름 매핑 제안 ---

_PUNCT = re.compile(r"[\s_\-./·,:;]+")
_PAREN = re.compile(r"[\(\[（].*?[\)\]）]")


def normalize_name(name: str, *, drop_units: bool = True) -> str:
    s = unicodedata.normalize("NFKC", str(name)).casefold()
    if drop_units:
        s = _PAREN.sub("", s)
    return _PUNCT.sub("", s)


def suggest_mapping(sources: list[str], targets: list[str], method: str, threshold: float = 80.0):
    """엑셀 항목 이름 목록 -> 데이터셋 열 이름 제안. method: exact | difflib | rapidfuzz.

    반환: [(source, 제안 target 또는 None, 점수)] . 제안은 자동 확정이 아니다(화면에서 사용자가 확인).
    같은 target을 둘 이상의 source가 가리키면 점수가 높은 쪽만 남긴다(1:1).
    """
    norm_t = [normalize_name(t) for t in targets]
    result = []
    for s in sources:
        ns = normalize_name(s)
        best, best_score = None, 0.0
        if method == "exact":
            for t, nt in zip(targets, norm_t, strict=True):
                if ns == nt:
                    best, best_score = t, 100.0
        elif method == "difflib":
            from difflib import SequenceMatcher

            for t, nt in zip(targets, norm_t, strict=True):
                sc = SequenceMatcher(None, ns, nt).ratio() * 100
                if sc > best_score:
                    best, best_score = t, sc
        elif method == "rapidfuzz":
            from rapidfuzz import fuzz, process

            hit = process.extractOne(ns, norm_t, scorer=fuzz.WRatio)
            if hit:
                best, best_score = targets[hit[2]], float(hit[1])
        else:
            raise ValueError(method)
        result.append((s, best if best_score >= threshold else None, best_score))
    seen: dict[str, tuple[int, float]] = {}
    for i, (_, t, sc) in enumerate(result):
        if t is not None and (t not in seen or sc > seen[t][1]):
            seen[t] = (i, sc)
    return [
        (s, t if t is not None and seen[t][0] == i else None, sc)
        for i, (s, t, sc) in enumerate(result)
    ]
