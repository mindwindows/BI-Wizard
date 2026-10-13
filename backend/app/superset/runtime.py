"""`superset` 모듈의 실행 부품을 설정으로 조립한다(앱 팩토리가 부른다)."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from app.config import SUPERSET_INTERNAL_URL, Settings
from app.superset.breaker import CircuitBreaker
from app.superset.client import DatasetApi, SupersetSession
from app.superset.constants import (
    BREAKER_COOLDOWN_SECONDS,
    BREAKER_FAILURE_THRESHOLD,
    GUEST_TOKEN_RATE_LIMIT,
    GUEST_TOKEN_RATE_WINDOW_SECONDS,
    ISSUER_TIMEOUT,
    SERVICE_TIMEOUT,
)
from app.superset.ratelimit import SlidingWindowLimiter
from app.superset.tokens import GuestTokenIssuer
from app.superset.worker import SupersetDatasetSync


@dataclass
class SupersetServices:
    """동기화 작업 스레드, 입장권 발급기, 사용자별 속도 제한기."""

    sync: SupersetDatasetSync
    issuer: GuestTokenIssuer
    limiter: SlidingWindowLimiter
    sessions: tuple[SupersetSession, ...]

    def stop(self) -> None:
        self.sync.stop()
        for session in self.sessions:
            session.close()


def superset_configured(settings: Settings) -> bool:
    """접속 설정 5개가 모두 있고 비어 있지 않을 때만 연동을 켠다(없어도 포털은 시작한다, 08
    §2-1)."""
    password = settings.superset_service_password
    issuer_password = settings.superset_guest_issuer_password
    return bool(
        settings.superset_app_root
        and settings.superset_service_user
        and password is not None
        and password.get_secret_value()
        and settings.superset_guest_issuer_user
        and issuer_password is not None
        and issuer_password.get_secret_value()
    )


def build_superset_services(
    settings: Settings,
    *,
    transport: httpx.BaseTransport | None = None,
    clock: Callable[[], float] = time.monotonic,
    base_url: str = SUPERSET_INTERNAL_URL,
    breaker_cooldown: float = BREAKER_COOLDOWN_SECONDS,
    **sync_options: float,
) -> SupersetServices | None:
    """설정이 모두 있으면 부품을 만든다. 없으면 None(동기화 요청은 no-op, E6은 503)."""
    if not superset_configured(settings):
        return None
    assert settings.superset_app_root is not None  # noqa: S101 - superset_configured가 확인했다
    assert settings.superset_service_user is not None  # noqa: S101
    assert settings.superset_service_password is not None  # noqa: S101
    assert settings.superset_guest_issuer_user is not None  # noqa: S101
    assert settings.superset_guest_issuer_password is not None  # noqa: S101
    root = settings.superset_app_root
    service_session = SupersetSession(
        root=root,
        base_url=base_url,
        username=settings.superset_service_user,
        password=settings.superset_service_password,
        timeout=SERVICE_TIMEOUT,
        transport=transport,
        clock=clock,
    )
    issuer_session = SupersetSession(
        root=root,
        base_url=base_url,
        username=settings.superset_guest_issuer_user,
        password=settings.superset_guest_issuer_password,
        timeout=ISSUER_TIMEOUT,
        transport=transport,
        clock=clock,
    )
    sync = SupersetDatasetSync(
        session=service_session,
        api=DatasetApi(service_session),
        breaker=CircuitBreaker(
            failure_threshold=BREAKER_FAILURE_THRESHOLD,
            cooldown_seconds=breaker_cooldown,
            clock=clock,
        ),
        clock=clock,
        **sync_options,
    )
    issuer = GuestTokenIssuer(
        issuer_session,
        CircuitBreaker(
            failure_threshold=BREAKER_FAILURE_THRESHOLD,
            cooldown_seconds=breaker_cooldown,
            clock=clock,
        ),
    )
    limiter = SlidingWindowLimiter(
        limit=GUEST_TOKEN_RATE_LIMIT, window_seconds=GUEST_TOKEN_RATE_WINDOW_SECONDS, clock=clock
    )
    return SupersetServices(sync, issuer, limiter, (service_session, issuer_session))
