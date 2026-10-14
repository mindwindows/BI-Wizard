"""`superset_datasets` `superset_dashboards` 데이터 접근(SQLAlchemy 표현식만, `text()` 금지).

트랜잭션 경계는 호출하는 쪽(service·worker)이 정한다. 업서트는 내장 `on_conflict_do_update`이고
`bi_app`의 열 단위 UPDATE 권한 안의 열만 쓴다(`dataset_id`·`id`·`embedded_uuid`·`created_at` 불변).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

from app.core.sorting import by_name
from app.db_metadata import superset_dashboards, superset_datasets


def _upsert(session: Session, values: dict[str, Any], set_columns: list[str]):
    """방언에 맞는 `INSERT … ON CONFLICT (dataset_id) DO UPDATE`(PostgreSQL이 운영, SQLite는
    시험)."""
    insert_fn = pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
    statement = insert_fn(superset_datasets).values(**values)
    return statement.on_conflict_do_update(
        index_elements=[superset_datasets.c.dataset_id],
        set_={name: getattr(statement.excluded, name) for name in set_columns},
    )


# --- superset_datasets ----


def get_sync_row(session: Session, dataset_id: int) -> RowMapping | None:
    stmt = select(superset_datasets).where(superset_datasets.c.dataset_id == dataset_id)
    return session.execute(stmt).mappings().first()


def all_sync_rows(session: Session) -> dict[int, RowMapping]:
    rows = session.execute(select(superset_datasets)).mappings().all()
    return {int(r["dataset_id"]): r for r in rows}


def mark_pending(session: Session, dataset_id: int, display_name: str) -> None:
    """동기화 요청 접수: 행이 없으면 만들고, 있으면 `pending`으로 되돌린다(번호·시각은 유지)."""
    values = {
        "dataset_id": dataset_id,
        "display_name": display_name,
        "sync_status": "pending",
        "last_error": None,
    }
    session.execute(_upsert(session, values, ["display_name", "sync_status", "last_error"]))


def record_superset_id(
    session: Session, dataset_id: int, display_name: str, superset_dataset_id: int
) -> None:
    """Superset에서 만든 번호를 곧바로 기록한다(크래시 뒤 중복 등록 방지). 상태는 바꾸지 않는다."""
    statement = _upsert(
        session,
        {
            "dataset_id": dataset_id,
            "display_name": display_name,
            "sync_status": "pending",
            "superset_dataset_id": superset_dataset_id,
        },
        ["superset_dataset_id"],
    )
    session.execute(statement)


def mark_registered(
    session: Session, dataset_id: int, display_name: str, superset_dataset_id: int
) -> None:
    statement = _upsert(
        session,
        {
            "dataset_id": dataset_id,
            "display_name": display_name,
            "sync_status": "registered",
            "superset_dataset_id": superset_dataset_id,
            "synced_at": func.now(),
            "last_error": None,
        },
        ["display_name", "sync_status", "superset_dataset_id", "synced_at", "last_error"],
    )
    session.execute(statement)


def mark_failed(session: Session, dataset_id: int, display_name: str, last_error: str) -> None:
    statement = _upsert(
        session,
        {
            "dataset_id": dataset_id,
            "display_name": display_name,
            "sync_status": "failed",
            "last_error": last_error,
        },
        ["display_name", "sync_status", "last_error"],
    )
    session.execute(statement)


# --- superset_dashboards ----


def list_dashboards(
    session: Session, *, include_inactive: bool, limit: int, offset: int
) -> tuple[list[RowMapping], int]:
    conditions = [] if include_inactive else [superset_dashboards.c.is_active.is_(True)]
    total = session.execute(
        select(func.count()).select_from(superset_dashboards).where(*conditions)
    ).scalar_one()
    stmt = (
        select(superset_dashboards)
        .where(*conditions)
        .order_by(by_name(superset_dashboards.c.name), superset_dashboards.c.id)
        .limit(limit)
        .offset(offset)
    )
    return list(session.execute(stmt).mappings().all()), int(total)


def get_dashboard(session: Session, dashboard_id: int, *, lock: bool = False) -> RowMapping | None:
    """`lock`이면 행을 `FOR NO KEY UPDATE`로 잠가 읽는다(변경 판정·감사 기록의 쓰기 전 값)."""
    stmt = select(superset_dashboards).where(superset_dashboards.c.id == dashboard_id)
    if lock:
        stmt = stmt.with_for_update(key_share=True)
    return session.execute(stmt).mappings().first()


def find_dashboard_by_uuid(session: Session, embedded_uuid: uuid.UUID) -> RowMapping | None:
    stmt = select(superset_dashboards).where(superset_dashboards.c.embedded_uuid == embedded_uuid)
    return session.execute(stmt).mappings().first()


def insert_dashboard(session: Session, *, name: str, embedded_uuid: uuid.UUID) -> RowMapping:
    stmt = (
        superset_dashboards.insert()
        .values(name=name, embedded_uuid=embedded_uuid)
        .returning(*superset_dashboards.c)
    )
    return session.execute(stmt).mappings().one()


def update_dashboard(session: Session, dashboard_id: int, values: dict[str, Any]) -> RowMapping:
    stmt = (
        update(superset_dashboards)
        .where(superset_dashboards.c.id == dashboard_id)
        .values(**values)
        .returning(*superset_dashboards.c)
    )
    return session.execute(stmt).mappings().one()
