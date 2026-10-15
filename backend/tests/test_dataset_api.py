"""데이터셋·열 정의 API 시험(05 §2-2 B1~B6, 06). SQLite와 실제 PostgreSQL(`pg`) 두 변형으로 돈다.

SQLite 변형은 `bi_data`를 메모리 DB로 붙여 원본 표 생성·열 추가까지 실제로 실행한다. 기준 날짜
열 규칙(NOT NULL 변경, CHECK, 유일 인덱스)은 SQLite가 지원하지 않아 호출 기록(`db.period_calls`)으로
대신하고, 실제 효과는 `pg` 변형에서 확인한다.
"""

import logging
import re
from contextlib import contextmanager
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app import ddl
from app.core.errors import AppError, ErrorCode
from app.core.ports import DefinitionHooks
from app.dataset.hashing import structure_hash
from app.db_metadata import DYNAMIC_SCHEMA, dataset_columns, datasets, formulas
from app.main import create_app
from tests.api_helpers import World, make_caller
from tests.conftest import Db, RecordingSync


def err(response) -> dict[str, Any]:
    return response.json()["error"]


def field_codes(response) -> dict[str, str]:
    return {f["field"]: f["code"] for f in err(response)["details"]["fields"]}


def make_dataset(api, world: World, name="월별 매출", unit="day", who="definer", team=None) -> dict:
    response = api(
        who,
        "POST",
        "/api/datasets",
        json={"team_id": team or world.team_a, "name": name, "date_unit": unit},
    )
    assert response.status_code == 201, response.text
    return response.json()


def make_column(
    api, dataset: dict, name="매출", column_type="number", who="definer", **extra
) -> dict:
    body = {"expected_version": dataset["def_version"], "display_name": name, "type": column_type}
    response = api(who, "POST", f"/api/datasets/{dataset['id']}/columns", json={**body, **extra})
    assert response.status_code == 201, response.text
    dataset["def_version"] = response.json()["def_version"]
    return response.json()["column"]


def ds_columns(db: Db, dataset_id: int) -> dict[str, str]:
    inspector = sa.inspect(db.engine)
    return {
        c["name"]: str(c["type"]).lower()
        for c in inspector.get_columns(f"ds_{dataset_id}", schema=DYNAMIC_SCHEMA)
    }


def ds_exists(db: Db, dataset_id: int) -> bool:
    return sa.inspect(db.engine).has_table(f"ds_{dataset_id}", schema=DYNAMIC_SCHEMA)


def dataset_row(db: Db, dataset_id: int) -> dict[str, Any]:
    return next(r for r in db.rows(datasets) if r["id"] == dataset_id)


@contextmanager
def custom_client(db: Db, settings, sync, *, hooks=None, quiet=False, row_view=None):
    """훅·동기화 대역을 끼운 앱의 호출기. `quiet`이면 서버 예외를 500 응답으로 받는다.

    앱이 닫히면 엔진이 정리되어(SQLite 메모리 DB도 사라진다) DB 확인은 `with` 안에서 한다.
    """
    app = create_app(
        settings, engine=db.engine, dataset_sync=sync, definition_hooks=hooks, row_view=row_view
    )
    with TestClient(app, raise_server_exceptions=not quiet) as client:
        yield make_caller(client)


def assert_no_dataset_leftovers(db: Db) -> None:
    assert db.rows(datasets) == []
    if db.kind == "pg":  # SQLite의 DDL은 트랜잭션에 묶이지 않아 표 확인은 PostgreSQL에서만 한다.
        assert sa.inspect(db.engine).get_table_names(schema=DYNAMIC_SCHEMA) == []


# --- B2 데이터셋 만들기 ----


def test_create_dataset_returns_detail_and_creates_the_source_table(api, db, world):
    response = api(
        "definer",
        "POST",
        "/api/datasets",
        json={"team_id": world.team_a, "name": "월별 매출", "date_unit": "month"},
    )
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {
        "id",
        "team_id",
        "name",
        "date_unit",
        "base_date_column_id",
        "status",
        "def_version",
        "created_by",
        "created_at",
        "team",
        "columns",
        "permissions",
    }
    assert body["team_id"] == world.team_a and body["name"] == "월별 매출"
    assert body["date_unit"] == "month" and body["base_date_column_id"] is None
    assert body["status"] == "active" and body["def_version"] == 1
    assert body["created_by"] == {"id": world.ids["definer"], "display_name": "정의 담당자"}
    assert body["created_at"].endswith("+09:00") and "T" in body["created_at"]
    assert body["team"] == {"id": world.team_a, "code": "team_a", "name": "A팀"}
    assert body["columns"] == []
    assert body["permissions"] == {"define": True, "enter": True}
    # 같은 트랜잭션에서 원본 표(`ds_<번호>`: row_id만)가 만들어졌다.
    assert ds_columns(db, body["id"]) == {"row_id": ds_columns(db, body["id"])["row_id"]}
    row = dataset_row(db, body["id"])
    # 1d부터 def_hash는 뷰 정의 해시(sha256 16진)다. 훅이 없을 때만 구조 해시를 쓴다.
    assert re.fullmatch("[0-9a-f]{64}", row["def_hash"])
    assert row["def_hash"] != structure_hash([]) and row["created_by"] == world.ids["definer"]


def test_created_dataset_names_use_the_numbered_table_only(api, db, world):
    first = make_dataset(api, world, name="한글 이름 데이터셋")
    second = make_dataset(api, world, name="또 다른 데이터셋")
    names = set(sa.inspect(db.engine).get_table_names(schema=DYNAMIC_SCHEMA))
    assert {f"ds_{first['id']}", f"ds_{second['id']}"} <= names
    assert all(
        n.startswith("ds_") and n[3:].isdigit() for n in names
    )  # 사용자 글자는 식별자에 없다


def test_create_dataset_requests_sync_after_commit(api, db, sync, world):
    dataset = make_dataset(api, world)
    assert sync.dataset_requests == [dataset["id"]]


def test_create_dataset_sync_failure_does_not_change_the_response(db, stub_settings, world, caplog):
    class Failing(RecordingSync):
        def request_dataset_sync(self, dataset_id: int) -> None:
            raise RuntimeError("secret detail SELECT")

    with custom_client(db, stub_settings, Failing()) as call, caplog.at_level(logging.ERROR):
        response = call(
            "definer",
            "POST",
            "/api/datasets",
            json={"team_id": world.team_a, "name": "x", "date_unit": "day"},
        )
    assert response.status_code == 201
    assert "RuntimeError" in caplog.text
    assert "secret detail" not in caplog.text and "SELECT" not in caplog.text


def test_create_dataset_duplicate_name_in_team_is_409_and_creates_nothing(api, db, sync, world):
    first = make_dataset(api, world, name="매출")
    before = set(sa.inspect(db.engine).get_table_names(schema=DYNAMIC_SCHEMA))
    response = api(
        "definer",
        "POST",
        "/api/datasets",
        json={"team_id": world.team_a, "name": "매출", "date_unit": "day"},
    )
    assert response.status_code == 409
    assert err(response)["code"] == "ALREADY_EXISTS"
    assert err(response)["details"] == {"field": "name"}
    assert set(sa.inspect(db.engine).get_table_names(schema=DYNAMIC_SCHEMA)) == before
    assert [r["id"] for r in db.rows(datasets)] == [first["id"]]
    assert sync.dataset_requests == [first["id"]]  # 실패한 요청은 동기화를 요청하지 않는다


def test_same_name_is_allowed_in_another_team(api, db, world):
    db.add_member(world.team_b, world.ids["definer"], "definer")
    a = make_dataset(api, world, name="매출", team=world.team_a)
    b = make_dataset(api, world, name="매출", team=world.team_b)
    assert a["id"] != b["id"]


