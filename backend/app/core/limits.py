"""무거운 읽기의 동시 실행 제한(07 §5).

미리보기(D3)·오류 칸 조회(D7·D8)·계산 열이 있는 행 조회(C1)가 공통으로 쓴다. 전역 동시 상한과
미리보기의 사용자당 동시 1건을 센다. 연결 풀이 5개(`max_overflow` 0)라 일반 요청용 연결 3개를
남기려고 전역 상한은 2건이다. 기다리지 않고 바로 429 `PREVIEW_BUSY`로 거절한다. 프로세스 메모리
값이며 worker 1개 전제다(06 §5).
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from app.core.errors import preview_busy

GLOBAL_HEAVY_READ_LIMIT = 2  # 07 §5 [제안]: 풀 5개 중 일반 요청용 3개를 남긴다


class HeavyReadLimiter:
    """무거운 읽기의 동시 실행 수를 센다."""

    def __init__(self, global_limit: int = GLOBAL_HEAVY_READ_LIMIT) -> None:
        self._lock = threading.Lock()
        self._limit = global_limit
        self._active = 0
        self._users: set[int] = set()

    @property
    def active(self) -> int:
        with self._lock:
            return self._active

    @contextmanager
    def slot(self, *, user_id: int | None = None) -> Iterator[None]:
        """자리 하나를 잡는다. `user_id`를 주면 그 사용자의 동시 1건 제한도 건다(미리보기)."""
        with self._lock:
            if self._active >= self._limit or (user_id is not None and user_id in self._users):
                raise preview_busy()
            self._active += 1
            if user_id is not None:
                self._users.add(user_id)
        try:
            yield
        finally:
            with self._lock:
                self._active -= 1
                if user_id is not None:
                    self._users.discard(user_id)
