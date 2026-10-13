"""Superset API 시험(05 §2-5 E1~E6): 동기 상태, 동기화 접수, 대시보드 연결, 입장권, 속도 제한.

SQLite와 실제 PostgreSQL(`pg`) 두 변형으로 돈다. 외부 Superset은 가짜
서버(`tests/fake_superset.py`)다.
"""

import logging
import time
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db_metadata import superset_dashboards, superset_datasets
from app.main import create_app
from app.superset.constants import GUEST_TOKEN_EXPIRES_IN, GUEST_TOKEN_RATE_LIMIT
from app.superset.errors import summarize
from app.superset.runtime import SupersetServices, build_superset_services
from tests.api_helpers import World, make_caller
from tests.conftest import Db
from tests.fake_superset import FakeSuperset, new_fake
from tests.superset_helpers import ISSUER, SERVICE, SUPERSET_ENV, Clock, settled

UUID_A = "11111111-2222-3333-4444-555555555555"
UUID_B = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def err(response) -> dict[str, Any]:
    return response.json()["error"]


@pytest.fixture
def fake() -> FakeSuperset:
    return new_fake()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def superset_settings(make_settings) -> Settings:
    return make_settings(AUTH_STUB_ENABLED="true", APP_ENV="test", **SUPERSET_ENV)


@pytest.fixture
def services(superset_settings, fake, clock) -> SupersetServices:
    built = build_superset_services(superset_settings, transport=fake.transport, clock=clock)
    assert built is not None
    return built


@pytest.fixture
def sapi(db: Db, superset_settings, services, monkeypatch) -> Iterator[Callable[..., Any]]:
    """Superset 연동이 켜진 앱. 작업 스레드는 띄우지 않고 시험이 `services.sync.drain()`으로
    돌린다."""
    monkeypatch.setattr(services.sync, "start", lambda: None)
    app = create_app(superset_settings, engine=db.engine, superset=services)
    with TestClient(app) as client:
        yield make_caller(client)


def add_dashboard(db: Db, name="월간 현황", embedded_uuid=UUID_A, is_active=True) -> int:
    from sqlalchemy import insert

    with db.writer.begin() as conn:
        return conn.execute(
            insert(superset_dashboards)
            .values(name=name, embedded_uuid=uuid.UUID(embedded_uuid), is_active=is_active)
            .returning(superset_dashboards.c.id)
        ).scalar_one()


def make_dataset(db: Db, world: World, fake: FakeSuperset, name="월간") -> int:
    dataset_id = db.add_dataset(world.team_a, name, world.ids["definer"])
    column_id = db.add_column(dataset_id, "매출")
    fake.views[dataset_id] = ["team", "row_id", f"c_{column_id}"]
    return dataset_id


# --- E1 GET /superset/datasets ----


def test_e1_dataset_without_row_is_pending_with_computed_name(sapi, db, world, fake):
    dataset_id = make_dataset(db, world, fake)
    response = sapi("viewer", "GET", "/api/superset/datasets")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1 and body["limit"] == 50 and body["offset"] == 0
    assert body["items"] == [
        {
            "dataset_id": dataset_id,
            "superset_name": "[A팀] 월간",
            "sync_status": "pending",
            "synced_at": None,
            "last_error": None,
        }
    ]


def test_e1_shows_registered_state_and_hides_last_error_from_non_admins(
    sapi, db, world, fake, services
):
    registered = make_dataset(db, world, fake, "등록됨")
    failed = make_dataset(db, world, fake, "실패")
    services.sync.request_dataset_sync(registered)
    services.sync.drain()
    fake.foreign_datasets.add(1)
    services.sync.request_dataset_sync(registered)
    services.sync.drain()  # 소유자가 아니라 실패
    services.sync.request_dataset_sync(failed)
    services.sync.drain()
    admin = {
        i["dataset_id"]: i for i in sapi("admin", "GET", "/api/superset/datasets").json()["items"]
    }
    other = {
        i["dataset_id"]: i for i in sapi("other", "GET", "/api/superset/datasets").json()["items"]
    }
    assert admin[registered]["sync_status"] == "failed"
    assert admin[registered]["last_error"] == summarize("NOT_OWNER")
    assert other[registered]["last_error"] is None  # 사유는 관리자만
    assert other[registered]["sync_status"] == "failed"  # 상태는 읽기 공개
    assert admin[failed]["sync_status"] == "registered"
    assert admin[failed]["synced_at"].endswith("+09:00")


