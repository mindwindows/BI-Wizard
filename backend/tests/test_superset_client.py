"""Superset 클라이언트 시험(08 §2-2, 프로브 문서의 응답 모양을 따르는 가짜 서버)."""

import logging

import httpx
import pytest

from app.superset.client import DatasetApi, rison_string
from app.superset.constants import LOGIN_RETRY_BACKOFF_SECONDS
from app.superset.errors import SupersetRejected, SupersetUnavailable
from tests.fake_superset import new_fake
from tests.superset_helpers import ISSUER, SERVICE, Clock, make_api, make_session

DATASET_PATH = "/api/v1/dataset/related/database"


def test_login_once_and_token_is_reused():
    fake = new_fake()
    session = make_session(fake)
    for _ in range(5):
        session.request("GET", DATASET_PATH)
    assert fake.logins == 1
    assert fake.count("POST", "/api/v1/security/login") == 1


def test_expired_token_is_refreshed_only_on_401_and_request_is_retried():
    fake = new_fake()
    session = make_session(fake)
    session.request("GET", DATASET_PATH)
    fake.expire_all_access_tokens()
    response = session.request("GET", DATASET_PATH)
    assert response.status_code == 200
    assert fake.refreshes == 1
    assert fake.logins == 1  # 갱신 토큰으로 갱신했다(재로그인 아님)
    # 갱신 뒤에는 다시 401이 없으므로 더 부르지 않는다.
    session.request("GET", DATASET_PATH)
    assert fake.refreshes == 1


def test_refresh_failure_falls_back_to_login():
    fake = new_fake()
    session = make_session(fake)
    session.request("GET", DATASET_PATH)
    fake.expire_all_access_tokens()
    fake._refresh.clear()  # 갱신 토큰이 무효가 된 상황
    assert session.request("GET", DATASET_PATH).status_code == 200
    assert fake.logins == 2


def test_wrong_password_is_auth_failed_without_secret_in_error():
    fake = new_fake()
    session = make_session(fake, ("bi_service", "wrong-password-XYZ"))
    with pytest.raises(SupersetRejected) as error:
        session.request("GET", DATASET_PATH)
    assert error.value.code == "AUTH_FAILED"
    assert "wrong-password-XYZ" not in repr(error.value) + str(error.value)


def test_malformed_token_422_is_not_a_login_loop():
    fake = new_fake()
    session = make_session(fake)
    session.request("GET", DATASET_PATH)
    session._access = "garbage"  # 깨진 토큰: Superset은 401이 아니라 422
    with pytest.raises(SupersetRejected) as error:
        session.request("GET", DATASET_PATH)
    assert error.value.code == "REJECTED_422"
    assert fake.logins == 1


def test_post_fetches_csrf_once_and_sends_cookie_and_header():
    fake = new_fake()
    api = make_api(fake)
    api.create(database_id=1, schema="bi_data", name="[A] x", sql="SELECT * FROM bi_data.dv_1")
    api.create(database_id=1, schema="bi_data", name="[A] y", sql="SELECT * FROM bi_data.dv_2")
    assert fake.count("GET", "/api/v1/security/csrf_token/") == 1
    assert len(fake.datasets) == 2


def test_csrf_error_400_refetches_token_and_retries_once():
    fake = new_fake()
    api = make_api(fake)
    api.create(database_id=1, schema="bi_data", name="[A] x", sql="SELECT * FROM bi_data.dv_1")
    # 세션이 바뀌어 CSRF가 무효가 된 상황: 서버가 모두 잊는다.
    fake._csrf.clear()
    new_id = api.create(
        database_id=1, schema="bi_data", name="[A] y", sql="SELECT * FROM bi_data.dv_2"
    )
    assert new_id == 2
    assert fake.count("GET", "/api/v1/security/csrf_token/") == 2


def test_400_without_csrf_text_is_not_retried():
    """훅 거부 400은 CSRF 400과 같은 상태 코드다. 본문에 CSRF가 있을 때만 다시 시도한다."""
    fake = new_fake()
    fake.embedded_uuids.add("11111111-2222-3333-4444-555555555555")
    session = make_session(fake, ISSUER)
    body = {"user": {"username": "1"}, "resources": [{"type": "dashboard", "id": "x"}], "rls": []}
    with pytest.raises(SupersetRejected) as error:
        session.request("POST", "/api/v1/security/guest_token/", json=body, csrf=True)
    assert error.value.code == "REJECTED_400"
    assert fake.count("POST", "/api/v1/security/guest_token/") == 1
    assert fake.count("GET", "/api/v1/security/csrf_token/") == 1


