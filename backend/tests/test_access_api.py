"""권한 관리 API(05 §2-1 A1~A9) 동작. SQLite와 실제 PostgreSQL(`pg`, 환경이 있을 때)에서 돈다."""

import logging
import unicodedata

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db_metadata import team_members, teams, users
from app.main import create_app
from tests.api_helpers import make_caller
from tests.conftest import Db, RecordingSync


def err(response) -> dict:
    return response.json()["error"]


def field_codes(response) -> dict[str, str]:
    return {f["field"]: f["code"] for f in err(response)["details"]["fields"]}


# --- A1 /me ----


def test_me_returns_profile_and_memberships(api, world):
    response = api("definer", "GET", "/api/me")
    assert response.status_code == 200
    assert response.json() == {
        "id": world.ids["definer"],
        "display_name": "정의 담당자",
        "is_active": True,
        "is_admin": False,
        "memberships": [
            {"team_id": world.team_a, "team_code": "team_a", "team_name": "A팀", "role": "definer"}
        ],
    }


def test_me_for_admin_without_team_has_empty_memberships(api, world):
    body = api("admin", "GET", "/api/me").json()
    assert body["is_admin"] is True and body["memberships"] == []


def test_me_rejects_inactive_unregistered_and_anonymous(api, world):
    assert err(api("inactive", "GET", "/api/me"))["code"] == "USER_INACTIVE"
    assert err(api("stranger", "GET", "/api/me"))["code"] == "USER_NOT_REGISTERED"
    assert err(api(None, "GET", "/api/me"))["code"] == "UNAUTHENTICATED"


# --- A2 GET /teams ----


def test_teams_list_shape_order_and_paging(api, db, world):
    body = api("viewer", "GET", "/api/teams").json()
    assert set(body) == {"items", "total", "limit", "offset"}
    assert (body["total"], body["limit"], body["offset"]) == (2, 50, 0)
    assert body["items"] == [
        {"id": world.team_a, "code": "team_a", "name": "A팀", "is_active": True},
        {"id": world.team_b, "code": "team_b", "name": "B팀", "is_active": True},
    ]
    page = api("viewer", "GET", "/api/teams", params={"limit": 1, "offset": 1}).json()
    assert [t["code"] for t in page["items"]] == ["team_b"]
    assert (page["total"], page["limit"], page["offset"]) == (2, 1, 1)


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"offset": -1}, {"limit": "x"}])
def test_list_paging_bounds_are_422(api, world, params):
    response = api("admin", "GET", "/api/teams", params=params)
    assert response.status_code == 422 and err(response)["code"] == "VALIDATION_ERROR"


def test_list_limit_200_is_allowed(api, world):
    assert api("admin", "GET", "/api/users", params={"limit": 200}).json()["limit"] == 200


def test_inactive_teams_are_listed(api, db, world):
    db.add_team("old", "옛 팀", is_active=False)
    items = api("viewer", "GET", "/api/teams").json()["items"]
    assert any(t["code"] == "old" and t["is_active"] is False for t in items)


# --- A3 POST /teams ----


def test_create_team(api, db, world):
    response = api("admin", "POST", "/api/teams", json={"code": "finance_1", "name": "재무팀"})
    assert response.status_code == 201
    body = response.json()
    assert body == {"id": body["id"], "code": "finance_1", "name": "재무팀", "is_active": True}
    assert [r["code"] for r in db.rows(teams, teams.c.id)][-1] == "finance_1"


@pytest.mark.parametrize(
    "code",
    ["", "Team", "has space", "a" * 33, "팀", "abc\n", "a-b", "a.b", " abc", "abc "],
)
def test_create_team_rejects_bad_code(api, world, code):
    response = api("admin", "POST", "/api/teams", json={"code": code, "name": "새 팀"})
    assert response.status_code == 422
    assert err(response)["code"] == "VALIDATION_ERROR"
    assert "code" in field_codes(response)


def test_create_team_accepts_boundary_codes(api, world):
    for i, code in enumerate(["a", "0", "_", "z" * 32]):
        assert (
            api("admin", "POST", "/api/teams", json={"code": code, "name": f"n{i}"}).status_code
            == 201
        )


