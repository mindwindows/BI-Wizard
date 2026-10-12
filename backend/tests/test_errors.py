"""오류 형식(05 §1), 요청 id, 검증 오류 변환, 500 처리."""

import logging

import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.core.errors import AppError, ErrorCode
from app.main import create_app

SECRET = "super-secret-value-123"


class Body(BaseModel):
    name: str = Field(max_length=5)
    count: int


def _app(make_settings, sqlite_engine) -> FastAPI:
    app = create_app(make_settings(), engine=sqlite_engine)
    router = APIRouter()

    @router.post("/_t/validate")
    def validate(body: Body, q: int = 0) -> dict:
        return {"ok": True}

    @router.get("/_t/item/{item_id}")
    def item(item_id: int) -> dict:
        return {"item_id": item_id}

    @router.get("/_t/app-error")
    def app_error():
        raise AppError(
            ErrorCode.ALREADY_EXISTS, "이미 있습니다.", status_code=409, details={"field": "code"}
        )

    @router.get("/_t/http-error")
    def http_error():
        raise HTTPException(status_code=403, detail="English internal detail")

    @router.get("/_t/boom")
    def boom():
        raise RuntimeError(f"SELECT * FROM users WHERE pw='{SECRET}' failed")  # noqa: S608

    app.include_router(router, prefix="/api")
    return app


@pytest.fixture
def client(make_settings, sqlite_engine):
    with TestClient(_app(make_settings, sqlite_engine), raise_server_exceptions=False) as c:
        yield c


def _assert_error_shape(response, code: str, status: int):
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"error"}
    error = body["error"]
    assert set(error) == {"code", "message", "details", "request_id"}
    assert error["code"] == code
    assert isinstance(error["details"], dict)
    assert error["request_id"] == response.headers["X-Request-ID"]
    assert error["message"]
    return error


def test_request_id_header_on_success(client):
    response = client.get("/api/health")
    assert len(response.headers["X-Request-ID"]) >= 16


def test_request_id_differs_between_requests(client):
    ids = {client.get("/api/health").headers["X-Request-ID"] for _ in range(3)}
    assert len(ids) == 3


def test_safe_incoming_request_id_is_kept(client):
    response = client.get("/api/health", headers={"X-Request-ID": "abc-123_X.y"})
    assert response.headers["X-Request-ID"] == "abc-123_X.y"


@pytest.mark.parametrize("bad", ["a b", "x" * 65, "a;b"])
def test_unsafe_incoming_request_id_is_replaced(client, bad):
    response = client.get("/api/health", headers={"X-Request-ID": bad})
    assert response.headers["X-Request-ID"] != bad


def test_request_id_length_boundary(client):
    ok = "x" * 64
    assert client.get("/api/health", headers={"X-Request-ID": ok}).headers["X-Request-ID"] == ok
    too_long = "x" * 65
    replaced = client.get("/api/health", headers={"X-Request-ID": too_long})
    assert replaced.headers["X-Request-ID"] != too_long


def test_non_ascii_request_id_is_replaced(client):
    """한글 헤더는 latin-1로 보낼 수 없으므로 원시 바이트(UTF-8)로 직접 보낸다."""
    response = client.get(
        "/api/health",
        headers=[(b"x-request-id", "한글".encode())],  # type: ignore[arg-type]
    )
    assert response.status_code == 200
    assert response.headers["X-Request-ID"].isascii()
    assert "한글" not in response.headers["X-Request-ID"]
    assert len(response.headers["X-Request-ID"]) >= 16


def test_app_error_format(client):
    error = _assert_error_shape(client.get("/api/_t/app-error"), "ALREADY_EXISTS", 409)
    assert error["details"] == {"field": "code"}


def test_not_found_route_uses_error_format(client):
    error = _assert_error_shape(client.get("/api/nope"), "NOT_FOUND", 404)
    assert "Not Found" not in error["message"]


def test_method_not_allowed_uses_error_format(client):
    _assert_error_shape(client.post("/api/health"), "METHOD_NOT_ALLOWED", 405)


