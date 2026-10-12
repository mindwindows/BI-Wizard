"""DB 예외 분류 도우미. 예외 메시지에는 SQL·파라미터가 섞일 수 있어 상태 코드와 클래스만 쓴다."""

from __future__ import annotations

from pg8000.exceptions import InterfaceError as Pg8000InterfaceError
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
# 문장 시간 초과(query_canceled): `statement_timeout`을 넘은 읽기.
STATEMENT_TIMEOUT_SQLSTATE = "57014"


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


def is_statement_timeout(exc: BaseException) -> bool:
    return sqlstate(exc) == STATEMENT_TIMEOUT_SQLSTATE


# SQLAlchemy가 감싸지 않고 그대로 올리는 연결 계층 예외: 소켓 시간 초과(긴 잠금 아래 `timeout`을
# 넘긴 읽기), 연결 끊김·거부, pg8000 자체의 네트워크 오류. 전역 핸들러가 503으로 바꾼다.
DB_NETWORK_ERRORS: tuple[type[BaseException], ...] = (
    TimeoutError,
    ConnectionError,
    Pg8000InterfaceError,
)


def is_db_unavailable(exc: BaseException) -> bool:
    """연결 실패·끊김·소켓 시간 초과·풀 고갈처럼 DB가 응답하지 못하는 경우."""
    return isinstance(
        exc,
        OperationalError | InterfaceError | DisconnectionError | PoolTimeoutError,
    ) or isinstance(exc, DB_NETWORK_ERRORS)


# SQLSTATE 앞 두 자리: 08 연결 예외, 53 자원 부족, 57 운영자 개입(관리자 종료 등).
_CONNECTION_SQLSTATE_CLASSES = frozenset({"08", "53", "57"})


def is_connection_failure(exc: BaseException) -> bool:
    """수식 같은 사용자 입력이 아니라 연결·서버 상태 때문에 난 DB 실패.

    `OperationalError`는 SQLite 같은 곳에서 문법·함수 오류에도 쓰이므로 클래스만 보지 않고, 연결
    끊김 표시(`connection_invalidated`)나 SQLSTATE 계열(08·53·57)을 함께 본다.
    """
    if isinstance(exc, (*DB_NETWORK_ERRORS, InterfaceError, DisconnectionError, PoolTimeoutError)):
        return True
    if isinstance(exc, DBAPIError):
        if exc.connection_invalidated:
            return True
        code = sqlstate(exc)
        return code is not None and code[:2] in _CONNECTION_SQLSTATE_CLASSES
    return False


def is_db_failure(exc: BaseException) -> bool:
    """사용자 조회 중 DB 계층에서 난 모든 오류와 연결 계층의 OS 오류. 인증에서 503으로 닫는다."""
    return isinstance(exc, SQLAlchemyError | OSError)
