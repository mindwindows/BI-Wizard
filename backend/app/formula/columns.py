"""수식이 보는 열 정보(`dataset_columns`의 읽기 전용 사본, 04 §2-1 formula는 dataset을 읽는다)."""

from __future__ import annotations

from dataclasses import dataclass

from app.formula.nodes import Node

# DB 열 종류 -> 수식 형. 선택 목록(`choice`)은 수식에서 글자로 취급한다(07 §2-2).
_FORMULA_TYPES = {
    "number": "number",
    "text": "text",
    "date": "date",
    "boolean": "boolean",
    "choice": "text",
}


@dataclass(frozen=True)
class ColumnInfo:
    """열 하나. `formula`는 계산 열(`kind='formula'`)의 저장된 AST다(원본 열은 `None`).

    `type`은 DB의 열 종류(`text`·`number`·`date`·`boolean`·`choice`)다. 계산 열의 `type`은 결과
    형이며,
    수식 안에서는 참조한 수식을 다시 분석한 형을 우선한다.
    """

    id: int
    name: str
    type: str
    kind: str = "raw"
    tag: str | None = None
    formula: Node | None = None

    @property
    def formula_type(self) -> str:
        """수식 안에서 보는 형(`choice`는 `text`). 모르는 종류면 `KeyError`."""
        return _FORMULA_TYPES[self.type]

    @property
    def is_formula(self) -> bool:
        return self.kind == "formula"


def is_supported_column_type(column_type: str) -> bool:
    return column_type in _FORMULA_TYPES
