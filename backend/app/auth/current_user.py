"""`current_user`: 모든 업무 API가 거치는 인증 의존성 한 곳(04 §2-1, 05 §1).

판정 순서(모두 fail-closed):
1. 어댑터·사용자 조회 미연결, 신원 없음, 어댑터·조회 예외 -> 401 `UNAUTHENTICATED`
2. 신원은 있으나 `users`에 없음 -> 403 `USER_NOT_REGISTERED`
3. 비활성 -> 403 `USER_INACTIVE`
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, Request

from app.auth.models import CurrentUser
from app.core.errors import unauthenticated, user_inactive, user_not_registered

logger = logging.getLogger(__name__)


def current_user(request: Request) -> CurrentUser:
    adapter = getattr(request.app.state, "identity_adapter", None)
    reader = getattr(request.app.state, "user_reader", None)
    if adapter is None or reader is None:
        raise unauthenticated()
    try:
        identity = adapter.identify(request)
        record = reader.find_by_login_id(request, identity.login_id) if identity else None
    except Exception:
        # 어떤 실패도 인증 통과로 이어지지 않는다. 상세는 로그에만(비밀·신원 값은 남기지 않는다).
        logger.exception("신원 확인 중 오류")
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