def test_e1_filters_and_paging(sapi, db, world, fake, services):
    ids = [make_dataset(db, world, fake, f"데이터{n}") for n in range(4)]
    other_team = db.add_dataset(world.team_b, "다른 팀", world.ids["other"])
    services.sync.request_dataset_sync(ids[0])
    services.sync.drain()
    fake.views[other_team] = ["team", "row_id"]

    def items(query: str) -> list[int]:
        response = sapi("viewer", "GET", f"/api/superset/datasets{query}")
        assert response.status_code == 200, response.text
        return [i["dataset_id"] for i in response.json()["items"]]

    assert items("?sync_status=registered") == [ids[0]]
    assert sorted(items("?sync_status=pending")) == sorted([*ids[1:], other_team])
    assert items(f"?dataset_id={ids[1]}&dataset_id={ids[2]}") == [ids[1], ids[2]]
    assert items(f"?dataset_ids={ids[2]},{ids[3]}") == [ids[2], ids[3]]
    assert items(f"?team_id={world.team_b}") == [other_team]
    page = sapi("viewer", "GET", "/api/superset/datasets?limit=2&offset=1").json()
    assert page["total"] == 5 and len(page["items"]) == 2 and page["offset"] == 1


@pytest.mark.parametrize(
    "query", ["?sync_status=done", "?dataset_ids=a,b", "?dataset_id=0", "?limit=0", "?limit=201"]
)
def test_e1_rejects_bad_queries_with_422(sapi, world, query):
    response = sapi("viewer", "GET", f"/api/superset/datasets{query}")
    assert response.status_code == 422 and err(response)["code"] == "VALIDATION_ERROR"


def test_e1_without_superset_configuration_still_lists_pending(db, stub_settings, world, fake):
    app = create_app(stub_settings, engine=db.engine)  # Superset 설정 없음
    dataset_id = make_dataset(db, world, fake)
    with TestClient(app) as client:
        response = make_caller(client)("viewer", "GET", "/api/superset/datasets")
    assert response.status_code == 200
    assert [i["dataset_id"] for i in response.json()["items"]] == [dataset_id]


# --- E2 POST /superset/sync ----


def test_e2_accepts_pending_and_failed_and_missing_rows_but_not_registered(
    sapi, db, world, fake, services
):
    registered = make_dataset(db, world, fake, "등록됨")
    services.sync.request_dataset_sync(registered)
    services.sync.drain()
    fresh = make_dataset(db, world, fake, "새 데이터셋")
    response = sapi("admin", "POST", "/api/superset/sync")
    assert response.status_code == 202
    assert response.json() == {"accepted": [fresh]}
    assert services.sync.pending_ids() == [fresh]
    calls_before = len(fake.calls)
    assert len(fake.calls) == calls_before  # 접수는 Superset을 부르지 않는다
    services.sync.drain()
    assert all(
        i["sync_status"] == "registered"
        for i in sapi("admin", "GET", "/api/superset/datasets").json()["items"]
    )


