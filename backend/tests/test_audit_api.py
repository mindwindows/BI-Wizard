"""감사 기록 목록 API 시험(05 §2-7 F1): 관리자 전용, 필터, 정렬, 페이지, 422 필드 코드, 경계.

SQLite와 실제 PostgreSQL(`pg`) 두 변형으로 돈다. 행은 소유자 연결로 직접 심어 시각을 정확히 정한다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import OperationalError

from app.audit.actions import ACTIONS
from app.db_metadata import audit_log
from tests.api_helpers import World
from tests.conftest import Db

PATH = "/api/audit-logs"
ITEM_KEYS = {
    "id",
    "occurred_at",
    "actor",
    "actor_source",
    "action",
    "target_type",
    "target_id",
    "details",
}


def err(response) -> dict[str, Any]:
    return response.json()["error"]


def field_codes(response) -> dict[str, str]:
    return {f["field"]: f["code"] for f in err(response)["details"]["fields"]}


def seed(
    db: Db,
    *,
    at: datetime | None = None,
    actor: int | None = None,
    action: str = "team.create",
    target_id: int = 1,
    details: dict[str, Any] | None = None,
) -> int:
    spec = ACTIONS[action]
    values: dict[str, Any] = {
        "actor_source": "user" if actor is not None else "cli",
        "actor_user_id": actor,
        "action": action,
        "target_type": spec.target_type,
        "target_id": target_id,
        "details": details if details is not None else {"target_name": "대상"},
    }
    if at is not None:
        values["occurred_at"] = at
    with db.writer.begin() as conn:
        return conn.execute(
            sa.insert(audit_log).values(**values).returning(audit_log.c.id)
        ).scalar_one()


def utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=UTC)


# --- 권한 ----


@pytest.mark.parametrize("role", ["definer", "entry", "other", "viewer"])
def test_non_admin_members_are_forbidden(api, world: World, role):
    response = api(role, "GET", PATH)
    assert (response.status_code, err(response)["code"]) == (403, "FORBIDDEN")


def test_permission_check_comes_before_query_validation(api, world: World):
    """권한이 없는 사용자는 입력 오류의 내용도 알 수 없다(403이 422보다 먼저)."""
    response = api("viewer", "GET", PATH, params={"from": "garbage", "limit": 9999})
    assert (response.status_code, err(response)["code"]) == (403, "FORBIDDEN")
    response = api("inactive", "GET", PATH, params={"action": "nope"})
    assert (response.status_code, err(response)["code"]) == (403, "USER_INACTIVE")


def test_anonymous_is_unauthenticated_and_the_body_has_no_rows(api, db: Db, world: World):
    seed(db, details={"target_name": "비밀스러운 이름"})
    response = api(None, "GET", PATH)
    assert (response.status_code, err(response)["code"]) == (401, "UNAUTHENTICATED")
    assert "비밀스러운" not in response.text


def test_unregistered_identity_is_forbidden_and_sees_nothing(api, db: Db, world: World):
    seed(db)
    response = api("stranger", "GET", PATH)
    assert (response.status_code, err(response)["code"]) == (403, "USER_NOT_REGISTERED")


def test_admin_can_read(api, world: World):
    response = api("admin", "GET", PATH)
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_there_is_no_way_to_write_through_the_api(api, world: World, method):
    """수정·삭제·내보내기 엔드포인트가 없다(05 F1 규칙 ①). 관리자도 405다."""
    response = api("admin", method, PATH, json={})
    assert (response.status_code, err(response)["code"]) == (405, "METHOD_NOT_ALLOWED")


@pytest.mark.parametrize("path", [PATH + "/1", PATH + "/export", PATH + "/export.csv"])
def test_no_item_or_export_routes_exist(api, world: World, path):
    for method in ("GET", "DELETE", "PATCH", "PUT"):
        assert api("admin", method, path).status_code in {404, 405}


# --- 응답 모양 ----


def test_item_shape_actor_and_kst_timestamp(api, db: Db, world: World):
    admin_id = world.ids["admin"]
    seed(db, at=utc(2026, 10, 13, 6, 30, 5), actor=admin_id, target_id=42)
    seed(db, at=utc(2026, 10, 13, 6, 30, 4), actor=None, action="user.bootstrap_admin")
    body = api("admin", "GET", PATH).json()
    assert body["total"] == 2 and (body["limit"], body["offset"]) == (50, 0)
    user_item, cli_item = body["items"]
    assert set(user_item) == ITEM_KEYS == set(cli_item)
    assert user_item["occurred_at"] == "2026-10-13T15:30:05+09:00"
    assert user_item["actor"] == {"id": admin_id, "display_name": "관리자"}
    assert user_item["actor_source"] == "user"
    assert (user_item["action"], user_item["target_type"], user_item["target_id"]) == (
        "team.create",
        "team",
        42,
    )
    assert user_item["details"] == {"target_name": "대상"}
    assert cli_item["actor"] is None and cli_item["actor_source"] == "cli"
    assert isinstance(user_item["id"], int)


def test_actor_display_name_is_read_at_query_time(api, db: Db, world: World):
    seed(db, actor=world.ids["definer"])
    assert api("admin", "GET", PATH).json()["items"][0]["actor"]["display_name"] == "정의 담당자"
    api("admin", "PATCH", f"/api/users/{world.ids['definer']}", json={"display_name": "새 이름"})
    items = api("admin", "GET", PATH).json()["items"]
    # 이름 변경(user.update)이 방금 기록돼 맨 위에 있고, 이전 행의 행위자 이름은 새 값이다
    assert [i["action"] for i in items] == ["user.update", "team.create"]
    assert items[1]["actor"]["display_name"] == "새 이름"


def test_inactive_actor_is_still_shown(api, db: Db, world: World):
    seed(db, actor=world.ids["inactive"])
    item = api("admin", "GET", PATH).json()["items"][0]
    assert item["actor"] == {"id": world.ids["inactive"], "display_name": "비활성"}


def test_details_are_returned_exactly_as_stored(api, db: Db, world: World):
    stored = {"target_name": "가나다", "changes": {"name": {"from": "가", "to": "나"}}}
    seed(db, action="team.update", details=stored)
    assert api("admin", "GET", PATH).json()["items"][0]["details"] == stored


# --- 정렬·페이지 ----


def test_order_is_newest_first_with_id_descending_on_ties(api, db: Db, world: World):
    t1, t2 = utc(2026, 10, 1, 0, 0, 0), utc(2026, 10, 2, 0, 0, 0)
    a = seed(db, at=t1)
    b = seed(db, at=t2)
    c = seed(db, at=t2)  # 같은 시각: id가 큰 쪽이 먼저
    d = seed(db, at=t1)
    assert [i["id"] for i in api("admin", "GET", PATH).json()["items"]] == [c, b, d, a]


def test_there_is_no_sort_parameter(api, db: Db, world: World):
    """정렬 인자는 없다: 보내도 정렬이 바뀌지 않는다."""
    first = seed(db, at=utc(2026, 10, 1))
    second = seed(db, at=utc(2026, 10, 2))
    for query in ({"sort": "asc"}, {"order": "asc"}, {"order_by": "id"}):
        assert [i["id"] for i in api("admin", "GET", PATH, params=query).json()["items"]] == [
            second,
            first,
        ]


def test_pagination_total_is_exact_and_pages_do_not_overlap(api, db: Db, world: World):
    base = utc(2026, 10, 1, 0, 0, 0)
    ids = [seed(db, at=base + timedelta(minutes=i), target_id=i + 1) for i in range(55)]
    expected = list(reversed(ids))
    first = api("admin", "GET", PATH).json()  # 기본 limit 50
    assert (first["total"], first["limit"], first["offset"], len(first["items"])) == (55, 50, 0, 50)
    second = api("admin", "GET", PATH, params={"offset": 50}).json()
    assert (second["total"], len(second["items"]), second["offset"]) == (55, 5, 50)
    assert [i["id"] for i in first["items"] + second["items"]] == expected
    page = api("admin", "GET", PATH, params={"limit": 10, "offset": 5}).json()
    assert [i["id"] for i in page["items"]] == expected[5:15]
    assert (page["limit"], page["offset"], page["total"]) == (10, 5, 55)
    past_end = api("admin", "GET", PATH, params={"offset": 1000}).json()
    assert (past_end["items"], past_end["total"]) == ([], 55)  # offset에 상한은 없다


def test_limit_boundaries(api, db: Db, world: World):
    for n in range(3):
        seed(db, target_id=n + 1)
    assert len(api("admin", "GET", PATH, params={"limit": 1}).json()["items"]) == 1
    assert api("admin", "GET", PATH, params={"limit": 200}).status_code == 200
    for bad in ({"limit": 0}, {"limit": 201}, {"limit": -1}, {"limit": "x"}, {"offset": -1}):
        response = api("admin", "GET", PATH, params=bad)
        assert (response.status_code, err(response)["code"]) == (422, "VALIDATION_ERROR"), bad


# --- 필터 ----


def test_from_and_to_are_inclusive_korean_dates(api, db: Db, world: World):
    # KST 10-12 23:59:59, 10-13 00:00:00, 10-13 23:59:59, 10-14 00:00:00
    ids = [
        seed(db, at=utc(2026, 10, 12, 14, 59, 59)),
        seed(db, at=utc(2026, 10, 12, 15, 0, 0)),
        seed(db, at=utc(2026, 10, 13, 14, 59, 59)),
        seed(db, at=utc(2026, 10, 13, 15, 0, 0)),
    ]

    def found(**params: str) -> list[int]:
        body = api("admin", "GET", PATH, params=params).json()
        assert body["total"] == len(body["items"])
        return sorted(i["id"] for i in body["items"])

    assert found(**{"from": "2026-10-13"}) == sorted(ids[1:])  # 그날 00:00부터
    assert found(to="2026-10-13") == sorted(ids[:3])  # 그날 24:00 전까지(그날 포함)
    assert found(**{"from": "2026-10-13", "to": "2026-10-13"}) == sorted(ids[1:3])
    assert found(**{"from": "2026-10-14", "to": "2026-10-14"}) == [ids[3]]
    assert found(**{"from": "2026-10-15"}) == []
    assert found(to="2026-10-11") == []
    assert found() == sorted(ids)  # 둘 다 없으면 전체 기간


def test_date_extremes_do_not_crash(api, world: World):
    for params in (
        {"from": "0001-01-01"},
        {"to": "0001-01-01"},
        {"from": "9999-12-31"},
        {"to": "9999-12-31"},
        {"from": "0001-01-01", "to": "9999-12-31"},
    ):
        assert api("admin", "GET", PATH, params=params).status_code == 200, params


def test_actor_target_and_action_filters_combine_with_and(api, db: Db, world: World):
    admin, definer = world.ids["admin"], world.ids["definer"]
    a = seed(db, actor=admin, action="team.create", target_id=5)
    b = seed(db, actor=admin, action="team.update", target_id=5)
    c = seed(db, actor=definer, action="column.add", target_id=5, details={"target_name": "d"})
    d = seed(db, actor=definer, action="team.create", target_id=6)
    e = seed(db, actor=None, action="user.bootstrap_admin", target_id=5)

    def found(**params: Any) -> list[int]:
        return sorted(i["id"] for i in api("admin", "GET", PATH, params=params).json()["items"])

    assert found(actor_user_id=admin) == [a, b]
    assert found(actor_user_id=definer) == [c, d]
    assert found(action="team.create") == [a, d]
    assert found(target_type="team") == [a, b, d]
    assert found(target_type="team", target_id=5) == [a, b]
    assert found(target_type="dataset", target_id=5) == [c]  # 같은 번호라도 대상 종류가 다르다
    assert found(target_type="user", target_id=5) == [e]
    assert found(actor_user_id=admin, action="team.update") == [b]
    assert found(actor_user_id=admin, target_type="team", target_id=5, action="team.create") == [a]
    assert found(actor_user_id=admin, action="column.add") == []
    assert found(actor_user_id=world.ids["entry"]) == []  # 행위자가 없는 사용자
    body = api("admin", "GET", PATH, params={"action": "team.create", "limit": 1}).json()
    assert (body["total"], len(body["items"])) == (2, 1)  # total은 필터 적용 전체 건수


def test_every_action_value_is_accepted_as_a_filter(api, world: World):
    for action in ACTIONS:
        assert api("admin", "GET", PATH, params={"action": action}).status_code == 200


# --- 422: 필드 코드는 05 F1 규칙 ②대로 ----


@pytest.mark.parametrize(
    "value",
    [
        "20261013",
        "2026-1-3",
        "2026-13-01",
        "2026-02-30",
        "2026-10-13T00:00:00",
        "abcd-ef-gh",
        "",
        " 2026-10-13",
        "2026-10-13 ",
        "2026-10-13\n",
        "\uff12\uff10\uff12\uff16-10-13",  # 전각 숫자
        "\u0662\u0660\u0662\u0666-10-13",  # 아랍 인도 숫자
        "1700000000",
        "2026-W41-1",
    ],
)
@pytest.mark.parametrize("name", ["from", "to"])
def test_bad_dates_are_bad_format_on_that_field(api, world: World, name, value):
    response = api("admin", "GET", PATH, params={name: value})
    assert (response.status_code, err(response)["code"]) == (422, "VALIDATION_ERROR")
    assert field_codes(response) == {name: "BAD_FORMAT"}


def test_from_after_to_is_out_of_range_on_to(api, world: World):
    response = api("admin", "GET", PATH, params={"from": "2026-10-14", "to": "2026-10-13"})
    assert response.status_code == 422 and field_codes(response) == {"to": "OUT_OF_RANGE"}
    ok = api("admin", "GET", PATH, params={"from": "2026-10-13", "to": "2026-10-13"})
    assert ok.status_code == 200  # 같은 날은 정상


def test_target_type_and_action_outside_the_list_are_not_in_options(api, world: World):
    response = api("admin", "GET", PATH, params={"target_type": "table"})
    assert field_codes(response) == {"target_type": "NOT_IN_OPTIONS"}
    response = api("admin", "GET", PATH, params={"action": "dataset.delete"})
    assert field_codes(response) == {"action": "NOT_IN_OPTIONS"}
    for bad in ("Team", "TEAM", "team ", ""):
        response = api("admin", "GET", PATH, params={"target_type": bad})
        assert field_codes(response) == {"target_type": "NOT_IN_OPTIONS"}, bad
    response = api("admin", "GET", PATH, params={"action": "member"})
    assert field_codes(response) == {"action": "NOT_IN_OPTIONS"}


def test_target_id_requires_target_type(api, world: World):
    response = api("admin", "GET", PATH, params={"target_id": 3})
    assert response.status_code == 422 and field_codes(response) == {"target_type": "REQUIRED"}
    # 유효하지 않은 종류와 같이 보내면 종류 오류가 먼저다(REQUIRED가 아니다)
    response = api("admin", "GET", PATH, params={"target_id": 3, "target_type": "x"})
    assert field_codes(response) == {"target_type": "NOT_IN_OPTIONS"}


@pytest.mark.parametrize(
    "params",
    [
        {"actor_user_id": "abc"},
        {"actor_user_id": "1.5"},
        {"actor_user_id": ""},
        {"actor_user_id": 0},
        {"actor_user_id": 2**31},  # integer 열 밖: DB 오류(500)가 되지 않는다
        {"target_type": "team", "target_id": "x"},
        {"target_type": "team", "target_id": 0},
        {"target_type": "team", "target_id": 2**63},
    ],
)
def test_non_integer_ids_are_bad_format_not_a_server_error(api, world: World, params):
    response = api("admin", "GET", PATH, params=params)
    assert response.status_code == 422, (params, response.text)
    assert set(field_codes(response).values()) == {"BAD_FORMAT"}


def test_large_but_valid_target_ids_work(api, db: Db, world: World):
    seed(db, target_id=2**62)
    body = api("admin", "GET", PATH, params={"target_type": "team", "target_id": 2**62}).json()
    assert body["total"] == 1 and body["items"][0]["target_id"] == 2**62


def test_several_problems_are_reported_together(api, world: World):
    response = api(
        "admin",
        "GET",
        PATH,
        params={"from": "x", "to": "2026-10-13", "target_type": "nope", "action": "nope"},
    )
    assert field_codes(response) == {
        "from": "BAD_FORMAT",
        "target_type": "NOT_IN_OPTIONS",
        "action": "NOT_IN_OPTIONS",
    }
    # 오류 응답에는 입력한 값이 되돌아가지 않는다
    assert "nope" not in response.text


# --- 503 ----


def test_database_failure_is_service_unavailable(api, world: World, monkeypatch):
    def boom(*args, **kwargs):
        raise OperationalError("SELECT secret FROM audit_log", {}, Exception("connection refused"))

    monkeypatch.setattr("app.audit.repo.list_entries", boom)
    response = api("admin", "GET", PATH)
    assert (response.status_code, err(response)["code"]) == (503, "SERVICE_UNAVAILABLE")
    assert "secret" not in response.text


# --- 이 조회가 기록을 남기거나 바꾸지 않는다 ----


def test_reading_does_not_create_or_change_audit_rows(api, db: Db, world: World):
    seed(db)
    before = db.rows(audit_log, audit_log.c.id)
    for _ in range(3):
        assert api("admin", "GET", PATH).status_code == 200
    assert db.rows(audit_log, audit_log.c.id) == before
