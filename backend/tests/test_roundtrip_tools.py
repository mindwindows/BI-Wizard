"""왕복 시험 도구(`migrations/roundtrip.py`)의 정규화·비교·기대값 판정을 DB 없이 점검한다."""

import copy

from migrations.roundtrip import (
    ACCESS_COLUMN_ACL,
    ACCESS_TABLE_ACL,
    DATASET_COLUMN_ACL,
    DATASET_TABLE_ACL,
    STATIC_COLUMN_ACL,
    STATIC_TABLE_ACL,
    diff,
    expect_bootstrap_state,
    expect_privileges,
    expect_static_privileges,
    normalize,
)


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


# --- 정적 표 권한(0003 + 0004) ----


def _static_snapshot(*, access: bool, dataset: bool) -> dict:
    """정적 표와 `bi_app` 권한이 있는 가짜 스냅샷."""
    snap = _snapshot(granted=True)
    relations = []
    column_acl = []
    groups = []
    if access:
        groups.append((ACCESS_TABLE_ACL, ACCESS_COLUMN_ACL))
    if dataset:
        groups.append((DATASET_TABLE_ACL, DATASET_COLUMN_ACL))
    for tables, columns in groups:
        for name, acl in tables.items():
            relations.append(["public", name, "r", "bi_owner", [acl, "bi_owner=arwdDxt/bi_owner"]])
        for table, column in sorted(columns):
            column_acl.append(["public", table, column, ["bi_app=w/bi_owner"]])
    snap["relations"] = relations
    snap["column_acl"] = column_acl
    return snap


def test_static_privileges_cover_access_and_dataset_tables():
    assert set(STATIC_TABLE_ACL) == {
        "users",
        "teams",
        "team_members",
        "datasets",
        "dataset_columns",
    }
    assert STATIC_COLUMN_ACL == ACCESS_COLUMN_ACL | DATASET_COLUMN_ACL
    # 불변 열은 UPDATE 권한 열 목록에 없다(06 §2).
    immutable = {
        ("datasets", "team_id"),
        ("datasets", "created_by"),
        ("datasets", "created_at"),
        ("datasets", "id"),
        ("dataset_columns", "dataset_id"),
        ("dataset_columns", "kind"),
        ("dataset_columns", "id"),
    }
    assert not immutable & DATASET_COLUMN_ACL
    # 계산 열 결과 형 때문에 type은 갱신할 수 있다(원본 열 금지는 앱 규칙).
    assert ("dataset_columns", "type") in DATASET_COLUMN_ACL
    # DELETE는 team_members에만 있다.
    assert [n for n, acl in STATIC_TABLE_ACL.items() if "d" in acl.split("=")[1].split("/")[0]] == [
        "team_members"
    ]


def test_static_privileges_expected_at_head_and_absent_at_base():
    head = _static_snapshot(access=True, dataset=True)
    assert expect_static_privileges(head, granted=True) == []
    base = _static_snapshot(access=False, dataset=False)
    assert expect_static_privileges(base, granted=False) == []
    assert expect_static_privileges(base, granted=True)
    assert expect_static_privileges(head, granted=False)


def test_static_privileges_per_revision_for_the_0004_step():
    """0004 한 단계: 0003 상태에서는 권한 관리 표만 있고 데이터셋 표는 없다."""
    mid = _static_snapshot(access=True, dataset=False)
    assert (
        expect_static_privileges(
            mid, granted=True, table_acl=ACCESS_TABLE_ACL, column_acl=ACCESS_COLUMN_ACL
        )
        == []
    )
    assert (
        expect_static_privileges(
            mid, granted=False, table_acl=DATASET_TABLE_ACL, column_acl=DATASET_COLUMN_ACL
        )
        == []
    )
    head = _static_snapshot(access=True, dataset=True)
    assert expect_static_privileges(
        head, granted=False, table_acl=DATASET_TABLE_ACL, column_acl=DATASET_COLUMN_ACL
    )


def test_static_privileges_detect_wrong_acl_and_extra_column_grant():
    head = _static_snapshot(access=True, dataset=True)
    wide = _static_snapshot(access=True, dataset=True)
    wide["column_acl"].append(["public", "datasets", "team_id", ["bi_app=w/bi_owner"]])
    assert any("열 단위" in p for p in expect_static_privileges(wide, granted=True))
    delete = _static_snapshot(access=True, dataset=True)
    for row in delete["relations"]:
        if row[1] == "datasets":
            row[4][0] = "bi_app=ard/bi_owner"  # DELETE가 붙었다
    assert any("datasets 표 ACL" in p for p in expect_static_privileges(delete, granted=True))
    readonly = _static_snapshot(access=True, dataset=True)
    readonly["relations"][3][4].append("bi_readonly=r/bi_owner")
    assert any("표 ACL" in p for p in expect_static_privileges(readonly, granted=True))
    assert expect_static_privileges(head, granted=True) == []
