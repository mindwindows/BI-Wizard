"""변환기와 함수 사전이 주고받는 값(07 §1 3단계 변환)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.sql.elements import ColumnElement

from app.formula.literals import Literals


@dataclass(frozen=True)
class Compiled:
    """식 한 개의 변환 결과.

    - `value`: 값 식(오류 칸이면 NULL).
    - `error`: 오류 식(셀 오류 코드 smallint, 정상·빈 값이면 NULL). 오류가 날 수 없으면 `None`.
    - `const`: 수식에 **직접 쓴** 상수의 파이썬 값(`Decimal`·`str`·`bool`)이면 그 값, 아니면 `None`.
    """

    value: ColumnElement[Any]
    error: ColumnElement[Any] | None
    type: str
    const: Any = None


@dataclass(frozen=True)
class ConvertContext:
    """사전 항목의 `to_sql`·`when`이 받는 환경. 상수와 NULL은 반드시 `lit`을 거친다."""

    lit: Literals
    source: Callable[[int], ColumnElement[Any]]  # 열 번호 -> 원본 열 값 식(`c_<번호>`)

    def null(self, kind: str) -> ColumnElement[Any]:
        return self.lit.null(kind)
