"""기준값 API(05 §2-8 R1~R5). 보호 라우터라 `register_routers`가 `current_user`를 붙인다.

R1·R3(읽기)은 인증된 활성 사용자 누구나, R2·R4·R5(쓰기)는 관리자만(`require_admin`)이다. 권한
검사는 의존성이라 본문·쿼리 검증보다 먼저 실행된다(403이 먼저). R6(정정 영향 조회)는 저장된 수식을
읽어야 해서 `formula` 모듈이 같은 경로 접두로 라우터를 가진다(`app/formula/router.py`).
판정 순서: 인증 -> 403 -> 본문 형태 422 -> 404 -> 값 규칙 422 -> 409 -> 쓰기.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import CurrentUser
from app.auth.permissions import require_admin
from app.core.deps import get_session
from app.core.errors import FieldErrorCode, validation_failed
from app.core.pagination import LIST_LIMIT_DEFAULT, LIST_LIMIT_MAX, Page
from app.reference import service
from app.reference.schemas import (
    ItemCreate,
    ReferenceItemOut,
    ReferenceValueOut,
    ValueCreate,
    ValueUpdate,
    ValueUpdatedOut,
)

router = APIRouter(tags=["reference"])

SessionDep = Annotated[Session, Depends(get_session)]
AdminUser = Annotated[CurrentUser, Depends(require_admin)]
LimitParam = Annotated[int, Query(ge=1, le=LIST_LIMIT_MAX)]
OffsetParam = Annotated[int, Query(ge=0)]


@router.get("/reference-items")
def list_items(
    session: SessionDep, limit: LimitParam = LIST_LIMIT_DEFAULT, offset: OffsetParam = 0
) -> Page[ReferenceItemOut]:
    """R1: 기준값 항목 목록(이름 가나다순, 모든 사용자)."""
    items, total = service.list_items(session, limit, offset)
    return Page[ReferenceItemOut](items=items, total=total, limit=limit, offset=offset)


@router.post("/reference-items", status_code=201)
def create_item(body: ItemCreate, session: SessionDep, admin: AdminUser) -> ReferenceItemOut:
    """R2: 항목 추가(관리자). 이름은 불변이고 삭제할 수 없다."""
    return ReferenceItemOut(
        **service.create_item(session, admin, name=body.name, description=body.description)
    )


@router.get("/reference-items/{item_id}/values")
def list_values(
    item_id: int,
    session: SessionDep,
    limit: LimitParam = LIST_LIMIT_DEFAULT,
    offset: OffsetParam = 0,
) -> Page[ReferenceValueOut]:
    """R3: 항목의 연도별 값(연도 내림차순, 모든 사용자)."""
    items, total = service.list_values(session, item_id, limit, offset)
    return Page[ReferenceValueOut](items=items, total=total, limit=limit, offset=offset)


@router.post("/reference-items/{item_id}/values", status_code=201)
def add_value(
    item_id: int, body: ValueCreate, session: SessionDep, admin: AdminUser
) -> ReferenceValueOut:
    """R4: 연도 값 추가(관리자). 같은 (항목, 연도)가 있으면 409."""
    return ReferenceValueOut(
        **service.add_value(session, admin, item_id, year=body.year, value=body.value)
    )


@router.patch("/reference-items/{item_id}/values/{value_id}")
def update_value(
    item_id: int, value_id: int, body: ValueUpdate, session: SessionDep, admin: AdminUser
) -> ValueUpdatedOut:
    """R5: 값 정정(관리자). `year`·`item_id`는 바꿀 수 없다(본문에 있으면 422 `READ_ONLY`)."""
    sent = body.model_fields_set
    readonly = [name for name in ("year", "item_id") if name in sent]
    if readonly:
        raise validation_failed([(name, FieldErrorCode.READ_ONLY) for name in readonly])
    return ValueUpdatedOut(
        **service.update_value(session, admin, item_id, value_id, value=body.value)
    )
