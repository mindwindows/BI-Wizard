"""오류 형식(05 §1)과 오류 코드 사전(05 §3).

모든 오류 응답은 `{"error": {"code", "message", "details", "request_id"}}` 모양이다.
- `message`는 사용자에게 보여 줄 한국어 문구다. SQL·내부 용어·입력 값·비밀을 넣지 않는다.
- 예기치 않은 예외의 상세는 로그에만 남기고 응답에는 넣지 않는다(`INTERNAL_ERROR`).
- `details`가 없는 오류는 빈 객체 `{}`다.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.db_errors import DB_NETWORK_ERRORS, is_db_unavailable
from app.core.request_id import REQUEST_ID_HEADER, get_request_id

logger = logging.getLogger(__name__)


class ErrorCode:
    """05 §3 사전의 코드. 문자열 상수라 JSON에 그대로 나간다."""

    UNAUTHENTICATED = "UNAUTHENTICATED"
    USER_NOT_REGISTERED = "USER_NOT_REGISTERED"
    USER_INACTIVE = "USER_INACTIVE"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    ROW_NOT_FOUND = "ROW_NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    DEFINITION_VERSION_MISMATCH = "DEFINITION_VERSION_MISMATCH"
    CELL_CONFLICT = "CELL_CONFLICT"
    PASTE_CONFLICT = "PASTE_CONFLICT"
    PERIOD_CONFLICT = "PERIOD_CONFLICT"
    DATASET_HAS_ROWS = "DATASET_HAS_ROWS"
    COLUMN_LOCKED = "COLUMN_LOCKED"
    LAST_ADMIN = "LAST_ADMIN"
    WRITE_BUSY = "WRITE_BUSY"
    FORMULA_INVALID = "FORMULA_INVALID"
    FORMULA_CIRCULAR = "FORMULA_CIRCULAR"
    FORMULA_RUNTIME_ERROR = "FORMULA_RUNTIME_ERROR"
    DEFINITION_BUSY = "DEFINITION_BUSY"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    PREVIEW_BUSY = "PREVIEW_BUSY"
    GUEST_TOKEN_RATE_LIMITED = "GUEST_TOKEN_RATE_LIMITED"  # noqa: S105 - 오류 코드 이름
    SUPERSET_REJECTED = "SUPERSET_REJECTED"
    SUPERSET_UNAVAILABLE = "SUPERSET_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"  # 405 (03b 17-1 결정 1, 05 §3)
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"  # 503 DB 등 내부 의존 장애 (03b 17-1 결정 2)
    TARGET_INACTIVE = "TARGET_INACTIVE"  # 409 비활성 팀·사용자에 소속 추가·변경 (03b 17-1 결정 3)
    DATASET_ARCHIVED = "DATASET_ARCHIVED"  # 409 보관된 데이터셋에 정의·입력 쓰기 (FU-2b, 03b 30-1)


class FieldErrorCode:
    """`VALIDATION_ERROR`의 `details.fields[].code`(05 §3 아래 목록)."""

    REQUIRED = "REQUIRED"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    BAD_FORMAT = "BAD_FORMAT"
    NOT_IN_OPTIONS = "NOT_IN_OPTIONS"
    NOT_PERIOD_START = "NOT_PERIOD_START"
    READ_ONLY = "READ_ONLY"
    TOO_LONG = "TOO_LONG"
    RESERVED = "RESERVED"


class AppError(Exception):
    """업무 코드에서 던지는 예상된 오류. 핸들러가 05 §1 형식으로 바꾼다."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int,
        details: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details: dict[str, Any] = dict(details) if details else {}
        self.headers = dict(headers) if headers else None


def unauthenticated() -> AppError:
    return AppError(ErrorCode.UNAUTHENTICATED, "로그인이 필요합니다.", status_code=401)


def user_not_registered() -> AppError:
    return AppError(
        ErrorCode.USER_NOT_REGISTERED,
        "접근 권한이 없습니다. 관리자에게 등록을 요청하세요.",
        status_code=403,
    )


def user_inactive() -> AppError:
    return AppError(
        ErrorCode.USER_INACTIVE, "사용이 중지된 계정입니다. 관리자에게 문의하세요.", status_code=403
    )


def forbidden() -> AppError:
    return AppError(ErrorCode.FORBIDDEN, "이 작업을 할 권한이 없습니다.", status_code=403)


def not_found() -> AppError:
    return AppError(ErrorCode.NOT_FOUND, "요청한 대상을 찾을 수 없습니다.", status_code=404)


