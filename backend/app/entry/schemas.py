"""요청·응답 모양(05 §2-3 C1~C4). 계약에 없는 필드는 만들지 않는다.

값(`cells`의 값, `value`, `expected`, 붙여넣기 `values`)은 JSON 아무 형이나 받고 서버가 열 타입으로
해석·재검증한다(`values.parse_cell`). `expected`는 키가 반드시 있어야 한다(없으면 422 `REQUIRED`,
값 `null` = 빈 칸이었음, 05 §1 동시성).
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, Field, StrictInt

from app.dataset.schemas import ExpectedVersion, Strict

# 한 요청이 다루는 열·변경 개수의 안전 상한(정상 사용에서는 닿지 않는다).
MAX_COLUMNS = 200

ColumnId = Annotated[StrictInt, Field(ge=1)]


class RowCreate(Strict):
    """C2. `cells`의 키는 열 번호 글자(`"12"`), 원본 열만, 필수 열은 전부 있어야 한다."""

    expected_version: ExpectedVersion
    cells: dict[str, Any]


class CellChange(Strict):
    column_id: ColumnId
    expected: Any  # 기본값이 없어 키가 필수다(null 허용)
    value: Any


class RowPatch(Strict):
    """C3. 한 요청의 칸 전부가 가드이고 하나라도 충돌하면 전체 취소된다."""

    expected_version: ExpectedVersion
    changes: Annotated[list[CellChange], Field(min_length=1, max_length=MAX_COLUMNS)]


class PasteRow(Strict):
    """`row_id`가 null이면 새 행, 정수면 기존 행(이때 `expected`가 필수)."""

    row_id: StrictInt | None = None
    expected: list[Any] | None = None
    values: list[Any]


class PasteBody(Strict):
    """C4. 행 수 상한(5,000)은 413이라 여기서 길이를 제한하지 않고 라우터가 센다."""

    expected_version: ExpectedVersion
    column_ids: Annotated[list[ColumnId], Field(min_length=1, max_length=MAX_COLUMNS)]
    rows: Annotated[list[PasteRow], Field(min_length=1)]


# --- 응답 ---


class RowOut(BaseModel):
    row_id: int
    cells: dict[str, Any]
    errors: dict[str, str]


class RowsPage(BaseModel):
    def_version: int
    items: list[RowOut]
    total: int
    limit: int
    offset: int


class RowResult(BaseModel):
    row: RowOut
    def_version: int


class CreatedRow(BaseModel):
    index: int
    row_id: int


class PasteResult(BaseModel):
    updated: int
    created: int
    created_rows: list[CreatedRow]
    def_version: int
