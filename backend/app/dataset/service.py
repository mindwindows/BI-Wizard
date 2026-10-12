"""데이터셋·열 정의 로직(05 §2-2 B1~B6, 06). 트랜잭션은 여기서 명시적으로 commit/rollback한다.

- 등록(B2)은 `datasets` 행 INSERT + `ds_<번호>` 원본 표 생성(`ddl`)을 **한 트랜잭션**으로 한다. 어느
  한쪽이 실패하면 둘 다 롤백된다(PostgreSQL DDL은 트랜잭션 안에서 되돌려진다).
- 정의를 바꾸는 B4~B6은 정의 변경 진입점(`definition.apply_definition_change`)을 지난다.
- 권한은 router가 판정한다(정의(팀) = 그 데이터셋 팀의 `definer`, 관리자라도 소속이 아니면 불가).
- 동기 상태는 읽지 않는다(04 §3). 커밋 뒤 동기화 요청은 router가 `DatasetSyncPort`로 한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app import ddl
from app.auth.models import CurrentUser
from app.auth.permissions import can_define, can_enter
from app.core.db_errors import sqlstate
from app.core.errors import (
    FieldErrorCode,
    already_exists,
    column_locked,
    dataset_has_rows,
    definition_version_mismatch,
    not_found,
    validation_failed,
)
from app.core.ports import DefinitionHooks
from app.core.timefmt import to_kst_iso
from app.dataset import repo, rules
from app.dataset.definition import (
    ROW_WRITE_LOCK_TIMEOUT,
    apply_definition_change,
    set_lock_timeout,
    translate_db_error,
)
from app.dataset.hashing import structure_hash

# 기준 날짜 열 규칙을 거는 DDL이 기존 값 때문에 실패하는 SQLSTATE: NOT NULL·CHECK·유일 위반.
_PERIOD_RULE_VIOLATIONS = frozenset({"23502", "23514", "23505"})
_DATASET_NAME_TAKEN = "같은 팀에 이미 같은 이름의 데이터셋이 있습니다."
_COLUMN_NAME_TAKEN = "이 데이터셋에 이미 같은 이름의 열이 있습니다."


@dataclass(frozen=True)
class RowColumn:
    """행 입력(entry)이 읽는 열 정의."""

    id: int
    display_name: str
    type: str
    kind: str
    required: bool
    rules: dict[str, Any] | None


@dataclass(frozen=True)
class RowContext:
    """행 읽기·쓰기가 쓰는 데이터셋 정의 한 장면(열은 `position`, `id` 순서)."""

    dataset_id: int
    team_id: int
    date_unit: str
    base_date_column_id: int | None
    def_version: int
    columns: tuple[RowColumn, ...]


@dataclass(frozen=True)
class ColumnChange:
    """B5·B6 결과: 정의가 바뀌었는지, 응답용 열, 정의 버전."""

    changed: bool
    column: dict[str, Any]
    def_version: int


# --- 읽기 ----


def _column_dict(row: RowMapping) -> dict[str, Any]:
    return dict(row)


def _dataset_dict(row: RowMapping) -> dict[str, Any]:
    return {
        "id": row["id"],
        "team_id": row["team_id"],
        "name": row["name"],
        "date_unit": row["date_unit"],
        "base_date_column_id": row["base_date_column_id"],
        "status": row["status"],
        "def_version": row["def_version"],
        "created_by": {"id": row["created_by"], "display_name": row["created_by_name"]},
        "created_at": to_kst_iso(row["created_at"]),
    }


def list_datasets(
    session: Session, user: CurrentUser, *, team_id: int | None, limit: int, offset: int
) -> tuple[list[dict[str, Any]], int]:
    mine = [m.team_id for m in user.memberships]
    rows, total = repo.list_datasets(
        session, my_team_ids=mine, team_id=team_id, limit=limit, offset=offset
    )
    return [_dataset_dict(r) for r in rows], total


def get_dataset_team_id(session: Session, dataset_id: int) -> int:
    """권한 판정용: 데이터셋이 속한 팀(`team_id`는 DB가 불변으로 강제한다). 없으면 404."""
    row = repo.get_dataset(session, dataset_id)
    if row is None:
        raise not_found()
    return int(row["team_id"])


def get_dataset_detail(session: Session, user: CurrentUser, dataset_id: int) -> dict[str, Any]:
    row = repo.get_dataset(session, dataset_id)
    if row is None:
        raise not_found()
    team = repo.get_team(session, row["team_id"])
    if team is None:  # FK가 보장하므로 일어나지 않는다.
        raise not_found()
    data = _dataset_dict(row)
    data["team"] = dict(team)
    data["columns"] = [_column_dict(c) for c in repo.list_columns(session, dataset_id)]
    data["permissions"] = {
        "define": can_define(user, row["team_id"]),
        "enter": can_enter(user, row["team_id"]),
    }
    return data


def _row_context(session: Session, row: RowMapping) -> RowContext:
    columns = tuple(
        RowColumn(
            id=c["id"],
            display_name=c["display_name"],
            type=c["type"],
            kind=c["kind"],
            required=c["required"],
            rules=c["rules"],
        )
        for c in repo.list_columns(session, row["id"])
    )
    return RowContext(
        dataset_id=row["id"],
        team_id=row["team_id"],
        date_unit=row["date_unit"],
        base_date_column_id=row["base_date_column_id"],
        def_version=int(row["def_version"]),
        columns=columns,
    )


def read_row_context(session: Session, dataset_id: int) -> RowContext:
    """행 조회(C1)용: 잠금 없이 정의를 읽는다. 데이터셋이 없으면 404."""
    row = repo.get_dataset(session, dataset_id)
    if row is None:
        raise not_found()
    return _row_context(session, row)


def lock_row_context(session: Session, dataset_id: int, expected_version: int) -> RowContext:
    """행 쓰기(C2~C4)의 첫 단계(04 §5, 06 §5): `datasets` 행을 `FOR SHARE`로 잠그고 버전을 확인한다.

    `lock_timeout`(코드 상수)을 걸고, 잠근 **뒤에** 정의(열 목록)를 읽는다. 버전이 다르면 잠금을
    풀고 409 `DEFINITION_VERSION_MISMATCH`다. 락 대기 초과·교착(`55P03`·`40P01`)은 DBAPIError로
    올라가며 호출한 쪽(entry service)이 `WRITE_BUSY`로 바꾼다. 잠금은 커밋·롤백할 때 풀린다.
    """
    set_lock_timeout(session, ROW_WRITE_LOCK_TIMEOUT)
    locked = repo.lock_dataset_shared(session, dataset_id)
    if locked is None:
        session.rollback()
        raise not_found()
    if int(locked["def_version"]) != expected_version:
        current = int(locked["def_version"])
        session.rollback()
        raise definition_version_mismatch(current)
    return _row_context(session, locked)


# --- B2 등록 ----


def create_dataset(
    session: Session,
    hooks: DefinitionHooks,
    user: CurrentUser,
    *,
    team_id: int,
    name: str,
    date_unit: str,
) -> int:
    """데이터셋 등록 + 원본 표 생성(한 트랜잭션). 새 데이터셋 번호를 돌려준다."""
    try:
        set_lock_timeout(session)
        if repo.get_team(session, team_id) is None:
            session.rollback()
            raise not_found()
        if repo.find_dataset_name_conflict(session, team_id, name):
            session.rollback()
            raise already_exists("name", _DATASET_NAME_TAKEN)
        dataset_id = repo.insert_dataset(
            session,
            team_id=team_id,
            name=name,
            date_unit=date_unit,
            created_by=user.id,
            def_hash=structure_hash([]),
        )
        ddl.create_dataset_table(session.connection(), dataset_id)
        hooks.run(session, dataset_id)
        session.commit()
    except DBAPIError as error:
        translated = translate_db_error(session, error)
        if translated is not None:
            raise translated from None
        raise
    except BaseException:
        session.rollback()  # 등록 행과 원본 표 생성이 함께 되돌려진다.
        raise
    return dataset_id


# --- B4 데이터셋 수정 ----


def _check_base_column(session: Session, dataset_id: int, column_id: int) -> None:
    column = repo.get_column(session, dataset_id, column_id)
    if column is None or column["kind"] != "raw" or column["type"] != "date":
        raise validation_failed([("base_date_column_id", FieldErrorCode.BAD_FORMAT)])


def update_dataset(
    session: Session,
    hooks: DefinitionHooks,
    dataset_id: int,
    *,
    expected_version: int,
    name: str | None,
    date_unit: str | None,
    base_given: bool,
    base_date_column_id: int | None,
) -> tuple[bool, int]:
    """이름·날짜 단위·기준 날짜 열을 바꾼다. (바뀌었는가, 정의 버전)을 돌려준다."""

    def change(locked: RowMapping) -> tuple[bool, dict[str, Any]]:
        updates: dict[str, Any] = {}
        if name is not None and name != locked["name"]:
            if repo.find_dataset_name_conflict(
                session, locked["team_id"], name, exclude_id=dataset_id
            ):
                raise already_exists("name", _DATASET_NAME_TAKEN)
            updates["name"] = name
        new_unit = date_unit if date_unit is not None else locked["date_unit"]
        old_base = locked["base_date_column_id"]
        new_base = base_date_column_id if base_given else old_base
        unit_changed = new_unit != locked["date_unit"]
        base_changed = new_base != old_base
        if unit_changed or base_changed:
            # 기존 값의 기간·유일성 검증을 피하려고 행이 0개일 때만 바꾼다(06 §3-3).
            if repo.dataset_has_rows(session, dataset_id):
                raise dataset_has_rows()
            if base_changed and new_base is not None:
                _check_base_column(session, dataset_id, new_base)
            connection = session.connection()
            if old_base is not None:
                ddl.drop_period_rules(connection, dataset_id, old_base)
            if new_base is not None:
                try:
                    ddl.add_period_rules(connection, dataset_id, new_base, new_unit)
                except DBAPIError as error:
                    # 잠금 아래에서 행이 0개임을 확인했으므로 일어나지 않아야 한다. 그래도 값이
                    # 들어와 NOT NULL·CHECK·유일 인덱스가 실패하면 500 대신 같은 422로 답한다.
                    if sqlstate(error) in _PERIOD_RULE_VIOLATIONS:
                        raise dataset_has_rows() from None
                    raise
            if unit_changed:
                updates["date_unit"] = new_unit
            if base_changed:
                updates["base_date_column_id"] = new_base
        if not updates:
            return False, {}
        repo.update_dataset(session, dataset_id, updates)
        return True, {}

    outcome = apply_definition_change(
        session, hooks, dataset_id, expected_version=expected_version, change=change
    )
    return outcome.changed, outcome.def_version


# --- B5 열 추가 ----


def _clean_rules_and_tag(
    column_type: str, raw_rules: dict[str, Any] | None, raw_tag: Any
) -> tuple[dict[str, Any] | None, str | None]:
    normalized, problems = rules.normalize_rules(column_type, raw_rules)
    tag, tag_problem = rules.clean_tag(raw_tag)
    if tag_problem is not None:
        problems.append(("tag", tag_problem))
    elif tag is not None and column_type != "number":
        problems.append(("tag", FieldErrorCode.BAD_FORMAT))  # 구분 태그는 숫자 열에만 붙인다.
    if problems:
        raise validation_failed(problems)
    return normalized, tag


def add_column(
    session: Session,
    hooks: DefinitionHooks,
    dataset_id: int,
    *,
    expected_version: int,
    display_name: str,
    column_type: str,
    required: bool,
    raw_rules: dict[str, Any] | None,
    raw_tag: Any,
    position: int | None,
) -> ColumnChange:
    """원본 열을 추가한다: 정의 행 + 원본 표 열을 한 트랜잭션으로 만든다."""
    normalized_rules, tag = _clean_rules_and_tag(column_type, raw_rules, raw_tag)

    def change(locked: RowMapping) -> tuple[bool, dict[str, Any]]:
        if repo.find_column_name_conflict(session, dataset_id, display_name):
            raise already_exists("display_name", _COLUMN_NAME_TAKEN)
        last = repo.max_position(session, dataset_id)
        column_id = repo.insert_column(
            session,
            dataset_id=dataset_id,
            display_name=display_name,
            column_type=column_type,
            required=required,
            rules=normalized_rules,
            tag=tag,
            position=position if position is not None else (0 if last is None else last + 1),
        )
        ddl.add_raw_column(session.connection(), dataset_id, column_id, column_type)
        return True, {"column_id": column_id}

    outcome = apply_definition_change(
        session, hooks, dataset_id, expected_version=expected_version, change=change
    )
    column = repo.get_column(session, dataset_id, outcome.result["column_id"])
    assert column is not None  # noqa: S101 - 방금 커밋한 행
    return ColumnChange(True, _column_dict(column), outcome.def_version)


# --- B6 열 수정 ----


def update_column(
    session: Session,
    hooks: DefinitionHooks,
    dataset_id: int,
    column_id: int,
    *,
    expected_version: int,
    fields: set[str],
    values: dict[str, Any],
) -> ColumnChange:
    """표시 이름·필수·규칙·태그·순서를 바꾼다. `type`·`kind`는 바꿀 수 없다(`COLUMN_LOCKED`).

    `fields`는 요청이 보낸 필드 이름 집합, `values`는 그 값이다(보낸 것만 바꾼다).
    """

    def change(locked: RowMapping) -> tuple[bool, dict[str, Any]]:
        current = repo.get_column(session, dataset_id, column_id)
        if current is None:
            raise not_found()
        for locked_field in ("type", "kind"):
            if locked_field in fields and values[locked_field] != current[locked_field]:
                raise column_locked()
        updates: dict[str, Any] = {}
        problems: list[rules.Problem] = []
        if "display_name" in fields and values["display_name"] != current["display_name"]:
            if repo.find_column_name_conflict(
                session, dataset_id, values["display_name"], exclude_id=column_id
            ):
                raise already_exists("display_name", _COLUMN_NAME_TAKEN)
            updates["display_name"] = values["display_name"]
        if "required" in fields and values["required"] != current["required"]:
            if values["required"] and current["kind"] != "raw":
                problems.append(("required", FieldErrorCode.BAD_FORMAT))  # 계산 열은 필수일 수 없다
            else:
                updates["required"] = values["required"]
        if "rules" in fields:
            if current["kind"] == "raw":
                new_rules, rule_problems = rules.normalize_rules(current["type"], values["rules"])
            else:  # 계산 열에는 검증 규칙이 없다(결과 형은 수식이 정한다).
                new_rules = None
                rule_problems = [("rules", FieldErrorCode.BAD_FORMAT)] if values["rules"] else []
            problems.extend(rule_problems)
            if not rule_problems and new_rules != current["rules"]:
                updates["rules"] = new_rules
        if "tag" in fields:
            tag, tag_problem = rules.clean_tag(values["tag"])
            if tag_problem is not None:
                problems.append(("tag", tag_problem))
            elif tag is not None and current["type"] != "number":
                problems.append(("tag", FieldErrorCode.BAD_FORMAT))
            elif tag != current["tag"]:
                updates["tag"] = tag
        if "position" in fields and values["position"] != current["position"]:
            updates["position"] = values["position"]
        if problems:
            raise validation_failed(problems)
        if not updates:
            return False, {}
        repo.update_column(session, column_id, updates)
        return True, {}

    outcome = apply_definition_change(
        session, hooks, dataset_id, expected_version=expected_version, change=change
    )
    column = repo.get_column(session, dataset_id, column_id)
    assert column is not None  # noqa: S101 - 존재를 change에서 확인했다
    return ColumnChange(outcome.changed, _column_dict(column), outcome.def_version)