def already_exists(field: str, message: str) -> AppError:
    """유일 값 중복(409 `ALREADY_EXISTS`). `details.field`는 중복된 필드 이름이다(05 §3)."""
    return AppError(ErrorCode.ALREADY_EXISTS, message, status_code=409, details={"field": field})


def service_unavailable() -> AppError:
    """DB 등 내부 의존 장애. 로그아웃(401)과 구분하며 접근은 계속 닫혀 있다(fail-closed)."""
    return AppError(
        ErrorCode.SERVICE_UNAVAILABLE,
        "일시적으로 서비스를 이용할 수 없습니다. 잠시 후 다시 시도하세요.",
        status_code=503,
    )


def target_inactive(field: str, message: str | None = None) -> AppError:
    """비활성 팀(`team`)·사용자(`user`)에 소속을 추가·변경하려 했다(A8). 해제(A9)는 허용된다.

    `message`를 주면 다른 작업(예: B2 데이터셋 만들기)의 문구로 바꾼다. 코드와 `details`는 같다.
    """
    label = "팀" if field == "team" else "사용자"
    return AppError(
        ErrorCode.TARGET_INACTIVE,
        message or f"사용 중지된 {label}에는 소속을 추가하거나 역할을 바꿀 수 없습니다.",
        status_code=409,
        details={"field": field},
    )


def definition_version_mismatch(current_version: int) -> AppError:
    return AppError(
        ErrorCode.DEFINITION_VERSION_MISMATCH,
        "다른 사람이 먼저 정의를 바꿨습니다. 새로 고친 뒤 다시 시도하세요.",
        status_code=409,
        details={"current_version": current_version},
    )


# 정의 변경 락 대기 초과 때 화면이 다시 시도를 안내할 때까지의 초(05 §3 `retry_after`).
DEFINITION_RETRY_AFTER_SECONDS = 2


def definition_busy() -> AppError:
    return AppError(
        ErrorCode.DEFINITION_BUSY,
        "다른 작업이 진행 중입니다. 잠시 후 다시 시도하세요.",
        status_code=503,
        details={"retry_after": DEFINITION_RETRY_AFTER_SECONDS},
    )


def dataset_archived() -> AppError:
    """보관된 데이터셋에 정의·입력 쓰기를 시도했다(B4 B5 B6 C2 C3 C4 D4 D5, 05 §3)."""
    return AppError(
        ErrorCode.DATASET_ARCHIVED,
        "보관된 데이터셋은 고칠 수 없습니다. 복구한 뒤 다시 시도하세요.",
        status_code=409,
        details={"status": "archived"},
    )


def dataset_has_rows() -> AppError:
    return AppError(
        ErrorCode.DATASET_HAS_ROWS,
        "입력된 행이 있어 바꿀 수 없습니다. 행이 없는 데이터셋에서만 바꿀 수 있습니다.",
        status_code=422,
    )


def column_locked() -> AppError:
    return AppError(
        ErrorCode.COLUMN_LOCKED,
        "열의 형식과 종류는 바꿀 수 없습니다. 새 열을 추가하세요.",
        status_code=422,
    )


def validation_failed(fields: list[tuple[str, str]]) -> AppError:
    """서비스 단계의 입력 규칙 위반(422 `VALIDATION_ERROR`). `fields`는 (필드, 필드 코드) 목록."""
    return AppError(
        ErrorCode.VALIDATION_ERROR,
        "입력한 내용을 확인해 주세요.",
        status_code=422,
        details={
            "fields": [
                {"field": field, "code": code, "message": _FIELD_MESSAGES.get(code, "")}
                for field, code in fields
            ]
        },
    )


def _cap(items: list[dict[str, Any]], limit: int) -> dict[str, Any]:
    """응답 상한 처리(05 §1 잘림 표시): `truncated`는 항상, `total`은 자르기 전 전체 건수."""
    return {"truncated": len(items) > limit, "total": len(items)}


def validation_failed_items(items: list[dict[str, Any]], *, limit: int) -> AppError:
    """입력 규칙 위반(422)을 항목 단위로 돌려준다. 각 항목은 `code`와 위치 키를 가진다.

    위치 키는 `field`(예: `cells.12`) 또는 `row_index`+`column_id`(붙여넣기, 05 §1 오류 형식)다.
    `message`는 `code`로 채운다. 입력 값은 응답에 넣지 않는다. 전체 목록을 받아 `limit`건에서 자르고
    `details.truncated`·`details.total`(자르기 전 전체 건수)을 넣는다.
    """
    return AppError(
        ErrorCode.VALIDATION_ERROR,
        "입력한 내용을 확인해 주세요.",
        status_code=422,
        details={
            "fields": [
                {**item, "message": _FIELD_MESSAGES.get(item["code"], "")} for item in items[:limit]
            ],
            **_cap(items, limit),
        },
    )


