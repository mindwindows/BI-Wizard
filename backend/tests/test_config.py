import pytest
from pydantic import ValidationError

from app.config import (
    AUTH_STUB_ALLOWED_ENVS,
    Settings,
    check_auth_stub_allowed,
    validate_base_path,
)
from app.db import APP_DB_USER, OWNER_DB_USER, build_database_url


def test_defaults_are_root_deploy_without_strip(make_settings):
    settings = make_settings()
    assert settings.app_base_path == ""
    assert settings.app_proxy_strip_prefix is False
    assert settings.received_api_prefix == "/api"


@pytest.mark.parametrize("value", ["", "/bi-wizard", "/a/b", "/bi-wizard/superset", "/a.b_c~d"])
def test_base_path_accepts_valid_values(value):
    assert validate_base_path(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "/",
        "bi-wizard",
        "/bi-wizard/",
        "//a",
        "/a//b",
        "/a b",
        "/a?b",
        "/a\n/b",
        "/a\n",
        "\n/a",
        "/..",
        "/a/..",
        "/a/../b",
        "/.",
        "/a/./b",
        "/../a",
    ],
)
def test_base_path_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        validate_base_path(value)


def test_invalid_base_path_fails_settings(make_settings):
    with pytest.raises(ValidationError):
        make_settings(APP_BASE_PATH="bi-wizard/")


@pytest.mark.parametrize(
    ("strip", "expected"),
    [("false", "/bi-wizard/api"), ("true", "/api")],
)
def test_received_api_prefix_follows_strip_setting(make_settings, strip, expected):
    settings = make_settings(APP_BASE_PATH="/bi-wizard", APP_PROXY_STRIP_PREFIX=strip)
    assert settings.received_api_prefix == expected


def test_bool_and_int_parsing(make_settings):
    settings = make_settings(APP_DEBUG="true", BACKEND_PORT="9000", LOG_LEVEL="debug")
    assert settings.app_debug is True
    assert settings.backend_port == 9000
    assert settings.log_level == "DEBUG"


def test_invalid_log_level_fails(make_settings):
    with pytest.raises(ValidationError):
        make_settings(LOG_LEVEL="LOUD")


def test_required_postgres_db_fails_closed(monkeypatch):
    monkeypatch.setenv("POSTGRES_DB", "")
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_database_url_uses_pg8000_and_escapes_password(make_settings):
    settings = make_settings(POSTGRES_APP_PASSWORD="p@ss:w/rd%2f?#")
    url = build_database_url(settings, "app")
    assert url.drivername == "postgresql+pg8000"
    assert url.password == "p@ss:w/rd%2f?#"
    assert url.host == "db.test"
    assert url.database == "testdb"
    # 로그나 repr에 비밀번호가 나오지 않는다.
    assert "p@ss" not in repr(url)
    assert "p@ss" not in repr(settings)
    assert "p@ss" not in url.render_as_string(hide_password=True)
    # 다시 파싱해도 같은 비밀번호가 된다(특수문자가 URL 인코딩된다).
    from sqlalchemy.engine import make_url

    assert make_url(url.render_as_string(hide_password=False)).password == "p@ss:w/rd%2f?#"


def test_db_user_names_are_code_constants_and_ignore_superuser_variables(make_settings):
    """슈퍼유저 변수(POSTGRES_USER/PASSWORD)가 있어도 접속 계정은 bi_app/bi_owner 상수다."""
    settings = make_settings(
        POSTGRES_USER="super",
        POSTGRES_PASSWORD="super-secret",
        POSTGRES_APP_PASSWORD="app-pw",
        POSTGRES_OWNER_PASSWORD="owner-pw",
    )
    assert not hasattr(settings, "postgres_user")
    assert not hasattr(settings, "postgres_password")
    app_url = build_database_url(settings, "app")
    owner_url = build_database_url(settings, "owner")
    assert (APP_DB_USER, OWNER_DB_USER) == ("bi_app", "bi_owner")
    assert (app_url.username, app_url.password) == ("bi_app", "app-pw")
    assert (owner_url.username, owner_url.password) == ("bi_owner", "owner-pw")
    for url in (app_url, owner_url):
        assert "super" not in url.render_as_string(hide_password=False)


@pytest.mark.parametrize(
    ("role", "variable"),
    [("app", "POSTGRES_APP_PASSWORD"), ("owner", "POSTGRES_OWNER_PASSWORD")],
)
def test_database_url_fails_closed_without_password(make_settings, role, variable):
    # 다른 역할의 비밀번호만 있어도 이 역할의 접속은 만들 수 없다(컨테이너마다 필요한 것만 받는다).
    other = "POSTGRES_OWNER_PASSWORD" if role == "app" else "POSTGRES_APP_PASSWORD"
    with pytest.raises(ValueError, match=variable):
        build_database_url(make_settings(**{other: "other-pw"}), role)
    with pytest.raises(ValueError, match=variable):
        build_database_url(make_settings(**{variable: ""}), role)


