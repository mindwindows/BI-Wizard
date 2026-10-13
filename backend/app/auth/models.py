"""인증된 사용자 타입(05 §2-1 A1 응답과 같은 모양)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TeamRole = Literal["definer", "entry"]


@dataclass(frozen=True, slots=True)
class Membership:
    team_id: int
    team_code: str
    team_name: str
    team_is_active: bool
    role: TeamRole


@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: int
    display_name: str
    is_active: bool
    is_admin: bool
    memberships: tuple[Membership, ...] = ()
