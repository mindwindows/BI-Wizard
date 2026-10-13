"""superset 모듈 시험 공용 도구."""

from __future__ import annotations

from collections.abc import Callable

import httpx
from pydantic import SecretStr

from app.superset.client import DatasetApi, SupersetSession
from tests.fake_superset import ROOT, FakeSuperset

BASE_URL = "http://superset:8088"
SERVICE = ("bi_service", "svc-pw-SECRET-1")
ISSUER = ("bi_guest_issuer", "iss-pw-SECRET-2")
SUPERSET_ENV = {
    "SUPERSET_APP_ROOT": ROOT,
    "SUPERSET_SERVICE_USER": SERVICE[0],
    "SUPERSET_SERVICE_PASSWORD": SERVICE[1],
    "SUPERSET_GUEST_ISSUER_USER": ISSUER[0],
    "SUPERSET_GUEST_ISSUER_PASSWORD": ISSUER[1],
}


def make_session(
    fake: FakeSuperset,
    account: tuple[str, str] = SERVICE,
    timeout: float = 5.0,
    clock: Callable[[], float] | None = None,
) -> SupersetSession:
    extra = {} if clock is None else {"clock": clock}
    return SupersetSession(
        root=ROOT,
        base_url=BASE_URL,
        username=account[0],
        password=SecretStr(account[1]),
        timeout=httpx.Timeout(timeout),
        transport=fake.transport,
        **extra,
    )


def make_api(fake: FakeSuperset) -> DatasetApi:
    return DatasetApi(make_session(fake))


class Clock:
    """주입용 시계: `clock.now`를 직접 움직인다."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def settled(condition: Callable[[], bool], timeout: float = 5.0) -> bool:
    """조건이 참이 될 때까지 짧게 기다린다(백그라운드 스레드 시험용)."""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return condition()
