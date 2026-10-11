import pytest
from pydantic import ValidationError

from app.config import Settings, validate_base_path
from app.db import build_database_url


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


@pytest.mark.parametrize("name", ["POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"])
def test_required_postgres_values_fail_closed(monkeypatch, name):
    monkeypatch.setenv(name, "")
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_database_url_uses_pg8000_and_escapes_password(make_settings):
    settings = make_settings(POSTGRES_PASSWORD="p@ss:w/rd%2f?#")
    url = build_database_url(settings)
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
