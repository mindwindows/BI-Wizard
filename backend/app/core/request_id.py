"""요청 id: 모든 응답에 `X-Request-ID` 헤더를 싣고 오류 본문의 `request_id`와 같은 값을 쓴다.

들어온 `X-Request-ID`는 안전한 문자(영숫자, `.`, `_`, `-`, 최대 64자)일 때만 쓰고,
아니면 새로 만든다(로그·헤더 주입 방지).
"""

from __future__ import annotations

import re
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
_SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")


def new_request_id() -> str:
    return uuid.uuid4().hex


def get_request_id(scope: Scope) -> str:
    """scope에 저장된 요청 id를 돌려준다. 없으면(미들웨어 밖) 새로 만들어 저장한다."""
    state = scope.setdefault("state", {})
    request_id = state.get("request_id")
    if not isinstance(request_id, str):
        request_id = new_request_id()
        state["request_id"] = request_id
    return request_id


class RequestIdMiddleware:
    """순수 ASGI 미들웨어. 응답 본문을 건드리지 않는다."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = Headers(scope=scope).get(REQUEST_ID_HEADER)
        state = scope.setdefault("state", {})
        state["request_id"] = (
            incoming if incoming and _SAFE_REQUEST_ID.fullmatch(incoming) else new_request_id()
        )
        request_id = state["request_id"]

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        await self.app(scope, receive, send_with_header)