def test_unknown_db_role_is_rejected(make_settings):
    with pytest.raises(ValueError):
        build_database_url(make_settings(), "postgres")  # type: ignore[arg-type]


# --- 인증 스텁 스위치(AP-13, bi-review 7-5) ---


def test_auth_stub_default_is_off_regardless_of_app_env(make_settings):
    assert make_settings().auth_stub_enabled is False
    # 꺼져 있으면 APP_ENV가 무엇이든 시작한다(운영 값 포함).
    assert make_settings(APP_ENV="production").auth_stub_enabled is False
    assert make_settings(AUTH_STUB_ENABLED="false", APP_ENV="staging").auth_stub_enabled is False


@pytest.mark.parametrize("app_env", ["local", "test"])
def test_auth_stub_on_allowed_in_explicit_local_and_test(make_settings, app_env):
    settings = make_settings(AUTH_STUB_ENABLED="true", APP_ENV=app_env)
    assert settings.auth_stub_enabled is True
    assert settings.app_env == app_env


def test_auth_stub_on_without_app_env_is_refused(make_settings):
    """코드 기본값 local이 채운 APP_ENV는 명시 설정으로 보지 않는다."""
    with pytest.raises(ValidationError, match="APP_ENV"):
        make_settings(AUTH_STUB_ENABLED="true")


@pytest.mark.parametrize(
    "app_env",
    [
        "",
        " ",
        "production",
        "prod",
        "staging",
        "stage",
        "development",
        "dev",
        "Local",
        "LOCAL",
        "test ",
        "local\n",
    ],
)
def test_auth_stub_on_refused_for_empty_or_non_allowed_app_env(make_settings, app_env):
    with pytest.raises(ValidationError, match="APP_ENV"):
        make_settings(AUTH_STUB_ENABLED="true", APP_ENV=app_env)


@pytest.mark.parametrize("value", ["maybe", "2", "enabled"])
def test_auth_stub_value_must_be_boolean(make_settings, value):
    with pytest.raises(ValidationError):
        make_settings(AUTH_STUB_ENABLED=value, APP_ENV="local")


def test_check_auth_stub_allowed_function_directly():
    assert AUTH_STUB_ALLOWED_ENVS == {"local", "test"}
    check_auth_stub_allowed(enabled=False, app_env="production", app_env_explicit=True)
    check_auth_stub_allowed(enabled=True, app_env="local", app_env_explicit=True)
    with pytest.raises(ValueError):
        check_auth_stub_allowed(enabled=True, app_env="local", app_env_explicit=False)
    with pytest.raises(ValueError):
        check_auth_stub_allowed(enabled=True, app_env="production", app_env_explicit=True)


