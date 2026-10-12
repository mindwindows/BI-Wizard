"""API 시험 공용 도구: 스텁 로그인 클라이언트와 시험 세계(팀·사용자) 만들기."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from fastapi.testclient import TestClient

from app.auth.stub import STUB_COOKIE

if TYPE_CHECKING:
    from tests.conftest import Db

Call = Callable[..., Any]


@dataclass(frozen=True)
class World:
    """권한 시험에 쓰는 팀 2개와 역할별 사용자(로그인 ID = 이름)."""

    team_a: int
    team_b: int
    ids: dict[str, int]
    # 데이터셋 정의 시험용(`dataset_world`가 채운다): A팀 데이터셋 하나와 그 원본 열 하나.
    dataset_id: int = 0
    column_id: int = 0
    row_id: int = 0  # 권한 매트릭스용 기존 행


def build_world(db: Db) -> World:
    team_a = db.add_team("team_a", "A팀")
    team_b = db.add_team("team_b", "B팀")
    ids = {
        "admin": db.add_user("admin", "관리자", is_admin=True),
        "definer": db.add_user("definer", "정의 담당자"),
        "entry": db.add_user("entry", "입력자"),
        "other": db.add_user("other", "다른 팀 구성원"),
        "viewer": db.add_user("viewer", "비소속 읽기"),
        "inactive": db.add_user("inactive", "비활성", is_active=False),
    }
    db.add_member(team_a, ids["definer"], "definer")
    db.add_member(team_a, ids["entry"], "entry")
    db.add_member(team_b, ids["other"], "entry")
    return World(team_a, team_b, ids)


def make_caller(client: TestClient) -> Call:
    """`call(login_id | None, method, path, **kw)`: 스텁 쿠키를 바꿔 가며 요청한다."""

    def call(login: str | None, method: str, path: str, **kw: Any):
        client.cookies.clear()
        if login is not None:
            client.cookies.set(STUB_COOKIE, quote(login, safe=""))
        return client.request(method, path, **kw)

    return call