@pytest.mark.parametrize(
    ("setup", "code"),
    [
        (lambda f: setattr(f, "up", False), "UNAVAILABLE_CONNECT"),
        (lambda f: setattr(f, "slow", True), "UNAVAILABLE_TIMEOUT"),
    ],
)
def test_transport_errors_become_unavailable_codes(setup, code):
    fake = new_fake()
    setup(fake)
    session = make_session(fake)
    with pytest.raises(SupersetUnavailable) as error:
        session.request("GET", DATASET_PATH)
    assert error.value.code == code
    assert "superset" not in str(error.value) and "http" not in str(error.value)
    assert error.value.__cause__ is None  # 원인 예외(URL이 든 메시지)를 붙이지 않는다


def test_5xx_is_unavailable_and_other_4xx_is_rejected_with_status():
    fake = new_fake()
    session = make_session(fake)
    session.request("GET", DATASET_PATH)
    fake.respond_once(lambda c: c.path == DATASET_PATH, lambda c: httpx.Response(502, text="bad"))
    with pytest.raises(SupersetUnavailable) as error:
        session.request("GET", DATASET_PATH)
    assert error.value.code == "UNAVAILABLE_5XX"
    fake.respond_once(lambda c: c.path == DATASET_PATH, lambda c: httpx.Response(418, text="tea"))
    with pytest.raises(SupersetRejected) as error:
        session.request("GET", DATASET_PATH)
    assert error.value.code == "REJECTED_418"


def test_login_server_error_is_unavailable():
    fake = new_fake()
    fake.respond_once(
        lambda c: c.path == "/api/v1/security/login", lambda c: httpx.Response(503, text="x")
    )
    with pytest.raises(SupersetUnavailable) as error:
        make_session(fake).request("GET", DATASET_PATH)
    assert error.value.code == "UNAVAILABLE_5XX"


def test_get_retries_once_on_dropped_connection_but_post_does_not():
    fake = new_fake()
    session = make_session(fake)
    session.request("GET", DATASET_PATH)

    def drop(call):
        raise httpx.RemoteProtocolError("server disconnected")

    fake.respond_once(lambda c: c.path == DATASET_PATH, drop)
    assert session.request("GET", DATASET_PATH).status_code == 200
    # POST는 중복 위험이 있어 다시 보내지 않는다.
    api = DatasetApi(session)
    fake.respond_once(lambda c: c.method == "POST" and c.path == "/api/v1/dataset/", drop)
    with pytest.raises(SupersetUnavailable):
        api.create(database_id=1, schema="bi_data", name="[A] x", sql="SELECT * FROM bi_data.dv_1")
    assert fake.datasets == {}


def test_no_secret_token_or_url_in_logs(caplog):
    caplog.set_level(logging.DEBUG)
    fake = new_fake()
    session = make_session(fake)
    session.request("GET", DATASET_PATH)
    fake.expire_all_access_tokens()
    session.request("GET", DATASET_PATH)
    fake.up = False
    with pytest.raises(SupersetUnavailable):
        session.request("GET", DATASET_PATH)
    wrong = make_session(new_fake(), ("bi_service", "wrong-password-XYZ"))
    with pytest.raises(SupersetRejected):
        wrong.request("GET", DATASET_PATH)
    text = "\n".join(r.getMessage() for r in caplog.records)
    for secret in (SERVICE[1], ISSUER[1], "wrong-password-XYZ", "AT-", "RT-", "superset:8088"):
        assert secret not in text
    assert "HTTP Request" not in text  # httpx 요청 로그(URL 포함)는 WARNING 위로 고정돼 있다


def test_httpx_loggers_are_pinned_to_warning():
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING


def test_client_ignores_proxy_environment(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:3128")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:3128")
    session = make_session(new_fake())
    assert session._client._trust_env is False
    assert session._client.follow_redirects is False


def test_rison_string_escapes_bang_and_quote():
    assert rison_string("a b") == "'a b'"
    assert rison_string("it's!ok") == "'it!'s!!ok'"


def test_database_id_is_looked_up_by_name_and_cached():
    fake = new_fake()
    fake.database_id = 7
    api = make_api(fake)
    assert api.database_id() == 7
    assert api.database_id() == 7
    assert fake.count("GET", "/api/v1/dataset/related/database") == 1


def test_database_not_found_is_a_reason_code():
    fake = new_fake()
    fake.database_name = "다른 연결"
    with pytest.raises(SupersetRejected) as error:
        make_api(fake).database_id()
    assert error.value.code == "DB_NOT_FOUND"


def test_find_by_sql_and_name_with_special_characters():
    fake = new_fake()
    api = make_api(fake)
    name = "[A팀] it's!ok"
    new_id = api.create(
        database_id=1, schema="bi_data", name=name, sql="SELECT * FROM bi_data.dv_1"
    )
    assert [h["id"] for h in api.find_by_sql("SELECT * FROM bi_data.dv_1", "bi_data")] == [new_id]
    assert [h["id"] for h in api.find_by_name(name, "bi_data")] == [new_id]
    assert api.find_by_sql("SELECT * FROM bi_data.dv_2", "bi_data") == []


