"""요청 단위 의존성. DB 세션은 `bi_app` 엔진(`app.state.engine`)에서 얻는다."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session


def get_session(request: Request) -> Iterator[Session]:
    """요청마다 세션 하나. 커밋은 service가 명시적으로 하고, 안 한 변경은 닫을 때 롤백된다."""
    with Session(request.app.state.engine) as session:
        yield session