def test_http_exception_uses_error_format_without_detail(client):
    error = _assert_error_shape(client.get("/api/_t/http-error"), "FORBIDDEN", 403)
    assert "English" not in error["message"]


# HTTPException 상태 -> (응답 상태, 오류 코드). 05 §1·§3, 03b 17-1 결정 1:
# 401·403·404·405·413은 상태 그대로 사전 코드, 그 밖의 4xx(400·409·418·422·429 등)는 422
# VALIDATION_ERROR로 통일, 5xx는 INTERNAL_ERROR. `BAD_REQUEST` 코드는 없다.
HTTP_STATUS_TABLE = [
    (400, 422, "VALIDATION_ERROR"),
    (401, 401, "UNAUTHENTICATED"),
    (403, 403, "FORBIDDEN"),
    (404, 404, "NOT_FOUND"),
    (405, 405, "METHOD_NOT_ALLOWED"),
    (409, 422, "VALIDATION_ERROR"),
    (413, 413, "PAYLOAD_TOO_LARGE"),
    (418, 422, "VALIDATION_ERROR"),
    (422, 422, "VALIDATION_ERROR"),
    (429, 422, "VALIDATION_ERROR"),
    (500, 500, "INTERNAL_ERROR"),
    (502, 502, "INTERNAL_ERROR"),
    (503, 503, "INTERNAL_ERROR"),
]


def test_bad_request_code_does_not_exist():
    assert not hasattr(ErrorCode, "BAD_REQUEST")
    assert ErrorCode.METHOD_NOT_ALLOWED == "METHOD_NOT_ALLOWED"
    assert ErrorCode.SERVICE_UNAVAILABLE == "SERVICE_UNAVAILABLE"
    assert ErrorCode.TARGET_INACTIVE == "TARGET_INACTIVE"


@pytest.mark.parametrize(("raised", "status", "code"), HTTP_STATUS_TABLE)
def test_http_exception_status_table(make_settings, sqlite_engine, raised, status, code):
    app = create_app(make_settings(), engine=sqlite_engine)
    router = APIRouter()

    @router.get("/_t/raise")
    def raise_it():
        raise HTTPException(status_code=raised, detail="English internal detail SELECT")

    app.include_router(router, prefix="/api")
    with TestClient(app, raise_server_exceptions=False) as c:
        response = c.get("/api/_t/raise")
    error = _assert_error_shape(response, code, status)
    assert "English" not in response.text and "SELECT" not in response.text
    # 422 통일 응답은 필드 정보가 없어 빈 fields를 담고, 나머지는 details가 비어 있다.
    assert error["details"] == ({"fields": []} if code == "VALIDATION_ERROR" else {})


def test_validation_error_is_converted(client):
    response = client.post("/api/_t/validate?q=abc", json={"name": "toolongname", "secretish": 1})
    error = _assert_error_shape(response, "VALIDATION_ERROR", 422)
    fields = {f["field"]: f for f in error["details"]["fields"]}
    assert fields["name"]["code"] == "TOO_LONG"
    assert fields["count"]["code"] == "REQUIRED"
    assert fields["q"]["code"] == "BAD_FORMAT"
    for f in fields.values():
        assert set(f) == {"field", "code", "message"}
    # 입력 값은 응답에 되돌려 주지 않는다.
    # request_id는 무작위 16진수라 "abc"가 우연히 들어갈 수 있으므로 뺀 본문으로 비교한다.
    text = response.text.replace(error["request_id"], "")
    assert "toolongname" not in text
    assert "abc" not in text


def test_wrong_method_is_405_and_malformed_path_is_422(client):
    """허용 안 되는 메서드는 405, 정수 자리의 글자 같은 경로 형식 오류는 422로 통일한다."""
    wrong_method = client.get("/api/_t/validate")
    _assert_error_shape(wrong_method, "METHOD_NOT_ALLOWED", 405)
    malformed = client.get("/api/_t/item/abc")
    error = _assert_error_shape(malformed, "VALIDATION_ERROR", 422)
    assert error["details"]["fields"][0]["field"] == "item_id"


