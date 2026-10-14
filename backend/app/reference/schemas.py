"""요청·응답 모양(05 §2-8 R1~R5). 계약에 없는 필드는 만들지 않는다.

`value`는 `number` 십진 문자열이다(05 §1). 요청의 `year`는 JSON 정수, `value`는 십진 문자열이며
JSON 숫자·불린은 형태 오류(422 `BAD_FORMAT`)다. 값 규칙(연도 범위·38자리)은 service가 404 뒤에
판정한다(05 §2-8 판정 순서).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
)
from pydantic_core import PydanticCustomError

from app.core.text import has_control_chars, normalize_text
from app.reference import values as rules


def _name(value: str) -> str:
    if value == "":
        raise PydanticCustomError("missing", "이름이 비어 있다")  # 필드 코드 REQUIRED
    if rules.name_has_forbidden_chars(value):
        raise ValueError("이름에 쓸 수 없는 문자가 있다")
    return value


def _description(value: str | None) -> str | None:
    if value is None:
        return None
    if value == "":
        return None  # 빈 설명은 NULL(06 §2-2)
    if has_control_chars(value):
        raise ValueError("제어문자는 쓸 수 없다")
    return value


ItemName = Annotated[
    str,
    BeforeValidator(normalize_text),
    Field(max_length=rules.NAME_MAX_LENGTH),
    AfterValidator(_name),
]
ItemDescription = Annotated[
    str | None,
    BeforeValidator(normalize_text),
    Field(max_length=rules.DESCRIPTION_MAX_LENGTH),
    AfterValidator(_description),
]


class Strict(BaseModel):
    """요청 본문 기반 모델: 알 수 없는 필드는 422로 거부한다."""

    model_config = ConfigDict(extra="forbid")


class ItemCreate(Strict):
    name: ItemName
    description: ItemDescription = None


class ValueCreate(Strict):
    year: StrictInt
    value: StrictStr


class ValueUpdate(BaseModel):
    """R5 본문: `value`만 받는다. `year`·`item_id`가 있으면 라우터가 `READ_ONLY`(422)로 답한다."""

    model_config = ConfigDict(extra="forbid")

    value: StrictStr
    year: object = None  # 있으면 거부(READ_ONLY): 보냈는지는 `model_fields_set`으로 본다
    item_id: object = None


class UserRef(BaseModel):
    id: int
    display_name: str


class ReferenceItemOut(BaseModel):
    id: int
    name: str
    description: str | None
    value_count: int
    year_min: int | None
    year_max: int | None
    created_by: UserRef
    created_at: str


class ReferenceValueOut(BaseModel):
    id: int
    item_id: int
    year: int
    value: str
    created_by: UserRef
    created_at: str


class ValueUpdatedOut(BaseModel):
    value: ReferenceValueOut
    previous_value: str
    changed: bool