def test_duplicate_name_422_returns_none_without_leaking_the_message():
    fake = new_fake()
    api = make_api(fake)
    api.create(database_id=1, schema="bi_data", name="[A] x", sql="SELECT * FROM bi_data.dv_1")
    assert (
        api.create(database_id=1, schema="bi_data", name="[A] x", sql="SELECT * FROM bi_data.dv_2")
        is None
    )


def test_health_ok_and_down():
    fake = new_fake()
    session = make_session(fake)
    assert session.health() is True
    fake.health_ok = False
    assert session.health() is False
    fake.up = False
    assert session.health() is False
    assert fake.logins == 0  # 건강 확인은 로그인하지 않는다


def test_put_names_never_sends_a_partial_column_list():
    fake = new_fake()
    fake.views[1] = ["team", "row_id", "c_1", "c_2"]
    api = make_api(fake)
    new_id = api.create(
        database_id=1, schema="bi_data", name="[A] x", sql="SELECT * FROM bi_data.dv_1"
    )
    current = api.get(new_id)
    assert current is not None and len(current["columns"]) == 4
    assert api.put_names(
        new_id, table_name="[A] x", columns=current["columns"], labels={"c_1": "매출"}
    )
    body = [c for c in fake.calls if c.method == "PUT"][-1].body
    assert set(body) == {"table_name", "columns"}
    assert [c["id"] for c in body["columns"]] == [c["id"] for c in current["columns"]]
    assert all(set(c) == {"id", "column_name", "verbose_name"} for c in body["columns"])
    after = api.get(new_id)
    assert after is not None
    assert [c["id"] for c in after["columns"]] == [c["id"] for c in current["columns"]]
    assert {c["column_name"]: c["verbose_name"] for c in after["columns"]}["c_1"] == "매출"
    with pytest.raises(SupersetRejected):
        api.put_names(new_id, table_name="[A] x", columns=[], labels={})


def test_get_dataset_404_is_none_and_foreign_dataset_put_is_not_owner():
    fake = new_fake()
    api = make_api(fake)
    assert api.get(99) is None
    new_id = api.create(
        database_id=1, schema="bi_data", name="[A] x", sql="SELECT * FROM bi_data.dv_1"
    )
    fake.foreign_datasets.add(new_id)
    current = api.get(new_id)
    assert current is not None
    with pytest.raises(SupersetRejected) as error:
        api.put_names(new_id, table_name="[A] x", columns=current["columns"], labels={})
    assert error.value.code == "NOT_OWNER"


def test_first_write_after_the_token_expired_refreshes_before_fetching_csrf():
    """읽기만 하다 15분이 지나 접근 토큰이 만료된 뒤 첫 호출이 쓰기여도(CSRF 캐시 없음) 막히지
    않는다."""
    fake = new_fake()
    api = make_api(fake)
    api.database_id()  # 읽기로 로그인만 해 둔다(CSRF 토큰은 아직 없다)
    fake.expire_all_access_tokens()
    new_id = api.create(
        database_id=1, schema="bi_data", name="[A] x", sql="SELECT * FROM bi_data.dv_1"
    )
    assert new_id == 1
    assert fake.refreshes == 1 and fake.logins == 1


# --- 로그인 거부 뒤 재시도 백오프 ----


def test_login_rejection_backs_off_then_retries_once_after_the_window():
    fake = new_fake()
    clock = Clock()
    session = make_session(fake, ("bi_service", "wrong-password-XYZ"), clock=clock)
    for _ in range(12):  # 사용자 요청이 몰려도 로그인 시도는 한 번뿐이다
        with pytest.raises(SupersetRejected) as error:
            session.request("GET", DATASET_PATH)
        assert error.value.code == "AUTH_FAILED"
    assert fake.count("POST", "/api/v1/security/login") == 1
    clock.advance(LOGIN_RETRY_BACKOFF_SECONDS - 1)
    with pytest.raises(SupersetRejected):
        session.request("GET", DATASET_PATH)
    assert fake.count("POST", "/api/v1/security/login") == 1
    clock.advance(1)  # 창이 끝났다: 한 번 더 시도하고 다시 막는다
    with pytest.raises(SupersetRejected):
        session.request("GET", DATASET_PATH)
    with pytest.raises(SupersetRejected):
        session.request("GET", DATASET_PATH)
    assert fake.count("POST", "/api/v1/security/login") == 2