def test_create_team_duplicate_code_and_name_report_field(api, world):
    dup_code = api("admin", "POST", "/api/teams", json={"code": "team_a", "name": "다른 이름"})
    assert dup_code.status_code == 409
    assert err(dup_code)["code"] == "ALREADY_EXISTS"
    assert err(dup_code)["details"] == {"field": "code"}
    dup_name = api("admin", "POST", "/api/teams", json={"code": "unique_1", "name": "A팀"})
    assert dup_name.status_code == 409 and err(dup_name)["details"] == {"field": "name"}


def test_create_team_name_rules(api, db, world):
    assert (
        api("admin", "POST", "/api/teams", json={"code": "t50", "name": "가" * 50}).status_code
        == 201
    )
    long = api("admin", "POST", "/api/teams", json={"code": "t51", "name": "가" * 51})
    assert long.status_code == 422 and field_codes(long) == {"name": "TOO_LONG"}
    for bad in ["", "   ", "줄\n바꿈", "탭\t중간"]:
        response = api("admin", "POST", "/api/teams", json={"code": "tbad", "name": bad})
        assert response.status_code == 422 and "name" in field_codes(response), bad


def test_create_team_normalizes_name_to_nfc_and_strips(api, db, world):
    decomposed = unicodedata.normalize("NFD", "한글팀")
    response = api("admin", "POST", "/api/teams", json={"code": "nfc", "name": f"  {decomposed} "})
    assert response.status_code == 201
    assert response.json()["name"] == "한글팀"
    assert unicodedata.is_normalized("NFC", db.rows(teams, teams.c.id)[-1]["name"])


def test_create_team_requires_fields_and_rejects_unknown(api, world):
    response = api("admin", "POST", "/api/teams", json={})
    assert field_codes(response) == {"code": "REQUIRED", "name": "REQUIRED"}
    extra = api("admin", "POST", "/api/teams", json={"code": "x1", "name": "x", "is_active": False})
    assert extra.status_code == 422


# --- A4 PATCH /teams/{id} ----


class SyncProbe(RecordingSync):
    """팀 동기화 요청 시점에 DB에 이미 커밋돼 있는지 확인하려고 그때의 팀 이름을 기록한다."""

    def __init__(self, db: Db) -> None:
        super().__init__()
        self.db = db
        self.names_seen: list[str] = []

    def request_team_sync(self, team_id: int) -> None:
        self.names_seen.append(next(r["name"] for r in self.db.rows(teams) if r["id"] == team_id))
        super().request_team_sync(team_id)


def test_rename_team_requests_team_sync_after_commit(db, stub_settings, world):
    probe = SyncProbe(db)
    with TestClient(create_app(stub_settings, engine=db.engine, dataset_sync=probe)) as client:
        call = make_caller(client)
        response = call("admin", "PATCH", f"/api/teams/{world.team_a}", json={"name": "새 A팀"})
        assert response.status_code == 200 and response.json()["name"] == "새 A팀"
    assert probe.team_requests == [world.team_a]
    assert probe.names_seen == ["새 A팀"]  # 커밋된 값을 본다.
    assert probe.dataset_requests == []


def test_team_patch_without_name_change_does_not_sync(api, sync, world):
    same = api("admin", "PATCH", f"/api/teams/{world.team_a}", json={"name": "A팀"})
    deactivate = api("admin", "PATCH", f"/api/teams/{world.team_a}", json={"is_active": False})
    empty = api("admin", "PATCH", f"/api/teams/{world.team_a}", json={})
    assert same.status_code == deactivate.status_code == empty.status_code == 200
    assert deactivate.json()["is_active"] is False and empty.json()["is_active"] is False
    assert sync.team_requests == []
    reactivate = api("admin", "PATCH", f"/api/teams/{world.team_a}", json={"is_active": True})
    assert reactivate.json()["is_active"] is True


def test_team_patch_errors(api, sync, world):
    dup = api("admin", "PATCH", f"/api/teams/{world.team_a}", json={"name": "B팀"})
    assert dup.status_code == 409 and err(dup)["details"] == {"field": "name"}
    assert api("admin", "PATCH", "/api/teams/99999", json={"name": "x"}).status_code == 404
    for body in ({"code": "new_code"}, {"name": None}, {"is_active": "yes"}, {"name": "가" * 51}):
        assert api("admin", "PATCH", f"/api/teams/{world.team_a}", json=body).status_code == 422
    assert sync.team_requests == []


