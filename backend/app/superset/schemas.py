"""요청·응답 모양(05 §2-5 E1~E6). 계약에 없는 필드는 만들지 않는다."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
)

from app.core.text import has_control_chars, normalize_text

# 대시보드 이름 길이 상한(05 §1 이름 규칙에 대시보드는 없어 데이터셋 이름과 같은 100자로 둔다).
DASHBOARD_NAME_MAX = 100

SyncStatus = Literal["pending", "registered", "failed"]


def _reject_control_chars(value: str) -> str:
    if has_control_chars(value):
        raise ValueError("제어문자는 쓸 수 없다")
    return value


def _embedded_uuid(value: object) -> object:
    """앞뒤 공백을 지우고 소문자로 바꾼 뒤 하이픈 있는 36자 정규형만 받는다(08 §4 훅의 형식
    요건)."""
    if not isinstance(value, str):
        return value
    cleaned = value.strip().lower()
    try:
        canonical = str(uuid.UUID(cleaned))
    except ValueError:
        raise ValueError("형식이 올바르지 않다") from None
    if canonical != cleaned:  # 하이픈 없음·중괄호·urn 형태는 거부한다
        raise ValueError("형식이 올바르지 않다")
    return canonical


DashboardName = Annotated[
    str,
    BeforeValidator(normalize_text),
    Field(min_length=1, max_length=DASHBOARD_NAME_MAX),
    AfterValidator(_reject_control_chars),
]
EmbeddedUuid = Annotated[str, BeforeValidator(_embedded_uuid)]


class Strict(BaseModel):
    """요청 본문 기반 모델: 알 수 없는 필드(`rls`, uuid 변경 등)는 422로 거부한다."""

    model_config = ConfigDict(extra="forbid")


class SupersetDatasetOut(BaseModel):
    dataset_id: int
    superset_name: str
    sync_status: SyncStatus
    synced_at: str | None
    last_error: str | None


class SyncRequest(Strict):
    dataset_ids: Annotated[list[int] | None, Field(max_length=1000)] = None


class SyncAccepted(BaseModel):
    accepted: list[int]


class DashboardOut(BaseModel):
    id: int
    name: str
    embedded_uuid: str
    is_active: bool


class DashboardCreate(Strict):
    name: DashboardName
    embedded_uuid: EmbeddedUuid


class DashboardUpdate(Strict):
    # 보낸 필드만 바꾼다(`model_fields_set`). null은 허용하지 않는다. embedded_uuid는 바꿀 수 없다.
    name: DashboardName = ""
    is_active: StrictBool = True


class GuestTokenOut(BaseModel):
    token: str
    expires_in: int
