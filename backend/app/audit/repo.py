"""`audit_log` 데이터 접근(SQLAlchemy 표현식만, `text()` 금지). 쓰기는 INSERT 하나뿐이다.

UPDATE·DELETE 경로는 없다(`bi_app`에 권한도 없다). 트랜잭션 경계는 호출한 service가 정한다.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, insert, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

from app.db_metadata import audit_log


def insert_entry(
    session: Session,
    *,
    actor_user_id: int | None,
    actor_source: str,
    action: str,
    target_type: str,
    target_id: int,
    details: dict[str, Any],
) -> None:
    session.execute(
        insert(audit_log).values(
            actor_user_id=actor_user_id,
            actor_source=actor_source,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details,
        )
    )


def _conditions(
    *,
    occurred_from: datetime | None,
    occurred_before: datetime | None,
    actor_user_id: int | None,
    target_type: str | None,
    target_id: int | None,
    action: str | None,
) -> list[Any]:
    conditions: list[Any] = []
    if occurred_from is not None:
        conditions.append(audit_log.c.occurred_at >= occurred_from)
    if occurred_before is not None:
        conditions.append(audit_log.c.occurred_at < occurred_before)
    if actor_user_id is not None:
        conditions.append(audit_log.c.actor_user_id == actor_user_id)
    if target_type is not None:
        conditions.append(audit_log.c.target_type == target_type)
    if target_id is not None:
        conditions.append(audit_log.c.target_id == target_id)
    if action is not None:
        conditions.append(audit_log.c.action == action)
    return conditions


def list_entries(
    session: Session,
    *,
    occurred_from: datetime | None,
    occurred_before: datetime | None,
    actor_user_id: int | None,
    target_type: str | None,
    target_id: int | None,
    action: str | None,
    limit: int,
    offset: int,
) -> tuple[Sequence[RowMapping], int]:
    """필터는 모두 AND. 정렬은 `occurred_at` 내림차순, 같으면 `id` 내림차순으로 고정이다."""
    conditions = _conditions(
        occurred_from=occurred_from,
        occurred_before=occurred_before,
        actor_user_id=actor_user_id,
        target_type=target_type,
        target_id=target_id,
        action=action,
    )
    total = session.execute(select(func.count()).select_from(audit_log).where(*conditions))
    rows = (
        session.execute(
            select(audit_log)
            .where(*conditions)
            .order_by(audit_log.c.occurred_at.desc(), audit_log.c.id.desc())
            .limit(limit)
            .offset(offset)
        )
        .mappings()
        .all()
    )
    return rows, int(total.scalar_one())