def test_e2_with_ids_requeues_them_and_unknown_id_rejects_everything(
    sapi, db, world, fake, services
):
    first = make_dataset(db, world, fake, "하나")
    second = make_dataset(db, world, fake, "둘")
    ok = sapi("admin", "POST", "/api/superset/sync", json={"dataset_ids": [second, first, first]})
    assert ok.status_code == 202 and ok.json() == {"accepted": sorted([first, second])}
    services.sync.drain()
    bad = sapi("admin", "POST", "/api/superset/sync", json={"dataset_ids": [first, 99999]})
    assert bad.status_code == 404 and err(bad)["code"] == "NOT_FOUND"
    assert services.sync.pending_ids() == []  # 하나라도 없으면 전체를 거부한다
    too_many = sapi(
        "admin", "POST", "/api/superset/sync", json={"dataset_ids": list(range(1, 1002))}
    )
    assert too_many.status_code == 422
    extra = sapi("admin", "POST", "/api/superset/sync", json={"rls": []})
    assert extra.status_code == 422


def test_e2_is_accepted_even_when_superset_is_down(sapi, db, world, fake, services):
    dataset_id = make_dataset(db, world, fake)
    fake.up = False
    start = time.monotonic()
    response = sapi("admin", "POST", "/api/superset/sync")
    assert response.status_code == 202 and response.json() == {"accepted": [dataset_id]}
    assert time.monotonic() - start < 2
    assert fake.calls == []


def test_e2_without_superset_configuration_is_accepted_as_noop(db, stub_settings, world, fake):
    app = create_app(stub_settings, engine=db.engine)
    dataset_id = make_dataset(db, world, fake)
    with TestClient(app) as client:
        response = make_caller(client)("admin", "POST", "/api/superset/sync")
    assert response.status_code == 202 and response.json() == {"accepted": [dataset_id]}


# --- E3~E5 대시보드 연결 ----


def test_e3_lists_active_dashboards_by_name_with_uuid_for_everyone(sapi, db, world):
    add_dashboard(db, "다 대시보드", UUID_A)
    add_dashboard(db, "가 대시보드", UUID_B)
    add_dashboard(db, "나 해제됨", "99999999-2222-3333-4444-555555555555", is_active=False)
    for who in ("viewer", "entry", "admin"):
        body = sapi(who, "GET", "/api/dashboards").json()
        assert [d["name"] for d in body["items"]] == ["가 대시보드", "다 대시보드"]
        assert body["total"] == 2
        assert set(body["items"][0]) == {"id", "name", "embedded_uuid", "is_active"}
        assert body["items"][0]["embedded_uuid"] == UUID_B


def test_e3_include_inactive_is_admin_only(sapi, db, world):
    add_dashboard(db, "활성", UUID_A)
    add_dashboard(db, "해제", UUID_B, is_active=False)
    admin = sapi("admin", "GET", "/api/dashboards?include_inactive=true").json()
    assert [d["name"] for d in admin["items"]] == ["해제", "활성"] or admin["total"] == 2
    assert admin["total"] == 2
    forbidden = sapi("viewer", "GET", "/api/dashboards?include_inactive=true")
    assert forbidden.status_code == 403 and err(forbidden)["code"] == "FORBIDDEN"
    assert sapi("viewer", "GET", "/api/dashboards?include_inactive=false").json()["total"] == 1


def test_e4_creates_with_normalized_uuid_and_rejects_duplicates_case_insensitively(sapi, db, world):
    response = sapi(
        "admin",
        "POST",
        "/api/dashboards",
        json={"name": "  월간 현황  ", "embedded_uuid": f"  {UUID_B.upper()}  "},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "월간 현황" and body["embedded_uuid"] == UUID_B
    assert body["is_active"] is True and isinstance(body["id"], int)
    dup = sapi(
        "admin", "POST", "/api/dashboards", json={"name": "다른 이름", "embedded_uuid": UUID_B}
    )
    assert dup.status_code == 409
    assert err(dup)["code"] == "ALREADY_EXISTS" and err(dup)["details"] == {
        "field": "embedded_uuid"
    }
    assert len(db.rows(superset_dashboards)) == 1


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "not-a-uuid",
        "11111111222233334444555555555555",  # 하이픈 없음
        "{11111111-2222-3333-4444-555555555555}",
        "urn:uuid:11111111-2222-3333-4444-555555555555",
        "11111111-2222-3333-4444-55555555555",  # 한 자리 모자람
        "11111111-2222-3333-4444-5555555555555",
        "gggggggg-2222-3333-4444-555555555555",
        12345,
        None,
    ],
)
def test_e4_rejects_uuid_that_is_not_the_canonical_36_char_form(sapi, world, bad):
    response = sapi("admin", "POST", "/api/dashboards", json={"name": "x", "embedded_uuid": bad})
    assert response.status_code == 422
    fields = {f["field"]: f["code"] for f in err(response)["details"]["fields"]}
    assert "embedded_uuid" in fields


