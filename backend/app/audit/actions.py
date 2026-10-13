"""감사 기록 행위 15개와 `details` 허용 키 표(04 §5-1, 06 §2-1). 이 파일이 허용 키의 유일한 출처다.

- 행위 이름은 `db_metadata.AUDIT_ACTIONS`(= `ck_audit_log_action` CHECK)와 같아야 한다(시험이
  대조한다).
- `details`의 키는 행위마다 정확히 이 표와 같아야 한다(`target_name` 공통). 목록 밖 키·빠진 키·
  틀린 형은 구현 오류이며 변경 전체가 롤백된다(`service.record`가 검사한다).
- 값은 비밀 아닌 스칼라(글자·정수·불리언·null)뿐이고, 중첩은 `changes`(`{필드: {from, to}}`) 하나만
  허용한다. 행 값·수식 원문·검증 규칙 값·토큰·비밀번호·`login_id`는 어느 행위에도 없다.
- 새 행위는 이 표 한 줄 + `AUDIT_ACTIONS`/CHECK 교체 revision + 시험이다.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

# 값의 형. `?`가 붙으면 null도 허용한다. bool은 int가 아니다.
INT, INT_OR_NULL = "int", "int?"
STR, STR_OR_NULL = "str", "str?"
BOOL = "bool"

# 글자 값 상한(06 §2-1 ②: 이미 검증된 표시 이름·코드 값, 한 값 100자 이내).
MAX_TEXT_CHARS = 100

TARGET_NAME_KEY = "target_name"
CHANGES_KEY = "changes"
CHANGE_FROM, CHANGE_TO = "from", "to"


@dataclass(frozen=True)
class ActionSpec:
    target_type: str
    # `target_name` 외 필수 키와 값의 형(`changes`는 아래 `changes`가 따로 정한다)
    keys: Mapping[str, str] = field(default_factory=dict)
    # `changes`를 쓰는 행위만: 허용하는 필드와 값의 형
    changes: Mapping[str, str] | None = None

    @property
    def detail_keys(self) -> frozenset[str]:
        """`details`가 가져야 하는 키 전체(`target_name` 포함)."""
        keys = {TARGET_NAME_KEY, *self.keys}
        if self.changes is not None:
            keys.add(CHANGES_KEY)
        return frozenset(keys)

    @property
    def change_flags(self) -> frozenset[str]:
        """`changes` 밖에서 "바뀌었다"를 알리는 불리언 키(`rules_changed` 등)."""
        return frozenset(k for k in self.keys if k.endswith("_changed") and self.keys[k] == BOOL)


ACTIONS: Mapping[str, ActionSpec] = {
    "dataset.create": ActionSpec("dataset", {"team_id": INT, "date_unit": STR, "def_version": INT}),
    "dataset.update": ActionSpec(
        "dataset",
        {"team_id": INT, "def_version": INT},
        changes={"name": STR, "date_unit": STR, "base_date_column_id": INT_OR_NULL},
    ),
    "column.add": ActionSpec(
        "dataset",
        {
            "column_id": INT,
            "column_name": STR,
            "column_type": STR,
            "required": BOOL,
            "def_version": INT,
        },
    ),
    "column.update": ActionSpec(
        "dataset",
        {"column_id": INT, "column_name": STR, "rules_changed": BOOL, "def_version": INT},
        changes={
            "display_name": STR,
            "required": BOOL,
            "tag": STR_OR_NULL,
            "position": INT,
        },
    ),
    "formula_column.add": ActionSpec(
        "dataset",
        {
            "column_id": INT,
            "column_name": STR,
            "result_type": STR,
            "ast_hash": STR,
            "def_version": INT,
        },
    ),
    "formula_column.update": ActionSpec(
        "dataset",
        {
            "column_id": INT,
            "column_name": STR,
            "result_type": STR,
            "result_type_changed": BOOL,
            "ast_hash_from": STR_OR_NULL,
            "ast_hash": STR,
            "def_version": INT,
        },
    ),
    "team.create": ActionSpec("team", {"code": STR}),
    "team.update": ActionSpec("team", changes={"name": STR, "is_active": BOOL}),
    "member.set": ActionSpec("team", {"user_id": INT, "role": STR, "role_from": STR_OR_NULL}),
    "member.remove": ActionSpec("team", {"user_id": INT, "role_from": STR}),
    "user.create": ActionSpec("user", {"is_admin": BOOL}),
    "user.update": ActionSpec(
        "user",
        {"display_name_changed": BOOL},
        changes={"is_admin": BOOL, "is_active": BOOL},
    ),
    "user.bootstrap_admin": ActionSpec("user", {"is_admin": BOOL}),
    "dashboard.create": ActionSpec("dashboard", {"embedded_uuid": STR}),
    "dashboard.update": ActionSpec("dashboard", changes={"name": STR, "is_active": BOOL}),
}
