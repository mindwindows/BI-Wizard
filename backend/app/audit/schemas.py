"""감사 기록 조회 응답 모양(05 §2-7 F1)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ActorOut(BaseModel):
    id: int
    display_name: str


class AuditLogOut(BaseModel):
    id: int
    occurred_at: str
    actor: ActorOut | None
    actor_source: str
    action: str
    target_type: str
    target_id: int
    details: dict[str, Any]
