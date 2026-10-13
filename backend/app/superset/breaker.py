"""서킷 브레이커: 연속 실패가 한계에 닿으면 일정 시간 호출을 건너뛴다(08 §2-1, P4).

Superset이 멈췄을 때 호출마다 타임아웃을 기다리는 일을 막는다. 쿨다운이 지나면 **한 건만** 시험
호출을 통과시키고(반열림) 나머지는 그 결과가 날 때까지 막는다. 성공하면 닫고 실패하면 다시 연다.
시험 호출의 결과가 기록되지 않은 채(예기치 않은 예외 등) 쿨다운만큼 지나면 다음 한 건을 다시
통과시킨다(영영 막히지 않게). 프로세스 메모리 값이다. 시계는 주입할 수 있다(시험).
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
        self._probe_started: float | None = None  # 반열림 시험 호출이 나간 시각

    def allow(self) -> bool:
        """지금 호출해도 되는가.

        닫혀 있으면 참이다. 열려 있으면 쿨다운이 끝나기 전까지 거짓이고, 끝난 뒤에는 시험 호출 한
        건에만 참이다(그 결과를 기록할 때까지 나머지는 거짓).
        """
        with self._lock:
            if self._opened_at is None:
                return True
            now = self._clock()
            if self._probe_started is not None and now - self._probe_started < self._cooldown:
                return False  # 시험 호출이 진행 중이다.
            if now - self._opened_at >= self._cooldown:
                self._probe_started = now
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None
            self._probe_started = None

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._probe_started is not None or self._failures >= self._threshold:
                # 시험 호출이 실패했거나 연속 실패가 한계에 닿았다: (다시) 연다.
                self._opened_at = self._clock()
                self._probe_started = None

    def release_probe(self) -> None:
        """결과를 기록하지 않고 시험 호출 자리만 푼다(Superset을 부르지 않은 로컬 오류용).

        닫혀 있으면 아무 일도 없다. 반열림이면 다음 호출이 다시 시험한다."""
        with self._lock:
            self._probe_started = None

    @property
    def is_open(self) -> bool:
        """열림 또는 반열림(시험 호출을 기다리는 중)인가."""
        with self._lock:
            return self._opened_at is not None
