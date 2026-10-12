"""모듈 사이 역방향 호출을 뒤집는 포트(04 §3). 구현은 소유 모듈이 하고 앱 팩토리가 연결한다."""

from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class DatasetSyncPort(Protocol):
    """Superset 가상 데이터셋 동기화 요청(구현은 `superset` 모듈, FU-1e).

    요청은 **커밋 뒤** 백그라운드에서 부른다. 구현은 예외를 밖으로 던지지 않아야 하고, 던져도
    호출한 요청의 결과는 바뀌지 않는다(호출 쪽이 기록만 한다).
    """

    def request_dataset_sync(self, dataset_id: int) -> None:
        """데이터셋 하나의 동기화를 요청한다."""
        ...

    def request_team_sync(self, team_id: int) -> None:
        """팀의 모든 가상 데이터셋 이름 갱신을 요청한다(팀 이름이 바뀐 뒤, 05 A4)."""
        ...


class NoopDatasetSync:
    """기본 구현. FU-1e에서 `superset` 모듈이 실제 구현으로 교체한다."""

    def request_dataset_sync(self, dataset_id: int) -> None:
        return None

    def request_team_sync(self, team_id: int) -> None:
        return None


def run_sync_request(port: DatasetSyncPort, team_id: int) -> None:
    """팀 단위 동기화를 요청하되 실패해도 예외를 밖으로 내지 않는다(응답은 이미 확정됐다)."""
    try:
        port.request_team_sync(team_id)
    except Exception as exc:
        # 상세는 클래스 이름만 남긴다(예외 메시지에 내부 정보가 섞일 수 있다).
        logger.error("팀 동기화 요청 실패: %s (team_id=%s)", type(exc).__name__, team_id)
