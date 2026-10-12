"""함수 사전 항목의 시험 사례 `Case`(07 §2-1 `cases`, §6 차분 시험의 씨앗).

사례는 **수식 글자 + 열 값 → 기대 결과**다. 1단계(DB 없음)의 SQLite 평가와 PostgreSQL 컴파일 검사,
2단계의
실제 PostgreSQL 평가·미리보기-뷰 차분 시험이 같은 데이터를 그대로 쓴다(`tests/formula_runner.py`).

기대 결과 종류
- `ok(...)`: 값(`None`은 빈 값). 숫자는 십진 문자열이나 정수로 쓴다(DB 값과 `Decimal`로 비교).
- `err(...)`: 오류 칸. 값은 빈 값이고 셀 오류 코드가 `E1`~`E3`.
- `reject(...)`: 수식 검사(C0)가 거부. 기대하는 오류 코드(`ARG_TYPE` 등)를 쓴다.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

OK = "value"
ERROR = "error"
REJECT = "reject"


@dataclass(frozen=True)
class Case:
    expression: str
    expect: str = OK
    value: Any = None  # expect == "value"일 때 기대 값(None = 빈 값)
    error: str | None = None  # expect == "error"면 셀 오류 코드, "reject"면 검사 오류 코드
    cols: Mapping[str, str] = field(default_factory=dict)  # 열 이름 -> 열 종류(number 등)
    row: Mapping[str, Any] = field(default_factory=dict)  # 열 이름 -> 값(없으면 빈 값)
    tags: Mapping[str, str] = field(default_factory=dict)  # 열 이름 -> 열 태그(`SUMTAG`용)
    note: str = ""


def ok(expression: str, value: Any, *, cols=None, row=None, tags=None, note: str = "") -> Case:
    return Case(
        expression, OK, value, None, dict(cols or {}), dict(row or {}), dict(tags or {}), note
    )


def err(expression: str, code: str, *, cols=None, row=None, tags=None, note: str = "") -> Case:
    return Case(
        expression, ERROR, None, code, dict(cols or {}), dict(row or {}), dict(tags or {}), note
    )


def reject(expression: str, code: str, *, cols=None, row=None, tags=None, note: str = "") -> Case:
    return Case(
        expression, REJECT, None, code, dict(cols or {}), dict(row or {}), dict(tags or {}), note
    )