def test_dataset_name_normalized_and_validated(api, world):
    ok = make_dataset(api, world, name="  한 글  ")
    assert ok["name"] == "한 글"
    assert make_dataset(api, world, name="가" * 100)["name"] == "가" * 100
    cases = {
        "가" * 101: "TOO_LONG",
        "": "REQUIRED",
        "   ": "REQUIRED",
        "줄\n바꿈": "BAD_FORMAT",
    }
    for name, code in cases.items():
        response = api(
            "definer",
            "POST",
            "/api/datasets",
            json={"team_id": world.team_a, "name": name, "date_unit": "day"},
        )
        assert response.status_code == 422, name
        assert field_codes(response) == {"name": code}, name


@pytest.mark.parametrize(
    "body",
    [
        {"name": "x", "date_unit": "day"},
        {"team_id": "a", "name": "x", "date_unit": "day"},
        {"team_id": 1, "date_unit": "day"},
        {"team_id": 1, "name": "x"},
        {"team_id": 1, "name": "x", "date_unit": "week"},
        {"team_id": 1, "name": "x", "date_unit": "day", "status": "active"},
        {"team_id": 1, "name": "x", "date_unit": "day", "created_by": 1},
    ],
)
def test_create_dataset_rejects_bad_bodies(api, world, body):
    body = {**body, **({"team_id": world.team_a} if body.get("team_id") == 1 else {})}
    response = api("definer", "POST", "/api/datasets", json=body)
    assert response.status_code == 422 and err(response)["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    ("login", "status", "code"),
    [
        ("admin", 403, "FORBIDDEN"),  # 관리자라도 팀 소속 정의 담당자가 아니면 거부
        ("entry", 403, "FORBIDDEN"),
        ("other", 403, "FORBIDDEN"),  # 다른 팀 구성원
        ("viewer", 403, "FORBIDDEN"),
        ("inactive", 403, "USER_INACTIVE"),
        (None, 401, "UNAUTHENTICATED"),
    ],
)
def test_create_dataset_requires_definer_of_that_team(api, db, world, login, status, code):
    response = api(
        login,
        "POST",
        "/api/datasets",
        json={"team_id": world.team_a, "name": "x", "date_unit": "day"},
    )
    assert (response.status_code, err(response)["code"]) == (status, code)
    assert db.rows(datasets) == []
    assert sa.inspect(db.engine).get_table_names(schema=DYNAMIC_SCHEMA) == []


def test_definer_of_another_team_cannot_create_here_and_unknown_team_is_403(api, world):
    other_team = api(
        "definer",
        "POST",
        "/api/datasets",
        json={"team_id": world.team_b, "name": "x", "date_unit": "day"},
    )
    assert other_team.status_code == 403
    unknown = api(
        "definer",
        "POST",
        "/api/datasets",
        json={"team_id": 99999, "name": "x", "date_unit": "day"},
    )
    assert unknown.status_code == 403


def test_admin_who_is_also_a_definer_member_can_create(api, db, world):
    db.add_member(world.team_a, world.ids["admin"], "definer")
    assert make_dataset(api, world, who="admin")["created_by"]["id"] == world.ids["admin"]


def test_definer_can_also_enter_so_permissions_report_both(api, world):
    assert make_dataset(api, world)["permissions"] == {"define": True, "enter": True}


def test_create_rolls_back_registration_when_table_creation_fails_afterwards(
    db, stub_settings, sync, world, monkeypatch
):
    """등록 + 원본 표 생성이 한 트랜잭션이다: 표를 만든 뒤 실패해도 등록 행과 표가 남지 않는다."""
    original = ddl.create_dataset_table

    def create_then_fail(conn, dataset_id):
        original(conn, dataset_id)
        raise RuntimeError("표 생성 직후 실패")

    monkeypatch.setattr(ddl, "create_dataset_table", create_then_fail)
    with custom_client(db, stub_settings, sync, quiet=True) as call:
        response = call(
            "definer",
            "POST",
            "/api/datasets",
            json={"team_id": world.team_a, "name": "x", "date_unit": "day"},
        )
        assert response.status_code == 500 and err(response)["code"] == "INTERNAL_ERROR"
        assert_no_dataset_leftovers(db)
        assert sync.dataset_requests == []


def test_create_rolls_back_registration_when_table_verification_fails(
    db, stub_settings, sync, world, monkeypatch
):
    """반대 방향: 등록(INSERT) 뒤 표 생성이 실패하면 등록 행도 사라진다(둘이 함께 롤백)."""

    def fail(conn, dataset_id):
        raise ddl.DdlVerificationError("표를 다시 읽지 못했다")

    monkeypatch.setattr(ddl, "create_dataset_table", fail)
    with custom_client(db, stub_settings, sync, quiet=True) as call:
        response = call(
            "definer",
            "POST",
            "/api/datasets",
            json={"team_id": world.team_a, "name": "x", "date_unit": "day"},
        )
        assert response.status_code == 500
        assert db.rows(datasets) == []


def test_definition_hook_runs_inside_the_creation_transaction(db, stub_settings, sync, world):
    seen: list[tuple[int, bool]] = []

    def hook(session, dataset_id):
        row = session.execute(sa.select(datasets.c.id).where(datasets.c.id == dataset_id)).first()
        seen.append((dataset_id, row is not None))  # 아직 커밋 전이지만 같은 트랜잭션이라 보인다

    hooks = DefinitionHooks()
    hooks.register(hook)
    with custom_client(db, stub_settings, sync, hooks=hooks) as call:
        created = call(
            "definer",
            "POST",
            "/api/datasets",
            json={"team_id": world.team_a, "name": "x", "date_unit": "day"},
        ).json()
    assert seen == [(created["id"], True)]


def test_failing_hook_rolls_back_the_whole_creation(db, stub_settings, sync, world):
    def hook(session, dataset_id):
        raise AppError(ErrorCode.FORMULA_INVALID, "수식을 확인하세요.", status_code=422)

    hooks = DefinitionHooks()
    hooks.register(hook)
    with custom_client(db, stub_settings, sync, hooks=hooks) as call:
        response = call(
            "definer",
            "POST",
            "/api/datasets",
            json={"team_id": world.team_a, "name": "x", "date_unit": "day"},
        )
        assert response.status_code == 422 and err(response)["code"] == "FORMULA_INVALID"
        assert_no_dataset_leftovers(db)
        assert sync.dataset_requests == []


# --- B1 목록, B3 상세 ----


def test_list_orders_my_teams_first_then_team_name_then_dataset_name(api, db, world):
    team_c = db.add_team("team_c", "C팀")
    admin = world.ids["admin"]
    for team, name in (
        (team_c, "가"),
        (world.team_b, "나"),
        (world.team_a, "하"),
        (world.team_a, "가"),
        (world.team_b, "가"),
    ):
        db.add_dataset(team, name, admin)

    def listing(login, **params):
        body = api(login, "GET", "/api/datasets", params=params).json()
        return [(d["team_id"], d["name"]) for d in body["items"]]

    # definer는 A팀 소속: A팀(가, 하) 먼저, 그다음 B팀(가, 나), C팀(가)
    assert listing("definer") == [
        (world.team_a, "가"),
        (world.team_a, "하"),
        (world.team_b, "가"),
        (world.team_b, "나"),
        (team_c, "가"),
    ]
    # other는 B팀 소속: B팀 먼저, 그다음 A팀, C팀
    assert [t for t, _ in listing("other")] == [world.team_b] * 2 + [world.team_a] * 2 + [team_c]
    # 소속이 없으면 팀 이름 순서(A팀, B팀, C팀)
    assert [t for t, _ in listing("viewer")] == [world.team_a] * 2 + [world.team_b] * 2 + [team_c]
    assert [t for t, _ in listing("admin")] == [world.team_a] * 2 + [world.team_b] * 2 + [team_c]


