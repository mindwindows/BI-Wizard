"""데이터셋 보관·복구 시험(05 §2-2 B7·B8, 04 §5·§5-1, 06 §5, `03b` 30-1). SQLite·PostgreSQL 두 변형.

- 상태 전이: 활성 -> 보관 -> 활성, 같은 상태 재요청은 200·감사 0건·변경 0건, 404, 본문 거부
- 권한: 그 팀 정의 담당자만(관리자 예외 없음), 비활성 팀도 허용, 복구 경로(비활성 팀 소속 지정)
- B1 `status` 필터(`total` 포함)와 잘못된 값 422
- 보관 중 거부: 판정이 버전 비교·검증 422보다 앞이고, 복구하면 읽어 둔 버전이 그대로 쓰인다
- 읽기·검사·미리보기·동기 요청·D10은 보관과 무관하게 동작, 이름 충돌 안내 문구
- 보관·복구가 정의 변경 훅·동기 요청·`def_version`·`def_hash`를 건드리지 않는다
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.dataset import service as dataset_service
from app.db_metadata import datasets, teams
from tests.audit_helpers import Ctx, audit_rows, audit_rows_of, static_snapshot
from tests.formula_api_helpers import (
    add_column,
    add_formula,
    err,
    make_dataset,
    version,
)

ARCHIVE_MESSAGE = "보관된 데이터셋은 고칠 수 없습니다. 복구한 뒤 다시 시도하세요."
ARCHIVED_NAME_HINT = "보관된 데이터셋과 같은 이름"


def archive(call, dataset_id, login="definer", **kw):
    return call(login, "POST", f"/api/datasets/{dataset_id}/archive", **kw)


def restore(call, dataset_id, login="definer", **kw):
    return call(login, "POST", f"/api/datasets/{dataset_id}/restore", **kw)


def detail(call, dataset_id, login="viewer"):
    return call(login, "GET", f"/api/datasets/{dataset_id}").json()


def row_of(db, dataset_id):
    return next(r for r in db.rows(datasets, datasets.c.id) if r["id"] == dataset_id)


@pytest.fixture
def ds(api, world):
    """A팀 데이터셋: 숫자 열 '매출', 계산 열 '두배'."""
    dataset = make_dataset(api, world, "보관 시험")
    sales = add_column(api, dataset["id"], "매출")["id"]
    calc = add_formula(api, dataset["id"], "두배", "[매출] * 2")["id"]
    return {"id": dataset["id"], "sales": sales, "calc": calc}


# --- 상태 전이 ----


def test_archive_then_restore_flips_only_the_status(api, db, world, ds):
    before = detail(api, ds["id"], "definer")
    state = row_of(db, ds["id"])
    archived = archive(api, ds["id"])
    assert archived.status_code == 200, archived.text
    body = archived.json()
    assert body["status"] == "archived"
    # 응답은 B3 상세와 같은 모양이고 status 말고는 그대로다(def_version도 그대로)
    assert {k: v for k, v in body.items() if k != "status"} == {
        k: v for k, v in before.items() if k != "status"
    }
    assert detail(api, ds["id"])["status"] == "archived"
    after = row_of(db, ds["id"])
    assert {k: v for k, v in after.items() if k != "status"} == {
        k: v for k, v in state.items() if k != "status"
    }  # def_version·def_hash·이름·기준 열 등 불변
    restored = restore(api, ds["id"])
    assert restored.status_code == 200, restored.text
    assert restored.json() == before  # 활성으로 돌아오면 처음 상세와 완전히 같다
    assert row_of(db, ds["id"]) == state


def test_repeating_the_same_state_is_200_with_no_audit_and_no_change(api, db, ctx: Ctx, ds):
    call = ctx.call
    audit_before = audit_rows(db)
    assert restore(call, ds["id"]).status_code == 200  # 이미 활성
    assert audit_rows(db) == audit_before
    assert archive(call, ds["id"]).status_code == 200
    state, snap = audit_rows(db), static_snapshot(db)
    again = archive(call, ds["id"])
    assert again.status_code == 200 and again.json()["status"] == "archived"
    assert audit_rows(db) == state and static_snapshot(db) == snap
    assert restore(call, ds["id"]).status_code == 200
    assert restore(call, ds["id"]).status_code == 200
    assert [r["action"] for r in audit_rows(db)[len(audit_before) :]] == [
        "dataset.archive",
        "dataset.restore",
    ]


@pytest.mark.parametrize("action", ["archive", "restore"])
def test_unknown_dataset_is_404_before_anything_else(api, world, action):
    for login, status in (("definer", 404), ("viewer", 404), ("admin", 404)):
        response = api(login, "POST", f"/api/datasets/999999/{action}")
        assert (response.status_code, err(response)["code"]) == (status, "NOT_FOUND")
    assert api(None, "POST", f"/api/datasets/999999/{action}").status_code == 401


@pytest.mark.parametrize("action", ["archive", "restore"])
def test_a_body_is_rejected_after_the_permission_check(api, ds, action):
    path = f"/api/datasets/{ds['id']}/{action}"
    bad = api("definer", "POST", path, json={"expected_version": 1})
    assert (bad.status_code, err(bad)["code"]) == (422, "VALIDATION_ERROR")
    assert err(bad)["details"]["fields"][0]["field"] == "body"
    # 권한 판정이 먼저다: 정의 담당자가 아니면 본문이 있어도 403, 없는 데이터셋은 404
    assert api("entry", "POST", path, json={"x": 1}).status_code == 403
    assert (
        api("definer", "POST", f"/api/datasets/999999/{action}", json={"x": 1}).status_code == 404
    )
    assert detail(api, ds["id"])["status"] == "active"  # 거부된 요청은 아무것도 바꾸지 않았다


def test_archive_makes_no_sync_request_and_never_runs_the_definition_hook(ctx: Ctx, sync, ds):
    ctx.boom_armed["on"] = True  # 정의 변경 훅이 불리면 500이 된다
    before = (list(sync.dataset_requests), list(sync.team_requests))
    assert archive(ctx.call, ds["id"]).status_code == 200
    assert restore(ctx.call, ds["id"]).status_code == 200
    ctx.boom_armed["on"] = False
    assert (sync.dataset_requests, sync.team_requests) == before


# --- 권한 ----


@pytest.mark.parametrize("action", ["archive", "restore"])
@pytest.mark.parametrize(
    ("login", "status", "code"),
    [
        ("definer", 200, None),
        ("entry", 403, "FORBIDDEN"),  # 입력자는 안 된다
        ("other", 403, "FORBIDDEN"),  # 다른 팀 구성원
        ("admin", 403, "FORBIDDEN"),  # 관리자 예외 없음(소속 없음)
        ("viewer", 403, "FORBIDDEN"),
        ("inactive", 403, "USER_INACTIVE"),
        (None, 401, "UNAUTHENTICATED"),
    ],
)
def test_only_the_teams_definer_can_archive_or_restore(api, db, ds, action, login, status, code):
    if action == "restore":
        assert archive(api, ds["id"]).status_code == 200
    response = api(login, "POST", f"/api/datasets/{ds['id']}/{action}")
    assert response.status_code == status, response.text
    if code is not None:
        assert err(response)["code"] == code
        expected = "archived" if action == "restore" else "active"  # 거부되면 상태가 그대로다
        assert row_of(db, ds["id"])["status"] == expected


def test_definer_of_another_team_cannot_archive(api, db, world, ds):
    other_definer = db.add_user("definer_b", "B팀 정의 담당자")
    db.add_member(world.team_b, other_definer, "definer")
    assert archive(api, ds["id"], login="definer_b").status_code == 403
    assert detail(api, ds["id"])["status"] == "active"


def test_an_admin_who_is_also_the_teams_definer_may_archive(api, db, world, ds):
    """예외가 아니라 정의 담당자 자격이다: 관리자가 팀 definer로 올라 있으면 같은 규칙이다."""
    db.add_member(world.team_a, world.ids["admin"], "definer")
    assert archive(api, ds["id"], login="admin").status_code == 200
    assert restore(api, ds["id"], login="admin").status_code == 200


def set_team_active(db, team_id, active):
    with db.writer.begin() as conn:
        conn.execute(sa.update(teams).where(teams.c.id == team_id).values(is_active=active))


def test_inactive_team_does_not_block_archive_or_restore(api, db, world, ds):
    set_team_active(db, world.team_a, False)
    archived = archive(api, ds["id"])
    assert archived.status_code == 200 and archived.json()["status"] == "archived"
    restored = restore(api, ds["id"])
    assert restored.status_code == 200 and restored.json()["status"] == "active"


def must(response, status=200):
    assert response.status_code == status, response.text
    return response


def test_admin_cannot_designate_a_definer_in_an_inactive_team_but_can_reactivate_first(
    api, db, world, ds
):
    """복구 경로 실측(03b 30-1 결정 2): 비활성 팀에는 A8로 definer를 지정할 수 없다(409).

    관리자 예외 코드는 없다. 다만 팀을 다시 활성화(A4)한 뒤 지정(A8)하면 새 definer가
    비활성 팀이어도 복구할 수 있다. 팀에 이미 definer가 남아 있으면 그 사람이 그대로 복구한다.
    """
    must(archive(api, ds["id"]))
    # 팀을 비활성으로 만들고 유일한 definer 소속을 해제한다(복구할 사람이 없다)
    team = f"/api/teams/{world.team_a}"
    must(api("admin", "PATCH", team, json={"is_active": False}))
    must(api("admin", "DELETE", f"{team}/members/{world.ids['definer']}"), 204)
    assert restore(api, ds["id"], login="definer").status_code == 403
    assert restore(api, ds["id"], login="admin").status_code == 403  # 관리자 예외 없음
    # (b) 비활성 팀에 definer를 지정하려 하면 409 TARGET_INACTIVE
    path = f"{team}/members/{world.ids['viewer']}"
    blocked = api("admin", "PUT", path, json={"role": "definer"})
    assert (blocked.status_code, err(blocked)["code"]) == (409, "TARGET_INACTIVE")
    assert err(blocked)["details"] == {"field": "team"}
    # 우회: 팀을 다시 활성화 -> definer 지정 -> (팀이 비활성이어도) 새 definer가 복구
    must(api("admin", "PATCH", team, json={"is_active": True}))
    must(api("admin", "PUT", path, json={"role": "definer"}))
    must(api("admin", "PATCH", team, json={"is_active": False}))
    restored = restore(api, ds["id"], login="viewer")
    assert restored.status_code == 200 and restored.json()["status"] == "active"


def test_a_definer_who_stays_in_an_inactive_team_can_restore_without_admin_help(api, db, world, ds):
    assert archive(api, ds["id"]).status_code == 200
    must(api("admin", "PATCH", f"/api/teams/{world.team_a}", json={"is_active": False}))
    assert restore(api, ds["id"]).status_code == 200


# --- B1 status 필터 ----


def names(response) -> list[str]:
    return [item["name"] for item in response.json()["items"]]


def test_b1_status_filter_default_active_archived_all_with_total(api, db, world):
    make_dataset(api, world, "가")
    b = make_dataset(api, world, "나")["id"]
    make_dataset(api, world, "다")
    assert archive(api, b).status_code == 200
    default = api("viewer", "GET", "/api/datasets")
    assert names(default) == ["가", "다"] and default.json()["total"] == 2
    assert names(api("viewer", "GET", "/api/datasets?status=active")) == ["가", "다"]
    only = api("viewer", "GET", "/api/datasets?status=archived")
    assert names(only) == ["나"] and only.json()["total"] == 1
    assert only.json()["items"][0]["status"] == "archived"
    everything = api("viewer", "GET", "/api/datasets?status=all")
    assert names(everything) == ["가", "나", "다"] and everything.json()["total"] == 3
    assert {i["status"] for i in everything.json()["items"]} == {"active", "archived"}
    # total은 같은 필터를 쓰고 페이지 경계와 무관하다
    page = api("viewer", "GET", "/api/datasets?status=all&limit=1&offset=1").json()
    assert (page["total"], len(page["items"]), page["items"][0]["id"]) == (3, 1, b)
    # team_id와 함께 쓴다
    team = api("viewer", "GET", f"/api/datasets?status=archived&team_id={world.team_b}").json()
    assert team["total"] == 0 and team["items"] == []
    # 복구하면 기본 목록으로 돌아온다
    assert restore(api, b).status_code == 200
    assert names(api("viewer", "GET", "/api/datasets")) == ["가", "나", "다"]


@pytest.mark.parametrize("value", ["bogus", "", "ACTIVE", "deleted", "active,archived"])
def test_b1_status_outside_the_options_is_422_not_in_options(api, world, value):
    response = api("viewer", "GET", "/api/datasets", params={"status": value})
    assert (response.status_code, err(response)["code"]) == (422, "VALIDATION_ERROR")
    assert err(response)["details"]["fields"] == [
        {"field": "status", "code": "NOT_IN_OPTIONS", "message": "선택 목록에 없는 값입니다."}
    ]


def test_b3_detail_shows_the_archived_status_and_keeps_the_permission_flags(api, ds):
    assert archive(api, ds["id"]).status_code == 200
    as_definer = api("definer", "GET", f"/api/datasets/{ds['id']}").json()
    assert as_definer["status"] == "archived"
    assert as_definer["permissions"] == {"define": True, "enter": True}
    assert api("viewer", "GET", f"/api/datasets/{ds['id']}").json()["status"] == "archived"


# --- 보관 중 거부 ----


def archived_error(response):
    assert response.status_code == 409, response.text
    error = err(response)
    assert error["code"] == "DATASET_ARCHIVED"
    assert error["message"] == ARCHIVE_MESSAGE
    assert error["details"] == {"status": "archived"}


def test_rejection_comes_before_the_version_comparison_and_the_422_validation(api, db, world, ds):
    make_dataset(api, world, "다른 이름")
    v = version(api, ds["id"])
    # 대조군: 활성일 때는 같은 요청이 각자의 오류를 낸다
    bad_rules = {
        "expected_version": v,
        "display_name": "열",
        "type": "number",
        "rules": {"min": "abc"},
    }
    invalid_cell = {"expected_version": v, "cells": {str(ds["sales"]): "숫자아님"}}
    one_change = {
        "expected_version": v,
        "changes": [{"column_id": ds["sales"], "expected": None, "value": "1"}],
    }
    assert (
        api("definer", "POST", f"/api/datasets/{ds['id']}/columns", json=bad_rules).status_code
        == 422
    )
    assert (
        api("definer", "POST", f"/api/datasets/{ds['id']}/rows", json=invalid_cell).status_code
        == 422
    )
    assert (
        api(
            "definer",
            "PATCH",
            f"/api/datasets/{ds['id']}/rows/999",
            json=one_change,
        ).status_code
        == 404
    )
    bad_formula = api(
        "definer",
        "POST",
        f"/api/datasets/{ds['id']}/formulas",
        json={"expected_version": v, "display_name": "나", "expression": "[없는 열] +"},
    )
    assert bad_formula.status_code == 422
    assert archive(api, ds["id"]).status_code == 200
    base = f"/api/datasets/{ds['id']}"
    cases = [
        ("PATCH", base, {"expected_version": 99, "name": "새 이름"}),
        ("PATCH", base, {"expected_version": v, "name": "다른 이름"}),  # 이름 충돌보다 먼저
        ("POST", f"{base}/columns", bad_rules),
        ("POST", f"{base}/columns", {**bad_rules, "expected_version": 99}),
        ("PATCH", f"{base}/columns/999999", {"expected_version": v, "display_name": "x"}),
        ("POST", f"{base}/rows", invalid_cell),
        ("POST", f"{base}/rows", {**invalid_cell, "expected_version": 99}),
        ("PATCH", f"{base}/rows/999", one_change),
        (
            "POST",
            f"{base}/rows/paste",
            {
                "expected_version": 99,
                "column_ids": [ds["sales"]],
                "rows": [{"row_id": None, "values": ["숫자아님"]}],
            },
        ),
        (
            "POST",
            f"{base}/formulas",
            {"expected_version": v, "display_name": "나", "expression": "[없는 열] +"},
        ),
        ("PUT", f"{base}/formulas/{ds['calc']}", {"expected_version": 99, "expression": "(((("}),
    ]
    snapshot = static_snapshot(db)
    for method, path, body in cases:
        archived_error(api("definer", method, path, json=body))
    assert static_snapshot(db) == snapshot  # 거부된 요청은 아무것도 바꾸지 않았다


def test_entry_user_gets_the_same_rejection_for_row_writes(api, ds):
    assert archive(api, ds["id"]).status_code == 200
    v = version(api, ds["id"])
    response = api(
        "entry",
        "POST",
        f"/api/datasets/{ds['id']}/rows",
        json={"expected_version": v, "cells": {str(ds["sales"]): "5"}},
    )
    archived_error(response)


def test_restoring_keeps_the_version_so_a_screen_read_before_archiving_still_works(api, db, ds):
    v = version(api, ds["id"])
    assert archive(api, ds["id"]).status_code == 200
    assert version(api, ds["id"]) == v
    assert restore(api, ds["id"]).status_code == 200
    assert version(api, ds["id"]) == v
    created = api(
        "entry",
        "POST",
        f"/api/datasets/{ds['id']}/rows",
        json={"expected_version": v, "cells": {str(ds["sales"]): "5"}},
    )
    assert created.status_code == 201, created.text
    column = api(
        "definer",
        "POST",
        f"/api/datasets/{ds['id']}/columns",
        json={"expected_version": v, "display_name": "비고", "type": "text"},
    )
    assert column.status_code == 201, column.text
    assert column.json()["def_version"] == v + 1


# --- 보관 중에도 동작하는 것 ----


def test_reads_checks_previews_and_sync_requests_still_work_while_archived(api, db, ds, sync):
    assert archive(api, ds["id"]).status_code == 200
    base = f"/api/datasets/{ds['id']}"
    for method, path, body, status in (
        ("GET", base, None, 200),  # B3
        ("GET", f"{base}/rows", None, 200),  # C1
        ("GET", "/api/formulas/functions", None, 200),  # D1
        ("POST", f"{base}/formulas/check", {"expression": "[매출] + 1"}, 200),  # D2
        ("GET", f"{base}/formulas/{ds['calc']}", None, 200),  # D6
        ("GET", f"{base}/formula-errors", None, 200),  # D8
        ("GET", "/api/checks/formula-errors", None, 200),  # D7(활성만 대상)
    ):
        kwargs = {"json": body} if body is not None else {}
        who = "definer" if method == "POST" else "viewer"
        assert api(who, method, path, **kwargs).status_code == status, path
    # E1 목록에 보관된 데이터셋이 보이고 E2 접수도 된다(Superset 등록은 유지)
    listed = api("viewer", "GET", "/api/superset/datasets").json()["items"]
    assert ds["id"] in [i["dataset_id"] for i in listed]
    assert (
        api("admin", "POST", "/api/superset/sync", json={"dataset_ids": [ds["id"]]}).status_code
        == 202
    )


def test_d10_retry_works_on_an_archived_dataset_and_keeps_it_archived(api, db, ds):
    """D10(뷰 재생성)은 정의 변경이 아니라 대조 복구라 보관 검사를 하지 않는다(bump=False)."""
    assert archive(api, ds["id"]).status_code == 200
    state = row_of(db, ds["id"])
    response = api("admin", "POST", "/api/checks/views/retry", json={"dataset_ids": [ds["id"]]})
    assert response.status_code == 200, response.text
    assert response.json()["rebuilt"] == 1
    after = row_of(db, ds["id"])
    assert (after["status"], after["def_version"]) == ("archived", state["def_version"])


def test_d7_lists_only_active_datasets_by_design(api, db, ds):
    """알려진 한계(05 §2-4 D7): 보관 중 오류 칸은 점검 목록에 안 보인다(코드 변경 없음)."""
    with Session(db.engine) as session:
        assert [r["dataset_id"] for r in dataset_service.list_formula_columns(session)] == [
            ds["id"]
        ]
    assert archive(api, ds["id"]).status_code == 200
    with Session(db.engine) as session:
        assert dataset_service.list_formula_columns(session) == []
        # 시작 대조 대상에는 보관 데이터셋이 포함된다(FU-2b)
        assert dataset_service.list_startup_check_dataset_ids(session) == [ds["id"]]


def test_startup_check_list_includes_every_dataset_active_or_archived(api, db, world):
    first = make_dataset(api, world, "하나")["id"]
    second = make_dataset(api, world, "둘")["id"]
    third = make_dataset(api, world, "셋")["id"]
    assert archive(api, second).status_code == 200
    with Session(db.engine) as session:
        assert dataset_service.list_startup_check_dataset_ids(session) == [first, second, third]


# --- 이름 점유와 충돌 안내 ----


def test_name_conflict_with_an_archived_dataset_mentions_it_on_create(api, world, ds):
    assert archive(api, ds["id"]).status_code == 200
    response = api(
        "definer",
        "POST",
        "/api/datasets",
        json={"team_id": world.team_a, "name": "보관 시험", "date_unit": "month"},
    )
    assert (response.status_code, err(response)["code"]) == (409, "ALREADY_EXISTS")
    assert err(response)["details"] == {"field": "name"}
    assert ARCHIVED_NAME_HINT in err(response)["message"]
    assert "같은 팀에 이미 같은 이름의 데이터셋이 있습니다." in err(response)["message"]
    # 복구하면 문구가 평소로 돌아온다(상대가 활성이므로 덧붙이지 않는다)
    assert restore(api, ds["id"]).status_code == 200
    again = api(
        "definer",
        "POST",
        "/api/datasets",
        json={"team_id": world.team_a, "name": "보관 시험", "date_unit": "month"},
    )
    assert err(again)["message"] == "같은 팀에 이미 같은 이름의 데이터셋이 있습니다."


def test_name_conflict_with_an_archived_dataset_mentions_it_on_rename(api, world, ds):
    other = make_dataset(api, world, "다른 이름")["id"]
    assert archive(api, ds["id"]).status_code == 200
    v = version(api, other)
    clash = api(
        "definer",
        "PATCH",
        f"/api/datasets/{other}",
        json={"expected_version": v, "name": "보관 시험"},
    )
    assert (clash.status_code, err(clash)["code"]) == (409, "ALREADY_EXISTS")
    assert ARCHIVED_NAME_HINT in err(clash)["message"]
    assert version(api, other) == v  # 이름이 바뀌지 않았다
    # 활성 상대와의 충돌에는 덧붙이지 않는다
    make_dataset(api, world, "셋째")
    plain = api(
        "definer", "PATCH", f"/api/datasets/{other}", json={"expected_version": v, "name": "셋째"}
    )
    assert err(plain)["message"] == "같은 팀에 이미 같은 이름의 데이터셋이 있습니다."


def test_name_conflict_hint_also_applies_when_the_unique_constraint_wins_the_race(
    api, world, ds, monkeypatch
):
    """사전 조회를 지나친 경쟁(유일 제약 위반 번역 경로)에서도 상대가 보관이면 문구가 붙는다."""
    from app.dataset import repo

    other = make_dataset(api, world, "다른 이름")["id"]
    assert archive(api, ds["id"]).status_code == 200
    real = repo.find_dataset_name_conflict
    calls = {"pre": True}

    def blind_then_real(session, team_id, name, exclude_id=None):
        if calls["pre"]:
            calls["pre"] = False
            return None  # 사전 조회는 못 본 척 -> INSERT/UPDATE가 제약에 걸린다
        return real(session, team_id, name, exclude_id)

    monkeypatch.setattr(repo, "find_dataset_name_conflict", blind_then_real)
    created = api(
        "definer",
        "POST",
        "/api/datasets",
        json={"team_id": world.team_a, "name": "보관 시험", "date_unit": "month"},
    )
    assert (created.status_code, err(created)["code"]) == (409, "ALREADY_EXISTS")
    assert ARCHIVED_NAME_HINT in err(created)["message"]
    calls["pre"] = True
    renamed = api(
        "definer",
        "PATCH",
        f"/api/datasets/{other}",
        json={"expected_version": version(api, other), "name": "보관 시험"},
    )
    assert (renamed.status_code, err(renamed)["code"]) == (409, "ALREADY_EXISTS")
    assert ARCHIVED_NAME_HINT in err(renamed)["message"]


# --- 감사 ----


def test_one_audit_row_each_with_team_id_and_no_def_version(api, db, world, ds):
    before = audit_rows(db)
    assert archive(api, ds["id"]).status_code == 200
    assert restore(api, ds["id"]).status_code == 200
    a, r = audit_rows(db)[len(before) :]
    for row, action in ((a, "dataset.archive"), (r, "dataset.restore")):
        assert row["action"] == action
        assert (row["target_type"], row["target_id"]) == ("dataset", ds["id"])
        assert (row["actor_source"], row["actor_user_id"]) == ("user", world.ids["definer"])
        assert row["details"] == {"target_name": "보관 시험", "team_id": world.team_a}
    assert audit_rows_of(db, "dataset.archive") == [a]


def test_active_dataset_stale_version_beats_invalid_rules_on_b5(api, ds):
    """B5의 규칙·태그 검증(422)은 잠금 아래라 활성 데이터셋에서도 낡은 버전(409)이 먼저다."""
    bad = {"display_name": "열", "type": "number", "rules": {"min": "abc"}}
    stale = api(
        "definer",
        "POST",
        f"/api/datasets/{ds['id']}/columns",
        json={**bad, "expected_version": version(api, ds["id"]) + 5},
    )
    assert (stale.status_code, err(stale)["code"]) == (409, "DEFINITION_VERSION_MISMATCH")
    fresh = api(
        "definer",
        "POST",
        f"/api/datasets/{ds['id']}/columns",
        json={**bad, "expected_version": version(api, ds["id"])},
    )
    assert (fresh.status_code, err(fresh)["code"]) == (422, "VALIDATION_ERROR")
