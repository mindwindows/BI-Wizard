"""`DatasetSyncPort` 구현과 백그라운드 실행(08 §2-1, 설계 §3-6).

핵심 규칙(P4): **요청 처리 중에는 Superset을 부르지 않는다.** `request_*`는 짧은 DB 쓰기(`pending`
표시)와 큐 투입뿐이다. Superset 호출은 단일 작업 스레드 하나가 큐에서 꺼내 처리한다. 요청 스레드
풀(anyio)에서 Superset을 직접 부르면 Superset이 멈췄을 때 호출이 스레드를 줄줄이 붙잡아 다른 API가
굶는다.

- 큐는 같은 데이터셋 번호를 합친다(중복 병합). 요청이 올 때마다 데이터셋별 세대 번호를 올리고,
  처리 도중 세대가 바뀌면 `registered`로 쓰지 않고 `pending`으로 남겨 다시 처리한다.
- **디바운스:** 요청 경로(`request_*`)로 들어온 항목은 `SYNC_DEBOUNCE_SECONDS` 뒤에야 꺼낼 수 있다
  (`not_before`). 같은 데이터셋의 반복 요청은 첫 요청의 시각을 유지한 채 합쳐져(창을 연장하지
  않는다) Superset 호출 한 번이 된다. 데이터셋마다 독립이다. 시작 대조·자동 재시도가 넣는 항목은
  지연이 없고, 이미 지연 중인 항목이면 가장 이른 시각으로 당겨진다. `drain()`(시험·진단용)은 지연을
  건너뛴다. 시계는 주입된다.
- 서킷 브레이커: 연결 실패·시간 초과·5xx가 연속 3회면 30초 동안 Superset을 부르지 않고 대기 항목을
  `failed`(`UNAVAILABLE_*`)로 기록한다.
- 상태 기계: `pending` → `registered` | `failed`. `failed` 중 연결 문제(`UNAVAILABLE_*`)는
  주기적으로
  자동 재시도하고, 그 밖의 사유는 관리자의 "다시 시도"(E2)나 다음 시작 점검이 되돌린다.
- 시작 점검(결정 E): Superset `/health`가 200이 될 때까지 **이 스레드 안에서** 기다린 뒤(backend
  시작과
  Superset과 무관한 API는 기다리지 않는다) 활성·보관 데이터셋 전체를 대조한다: 등록 행이 없거나
  `pending`·`failed`면 큐에 넣고, `registered`는 Superset의 이름·SQL·열을 읽어 어긋나면 큐에 넣는다
  (커밋 직후 크래시로 열 변경이 반영되지 않은 틈).
- 로그에는 클래스 이름과 사유 코드만 남긴다(예외 메시지·URL·응답 본문·토큰 금지).
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.dataset import service as dataset_service
from app.superset import repo
from app.superset.breaker import CircuitBreaker
from app.superset.client import DatasetApi, SupersetSession
from app.superset.constants import (
    RETRY_INTERVAL_SECONDS,
    STARTUP_HEALTH_INTERVAL_SECONDS,
    STARTUP_HEALTH_MAX_WAIT_SECONDS,
    SYNC_DEBOUNCE_SECONDS,
)
from app.superset.errors import (
    UNAVAILABLE_CODES,
    SupersetError,
    SupersetLocalError,
    SupersetUnavailable,
    summarize,
)
from app.superset.naming import superset_name
from app.superset.sync import SyncPlan, is_in_sync, sync_dataset

logger = logging.getLogger(__name__)

_POLL_SECONDS = 0.2  # 큐가 비었을 때 타이머를 다시 확인하는 간격


class SupersetDatasetSync:
    """`DatasetSyncPort` 구현. Superset 접속 설정이 모두 있을 때만 앱 팩토리가 쓴다."""

    def __init__(
        self,
        *,
        session: SupersetSession,
        api: DatasetApi,
        breaker: CircuitBreaker,
        clock: Callable[[], float] = time.monotonic,
        health_interval: float = STARTUP_HEALTH_INTERVAL_SECONDS,
        health_max_wait: float = STARTUP_HEALTH_MAX_WAIT_SECONDS,
        retry_interval: float = RETRY_INTERVAL_SECONDS,
        poll_seconds: float = _POLL_SECONDS,
        debounce_seconds: float = SYNC_DEBOUNCE_SECONDS,
    ) -> None:
        self._session = session
        self._api = api
        self._breaker = breaker
        self._clock = clock
        self._health_interval = health_interval
        self._health_max_wait = health_max_wait
        self._retry_interval = retry_interval
        self._poll = poll_seconds
        self._debounce = debounce_seconds
        self._engine: Engine | None = None
        self._cond = threading.Condition()
        self._queue: OrderedDict[int, float] = OrderedDict()  # 데이터셋 번호 -> not_before
        self._generation: dict[int, int] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._startup_pending = True

    # --- 연결 ---

    def bind(self, engine: Engine) -> None:
        """DB 엔진을 받는다(엔진은 앱 lifespan에서 만들어진다)."""
        self._engine = engine

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="superset-sync", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._cond:
            self._cond.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    # --- DatasetSyncPort ---

    def request_dataset_sync(self, dataset_id: int) -> None:
        """데이터셋 하나의 동기화를 요청한다.

        `pending` 표시와 큐 투입뿐이다(Superset을 부르지 않는다)."""
        with self._cond:
            self._generation[dataset_id] = self._generation.get(dataset_id, 0) + 1
        self._mark_pending([dataset_id])
        self._enqueue([dataset_id], delay=self._debounce)

    def request_team_sync(self, team_id: int) -> None:
        """팀의 모든 가상 데이터셋 이름 갱신을 요청한다(팀 이름 변경 뒤, 05 A4)."""
        if self._engine is None:
            return
        with Session(self._engine) as session:
            ids = dataset_service.list_team_dataset_ids(session, team_id)
        for dataset_id in ids:
            self.request_dataset_sync(dataset_id)

    # --- 큐 ---

    def _enqueue(self, dataset_ids: list[int], *, delay: float = 0.0) -> None:
        """큐에 넣는다. 이미 있으면 합치되 `not_before`는 더 이른 쪽을 유지한다(창 연장 없음)."""
        with self._cond:
            not_before = self._clock() + delay
            for dataset_id in dataset_ids:
                current = self._queue.get(dataset_id)
                if current is None or not_before < current:
                    self._queue[dataset_id] = not_before
            self._cond.notify_all()

    def pending_ids(self) -> list[int]:
        with self._cond:
            return list(self._queue)

    def _next_ready(self, force: bool) -> int | None:
        """지금 꺼낼 수 있는 가장 앞의 항목(`force`면 지연 무시). 없으면 None. 잠금 안에서 쓴다."""
        now = self._clock()
        for dataset_id, not_before in self._queue.items():
            if force or not_before <= now:
                return dataset_id
        return None

    def _take(self, timeout: float, *, force: bool = False) -> int | None:
        with self._cond:
            dataset_id = self._next_ready(force)
            if dataset_id is None and timeout > 0:
                # 가장 이른 not_before까지만 기다린다(시계가 주입돼도 timeout이 상한이다).
                wake = min(self._queue.values(), default=None)
                wait = timeout if wake is None else min(timeout, max(0.0, wake - self._clock()))
                self._cond.wait(max(wait, 0.001))
                dataset_id = self._next_ready(force)
            if dataset_id is None:
                return None
            del self._queue[dataset_id]
            return dataset_id

    # --- DB ---

    def _mark_pending(self, dataset_ids: list[int]) -> None:
        """등록 행이 없으면 만들고 `pending`으로 표시한다. 실패해도 요청은 막지 않는다."""
        if self._engine is None:
            return
        try:
            with Session(self._engine) as session:
                for dataset_id in dataset_ids:
                    source = dataset_service.read_sync_source(session, dataset_id)
                    if source is None:
                        continue
                    repo.mark_pending(
                        session, dataset_id, superset_name(source.team_name, source.name)
                    )
                session.commit()
        except Exception as error:
            logger.error("동기 상태(pending) 기록 실패: %s", type(error).__name__)

    def _write_result(
        self,
        dataset_id: int,
        display_name: str,
        *,
        superset_id: int | None = None,
        error_code: str | None = None,
        generation: int | None = None,
    ) -> None:
        """결과를 기록한다.

        처리 도중 새 요청이 왔으면(세대 변경) 성공을 `registered`로 쓰지 않는다."""
        assert self._engine is not None  # noqa: S101 - _process가 확인했다
        try:
            with Session(self._engine) as session:
                if error_code is not None:
                    repo.mark_failed(session, dataset_id, display_name, summarize(error_code))
                elif superset_id is not None:
                    with self._cond:
                        stale = generation is not None and (
                            self._generation.get(dataset_id, 0) != generation
                        )
                    if stale:
                        repo.record_superset_id(session, dataset_id, display_name, superset_id)
                        # 처리 중 온 요청이 이미 지연 항목을 넣었다: 그 시각을 유지해 합친다.
                        self._enqueue([dataset_id], delay=self._debounce)
                    else:
                        repo.mark_registered(session, dataset_id, display_name, superset_id)
                session.commit()
        except Exception as error:
            logger.error("동기 상태 기록 실패: %s", type(error).__name__)

    # --- 한 건 처리 ---

    def process_next(self, timeout: float = 0.0, *, force: bool = False) -> bool:
        """지연이 끝난 항목 하나를 꺼내 처리한다. 처리했으면 True. `force`면 지연을 무시한다."""
        dataset_id = self._take(timeout, force=force)
        if dataset_id is None:
            return False
        self._process(dataset_id)
        return True

    def drain(self) -> int:
        """큐가 빌 때까지 처리한다(시험·진단용, 지연을 건너뛴다). 처리한 건수를 돌려준다."""
        count = 0
        while self.process_next(force=True):
            count += 1
        return count

    def _process(self, dataset_id: int) -> None:
        if self._engine is None:
            return
        with self._cond:
            generation = self._generation.get(dataset_id, 0)
        try:
            with Session(self._engine) as session:
                source = dataset_service.read_sync_source(session, dataset_id)
                row = repo.get_sync_row(session, dataset_id) if source is not None else None
        except Exception as error:
            logger.error("동기화 대상 읽기 실패: %s", type(error).__name__)
            self._enqueue([dataset_id])  # DB가 잠시 불가: 잠깐 쉰 뒤 다시 시도한다.
            self._stop.wait(1.0)
            return
        if source is None:
            return
        plan = SyncPlan.from_source(source)
        stored_id = row["superset_dataset_id"] if row is not None else None
        if not self._breaker.allow():
            self._write_result(dataset_id, plan.name, error_code="UNAVAILABLE_CONNECT")
            return

        def on_created(new_id: int) -> None:
            try:
                assert self._engine is not None  # noqa: S101
                with Session(self._engine) as session:
                    repo.record_superset_id(session, dataset_id, plan.name, new_id)
                    session.commit()
            except Exception as error:
                logger.error("Superset 번호 기록 실패: %s", type(error).__name__)

        try:
            superset_id = sync_dataset(self._api, plan, stored_id=stored_id, on_created=on_created)
        except SupersetUnavailable as error:
            self._breaker.record_failure()
            self._write_result(dataset_id, plan.name, error_code=error.code)
            return
        except SupersetError as error:
            if isinstance(error, SupersetLocalError):
                self._breaker.release_probe()  # Superset을 부르지 않은 로컬 오류: 기록하지 않는다.
            else:
                self._breaker.record_success()  # 연결은 된다: 거부는 이 데이터셋의 문제다.
            self._write_result(dataset_id, plan.name, error_code=error.code)
            return
        except Exception as error:
            logger.error("동기화 중 예기치 않은 오류: %s", type(error).__name__)
            self._breaker.release_probe()
            self._write_result(dataset_id, plan.name, error_code="INTERNAL")
            return
        self._breaker.record_success()
        self._write_result(dataset_id, plan.name, superset_id=superset_id, generation=generation)

    # --- 시작 점검·자동 재시도 ---

    def reconcile_all(self) -> int:
        """활성·보관 데이터셋 전체를 Superset과 대조해 어긋난 것을 큐에 넣는다(결정 E ①).

        Superset을 읽는 호출이 연결 문제로 실패하면 `SupersetUnavailable`을 그대로 올려 호출한 쪽이
        나중에 다시 하게 한다. 큐에 넣은 건수를 돌려준다.
        """
        if self._engine is None:
            return 0
        with Session(self._engine) as session:
            ids = dataset_service.list_startup_check_dataset_ids(session)
            rows = repo.all_sync_rows(session)
        queued = 0
        for dataset_id in ids:
            row = rows.get(dataset_id)
            if row is None or row["sync_status"] != "registered":
                self._enqueue([dataset_id])
                queued += 1
                continue
            with Session(self._engine) as session:
                source = dataset_service.read_sync_source(session, dataset_id)
            if source is None:
                continue
            if not self._breaker.allow():
                raise SupersetUnavailable("UNAVAILABLE_CONNECT")
            try:
                in_sync = is_in_sync(
                    self._api, SyncPlan.from_source(source), row["superset_dataset_id"]
                )
            except SupersetUnavailable:
                self._breaker.record_failure()
                raise
            except SupersetError as error:
                if isinstance(error, SupersetLocalError):
                    self._breaker.release_probe()
                else:
                    self._breaker.record_success()
                in_sync = False  # 읽을 수 없으면 다시 동기화해 사유를 남긴다.
            else:
                self._breaker.record_success()
            if not in_sync:
                self._enqueue([dataset_id])
                queued += 1
        return queued

    def requeue_unavailable(self) -> int:
        """연결 문제로 `failed`가 된 데이터셋을 다시 큐에 넣는다(Superset이 돌아왔을 수 있다)."""
        if self._engine is None:
            return 0
        with Session(self._engine) as session:
            rows = repo.all_sync_rows(session)
        ids = [
            dataset_id
            for dataset_id, row in rows.items()
            if row["sync_status"] == "failed"
            and (row["last_error"] or "").split(":", 1)[0] in UNAVAILABLE_CODES
        ]
        self._enqueue(sorted(ids))
        return len(ids)

    def _loop(self) -> None:
        clock = self._clock
        deadline = clock() + self._health_max_wait
        next_health = clock()
        next_retry = clock() + self._retry_interval
        while not self._stop.is_set():
            now = clock()
            try:
                if self._startup_pending and now >= next_health:
                    self._startup_step(now, deadline)
                    next_health = now + self._health_interval
                if now >= next_retry:
                    self.requeue_unavailable()
                    next_retry = now + self._retry_interval
                self.process_next(timeout=self._poll)
            except Exception as error:  # 작업 스레드는 어떤 오류로도 멈추지 않는다.
                logger.error("동기화 작업 스레드 오류: %s", type(error).__name__)
                self._stop.wait(self._poll)

    def _startup_step(self, now: float, deadline: float) -> None:
        """Superset이 준비됐으면 전체 대조를 한 번 하고 끝낸다. 아직이면 다음 간격에 다시 본다."""
        if not self._session.health():
            if now >= deadline:
                self._startup_pending = False
                logger.warning("Superset 준비를 기다리다 포기했다(주기 재시도가 이어서 처리한다).")
            return
        try:
            queued = self.reconcile_all()
        except SupersetUnavailable:
            return  # 아직 불안정하다: 다음 간격에 다시 대조한다.
        self._startup_pending = False
        logger.info("Superset 시작 대조 완료: 동기화 대기 %d건", queued)

    @property
    def startup_pending(self) -> bool:
        return self._startup_pending
