"""정의 변경 진입점(04 §5, 06 §3-5·§5, 07 §8). 정의를 바꾸는 모든 경로는 이 함수를 지나간다.

순서는 고정이다:
1. `lock_timeout`을 건다(`ALTER TABLE`은 읽기와 서로 기다리므로 오래 기다리지 않는다).
2. `datasets` 행을 `FOR NO KEY UPDATE` 한 가지 잠금으로 잡는다(advisory 잠금 불사용, 읽기는
   막지 않는다).
2-1. (FU-2b) `bump=True`이고 잠근 행의 `status`가 `archived`면 409 `DATASET_ARCHIVED`로 롤백한다.
   판정은 잠금 직후이며 버전 비교(3)·`change`(검증 422)보다 앞이다. `bump=False`(뷰 재생성·재시도)는
   정의 변경이 아니라 대조 복구이므로 보관 검사를 하지 않는다.
3. `expected_version`이 `def_version`과 다르면 `DEFINITION_VERSION_MISMATCH`(409).
4. 호출한 쪽이 넘긴 `change`가 열 변경(`dataset_columns`, 동적 DDL)을 한다. 바뀐 것이 없으면 버전을
   올리지 않고 끝낸다.
5. 정의 변경 훅(`core.ports.DefinitionHooks`): formula 모듈이 등록해 수식·의존·뷰를 같은
   트랜잭션에서 만들고 뷰 정의 해시를 돌려준다. 등록된 훅이 없으면 no-op이다.
6. `def_version + 1`과 `def_hash`(훅이 돌려준 뷰 정의 해시, 없으면 구조 해시 `hashing.py`)를
   기록한다.
7. 감사 기록(FU-2a, 04 §5-1): 호출한 쪽이 넘긴 `AuditSpec`으로 `audit.record`를 **정확히 한 번**
   부르고 커밋한다. 바뀐 것이 없으면(`changed=False`) 기록도 없다. 버전을 올리는 호출(`bump=True`)은
   `AuditSpec`이 **필수**다(감사 없는 정의 변경 경로가 생기는 것을 막는다, fail-closed). formula 훅·
   repo·내부 helper는 `audit`을 부르지 않는다.
중간에 실패하면(훅·감사 INSERT 포함) 전부 롤백된다(동적 DDL도 같은 트랜잭션이다).

락 대기 초과(`55P03`)·교착(`40P01`)은 503 `DEFINITION_BUSY`(재시도 가능)다. 시작 시 재생성·재시도
(05 D10)는 `expected_version=None`, `bump=False`로 같은 함수를 쓴다(정의는 그대로이고 버전은 올리지
않으며 `lock_timeout`을 더 짧게 줄 수 있다).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, literal, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app import audit
from app.core.db_errors import constraint_name, is_lock_conflict
from app.core.errors import (
    AppError,
    already_exists,
    dataset_archived,
    definition_busy,
    definition_version_mismatch,
    not_found,
)
from app.core.ports import DefinitionHooks
from app.dataset import repo
from app.dataset.hashing import structure_hash

# 정의 변경 락 대기 한도(코드 상수, PostgreSQL `lock_timeout` 표기). 07 §8의 시작값 1초이며 운영
# 부하를 보고 조정한다.
DEFINITION_LOCK_TIMEOUT = "1000ms"
# 행 쓰기(C2~C4) 락 대기 한도(코드 상수). 같은 기간·같은 행을 쓰는 다른 트랜잭션이 끝나기를
# 기다리는 시간이며, 넘으면 503 `WRITE_BUSY`(재시도 가능)다. 붙여넣기는 행마다 잠금을 잡으므로
# 정의 변경보다 길다.
ROW_WRITE_LOCK_TIMEOUT = "3000ms"

# 유일 제약 -> (필드, 문구). 먼저 조회로 막지만 경쟁으로 제약에 걸려도 같은 409로 바꾼다.
_UNIQUE_MESSAGES = {
    "uq_datasets_team_id_name": ("name", "같은 팀에 이미 같은 이름의 데이터셋이 있습니다."),
    "uq_dataset_columns_dataset_id_display_name": (
        "display_name",
        "이 데이터셋에 이미 같은 이름의 열이 있습니다.",
    ),
}
# SQLite 시험 엔진의 위반 메시지 조각 -> 위 제약 이름.
_SQLITE_UNIQUE_HINTS = {
    "datasets.team_id": "uq_datasets_team_id_name",
    "dataset_columns.dataset_id, dataset_columns.display_name": (
        "uq_dataset_columns_dataset_id_display_name"
    ),
}


@dataclass(frozen=True)
class AuditSpec:
    """정의 변경 한 건의 감사 서술(04 §5-1 "행위 서술"): 행위자, 행위 이름, `details` 만드는 함수.

    `build(result, new_version)`은 `change`가 돌려준 값과 변경 뒤 `def_version`을 받아
    (`target_name`, `details`)를 돌려준다. `details`는 `audit.actions`의 허용 키와 같아야 한다.
    """

    actor: audit.Actor
    action: str
    build: Callable[[dict[str, Any], int], tuple[str, dict[str, Any]]]


@dataclass(frozen=True)
class DefinitionOutcome:
    changed: bool
    def_version: int
    result: dict[str, Any]


def set_lock_timeout(session: Session, timeout: str = DEFINITION_LOCK_TIMEOUT) -> None:
    """이 트랜잭션에서만 락 대기 한도를 건다(PostgreSQL). 다른 엔진(SQLite 시험)은 건너뛴다."""
    if session.get_bind().dialect.name != "postgresql":
        return
    session.execute(select(func.set_config("lock_timeout", literal(timeout), True)))


def unique_conflict(error: IntegrityError) -> AppError | None:
    """유일 제약 위반을 409 `ALREADY_EXISTS`로 바꾼다. 우리가 아는 제약이 아니면 None."""
    name = constraint_name(error)
    if name is None:
        message = str(getattr(error, "orig", error))
        name = next((n for hint, n in _SQLITE_UNIQUE_HINTS.items() if hint in message), None)
    if name in _UNIQUE_MESSAGES:
        field, text = _UNIQUE_MESSAGES[name]
        return already_exists(field, text)
    return None


def translate_db_error(session: Session, error: DBAPIError) -> AppError | None:
    """롤백한 뒤 DB 오류를 업무 오류로 바꾼다. 바꿀 수 없으면 None(호출한 쪽이 다시 올린다)."""
    session.rollback()
    if is_lock_conflict(error):
        return definition_busy()
    if isinstance(error, IntegrityError):
        return unique_conflict(error)
    return None


def apply_definition_change(
    session: Session,
    hooks: DefinitionHooks,
    dataset_id: int,
    *,
    expected_version: int | None,
    change: Callable[[RowMapping], tuple[bool, dict[str, Any]]],
    bump: bool = True,
    lock_timeout: str = DEFINITION_LOCK_TIMEOUT,
    audit_spec: AuditSpec | None = None,
) -> DefinitionOutcome:
    """잠금 → 버전 확인 → 열 변경 → 훅 → `def_hash` 기록 → 감사 기록 → 커밋.

    `change(locked)`는 (바뀌었는가, 응답에 쓸 값)을 돌려준다. 바뀌지 않았으면 훅·버전·해시·감사를
    건드리지 않고 롤백(잠금 해제)한다. 업무 오류(`AppError`)는 롤백하고 그대로 올린다.
    """
    if bump and audit_spec is None:
        raise audit.AuditRecordError("감사 서술(audit_spec) 없이 정의 버전을 올릴 수 없다")
    try:
        set_lock_timeout(session, lock_timeout)
        locked = repo.lock_dataset(session, dataset_id)
        if locked is None:
            session.rollback()
            raise not_found()
        if bump and locked["status"] == "archived":
            session.rollback()
            raise dataset_archived()
        current = int(locked["def_version"])
        if expected_version is not None and expected_version != current:
            session.rollback()
            raise definition_version_mismatch(current)
        changed, result = change(locked)
        if not changed:
            session.rollback()
            return DefinitionOutcome(False, current, result)
        view_hash = hooks.run(session, dataset_id)
        new_version = current + 1 if bump else current
        repo.update_dataset(
            session,
            dataset_id,
            {
                "def_version": new_version,
                "def_hash": view_hash or structure_hash(repo.list_columns(session, dataset_id)),
            },
        )
        if audit_spec is not None:
            target_name, details = audit_spec.build(result, new_version)
            audit.record(
                session,
                actor=audit_spec.actor,
                action=audit_spec.action,
                target_id=dataset_id,
                target_name=target_name,
                details=details,
            )
        session.commit()
        return DefinitionOutcome(True, new_version, result)
    except AppError:
        session.rollback()
        raise
    except DBAPIError as error:
        translated = translate_db_error(session, error)
        if translated is not None:
            raise translated from None
        raise
    except BaseException:
        session.rollback()
        raise