def test_auth_stub_startup_refusal_exits_main(monkeypatch):
    """`python -m app`의 main()은 설정 오류 때 서버를 띄우기 전에 예외로 끝난다."""
    from app import __main__ as entry

    monkeypatch.setenv("AUTH_STUB_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("POSTGRES_APP_PASSWORD", "app-pw")
    called = []
    monkeypatch.setattr(entry.uvicorn, "run", lambda *a, **k: called.append(True))
    with pytest.raises(ValidationError):
        entry.main()
    assert called == []


def test_main_refuses_to_start_without_app_password(monkeypatch):
    from app import __main__ as entry

    called = []
    monkeypatch.setattr(entry.uvicorn, "run", lambda *a, **k: called.append(True))
    with pytest.raises(ValueError, match="POSTGRES_APP_PASSWORD"):
        entry.main()
    assert called == []


def test_validation_errors_do_not_echo_secret_values(make_settings):
    """시작 거부 오류(스텁 스위치 등)에 비밀번호 입력 값이 섞여 나오지 않는다."""
    with pytest.raises(ValidationError) as caught:
        make_settings(
            AUTH_STUB_ENABLED="true",
            APP_ENV="production",
            POSTGRES_APP_PASSWORD="SECRET-APP-PW-123",
            POSTGRES_OWNER_PASSWORD="SECRET-OWNER-PW-456",
        )
    text = str(caught.value)
    assert "SECRET-APP-PW-123" not in text
    assert "SECRET-OWNER-PW-456" not in text
    assert "APP_ENV" in text


# --- Superset 접속 설정(EW-3, AP-12). 사용(HTTP 호출)은 FU-1e ---

_SUPERSET_ENV = {
    "SUPERSET_APP_ROOT": "/bi-wizard/superset",
    "SUPERSET_SERVICE_USER": "bi_service",
    "SUPERSET_SERVICE_PASSWORD": "SECRET-SERVICE-PW-1",
    "SUPERSET_GUEST_ISSUER_USER": "bi_guest_issuer",
    "SUPERSET_GUEST_ISSUER_PASSWORD": "SECRET-ISSUER-PW-2",
}


def test_superset_settings_are_optional_so_backend_starts_without_them(make_settings):
    """Superset 불가가 포털을 멈추지 않는다: 값이 없어도 설정은 로드된다."""
    settings = make_settings()
    assert settings.superset_app_root is None
    assert settings.superset_service_user is None
    assert settings.superset_service_password is None
    assert settings.superset_guest_issuer_user is None
    assert settings.superset_guest_issuer_password is None


def test_superset_settings_load_from_environment(make_settings):
    settings = make_settings(**_SUPERSET_ENV)
    assert settings.superset_app_root == "/bi-wizard/superset"
    assert settings.superset_service_user == "bi_service"
    assert settings.superset_guest_issuer_user == "bi_guest_issuer"
    assert settings.superset_service_password is not None
    assert settings.superset_service_password.get_secret_value() == "SECRET-SERVICE-PW-1"
    assert settings.superset_guest_issuer_password is not None
    assert settings.superset_guest_issuer_password.get_secret_value() == "SECRET-ISSUER-PW-2"


def test_superset_internal_url_is_a_code_constant_not_a_setting():
    from app.config import SUPERSET_INTERNAL_URL

    assert SUPERSET_INTERNAL_URL == "http://superset:8088"
    assert "superset_internal_url" not in Settings.model_fields


def test_superset_passwords_do_not_appear_in_repr_str_or_dump(make_settings):
    settings = make_settings(**_SUPERSET_ENV)
    for text in (repr(settings), str(settings), str(settings.model_dump())):
        assert "SECRET-SERVICE-PW-1" not in text
        assert "SECRET-ISSUER-PW-2" not in text
    assert "SECRET-SERVICE-PW-1" not in repr(settings.superset_service_password)


@pytest.mark.parametrize(
    "value", ["", "bi-wizard/superset", "/bi-wizard/superset/", "/a//b", "/a/../b", "/a b"]
)
def test_superset_app_root_rejects_empty_and_invalid_values(make_settings, value):
    with pytest.raises(ValidationError):
        make_settings(SUPERSET_APP_ROOT=value)


@pytest.mark.parametrize("variable", ["SUPERSET_SERVICE_USER", "SUPERSET_GUEST_ISSUER_USER"])
def test_superset_account_name_cannot_be_empty(make_settings, variable):
    with pytest.raises(ValidationError, match=variable.lower()):
        make_settings(**{variable: ""})


def test_validation_errors_do_not_echo_superset_passwords(make_settings):
    """다른 항목 때문에 설정 검증이 실패해도 오류 메시지에 비밀번호가 섞여 나오지 않는다."""
    with pytest.raises(ValidationError) as caught:
        make_settings(**{**_SUPERSET_ENV, "SUPERSET_APP_ROOT": "", "SUPERSET_SERVICE_USER": ""})
    text = str(caught.value)
    assert "SECRET-SERVICE-PW-1" not in text
    assert "SECRET-ISSUER-PW-2" not in text
    assert "superset_app_root" in text


def test_main_starts_without_superset_settings(monkeypatch):
    """Superset 설정이 없어도 `python -m app` 시작은 막히지 않는다(DB 비밀번호만 조건)."""
    from app import __main__ as entry

    monkeypatch.setenv("POSTGRES_APP_PASSWORD", "app-pw")
    called = []
    monkeypatch.setattr(entry.uvicorn, "run", lambda *a, **k: called.append(True))
    entry.main()
    assert called == [True]


@pytest.mark.parametrize("variable", ["SUPERSET_SERVICE_USER", "SUPERSET_GUEST_ISSUER_USER"])
@pytest.mark.parametrize("value", [" ", "   ", "\t", "\n"])
def test_superset_account_name_cannot_be_whitespace_only(make_settings, variable, value):
    with pytest.raises(ValidationError, match=variable.lower()):
        make_settings(**{variable: value})


@pytest.mark.parametrize(
    "variable", ["SUPERSET_SERVICE_PASSWORD", "SUPERSET_GUEST_ISSUER_PASSWORD"]
)
def test_superset_empty_password_is_unset_not_an_error(make_settings, variable):
    """빈 비밀번호는 로드 오류가 아니라 미설정과 같다(사용하는 쪽이 사용 시점에 실패한다)."""
    settings = make_settings(**{variable: ""})
    secret = getattr(settings, variable.lower())
    assert secret is not None
    assert secret.get_secret_value() == ""


def test_runtime_engine_hides_sql_parameters(make_settings):
    """DB 오류 메시지에 파라미터 값(login_id 등)이 들어가지 않게 엔진이 hide_parameters를 켠다."""
    from app.db import create_db_engine

    engine = create_db_engine(make_settings(POSTGRES_APP_PASSWORD="app-pw"))
    try:
        assert engine.hide_parameters is True
    finally:
        engine.dispose()
