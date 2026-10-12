"""`current_user`: 모든 업무 API가 거치는 인증 의존성 한 곳(04 §2-1, 05 §1).

판정 순서(모두 fail-closed, 접근은 어떤 실패에서도 열리지 않는다):
1. 어댑터·사용자 조회 미연결, 신원 없음, 신원 어댑터 예외 -> 401 `UNAUTHENTICATED`
2. 사용자 조회 중 DB 연결·운영 오류 -> 503 `SERVICE_UNAVAILABLE`(로그아웃과 구분, 03b 17-1 결정 2)
3. 신원은 있으나 `users`에 없음 -> 403 `USER_NOT_REGISTERED`
4. 비활성 -> 403 `USER_INACTIVE`

그 밖의 조회 예외(DB와 무관한 오류)는 401로 닫는다. 어떤 실패도 로그에는 예외 클래스 이름과
request_id만 남긴다(메시지·트레이스백에는 SQL·파라미터·login_id가 섞일 수 있다).
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, Request

from app.auth.models import CurrentUser
from app.core.db_errors import is_db_failure
from app.core.errors import (
    service_unavailable,
    unauthenticated,
    user_inactive,
    user_not_registered,
)
from app.core.request_id import get_request_id

logger = logging.getLogger(__name__)


def current_user(request: Request) -> CurrentUser:
    adapter = getattr(request.app.state, "identity_adapter", None)
    reader = getattr(request.app.state, "user_reader", None)
    if adapter is None or reader is None:
        raise unauthenticated()
    request_id = get_request_id(request.scope)
    try:
        identity = adapter.identify(request)
    except Exception as exc:
        logger.error(
            "인증 조회 실패(401로 닫음): %s (request_id=%s)", type(exc).__name__, request_id
        )
        raise unauthenticated() from None
    if identity is None:
        raise unauthenticated()
    try:
        record = reader.find_by_login_id(request, identity.login_id)
    except Exception as exc:
        if is_db_failure(exc):
            logger.error(
                "사용자 조회 중 DB 장애(503으로 닫음): %s (request_id=%s)",
                type(exc).__name__,
                request_id,
            )
            raise service_unavailable() from None
        logger.error(
            "인증 조회 실패(401로 닫음): %s (request_id=%s)", type(exc).__name__, request_id
        )
        raise unauthenticated() from None
    if record is None:
        raise user_not_registered()
    if not record.user.is_active:
        raise user_inactive()
    return record.user


# 라우트 함수 인자에 쓰는 별칭: `user: CurrentUserDep`
CurrentUserDep = Annotated[CurrentUser, Depends(current_user)]
