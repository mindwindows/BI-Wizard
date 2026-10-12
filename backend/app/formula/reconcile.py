"""뷰 대조(시작 시 재생성)와 다시 시도(D10)(07 §8, 06 §5).

- 시작할 때 활성 데이터셋마다 **현재 정의로 계산한 정의 해시**와 `datasets.def_hash`를 비교하고 뷰가
  있는지 확인한다. 다르거나 없으면 그 데이터셋의 뷰만 정의 변경 진입점의 "버전을 올리지 않는" 형태로
  다시 만든다(잠금 -> 훅 -> `def_hash`). 같은 `datasets` 행 잠금을 쓰므로 정의 편집·다시 시도와
  직렬화된다. 짧은 `lock_timeout`(0.5초)으로 못 잡으면 실패로 남긴다.
- **시작을 막지 않는다.** 실패는 `ViewStatus`(프로세스 메모리)에 사유 코드와 쉬운 말 요약으로
  남고 `/health`의 `views_failed_count`와 D9에 나온다. 로그에는 클래스 이름·SQLSTATE만
  쓴다(SQL·상수 금지).
"""

from __future__ import annotations

import logging

from sqlalchemy import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app import ddl
from app.core.db_errors import is_lock_conflict, sqlstate
from app.core.errors import AppError, ErrorCode, definition_busy, not_found
from app.core.ports import DefinitionHooks
from app.dataset import definition as dataset_definition
from app.dataset import service as dataset_service
from app.formula import repo
from app.formula.hook import FORCE_KEY, is_postgresql, make_probe
from app.formula.literals import LiteralError
from app.formula.status import ViewStatus
from app.formula.views import (
    FormulaCompileFailure,
    build_column_infos,
    build_plan,
    compile_all,
    source_columns,
    source_table,
)

logger = logging.getLogger(__name__)

STARTUP_LOCK_TIMEOUT = "500ms"  # 07 §8 / X-17 범위 500ms~2s 중 시작 시 재생성은 짧게
RETRY_LOCK_TIMEOUT = dataset_definition.DEFINITION_LOCK_TIMEOUT


def failure_reason(exc: BaseException) -> str:
    """실패 사유 코드와 쉬운 말 요약. SQL·상수·비밀을 넣지 않는다."""
    if isinstance(exc, AppError):
        if exc.code == ErrorCode.DEFINITION_BUSY:
            return "LOCK_TIMEOUT: 다른 작업이 진행 중이라 뷰를 만들지 못했습니다."
        if exc.code in {ErrorCode.FORMULA_INVALID, ErrorCode.FORMULA_CIRCULAR}:
            return "FORMULA_INVALID: 저장된 수식에 문제가 있어 뷰를 만들지 못했습니다."
        return f"{exc.code}: 뷰를 만들지 못했습니다."
    if isinstance(exc, ddl.DdlError):
        return "VIEW_VERIFY_FAILED: 만든 뷰를 다시 읽어 확인하지 못해 되돌렸습니다."
    if isinstance(exc, LiteralError):
        return "LITERAL_INVALID: 수식 상수가 규칙에 맞지 않아 뷰를 만들지 못했습니다."
    if isinstance(exc, DBAPIError):
        if is_lock_conflict(exc):
            return "LOCK_TIMEOUT: 다른 작업이 진행 중이라 뷰를 만들지 못했습니다."
        return f"DB_ERROR: 데이터베이스 오류로 뷰를 만들지 못했습니다(코드 {sqlstate(exc) or '?'})."
    return f"UNEXPECTED: 예기치 않은 오류로 뷰를 만들지 못했습니다({type(exc).__name__})."


def view_needs_rebuild(session: Session, dataset_id: int) -> bool:
    """현재 정의의 해시가 저장된 해시와 다르거나 뷰가 없으면 True. 계산하지 못해도 True다."""
    try:
        defn = dataset_service.read_definition(session, dataset_id)
        stored = repo.load_formulas(session, dataset_id)
        infos = build_column_infos(defn, stored)
        ds = source_table(defn)
        probe = make_probe(session) if is_postgresql(session) else None
        try:
            results = compile_all(infos, source_columns(defn, ds), probe)
            plan = build_plan(defn, ds, results)
        except (FormulaCompileFailure, LiteralError):
            return True  # 잠금 아래에서 다시 계산하면 같은 오류가 사유로 남는다
        if plan.def_hash != defn.def_hash:
            return True
        conn = session.connection()
        return (
            ddl.view_column_names(conn, "dv", dataset_id) is None
            or ddl.view_column_names(conn, "de", dataset_id) is None
        )
    finally:
        session.rollback()


