"""Superset 클라이언트 시험(08 §2-2, 프로브 문서의 응답 모양을 따르는 가짜 서버)."""

import logging

import httpx
import pytest

from app.superset.client import DatasetApi, rison_string
from app.superset.errors import SupersetRejected, SupersetUnavailable
from tests.fake_superset import new_fake
from tests.superset_helpers import ISSUER, SERVICE, make_api, make_session

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
