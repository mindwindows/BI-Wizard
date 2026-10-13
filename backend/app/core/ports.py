"""모듈 사이 역방향 호출을 뒤집는 포트(04 §3). 구현은 소유 모듈이 하고 앱 팩토리가 연결한다."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class DefinitionChangeHook(Protocol):
    """데이터셋 정의 변경 훅(04 §3, §5). formula 모듈이 1d에서 등록해 수식·의존·뷰를 만든다.

    정의 변경 진입점이 **같은 트랜잭션 안에서**(행 잠금 → 버전 확인 → 열 변경 뒤, `def_hash` 기록
    전에) 부른다. 새 열 `id`가 이미 있는 상태이며, 예외를 올리면 열 변경과 동적 DDL까지
    전부 롤백된다. 돌려주는 글자는 방금 만든 뷰 정의의 해시이고 진입점이 `datasets.def_hash`에
    기록한다(없으면 `None`: 해시를 바꾸지 않는다, 06 §5).
    """

    def __call__(self, session: Session, dataset_id: int) -> str | None: ...


class DefinitionHooks:
    """정의 변경 훅 등록부. 등록 순서대로 부른다. 등록된 훅이 없으면 no-op 지점이다."""

    def __init__(self) -> None:
        self._hooks: list[Callable[[Session, int], str | None]] = []

    def register(self, hook: Callable[[Session, int], str | None]) -> None:
        self._hooks.append(hook)

    def run(self, session: Session, dataset_id: int) -> str | None:
        """훅을 차례로 부르고 마지막으로 돌려받은 `def_hash` 값(없으면 None)을 돌려준다."""
        def_hash: str | None = None
        for hook in self._hooks:
            result = hook(session, dataset_id)
            if result is not None:
                def_hash = result
        return def_hash

    def __len__(self) -> int:
        return len(self._hooks)


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


def run_dataset_sync_request(port: DatasetSyncPort, dataset_id: int) -> None:
    """데이터셋 동기화를 요청하되 실패해도 예외를 밖으로 내지 않는다(커밋 뒤라 응답은 확정됐다)."""
    try:
        port.request_dataset_sync(dataset_id)
    except Exception as exc:
        logger.error(
            "데이터셋 동기화 요청 실패: %s (dataset_id=%s)", type(exc).__name__, dataset_id
        )


def run_sync_request(port: DatasetSyncPort, team_id: int) -> None:
    """팀 단위 동기화를 요청하되 실패해도 예외를 밖으로 내지 않는다(응답은 이미 확정됐다)."""
    try:
        port.request_team_sync(team_id)
    except Exception as exc:
        # 상세는 클래스 이름만 남긴다(예외 메시지에 내부 정보가 섞일 수 있다).
        logger.error("팀 동기화 요청 실패: %s (team_id=%s)", type(exc).__name__, team_id)


@dataclass(frozen=True)
class ComputedRow:
    """한 행의 계산 열 결과. 키는 계산 열 번호(`dataset_columns.id`)다."""

    # DB 값 형(Decimal·date·bool·str·None)
    values: Mapping[int, Any] = field(default_factory=dict)
    # 오류 칸의 셀 오류 코드("E1" 등, 05 §3)
    errors: Mapping[int, str] = field(default_factory=dict)


class RowViewPort(Protocol):
    """행 조회가 계산 열 값과 오류 칸을 받는 포트(04 §3, 07 §3-1). 구현은 formula 모듈(FU-1d).

    `entry`는 데이터셋에 계산 열(`kind='formula'`)이 있을 때만 부른다. 같은 세션(트랜잭션)으로
    읽으므로 방금 쓴 행도 보인다. 돌려주는 매핑에 없는 행은 계산 열이 모두 빈 값(오류 아님)이다.
    """

    def read_computed(
        self,
        session: Session,
        dataset_id: int,
        row_ids: Sequence[int],
        column_ids: Sequence[int],
    ) -> Mapping[int, ComputedRow]: ...


class PlainRowView:
    """기본 구현(1c): 계산 열 값이 없고 오류 칸도 없다(`errors`는 항상 `{}`). 1d가 교체한다."""

    def read_computed(
        self,
        session: Session,
        dataset_id: int,
        row_ids: Sequence[int],
        column_ids: Sequence[int],
    ) -> Mapping[int, ComputedRow]:
        return {}
