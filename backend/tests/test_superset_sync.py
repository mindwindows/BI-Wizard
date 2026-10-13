"""데이터셋 하나의 동기화 절차(sync_dataset)와 대조(is_in_sync) 시험 — DB 없이 가짜 Superset으로."""

import httpx
import pytest

from app.superset.errors import SupersetRejected
from app.superset.sync import SyncPlan, is_in_sync, sync_dataset
from tests.fake_superset import new_fake
from tests.superset_helpers import make_api

SQL1 = "SELECT * FROM bi_data.dv_1"


def plan(name="[영업팀] 월간", labels=None):
    return SyncPlan(
        dataset_id=1, name=name, sql=SQL1, display_names=labels or {1: "매출", 2: "비용"}
    )


def fake_with_view(*extra):
    fake = new_fake()
    fake.views[1] = ["team", "row_id", "c_1", "c_2", *extra]
    return fake


def labels_of(fake, dataset_id=1):
    return {c["column_name"]: c["verbose_name"] for c in fake.datasets[dataset_id]["columns"]}


def run(api, the_plan, stored=None, created=None):
    return sync_dataset(
        api,
        the_plan,
        stored_id=stored,
        on_created=(created.append if created is not None else lambda _id: None),
    )


def test_first_sync_registers_with_full_labels_and_records_the_id_immediately():
    fake = fake_with_view()
    created: list[int] = []
    superset_id = run(make_api(fake), plan(), created=created)
    assert superset_id == 1 and created == [1]
    assert fake.datasets[1]["table_name"] == "[영업팀] 월간"
    assert fake.datasets[1]["sql"] == SQL1
    assert labels_of(fake) == {"team": "팀", "row_id": "행 번호", "c_1": "매출", "c_2": "비용"}
    assert len(fake.datasets[1]["columns"]) == 4
    # 새로 만든 데이터셋은 방금 열을 읽었으므로 새로고침을 부르지 않는다.
    assert fake.count("PUT", "/api/v1/dataset/1/refresh") == 0


def test_resync_is_idempotent_one_dataset_and_column_ids_unchanged():
    fake = fake_with_view()
    api = make_api(fake)
    created: list[int] = []
    run(api, plan(), created=created)
    ids_before = [c["id"] for c in fake.datasets[1]["columns"]]
    for stored in (None, 1):  # 보관한 번호가 없어도(크래시 뒤) 고정 SQL로 찾는다
        assert run(api, plan(), stored=stored, created=created) == 1
    assert len(fake.datasets) == 1 and created == [1]
    assert [c["id"] for c in fake.datasets[1]["columns"]] == ids_before
    assert fake.count("PUT", "/api/v1/dataset/1/refresh") == 2


def test_every_put_sends_the_full_column_list_and_never_loses_columns():
    """03c A-27: `columns`는 교체다. 일부 열만 보내는 호출이 없고 열 수·id가 변하지 않는다."""
    fake = fake_with_view()
    api = make_api(fake)
    run(api, plan())
    fake.views[1].append("c_3")  # 계산 열이 하나 늘어난 뷰
    before = {c["column_name"]: c["id"] for c in fake.datasets[1]["columns"]}
    run(api, plan(labels={1: "매출", 2: "비용", 3: "이익"}), stored=1)
    after = {c["column_name"]: c["id"] for c in fake.datasets[1]["columns"]}
    assert len(after) == 5 and all(after[name] == column_id for name, column_id in before.items())
    assert labels_of(fake)["c_3"] == "이익" and labels_of(fake)["c_1"] == "매출"
    for call in (c for c in fake.calls if c.method == "PUT" and c.path == "/api/v1/dataset/1"):
        sent = {c["column_name"] if "column_name" in c else c["id"] for c in call.body["columns"]}
        assert len(call.body["columns"]) == len(sent) >= 4
        assert all(set(c) == {"id", "column_name", "verbose_name"} for c in call.body["columns"])
    last = [c for c in fake.calls if c.method == "PUT" and c.path == "/api/v1/dataset/1"][-1]
    assert len(last.body["columns"]) == 5  # 전체 열을 보냈다


def test_unknown_superset_columns_keep_their_existing_labels():
    fake = fake_with_view("c_77")  # 정의에 없는 번호의 열
    api = make_api(fake)
    run(api, plan())
    fake.datasets[1]["columns"][-1]["verbose_name"] = "수동으로 붙인 이름"
    run(api, plan(), stored=1)
    assert labels_of(fake)["c_77"] == "수동으로 붙인 이름"


