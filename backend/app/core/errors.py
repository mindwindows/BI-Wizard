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
from starlette.exceptions import HTTPException as StarletteHTTPException

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
    # 05 §3 사전에 없는 코드(계약 추가 제안): 라우터가 만드는 405와 그 밖의 4xx용.
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    BAD_REQUEST = "BAD_REQUEST"


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


# HTTP 상태 코드 -> (오류 코드, 한국어 문구). HTTPException의 detail은 영어이거나
# 내부 용어일 수 있어 응답에 쓰지 않고 이 표만 쓴다.
_HTTP_STATUS_ERRORS: dict[int, tuple[str, str]] = {
    401: (ErrorCode.UNAUTHENTICATED, "로그인이 필요합니다."),
    403: (ErrorCode.FORBIDDEN, "이 작업을 할 권한이 없습니다."),
    404: (ErrorCode.NOT_FOUND, "요청한 대상을 찾을 수 없습니다."),
    405: (ErrorCode.METHOD_NOT_ALLOWED, "허용되지 않는 요청 방식입니다."),
    413: (ErrorCode.PAYLOAD_TOO_LARGE, "요청 크기가 너무 큽니다."),
}
_INTERNAL_MESSAGE = "처리 중 오류가 발생했습니다. 잠시 후 다시 시도하세요."

_FIELD_MESSAGES = {
    FieldErrorCode.REQUIRED: "필수 항목입니다.",
    FieldErrorCode.TOO_LONG: "너무 깁니다.",
    FieldErrorCode.BAD_FORMAT: "형식이 올바르지 않습니다.",
}
# pydantic 오류 type -> 필드 코드. 목록 밖은 BAD_FORMAT이다.
_FIELD_CODE_BY_TYPE = {
    "missing": FieldErrorCode.REQUIRED,
    "string_too_long": FieldErrorCode.TOO_LONG,
    "too_long": FieldErrorCode.TOO_LONG,
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
        code, message = ErrorCode.INTERNAL_ERROR, _INTERNAL_MESSAGE
    else:
        code, message = _HTTP_STATUS_ERRORS.get(
            exc.status_code, (ErrorCode.BAD_REQUEST, "요청을 처리할 수 없습니다.")
        )
    return error_response(
        status_code=exc.status_code,
        code=code,
        message=message,
        headers=exc.headers,
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
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(Exception, _handle_unexpected)