# 행 쓰기의 락 대기 초과·교착 때 화면이 다시 시도를 안내할 때까지의 초(05 §3 `retry_after`).
WRITE_RETRY_AFTER_SECONDS = 2


def write_busy() -> AppError:
    return AppError(
        ErrorCode.WRITE_BUSY,
        "다른 사람이 같은 데이터를 입력하고 있습니다. 잠시 후 다시 시도하세요.",
        status_code=503,
        details={"retry_after": WRITE_RETRY_AFTER_SECONDS},
    )


def row_not_found() -> AppError:
    return AppError(ErrorCode.ROW_NOT_FOUND, "요청한 행을 찾을 수 없습니다.", status_code=404)


def cell_conflict(conflicts: list[dict[str, Any]]) -> AppError:
    """C3: 다른 사람이 먼저 칸 값을 바꿨다. `conflicts[{row_id, column_id, current}]`."""
    return AppError(
        ErrorCode.CELL_CONFLICT,
        "다른 사람이 먼저 값을 바꿨습니다. 최신 값을 확인한 뒤 다시 시도하세요.",
        status_code=409,
        details={"conflicts": conflicts},
    )


def period_conflict(conflicts: list[dict[str, Any]]) -> AppError:
    """C2·C3: 같은 기간의 행이 이미 있다. `conflicts[{row_id, column_id, current}]`(그 행)."""
    return AppError(
        ErrorCode.PERIOD_CONFLICT,
        "같은 기간의 행이 이미 있습니다.",
        status_code=409,
        details={"conflicts": conflicts},
    )


def paste_conflict(conflicts: list[dict[str, Any]], *, limit: int) -> AppError:
    """C4: 붙여넣기 충돌(전부 취소). `conflicts[{row_index, row_id, column_id, kind, current}]`.

    전체 목록을 받아 `limit`건에서 자르고 `details.truncated`·`details.total`을 넣는다(05 §1).
    """
    return AppError(
        ErrorCode.PASTE_CONFLICT,
        "붙여넣기가 다른 사람의 변경과 충돌해 아무것도 반영하지 않았습니다.",
        status_code=409,
        details={"conflicts": conflicts[:limit], **_cap(conflicts, limit)},
    )


def payload_too_large(limit: int, message: str) -> AppError:
    """C4 요청 상한 초과. `details.limit`은 넘긴 상한 값이다(행 수 또는 바이트 수, 문구로 구분)."""
    return AppError(ErrorCode.PAYLOAD_TOO_LARGE, message, status_code=413, details={"limit": limit})


def formula_invalid(errors: list[dict[str, Any]]) -> AppError:
    """수식 검사(C0) 실패(422 `FORMULA_INVALID`). `details.errors`는 D2와 같은 모양이다."""
    return AppError(
        ErrorCode.FORMULA_INVALID,
        "수식에 고칠 곳이 있어 저장하지 않았습니다.",
        status_code=422,
        details={"errors": errors, **_cap(errors, len(errors))},
    )


def formula_circular(path: list[str]) -> AppError:
    """순환 참조(422 `FORMULA_CIRCULAR`). `details.path`는 열 이름 경로다(A → B → A)."""
    return AppError(
        ErrorCode.FORMULA_CIRCULAR,
        "계산 열이 서로를 참조하는 순환이 생겨 저장할 수 없습니다: " + " → ".join(path),
        status_code=422,
        details={"path": path},
    )


def formula_runtime_error() -> AppError:
    """계산 불가(422 `FORMULA_RUNTIME_ERROR`): DB 예외·시간 초과는 이 하나로 정규화한다."""
    return AppError(
        ErrorCode.FORMULA_RUNTIME_ERROR,
        "수식을 계산할 수 없습니다. 시간이 너무 오래 걸렸거나 계산이 불가능한 수식일 수 있습니다.",
        status_code=422,
    )


# 미리보기·오류 칸 조회가 바쁠 때 화면이 다시 시도할 때까지의 초(05 §3 `retry_after`).
PREVIEW_RETRY_AFTER_SECONDS = 2


