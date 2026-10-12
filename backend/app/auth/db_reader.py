"""`UserReader`의 DB 구현: `users`와 `team_members`(+`teams`)를 읽는다(04 §2-1 auth 읽기 service).

읽기 전용이다. 쓰기는 `access` 모듈이 한다. 다른 모듈이 팀 이름·코드를 읽는 길도 이 모듈이다.
요청마다 짧은 연결 하나로 두 질의(사용자, 소속)를 실행한다.
"""

from __future__ import annotations

from fastapi import Request
from sqlalchemy import Engine, select

from app.auth.identity import UserRecord
from app.auth.models import CurrentUser, Membership, TeamRole
from app.db_metadata import team_members, teams, users


class DbUserReader:
    def find_by_login_id(self, request: Request, login_id: str) -> UserRecord | None:
        engine: Engine = request.app.state.engine
        with engine.connect() as conn:
            user = conn.execute(
                select(users.c.id, users.c.display_name, users.c.is_active, users.c.is_admin).where(
                    users.c.login_id == login_id
                )
            ).first()
            if user is None:
                return None
            rows = conn.execute(
                select(teams.c.id, teams.c.code, teams.c.name, team_members.c.role)
                .join(team_members, team_members.c.team_id == teams.c.id)
                .where(team_members.c.user_id == user.id)
                .order_by(teams.c.name, teams.c.id)
            ).all()
        memberships = tuple(
            Membership(team_id=r.id, team_code=r.code, team_name=r.name, role=_role(r.role))
            for r in rows
        )
        return UserRecord(
            user=CurrentUser(
                id=user.id,
                display_name=user.display_name,
                is_active=bool(user.is_active),
                is_admin=bool(user.is_admin),
                memberships=memberships,
            )
        )


def _role(value: str) -> TeamRole:
    # DB의 CHECK가 두 값만 허용한다. 알 수 없는 값은 권한을 주지 않도록 예외로 닫는다(fail-closed).
    if value == "definer":
        return "definer"
    if value == "entry":
        return "entry"
    raise ValueError("알 수 없는 팀 역할")