def test_team_sync_failure_does_not_change_response_and_is_logged_safely(
    db, stub_settings, world, caplog
):
    failing = RecordingSync(fail=True)
    with TestClient(create_app(stub_settings, engine=db.engine, dataset_sync=failing)) as client:
        with caplog.at_level(logging.ERROR):
            response = make_caller(client)(
                "admin", "PATCH", f"/api/teams/{world.team_a}", json={"name": "바뀐 이름"}
            )
    assert response.status_code == 200 and response.json()["name"] == "바뀐 이름"
    assert failing.team_requests == [world.team_a]
    assert "팀 동기화 요청 실패: RuntimeError" in caplog.text
    assert "secret detail" not in caplog.text


# --- A5 GET /users ----


def test_users_list_includes_memberships(api, world):
    body = api("admin", "GET", "/api/users").json()
    assert body["total"] == 6 and body["limit"] == 50
    by_login = {u["login_id"]: u for u in body["items"]}
    assert set(by_login["definer"]) == {
        "id",
        "login_id",
        "display_name",
        "is_admin",
        "is_active",
        "memberships",
    }
    assert by_login["definer"]["memberships"] == [{"team_id": world.team_a, "role": "definer"}]
    assert by_login["viewer"]["memberships"] == []
    assert by_login["inactive"]["is_active"] is False


def test_users_list_filters(api, db, world):
    def logins(**params):
        return sorted(
            u["login_id"] for u in api("admin", "GET", "/api/users", params=params).json()["items"]
        )

    assert logins(team_id=world.team_a) == ["definer", "entry"]
    assert logins(team_id=world.team_b) == ["other"]
    assert logins(is_active="false") == ["inactive"]
    assert logins(q="ADMIN") == ["admin"]  # 대소문자 무시
    assert logins(q="입력") == ["entry"]  # 표시 이름 검색
    assert logins(q="no-such") == []
    assert logins(q="%") == []  # 와일드카드가 아니라 글자 그대로
    assert logins(q="_") == []
    assert logins(team_id=world.team_a, is_active="false") == []


def test_users_list_paging_total(api, world):
    page = api("admin", "GET", "/api/users", params={"limit": 2, "offset": 4}).json()
    assert len(page["items"]) == 2 and page["total"] == 6 and page["offset"] == 4


# --- A6 POST /users ----


def test_create_user_defaults(api, db, world):
    response = api(
        "admin", "POST", "/api/users", json={"login_id": "newbie", "display_name": "  신입 "}
    )
    assert response.status_code == 201
    body = response.json()
    assert body == {
        "id": body["id"],
        "login_id": "newbie",
        "display_name": "신입",
        "is_admin": False,
        "is_active": True,
        "memberships": [],
    }
    # 만든 사용자는 곧바로 스텁으로 로그인할 수 있다.
    assert api("newbie", "GET", "/api/me").status_code == 200


def test_create_admin_user(api, world):
    body = api(
        "admin",
        "POST",
        "/api/users",
        json={"login_id": "boss", "display_name": "상사", "is_admin": True},
    ).json()
    assert body["is_admin"] is True


def test_create_user_duplicate_login_id(api, world):
    response = api(
        "admin", "POST", "/api/users", json={"login_id": "viewer", "display_name": "중복"}
    )
    assert response.status_code == 409
    assert err(response)["code"] == "ALREADY_EXISTS" and err(response)["details"] == {
        "field": "login_id"
    }
    # 로그인 ID는 정확히 같을 때만 중복이다(대소문자 구분, 신원 어댑터 값을 그대로 쓴다).
    ok = api("admin", "POST", "/api/users", json={"login_id": "VIEWER", "display_name": "대문자"})
    assert ok.status_code == 201


