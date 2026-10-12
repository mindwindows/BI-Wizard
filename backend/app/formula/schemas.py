"""요청·응답 모양(05 §2-4 D1~D10). 계약에 없는 필드는 만들지 않는다.

위치(`start`/`end`)는 원문 수식의 코드포인트 번호(0부터, `end`는 포함하지 않음)다.
`signature`·`returns`는
사전에서 자동 생성한 글자다(편집기 자동완성·도움말).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from app.dataset.schemas import ColumnName, ColumnOut, ExpectedVersion, Position

# 수식 글자 상한(C0가 2,000자를 쉬운 말로 거부하므로 그보다 훨씬 위에서만 형식 오류로 막는다).
MAX_EXPRESSION_REQUEST = 10_000
Expression = Annotated[str, Field(max_length=MAX_EXPRESSION_REQUEST)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FormulaCheckBody(Strict):
    """D2·D3: `column_id`는 편집 중인 계산 열(자기 참조·순환 기준)이다."""

    expression: Expression
    column_id: StrictInt | None = None


class FormulaCreate(Strict):
    """D4: 계산 열 만들기."""

    expected_version: ExpectedVersion
    display_name: ColumnName
    expression: Expression
    tag: str | None = None
    position: Position | None = None


class FormulaUpdate(Strict):
    """D5: 수식 고치기."""

    expected_version: ExpectedVersion
    expression: Expression


class ViewsRetryBody(Strict):
    """D10: `dataset_ids` 생략 = 실패 전부."""

    dataset_ids: list[StrictInt] | None = Field(default=None, max_length=1000)


# --- 응답 ---


class FunctionOut(BaseModel):
    name: str
    signature: str
    returns: str
    help_ko: str
    excel_diff: str


class FunctionCatalogOut(BaseModel):
    functions: list[FunctionOut]
    cell_errors: dict[str, str]


class CheckErrorOut(BaseModel):
    code: str
    message: str
    start: int
    end: int


class CheckRefOut(BaseModel):
    column_id: int
    display_name: str


class CheckOut(BaseModel):
    ok: bool
    result_type: str | None
    refs: list[CheckRefOut]
    errors: list[CheckErrorOut]


class PreviewRowOut(BaseModel):
    row_id: int
    period: str | None
    value: str | bool | None
    error: str | None


class PreviewOut(BaseModel):
    result_type: str | None
    rows: list[PreviewRowOut]
    total_rows: int
    error_count: int
    empty_count: int
    def_version: int


class FormulaCreatedOut(BaseModel):
    """D4 응답: 새 계산 열과 새 정의 버전."""

    column: ColumnOut
    def_version: int


class FormulaUpdatedOut(FormulaCreatedOut):
    """D5 응답: 결과 형이 바뀌었는지(저장된 차트 영향 안내용)."""

    result_type_changed: bool


class FormulaRefOut(BaseModel):
    column_id: int
    display_name: str
    kind: str


class FormulaViewOut(BaseModel):
    column_id: int
    text: str
    refs: list[FormulaRefOut]
    tag_columns: list[str]
    error_count: int


class FormulaErrorSummaryOut(BaseModel):
    dataset_id: int
    dataset_name: str
    team_name: str
    column_id: int
    column_name: str
    error_count: int


class FormulaErrorCellOut(BaseModel):
    row_id: int
    period: str | None
    column_id: int
    error: str
    message: str


class ViewFailureOut(BaseModel):
    dataset_id: int
    dataset_name: str
    reason: str
    since: str | None


class ViewsStatusOut(BaseModel):
    views: int
    views_failed_count: int
    failed: list[ViewFailureOut]


class ViewsRetryOut(BaseModel):
    rebuilt: int
    views_failed_count: int
