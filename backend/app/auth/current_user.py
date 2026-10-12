"""`current_user`: 모든 업무 API가 거치는 인증 의존성 한 곳(04 §2-1, 05 §1).

판정 순서(모두 fail-closed):
1. 어댑터·사용자 조회 미연결, 신원 없음, 어댑터·조회 예외 -> 401 `UNAUTHENTICATED`
2. 신원은 있으나 `users`에 없음 -> 403 `USER_NOT_REGISTERED`
3. 비활성 -> 403 `USER_INACTIVE`

결정: DB 오류도 401로 닫고(fail-closed), 장애는 error 로그(클래스 이름·request_id만)로 감지한다.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, Request

from app.auth.models import CurrentUser
from app.core.errors import unauthenticated, user_inactive, user_not_registered
from app.core.request_id import get_request_id

logger = logging.getLogger(__name__)


def current_user(request: Request) -> CurrentUser:
    adapter = getattr(request.app.state, "identity_adapter", None)
    reader = getattr(request.app.state, "user_reader", None)
    if adapter is None or reader is None:
        raise unauthenticated()
    try:
        identity = adapter.identify(request)
        record = reader.find_by_login_id(request, identity.login_id) if identity else None
    except Exception as exc:
        # 어떤 실패도 인증 통과로 이어지지 않는다. 예외 메시지·트레이스백에는 SQL·파라미터·
        # login_id가 섞일 수 있어 클래스 이름과 request_id만 남긴다(exc_info 금지).
        logger.error(
            "인증 조회 실패(401로 닫음): %s (request_id=%s)",
            type(exc).__name__,
            get_request_id(request.scope),
        )
        raise unauthenticated() from None
    if identity is None:
        raise unauthenticated()
    if record is None:
        raise user_not_registered()
    if not record.user.is_active:
        raise user_inactive()
    return record.user


# 라우트 함수 인자에 쓰는 별칭: `user: CurrentUserDep`
CurrentUserDep = Annotated[CurrentUser, Depends(current_user)]