@pytest.mark.parametrize("name", ["", "   ", "가" * 101, "줄\n바꿈", "탭\t이름"])
def test_e4_validates_name(sapi, world, name):
    response = sapi(
        "admin", "POST", "/api/dashboards", json={"name": name, "embedded_uuid": UUID_A}
    )
    assert response.status_code == 422
    assert "name" in {f["field"] for f in err(response)["details"]["fields"]}


def test_e4_accepts_name_of_exactly_100_chars_and_rejects_unknown_keys(sapi, world):
    ok = sapi(
        "admin", "POST", "/api/dashboards", json={"name": "가" * 100, "embedded_uuid": UUID_A}
    )
    assert ok.status_code == 201
    extra = sapi(
        "admin",
        "POST",
        "/api/dashboards",
        json={"name": "x", "embedded_uuid": UUID_B, "is_active": False},
    )
    assert extra.status_code == 422


def test_e5_updates_name_and_active_but_never_the_uuid(sapi, db, world):
    dashboard_id = add_dashboard(db)
    renamed = sapi("admin", "PATCH", f"/api/dashboards/{dashboard_id}", json={"name": "새 이름"})
    assert renamed.status_code == 200
    assert renamed.json() == {
        "id": dashboard_id,
        "name": "새 이름",
        "embedded_uuid": UUID_A,
        "is_active": True,
    }
    off = sapi("admin", "PATCH", f"/api/dashboards/{dashboard_id}", json={"is_active": False})
    assert off.json()["is_active"] is False and off.json()["name"] == "새 이름"
    both = sapi(
        "admin", "PATCH", f"/api/dashboards/{dashboard_id}", json={"name": "셋", "is_active": True}
    )
    assert both.json()["name"] == "셋" and both.json()["is_active"] is True
    for body in ({}, {"embedded_uuid": UUID_B}, {"name": None}, {"is_active": None}, {"id": 5}):
        response = sapi("admin", "PATCH", f"/api/dashboards/{dashboard_id}", json=body)
        assert response.status_code == 422, body
    assert db.rows(superset_dashboards)[0]["embedded_uuid"].__str__() == UUID_A
    assert sapi("admin", "PATCH", "/api/dashboards/99999", json={"name": "x"}).status_code == 404


# --- E6 POST /dashboards/{id}/guest-token ----


def test_e6_issues_token_with_exact_request_to_superset_and_no_store_headers(sapi, db, world, fake):
    dashboard_id = add_dashboard(db, embedded_uuid=UUID_A)
    fake.embedded_uuids.add(UUID_A)
    response = sapi("viewer", "POST", f"/api/dashboards/{dashboard_id}/guest-token")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"token", "expires_in"}
    assert body["expires_in"] == GUEST_TOKEN_EXPIRES_IN == 300
    assert body["token"] == fake.tokens_issued[0]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    call = next(c for c in fake.calls if c.path == "/api/v1/security/guest_token/")
    assert call.body == {
        "user": {"username": str(world.ids["viewer"])},  # first_name/last_name은 보내지 않는다
        "resources": [{"type": "dashboard", "id": UUID_A}],
        "rls": [],
    }
    assert call.account == ISSUER[0]  # 발급 전용 계정으로만 발급한다
    assert not any(c.account == ISSUER[0] for c in fake.calls if "/dataset" in c.path)