def preview_busy() -> AppError:
    return AppError(
        ErrorCode.PREVIEW_BUSY,
        "지금 계산 요청이 많습니다. 잠시 후 다시 시도하세요.",
        status_code=429,
        details={"retry_after": PREVIEW_RETRY_AFTER_SECONDS},
        headers={"Retry-After": str(PREVIEW_RETRY_AFTER_SECONDS)},
    )


def superset_unavailable() -> AppError:
    """Superset 연결 불가·시간 초과·5xx(503). 내부 용어를 쓰지 않는다."""
    return AppError(
        ErrorCode.SUPERSET_UNAVAILABLE,
        "대시보드 서비스에 연결할 수 없습니다. 잠시 후 다시 시도하세요.",
        status_code=503,
    )


def superset_rejected() -> AppError:
    """Superset이 요청을 받아들이지 않았다(인증·검증 거부, 502)."""
    return AppError(
        ErrorCode.SUPERSET_REJECTED,
        "대시보드 서비스가 요청을 받아들이지 않았습니다. 관리자에게 문의하세요.",
        status_code=502,
    )


def guest_token_rate_limited(retry_after: int) -> AppError:
    """입장권 발급이 사용자별 한도를 넘었다(429, `Retry-After`)."""
    return AppError(
        ErrorCode.GUEST_TOKEN_RATE_LIMITED,
        "요청이 너무 많습니다. 잠시 후 다시 시도하세요.",
        status_code=429,
        details={"retry_after": retry_after},
        headers={"Retry-After": str(retry_after)},
    )


def last_admin() -> AppError:
    return AppError(
        ErrorCode.LAST_ADMIN,
        "마지막 활성 관리자는 관리자 권한을 해제하거나 비활성화할 수 없습니다.",
        status_code=409,
    )


# HTTP 상태 코드 -> (오류 코드, 한국어 문구). HTTPException의 detail은 영어이거나 내부 용어일 수
# 있어 응답에 쓰지 않고 이 표만 쓴다(05 §1, 03b 17-1 결정 1).
# - 표에 있는 상태는 상태를 그대로 두고 사전 코드로 바꾼다.
# - 표 밖의 4xx(깨진 요청 400, 418 등)는 422 `VALIDATION_ERROR`로 통일한다(400은 쓰지 않는다).
#   409·429는 상태만으로 구체 코드(`ALREADY_EXISTS`, `PREVIEW_BUSY` 등)를 고를 수 없으므로 업무
#   코드가 항상 `AppError`로 구체 코드를 던진다. HTTPException으로 올라온 409·429도 여기서는
#   422로 통일된다.
# - 5xx는 `INTERNAL_ERROR`다(상세는 로그에만).
_HTTP_STATUS_ERRORS: dict[int, tuple[str, str]] = {
    401: (ErrorCode.UNAUTHENTICATED, "로그인이 필요합니다."),
    403: (ErrorCode.FORBIDDEN, "이 작업을 할 권한이 없습니다."),
    404: (ErrorCode.NOT_FOUND, "요청한 대상을 찾을 수 없습니다."),
    405: (ErrorCode.METHOD_NOT_ALLOWED, "허용되지 않는 요청 방식입니다."),
    413: (ErrorCode.PAYLOAD_TOO_LARGE, "요청 크기가 너무 큽니다."),
}
_UNIFIED_4XX = (ErrorCode.VALIDATION_ERROR, "입력한 내용을 확인해 주세요.")
_INTERNAL_MESSAGE = "처리 중 오류가 발생했습니다. 잠시 후 다시 시도하세요."

_FIELD_MESSAGES = {
    FieldErrorCode.REQUIRED: "필수 항목입니다.",
    FieldErrorCode.TOO_LONG: "너무 깁니다.",
    FieldErrorCode.BAD_FORMAT: "형식이 올바르지 않습니다.",
    FieldErrorCode.RESERVED: "예약된 이름이라 쓸 수 없습니다.",
    FieldErrorCode.OUT_OF_RANGE: "허용 범위를 벗어났습니다.",
    FieldErrorCode.NOT_IN_OPTIONS: "선택 목록에 없는 값입니다.",
    FieldErrorCode.NOT_PERIOD_START: "기간의 첫날이 아닙니다.",
    FieldErrorCode.READ_ONLY: "바꿀 수 없는 항목입니다.",
}
# pydantic 오류 type -> 필드 코드. 목록 밖은 BAD_FORMAT이다. `reserved`는 우리 검증기가 올리는
# 사용자 정의 오류 type(`PydanticCustomError("reserved", …)`)이다.
_FIELD_CODE_BY_TYPE = {
    "missing": FieldErrorCode.REQUIRED,
    "string_too_long": FieldErrorCode.TOO_LONG,
    "too_long": FieldErrorCode.TOO_LONG,
    "reserved": FieldErrorCode.RESERVED,
    "out_of_range": FieldErrorCode.OUT_OF_RANGE,
}
_LOCATION_PREFIXES = {"body", "query", "path", "header", "cookie"}


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    request_id: str,
    details: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    response_headers = dict(headers) if headers else {}
    response_headers[REQUEST_ID_HEADER] = request_id
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": dict(details) if details else {},
                "request_id": request_id,
            }
        },
        headers=response_headers,
    )