def test_list_shape_filter_and_paging(api, db, world):
    admin = world.ids["admin"]
    ids = [db.add_dataset(world.team_a, f"데이터{n}", admin) for n in range(5)]
    db.add_dataset(world.team_b, "다른 팀", admin)
    body = api("viewer", "GET", "/api/datasets").json()
    assert set(body) == {"items", "total", "limit", "offset"}
    assert (body["total"], body["limit"], body["offset"]) == (6, 50, 0)
    assert set(body["items"][0]) == {
        "id",
        "team_id",
        "name",
        "date_unit",
        "base_date_column_id",
        "status",
        "def_version",
        "created_by",
        "created_at",
    }
    assert "columns" not in body["items"][0] and "def_hash" not in body["items"][0]
    only_a = api("viewer", "GET", "/api/datasets", params={"team_id": world.team_a}).json()
    assert only_a["total"] == 5 and [d["id"] for d in only_a["items"]] == ids
    page = api(
        "viewer", "GET", "/api/datasets", params={"team_id": world.team_a, "limit": 2, "offset": 3}
    )
    assert [d["id"] for d in page.json()["items"]] == ids[3:]
    assert page.json()["total"] == 5


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"offset": -1}, {"team_id": "x"}])
def test_list_rejects_bad_query(api, world, params):
    assert api("viewer", "GET", "/api/datasets", params=params).status_code == 422


def test_list_and_detail_are_readable_by_every_active_user_but_not_anonymous(api, db, world):
    dataset_id = db.add_dataset(world.team_a, "읽기", world.ids["admin"])
    for login in ("admin", "definer", "entry", "other", "viewer"):
        assert api(login, "GET", "/api/datasets").status_code == 200, login
        assert api(login, "GET", f"/api/datasets/{dataset_id}").status_code == 200, login
    assert api("inactive", "GET", "/api/datasets").status_code == 403
    assert api(None, "GET", f"/api/datasets/{dataset_id}").status_code == 401


def test_detail_has_columns_in_order_team_and_my_permissions(api, db, world):
    dataset = make_dataset(api, world)
    third = make_column(api, dataset, "셋째", "text", position=5)
    first = make_column(api, dataset, "첫째", "number", position=1)
    second = make_column(api, dataset, "둘째", "date", position=1)  # 같은 position은 번호 순서
    body = api("viewer", "GET", f"/api/datasets/{dataset['id']}").json()
    assert [c["id"] for c in body["columns"]] == [first["id"], second["id"], third["id"]]
    assert set(body["columns"][0]) == {
        "id",
        "display_name",
        "type",
        "kind",
        "required",
        "rules",
        "tag",
        "position",
    }
    assert body["team"] == {"id": world.team_a, "code": "team_a", "name": "A팀"}
    expected = {
        "definer": {"define": True, "enter": True},
        "entry": {"define": False, "enter": True},
        "other": {"define": False, "enter": False},
        "viewer": {"define": False, "enter": False},
        "admin": {"define": False, "enter": False},
    }
    for login, permissions in expected.items():
        got = api(login, "GET", f"/api/datasets/{dataset['id']}").json()["permissions"]
        assert got == permissions, login


def test_detail_unknown_dataset_is_404_and_bad_path_is_422(api, world):
    assert err(api("viewer", "GET", "/api/datasets/99999"))["code"] == "NOT_FOUND"
    assert api("viewer", "GET", "/api/datasets/abc").status_code == 422


# --- B5 열 추가 ----


COLUMN_SQL_TYPES = {
    "text": "text",
    "number": "numeric",
    "date": "date",
    "boolean": "boolean",
    "choice": "text",
}


@pytest.mark.parametrize("column_type", list(COLUMN_SQL_TYPES))
def test_add_column_creates_definition_and_source_column(api, db, world, column_type):
    dataset = make_dataset(api, world)
    extra = {"rules": {"options": ["가", "나"]}} if column_type == "choice" else {}
    response = api(
        "definer",
        "POST",
        f"/api/datasets/{dataset['id']}/columns",
        json={
            "expected_version": 1,
            "display_name": "열",
            "type": column_type,
            "required": True,
            **extra,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"column", "def_version"} and body["def_version"] == 2
    column = body["column"]
    assert column["type"] == column_type and column["kind"] == "raw"
    assert column["required"] is True and column["tag"] is None and column["position"] == 0
    assert column["rules"] == (extra.get("rules") if extra else None)
    # 원본 표에 `c_<번호>` 열이 생겼다(표시 이름이 아니라 번호 이름).
    assert ds_columns(db, dataset["id"])[f"c_{column['id']}"] == COLUMN_SQL_TYPES[column_type]
    assert dataset_row(db, dataset["id"])["def_version"] == 2


def test_add_column_positions_default_to_the_end_and_versions_increase(api, world):
    dataset = make_dataset(api, world)
    a = make_column(api, dataset, "가", "text")
    b = make_column(api, dataset, "나", "text")
    c = make_column(api, dataset, "다", "text", position=10)
    d = make_column(api, dataset, "라", "text")
    assert [a["position"], b["position"], c["position"], d["position"]] == [0, 1, 10, 11]
    assert dataset["def_version"] == 5


def test_add_column_updates_the_definition_hash(api, db, world):
    dataset = make_dataset(api, world)
    before = dataset_row(db, dataset["id"])["def_hash"]
    make_column(api, dataset, "매출", "number")
    after = dataset_row(db, dataset["id"])["def_hash"]
    assert re.fullmatch("[0-9a-f]{64}", before) and re.fullmatch("[0-9a-f]{64}", after)
    assert after != before


def test_definition_hook_hash_is_stored_as_def_hash(db, stub_settings, sync, world):
    """훅이 돌려준 해시가 `def_hash`가 된다(등록 때와 정의 변경 때 모두)."""
    hooks = DefinitionHooks()
    hooks.register(lambda session, dataset_id: "h" * 64)
    with custom_client(db, stub_settings, sync, hooks=hooks) as call:
        created = call(
            "definer",
            "POST",
            "/api/datasets",
            json={"team_id": world.team_a, "name": "훅 해시", "date_unit": "day"},
        ).json()
        assert dataset_row(db, created["id"])["def_hash"] == "h" * 64
        column = call(
            "definer",
            "POST",
            f"/api/datasets/{created['id']}/columns",
            json={"expected_version": 1, "display_name": "열", "type": "text"},
        )
        assert column.status_code == 201
        assert dataset_row(db, created["id"])["def_hash"] == "h" * 64


def test_without_a_hash_from_the_hooks_the_structure_hash_is_used(db, stub_settings, sync, world):
    """훅이 없거나 해시를 주지 않으면 정의 구조 해시를 쓴다."""
    with custom_client(db, stub_settings, sync, hooks=DefinitionHooks()) as call:
        created = call(
            "definer",
            "POST",
            "/api/datasets",
            json={"team_id": world.team_a, "name": "훅 없음", "date_unit": "day"},
        ).json()
        assert dataset_row(db, created["id"])["def_hash"] == structure_hash([])


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("합계[원]", "BAD_FORMAT"),
        ("합계]", "BAD_FORMAT"),
        ('"따옴표"', "BAD_FORMAT"),
        ("줄\n바꿈", "BAD_FORMAT"),
        ("team", "RESERVED"),
        ("팀", "RESERVED"),
        ("row_id", "RESERVED"),
        ("행 번호", "RESERVED"),
        ("TEAM", "RESERVED"),
        ("가" * 101, "TOO_LONG"),
        ("", "REQUIRED"),
        ("   ", "REQUIRED"),
    ],
)
def test_add_column_name_rules(api, db, world, name, code):
    dataset = make_dataset(api, world)
    response = api(
        "definer",
        "POST",
        f"/api/datasets/{dataset['id']}/columns",
        json={"expected_version": 1, "display_name": name, "type": "text"},
    )
    assert response.status_code == 422
    assert field_codes(response) == {"display_name": code}
    assert db.rows(dataset_columns) == []
    assert list(ds_columns(db, dataset["id"])) == ["row_id"]