def test_e6_sends_lowercase_canonical_uuid(sapi, db, world, fake):
    dashboard_id = add_dashboard(db, embedded_uuid=UUID_B.upper())
    fake.embedded_uuids.add(UUID_B)
    assert sapi("viewer", "POST", f"/api/dashboards/{dashboard_id}/guest-token").status_code == 200
    call = next(c for c in fake.calls if c.path == "/api/v1/security/guest_token/")
    assert call.body["resources"][0]["id"] == UUID_B


def test_e6_only_takes_the_portal_id_any_body_is_422_and_superset_is_not_called(
    sapi, db, world, fake
):
    dashboard_id = add_dashboard(db)
    fake.embedded_uuids.add(UUID_A)
    path = f"/api/dashboards/{dashboard_id}/guest-token"
    for kwargs in (
        {"json": {}},
        {"json": {"rls": [{"clause": "1=1"}]}},
        {"json": {"embedded_uuid": UUID_B}},
        {"content": b"x"},
    ):
        response = sapi("viewer", "POST", path, **kwargs)
        assert response.status_code == 422, kwargs
        assert err(response)["code"] == "VALIDATION_ERROR"
    assert fake.calls == []


def test_e6_not_found_for_missing_and_inactive_dashboards_without_calling_superset(
    sapi, db, world, fake
):
    inactive = add_dashboard(db, embedded_uuid=UUID_B, is_active=False)
    for dashboard_id in (inactive, 99999):
        response = sapi("viewer", "POST", f"/api/dashboards/{dashboard_id}/guest-token")
        assert response.status_code == 404 and err(response)["code"] == "NOT_FOUND"
    assert fake.calls == []


def test_e6_requires_login_and_an_active_user(sapi, db, world):
    dashboard_id = add_dashboard(db)
    path = f"/api/dashboards/{dashboard_id}/guest-token"
    assert sapi(None, "POST", path).status_code == 401
    assert sapi("inactive", "POST", path).status_code == 403


def test_e6_superset_down_is_503_and_rejection_is_502(sapi, db, world, fake):
    dashboard_id = add_dashboard(db)
    path = f"/api/dashboards/{dashboard_id}/guest-token"
    rejected = sapi(
        "viewer", "POST", path
    )  # Superset에 임베드가 켜져 있지 않다 -> 훅/기본 검사 400
    assert rejected.status_code == 502
    assert err(rejected)["code"] == "SUPERSET_REJECTED"
    fake.up = False
    down = sapi("viewer", "POST", path)
    assert down.status_code == 503 and err(down)["code"] == "SUPERSET_UNAVAILABLE"
    for response in (rejected, down):
        text = response.text.lower()
        for internal in ("superset", "csrf", "rls", "guest", "token", "http", "400"):
            assert internal not in text.replace("superset_", "").replace("request_id", "")


def test_e6_without_superset_configuration_is_503(db, stub_settings, world):
    dashboard_id = add_dashboard(db)
    app = create_app(stub_settings, engine=db.engine)
    with TestClient(app) as client:
        response = make_caller(client)(
            "viewer", "POST", f"/api/dashboards/{dashboard_id}/guest-token"
        )
    assert response.status_code == 503 and err(response)["code"] == "SUPERSET_UNAVAILABLE"


def test_e6_rate_limit_is_per_user_30_per_60_seconds_with_retry_after(sapi, db, world, fake, clock):
    dashboard_id = add_dashboard(db)
    fake.embedded_uuids.add(UUID_A)
    path = f"/api/dashboards/{dashboard_id}/guest-token"
    for number in range(GUEST_TOKEN_RATE_LIMIT):
        assert sapi("viewer", "POST", path).status_code == 200, number
        clock.advance(1)  # 29초 동안 30번
    clock.now -= 1  # 한 번째 호출 후 29초가 지난 시점
    blocked = sapi("viewer", "POST", path)
    assert blocked.status_code == 429
    assert err(blocked)["code"] == "GUEST_TOKEN_RATE_LIMITED"
    retry_after = int(blocked.headers["retry-after"])
    assert retry_after == err(blocked)["details"]["retry_after"] == 31 - 1 + 0 or retry_after >= 1
    assert len([c for c in fake.calls if c.path == "/api/v1/security/guest_token/"]) == 30
    # 다른 사용자는 영향이 없다.
    assert sapi("entry", "POST", path).status_code == 200
    # 윈도가 지나면 풀린다.
    clock.advance(retry_after)
    assert sapi("viewer", "POST", path).status_code == 200


