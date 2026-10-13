"""수식 시험의 공용 도구: 표준 열 목록, 계산 열 만들기, SQLite 상수 검사기."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from app.formula import ColumnInfo, compile_formula
from tests.formula_runner import make_probe

SALES, COST, NAME, DAY, FLAG, CHOICE = 1, 2, 3, 4, 5, 6


def standard_columns() -> list[ColumnInfo]:
    """원본 열 6개: 매출·비용(숫자), 이름(글자), 일자(날짜), 사용(참거짓), 구분(선택 목록)."""
    return [
        ColumnInfo(SALES, "매출", "number"),
        ColumnInfo(COST, "비용", "number"),
        ColumnInfo(NAME, "이름", "text"),
        ColumnInfo(DAY, "일자", "date"),
        ColumnInfo(FLAG, "사용", "boolean"),
        ColumnInfo(CHOICE, "구분", "choice"),
    ]


def formula_column(
    column_id: int,
    name: str,
    expression: str,
    columns: Sequence[ColumnInfo],
    *,
    column_type: str = "number",
    tag: str | None = None,
) -> ColumnInfo:
    """수식을 컴파일해 저장된 AST를 가진 계산 열을 만든다(컴파일이 실패하면 AssertionError)."""
    result = compile_formula(expression, columns, build_sql=False)
    assert result.ok, [i.as_dict() for i in result.issues]
    return ColumnInfo(column_id, name, column_type, kind="formula", tag=tag, formula=result.ast)


def with_formulas(*specs: tuple[int, str, str]) -> list[ColumnInfo]:
    """표준 열에 계산 열을 차례로 덧붙인다: (번호, 이름, 수식)."""
    columns = standard_columns()
    for column_id, name, expression in specs:
        columns.append(formula_column(column_id, name, expression, columns))
    return columns


class SqliteProbe:
    """상수 SELECT를 SQLite로 평가하는 `ConstProbe`(호출 횟수와 조건 수를 센다)."""

    def __init__(self) -> None:
        self.engine = sa.create_engine("sqlite://")
        self.connection = self.engine.connect()
        self._probe = make_probe(self.connection)
        self.calls: list[int] = []

    def __call__(self, conditions):
        self.calls.append(len(conditions))
        return self._probe(conditions)

    def close(self) -> None:
        self.connection.close()
        self.engine.dispose()