def rebuild(
    engine: Engine,
    hooks: DefinitionHooks,
    dataset_id: int,
    *,
    force: bool,
    lock_timeout: str,
) -> None:
    """뷰 하나를 정의 변경 진입점 안에서 다시 만든다(버전은 올리지 않는다). 실패하면 예외."""
    with Session(engine) as session:
        if force:
            session.info[FORCE_KEY] = True
        dataset_definition.apply_definition_change(
            session,
            hooks,
            dataset_id,
            expected_version=None,
            change=lambda _locked: (True, {}),
            bump=False,
            lock_timeout=lock_timeout,
        )


def reconcile_one(
    engine: Engine, hooks: DefinitionHooks, status: ViewStatus, dataset_id: int
) -> None:
    try:
        with Session(engine) as session:
            needed = view_needs_rebuild(session, dataset_id)
        if needed:
            rebuild(engine, hooks, dataset_id, force=False, lock_timeout=STARTUP_LOCK_TIMEOUT)
        status.ok(dataset_id)
    except Exception as exc:
        status.fail(dataset_id, failure_reason(exc))
        logger.error(
            "뷰 대조 실패: %s (dataset_id=%s, sqlstate=%s)",
            type(exc).__name__,
            dataset_id,
            sqlstate(exc),
        )


def reconcile_all(engine: Engine, hooks: DefinitionHooks, status: ViewStatus) -> None:
    """시작 때 모든 활성 데이터셋의 뷰를 대조한다. 실패는 밖으로 내지 않는다."""
    if engine.dialect.name != "postgresql":
        return  # 뷰 DDL은 PostgreSQL 전용이다(SQLite 시험 변형은 대조하지 않는다)
    try:
        with Session(engine) as session:
            dataset_ids = dataset_service.list_active_dataset_ids(session)
            session.rollback()
    except Exception as exc:
        logger.error("뷰 대조 목록을 읽지 못했다: %s", type(exc).__name__)
        return
    for dataset_id in dataset_ids:
        reconcile_one(engine, hooks, status, dataset_id)
    logger.info(
        "뷰 대조 완료: 활성 데이터셋 %d개, 실패 %d개", len(dataset_ids), status.failed_count
    )


def retry(
    engine: Engine,
    hooks: DefinitionHooks,
    status: ViewStatus,
    dataset_ids: list[int] | None,
) -> int:
    """D10: 실패한 뷰(또는 지정한 데이터셋)를 해시가 같아도 다시 만든다. 다시 만든 수를 돌려준다.

    락 대기 초과는 503 `DEFINITION_BUSY`로 중단한다(이미 처리한 것은 반영된 채 남는다).
    """
    targets = list(dataset_ids) if dataset_ids is not None else status.failed_ids()
    with Session(engine) as session:
        for dataset_id in targets:  # 없는 번호는 아무것도 하기 전에 404
            dataset_service.get_dataset_team_id(session, dataset_id)
        session.rollback()
    rebuilt = 0
    for dataset_id in targets:
        try:
            rebuild(engine, hooks, dataset_id, force=True, lock_timeout=RETRY_LOCK_TIMEOUT)
            rebuilt += 1
        except Exception as exc:
            status.fail(dataset_id, failure_reason(exc))
            logger.error(
                "뷰 다시 시도 실패: %s (dataset_id=%s, sqlstate=%s)",
                type(exc).__name__,
                dataset_id,
                sqlstate(exc),
            )
            if isinstance(exc, AppError) and exc.code == ErrorCode.DEFINITION_BUSY:
                raise definition_busy() from None
            if isinstance(exc, AppError) and exc.code == ErrorCode.NOT_FOUND:
                raise not_found() from None
    return rebuilt
