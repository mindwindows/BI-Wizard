"""감사 기록 목록 API(05 §2-7 F1). 관리자 전용 읽기이며 수정·삭제·내보내기 경로는 없다.

보호 라우터라 `register_routers`가 `current_user`를 붙인다. `require_admin`은 의존성이라 쿼리
검증보다 먼저 실행된다(권한 없는 사용자는 입력 오류 내용을 알 수 없다). 쿼리 오류는 422
`VALIDATION_ERROR` 한 가지이며 필드 코드는 05 §2-7 F1 규칙 ②를 따른다.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.audit import service
from app.audit.schemas import AuditLogOut
from app.auth.permissions import require_admin
from app.core.deps import get_session
from app.core.errors import FieldErrorCode, validation_failed
from app.core.pagination import LIST_LIMIT_DEFAULT, LIST_LIMIT_MAX, Page
from app.db_metadata import AUDIT_ACTIONS, AUDIT_TARGET_TYPES

router = APIRouter(tags=["audit"])

SessionDep = Annotated[Session, Depends(get_session)]
LimitParam = Annotated[int, Query(ge=1, le=LIST_LIMIT_MAX)]
OffsetParam = Annotated[int, Query(ge=0)]
# 번호는 DB 열 크기 안(integer, bigint)으로 막아 DB 오류(500)가 되지 않게 한다.
ActorIdParam = Annotated[int | None, Query(ge=1, le=2**31 - 1)]
TargetIdParam = Annotated[int | None, Query(ge=1, le=2**63 - 1)]

_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def _parse_date(value: str | None) -> date | None:
    """`YYYY-MM-DD`(ASCII 숫자, 실제로 있는 날짜)만 받는다. 아니면 ValueError."""
    if value is None:
        return None
    if _DATE.fullmatch(value) is None:
        raise ValueError(value)
    return date(int(value[0:4]), int(value[5:7]), int(value[8:10]))


@router.get("/audit-logs", dependencies=[Depends(require_admin)])
def list_audit_logs(
    session: SessionDep,
    date_from: Annotated[str | None, Query(alias="from")] = None,
    date_to: Annotated[str | None, Query(alias="to")] = None,
    actor_user_id: ActorIdParam = None,
    target_type: str | None = None,
    target_id: TargetIdParam = None,
    action: str | None = None,
    limit: LimitParam = LIST_LIMIT_DEFAULT,
    offset: OffsetParam = 0,
) -> Page[AuditLogOut]:
    """F1: 감사 기록 목록(필터는 모두 AND, `occurred_at` 내림차순, `id` 내림차순)."""
    problems: list[tuple[str, str]] = []
    start = end = None
    try:
        start = _parse_date(date_from)
    except ValueError:
        problems.append(("from", FieldErrorCode.BAD_FORMAT))
    try:
        end = _parse_date(date_to)
    except ValueError:
        problems.append(("to", FieldErrorCode.BAD_FORMAT))
    if start is not None and end is not None and start > end:
        problems.append(("to", FieldErrorCode.OUT_OF_RANGE))
    if target_type is not None and target_type not in AUDIT_TARGET_TYPES:
        problems.append(("target_type", FieldErrorCode.NOT_IN_OPTIONS))
    if target_id is not None and target_type is None:
        problems.append(("target_type", FieldErrorCode.REQUIRED))
    if action is not None and action not in AUDIT_ACTIONS:
        problems.append(("action", FieldErrorCode.NOT_IN_OPTIONS))
    if problems:
        raise validation_failed(problems)
    items, total = service.list_logs(
        session,
        date_from=start,
        date_to=end,
        actor_user_id=actor_user_id,
        target_type=target_type,
        target_id=target_id,
        action=action,
        limit=limit,
        offset=offset,
    )
    return Page[AuditLogOut](
        items=[AuditLogOut(**item) for item in items], total=total, limit=limit, offset=offset
    )
