"""인증 스텁(개발·시험 전용, 05 §2-6 DV1~DV3, `bi-review` 7-5).

시험용 사용자로 접속자를 흉내 내는 임시 기능이다. 신원 방식(브리프 5절 8번)이 정해지면
어댑터를 바꾸고 이 파일의 `/dev/*`는 없어진다. A1 이하 계약은 그대로다.

- 켜는 조건은 `AUTH_STUB_ENABLED=true`이고 `APP_ENV`가 **명시적으로** `local`/`test`일 때뿐이다.
  `Settings`가 로딩 때 거부하고, 여기서 한 번 더(방어적으로) 같은 판정을 부른다.
- 꺼져 있으면 어댑터도 `/dev/*` 라우트도 만들지 않는다(경로 자체가 없어 404).
- 신원 쿠키 `bi_stub_login`(HttpOnly)의 값은 로그인 ID를 URL 인코딩한 것이다. 서명하지 않는다
  (개발 전용). 쿠키가 있어도 `users`에 없으면 `current_user`가 403 `USER_NOT_REGISTERED`로 닫는다.
"""

from __future__ import annotations

from typing import Annotated
from urllib.parse import quote, unquote

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.identity import Identity
from app.config import Settings, check_auth_stub_allowed
from app.core.deps import get_session
from app.core.errors import not_found
from app.core.sorting import by_name
from app.db_metadata import users

STUB_COOKIE = "bi_stub_login"
_MAX_LOGIN_ID = 200
_LIST_LIMIT = 200


def assert_stub_allowed(settings: Settings) -> None:
    """스텁을 쓸 수 있는 설정인지 다시 판정한다(스위치가 꺼져 있으면 실패)."""
    if not settings.auth_stub_enabled:
        raise ValueError("AUTH_STUB_ENABLED가 꺼져 있어 인증 스텁을 쓸 수 없다.")
    check_auth_stub_allowed(
        enabled=True,
        app_env=settings.app_env,
        app_env_explicit="app_env" in settings.model_fields_set,
    )


class StubIdentityAdapter:
    """쿠키 `bi_stub_login`에서 로그인 ID를 꺼낸다. 없거나 비었거나 너무 길면 신원 없음."""

    def identify(self, request: Request) -> Identity | None:
        raw = request.cookies.get(STUB_COOKIE)
        if not raw:
            return None
        login_id = unquote(raw)
        if not login_id or len(login_id) > _MAX_LOGIN_ID:
            return None
        return Identity(login_id)


def build_stub_adapter(settings: Settings) -> StubIdentityAdapter:
    assert_stub_allowed(settings)
    return StubIdentityAdapter()


class StubUserItem(BaseModel):
    login_id: str
    display_name: str
    is_admin: bool


class StubUsersResponse(BaseModel):
    items: list[StubUserItem]
    current: str | None


class StubLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    login_id: Annotated[str, Field(min_length=1, max_length=_MAX_LOGIN_ID)]


# 이 라우터는 `current_user` 없이 열린다(신원을 고르기 전에 목록이 필요하다). 그래서 스텁이 켜진
# 설정에서만 `register_routers(dev=...)`가 붙이며, 경로는 `guard.DEV_STUB_PATHS` 안이어야 한다.
router = APIRouter(tags=["dev-stub"])


@router.get("/dev/stub-users")
def stub_users(
    request: Request, session: Annotated[Session, Depends(get_session)]
) -> StubUsersResponse:
    rows = session.execute(
        select(users.c.login_id, users.c.display_name, users.c.is_admin)
        .order_by(by_name(users.c.display_name), users.c.id)
        .limit(_LIST_LIMIT)
    ).all()
    raw = request.cookies.get(STUB_COOKIE)
    return StubUsersResponse(
        items=[
            StubUserItem(login_id=r.login_id, display_name=r.display_name, is_admin=r.is_admin)
            for r in rows
        ],
        current=unquote(raw) if raw else None,
    )


@router.put("/dev/stub-user", status_code=204)
def stub_login(
    body: StubLoginRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    exists = session.execute(select(users.c.id).where(users.c.login_id == body.login_id)).first()
    if exists is None:
        raise not_found()
    response = Response(status_code=204)
    response.set_cookie(
        STUB_COOKIE,
        quote(body.login_id, safe=""),
        httponly=True,
        samesite="lax",
        path=_cookie_path(request),
    )
    return response


@router.delete("/dev/stub-user", status_code=204)
def stub_logout(request: Request) -> Response:
    response = Response(status_code=204)
    response.delete_cookie(STUB_COOKIE, path=_cookie_path(request), httponly=True, samesite="lax")
    return response


def _cookie_path(request: Request) -> str:
    # 쿠키 범위: 포털 하위 경로(APP_BASE_PATH). 빈 값(루트 배포)이면 "/".
    return request.app.root_path or "/"