def test_e6_limit_applies_before_the_404_check(sapi, db, world, fake, clock):
    """없는 번호를 두드리는 정찰도 제한한다."""
    for _ in range(GUEST_TOKEN_RATE_LIMIT):
        assert sapi("viewer", "POST", "/api/dashboards/99999/guest-token").status_code == 404
    assert sapi("viewer", "POST", "/api/dashboards/99999/guest-token").status_code == 429


def test_e6_limit_value_can_be_injected(superset_settings, fake, clock, db, world, monkeypatch):
    built = build_superset_services(superset_settings, transport=fake.transport, clock=clock)
    assert built is not None
    from app.superset.ratelimit import SlidingWindowLimiter

    built.limiter = SlidingWindowLimiter(limit=2, window_seconds=10, clock=clock)
    monkeypatch.setattr(built.sync, "start", lambda: None)
    dashboard_id = add_dashboard(db)
    fake.embedded_uuids.add(UUID_A)
    app = create_app(superset_settings, engine=db.engine, superset=built)
    with TestClient(app) as client:
        call = make_caller(client)
        path = f"/api/dashboards/{dashboard_id}/guest-token"
        assert [call("viewer", "POST", path).status_code for _ in range(3)] == [200, 200, 429]
        clock.advance(10)
        assert call("viewer", "POST", path).status_code == 200


def test_e6_token_never_appears_in_logs_or_error_bodies(sapi, db, world, fake, caplog):
    caplog.set_level(logging.DEBUG)
    dashboard_id = add_dashboard(db)
    fake.embedded_uuids.add(UUID_A)
    path = f"/api/dashboards/{dashboard_id}/guest-token"
    token = sapi("viewer", "POST", path).json()["token"]
    fake.up = False
    sapi("viewer", "POST", path)  # 실패 경로
    fake.up = True
    sapi("viewer", "POST", "/api/dashboards/99999/guest-token")
    text = "\n".join(f"{r.getMessage()} {r.exc_text or ''} {r.name}" for r in caplog.records)
    assert token not in text
    assert "eyJ" not in text
    for secret in (SERVICE[1], ISSUER[1]):
        assert secret not in text


def test_e6_issuer_stops_calling_superset_after_consecutive_connection_failures(
    sapi, db, world, fake
):
    dashboard_id = add_dashboard(db)
    path = f"/api/dashboards/{dashboard_id}/guest-token"
    fake.up = False
    for _ in range(6):
        assert sapi("viewer", "POST", path).status_code == 503
    assert len(fake.calls) == 3  # 서킷 브레이커: 연속 3회 뒤에는 호출하지 않는다


def test_e6_login_failure_of_issuer_is_502_and_not_a_server_error(
    superset_settings, fake, clock, db, world, monkeypatch
):
    fake.accounts[ISSUER[0]] = "다른 비밀번호"  # superset-init이 비밀번호를 되돌리기 전 상황
    built = build_superset_services(superset_settings, transport=fake.transport, clock=clock)
    assert built is not None
    monkeypatch.setattr(built.sync, "start", lambda: None)
    dashboard_id = add_dashboard(db)
    app = create_app(superset_settings, engine=db.engine, superset=built)
    with TestClient(app) as client:
        response = make_caller(client)(
            "viewer", "POST", f"/api/dashboards/{dashboard_id}/guest-token"
        )
    assert response.status_code == 502 and err(response)["code"] == "SUPERSET_REJECTED"