@pytest.mark.parametrize(
    "body",
    [
        {"login_id": "", "display_name": "x"},
        {"login_id": "a" * 201, "display_name": "x"},
        {"login_id": "line\nbreak", "display_name": "x"},
        {"login_id": "ok", "display_name": ""},
        {"login_id": "ok", "display_name": "  "},
        {"login_id": "ok", "display_name": "가" * 101},
        {"login_id": "ok", "display_name": "탭\t중간"},
        {"login_id": "ok", "display_name": "x", "is_admin": "true"},
        {"login_id": "ok", "display_name": "x", "is_active": False},
        {"display_name": "x"},
    ],
)
def test_create_user_validation(api, world, body):
    response = api("admin", "POST", "/api/users", json=body)
    assert response.status_code == 422 and err(response)["code"] == "VALIDATION_ERROR"


# --- A7 PATCH /users/{id} ----


def test_update_user_fields(api, db, world):
    uid = world.ids["viewer"]
    response = api("admin", "PATCH", f"/api/users/{uid}", json={"display_name": "새 이름"})
    assert response.status_code == 200 and response.json()["display_name"] == "새 이름"
    promoted = api("admin", "PATCH", f"/api/users/{uid}", json={"is_admin": True}).json()
    assert promoted["is_admin"] is True and promoted["display_name"] == "새 이름"
    deactivated = api("admin", "PATCH", f"/api/users/{uid}", json={"is_active": False}).json()
    assert deactivated["is_active"] is False
    assert err(api("viewer", "GET", "/api/me"))["code"] == "USER_INACTIVE"
    api("admin", "PATCH", f"/api/users/{uid}", json={"is_active": True})
    assert api("viewer", "GET", "/api/me").status_code == 200


def test_update_user_returns_memberships(api, world):
    body = api("admin", "PATCH", f"/api/users/{world.ids['definer']}", json={}).json()
    assert body["memberships"] == [{"team_id": world.team_a, "role": "definer"}]


def test_update_user_errors(api, world):
    uid = world.ids["viewer"]
    assert api("admin", "PATCH", "/api/users/99999", json={"is_active": False}).status_code == 404
    for body in ({"login_id": "new"}, {"is_admin": None}, {"display_name": ""}, {"is_active": 1}):
        assert api("admin", "PATCH", f"/api/users/{uid}", json=body).status_code == 422, body


def test_last_admin_cannot_be_demoted_or_deactivated(api, db, world):
    uid = world.ids["admin"]
    demote = api("admin", "PATCH", f"/api/users/{uid}", json={"is_admin": False})
    assert demote.status_code == 409 and err(demote)["code"] == "LAST_ADMIN"
    deactivate = api("admin", "PATCH", f"/api/users/{uid}", json={"is_active": False})
    assert deactivate.status_code == 409 and err(deactivate)["code"] == "LAST_ADMIN"
    both = api("admin", "PATCH", f"/api/users/{uid}", json={"is_admin": False, "is_active": False})
    assert both.status_code == 409
    row = next(r for r in db.rows(users) if r["id"] == uid)
    assert row["is_admin"] and row["is_active"]
    # 마지막 관리자도 다른 필드는 바꿀 수 있고, 그대로 두는 요청(이미 관리자)은 막지 않는다.
    assert (
        api("admin", "PATCH", f"/api/users/{uid}", json={"display_name": "총괄"}).status_code == 200
    )
    assert api("admin", "PATCH", f"/api/users/{uid}", json={"is_admin": True}).status_code == 200


def test_last_admin_rule_counts_only_active_admins(api, db, world):
    # 비활성 관리자는 세지 않는다: 활성 관리자 한 명만 남은 상태다.
    inactive_admin = db.add_user("old-admin", "옛 관리자", is_admin=True, is_active=False)
    blocked = api("admin", "PATCH", f"/api/users/{world.ids['admin']}", json={"is_admin": False})
    assert blocked.status_code == 409
    # 비활성 관리자를 일반 사용자로 바꾸는 것은 막지 않는다(활성 관리자가 줄지 않는다).
    freed = api("admin", "PATCH", f"/api/users/{inactive_admin}", json={"is_admin": False})
    assert freed.status_code == 200


