"""`audit.record`와 허용 키 표(`audit.actions`)의 단위 시험(04 §5-1, 06 §2-1).

- 행위 20개의 허용 키 표가 04 §5-1 표와 같다(키 이름이 곧 계약이다).
- 목록 밖 키·빠진 키·틀린 형·긴 글자·알 수 없는 행위자는 구현 오류(`AuditRecordError`)이고 DB에
  아무것도 쓰지 않는다. 자르거나 고쳐 쓰지 않는다.
- 가장 긴 값으로 채워도 `details`가 4,000바이트 안이다(DB CHECK는 안전망일 뿐 정상 경로에서
  닿지 않는다).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app import audit
from app.audit import CLI_ACTOR, AuditRecordError
from app.audit import service as audit_service
from app.audit.actions import (
    ACTIONS,
    BOOL,
    INT,
    INT_OR_NULL,
    MAX_TEXT_CHARS,
    STR,
    STR_OR_NULL,
    ActionSpec,
)
from app.auth.models import CurrentUser
from app.db_metadata import AUDIT_ACTIONS, AUDIT_DETAILS_MAX_BYTES
from tests.audit_helpers import audit_rows
from tests.conftest import Db

# 04 §5-1 표의 "허용 details 키(target_name 외)"를 그대로 옮긴 것이다. 구현 표와 따로 적어 대조한다.
DOC_KEYS = {
    "dataset.create": ({"team_id", "date_unit", "def_version"}, None),
    "dataset.update": (
        {"team_id", "def_version"},
        {"name", "date_unit", "base_date_column_id"},
    ),
    "dataset.archive": ({"team_id"}, None),  # 보관·복구는 정의 버전을 올리지 않는다(FU-2b)
    "dataset.restore": ({"team_id"}, None),
    "column.add": ({"column_id", "column_name", "column_type", "required", "def_version"}, None),
    "column.update": (
        {"column_id", "column_name", "rules_changed", "def_version"},
        {"display_name", "required", "tag", "position"},
    ),
    "formula_column.add": (
        {"column_id", "column_name", "result_type", "ast_hash", "def_version"},
        None,
    ),
    "formula_column.update": (
        {
            "column_id",
            "column_name",
            "result_type",
            "result_type_changed",
            "ast_hash_from",
            "ast_hash",
            "def_version",
        },
        None,
    ),
    "team.create": ({"code"}, None),
    "team.update": (set(), {"name", "is_active"}),
    "member.set": ({"user_id", "role", "role_from"}, None),
    "member.remove": ({"user_id", "role_from"}, None),
    "user.create": ({"is_admin"}, None),
    "user.update": ({"display_name_changed"}, {"is_admin", "is_active"}),
    "user.bootstrap_admin": ({"is_admin"}, None),
    "dashboard.create": ({"embedded_uuid"}, None),
    "dashboard.update": (set(), {"name", "is_active"}),
    # FU-3: 기준값(포털 전역 설정값)은 행 값이 아니다. 설명 원문은 기록하지 않고 길이만 남긴다.
    "reference.create": ({"description_length"}, None),
    "reference_value.add": ({"year", "value"}, None),
    "reference_value.update": ({"year", "value_from", "value_to"}, None),
}
TARGET_TYPES = {
    "dataset.create": "dataset",
    "dataset.update": "dataset",
    "dataset.archive": "dataset",
    "dataset.restore": "dataset",
    "column.add": "dataset",
    "column.update": "dataset",
    "formula_column.add": "dataset",
    "formula_column.update": "dataset",
    "team.create": "team",
    "team.update": "team",
    "member.set": "team",
    "member.remove": "team",
    "user.create": "user",
    "user.update": "user",
    "user.bootstrap_admin": "user",
    "dashboard.create": "dashboard",
    "dashboard.update": "dashboard",
    "reference.create": "reference",
    "reference_value.add": "reference",
    "reference_value.update": "reference",
}


def sample_value(kind: str, *, long: bool = False, alt: bool = False) -> Any:
    if kind == INT or kind == INT_OR_NULL:
        return 2 if alt else 1
    if kind == STR or kind == STR_OR_NULL:
        return ("나" if alt else "가") * (MAX_TEXT_CHARS if long else 3)
    assert kind == BOOL
    return alt


def sample(spec: ActionSpec, *, long: bool = False) -> dict[str, Any]:
    """`target_name`을 뺀 유효한 `details` 하나."""
    details = {name: sample_value(kind, long=long) for name, kind in spec.keys.items()}
    if spec.changes is not None:
        details["changes"] = {
            name: {
                "from": sample_value(kind, long=long),
                "to": sample_value(kind, long=long, alt=True),
            }
            for name, kind in spec.changes.items()
        }
    return details


def user_actor(user_id: int = 1) -> CurrentUser:
    return CurrentUser(id=user_id, display_name="a", is_active=True, is_admin=True)


# --- 허용 키 표 ----


def test_there_are_twenty_actions_in_the_order_of_the_check_constraint():
    assert tuple(ACTIONS) == AUDIT_ACTIONS and len(ACTIONS) == 20


@pytest.mark.parametrize("action", AUDIT_ACTIONS)
def test_allowed_keys_match_the_contract_table(action):
    spec = ACTIONS[action]
    scalar_keys, change_fields = DOC_KEYS[action]
    assert set(spec.keys) == scalar_keys
    assert (set(spec.changes) if spec.changes is not None else None) == change_fields
    assert spec.target_type == TARGET_TYPES[action]
    expected = {"target_name", *scalar_keys, *({"changes"} if change_fields is not None else set())}
    assert spec.detail_keys == expected


def test_no_action_allows_a_forbidden_key():
    """06 §2-1 ③: 행 값·수식 원문·규칙 값·토큰·비밀번호·rls·SQL·예외 메시지·login_id는 없다."""
    forbidden = (
        "login_id",
        "expression",
        "formula",
        "text",
        "rules",
        "value",
        "values",
        "cells",
        "row",
        "password",
        "token",
        "secret",
        "rls",
        "sql",
        "error",
        "message",
        "last_error",
    )
    # 06 §2-1 ③ 예외: 기준값 항목의 연도 값은 포털 전역 설정값이며 행 값이 아니다. 이 세 키는 기준값
    # 행위 두 개에서만 허용하고 다른 행위·키에는 쓸 수 없다.
    reference_value_keys = {
        "reference_value.add": {"value"},
        "reference_value.update": {"value_from", "value_to"},
    }
    for action, spec in ACTIONS.items():
        names = {*spec.keys, *(spec.changes or {})}
        exempt = reference_value_keys.get(action, set())
        for name in names - exempt:
            assert name not in forbidden, (action, name)
            assert "password" not in name and "token" not in name and "secret" not in name
        assert exempt <= names, action
        assert not (
            names & {"value", "value_from", "value_to"} and action not in reference_value_keys
        ), action
        # 규칙 값은 불리언(rules_changed)으로만, 수식은 열 번호와 해시로만 남는다
        assert all(
            kind in {INT, INT_OR_NULL, STR, STR_OR_NULL, BOOL} for kind in spec.keys.values()
        )


@pytest.mark.parametrize("action", AUDIT_ACTIONS)
def test_a_valid_sample_passes_and_the_worst_case_fits_in_4000_bytes(action):
    spec = ACTIONS[action]
    full = audit_service.validate_details(action, "가" * MAX_TEXT_CHARS, sample(spec, long=True))
    assert set(full) == set(spec.detail_keys)
    # 가장 긴 값(한 글자 100자, 한글은 3바이트)으로 채워도 정상 경로는 안전망 4,000바이트 밑이다
    size = len(json.dumps(full, ensure_ascii=False, separators=(", ", ": ")).encode("utf-8"))
    assert size == audit_service._serialized_size(full)
    assert size < AUDIT_DETAILS_MAX_BYTES, (action, size)
    assert audit_service.validate_details(action, "가", sample(spec))  # 짧은 값도 통과


# --- 구현 오류: 어긋나면 기록하지 않고 예외 ----


def valid(action: str = "team.update") -> dict[str, Any]:
    return sample(ACTIONS[action])


def fail(action: str, target_name: str, details: dict[str, Any]) -> AuditRecordError:
    with pytest.raises(AuditRecordError) as error:
        audit_service.validate_details(action, target_name, details)
    return error.value


@pytest.mark.parametrize("action", AUDIT_ACTIONS)
def test_extra_missing_and_misspelled_keys_are_rejected(action):
    spec = ACTIONS[action]
    good = sample(spec)
    fail(action, "n", {**good, "login_id": "x"})  # 목록 밖 키(금지 항목)
    fail(action, "n", {**good, "extra": 1})
    fail(action, "n", {**good, "target_name": "중복"})  # target_name은 인자로만 준다
    for name in list(good):
        fail(action, "n", {k: v for k, v in good.items() if k != name})  # 빠진 키
        renamed = {(k if k != name else name + "_x"): v for k, v in good.items()}
        fail(action, "n", renamed)  # 철자가 다른 키


def test_unknown_action_is_rejected():
    fail("dataset.delete", "n", {})
    fail("", "n", {})


@pytest.mark.parametrize(
    ("value", "kind"),
    [
        (True, INT),  # bool은 정수가 아니다
        ("1", INT),
        (1.0, INT),
        (None, INT),
        (1, STR),
        (None, STR),
        ("가" * (MAX_TEXT_CHARS + 1), STR),  # 길이 상한
        (1, BOOL),
        ("true", BOOL),
        (None, BOOL),
        ({"a": 1}, STR_OR_NULL),  # 중첩 금지
        (["x"], STR_OR_NULL),
        ("가" * (MAX_TEXT_CHARS + 1), STR_OR_NULL),
    ],
)
def test_scalar_values_must_have_the_declared_type_and_length(value, kind):
    action = next(
        a for a, spec in ACTIONS.items() if kind in spec.keys.values() and not spec.changes
    )
    spec = ACTIONS[action]
    key = next(k for k, v in spec.keys.items() if v == kind)
    fail(action, "n", {**sample(spec), key: value})


def test_nullable_values_accept_null_and_a_hundred_characters():
    ok = audit_service.validate_details(
        "member.set", "팀", {"user_id": 1, "role": "entry", "role_from": None}
    )
    assert ok["role_from"] is None
    audit_service.validate_details(
        "formula_column.update",
        "n",
        {**sample(ACTIONS["formula_column.update"]), "ast_hash_from": None},
    )


def test_target_name_must_be_a_nonempty_short_string():
    base = valid()
    fail("team.update", "", base)
    fail("team.update", "가" * (MAX_TEXT_CHARS + 1), base)
    fail("team.update", None, base)  # type: ignore[arg-type]
    fail("team.update", 5, base)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "changes",
    [
        None,
        [],
        "x",
        {"unknown": {"from": 1, "to": 2}},  # 목록 밖 필드
        {"name": {"from": "가"}},  # to 없음
        {"name": {"from": "가", "to": "나", "x": 1}},  # 키가 더 있다
        {"name": "나"},  # from·to 구조가 아니다
        {"name": {"from": "가", "to": "가"}},  # 실제로 바뀐 값이 아니다
        {"is_active": {"from": True, "to": True}},
        {"name": {"from": "가", "to": ["나"]}},  # 중첩 값
        {"name": {"from": "가", "to": {"v": "나"}}},
        {"is_active": {"from": 0, "to": 1}},  # bool이 아니다
        {"name": {"from": None, "to": "나"}},  # name은 null 불가
    ],
)
def test_changes_must_be_a_flat_set_of_real_from_to_pairs(changes):
    fail("team.update", "n", {"changes": changes})


def test_changes_may_not_be_empty_unless_a_flag_says_something_changed():
    fail("team.update", "n", {"changes": {}})  # 바뀐 것이 없다
    fail("dataset.update", "n", {"team_id": 1, "def_version": 2, "changes": {}})
    fail("dashboard.update", "n", {"changes": {}})
    # 플래그가 참이면 changes가 비어 있어도 된다(규칙 값·표시 이름 값은 changes에 넣지 않는다)
    audit_service.validate_details(
        "column.update",
        "n",
        {
            "column_id": 1,
            "column_name": "열",
            "rules_changed": True,
            "def_version": 3,
            "changes": {},
        },
    )
    audit_service.validate_details(
        "user.update", "n", {"display_name_changed": True, "changes": {}}
    )
    fail(
        "column.update",
        "n",
        {
            "column_id": 1,
            "column_name": "열",
            "rules_changed": False,
            "def_version": 3,
            "changes": {},
        },
    )


def test_a_size_over_the_limit_is_rejected_not_truncated(monkeypatch):
    monkeypatch.setattr(audit_service, "AUDIT_DETAILS_MAX_BYTES", 60)
    error = fail("team.create", "X" * 40, {"code": "team_c"})
    assert "60바이트" in str(error)
    assert "team_c" not in str(error) and "XXXX" not in str(error)  # 메시지에 값이 없다


def test_error_messages_never_contain_values():
    secret = "SUPER-SECRET-VALUE-5521"
    errors = [
        fail("team.update", secret, {"changes": {"name": {"from": secret, "to": [secret]}}}),
        fail("user.create", "n", {"is_admin": secret}),
        fail("user.create", "n", {"is_admin": True, secret: 1}),
        fail("team.create", "n", {"code": secret * 50}),
    ]
    for error in errors:
        assert secret not in str(error), str(error)


# --- record: 행위자와 INSERT ----


def test_record_writes_one_row_for_a_user_actor(db: Db):
    uid = db.add_user("actor", "행위자", is_admin=True)
    with Session(db.engine) as session:
        audit.record(
            session,
            actor=user_actor(uid),
            action="team.create",
            target_id=7,
            target_name="새 팀",
            details={"code": "new_team"},
        )
        session.commit()
    [row] = audit_rows(db)
    assert (row["actor_source"], row["actor_user_id"]) == ("user", uid)
    assert (row["action"], row["target_type"], row["target_id"]) == ("team.create", "team", 7)
    assert row["details"] == {"target_name": "새 팀", "code": "new_team"}


def test_record_writes_a_null_actor_for_the_server_command(db: Db):
    with Session(db.engine) as session:
        audit.record(
            session,
            actor=CLI_ACTOR,
            action="user.bootstrap_admin",
            target_id=1,
            target_name="관리자",
            details={"is_admin": True},
        )
        session.commit()
    [row] = audit_rows(db)
    assert (row["actor_source"], row["actor_user_id"]) == ("cli", None)


@pytest.mark.parametrize("actor", [None, "cli", 1, {"id": 1}, object(), type(CLI_ACTOR)])
def test_record_rejects_anything_that_is_not_a_current_user_or_the_cli_marker(db: Db, actor):
    with Session(db.engine) as session, pytest.raises(AuditRecordError):
        audit.record(
            session,
            actor=actor,  # type: ignore[arg-type]
            action="team.create",
            target_id=1,
            target_name="n",
            details={"code": "c"},
        )
    assert audit_rows(db) == []


@pytest.mark.parametrize("target_id", [0, -1, True, "1", None, 1.0])
def test_record_rejects_a_bad_target_id(db: Db, target_id):
    with Session(db.engine) as session, pytest.raises(AuditRecordError):
        audit.record(
            session,
            actor=CLI_ACTOR,
            action="user.bootstrap_admin",
            target_id=target_id,  # type: ignore[arg-type]
            target_name="n",
            details={"is_admin": True},
        )
    assert audit_rows(db) == []


def test_record_validates_before_writing_anything(db: Db):
    with Session(db.engine) as session:
        with pytest.raises(AuditRecordError):
            audit.record(
                session,
                actor=CLI_ACTOR,
                action="user.bootstrap_admin",
                target_id=1,
                target_name="n",
                details={"is_admin": True, "login_id": "x"},
            )
        session.commit()
    assert audit_rows(db) == []


def test_record_does_not_commit_or_roll_back(db: Db):
    """record는 호출한 쪽의 트랜잭션에 INSERT만 더한다: 커밋하지 않으면 사라진다."""
    with Session(db.engine) as session:
        audit.record(
            session,
            actor=CLI_ACTOR,
            action="user.bootstrap_admin",
            target_id=1,
            target_name="n",
            details={"is_admin": True},
        )
        assert session.in_transaction()
        session.rollback()
    assert audit_rows(db) == []


def test_record_source_has_no_commit_rollback_or_raw_sql():
    """audit 모듈은 commit·rollback·text()·raw SQL을 쓰지 않는다(UPDATE·DELETE 경로도 없다)."""
    import re
    from pathlib import Path

    root = Path(audit.__file__).parent
    for path in root.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        code = re.sub(r'""".*?"""', "", source, flags=re.S)
        code = "\n".join(line.split("#")[0] for line in code.splitlines())
        assert ".commit(" not in code, path.name
        assert "text(" not in code and "exec_driver_sql" not in code, path.name
        assert not re.search(r"\b(update|delete)\(", code), path.name  # 수정·삭제 경로 없음
        if path.name != "service.py":
            assert ".rollback(" not in code, path.name
