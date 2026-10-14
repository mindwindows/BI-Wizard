"""`datasets` `dataset_columns` 데이터 접근(SQLAlchemy 표현식만, `text()` 금지).

트랜잭션 경계(commit/rollback)는 service가 정한다. 여기서는 실행만 한다. 원본 표(`ds_<번호>`)의 행
존재 확인도 이 파일의 읽기 질의다(DDL이 아니다). 이름은 `ddl.names` 규칙 함수로만 만든다.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import case, column, func, insert, null, select, table, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

from app.core.sorting import by_name
from app.db_metadata import DYNAMIC_SCHEMA, dataset_columns, datasets, teams, users
from app.ddl import dataset_table_name

_COLUMN_FIELDS = (
    dataset_columns.c.id,
    dataset_columns.c.display_name,
    dataset_columns.c.type,
    dataset_columns.c.kind,
    dataset_columns.c.required,
    dataset_columns.c.rules,
    dataset_columns.c.tag,
    dataset_columns.c.position,
)
_DATASET_FIELDS = (
    datasets.c.id,
    datasets.c.team_id,
    datasets.c.name,
    datasets.c.date_unit,
    datasets.c.base_date_column_id,
    datasets.c.status,
    datasets.c.def_version,
    datasets.c.created_at,
    datasets.c.created_by,
    users.c.display_name.label("created_by_name"),
)


def _dataset_select():
    return select(*_DATASET_FIELDS).join(users, users.c.id == datasets.c.created_by)


# --- 읽기 ----


def get_dataset(session: Session, dataset_id: int) -> RowMapping | None:
    stmt = _dataset_select().where(datasets.c.id == dataset_id)
    return session.execute(stmt).mappings().first()


def get_dataset_definition(session: Session, dataset_id: int) -> RowMapping | None:
    """수식 엔진용 정의 읽기: 해시와 팀·기준 열까지(잠금 없음)."""
    stmt = select(
        datasets.c.id,
        datasets.c.team_id,
        datasets.c.name,
        datasets.c.date_unit,
        datasets.c.base_date_column_id,
        datasets.c.def_version,
        datasets.c.def_hash,
    ).where(datasets.c.id == dataset_id)
    return session.execute(stmt).mappings().first()


def list_startup_check_dataset_ids(session: Session) -> list[int]:
    """시작 시 뷰·Superset 대조 대상: 활성과 보관 데이터셋 전부(FU-2b, 03b 30-1 결정 7).

    보관해도 `dv_` 뷰는 `bi_readonly`에 공개되고 Superset 가상 데이터셋은 남으므로 대조에서 빼지
    않는다.
    (오류 칸 점검 D7의 `list_formula_columns`는 활성만 읽는다: 코드 변경 없음, 05 §2-4.)
    """
    stmt = select(datasets.c.id).order_by(datasets.c.id)
    return [int(i) for i in session.execute(stmt).scalars()]


def get_team(session: Session, team_id: int) -> RowMapping | None:
    stmt = select(teams.c.id, teams.c.code, teams.c.name, teams.c.is_active).where(
        teams.c.id == team_id
    )
    return session.execute(stmt).mappings().first()


def list_datasets(
    session: Session,
    *,
    my_team_ids: Sequence[int],
    team_id: int | None,
    status: str | None,
    limit: int,
    offset: int,
) -> tuple[list[RowMapping], int]:
    """정렬: 내 소속 팀 먼저, 다음 팀 이름, 데이터셋 이름(03b 2-4).

    `status`가 None이면 전체, 아니면 그 상태만이다(`total`에도 같은 조건, FU-2b B1).
    """
    conditions = [] if team_id is None else [datasets.c.team_id == team_id]
    if status is not None:
        conditions.append(datasets.c.status == status)
    total = session.execute(
        select(func.count()).select_from(datasets).where(*conditions)
    ).scalar_one()
    mine_first = case((datasets.c.team_id.in_(list(my_team_ids)), 0), else_=1)
    stmt = (
        _dataset_select()
        .join(teams, teams.c.id == datasets.c.team_id)
        .where(*conditions)
        .order_by(mine_first, by_name(teams.c.name), by_name(datasets.c.name), datasets.c.id)
        .limit(limit)
        .offset(offset)
    )
    return list(session.execute(stmt).mappings().all()), int(total)


def list_sync_names(
    session: Session, *, dataset_ids: Sequence[int] | None, team_id: int | None
) -> list[RowMapping]:
    """Superset 동기화가 읽는 이름 목록(팀 이름, 데이터셋 이름 순). 필터는 선택이다."""
    stmt = (
        select(
            datasets.c.id,
            datasets.c.team_id,
            datasets.c.name,
            teams.c.name.label("team_name"),
        )
        .join(teams, teams.c.id == datasets.c.team_id)
        .order_by(by_name(teams.c.name), by_name(datasets.c.name), datasets.c.id)
    )
    if dataset_ids is not None:
        stmt = stmt.where(datasets.c.id.in_(list(dataset_ids)))
    if team_id is not None:
        stmt = stmt.where(datasets.c.team_id == team_id)
    return list(session.execute(stmt).mappings().all())


def list_columns(session: Session, dataset_id: int) -> list[RowMapping]:
    stmt = (
        select(*_COLUMN_FIELDS)
        .where(dataset_columns.c.dataset_id == dataset_id)
        .order_by(dataset_columns.c.position, dataset_columns.c.id)
    )
    return list(session.execute(stmt).mappings().all())


def get_column(session: Session, dataset_id: int, column_id: int) -> RowMapping | None:
    stmt = select(*_COLUMN_FIELDS).where(
        dataset_columns.c.dataset_id == dataset_id, dataset_columns.c.id == column_id
    )
    return session.execute(stmt).mappings().first()


def list_formula_columns(session: Session) -> list[RowMapping]:
    """모든 활성 데이터셋의 계산 열(오류 칸 점검용): 팀 이름, 데이터셋 이름, 열 순서."""
    stmt = (
        select(
            datasets.c.id.label("dataset_id"),
            datasets.c.name.label("dataset_name"),
            teams.c.name.label("team_name"),
            dataset_columns.c.id.label("column_id"),
            dataset_columns.c.display_name.label("column_name"),
        )
        .join(dataset_columns, dataset_columns.c.dataset_id == datasets.c.id)
        .join(teams, teams.c.id == datasets.c.team_id)
        .where(dataset_columns.c.kind == "formula", datasets.c.status == "active")
        .order_by(
            by_name(teams.c.name),
            by_name(datasets.c.name),
            datasets.c.id,
            dataset_columns.c.position,
            dataset_columns.c.id,
        )
    )
    return list(session.execute(stmt).mappings().all())


def max_position(session: Session, dataset_id: int) -> int | None:
    return session.execute(
        select(func.max(dataset_columns.c.position)).where(
            dataset_columns.c.dataset_id == dataset_id
        )
    ).scalar_one()


def find_dataset_name_conflict(
    session: Session, team_id: int, name: str, exclude_id: int | None = None
) -> str | None:
    """같은 팀에 같은 이름의 데이터셋이 있으면 그 `status`, 없으면 None(보관도 이름을 점유한다)."""
    stmt = select(datasets.c.status).where(datasets.c.team_id == team_id, datasets.c.name == name)
    if exclude_id is not None:
        stmt = stmt.where(datasets.c.id != exclude_id)
    return session.execute(stmt).scalars().first()


def find_column_name_conflict(
    session: Session, dataset_id: int, display_name: str, exclude_id: int | None = None
) -> bool:
    stmt = select(dataset_columns.c.id).where(
        dataset_columns.c.dataset_id == dataset_id, dataset_columns.c.display_name == display_name
    )
    if exclude_id is not None:
        stmt = stmt.where(dataset_columns.c.id != exclude_id)
    return session.execute(stmt).first() is not None


def dataset_has_rows(session: Session, dataset_id: int) -> bool:
    """원본 표에 행이 하나라도 있는가(없으면 기준 날짜 열·날짜 단위를 바꿀 수 있다, 06 §3-3)."""
    rows = table(dataset_table_name(dataset_id), column("row_id"), schema=DYNAMIC_SCHEMA)
    return session.execute(select(rows.c.row_id).limit(1)).first() is not None


# --- 잠금 ----


def lock_dataset(session: Session, dataset_id: int) -> RowMapping | None:
    """정의 변경 직렬화: `datasets` 행을 `FOR NO KEY UPDATE`로 잡는다(06 §5, 07 §8 한 가지 잠금).

    `id`가 불변이라 이 정도면 충분하고, `FOR UPDATE`는 FK 자식 INSERT의 KEY SHARE까지 막는다.
    다른 읽기는 막지 않는다. 락 대기는 호출한 쪽이 건 `lock_timeout`으로 끊긴다.
    """
    stmt = (
        select(
            datasets.c.id,
            datasets.c.team_id,
            datasets.c.name,
            datasets.c.date_unit,
            datasets.c.base_date_column_id,
            datasets.c.status,
            datasets.c.def_version,
            datasets.c.def_hash,
        )
        .where(datasets.c.id == dataset_id)
        .with_for_update(key_share=True)
    )
    return session.execute(stmt).mappings().first()


def lock_dataset_shared(session: Session, dataset_id: int) -> RowMapping | None:
    """행 쓰기(C2~C4)가 `datasets` 행을 `FOR SHARE`로 잡는다(06 §5 "행 쓰기 ↔ 정의").

    정의 변경(`FOR NO KEY UPDATE`)과는 서로 기다리고 행 쓰기끼리는 서로 막지 않는다. 락 대기는
    호출한 쪽이 건 `lock_timeout`으로 끊긴다.
    """
    stmt = (
        select(
            datasets.c.id,
            datasets.c.team_id,
            datasets.c.date_unit,
            datasets.c.base_date_column_id,
            datasets.c.status,
            datasets.c.def_version,
        )
        .where(datasets.c.id == dataset_id)
        .with_for_update(read=True)
    )
    return session.execute(stmt).mappings().first()


# --- 쓰기 ----


def insert_dataset(
    session: Session, *, team_id: int, name: str, date_unit: str, created_by: int, def_hash: str
) -> int:
    return session.execute(
        insert(datasets)
        .values(
            team_id=team_id,
            name=name,
            date_unit=date_unit,
            created_by=created_by,
            def_hash=def_hash,
        )
        .returning(datasets.c.id)
    ).scalar_one()


def update_dataset(session: Session, dataset_id: int, values: dict[str, Any]) -> None:
    session.execute(update(datasets).where(datasets.c.id == dataset_id).values(**values))


def insert_column(
    session: Session,
    *,
    dataset_id: int,
    display_name: str,
    column_type: str,
    required: bool,
    rules: dict[str, Any] | None,
    tag: str | None,
    position: int,
    kind: str = "raw",
) -> int:
    return session.execute(
        insert(dataset_columns)
        .values(
            dataset_id=dataset_id,
            display_name=display_name,
            type=column_type,
            kind=kind,
            required=required,
            rules=rules if rules is not None else null(),  # JSON null이 아니라 SQL NULL
            tag=tag,
            position=position,
        )
        .returning(dataset_columns.c.id)
    ).scalar_one()


def update_column(session: Session, column_id: int, values: dict[str, Any]) -> None:
    if "rules" in values and values["rules"] is None:
        values = {**values, "rules": null()}
    session.execute(
        update(dataset_columns).where(dataset_columns.c.id == column_id).values(**values)
    )
