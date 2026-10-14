"""`users` `teams` `team_members` 데이터 접근(SQLAlchemy 표현식만, `text()` 금지).

트랜잭션 경계(commit/rollback)는 service가 정한다. 여기서는 실행만 한다.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, func, insert, or_, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

from app.core.sorting import by_name
from app.db_metadata import team_members, teams, users

_TEAM_COLUMNS = (teams.c.id, teams.c.code, teams.c.name, teams.c.is_active)
_USER_COLUMNS = (
    users.c.id,
    users.c.login_id,
    users.c.display_name,
    users.c.is_admin,
    users.c.is_active,
)


# --- teams ----


def list_teams(session: Session, limit: int, offset: int) -> tuple[list[RowMapping], int]:
    total = session.execute(select(func.count()).select_from(teams)).scalar_one()
    rows = (
        session.execute(
            select(*_TEAM_COLUMNS)
            .order_by(by_name(teams.c.name), teams.c.id)
            .limit(limit)
            .offset(offset)
        )
        .mappings()
        .all()
    )
    return list(rows), int(total)


def get_team(session: Session, team_id: int, *, lock: bool = False) -> RowMapping | None:
    stmt = select(*_TEAM_COLUMNS).where(teams.c.id == team_id)
    if lock:
        stmt = stmt.with_for_update(
            key_share=True
        )  # id·code는 불변이라 FOR NO KEY UPDATE로 충분하다.
    return session.execute(stmt).mappings().first()


def find_team_by_code(session: Session, code: str) -> RowMapping | None:
    return session.execute(select(*_TEAM_COLUMNS).where(teams.c.code == code)).mappings().first()


def find_team_conflict(
    session: Session,
    *,
    code: str | None = None,
    name: str | None = None,
    exclude_id: int | None = None,
) -> str | None:
    """같은 코드·이름의 다른 팀이 있으면 겹친 필드 이름(`code` 먼저)을, 없으면 None."""
    for field, value in (("code", code), ("name", name)):
        if value is None:
            continue
        stmt = select(teams.c.id).where(teams.c[field] == value)
        if exclude_id is not None:
            stmt = stmt.where(teams.c.id != exclude_id)
        if session.execute(stmt).first() is not None:
            return field
    return None


def insert_team(session: Session, *, code: str, name: str) -> RowMapping:
    return (
        session.execute(insert(teams).values(code=code, name=name).returning(*_TEAM_COLUMNS))
        .mappings()
        .one()
    )


def update_team(session: Session, team_id: int, values: dict[str, Any]) -> RowMapping:
    return (
        session.execute(
            update(teams).where(teams.c.id == team_id).values(**values).returning(*_TEAM_COLUMNS)
        )
        .mappings()
        .one()
    )


# --- users ----


def _user_filter(q: str | None, team_id: int | None, is_active: bool | None) -> list[Any]:
    conditions: list[Any] = []
    if q:
        conditions.append(
            or_(
                users.c.login_id.icontains(q, autoescape=True),
                users.c.display_name.icontains(q, autoescape=True),
            )
        )
    if team_id is not None:
        conditions.append(
            users.c.id.in_(select(team_members.c.user_id).where(team_members.c.team_id == team_id))
        )
    if is_active is not None:
        conditions.append(users.c.is_active == is_active)
    return conditions


def list_users(
    session: Session,
    *,
    q: str | None,
    team_id: int | None,
    is_active: bool | None,
    limit: int,
    offset: int,
) -> tuple[list[RowMapping], int]:
    conditions = _user_filter(q, team_id, is_active)
    total = session.execute(select(func.count()).select_from(users).where(*conditions)).scalar_one()
    rows = (
        session.execute(
            select(*_USER_COLUMNS)
            .where(*conditions)
            .order_by(by_name(users.c.display_name), users.c.id)
            .limit(limit)
            .offset(offset)
        )
        .mappings()
        .all()
    )
    return list(rows), int(total)


def memberships_by_user(
    session: Session, user_ids: Sequence[int]
) -> dict[int, list[dict[str, Any]]]:
    result: dict[int, list[dict[str, Any]]] = {user_id: [] for user_id in user_ids}
    if not user_ids:
        return result
    rows = session.execute(
        select(team_members.c.user_id, team_members.c.team_id, team_members.c.role)
        .where(team_members.c.user_id.in_(list(user_ids)))
        .order_by(team_members.c.user_id, team_members.c.team_id)
    ).all()
    for row in rows:
        result[row.user_id].append({"team_id": row.team_id, "role": row.role})
    return result


def find_user_by_login_id(session: Session, login_id: str) -> RowMapping | None:
    return (
        session.execute(select(*_USER_COLUMNS).where(users.c.login_id == login_id))
        .mappings()
        .first()
    )


def get_user(session: Session, user_id: int) -> RowMapping | None:
    return session.execute(select(*_USER_COLUMNS).where(users.c.id == user_id)).mappings().first()


def lock_target_and_active_admins(
    session: Session, user_id: int
) -> tuple[RowMapping | None, list[int]]:
    """대상 사용자와 모든 활성 관리자 행을 **id 순서로 한 문장에서** 잠그고 읽는다.

    마지막 활성 관리자 보호(LAST_ADMIN)용이다. 한 문장·id 순서로 잠그므로 서로 다른 관리자를
    동시에 해제·비활성하는 요청이 교착 없이 줄을 서고, 먼저 끝난 쪽의 변경을 나중 쪽이 다시
    읽어 보호가 작동한다(READ COMMITTED의 FOR UPDATE는 기다린 뒤 행을 다시 평가한다).
    `FOR UPDATE`는 열 단위 UPDATE 권한만 있어도 실행된다.
    """
    rows = (
        session.execute(
            select(*_USER_COLUMNS)
            .where(
                or_(
                    users.c.id == user_id,
                    (users.c.is_admin.is_(True)) & users.c.is_active.is_(True),
                )
            )
            .order_by(users.c.id)
            .with_for_update(key_share=True)
        )
        .mappings()
        .all()
    )
    target = next((r for r in rows if r["id"] == user_id), None)
    active_admins = [r["id"] for r in rows if r["is_admin"] and r["is_active"]]
    return target, active_admins


def find_user_conflict(session: Session, login_id: str) -> str | None:
    return "login_id" if find_user_by_login_id(session, login_id) is not None else None


def insert_user(
    session: Session, *, login_id: str, display_name: str, is_admin: bool
) -> RowMapping:
    return (
        session.execute(
            insert(users)
            .values(login_id=login_id, display_name=display_name, is_admin=is_admin)
            .returning(*_USER_COLUMNS)
        )
        .mappings()
        .one()
    )


def update_user(session: Session, user_id: int, values: dict[str, Any]) -> RowMapping:
    return (
        session.execute(
            update(users).where(users.c.id == user_id).values(**values).returning(*_USER_COLUMNS)
        )
        .mappings()
        .one()
    )


# --- team_members ----


def set_member_role(session: Session, team_id: int, user_id: int, role: str) -> str:
    """소속이 있으면 역할을 바꾸고 없으면 추가한다. 돌려주는 값은 저장된 역할."""
    where = (team_members.c.team_id == team_id) & (team_members.c.user_id == user_id)
    updated = session.execute(
        update(team_members).where(where).values(role=role).returning(team_members.c.role)
    ).first()
    if updated is None:
        session.execute(insert(team_members).values(team_id=team_id, user_id=user_id, role=role))
    return role


def insert_member(session: Session, team_id: int, user_id: int, role: str) -> None:
    """새 소속을 추가한다. 이미 있으면(동시에 추가한 경쟁) 유일 위반(IntegrityError)이다."""
    session.execute(insert(team_members).values(team_id=team_id, user_id=user_id, role=role))


def update_member_role(session: Session, team_id: int, user_id: int, role: str) -> bool:
    """있는 소속의 역할을 바꾼다. 바꾼 행이 있으면 True.

    호출한 쪽이 `get_member_role(lock=True)`로 행을 잠가 읽은 뒤에 부르므로 그 사이에 행이 바뀌지
    않는다(쓰기 전 값이 감사 `role_from`과 같다).
    """
    where = (team_members.c.team_id == team_id) & (team_members.c.user_id == user_id)
    updated = session.execute(
        update(team_members).where(where).values(role=role).returning(team_members.c.role)
    ).first()
    return updated is not None


def get_member_role(
    session: Session, team_id: int, user_id: int, *, lock: bool = False
) -> str | None:
    """소속의 현재 역할(없으면 None). `lock`이면 행을 `FOR NO KEY UPDATE`로 잠가 읽는다.

    역할 변경의 쓰기 전 값(감사 `role_from`)을 경쟁 없이 읽으려는 것이다. `role` 열의 UPDATE
    권한만으로 실행된다.
    """
    stmt = select(team_members.c.role).where(
        (team_members.c.team_id == team_id) & (team_members.c.user_id == user_id)
    )
    if lock:
        stmt = stmt.with_for_update(key_share=True)
    return session.execute(stmt).scalar_one_or_none()


def delete_member(session: Session, team_id: int, user_id: int) -> str | None:
    """소속을 지우고 지운 소속의 역할을 돌려준다(없었으면 None)."""
    return session.execute(
        delete(team_members)
        .where((team_members.c.team_id == team_id) & (team_members.c.user_id == user_id))
        .returning(team_members.c.role)
    ).scalar_one_or_none()
