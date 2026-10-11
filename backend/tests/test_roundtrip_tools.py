"""왕복 시험 도구(`migrations/roundtrip.py`)의 정규화·비교·기대값 판정을 DB 없이 점검한다."""

import copy

from migrations.roundtrip import diff, expect_bootstrap_state, expect_privileges, normalize


def _snapshot(*, granted: bool, version_table: bool = False) -> dict:
    schema_acl = ["bi_owner=UC/bi_owner"]
    default_acl = []
    if granted:
        schema_acl += ["bi_app=UC/bi_owner", "bi_readonly=U/bi_owner"]
        default_acl = [
            ["bi_app", "bi_data", "r", ["bi_app=arwdDxt/bi_app", "bi_readonly=r/bi_app"]]
        ]
    return {
        "roles": [
            ["bi_app", False, True, False, False, True, False, None],
            ["bi_owner", False, True, False, False, True, False, None],
            [
                "bi_readonly",
                False,
                True,
                False,
                False,
                True,
                False,
                ["default_transaction_read_only=on", "statement_timeout=30s"],
            ],
        ],
        "memberships": [["bi_app", "bi_owner", "False", "True", "False"]],
        "schemas": [
            ["bi_data", "bi_owner", sorted(schema_acl)],
            ["public", "pg_database_owner", ["=U/pg_database_owner", "pg_database_owner=UC/x"]],
        ],
        "relations": (
            [
                ["public", "alembic_version", "r", "bi_owner", None],
                ["public", "alembic_version_pkc", "i", "bi_owner", None],
            ]
            if version_table
            else []
        ),
        "default_acl": default_acl,
        "public_tables": ({"alembic_version": {"columns": []}} if version_table else {}),
        "alembic_version": [] if version_table else None,
    }


def test_bootstrap_state_passes_for_expected_snapshot():
    assert expect_bootstrap_state(_snapshot(granted=False)) == []


def test_bootstrap_state_reports_superuser_missing_membership_and_timeout():
    snap = _snapshot(granted=False)
    snap["roles"][0][1] = True  # bi_app이 슈퍼유저
    snap["roles"][2][7] = ["default_transaction_read_only=on"]  # statement_timeout 없음
    snap["memberships"] = []
    problems = expect_bootstrap_state(snap)
    assert any("bi_app" in p and "속성" in p for p in problems)
    assert any("statement_timeout=30s" in p for p in problems)
    assert any("멤버" in p for p in problems)


def test_privileges_expected_at_head_and_absent_at_base():
    assert expect_privileges(_snapshot(granted=True), granted=True) == []
    assert expect_privileges(_snapshot(granted=False), granted=False) == []
    assert len(expect_privileges(_snapshot(granted=False), granted=True)) == 3
    assert len(expect_privileges(_snapshot(granted=True), granted=False)) == 3


def test_normalize_schema_acl_null_equals_owner_explicit():
    explicit = _snapshot(granted=False)
    null_acl = copy.deepcopy(explicit)
    null_acl["schemas"][0][2] = None  # NULL ACL = 소유자 기본 권한
    assert diff(normalize(explicit), normalize(null_acl)) == []
    # 정규화 없이는 다르다(복원 안 되는 차이로 알려진 것).
    assert diff(explicit, null_acl)


def test_normalize_ignores_empty_alembic_version_but_not_other_differences():
    before = _snapshot(granted=False, version_table=False)
    after = _snapshot(granted=False, version_table=True)
    assert diff(normalize(before), normalize(after)) == []
    changed = copy.deepcopy(after)
    changed["relations"].append(["public", "teams", "r", "bi_owner", None])
    assert diff(normalize(before), normalize(changed))


def test_diff_detects_privilege_left_behind():
    base = _snapshot(granted=False)
    leftover = _snapshot(granted=True)
    problems = diff(normalize(base), normalize(leftover))
    assert any(p.startswith("schemas") for p in problems)
    assert any(p.startswith("default_acl") for p in problems)
