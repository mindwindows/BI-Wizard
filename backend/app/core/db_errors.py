"""DB 예외 분류 도우미. 예외 메시지에는 SQL·파라미터가 섞일 수 있어 상태 코드와 클래스만 쓴다."""

from __future__ import annotations

from sqlalchemy.exc import (
    DBAPIError,
    DisconnectionError,
    InterfaceError,
    OperationalError,
    SQLAlchemyError,
)
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

# 잠금 대기 초과(lock_not_available)와 교착(deadlock_detected): 다시 시도하면 되는 오류.
LOCK_TIMEOUT_SQLSTATE = "55P03"
DEADLOCK_SQLSTATE = "40P01"


def sqlstate(exc: BaseException) -> str | None:
    """pg8000이 올린 DB 오류의 SQLSTATE(5자리). 알 수 없으면 None."""
    if not isinstance(exc, DBAPIError):
        return None
    args = getattr(exc.orig, "args", ())
    if args and isinstance(args[0], dict):
        code = args[0].get("C")
        return str(code) if code else None
    return None


def constraint_name(exc: BaseException) -> str | None:
    """제약 위반(23xxx) 오류가 알려 주는 제약 이름(pg8000의 오류 필드 `n`). 없으면 None."""
    if not isinstance(exc, DBAPIError):
        return None
    args = getattr(exc.orig, "args", ())
    if args and isinstance(args[0], dict):
        name = args[0].get("n")
        return str(name) if name else None
    return None


def is_lock_conflict(exc: BaseException) -> bool:
    return sqlstate(exc) in {LOCK_TIMEOUT_SQLSTATE, DEADLOCK_SQLSTATE}


def is_db_unavailable(exc: BaseException) -> bool:
    """연결 실패·끊김·풀 고갈처럼 DB가 응답하지 못하는 경우(요청 처리 중 일반 처리용)."""
    return isinstance(
        exc, OperationalError | InterfaceError | DisconnectionError | PoolTimeoutError
    )


def is_db_failure(exc: BaseException) -> bool:
    """사용자 조회 중 DB 계층에서 난 모든 오류와 연결 계층의 OS 오류. 인증에서 503으로 닫는다."""
    return isinstance(exc, SQLAlchemyError | OSError)
