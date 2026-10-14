"""`reference_items` `reference_values` 데이터 접근(SQLAlchemy 표현식만, `text()` 금지).

트랜잭션 경계(commit/rollback)는 service가 정한다. 두 표를 쓰는 곳은 이 모듈뿐이다(04 §2-2).
`bi_app`의 UPDATE 권한은 `reference_values.number_value`와 `reference_items.description`뿐이다
(`id`·`item_id`·`year`·`name`·`created_*`는 DB가 변경을 거부한다). DELETE는 없다.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

from app.core.sorting import by_name
from app.db_metadata import reference_items, reference_values

_ITEM_COLUMNS = (
    reference_items.c.id,
    reference_items.c.name,
    reference_items.c.description,
    reference_items.c.created_by,
    reference_items.c.created_at,
)
_VALUE_COLUMNS = (
    reference_values.c.id,
    reference_values.c.item_id,
    reference_values.c.year,
    reference_values.c.number_value,
    reference_values.c.created_by,
    reference_values.c.created_at,
)


def _insert_fn(session: Session):
    """방언에 맞는 `insert`(PostgreSQL이 운영, SQLite는 시험)."""
    return postgresql.insert if session.get_bind().dialect.name == "postgresql" else sqlite.insert


# --- 읽기 ----


def count_items(session: Session) -> int:
    return int(session.execute(select(func.count()).select_from(reference_items)).scalar_one())


def list_items(session: Session, limit: int, offset: int) -> list[RowMapping]:
    """항목 목록(이름 가나다순)과 값 개수·연도 범위(값이 없으면 개수 0, 연도 null)."""
    stats = (
        select(
            reference_values.c.item_id.label("item_id"),
            func.count().label("value_count"),
            func.min(reference_values.c.year).label("year_min"),
            func.max(reference_values.c.year).label("year_max"),
        )
        .group_by(reference_values.c.item_id)
        .subquery("stats")
    )
    stmt = (
        select(
            *_ITEM_COLUMNS,
            func.coalesce(stats.c.value_count, 0).label("value_count"),
            stats.c.year_min,
            stats.c.year_max,
        )
        .select_from(reference_items.outerjoin(stats, stats.c.item_id == reference_items.c.id))
        .order_by(by_name(reference_items.c.name), reference_items.c.id)
        .limit(limit)
        .offset(offset)
    )
    return list(session.execute(stmt).mappings().all())


def get_item_stats(session: Session, item_id: int) -> RowMapping | None:
    """항목 하나(목록과 같은 모양: 값 개수·연도 범위 포함)."""
    stmt = (
        select(
            *_ITEM_COLUMNS,
            func.count(reference_values.c.id).label("value_count"),
            func.min(reference_values.c.year).label("year_min"),
            func.max(reference_values.c.year).label("year_max"),
        )
        .select_from(
            reference_items.outerjoin(
                reference_values, reference_values.c.item_id == reference_items.c.id
            )
        )
        .where(reference_items.c.id == item_id)
        .group_by(reference_items.c.id)
    )
    return session.execute(stmt).mappings().first()


def lock_item(session: Session, item_id: int) -> RowMapping | None:
    """항목 행을 `FOR NO KEY UPDATE`로 잡는다(06 §5 기준값 쓰기, `datasets`는 건드리지 않는다)."""
    stmt = (
        select(reference_items.c.id, reference_items.c.name)
        .where(reference_items.c.id == item_id)
        .with_for_update(key_share=True)
    )
    return session.execute(stmt).mappings().first()


def get_item(session: Session, item_id: int) -> RowMapping | None:
    stmt = select(reference_items.c.id, reference_items.c.name).where(
        reference_items.c.id == item_id
    )
    return session.execute(stmt).mappings().first()


def name_to_id(session: Session) -> dict[str, int]:
    """항목 이름 -> 번호(수식 컴파일 환경). 잠금 없는 SELECT다."""
    rows = session.execute(select(reference_items.c.name, reference_items.c.id)).all()
    return {str(r.name): int(r.id) for r in rows}


def count_values(session: Session, item_id: int) -> int:
    stmt = (
        select(func.count())
        .select_from(reference_values)
        .where(reference_values.c.item_id == item_id)
    )
    return int(session.execute(stmt).scalar_one())


def list_values(session: Session, item_id: int, limit: int, offset: int) -> list[RowMapping]:
    stmt = (
        select(*_VALUE_COLUMNS)
        .where(reference_values.c.item_id == item_id)
        .order_by(reference_values.c.year.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.execute(stmt).mappings().all())


def get_value(session: Session, item_id: int, value_id: int) -> RowMapping | None:
    """항목 소속 값 한 줄(다른 항목의 값 번호면 None)."""
    stmt = select(*_VALUE_COLUMNS).where(
        reference_values.c.id == value_id, reference_values.c.item_id == item_id
    )
    return session.execute(stmt).mappings().first()


# --- 쓰기 ----


def insert_item(
    session: Session, *, name: str, description: str | None, created_by: int
) -> RowMapping | None:
    """`INSERT … ON CONFLICT (name) DO NOTHING RETURNING`. 같은 이름이 있으면 None(409)."""
    stmt = (
        _insert_fn(session)(reference_items)
        .values(name=name, description=description, created_by=created_by)
        .on_conflict_do_nothing(index_elements=[reference_items.c.name])
        .returning(*_ITEM_COLUMNS)
    )
    return session.execute(stmt).mappings().first()


def insert_value(
    session: Session, *, item_id: int, year: int, value: Decimal, created_by: int
) -> RowMapping | None:
    """`INSERT … ON CONFLICT (item_id, year) DO NOTHING RETURNING`. 같은 연도가 있으면 None(409)."""
    stmt = (
        _insert_fn(session)(reference_values)
        .values(item_id=item_id, year=year, number_value=value, created_by=created_by)
        .on_conflict_do_nothing(
            index_elements=[reference_values.c.item_id, reference_values.c.year]
        )
        .returning(*_VALUE_COLUMNS)
    )
    return session.execute(stmt).mappings().first()


def update_value(session: Session, value_id: int, value: Decimal) -> RowMapping:
    """정정: `number_value` 한 칸만 UPDATE한다(다른 열은 DB가 거부한다)."""
    return (
        session.execute(
            update(reference_values)
            .where(reference_values.c.id == value_id)
            .values(number_value=value)
            .returning(*_VALUE_COLUMNS)
        )
        .mappings()
        .one()
    )


__all__ = [
    "count_items",
    "count_values",
    "get_item",
    "get_item_stats",
    "get_value",
    "insert_item",
    "insert_value",
    "list_items",
    "list_values",
    "lock_item",
    "name_to_id",
    "update_value",
]
