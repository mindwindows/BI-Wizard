"""입장권(guest token) 발급(E6, 08 §4).

- 발급 전용 계정 세션(`bi_guest_issuer`)으로 Superset의 `POST /security/guest_token/`을 부른다.
  본문: `user.username`(포털 사용자 번호 문자열)만, `resources`는 대시보드 하나(embedded uuid 소문자
  정규형), `rls`는 **항상 빈 목록**이다. 클라이언트 입력은 어느 것도 이 본문에 들어가지 않는다.
- backend는 토큰을 만들거나 해석하지 않는다(서명 키 없음, JWT 라이브러리 없음, AP-1). Superset이 준
  글자를 그대로 돌려줄 뿐이다.
- **토큰은 함수의 지역 변수로만 다루고 로그·예외 메시지·`last_error`·캐시 어디에도 남기지 않는다.**
  실패는 사유 코드만 담은 예외로 올린다.
- 동시 호출 수를 제한하고 서킷 브레이커를 둔다: Superset이 멈췄을 때 요청 스레드가 줄줄이 타임아웃을
  기다려 다른 API가 굶는 일을 막는다(P4).
"""

from __future__ import annotations

import logging
import threading
import uuid

from app.superset.breaker import CircuitBreaker
from app.superset.client import SupersetSession
from app.superset.constants import ISSUER_MAX_CONCURRENT
from app.superset.errors import SupersetError, SupersetRejected, SupersetUnavailable

logger = logging.getLogger(__name__)

_GUEST_TOKEN_PATH = "/api/v1/security/guest_token/"  # noqa: S105 - API 경로
_ACQUIRE_TIMEOUT_SECONDS = 2.0


def canonical_uuid(value: uuid.UUID | str) -> str:
    """하이픈 있는 36자 소문자 정규형(훅의 형식 검사 요건, 프로브 P-3: 대문자는 훅을 통과해
    버린다)."""
    return str(value if isinstance(value, uuid.UUID) else uuid.UUID(value))


class GuestTokenIssuer:
    def __init__(
        self,
        session: SupersetSession,
        breaker: CircuitBreaker,
        *,
        max_concurrent: int = ISSUER_MAX_CONCURRENT,
    ) -> None:
        self._session = session
        self._breaker = breaker
        self._slots = threading.BoundedSemaphore(max_concurrent)

    def issue(self, *, username: str, dashboard_uuid: uuid.UUID | str) -> str:
        """입장권 글자 하나를 돌려준다. 실패는 `SupersetUnavailable`/`SupersetRejected`(코드만)."""
        if not self._breaker.allow():
            raise SupersetUnavailable("UNAVAILABLE_CONNECT")
        if not self._slots.acquire(timeout=_ACQUIRE_TIMEOUT_SECONDS):
            raise SupersetUnavailable("UNAVAILABLE_TIMEOUT")
        try:
            body = {
                "user": {"username": username},
                "resources": [{"type": "dashboard", "id": canonical_uuid(dashboard_uuid)}],
                "rls": [],
            }
            try:
                response = self._session.request("POST", _GUEST_TOKEN_PATH, json=body, csrf=True)
                token = self._session.json(response).get("token")
            except SupersetUnavailable:
                self._breaker.record_failure()
                raise
            except SupersetError:
                self._breaker.record_success()  # 연결은 된다. 거부는 입력·권한 문제다.
                raise
            except Exception as error:  # 클라이언트 경계가 못 바꾼 예외: 클래스 이름만 남긴다
                logger.error("입장권 발급 중 예기치 않은 예외: %s", type(error).__name__)
                self._breaker.record_success()
                raise SupersetRejected("INTERNAL") from None
            self._breaker.record_success()
            if not isinstance(token, str) or not token:
                raise SupersetRejected("BAD_RESPONSE")
            return token
        finally:
            self._slots.release()
