"""권한 판정 함수(05 §1 권한 표기, 06 §4-1). 읽기는 인증된 활성 사용자 전부라 판정이 필요 없다.

- 관리자: `is_admin`
- 정의(팀): 그 팀의 `definer`. 관리자라도 팀 소속이 아니면 불가.
- 입력(팀): 그 팀의 `entry` 또는 `definer`.
"""

from __future__ import annotations

from app.auth.current_user import CurrentUserDep
from app.auth.models import CurrentUser
from app.core.errors import forbidden


def is_admin(user: CurrentUser) -> bool:
    return user.is_active and user.is_admin


def can_define(user: CurrentUser, team_id: int) -> bool:
    return user.is_active and any(
        m.team_id == team_id and m.role == "definer" for m in user.memberships
    )


def can_enter(user: CurrentUser, team_id: int) -> bool:
    return user.is_active and any(
        m.team_id == team_id and m.role in ("definer", "entry") for m in user.memberships
    )


def require_admin(user: CurrentUserDep) -> CurrentUser:
    """관리자 전용 라우트용 의존성."""
    if not is_admin(user):
        raise forbidden()
    return user