def test_add_column_name_boundaries_and_normalization(api, world):
    dataset = make_dataset(api, world)
    assert make_column(api, dataset, "가" * 100, "text")["display_name"] == "가" * 100
    assert make_column(api, dataset, "  한  ", "text")["display_name"] == "한"
    assert (
        make_column(api, dataset, "teams", "text")["display_name"] == "teams"
    )  # 예약어는 정확히 일치만


def test_add_column_duplicate_name_is_409_within_the_dataset_only(api, db, world):
    first = make_dataset(api, world, name="하나")
    second = make_dataset(api, world, name="둘")
    make_column(api, first, "매출", "number")
    response = api(
        "definer",
        "POST",
        f"/api/datasets/{first['id']}/columns",
        json={"expected_version": first["def_version"], "display_name": "매출", "type": "text"},
    )
    assert response.status_code == 409
    assert err(response)["code"] == "ALREADY_EXISTS" and err(response)["details"] == {
        "field": "display_name"
    }
    assert len(db.rows(dataset_columns)) == 1
    make_column(api, second, "매출", "number")  # 다른 데이터셋은 같은 이름 가능


def test_add_column_rules_are_validated_and_normalized(api, world):
    dataset = make_dataset(api, world)
    number = make_column(
        api, dataset, "수량", "number", rules={"min": 0, "max": "100.50", "decimals": 2}
    )
    assert number["rules"] == {"min": "0", "max": "100.5", "decimals": 2}
    text = make_column(api, dataset, "비고", "text", rules={"max_length": 30})
    assert text["rules"] == {"max_length": 30}
    day = make_column(
        api, dataset, "날짜", "date", rules={"min": "2020-01-01", "max": "2030-12-31"}
    )
    assert day["rules"] == {"min": "2020-01-01", "max": "2030-12-31"}
    choice = make_column(api, dataset, "지역", "choice", rules={"options": [" 서울 ", "부산"]})
    assert choice["rules"] == {"options": ["서울", "부산"]}
    plain = make_column(api, dataset, "그냥", "boolean", rules={})
    assert plain["rules"] is None