def test_login_succeeds_after_the_account_is_fixed_and_the_window_passes():
    fake = new_fake()
    clock = Clock()
    session = make_session(fake, ("bi_service", "new-password-1"), clock=clock)
    with pytest.raises(SupersetRejected):
        session.request("GET", DATASET_PATH)
    fake.add_account("bi_service", "new-password-1", "service")  # 관리자가 계정을 고쳤다
    with pytest.raises(SupersetRejected):  # 창 안에서는 아직 막혀 있다
        session.request("GET", DATASET_PATH)
    clock.advance(LOGIN_RETRY_BACKOFF_SECONDS)
    assert session.request("GET", DATASET_PATH).status_code == 200
    session.request("GET", DATASET_PATH)
    assert fake.count("POST", "/api/v1/security/login") == 2  # 실패 1 + 성공 1, 이후 재사용


def test_connection_failures_do_not_start_the_login_backoff():
    fake = new_fake()
    clock = Clock()
    session = make_session(fake, clock=clock)
    fake.up = False
    for _ in range(3):
        with pytest.raises(SupersetUnavailable):
            session.request("GET", DATASET_PATH)
    fake.up = True
    assert session.request("GET", DATASET_PATH).status_code == 200  # 기다릴 필요가 없다


# --- httpx.HTTPError가 아닌 예외도 클래스 이름만 남기고 사유 코드로 바뀐다 ----

SECRET_DETAIL = "secret-detail http://superset:8088/bi-wizard/superset/api/v1/x?token=abc"


def _raise(error: BaseException):
    def respond(call):
        raise error

    return respond


@pytest.mark.parametrize(
    "error",
    [
        httpx.InvalidURL(SECRET_DETAIL),
        httpx.CookieConflict(SECRET_DETAIL),
        httpx.StreamClosed(),
        RuntimeError(SECRET_DETAIL),
    ],
    ids=lambda e: type(e).__name__,
)
@pytest.mark.parametrize(
    "path",
    ["/api/v1/security/login", "/api/v1/security/csrf_token/", DATASET_PATH],
    ids=["login", "csrf", "request"],
)
def test_non_http_exceptions_become_a_reason_code_without_url_message_or_traceback(
    path, error, caplog
):
    caplog.set_level(logging.DEBUG)
    fake = new_fake()
    session = make_session(fake)
    if path != "/api/v1/security/login":
        session.request("GET", DATASET_PATH)  # 로그인은 미리 해 둔다
    fake.respond_once(lambda c: c.path == path, _raise(error))
    with pytest.raises(SupersetRejected) as raised:
        if path == "/api/v1/security/csrf_token/":
            session.request("POST", "/api/v1/dataset/", json={}, csrf=True)
        else:
            session.request("GET", DATASET_PATH)
    assert raised.value.code == "INTERNAL"
    assert raised.value.__cause__ is None and raised.value.__suppress_context__ is True
    text = "\n".join(f"{r.getMessage()} {r.exc_text or ''}" for r in caplog.records)
    assert type(error).__name__ in text  # 클래스 이름만 남는다
    for leaked in ("secret-detail", "superset:8088", "token=abc", "http"):
        assert leaked not in text
    assert all(r.exc_info is None for r in caplog.records)  # 트레이스백 없음


def test_non_http_exception_in_health_is_just_not_ready(caplog):
    caplog.set_level(logging.DEBUG)
    fake = new_fake()
    session = make_session(fake)
    fake.respond_once(lambda c: c.path == "/health", _raise(httpx.InvalidURL(SECRET_DETAIL)))
    assert session.health() is False
    text = "\n".join(f"{r.getMessage()} {r.exc_text or ''}" for r in caplog.records)
    assert "InvalidURL" in text and "secret-detail" not in text
    assert all(r.exc_info is None for r in caplog.records)
    assert session.health() is True


def test_fake_superset_accepts_uppercase_embedded_uuid_like_the_real_hook():
    """프로브 P-3: 실제 6.1.0은 대문자 uuid를 통과시키고 토큰에는 보낸 글자가 그대로 들어간다."""
    fake = new_fake()
    value = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    fake.embedded_uuids.add(value)
    session = make_session(fake, ISSUER)
    for sent, status in (
        (value, 200),
        (value.upper(), 200),  # 대문자도 200
        (value.replace("-", ""), 400),  # 하이픈 없는 형태는 훅이 거부
        ("{" + value + "}", 400),
        ("bbbbbbbb-bbbb-cccc-dddd-eeeeeeeeeeee", 400),  # 임베드되지 않은 uuid
    ):
        response = session.request(
            "POST",
            "/api/v1/security/guest_token/",
            json={"user": {"username": "1"}, "resources": [{"type": "dashboard", "id": sent}], "rls": []},
            csrf=True,
            accept=(400,),
        )
        assert response.status_code == status, sent