def test_rename_updates_the_same_dataset_in_place():
    fake = fake_with_view()
    api = make_api(fake)
    run(api, plan())
    run(api, plan(name="[새 팀] 월간"), stored=1)
    assert len(fake.datasets) == 1 and fake.datasets[1]["table_name"] == "[새 팀] 월간"


def test_lost_stored_id_falls_back_to_fixed_sql_lookup():
    fake = fake_with_view()
    api = make_api(fake)
    run(api, plan())
    assert run(api, plan(), stored=999) == 1  # 보관한 번호가 Superset에 없다(404)
    assert len(fake.datasets) == 1


def test_duplicate_name_with_same_sql_is_adopted_and_with_other_sql_is_a_conflict():
    fake = fake_with_view()
    api = make_api(fake)
    # 같은 SQL이 다른 이름으로 이미 있으면 SQL로 찾아 이름을 바꾼다(중복 등록 없음).
    api.create(database_id=1, schema="bi_data", name="옛 이름", sql=SQL1)
    assert run(api, plan()) == 1 and len(fake.datasets) == 1
    assert fake.datasets[1]["table_name"] == "[영업팀] 월간"
    # 같은 이름이 다른 SQL로 있으면 이름 충돌이다(관리자가 먼저 만든 경우).
    fake2 = fake_with_view()
    api2 = make_api(fake2)
    api2.create(
        database_id=1, schema="bi_data", name="[영업팀] 월간", sql="SELECT * FROM bi_data.dv_9"
    )
    with pytest.raises(SupersetRejected) as error:
        run(api2, plan())
    assert error.value.code == "NAME_CONFLICT"


def test_database_mismatch_is_reported_by_code():
    fake = fake_with_view()
    fake.dataset_database_name = "다른 연결"
    with pytest.raises(SupersetRejected) as error:
        run(make_api(fake), plan())
    assert error.value.code == "DB_MISMATCH"


def test_missing_view_is_a_reason_code_on_create_and_refresh():
    fake = fake_with_view()
    api = make_api(fake)
    fake.missing_views.add(1)
    with pytest.raises(SupersetRejected) as error:
        run(api, plan())
    assert error.value.code == "REJECTED_422"
    fake.missing_views.clear()
    run(api, plan())
    fake.missing_views.add(1)
    with pytest.raises(SupersetRejected) as error:
        run(api, plan(), stored=1)
    assert error.value.code == "VIEW_MISSING"


def test_foreign_owner_is_not_owner():
    fake = fake_with_view()
    api = make_api(fake)
    run(api, plan())
    fake.foreign_datasets.add(1)
    with pytest.raises(SupersetRejected) as error:
        run(api, plan(), stored=1)
    assert error.value.code == "NOT_OWNER"


def test_columns_do_not_exist_422_is_retried_once_after_rereading():
    fake = fake_with_view()
    api = make_api(fake)
    run(api, plan())
    fake.respond_once(
        lambda c: c.method == "PUT" and c.path == "/api/v1/dataset/1",
        lambda c: httpx.Response(
            422, json={"message": {"columns": ["One or more columns do not exist"]}}
        ),
    )
    assert run(api, plan(), stored=1) == 1
    puts = [c for c in fake.calls if c.method == "PUT" and c.path == "/api/v1/dataset/1"]
    assert len(puts) == 3  # 최초 + (실패 1회) + 재시도 1회

    for _ in range(2):
        fake.respond_once(
            lambda c: c.method == "PUT" and c.path == "/api/v1/dataset/1",
            lambda c: httpx.Response(
                422, json={"message": {"columns": ["One or more columns do not exist"]}}
            ),
        )
    with pytest.raises(SupersetRejected) as error:
        run(api, plan(), stored=1)
    assert error.value.code == "REJECTED_422"


def test_is_in_sync_detects_each_kind_of_drift():
    fake = fake_with_view()
    api = make_api(fake)
    p = plan()
    run(api, p)
    assert is_in_sync(api, p, 1) is True
    assert is_in_sync(api, p, None) is False
    assert is_in_sync(api, p, 404) is False
    # 이름이 다르다(팀 이름 변경 직후 크래시)
    assert is_in_sync(api, plan(name="[다른 팀] 월간"), 1) is False
    # 열이 늘었다(뷰는 바뀌었는데 Superset 새로고침 전 크래시)
    assert is_in_sync(api, plan(labels={1: "매출", 2: "비용", 3: "이익"}), 1) is False
    # 열 표시 이름이 다르다
    assert is_in_sync(api, plan(labels={1: "매출액", 2: "비용"}), 1) is False
    # 읽기만 한다
    puts_before = fake.count("PUT", "/api/v1/dataset/")
    is_in_sync(api, p, 1)
    assert fake.count("PUT", "/api/v1/dataset/") == puts_before