@pytest.mark.parametrize(
    "raw_rules",
    [
        '{"min": 1.5}',
        '{"min": 0.1234567890123456789}',
        '{"max": 12345678901234567890.123}',
        '{"max": 1e400}',
        '{"min": 1' + "0" * 5000 + "}",  # 5001자리 JSON 정수: 500이 아니라 422
    ],
    ids=["float", "float-19-digits", "float-large", "float-overflow", "int-5001-digits"],
)
def test_json_float_and_huge_integer_rules_are_rejected_not_500(api, world, raw_rules):
    dataset = make_dataset(api, world)
    body = (
        '{"expected_version": 1, "display_name": "수량", "type": "number", "rules": '
        + raw_rules
        + "}"
    )
    response = api(
        "definer",
        "POST",
        f"/api/datasets/{dataset['id']}/columns",
        content=body,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422, response.text
    assert err(response)["code"] == "VALIDATION_ERROR"


def test_json_integer_rules_are_accepted(api, world):
    dataset = make_dataset(api, world)
    column = make_column(api, dataset, "수량", "number", rules={"min": 1000, "max": 2000})
    assert column["rules"] == {"min": "1000", "max": "2000"}


@pytest.mark.parametrize(
    ("column_type", "rules", "field", "code"),
    [
        ("number", {"min": "abc"}, "rules.min", "BAD_FORMAT"),
        ("number", {"min": 5, "max": 4}, "rules.max", "OUT_OF_RANGE"),
        ("number", {"decimals": 99}, "rules.decimals", "OUT_OF_RANGE"),
        ("number", {"max_length": 3}, "rules.max_length", "BAD_FORMAT"),
        ("text", {"max_length": 0}, "rules.max_length", "OUT_OF_RANGE"),
        ("date", {"min": "2020-13-40"}, "rules.min", "BAD_FORMAT"),
        ("date", {"min": "2021-01-01", "max": "2020-01-01"}, "rules.max", "OUT_OF_RANGE"),
        ("choice", None, "rules.options", "REQUIRED"),
        ("choice", {"options": []}, "rules.options", "REQUIRED"),
        ("choice", {"options": ["a", "a"]}, "rules.options.1", "BAD_FORMAT"),
        ("boolean", {"min": 1}, "rules.min", "BAD_FORMAT"),
    ],
)
def test_add_column_invalid_rules_are_422_and_change_nothing(
    api, db, world, column_type, rules, field, code
):
    dataset = make_dataset(api, world)
    response = api(
        "definer",
        "POST",
        f"/api/datasets/{dataset['id']}/columns",
        json={
            "expected_version": 1,
            "display_name": "열",
            "type": column_type,
            "rules": rules,
        },
    )
    assert response.status_code == 422
    assert field_codes(response).get(field) == code
    assert db.rows(dataset_columns) == [] and dataset_row(db, dataset["id"])["def_version"] == 1


def test_add_column_tag_rules(api, world):
    dataset = make_dataset(api, world)
    assert make_column(api, dataset, "매출", "number", tag=" 수익 ")["tag"] == "수익"
    assert make_column(api, dataset, "공백", "number", tag="  ")["tag"] is None
    for tag, code in (("x" * 51, "TOO_LONG"), ('a"b', "BAD_FORMAT")):
        response = api(
            "definer",
            "POST",
            f"/api/datasets/{dataset['id']}/columns",
            json={
                "expected_version": dataset["def_version"],
                "display_name": f"열{code}",
                "type": "number",
                "tag": tag,
            },
        )
        assert field_codes(response) == {"tag": code}
    on_text = api(
        "definer",
        "POST",
        f"/api/datasets/{dataset['id']}/columns",
        json={
            "expected_version": dataset["def_version"],
            "display_name": "글자",
            "type": "text",
            "tag": "수익",
        },
    )
    assert field_codes(on_text) == {"tag": "BAD_FORMAT"}  # 구분 태그는 숫자 열에만


@pytest.mark.parametrize(
    "extra",
    [
        {"type": "formula"},
        {"type": "reference"},
        {"type": "NUMBER"},
        {"kind": "formula"},
        {"required": "yes"},
        {"position": -1},
        {"position": 1.5},
        {"unknown": 1},
        {"expected_version": 0},
        {"expected_version": "1"},
        {"expected_version": None},
    ],
)
def test_add_column_rejects_bad_bodies(api, db, world, extra):
    dataset = make_dataset(api, world)
    body = {"expected_version": 1, "display_name": "열", "type": "text", **extra}
    response = api("definer", "POST", f"/api/datasets/{dataset['id']}/columns", json=body)
    assert response.status_code == 422 and err(response)["code"] == "VALIDATION_ERROR"
    assert db.rows(dataset_columns) == []


def test_add_column_requires_expected_version(api, world):
    dataset = make_dataset(api, world)
    response = api(
        "definer",
        "POST",
        f"/api/datasets/{dataset['id']}/columns",
        json={"display_name": "열", "type": "text"},
    )
    assert response.status_code == 422
    assert field_codes(response) == {"expected_version": "REQUIRED"}


def test_add_column_with_stale_version_is_409_with_current_version(api, db, world):
    dataset = make_dataset(api, world)
    make_column(api, dataset, "하나", "text")  # 버전 2
    response = api(
        "definer",
        "POST",
        f"/api/datasets/{dataset['id']}/columns",
        json={"expected_version": 1, "display_name": "둘", "type": "text"},
    )
    assert response.status_code == 409
    assert err(response)["code"] == "DEFINITION_VERSION_MISMATCH"
    assert err(response)["details"] == {"current_version": 2}
    assert len(db.rows(dataset_columns)) == 1
    assert len(ds_columns(db, dataset["id"])) == 2  # row_id + c_1
    # 적중한 버전으로 다시 하면 된다.
    make_column(api, dataset, "둘", "text")


def test_add_column_unknown_dataset_is_404(api, world):
    response = api(
        "definer",
        "POST",
        "/api/datasets/99999/columns",
        json={"expected_version": 1, "display_name": "열", "type": "text"},
    )
    assert err(response)["code"] == "NOT_FOUND" and response.status_code == 404


@pytest.mark.parametrize(
    ("login", "status", "code"),
    [
        ("admin", 403, "FORBIDDEN"),
        ("entry", 403, "FORBIDDEN"),
        ("other", 403, "FORBIDDEN"),
        ("viewer", 403, "FORBIDDEN"),
        ("inactive", 403, "USER_INACTIVE"),
        (None, 401, "UNAUTHENTICATED"),
    ],
)
def test_column_and_dataset_edits_require_the_datasets_team_definer(
    api, db, world, login, status, code
):
    dataset = make_dataset(api, world)
    column = make_column(api, dataset, "열", "text")
    version = dataset["def_version"]
    attempts = [
        (
            "PATCH",
            f"/api/datasets/{dataset['id']}",
            {"expected_version": version, "name": "새 이름"},
        ),
        (
            "POST",
            f"/api/datasets/{dataset['id']}/columns",
            {"expected_version": version, "display_name": "새 열", "type": "text"},
        ),
        (
            "PATCH",
            f"/api/datasets/{dataset['id']}/columns/{column['id']}",
            {"expected_version": version, "display_name": "새 이름"},
        ),
    ]
    for method, path, body in attempts:
        response = api(login, method, path, json=body)
        assert (response.status_code, err(response)["code"]) == (status, code), path
    assert dataset_row(db, dataset["id"])["name"] == "월별 매출"
    assert dataset_row(db, dataset["id"])["def_version"] == version
    assert len(db.rows(dataset_columns)) == 1


def test_permission_is_checked_before_body_validation_for_edits(api, world):
    dataset = make_dataset(api, world)
    response = api("viewer", "POST", f"/api/datasets/{dataset['id']}/columns", json={"x": 1})
    assert response.status_code == 403
    assert (
        api("viewer", "PATCH", f"/api/datasets/{dataset['id']}", json={"x": 1}).status_code == 403
    )
    assert api("viewer", "PATCH", "/api/datasets/99999", json={"x": 1}).status_code == 404


def test_add_column_requests_sync_once_and_only_on_success(api, sync, world):
    dataset = make_dataset(api, world)
    make_column(api, dataset, "열", "text")
    assert sync.dataset_requests == [dataset["id"]] * 2  # 만들기 + 열 추가
    api(
        "definer",
        "POST",
        f"/api/datasets/{dataset['id']}/columns",
        json={"expected_version": 1, "display_name": "충돌", "type": "text"},
    )
    assert len(sync.dataset_requests) == 2


def test_add_column_rolls_back_definition_when_source_column_fails(
    db, stub_settings, sync, world, monkeypatch
):
    dataset = db.add_dataset(world.team_a, "정의", world.ids["definer"])

    def fail(conn, dataset_id, column_id, column_type):
        raise RuntimeError("열 추가 실패")

    monkeypatch.setattr(ddl, "add_raw_column", fail)
    with custom_client(db, stub_settings, sync, quiet=True) as call:
        response = call(
            "definer",
            "POST",
            f"/api/datasets/{dataset}/columns",
            json={"expected_version": 1, "display_name": "열", "type": "text"},
        )
        assert response.status_code == 500
        assert db.rows(dataset_columns) == []
        assert dataset_row(db, dataset)["def_version"] == 1
        assert sync.dataset_requests == []


def test_definition_hook_sees_the_new_column_and_failure_rolls_everything_back(
    db, stub_settings, sync, world
):
    dataset = db.add_dataset(world.team_a, "정의", world.ids["definer"])
    seen: list[list[int]] = []
    fail = {"on": False}

    def hook(session, dataset_id):
        ids = session.execute(
            sa.select(dataset_columns.c.id).where(dataset_columns.c.dataset_id == dataset_id)
        ).scalars()
        seen.append(sorted(ids))
        if fail["on"]:
            raise AppError(ErrorCode.FORMULA_CIRCULAR, "순환 참조입니다.", status_code=422)

    hooks = DefinitionHooks()
    hooks.register(hook)
    with custom_client(db, stub_settings, sync, hooks=hooks) as call:
        url = f"/api/datasets/{dataset}/columns"
        first = {"expected_version": 1, "display_name": "a", "type": "text"}
        ok = call("definer", "POST", url, json=first)
        assert ok.status_code == 201
        first_id = ok.json()["column"]["id"]
        assert seen == [[first_id]]  # 훅은 새 열 번호가 있는 상태에서 불린다
        fail["on"] = True
        second = {"expected_version": 2, "display_name": "b", "type": "text"}
        bad = call("definer", "POST", url, json=second)
        assert bad.status_code == 422 and err(bad)["code"] == "FORMULA_CIRCULAR"
        assert [r["id"] for r in db.rows(dataset_columns)] == [first_id]  # 두 번째 열은 롤백
        assert len(ds_columns(db, dataset)) == 2  # row_id + 첫 열
        assert dataset_row(db, dataset)["def_version"] == 2


# --- B6 열 수정 ----


def test_update_column_changes_only_the_sent_fields(api, db, world):
    dataset = make_dataset(api, world)
    column = make_column(api, dataset, "매출", "number", rules={"min": 0}, tag="수익")
    path = f"/api/datasets/{dataset['id']}/columns/{column['id']}"
    response = api(
        "definer",
        "PATCH",
        path,
        json={
            "expected_version": dataset["def_version"],
            "display_name": "총매출",
            "required": True,
            "rules": {"max": 100},
            "position": 7,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["def_version"] == dataset["def_version"] + 1
    assert body["column"] == {
        "id": column["id"],
        "display_name": "총매출",
        "type": "number",
        "kind": "raw",
        "required": True,
        "rules": {"max": "100"},  # 보낸 규칙 전체로 바뀐다(min은 사라짐)
        "tag": "수익",  # 보내지 않은 것은 그대로
        "position": 7,
    }
    # 이름을 바꿔도 원본 표의 열 이름(c_<번호>)은 그대로이고 뷰 재생성은 없다.
    assert f"c_{column['id']}" in ds_columns(db, dataset["id"])


def test_update_column_no_effective_change_keeps_the_version_and_requests_no_sync(api, sync, world):
    dataset = make_dataset(api, world)
    column = make_column(api, dataset, "매출", "number", tag="수익", position=3)
    sync.dataset_requests.clear()
    version = dataset["def_version"]
    response = api(
        "definer",
        "PATCH",
        f"/api/datasets/{dataset['id']}/columns/{column['id']}",
        json={
            "expected_version": version,
            "display_name": "매출",
            "required": False,
            "tag": "수익",
            "position": 3,
            "type": "number",  # 현재와 같은 type·kind는 무시한다
            "kind": "raw",
        },
    )
    assert response.status_code == 200 and response.json()["def_version"] == version
    empty = api(
        "definer",
        "PATCH",
        f"/api/datasets/{dataset['id']}/columns/{column['id']}",
        json={"expected_version": version},
    )
    assert empty.status_code == 200 and empty.json()["def_version"] == version
    assert sync.dataset_requests == []


@pytest.mark.parametrize(
    "body", [{"type": "text"}, {"kind": "formula"}, {"type": "date", "kind": "raw"}]
)
def test_update_column_type_and_kind_are_locked(api, db, world, body):
    dataset = make_dataset(api, world)
    column = make_column(api, dataset, "매출", "number")
    response = api(
        "definer",
        "PATCH",
        f"/api/datasets/{dataset['id']}/columns/{column['id']}",
        json={"expected_version": dataset["def_version"], "display_name": "다른 이름", **body},
    )
    assert response.status_code == 422 and err(response)["code"] == "COLUMN_LOCKED"
    row = next(r for r in db.rows(dataset_columns) if r["id"] == column["id"])
    assert (row["type"], row["kind"], row["display_name"]) == ("number", "raw", "매출")
    assert dataset_row(db, dataset["id"])["def_version"] == dataset["def_version"]


def test_update_column_name_conflict_and_own_name(api, db, world):
    dataset = make_dataset(api, world)
    a = make_column(api, dataset, "가", "text")
    b = make_column(api, dataset, "나", "text")
    path = f"/api/datasets/{dataset['id']}/columns/{b['id']}"
    clash = api(
        "definer",
        "PATCH",
        path,
        json={"expected_version": dataset["def_version"], "display_name": "가"},
    )
    assert clash.status_code == 409 and err(clash)["details"] == {"field": "display_name"}
    same = api(
        "definer",
        "PATCH",
        path,
        json={"expected_version": dataset["def_version"], "display_name": "나"},
    )
    assert same.status_code == 200 and same.json()["def_version"] == dataset["def_version"]
    assert a["id"] != b["id"]


@pytest.mark.parametrize(
    ("name", "code"),
    [("team", "RESERVED"), ("합계[원]", "BAD_FORMAT"), ("가" * 101, "TOO_LONG"), ("", "REQUIRED")],
)
def test_update_column_name_rules(api, world, name, code):
    dataset = make_dataset(api, world)
    column = make_column(api, dataset, "열", "text")
    response = api(
        "definer",
        "PATCH",
        f"/api/datasets/{dataset['id']}/columns/{column['id']}",
        json={"expected_version": dataset["def_version"], "display_name": name},
    )
    assert response.status_code == 422 and field_codes(response) == {"display_name": code}


def test_update_column_rules_and_tag_validation(api, world):
    dataset = make_dataset(api, world)
    number = make_column(api, dataset, "수량", "number", rules={"min": 0}, tag="수익")
    text = make_column(api, dataset, "비고", "text")
    choice = make_column(api, dataset, "지역", "choice", rules={"options": ["가"]})
    base = f"/api/datasets/{dataset['id']}/columns"
    current = {"version": dataset["def_version"]}

    def patch(column, **body):
        return api(
            "definer",
            "PATCH",
            f"{base}/{column['id']}",
            json={"expected_version": current["version"], **body},
        )

    assert field_codes(patch(number, rules={"min": 9, "max": 1})) == {"rules.max": "OUT_OF_RANGE"}
    assert field_codes(patch(text, rules={"min": 1})) == {"rules.min": "BAD_FORMAT"}
    assert field_codes(patch(choice, rules=None)) == {"rules.options": "REQUIRED"}
    assert field_codes(patch(text, tag="수익")) == {"tag": "BAD_FORMAT"}
    assert field_codes(patch(number, tag="x" * 51)) == {"tag": "TOO_LONG"}
    # 규칙·태그 지우기: null은 지운다.
    cleared = patch(number, rules=None, tag=None)
    assert cleared.status_code == 200
    assert cleared.json()["column"]["rules"] is None and cleared.json()["column"]["tag"] is None
    current["version"] = cleared.json()["def_version"]
    changed = patch(choice, rules={"options": ["다", "라"]})
    assert changed.json()["column"]["rules"] == {"options": ["다", "라"]}


@pytest.mark.parametrize(
    "body",
    [
        {"unknown": 1},
        {"display_name": 5},
        {"required": "yes"},
        {"position": -1},
        {"expected_version": 0},
        {"base_date_column_id": 1},
    ],
)
def test_update_column_rejects_bad_bodies(api, world, body):
    dataset = make_dataset(api, world)
    column = make_column(api, dataset, "열", "text")
    payload = {"expected_version": dataset["def_version"], **body}
    if "expected_version" in body:
        payload["expected_version"] = body["expected_version"]
    response = api(
        "definer", "PATCH", f"/api/datasets/{dataset['id']}/columns/{column['id']}", json=payload
    )
    assert response.status_code == 422 and err(response)["code"] == "VALIDATION_ERROR"


def test_update_column_not_found_cases(api, db, world):
    dataset = make_dataset(api, world)
    other = make_dataset(api, world, name="다른")
    foreign = make_column(api, other, "다른 데이터셋 열", "text")
    version = dataset["def_version"]
    for column_id in (99999, foreign["id"]):  # 없는 열, 다른 데이터셋의 열
        response = api(
            "definer",
            "PATCH",
            f"/api/datasets/{dataset['id']}/columns/{column_id}",
            json={"expected_version": version, "display_name": "x"},
        )
        assert response.status_code == 404 and err(response)["code"] == "NOT_FOUND"
    assert dataset_row(db, dataset["id"])["def_version"] == version
    assert dataset_row(db, other["id"])["def_version"] == other["def_version"]


def test_update_column_stale_version_is_409(api, world):
    dataset = make_dataset(api, world)
    column = make_column(api, dataset, "열", "text")
    response = api(
        "definer",
        "PATCH",
        f"/api/datasets/{dataset['id']}/columns/{column['id']}",
        json={"expected_version": 1, "display_name": "새"},
    )
    assert response.status_code == 409
    assert err(response)["details"] == {"current_version": dataset["def_version"]}


def test_formula_columns_cannot_be_required_and_only_accept_display_rules(api, db, world):
    dataset = make_dataset(api, world)
    formula_id = db.add_dataset(world.team_a, "계산", world.ids["definer"])
    with db.writer.begin() as conn:
        column_id = conn.execute(
            sa.insert(dataset_columns)
            .values(
                dataset_id=formula_id,
                display_name="계산 열",
                type="number",
                kind="formula",
                position=0,
            )
            .returning(dataset_columns.c.id)
        ).scalar_one()
        # 계산 열에는 저장된 수식이 있어야 한다(없으면 정의 변경 훅이 FORMULA_INVALID로 거부한다).
        conn.execute(
            sa.insert(formulas).values(
                column_id=column_id, expression="1", ast={"t": "num", "v": "1"}, ast_hash="h"
            )
        )
    path = f"/api/datasets/{formula_id}/columns/{column_id}"
    assert dataset["id"] != formula_id
    assert field_codes(
        api("definer", "PATCH", path, json={"expected_version": 1, "required": True})
    ) == {"required": "BAD_FORMAT"}
    assert field_codes(
        api("definer", "PATCH", path, json={"expected_version": 1, "rules": {"min": 1}})
    ) == {"rules.min": "BAD_FORMAT"}  # 계산 열은 표시 형식 키만 받는다(03b 33-2)
    ok = api(
        "definer",
        "PATCH",
        path,
        json={"expected_version": 1, "display_name": "이름 바꿈", "tag": "합계", "position": 3},
    )
    assert ok.status_code == 200
    assert ok.json()["column"]["kind"] == "formula" and ok.json()["column"]["tag"] == "합계"


def test_update_column_runs_hook_once_and_requests_sync(db, stub_settings, sync, world):
    dataset = db.add_dataset(world.team_a, "정의", world.ids["definer"])
    column = db.add_column(dataset, "열", "text")
    calls: list[int] = []
    hooks = DefinitionHooks()
    hooks.register(lambda session, dataset_id: calls.append(dataset_id))
    with custom_client(db, stub_settings, sync, hooks=hooks) as call:
        path = f"/api/datasets/{dataset}/columns/{column}"
        ok = call("definer", "PATCH", path, json={"expected_version": 1, "display_name": "새 열"})
        same = {"expected_version": 2, "display_name": "새 열"}
        no_change = call("definer", "PATCH", path, json=same)
    assert ok.status_code == 200 and ok.json()["def_version"] == 2
    assert no_change.status_code == 200 and no_change.json()["def_version"] == 2
    assert calls == [dataset]  # 바뀐 한 번만
    assert sync.dataset_requests == [dataset]


# --- B4 데이터셋 수정 ----


def test_update_dataset_renames_and_bumps_version(api, db, sync, world):
    dataset = make_dataset(api, world)
    sync.dataset_requests.clear()
    response = api(
        "definer",
        "PATCH",
        f"/api/datasets/{dataset['id']}",
        json={"expected_version": 1, "name": "  새 이름  "},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "새 이름" and body["def_version"] == 2
    assert set(body) >= {"team", "columns", "permissions"}
    assert sync.dataset_requests == [dataset["id"]]
    assert dataset_row(db, dataset["id"])["name"] == "새 이름"


def test_update_dataset_name_conflict_and_same_name_noop(api, sync, world):
    first = make_dataset(api, world, name="하나")
    second = make_dataset(api, world, name="둘")
    clash = api(
        "definer",
        "PATCH",
        f"/api/datasets/{second['id']}",
        json={"expected_version": 1, "name": "하나"},
    )
    assert clash.status_code == 409 and err(clash)["details"] == {"field": "name"}
    sync.dataset_requests.clear()
    same = api(
        "definer",
        "PATCH",
        f"/api/datasets/{first['id']}",
        json={"expected_version": 1, "name": "하나"},
    )
    assert same.status_code == 200 and same.json()["def_version"] == 1
    only_version = api(
        "definer", "PATCH", f"/api/datasets/{first['id']}", json={"expected_version": 1}
    )
    assert only_version.status_code == 200 and only_version.json()["def_version"] == 1
    assert sync.dataset_requests == []


def test_update_dataset_stale_version_is_409(api, world):
    dataset = make_dataset(api, world)
    make_column(api, dataset, "열", "text")
    response = api(
        "definer",
        "PATCH",
        f"/api/datasets/{dataset['id']}",
        json={"expected_version": 1, "name": "x"},
    )
    assert response.status_code == 409
    assert err(response)["code"] == "DEFINITION_VERSION_MISMATCH"
    assert err(response)["details"] == {"current_version": 2}


@pytest.mark.parametrize(
    "body",
    [
        {"name": ""},
        {"name": "가" * 101},
        {"date_unit": "week"},
        {"base_date_column_id": "x"},
        {"base_date_column_id": 1.5},
        {"team_id": 2},
        {"status": "active"},
        {"def_version": 9},
    ],
)
def test_update_dataset_rejects_bad_bodies(api, world, body):
    dataset = make_dataset(api, world)
    response = api(
        "definer", "PATCH", f"/api/datasets/{dataset['id']}", json={"expected_version": 1, **body}
    )
    assert response.status_code == 422 and err(response)["code"] == "VALIDATION_ERROR"


def test_update_dataset_date_unit_changes_only_while_empty(api, db, world):
    dataset = make_dataset(api, world, unit="day")
    changed = api(
        "definer",
        "PATCH",
        f"/api/datasets/{dataset['id']}",
        json={"expected_version": 1, "date_unit": "month"},
    )
    assert changed.status_code == 200 and changed.json()["date_unit"] == "month"
    db.add_rows(dataset["id"], 2)
    refused = api(
        "definer",
        "PATCH",
        f"/api/datasets/{dataset['id']}",
        json={"expected_version": 2, "date_unit": "year"},
    )
    assert refused.status_code == 422 and err(refused)["code"] == "DATASET_HAS_ROWS"
    assert dataset_row(db, dataset["id"])["date_unit"] == "month"
    assert dataset_row(db, dataset["id"])["def_version"] == 2
    # 같은 값이거나 이름만 바꾸는 것은 행이 있어도 된다.
    same = api(
        "definer",
        "PATCH",
        f"/api/datasets/{dataset['id']}",
        json={"expected_version": 2, "date_unit": "month", "name": "행 있음"},
    )
    assert same.status_code == 200 and same.json()["name"] == "행 있음"


def test_set_base_date_column_requires_a_raw_date_column_of_the_same_dataset(api, db, world):
    dataset = make_dataset(api, world)
    number = make_column(api, dataset, "숫자", "number")
    text = make_column(api, dataset, "글자", "text")
    other = make_dataset(api, world, name="다른")
    foreign = make_column(api, other, "날짜", "date")
    formula = db.add_column(dataset["id"], "계산 날짜", "date")
    with (
        db.writer.begin() as conn
    ):  # 계산 열로 바꿔 둔다(kind는 앱 계약상 FU-1에서 직접 만들지 않는다)
        conn.execute(
            sa.update(dataset_columns).where(dataset_columns.c.id == formula).values(kind="formula")
        )
    version = dataset_row(db, dataset["id"])["def_version"]
    for column_id in (number["id"], text["id"], foreign["id"], formula, 99999):
        response = api(
            "definer",
            "PATCH",
            f"/api/datasets/{dataset['id']}",
            json={"expected_version": version, "base_date_column_id": column_id},
        )
        assert response.status_code == 422, column_id
        assert field_codes(response) == {"base_date_column_id": "BAD_FORMAT"}
    assert dataset_row(db, dataset["id"])["base_date_column_id"] is None
    assert dataset_row(db, dataset["id"])["def_version"] == version
    assert db.period_calls == [] or db.kind == "pg"


def test_set_and_clear_base_date_column_applies_the_period_rules(api, db, world):
    dataset = make_dataset(api, world, unit="month")
    column = make_column(api, dataset, "기준일", "date")
    url = f"/api/datasets/{dataset['id']}"
    set_response = api(
        "definer",
        "PATCH",
        url,
        json={"expected_version": dataset["def_version"], "base_date_column_id": column["id"]},
    )
    assert set_response.status_code == 200
    body = set_response.json()
    assert (
        body["base_date_column_id"] == column["id"]
        and body["def_version"] == dataset["def_version"] + 1
    )
    if db.kind == "sqlite":
        assert db.period_calls == [("add:month", dataset["id"], column["id"])]
    else:
        inspector = sa.inspect(db.engine)
        assert [
            c["name"]
            for c in inspector.get_check_constraints(f"ds_{dataset['id']}", schema=DYNAMIC_SCHEMA)
        ] == [f"ck_ds_{dataset['id']}_period"]
        assert any(
            i["name"] == f"ux_ds_{dataset['id']}_period" and i["unique"]
            for i in inspector.get_indexes(f"ds_{dataset['id']}", schema=DYNAMIC_SCHEMA)
        )
        assert not next(
            c
            for c in inspector.get_columns(f"ds_{dataset['id']}", schema=DYNAMIC_SCHEMA)
            if c["name"] == f"c_{column['id']}"
        )["nullable"]
    cleared = api(
        "definer",
        "PATCH",
        url,
        json={"expected_version": body["def_version"], "base_date_column_id": None},
    )
    assert cleared.status_code == 200 and cleared.json()["base_date_column_id"] is None
    if db.kind == "sqlite":
        assert db.period_calls[-1] == ("drop", dataset["id"], column["id"])
    else:
        inspector = sa.inspect(db.engine)
        assert inspector.get_check_constraints(f"ds_{dataset['id']}", schema=DYNAMIC_SCHEMA) == []
        assert next(
            c
            for c in inspector.get_columns(f"ds_{dataset['id']}", schema=DYNAMIC_SCHEMA)
            if c["name"] == f"c_{column['id']}"
        )["nullable"]


def test_base_date_column_cannot_change_when_rows_exist(api, db, world):
    dataset = make_dataset(api, world)
    first = make_column(api, dataset, "기준일", "date")
    second = make_column(api, dataset, "다른 날짜", "date")
    url = f"/api/datasets/{dataset['id']}"
    ok = api(
        "definer",
        "PATCH",
        url,
        json={"expected_version": dataset["def_version"], "base_date_column_id": first["id"]},
    )
    version = ok.json()["def_version"]
    db.add_rows(dataset["id"], 1) if db.kind == "sqlite" else None
    if db.kind == "pg":
        with db.engine.begin() as conn:
            table = sa.table(
                f"ds_{dataset['id']}", sa.column("c_" + str(first["id"])), schema=DYNAMIC_SCHEMA
            )
            import datetime

            conn.execute(sa.insert(table).values({f"c_{first['id']}": datetime.date(2026, 1, 1)}))
    for value in (second["id"], None):
        response = api(
            "definer",
            "PATCH",
            url,
            json={"expected_version": version, "base_date_column_id": value},
        )
        assert response.status_code == 422 and err(response)["code"] == "DATASET_HAS_ROWS"
    same = api(
        "definer",
        "PATCH",
        url,
        json={"expected_version": version, "base_date_column_id": first["id"]},
    )
    assert same.status_code == 200 and same.json()["def_version"] == version
    assert dataset_row(db, dataset["id"])["base_date_column_id"] == first["id"]


@pytest.mark.parametrize(
    ("state", "status", "code"),
    [
        ("23502", 422, "DATASET_HAS_ROWS"),  # NOT NULL 변경이 기존 NULL 값 때문에 실패
        ("23514", 422, "DATASET_HAS_ROWS"),  # 기간 첫날 CHECK가 기존 값 때문에 실패
        ("23505", 422, "DATASET_HAS_ROWS"),  # 유일 인덱스가 기존 중복 때문에 실패
        ("55P03", 503, "DEFINITION_BUSY"),  # 표 잠금 대기 초과(읽기 중인 ALTER)
        ("40P01", 503, "DEFINITION_BUSY"),
        ("XX000", 500, "INTERNAL_ERROR"),  # 알 수 없는 DB 오류는 그대로 내부 오류
    ],
)
def test_period_rule_ddl_failures_are_mapped_not_leaked(
    api, db, world, monkeypatch, state, status, code
):
    """잠금 아래에서 행이 0개임을 확인하므로 일어나지 않아야 하지만, 규칙 DDL이 값 때문에 실패하면
    `DATASET_HAS_ROWS`(422), 락 대기 초과·교착이면 `DEFINITION_BUSY`(503)로 답한다."""
    from sqlalchemy.exc import DBAPIError

    dataset = make_dataset(api, world)
    column = make_column(api, dataset, "기준일", "date")

    def failing(conn, dataset_id, column_id, unit):
        raise DBAPIError("stmt", {}, Exception({"C": state}))

    monkeypatch.setattr(ddl, "add_period_rules", failing)
    response = api(
        "definer",
        "PATCH",
        f"/api/datasets/{dataset['id']}",
        json={"expected_version": dataset["def_version"], "base_date_column_id": column["id"]},
    )
    assert (response.status_code, err(response)["code"]) == (status, code)
    assert dataset_row(db, dataset["id"])["base_date_column_id"] is None  # 롤백됨
    assert dataset_row(db, dataset["id"])["def_version"] == dataset["def_version"]


def test_changing_base_column_or_unit_replaces_the_period_rules(api, db, world):
    dataset = make_dataset(api, world, unit="day")
    first = make_column(api, dataset, "기준일", "date")
    second = make_column(api, dataset, "다른 날짜", "date")
    url = f"/api/datasets/{dataset['id']}"

    def patch(**body):
        response = api(
            "definer", "PATCH", url, json={"expected_version": dataset["def_version"], **body}
        )
        assert response.status_code == 200, response.text
        dataset["def_version"] = response.json()["def_version"]

    patch(base_date_column_id=first["id"])
    patch(base_date_column_id=second["id"])  # 첫 열 규칙을 풀고 둘째 열에 건다
    patch(date_unit="year")  # 단위가 바뀌면 같은 열의 규칙을 다시 건다
    row = dataset_row(db, dataset["id"])
    assert row["base_date_column_id"] == second["id"] and row["date_unit"] == "year"
    if db.kind == "sqlite":
        assert db.period_calls == [
            ("add:day", dataset["id"], first["id"]),
            ("drop", dataset["id"], first["id"]),
            ("add:day", dataset["id"], second["id"]),
            ("drop", dataset["id"], second["id"]),
            ("add:year", dataset["id"], second["id"]),
        ]
    else:
        inspector = sa.inspect(db.engine)
        indexes = inspector.get_indexes(f"ds_{dataset['id']}", schema=DYNAMIC_SCHEMA)
        assert [
            i["column_names"] for i in indexes if i["name"] == f"ux_ds_{dataset['id']}_period"
        ] == [[f"c_{second['id']}"]]
        columns = {
            c["name"]: c
            for c in inspector.get_columns(f"ds_{dataset['id']}", schema=DYNAMIC_SCHEMA)
        }
        assert (
            columns[f"c_{first['id']}"]["nullable"] and not columns[f"c_{second['id']}"]["nullable"]
        )


def test_date_unit_change_without_base_column_touches_no_period_rules(api, db, world):
    dataset = make_dataset(api, world, unit="day")
    response = api(
        "definer",
        "PATCH",
        f"/api/datasets/{dataset['id']}",
        json={"expected_version": 1, "date_unit": "month"},
    )
    assert response.status_code == 200 and db.period_calls == []


def test_failed_period_rule_rolls_back_the_dataset_update(
    db, stub_settings, sync, world, monkeypatch
):
    dataset = db.add_dataset(world.team_a, "정의", world.ids["definer"])
    column = db.add_column(dataset, "기준일", "date")

    def fail(conn, dataset_id, column_id, unit):
        raise RuntimeError("규칙 적용 실패")

    monkeypatch.setattr(ddl, "add_period_rules", fail)
    body = {"expected_version": 1, "base_date_column_id": column, "name": "바뀐 이름"}
    with custom_client(db, stub_settings, sync, quiet=True) as call:
        response = call("definer", "PATCH", f"/api/datasets/{dataset}", json=body)
        assert response.status_code == 500
        row = dataset_row(db, dataset)
        assert (row["base_date_column_id"], row["name"], row["def_version"]) == (None, "정의", 1)
        assert sync.dataset_requests == []


def test_dataset_hash_is_not_changed_by_a_pure_rename(api, db, world):
    dataset = make_dataset(api, world)
    make_column(api, dataset, "열", "text")
    before = dataset_row(db, dataset["id"])["def_hash"]
    api(
        "definer",
        "PATCH",
        f"/api/datasets/{dataset['id']}",
        json={"expected_version": dataset["def_version"], "name": "이름만"},
    )
    assert dataset_row(db, dataset["id"])["def_hash"] == before


# --- 비활성 팀의 데이터셋 만들기 거부(B2, 03b 19-1 결정 1) ----


def _create_in(api, login, team_id, name="새 데이터셋"):
    return api(
        login,
        "POST",
        "/api/datasets",
        json={"team_id": team_id, "name": name, "date_unit": "day"},
    )


def test_create_in_inactive_team_is_409_target_inactive_and_creates_nothing(api, db, sync, world):
    team_off = db.add_team("team_off", "중지 팀", is_active=False)
    db.add_member(team_off, world.ids["definer"], "definer")
    response = _create_in(api, "definer", team_off)
    assert response.status_code == 409
    body = err(response)
    assert body["code"] == "TARGET_INACTIVE" and body["details"] == {"field": "team"}
    assert body["message"] and "데이터셋" in body["message"]
    assert db.rows(datasets) == [] and sync.dataset_requests == []
    assert sa.inspect(db.engine).get_table_names(schema=DYNAMIC_SCHEMA) == []
    # 활성 팀의 정의 담당자는 계속 만들 수 있다.
    assert _create_in(api, "definer", world.team_a).status_code == 201


def test_inactive_team_permission_is_judged_before_activity(api, db, world):
    team_off = db.add_team("team_off", "중지 팀", is_active=False)
    db.add_member(team_off, world.ids["entry"], "entry")
    # 정의 담당자가 아니면(입력자, 비소속, 관리자) 팀이 비활성이어도 403이다.
    for login in ("entry", "viewer", "admin", "other"):
        assert _create_in(api, login, team_off).status_code == 403, login
    assert _create_in(api, None, team_off).status_code == 401
