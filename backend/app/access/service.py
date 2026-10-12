"""권한 관리 로직(05 §2-1 A3~A9). 트랜잭션은 여기서 명시적으로 commit/rollback한다.

- 유일 값 중복(`teams.code`/`teams.name`/`users.login_id`)은 먼저 조회하고, 경쟁으로 DB 제약에
  걸려도 같은 409 `ALREADY_EXISTS`(`details.field`)로 바꾼다.
- 마지막 활성 관리자 보호(`LAST_ADMIN`)는 관리자 행을 잠근 채 판정한다
  (`repo.lock_target_and_active_admins`).
- 팀 이름 변경 뒤 동기화 요청은 이 모듈이 하지 않고 호출한 쪽(router)이 **커밋 뒤**
  `DatasetSyncPort`로 부른다. 여기서는 이름이 바뀌었는지만 알려 준다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.access import repo
from app.core.errors import already_exists, last_admin, not_found

_TEAM_MESSAGES = {
    "code": "이미 사용 중인 팀 코드입니다.",
    "name": "이미 사용 중인 팀 이름입니다.",
}
_LOGIN_ID_MESSAGE = "이미 등록된 로그인 ID입니다."


@dataclass(frozen=True)
class TeamChange:
    team: dict[str, Any]
    name_changed: bool


def _team_conflict(field: str):
    return already_exists(field, _TEAM_MESSAGES[field])


# --- teams ----


def list_teams(session: Session, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    rows, total = repo.list_teams(session, limit, offset)
    return [dict(r) for r in rows], total


def create_team(session: Session, *, code: str, name: str) -> dict[str, Any]:
    conflict = repo.find_team_conflict(session, code=code, name=name)
    if conflict:
        raise _team_conflict(conflict)
    try:
        team = repo.insert_team(session, code=code, name=name)
        session.commit()
    except IntegrityError:
        session.rollback()
        conflict = repo.find_team_conflict(session, code=code, name=name)
        if conflict:
            raise _team_conflict(conflict) from None
        raise
    return dict(team)


def update_team(
    session: Session, team_id: int, *, name: str | None, is_active: bool | None
) -> TeamChange:
    team = repo.get_team(session, team_id, lock=True)
    if team is None:
        raise not_found()
    values: dict[str, Any] = {}
    if name is not None and name != team["name"]:
        conflict = repo.find_team_conflict(session, name=name, exclude_id=team_id)
        if conflict:
            raise _team_conflict(conflict)
        values["name"] = name
    if is_active is not None and is_active != team["is_active"]:
        values["is_active"] = is_active
    if not values:
        session.rollback()  # 잠금 해제
        return TeamChange(dict(team), name_changed=False)
    try:
        updated = repo.update_team(session, team_id, values)
        session.commit()
    except IntegrityError:
        session.rollback()
        conflict = repo.find_team_conflict(session, name=name, exclude_id=team_id)
        if conflict:
            raise _team_conflict(conflict) from None
        raise
    return TeamChange(dict(updated), name_changed="name" in values)


# --- users ----


def _with_memberships(session: Session, rows: list[Any]) -> list[dict[str, Any]]:
    by_user = repo.memberships_by_user(session, [r["id"] for r in rows])
    return [{**dict(r), "memberships": by_user[r["id"]]} for r in rows]


def list_users(
    session: Session,
    *,
    q: str | None,
    team_id: int | None,
    is_active: bool | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    rows, total = repo.list_users(
        session, q=q, team_id=team_id, is_active=is_active, limit=limit, offset=offset
    )
    return _with_memberships(session, rows), total


def create_user(
    session: Session, *, login_id: str, display_name: str, is_admin: bool
) -> dict[str, Any]:
    if repo.find_user_conflict(session, login_id):
        raise already_exists("login_id", _LOGIN_ID_MESSAGE)
    try:
        row = repo.insert_user(
            session, login_id=login_id, display_name=display_name, is_admin=is_admin
        )
        session.commit()
    except IntegrityError:
        session.rollback()
        if repo.find_user_conflict(session, login_id):
            raise already_exists("login_id", _LOGIN_ID_MESSAGE) from None
        raise
    return {**dict(row), "memberships": []}


def update_user(
    session: Session,
    user_id: int,
    *,
    display_name: str | None,
    is_admin: bool | None,
    is_active: bool | None,
) -> dict[str, Any]:
    # 대상과 활성 관리자 전체를 먼저 잠근 뒤에 판정한다(경쟁해도 활성 관리자가 0명이 되지 않는다).
    target, active_admins = repo.lock_target_and_active_admins(session, user_id)
    if target is None:
        session.rollback()
        raise not_found()
    new_admin = target["is_admin"] if is_admin is None else is_admin
    new_active = target["is_active"] if is_active is None else is_active
    was_active_admin = target["is_admin"] and target["is_active"]
    if was_active_admin and not (new_admin and new_active) and active_admins == [user_id]:
        session.rollback()
        raise last_admin()
    values: dict[str, Any] = {}
    if display_name is not None and display_name != target["display_name"]:
        values["display_name"] = display_name
    if new_admin != target["is_admin"]:
        values["is_admin"] = new_admin
    if new_active != target["is_active"]:
        values["is_active"] = new_active
    if values:
        row = repo.update_user(session, user_id, values)
        session.commit()
    else:
        session.rollback()
        row = target
    return _single_with_memberships(session, row)


def _single_with_memberships(session: Session, row: Any) -> dict[str, Any]:
    return _with_memberships(session, [row])[0]


# --- team_members ----


def set_member(session: Session, team_id: int, user_id: int, role: str) -> dict[str, Any]:
    if repo.get_team(session, team_id) is None or repo.get_user(session, user_id) is None:
        raise not_found()
    try:
        repo.set_member_role(session, team_id, user_id, role)
        session.commit()
    except IntegrityError:
        # 같은 소속을 동시에 추가한 경쟁: 상대가 이미 넣었으니 역할만 바꾼다.
        session.rollback()
        repo.set_member_role(session, team_id, user_id, role)
        session.commit()
    return {"team_id": team_id, "user_id": user_id, "role": role}


def remove_member(session: Session, team_id: int, user_id: int) -> None:
    deleted = repo.delete_member(session, team_id, user_id)
    if not deleted:
        session.rollback()
        raise not_found()
    session.commit()


# --- 서버 명령(app/cli.py)용 ----


class UserExistsError(Exception):
    """이미 등록된 사용자라 최초 관리자로 만들 수 없다(권한을 조용히 바꾸지 않는다)."""


def create_first_admin(session: Session, *, login_id: str, display_name: str) -> bool:
    """최초 관리자 생성. 새로 만들었으면 True, 이미 활성 관리자라 바꿀 것이 없으면 False(멱등).

    같은 로그인 ID가 일반 사용자이거나 비활성이면 `UserExistsError`: 명령 한 줄이 기존 계정의 권한을
    조용히 올리지 않게 한다(관리자 화면 또는 다른 관리자가 바꾼다).
    """
    existing = repo.find_user_by_login_id(session, login_id)
    if existing is None:
        try:
            repo.insert_user(session, login_id=login_id, display_name=display_name, is_admin=True)
            session.commit()
            return True
        except IntegrityError:
            session.rollback()  # 동시에 만든 쪽이 있다. 아래에서 다시 판정한다.
            existing = repo.find_user_by_login_id(session, login_id)
            if existing is None:
                raise
    if existing["is_admin"] and existing["is_active"]:
        return False
    raise UserExistsError(login_id)


# 시험용 사용자 시드(개발·시험 전용, AUTH_STUB_ENABLED가 켜진 설정에서만 명령이 실행된다).
STUB_TEAMS = (("stub_a", "시험 A팀"), ("stub_b", "시험 B팀"))
# (로그인 ID, 표시 이름, 관리자, 활성)
STUB_USERS = (
    ("stub-admin", "시험 관리자", True, True),
    ("stub-definer", "시험 정의 담당자", False, True),
    ("stub-entry", "시험 입력자", False, True),
    ("stub-multi", "시험 두 팀 소속", False, True),
    ("stub-viewer", "시험 열람자", False, True),
    ("stub-inactive", "시험 비활성", False, False),
)
# (로그인 ID, 팀 코드, 역할)
STUB_MEMBERS = (
    ("stub-definer", "stub_a", "definer"),
    ("stub-entry", "stub_a", "entry"),
    ("stub-multi", "stub_a", "entry"),
    ("stub-multi", "stub_b", "definer"),
    ("stub-inactive", "stub_a", "entry"),
)


def seed_stub_data(session: Session) -> dict[str, int]:
    """시험용 팀·사용자·소속을 넣는다(멱등). 새로 만든 개수를 돌려준다."""
    created = {"teams": 0, "users": 0, "memberships": 0}
    team_ids: dict[str, int] = {}
    for code, name in STUB_TEAMS:
        row = repo.find_team_by_code(session, code)
        if row is None:
            row = repo.insert_team(session, code=code, name=name)
            created["teams"] += 1
        team_ids[code] = row["id"]
    user_ids: dict[str, int] = {}
    for login_id, display_name, is_admin, is_active in STUB_USERS:
        user = repo.find_user_by_login_id(session, login_id)
        if user is None:
            user = repo.insert_user(
                session, login_id=login_id, display_name=display_name, is_admin=is_admin
            )
            if not is_active:
                user = repo.update_user(session, user["id"], {"is_active": False})
            created["users"] += 1
        user_ids[login_id] = user["id"]
    existing = repo.memberships_by_user(session, list(user_ids.values()))
    for login_id, code, role in STUB_MEMBERS:
        user_id, team_id = user_ids[login_id], team_ids[code]
        if any(m["team_id"] == team_id for m in existing[user_id]):
            continue
        repo.set_member_role(session, team_id, user_id, role)
        created["memberships"] += 1
    session.commit()
    return created