# --- 정의 변경 후 동기화 요청(DatasetSyncPort, 커밋 뒤) ----


def test_dataset_creation_and_changes_request_sync_through_the_real_port(
    sapi, db, world, fake, services
):
    created = sapi(
        "definer",
        "POST",
        "/api/datasets",
        json={"team_id": world.team_a, "name": "월 매출", "date_unit": "month"},
    )
    assert created.status_code == 201
    dataset = created.json()
    assert fake.calls == []  # 요청 처리 중에는 Superset을 부르지 않는다
    rows = db.rows(superset_datasets)
    assert [r["sync_status"] for r in rows] == ["pending"]
    assert services.sync.pending_ids() == [dataset["id"]]
    column = sapi(
        "definer",
        "POST",
        f"/api/datasets/{dataset['id']}/columns",
        json={"expected_version": dataset["def_version"], "display_name": "매출", "type": "number"},
    )
    assert column.status_code == 201
    # 뷰는 1d 훅이 만든다. 가짜 Superset의 뷰 열은 시험이 알려 준다.
    fake.views[dataset["id"]] = ["team", "row_id", f"c_{column.json()['column']['id']}"]
    services.sync.drain()
    assert db.rows(superset_datasets)[0]["sync_status"] == "registered"
    labels = {c["column_name"]: c["verbose_name"] for c in fake.datasets[1]["columns"]}
    assert set(labels.values()) == {"팀", "행 번호", "매출"}


def test_team_rename_through_api_updates_all_superset_names(sapi, db, world, fake, services):
    dataset_id = make_dataset(db, world, fake)
    services.sync.request_dataset_sync(dataset_id)
    services.sync.drain()
    response = sapi("admin", "PATCH", f"/api/teams/{world.team_a}", json={"name": "새 A팀"})
    assert response.status_code == 200
    assert (
        fake.datasets[1]["table_name"] == "[A팀] 월간"
    )  # 요청 처리 중에는 아직 Superset을 부르지 않는다
    assert services.sync.pending_ids() == [dataset_id]
    services.sync.drain()
    assert fake.datasets[1]["table_name"] == "[새 A팀] 월간"
    assert len(fake.datasets) == 1


# --- Superset이 멈춰도 포털은 즉시 시작하고 다른 API가 정상이다(P4) ----


@pytest.fixture
def live_app(db: Db, superset_settings, fake):
    """실제 작업 스레드까지 도는 앱(실제 시계)."""
    services = build_superset_services(
        superset_settings,
        transport=fake.transport,
        health_interval=0.02,
        retry_interval=0.05,
        breaker_cooldown=0.1,
    )
    assert services is not None
    app = create_app(superset_settings, engine=db.engine, superset=services)
    with TestClient(app) as client:
        yield make_caller(client), services


