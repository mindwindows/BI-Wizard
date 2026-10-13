"""이름순 정렬(한글 가나다순, 03b 19-1 결정 2): A2 `/teams`, A5 `/users`, B1 `/datasets`, DV1.

순서 단정은 PostgreSQL 변형(`ko-KR-x-icu`)에서만 한다. SQLite 변형은 정렬을 흉내 내지 않고
같은 항목이 모두 나오는지와 같은 이름의 안정 정렬(`id`)만 확인한다.
"""

import pytest
from sqlalchemy import column, select, table
from sqlalchemy.dialects import postgresql, sqlite

from app.core import sorting
from app.core.sorting import by_name
from tests.conftest import Db

HANGUL = ["가계부", "김비소속", "나눔", "다람", "박재무", "시험 관리자", "이영업"]
# ICU 한계: 숫자는 글자 순서(10이 9보다 앞), 라틴은 한글 뒤, 대소문자는 소문자가 앞.
MIXED = ["10팀", "9팀", "가", "A1", "abc", "Abc"]


# --- DB 없이: 만들어지는 SQL ----


def _sql(dialect) -> str:
    stmt = select(column("name")).select_from(table("t")).order_by(by_name(column("name")))
    return str(stmt.compile(dialect=dialect))


def test_postgresql_order_by_has_the_korean_collation():
    assert 'ORDER BY name COLLATE "ko-KR-x-icu"' in _sql(postgresql.dialect())


def test_other_dialects_get_no_collate():
    assert "COLLATE" not in _sql(sqlite.dialect())


def test_missing_collation_falls_back_to_plain_order():
    sorting.set_collation_available(False)
    try:
        assert "COLLATE" not in _sql(postgresql.dialect())
    finally:
        sorting.set_collation_available(True)


# --- API ----


def _teams(api, who="admin"):
    return [t["name"] for t in api(who, "GET", "/api/teams?limit=200").json()["items"]]


def _users(api, who="admin"):
    return [u["display_name"] for u in api(who, "GET", "/api/users?limit=200").json()["items"]]


def _check(db: Db, got: list[str], expected: list[str]) -> None:
    if db.kind == "pg":
        assert got == expected
    else:
        assert sorted(got) == sorted(expected)


def test_a2_hangul_only_order(api, db: Db, world):
    for n, name in enumerate(
        ["이영업", "가계부", "시험 관리자", "나눔", "박재무", "다람", "김비소속"]
    ):
        db.add_team(f"h{n}", name)
    got = [n for n in _teams(api) if n in HANGUL]
    _check(db, got, ["가계부", "김비소속", "나눔", "다람", "박재무", "시험 관리자", "이영업"])


def test_a2_mixed_latin_digit_hangul_order(api, db: Db, world):
    for n, name in enumerate(["abc", "Abc", "A1", "가", "9팀", "10팀"]):
        db.add_team(f"m{n}", name)
    got = [n for n in _teams(api) if n in MIXED]
    _check(db, got, ["10팀", "9팀", "가", "A1", "abc", "Abc"])


def test_a5_users_are_in_hangul_order(api, db: Db, world):
    for n, name in enumerate(
        ["이영업", "가계부", "시험 관리자", "나눔", "박재무", "다람", "김비소속"]
    ):
        db.add_user(f"u{n}", name)
    got = [n for n in _users(api) if n in HANGUL]
    _check(db, got, ["가계부", "김비소속", "나눔", "다람", "박재무", "시험 관리자", "이영업"])


def test_a5_equal_display_names_are_stable_by_id(api, db: Db, world):
    first = db.add_user("same_a", "동명")
    second = db.add_user("same_b", "동명")
    items = api("admin", "GET", "/api/users?limit=200").json()["items"]
    assert [u["id"] for u in items if u["display_name"] == "동명"] == [first, second]


def test_b1_datasets_my_team_first_then_team_name_then_dataset_name_in_hangul(api, db: Db, world):
    admin = world.ids["admin"]
    team_na = db.add_team("na", "나팀")
    team_ga = db.add_team("ga", "가팀")
    team_da = db.add_team("da", "다팀")
    db.add_member(team_da, world.ids["viewer"], "entry")
    for team, name in [
        (team_na, "하"),
        (team_na, "가"),
        (team_ga, "다"),
        (team_ga, "나"),
        (team_da, "마"),
        (team_da, "바"),
    ]:
        db.add_dataset(team, name, admin)
    items = api("viewer", "GET", "/api/datasets?limit=200").json()["items"]
    got = [(d["team_id"], d["name"]) for d in items]
    expected = [
        (team_da, "마"),
        (team_da, "바"),  # 내 팀 먼저
        (team_ga, "나"),
        (team_ga, "다"),
        (team_na, "가"),
        (team_na, "하"),
    ]
    if db.kind == "pg":
        assert got == expected
    else:
        assert sorted(got) == sorted(expected)
        assert [t for t, _ in got[:2]] == [team_da] * 2  # 내 팀 먼저는 방언과 무관


def test_dv1_stub_users_are_in_display_name_order(api, db: Db, world):
    for n, name in enumerate(["이영업", "가계부", "박재무", "김비소속"]):
        db.add_user(f"s{n}", name)
    items = api(None, "GET", "/api/dev/stub-users").json()["items"]
    got = [u["display_name"] for u in items if u["display_name"] in HANGUL]
    _check(db, got, ["가계부", "김비소속", "박재무", "이영업"])


@pytest.mark.parametrize("who", ["admin", "viewer"])
def test_a1_memberships_are_in_hangul_order(api, db: Db, world, who):
    uid = world.ids[who]
    for n, name in enumerate(["나눔", "가계부", "다람"]):
        db.add_member(db.add_team(f"mm{n}", name), uid, "entry")
    memberships = api(who, "GET", "/api/me").json()["memberships"]
    got = [m["team_name"] for m in memberships if m["team_name"] in {"나눔", "가계부", "다람"}]
    _check(db, got, ["가계부", "나눔", "다람"])
