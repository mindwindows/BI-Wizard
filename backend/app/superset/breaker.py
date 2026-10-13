"""서킷 브레이커: 연속 실패가 한계에 닿으면 일정 시간 호출을 건너뛴다(08 §2-1, P4).

Superset이 멈췄을 때 호출마다 타임아웃을 기다리는 일을 막는다. 쿨다운이 지나면 한 번
시도하고(반열림),
성공하면 닫고 실패하면 다시 연다. 프로세스 메모리 값이다. 시계는 주입할 수 있다(시험).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class CircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int,
        cooldown_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._threshold = failure_threshold
        self._cooldown = cooldown_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._failures = 0
        self._opened_at: float | None = None

    def allow(self) -> bool:
        """지금 호출해도 되는가. 열려 있으면 쿨다운이 끝나기 전까지 거짓이다."""
        with self._lock:
            if self._opened_at is None:
                return True
            if self._clock() - self._opened_at >= self._cooldown:
                # 반열림: 한 번 시도하게 한다. 실패하면 record_failure가 다시 연다.
                self._opened_at = None
                self._failures = self._threshold - 1
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self._threshold:
                self._opened_at = self._clock()

    @property
    def is_open(self) -> bool:
        with self._lock:
            return self._opened_at is not None and (
                self._clock() - self._opened_at < self._cooldown
            )
