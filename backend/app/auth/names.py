"""사용자 표시 이름 일괄 조회(04 §2-1 auth 읽기 service). 읽기 전용이다.

다른 모듈(감사 기록 조회 등)이 `users`를 직접 읽지 않고 이 함수로 행위자 표시 이름을 얻는다.
번호가 없는 사용자는 결과에서 빠진다(`users`에는 삭제가 없어 FK가 있으면 항상 있다).
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db_metadata import users


def display_names(session: Session, user_ids: Iterable[int]) -> dict[int, str]:
    ids = sorted(set(user_ids))
    if not ids:
        return {}
    rows = session.execute(select(users.c.id, users.c.display_name).where(users.c.id.in_(ids)))
    return {int(row.id): row.display_name for row in rows}