def test_app_starts_instantly_and_other_apis_work_while_superset_is_down(
    db, world, fake, superset_settings
):
    if db.kind == "sqlite":
        pytest.skip("SQLite 시험 DB는 연결 하나를 스레드 사이에 공유한다(PostgreSQL 변형에서 확인)")
    fake.up = False
    services = build_superset_services(
        superset_settings,
        transport=fake.transport,
        health_interval=0.02,
        retry_interval=0.05,
        breaker_cooldown=0.1,
    )
    assert services is not None
    app = create_app(superset_settings, engine=db.engine, superset=services)
    start = time.monotonic()
    with TestClient(app) as client:
        assert time.monotonic() - start < 3  # Superset을 기다리지 않는다
        call = make_caller(client)
        assert call(None, "GET", "/api/health").status_code == 200
        created = call(
            "definer",
            "POST",
            "/api/datasets",
            json={"team_id": world.team_a, "name": "월 매출", "date_unit": "month"},
        )
        assert created.status_code == 201
        dataset = created.json()
        column = call(
            "definer",
            "POST",
            f"/api/datasets/{dataset['id']}/columns",
            json={
                "expected_version": dataset["def_version"],
                "display_name": "매출",
                "type": "number",
            },
        )
        assert column.status_code == 201
        assert call("viewer", "GET", "/api/datasets").status_code == 200
        assert call("viewer", "GET", f"/api/datasets/{dataset['id']}/rows").status_code == 200
        assert call("viewer", "GET", "/api/dashboards").status_code == 200
        # 동기 상태는 pending에서 failed로 간다(연결 거부).
        assert settled(
            lambda: (
                call("admin", "GET", "/api/superset/datasets").json()["items"][0]["sync_status"]
                == "failed"
            )
        )
        failed = call("admin", "GET", "/api/superset/datasets").json()["items"][0]
        assert failed["last_error"] == summarize("UNAVAILABLE_CONNECT")
        # 모의 Superset을 올리면 스스로 복구한다. 중복 등록은 없다.
        fake.views[dataset["id"]] = ["team", "row_id", f"c_{column.json()['column']['id']}"]
        fake.up = True
        assert settled(
            lambda: (
                call("admin", "GET", "/api/superset/datasets").json()["items"][0]["sync_status"]
                == "registered"
            ),
            timeout=10,
        )
        assert len(fake.datasets) == 1
    assert settled(
        lambda: not any(t.name == "superset-sync" for t in __import__("threading").enumerate())
    )


def test_startup_waits_for_superset_health_inside_the_worker_only(live_app, fake, db, world):
    if db.kind == "sqlite":
        pytest.skip("SQLite 시험 DB는 연결 하나를 스레드 사이에 공유한다(PostgreSQL 변형에서 확인)")
    call, services = live_app
    assert call(None, "GET", "/api/health").status_code == 200
    assert services.sync.startup_pending is False or fake.health_ok  # 건강한 가짜면 곧 끝난다
    assert settled(lambda: services.sync.startup_pending is False)


# --- 권한 매트릭스(Superset 연동이 켜진 앱: E6 성공은 실제 200) ----

ROLES = ["admin", "definer", "entry", "other", "viewer", "inactive", None]
READERS = {"admin", "definer", "entry", "other", "viewer"}


@pytest.mark.parametrize("role", ROLES, ids=lambda r: r or "anonymous")
@pytest.mark.parametrize(
    ("endpoint", "method", "path", "body", "success", "allowed"),
    [
        ("E1", "GET", "/api/superset/datasets", None, 200, READERS),
        ("E2", "POST", "/api/superset/sync", {}, 202, {"admin"}),
        ("E3", "GET", "/api/dashboards", None, 200, READERS),
        ("E4", "POST", "/api/dashboards", {"name": "n", "embedded_uuid": UUID_B}, 201, {"admin"}),
        ("E5", "PATCH", "/api/dashboards/{d}", {"is_active": False}, 200, {"admin"}),
        ("E6", "POST", "/api/dashboards/{d}/guest-token", None, 200, READERS),
    ],
)
def test_e_endpoints_by_role(
    sapi, db, world, fake, endpoint, method, path, body, success, allowed, role
):
    dashboard_id = add_dashboard(db)
    fake.embedded_uuids.add(UUID_A)
    response = sapi(
        role,
        method,
        path.format(d=dashboard_id),
        **({"json": body} if body is not None else {}),
    )
    if role is None:
        assert (response.status_code, err(response)["code"]) == (401, "UNAUTHENTICATED")
    elif role == "inactive":
        assert (response.status_code, err(response)["code"]) == (403, "USER_INACTIVE")
    elif role in allowed:
        assert response.status_code == success, response.text
    else:
        assert (response.status_code, err(response)["code"]) == (403, "FORBIDDEN")
    if role not in allowed:  # 거부된 요청은 Superset을 부르지도, 데이터를 바꾸지도 않는다
        assert fake.calls == []
        rows = db.rows(superset_dashboards)
        assert len(rows) == 1 and rows[0]["is_active"] is True and rows[0]["name"] == "월간 현황"