def test_raw_409_and_429_http_exceptions_are_not_given_business_codes(make_settings, sqlite_engine):
    """업무 409·429는 AppError로 구체 코드를 던진다. HTTPException은 구체 코드를 못 얻는다."""
    app = create_app(make_settings(), engine=sqlite_engine)
    router = APIRouter()

    @router.get("/_t/rate")
    def rate():
        raise HTTPException(status_code=429, detail="x", headers={"Retry-After": "3"})

    @router.get("/_t/business")
    def business():
        raise AppError(
            ErrorCode.PREVIEW_BUSY,
            "잠시 후 다시 시도하세요.",
            status_code=429,
            details={"retry_after": 3},
            headers={"Retry-After": "3"},
        )

    app.include_router(router, prefix="/api")
    with TestClient(app, raise_server_exceptions=False) as c:
        raw = c.get("/api/_t/rate")
        concrete = c.get("/api/_t/business")
    assert raw.status_code == 422 and raw.json()["error"]["code"] == "VALIDATION_ERROR"
    assert raw.headers["Retry-After"] == "3"
    assert concrete.status_code == 429 and concrete.json()["error"]["code"] == "PREVIEW_BUSY"
    assert concrete.headers["Retry-After"] == "3"


def test_unhandled_db_connection_error_is_503_without_leaks(make_settings, sqlite_engine, caplog):
    """핸들러에서 DB 연결 오류가 새면 503 SERVICE_UNAVAILABLE(로그에는 클래스 이름만)."""
    from sqlalchemy.exc import OperationalError

    app = create_app(make_settings(), engine=sqlite_engine)
    router = APIRouter()

    @router.get("/_t/dbdown")
    def dbdown():
        raise OperationalError("SELECT secret FROM users WHERE id = %s", {"id": 7}, Exception("x"))

    app.include_router(router, prefix="/api")
    with TestClient(app, raise_server_exceptions=False) as c, caplog.at_level(logging.ERROR):
        response = c.get("/api/_t/dbdown")
    error = _assert_error_shape(response, "SERVICE_UNAVAILABLE", 503)
    assert error["details"] == {}
    for leaked in ("SELECT", "secret", "users", "Traceback"):
        assert leaked not in response.text
        assert leaked not in caplog.text
    assert "OperationalError" in caplog.text and error["request_id"] in caplog.text


def test_validation_error_for_broken_json(client):
    response = client.post(
        "/api/_t/validate", content=b'{"name": ', headers={"Content-Type": "application/json"}
    )
    _assert_error_shape(response, "VALIDATION_ERROR", 422)


def test_unexpected_exception_is_500_without_leaks(client, caplog):
    with caplog.at_level(logging.ERROR):
        response = client.get("/api/_t/boom")
    error = _assert_error_shape(response, "INTERNAL_ERROR", 500)
    assert error["details"] == {}
    for leaked in (SECRET, "SELECT", "RuntimeError", "Traceback", "boom"):
        assert leaked not in response.text
    # 상세는 로그에만 남고 요청 id로 찾을 수 있다.
    assert error["request_id"] in caplog.text
    assert "RuntimeError" in caplog.text


def test_unexpected_exception_still_has_request_id_header(client):
    assert client.get("/api/_t/boom").headers["X-Request-ID"]


def test_get_session_gives_session_bound_to_app_engine(make_settings, sqlite_engine):
    from fastapi import Depends
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.core.deps import get_session

    app = create_app(make_settings(), engine=sqlite_engine)
    router = APIRouter()

    @router.get("/_t/session")
    def session_route(session: Session = Depends(get_session)) -> dict:  # noqa: B008
        return {"one": session.execute(select(1)).scalar_one()}

    app.include_router(router, prefix="/api")
    with TestClient(app) as client:
        assert client.get("/api/_t/session").json() == {"one": 1}
