"""요청·응답 모양(05 §1 공통 형태 Column·Dataset, §2-2 B1~B6). 계약에 없는 필드는 만들지 않는다.

이름 검증(정리, 길이, 금지 문자, 예약어)은 요청 모델에서 하고 위반은 422 `VALIDATION_ERROR`의
`details.fields`가 된다(필드 코드 `TOO_LONG`·`BAD_FORMAT`·`RESERVED`). `rules`와 `tag`는 열 형에
따라 달라져 서비스가 검사한다.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
)
from pydantic_core import PydanticCustomError

from app.core.errors import FieldErrorCode
from app.core.text import has_control_chars, normalize_text
from app.dataset import rules

DateUnit = Literal["day", "month", "year"]
ColumnType = Literal["text", "number", "date", "boolean", "choice"]
ColumnKind = Literal["raw", "formula"]
DatasetStatus = Literal["active"]


def _dataset_name(value: str) -> str:
    if not value:
        raise PydanticCustomError("missing", "필수 항목입니다.")
    if has_control_chars(value):
        raise PydanticCustomError("bad_format", "제어문자는 쓸 수 없다")
    return value


def _column_name(value: str) -> str:
    problem = rules.column_name_problem(value)
    if problem is None:
        return value
    if problem == FieldErrorCode.RESERVED:
        raise PydanticCustomError("reserved", "예약된 이름이라 쓸 수 없다")
    if problem == FieldErrorCode.TOO_LONG:
        raise PydanticCustomError("string_too_long", "너무 깁니다")
    if problem == FieldErrorCode.REQUIRED:
        raise PydanticCustomError("missing", "필수 항목입니다")
    raise PydanticCustomError("bad_format", "쓸 수 없는 문자가 있다")


# 길이 상한은 정리 뒤에 센다(앞뒤 공백 제거·NFC). 최대 길이를 넘으면 `string_too_long` → TOO_LONG.
DatasetName = Annotated[
    str,
    BeforeValidator(normalize_text),
    Field(max_length=rules.DATASET_NAME_MAX),
    AfterValidator(_dataset_name),
]
ColumnName = Annotated[
    str,
    BeforeValidator(normalize_text),
    AfterValidator(_column_name),
]
Position = Annotated[StrictInt, Field(ge=0, le=1_000_000)]
ExpectedVersion = Annotated[StrictInt, Field(ge=1)]


class Strict(BaseModel):
    """요청 본문 기반 모델: 알 수 없는 필드는 422로 거부한다."""

    model_config = ConfigDict(extra="forbid")


class DatasetCreate(Strict):
    team_id: StrictInt
    name: DatasetName
    date_unit: DateUnit


class DatasetUpdate(Strict):
    """B4. 보낸 필드만 바꾼다(`model_fields_set`). `base_date_column_id: null`은 해제다."""

    expected_version: ExpectedVersion
    name: DatasetName = ""
    date_unit: DateUnit = "day"
    base_date_column_id: StrictInt | None = None


class ColumnCreate(Strict):
    """B5. 원본 열만 만든다(계산 열은 D4)."""

    expected_version: ExpectedVersion
    display_name: ColumnName
    type: ColumnType
    required: StrictBool = False
    rules: dict[str, Any] | None = None
    tag: str | None = None
    position: Position | None = None


class ColumnUpdate(Strict):
    """B6. `type`·`kind`는 바꿀 수 없다: 값이 현재와 다르면 422 `COLUMN_LOCKED`로 거부한다."""

    expected_version: ExpectedVersion
    display_name: ColumnName = ""
    required: StrictBool = False
    rules: dict[str, Any] | None = None
    tag: str | None = None
    position: Position = 0
    # 잠긴 항목: 받아서 현재 값과 비교하고 다르면 COLUMN_LOCKED로 답한다.
    type: str | None = None
    kind: str | None = None


# --- 응답 ---


class ColumnOut(BaseModel):
    id: int
    display_name: str
    type: ColumnType
    kind: ColumnKind
    required: bool
    rules: dict[str, Any] | None
    tag: str | None
    position: int


class UserRef(BaseModel):
    id: int
    display_name: str


class TeamRef(BaseModel):
    id: int
    code: str
    name: str


class Permissions(BaseModel):
    define: bool
    enter: bool


class DatasetOut(BaseModel):
    id: int
    team_id: int
    name: str
    date_unit: DateUnit
    base_date_column_id: int | None
    status: DatasetStatus
    def_version: int
    created_by: UserRef
    created_at: str


class DatasetDetailOut(DatasetOut):
    team: TeamRef
    columns: list[ColumnOut]
    permissions: Permissions


class ColumnResult(BaseModel):
    """B5·B6 응답: 열과 새 정의 버전."""

    column: ColumnOut
    def_version: int