def _field_name(location: tuple[Any, ...]) -> str:
    parts = list(location)
    if parts and parts[0] in _LOCATION_PREFIXES:
        parts = parts[1:]
    return ".".join(str(part) for part in parts)


def convert_validation_errors(errors: list[Any]) -> list[dict[str, str]]:
    """pydantic 오류 목록을 `details.fields`로 바꾼다. 입력 값(`input`, `ctx`)은 옮기지 않는다."""
    fields = []
    for error in errors:
        code = _FIELD_CODE_BY_TYPE.get(str(error.get("type")), FieldErrorCode.BAD_FORMAT)
        fields.append(
            {
                "field": _field_name(tuple(error.get("loc", ()))),
                "code": code,
                "message": _FIELD_MESSAGES[code],
            }
        )
    return fields


async def _handle_app_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AppError):
        raise exc
    return error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
        headers=exc.headers,
        request_id=get_request_id(request.scope),
    )


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    return error_response(
        status_code=422,
        code=ErrorCode.VALIDATION_ERROR,
        message="입력한 내용을 확인해 주세요.",
        details={"fields": convert_validation_errors(list(exc.errors()))},
        request_id=get_request_id(request.scope),
    )


async def _handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):
        raise exc
    request_id = get_request_id(request.scope)
    if exc.status_code >= 500:
        logger.error("HTTP %s 예외 (request_id=%s)", exc.status_code, request_id)
        return error_response(
            status_code=exc.status_code,
            code=ErrorCode.INTERNAL_ERROR,
            message=_INTERNAL_MESSAGE,
            headers=exc.headers,
            request_id=request_id,
        )
    known = _HTTP_STATUS_ERRORS.get(exc.status_code)
    if known is not None:
        code, message = known
        return error_response(
            status_code=exc.status_code,
            code=code,
            message=message,
            headers=exc.headers,
            request_id=request_id,
        )
    # 표 밖 4xx는 422 VALIDATION_ERROR로 통일한다(필드 정보가 없어 `fields`는 빈 목록).
    return error_response(
        status_code=422,
        code=_UNIFIED_4XX[0],
        message=_UNIFIED_4XX[1],
        details={"fields": []},
        headers=exc.headers,
        request_id=request_id,
    )


async def _handle_db_unavailable(request: Request, exc: Exception) -> JSONResponse:
    """요청 처리 중 DB 연결 실패 등은 503 `SERVICE_UNAVAILABLE`이다(05 §1, 03b 17-1 결정 2)."""
    request_id = get_request_id(request.scope)
    if not is_db_unavailable(exc):
        # 잠금 충돌 등은 업무 코드가 먼저 처리해야 한다. 여기까지 왔으면 예상 밖의 오류다.
        return await _handle_unexpected(request, exc)
    # 메시지·SQL에 파라미터가 섞일 수 있어 클래스 이름과 request_id만 남긴다.
    logger.error("DB 장애로 503 응답: %s (request_id=%s)", type(exc).__name__, request_id)
    error = service_unavailable()
    return error_response(
        status_code=error.status_code,
        code=error.code,
        message=error.message,
        request_id=request_id,
    )


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    request_id = get_request_id(request.scope)
    # 상세(트레이스백)는 로그에만 남긴다. 응답에는 쓰지 않는다.
    logger.error(
        "처리되지 않은 예외 (request_id=%s, %s %s)",
        request_id,
        request.method,
        request.url.path,
        exc_info=exc,
    )
    return error_response(
        status_code=500,
        code=ErrorCode.INTERNAL_ERROR,
        message=_INTERNAL_MESSAGE,
        request_id=request_id,
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(SQLAlchemyError, _handle_db_unavailable)
    for network_error in DB_NETWORK_ERRORS:  # 감싸지 않은 소켓 시간 초과·연결 끊김도 503
        app.add_exception_handler(network_error, _handle_db_unavailable)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(Exception, _handle_unexpected)
