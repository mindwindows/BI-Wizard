"""서버 명령(`python -m app.cli`): 최초 관리자 만들기와 시험용 사용자 시드."""

import pytest

from app.cli import EXIT_DB, EXIT_INPUT, EXIT_OK, EXIT_REFUSED, main
from app.config import Settings
from app.db_metadata import team_members, teams, users
from tests.conftest import Db


def run(argv, settings, engine):
    return main(argv, settings=settings, engine=engine)


def admin_args(login_id="boss", name="총괄 관리자"):
    return ["create-admin", "--login-id", login_id, "--display-name", name]


# --- create-admin ----


def test_create_admin_creates_active_admin(make_settings, db: Db, capsys):
    assert run(admin_args(), make_settings(), db.engine) == EXIT_OK
    assert capsys.readouterr().out.strip() == "관리자를 만들었다."
    [row] = db.rows(users)
    assert (row["login_id"], row["display_name"], row["is_admin"], row["is_active"]) == (
        "boss",
        "총괄 관리자",
        True,
        True,
    )


def test_create_admin_is_idempotent_for_existing_active_admin(make_settings, db: Db, capsys):
    run(admin_args(), make_settings(), db.engine)
    capsys.readouterr()
    assert run(admin_args(name="다른 이름"), make_settings(), db.engine) == EXIT_OK
    assert "변경 없음" in capsys.readouterr().out
    [row] = db.rows(users)
    assert row["display_name"] == "총괄 관리자"  # 기존 값을 바꾸지 않는다.


@pytest.mark.parametrize(
    ("is_admin", "is_active"), [(False, True), (False, False), (True, False)], ids=str
)
def test_create_admin_refuses_existing_non_admin_or_inactive_user(
    make_settings, db: Db, capsys, is_admin, is_active
):
    db.add_user("boss", "기존", is_admin=is_admin, is_active=is_active)
    assert run(admin_args(), make_settings(), db.engine) == EXIT_INPUT
    assert "이미 등록된 사용자" in capsys.readouterr().err
    [row] = db.rows(users)
    assert (row["display_name"], row["is_admin"], row["is_active"]) == ("기존", is_admin, is_active)


@pytest.mark.parametrize(
    ("login_id", "name"),
    [("", "이름"), ("ok", ""), ("ok", "  "), ("a" * 201, "x"), ("a\nb", "x")],
)
def test_create_admin_validates_input(make_settings, db: Db, capsys, login_id, name):
    assert run(admin_args(login_id, name), make_settings(), db.engine) == EXIT_INPUT
    assert "올바르지 않다" in capsys.readouterr().err
    assert db.rows(users) == []


def test_create_admin_works_with_stub_off_and_on(make_settings, db: Db):
    assert run(admin_args("a"), make_settings(), db.engine) == EXIT_OK
    settings = make_settings(AUTH_STUB_ENABLED="true", APP_ENV="test")
    assert run(admin_args("b"), settings, db.engine) == EXIT_OK


def test_db_failure_exits_1_without_leaking_details(make_settings, broken_engine, capsys):
    settings = make_settings(POSTGRES_APP_PASSWORD="top-secret-pw")
    assert run(admin_args(), settings, broken_engine) == EXIT_DB
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "OperationalError" in output
    for leaked in ("top-secret-pw", "nonexistent-dir", "boss"):
        assert leaked not in output


def test_missing_app_password_is_refused_without_engine(make_settings, capsys):
    assert main(admin_args(), settings=make_settings()) == EXIT_REFUSED
    err = capsys.readouterr().err
    assert "POSTGRES_APP_PASSWORD" in err and "DB 접속 설정이 없다" in err


# --- seed-stub-users ----


def test_seed_refused_when_stub_is_off(make_settings, db: Db, capsys):
    assert run(["seed-stub-users"], make_settings(), db.engine) == EXIT_REFUSED
    assert "AUTH_STUB_ENABLED" in capsys.readouterr().err
    assert db.rows(users) == [] and db.rows(teams) == []


def test_seed_refused_even_with_local_app_env_when_stub_is_off(make_settings, db: Db):
    assert run(["seed-stub-users"], make_settings(APP_ENV="local"), db.engine) == EXIT_REFUSED
    assert db.rows(users) == []


@pytest.mark.parametrize("app_env", ["production", "staging", "Local", ""])
def test_seed_refused_when_settings_forbid_stub_in_this_env(monkeypatch, app_env, capsys):
    """스텁이 켜졌는데 APP_ENV가 허용 밖이면 설정 로딩부터 거부한다(DB에 닿기 전에)."""
    monkeypatch.setenv("AUTH_STUB_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", app_env)
    assert main(["seed-stub-users"]) == EXIT_REFUSED
    assert "설정이 올바르지 않아" in capsys.readouterr().err


def test_seed_refused_without_explicit_app_env(monkeypatch):
    monkeypatch.setenv("AUTH_STUB_ENABLED", "true")
    assert main(["seed-stub-users"]) == EXIT_REFUSED


def test_seed_creates_stub_data_once(stub_settings: Settings, db: Db, capsys):
    assert run(["seed-stub-users"], stub_settings, db.engine) == EXIT_OK
    assert "팀 2, 사용자 6, 소속 5개 새로 만듦" in capsys.readouterr().out
    logins = {r["login_id"]: r for r in db.rows(users)}
    assert set(logins) == {
        "stub-admin",
        "stub-definer",
        "stub-entry",
        "stub-multi",
        "stub-viewer",
        "stub-inactive",
    }
    assert logins["stub-admin"]["is_admin"] and not logins["stub-definer"]["is_admin"]
    assert logins["stub-inactive"]["is_active"] is False
    assert len(db.rows(teams)) == 2 and len(db.rows(team_members)) == 5
    # 두 번째 실행은 아무것도 만들지 않는다(멱등).
    assert run(["seed-stub-users"], stub_settings, db.engine) == EXIT_OK
    assert "팀 0, 사용자 0, 소속 0개 새로 만듦" in capsys.readouterr().out
    assert len(db.rows(users)) == 6


def test_seed_does_not_touch_existing_rows(stub_settings: Settings, db: Db):
    db.add_user("stub-viewer", "내가 바꾼 이름", is_admin=True)
    run(["seed-stub-users"], stub_settings, db.engine)
    viewer = next(r for r in db.rows(users) if r["login_id"] == "stub-viewer")
    assert (viewer["display_name"], viewer["is_admin"]) == ("내가 바꾼 이름", True)


def test_unknown_command_is_rejected_by_argparse():
    with pytest.raises(SystemExit) as exit_info:
        main(["delete-everything"])
    assert exit_info.value.code == 2
