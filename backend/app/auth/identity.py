"""신원 어댑터 인터페이스와 사용자 조회 인터페이스.

- `IdentityAdapter`: 요청에서 "누구인가"(로그인 ID)만 뽑는다. 방식(헤더/토큰/로그인/스텁)을 바꿀 때
  이 인터페이스의 구현 한 곳만 바꾼다(04 §5 확장점 "신원 방식 교체 = auth 1곳").
- `UserReader`: 로그인 ID로 포털 사용자(`users`)를 찾는다. 표는 FU-1a에서 생기며 그때 구현한다.
둘 다 `app.state`에 연결한다(앱 팩토리). 하나라도 없으면 `current_user`는 401로 거부한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from fastapi import Request

from app.auth.models import CurrentUser


@dataclass(frozen=True, slots=True)
class Identity:
    login_id: str


@dataclass(frozen=True, slots=True)
class UserRecord:
    """`UserReader`가 돌려주는 사용자 한 명(미등록이면 `None`을 돌려주고 레코드를 만들지 않는다)."""

    user: CurrentUser


class IdentityAdapter(Protocol):
    def identify(self, request: Request) -> Identity | None:
        """신원을 확인할 수 없으면 `None`. 예외를 던지지 않는다(던져도 401로 처리된다)."""
        ...


class UserReader(Protocol):
    def find_by_login_id(self, request: Request, login_id: str) -> UserRecord | None:
        """등록된 사용자면 레코드, 아니면 `None`."""
        ...
