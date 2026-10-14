"""뷰 대조 결과(프로세스 메모리).

- `ViewStatus`: 시작 시 대조·재시도가 확인한 데이터셋(활성·보관) 수(`views`)와
  실패(`views_failed_count`, 실패 목록의 사유·시각). `/health`(05 H1)와 D9가 같은 값을 읽는다.
  영속되는 것은 `datasets.def_hash` 표 값뿐이고 이 값은 **프로세스 메모리**다(worker 1개 전제,
  06 §5). 사유에는 SQL·비밀을 넣지 않는다.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.startup_check import StartupReport


@dataclass(frozen=True)
class ViewFailure:
    dataset_id: int
    reason: str  # 사유 코드와 쉬운 말 요약(SQL·비밀 없음)
    since: datetime


class ViewStatus:
    """뷰 대조 결과. 스레드 안전하다(요청은 스레드풀에서 실행된다)."""

    def __init__(self, report: StartupReport | None = None) -> None:
        self._lock = threading.Lock()
        self._report = report
        self._known: set[int] = set()
        self._failures: dict[int, ViewFailure] = {}

    def bind(self, report: StartupReport) -> None:
        """`/health` 본문이 읽는 시작 점검 결과 객체에 연결한다(값은 대조 결과가 생길 때
        반영한다)."""
        with self._lock:
            self._report = report

    def _sync(self) -> None:
        if self._report is not None:
            self._report.views = len(self._known)
            self._report.views_failed_count = len(self._failures)

    def ok(self, dataset_id: int) -> None:
        with self._lock:
            self._known.add(dataset_id)
            self._failures.pop(dataset_id, None)
            self._sync()

    def fail(self, dataset_id: int, reason: str) -> None:
        with self._lock:
            self._known.add(dataset_id)
            previous = self._failures.get(dataset_id)
            since = previous.since if previous is not None else datetime.now(UTC)
            self._failures[dataset_id] = ViewFailure(dataset_id, reason, since)
            self._sync()

    @property
    def views(self) -> int:
        with self._lock:
            return len(self._known)

    @property
    def failed_count(self) -> int:
        with self._lock:
            return len(self._failures)

    def failures(self) -> list[ViewFailure]:
        with self._lock:
            return sorted(self._failures.values(), key=lambda f: f.dataset_id)

    def failed_ids(self) -> list[int]:
        with self._lock:
            return sorted(self._failures)
