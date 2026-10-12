"""원본 표 `bi_data.ds_<번호>`의 행 읽기·쓰기(DML). SQLAlchemy 표현식만 쓴다(`text()` 금지).

DDL이 아니다(표·열 만들기는 `ddl` 모듈). 표·열 이름은 `ddl` 이름 규칙 함수로만 만들고 사용자 글자는
식별자에 쓰지 않는다. 값은 항상 바인드 파라미터로 간다. 트랜잭션 경계는 service가 정한다.

PostgreSQL과 SQLite(DB 없는 시험)의 `INSERT … ON CONFLICT DO NOTHING`은 방언별 `insert`로 만든다
(`bi_app` 운영은 PostgreSQL뿐이다).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    Numeric,
    Text,
    and_,
    column,
    func,
    or_,
    select,
    table,
    update,
)
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement, KeyedColumnElement
from sqlalchemy.sql.expression import TableClause
from sqlalchemy.types import TypeEngine

from app.dataset.service import RowContext
from app.db_metadata import DYNAMIC_SCHEMA
from app.ddl import column_name, dataset_table_name

_SQL_TYPES: dict[str, type[TypeEngine]] = {
    "text": Text,
    "choice": Text,
    "number": Numeric,
    "date": Date,
    "boolean": Boolean,
}


def dynamic_table(ctx: RowContext) -> TableClause:
    """`ds_<번호>`를 가리키는 가벼운 표 설명(원본 열만). 열 이름은 열 번호로만 만든다."""
    columns = [
        column(column_name(c.id), _SQL_TYPES[c.type]()) for c in ctx.columns if c.kind == "raw"
    ]
    return table(
        dataset_table_name(ctx.dataset_id),
        column("row_id", BigInteger),
        *columns,
        schema=DYNAMIC_SCHEMA,
    )


def col(tbl: TableClause, column_id: int) -> KeyedColumnElement[Any]:
    return tbl.c[column_name(column_id)]


# --- 읽기 ----


def count_rows(session: Session, tbl: TableClause) -> int:
    return int(session.execute(select(func.count()).select_from(tbl)).scalar_one())


def select_rows(
    session: Session,
    tbl: TableClause,
    *,
    order_column_id: int | None,
    descending: bool,
    limit: int | None = None,
    offset: int = 0,
    row_ids: Sequence[int] | None = None,
) -> list[Mapping[str, Any]]:
    """행을 읽는다. 정렬: 기준 날짜 열(없으면 `row_id`), 같으면 `row_id`로 안정화."""
    stmt = select(tbl)
    if row_ids is not None:
        stmt = stmt.where(tbl.c.row_id.in_(list(row_ids)))
    keys = [col(tbl, order_column_id)] if order_column_id is not None else []
    keys.append(tbl.c.row_id)
    stmt = stmt.order_by(*[k.desc() if descending else k.asc() for k in keys])
    if limit is not None:
        stmt = stmt.limit(limit).offset(offset)
    return list(session.execute(stmt).mappings().all())


def get_row(session: Session, tbl: TableClause, row_id: int) -> Mapping[str, Any] | None:
    return session.execute(select(tbl).where(tbl.c.row_id == row_id)).mappings().first()


def existing_row_ids(session: Session, tbl: TableClause, row_ids: Sequence[int]) -> set[int]:
    if not row_ids:
        return set()
    stmt = select(tbl.c.row_id).where(tbl.c.row_id.in_(list(row_ids)))
    return {int(r) for r in session.execute(stmt).scalars()}


def find_by_period(
    session: Session, tbl: TableClause, base_column_id: int, period: date
) -> int | None:
    """같은 기간의 행 번호(기간 충돌 응답용). 없으면 None."""
    stmt = select(tbl.c.row_id).where(col(tbl, base_column_id) == period)
    return session.execute(stmt).scalar()


# --- 쓰기 ----


def insert_row(
    session: Session, tbl: TableClause, values: Mapping[int, Any], *, skip_period_conflict: bool
) -> int | None:
    """행 하나를 넣고 `row_id`를 돌려준다. 기간 유일 인덱스에 걸리면 None(트랜잭션은 안 깨진다).

    `INSERT … ON CONFLICT DO NOTHING RETURNING row_id`다(06 §5). 같은 기간을 먼저 넣은 다른
    트랜잭션이 아직 끝나지 않았으면 그 끝까지 기다린다(락 대기 한도는 `lock_timeout`).
    """
    dialect = session.get_bind().dialect.name
    maker = postgresql.insert if dialect == "postgresql" else sqlite.insert
    stmt = maker(tbl).values({col(tbl, cid).key: value for cid, value in values.items()})
    if skip_period_conflict:
        stmt = stmt.on_conflict_do_nothing()
    return session.execute(stmt.returning(tbl.c.row_id)).scalar()


def _guard(tbl: TableClause, column_id: int, expected: Any, value: Any) -> ColumnElement[bool]:
    """칸 가드: 지금 값이 읽었던 값(`expected`)이거나 이미 바꾸려는 값(`value`)이다."""
    target = col(tbl, column_id)
    return or_(target.is_not_distinct_from(expected), target.is_not_distinct_from(value))


def update_guarded(
    session: Session,
    tbl: TableClause,
    row_id: int,
    changes: Mapping[int, tuple[Any, Any]],
) -> int:
    """칸 단위 값 비교 갱신(06 §5): 한 UPDATE로 모든 칸이 가드에 맞을 때만 쓴다.

    `changes`는 `{열 번호: (expected, value)}`. 영향받은 행 수(0 또는 1)를 돌려준다:
    0이면 행이 없거나 어떤 칸이 이미 다른 값이다(원인 구분은 호출한 쪽이 다시 읽어 한다).
    """
    guards = [_guard(tbl, cid, expected, value) for cid, (expected, value) in changes.items()]
    stmt = (
        update(tbl)
        .where(and_(tbl.c.row_id == row_id, *guards))
        .values({col(tbl, cid).key: value for cid, (_e, value) in changes.items()})
    )
    return int(session.execute(stmt).rowcount)
