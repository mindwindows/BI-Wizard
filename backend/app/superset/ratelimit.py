"""사용자별 슬라이딩 윈도 속도 제한(입장권 발급, 승인 03b 23-1 C: 사용자당 60초에 30회).

- 저장소는 프로세스 메모리다(`dict[user_id, deque[시각]]` + 잠금). **backend 워커가 여러 개면 한도가
  워커별로 걸리므로 실효 한도는 워커 수 배가 된다.** 지금은 워커 1개 전제이고 워커를 늘리면 공유
  저장소로 재설계한다(08 §4, 06 §5).
- 검사와 기록은 같은 잠금 안에서 한다. 통과한 요청만 기록하므로 거절된 요청을 계속 보내도 윈도가
  밀려 영원히 막히지는 않는다.
- 시계와 한도·윈도는 생성자로 주입한다(시험).
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from collections.abc import Callable


class SlidingWindowLimiter:
    def __init__(
        self,
        *,
        limit: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._hits: dict[int, deque[float]] = {}

    def acquire(self, user_id: int) -> int | None:
        """통과하면 None, 한도를 넘으면 다시 시도할 때까지의 초(올림, 최소 1)를 돌려준다."""
        with self._lock:
            now = self._clock()
            hits = self._hits.setdefault(user_id, deque())
            while hits and now - hits[0] >= self._window:
                hits.popleft()
            if len(hits) >= self._limit:
                retry = math.ceil(self._window - (now - hits[0]))
                return max(1, retry)
            hits.append(now)
            return None

    def forget_idle(self) -> None:
        """윈도가 지난 기록이 전부인 사용자 키를 지운다(메모리 정리)."""
        with self._lock:
            now = self._clock()
            for user_id in [
                u for u, h in self._hits.items() if not h or now - h[-1] >= self._window
            ]:
                del self._hits[user_id]