def test_admin_can_be_demoted_when_another_active_admin_exists(api, db, world):
    other = db.add_user("admin2", "관리자2", is_admin=True)
    assert api("admin", "PATCH", f"/api/users/{other}", json={"is_admin": False}).status_code == 200
    # 이제 admin이 마지막이다.
    last = api("admin", "PATCH", f"/api/users/{world.ids['admin']}", json={"is_active": False})
    assert err(last)["code"] == "LAST_ADMIN"
    db.add_user("admin3", "관리자3", is_admin=True)
    # 자기 자신을 비활성화하면 이후 요청은 USER_INACTIVE다.
    assert (
        api(
            "admin", "PATCH", f"/api/users/{world.ids['admin']}", json={"is_active": False}
        ).status_code
        == 200
    )
    assert err(api("admin", "GET", "/api/me"))["code"] == "USER_INACTIVE"


# --- A8 PUT / A9 DELETE members ----


def test_put_member_adds_then_changes_role(api, db, world):
    uid, tid = world.ids["viewer"], world.team_b
    path = f"/api/teams/{tid}/members/{uid}"
    added = api("admin", "PUT", path, json={"role": "entry"})
    assert added.status_code == 200
    assert added.json() == {"team_id": tid, "user_id": uid, "role": "entry"}
    changed = api("admin", "PUT", path, json={"role": "definer"})
    assert changed.json()["role"] == "definer"
    same = api("admin", "PUT", path, json={"role": "definer"})
    assert same.status_code == 200
    rows = [r for r in db.rows(team_members) if r["user_id"] == uid]
    assert rows == [{"team_id": tid, "user_id": uid, "role": "definer"}]
    # 새 소속이 /me에 나타난다(여러 팀 소속 가능).
    api("admin", "PUT", f"/api/teams/{world.team_a}/members/{uid}", json={"role": "entry"})
    memberships = api("viewer", "GET", "/api/me").json()["memberships"]
    assert sorted((m["team_code"], m["role"]) for m in memberships) == [
        ("team_a", "entry"),
        ("team_b", "definer"),
    ]


def test_put_member_errors(api, world):
    path = f"/api/teams/{world.team_a}/members/{world.ids['viewer']}"
    for role in ("admin", "", None, "DEFINER"):
        assert api("admin", "PUT", path, json={"role": role}).status_code == 422, role
    assert api("admin", "PUT", path, json={}).status_code == 422
    assert api("admin", "PUT", path, json={"role": "entry", "x": 1}).status_code == 422
    assert (
        api(
            "admin",
            "PUT",
            f"/api/teams/99999/members/{world.ids['viewer']}",
            json={"role": "entry"},
        ).status_code
        == 404
    )
    assert (
        api(
            "admin", "PUT", f"/api/teams/{world.team_a}/members/99999", json={"role": "entry"}
        ).status_code
        == 404
    )


def test_delete_member(api, db, world):
    path = f"/api/teams/{world.team_a}/members/{world.ids['entry']}"
    response = api("admin", "DELETE", path)
    assert response.status_code == 204 and response.content == b""
    assert api("entry", "GET", "/api/me").json()["memberships"] == []
    again = api("admin", "DELETE", path)
    assert again.status_code == 404 and err(again)["code"] == "NOT_FOUND"
    assert api("admin", "DELETE", f"/api/teams/{world.team_a}/members/99999").status_code == 404


def test_permission_checked_before_validation(api, world):
    """권한 없는 사용자는 입력 검증 결과를 알 수 없다: 잘못된 본문이어도 403이다."""
    assert api("viewer", "POST", "/api/teams", json={"code": "BAD"}).status_code == 403
    assert api("viewer", "PATCH", "/api/users/abc", json={}).status_code == 403
    assert api(None, "POST", "/api/teams", json={"code": "BAD"}).status_code == 401


def test_responses_have_request_id_and_error_envelope(api, world):
    response = api("viewer", "POST", "/api/teams", json={"code": "x", "name": "y"})
    body = err(response)
    assert body["code"] == "FORBIDDEN" and body["request_id"] == response.headers["X-Request-ID"]
    assert set(body) == {"code", "message", "details", "request_id"}


def test_settings_fixture_is_stub_enabled(stub_settings: Settings):
    assert stub_settings.auth_stub_enabled and stub_settings.app_env == "test"
