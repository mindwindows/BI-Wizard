"""감사 기록 쓰기(`record`)와 관리자 목록 조회(05 F1). 04 §5-1, 06 §2-1.

`record`는 **커밋·롤백을 하지 않는다**. 호출한 service가 `session.commit()` **앞에서** 부르고
INSERT가 실패하면 변경도 실패한다(같은 트랜잭션, 감사 없는 변경은 없다). 행위자는 `CurrentUser`
(포털 요청, `actor_source=user`) 또는 `CLI_ACTOR`(서버 명령, 행위자 NULL)뿐이고 그 외는 오류다.
`details`는 `actions.ACTIONS`의 허용 키 표와 정확히 맞아야 하며 어긋나면 `AuditRecordError`
(구현 오류)를 올린다: 자르거나 고쳐 쓰지 않는다. 오류 메시지에는 값을 넣지 않는다(행위·키 이름만).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.audit import repo
from app.audit.actions import (
    ACTIONS,
    BOOL,
    CHANGE_FROM,
    CHANGE_TO,
    CHANGES_KEY,
    INT,
    INT_OR_NULL,
    MAX_TEXT_CHARS,
    STR,
    STR_OR_NULL,
    TARGET_NAME_KEY,
    ActionSpec,
)
from app.auth import CurrentUser
from app.auth.names import display_names
from app.core.timefmt import KST, to_kst_iso
from app.db_metadata import AUDIT_DETAILS_MAX_BYTES


class AuditRecordError(Exception):
    """감사 기록을 쓸 수 없는 호출(허용 키 밖, 형 오류, 알 수 없는 행위자). 구현 오류다."""


class CliActor:
    """서버 명령(`python -m app.cli`)이 행위자임을 밝히는 표식. 행위자 번호는 비어 있다."""

    __slots__ = ()


CLI_ACTOR = CliActor()
Actor = CurrentUser | CliActor


def _fail(action: str, reason: str) -> AuditRecordError:
    return AuditRecordError(f"감사 기록을 쓸 수 없다({action}): {reason}")


_SAFE_NAME = re.compile(r"[a-z][a-z_]{0,39}")


def _names(keys: Iterable[Any]) -> list[str]:
    """오류 메시지용 키 이름. 코드 식별자 모양이 아니면 값이 섞였을 수 있어 이름을 싣지 않는다."""
    return sorted(
        k if isinstance(k, str) and _SAFE_NAME.fullmatch(k) else "<식별자가 아닌 키>" for k in keys
    )


def _check_scalar(action: str, name: str, value: Any, kind: str) -> None:
    ok: bool
    if value is None:
        ok = kind in (INT_OR_NULL, STR_OR_NULL)
    elif kind in (INT, INT_OR_NULL):
        ok = type(value) is int
    elif kind in (STR, STR_OR_NULL):
        ok = type(value) is str and len(value) <= MAX_TEXT_CHARS
    elif kind == BOOL:
        ok = type(value) is bool
    else:  # 표 정의 오류
        ok = False
    if not ok:
        raise _fail(action, f"`{name}`의 형 또는 길이가 허용 밖이다")


def _check_changes(action: str, spec: ActionSpec, changes: Any) -> None:
    allowed = spec.changes or {}
    if not isinstance(changes, dict):
        raise _fail(action, "`changes`는 객체여야 한다")
    for field_name, pair in changes.items():
        if field_name not in allowed:
            raise _fail(action, f"`changes`에 허용 밖 필드 {_names([field_name])}가 있다")
        if not isinstance(pair, dict) or set(pair) != {CHANGE_FROM, CHANGE_TO}:
            raise _fail(action, f"`changes.{field_name}`는 from·to만 가져야 한다")
        _check_scalar(action, f"changes.{field_name}.from", pair[CHANGE_FROM], allowed[field_name])
        _check_scalar(action, f"changes.{field_name}.to", pair[CHANGE_TO], allowed[field_name])
        if pair[CHANGE_FROM] == pair[CHANGE_TO] and type(pair[CHANGE_FROM]) is type(
            pair[CHANGE_TO]
        ):
            raise _fail(action, f"`changes.{field_name}`가 실제로 바뀐 값이 아니다")


def _serialized_size(details: Mapping[str, Any]) -> int:
    """DB `details::text`와 같은 모양(구분자 뒤 공백, 글자는 그대로)으로 직렬화한 바이트 수."""
    return len(json.dumps(details, ensure_ascii=False, separators=(", ", ": ")).encode("utf-8"))


def validate_details(action: str, target_name: str, details: Mapping[str, Any]) -> dict[str, Any]:
    """허용 키 표와 대조한 `details`(`target_name` 포함)를 돌려준다. 어긋나면 `AuditRecordError`."""
    spec = ACTIONS.get(action)
    if spec is None:
        raise _fail(action, "알 수 없는 행위다")
    full: dict[str, Any] = {TARGET_NAME_KEY: target_name, **details}
    if TARGET_NAME_KEY in details:
        raise _fail(action, "`target_name`은 인자로만 준다")
    actual, expected = set(full), set(spec.detail_keys)
    if actual != expected:
        raise _fail(
            action,
            f"허용 키와 다르다(밖 {_names(actual - expected)}, 빠짐 {_names(expected - actual)})",
        )
    _check_scalar(action, TARGET_NAME_KEY, target_name, STR)
    if not target_name:
        raise _fail(action, "`target_name`이 비어 있다")
    for name, kind in spec.keys.items():
        _check_scalar(action, name, full[name], kind)
    if spec.changes is not None:
        _check_changes(action, spec, full[CHANGES_KEY])
        if not full[CHANGES_KEY] and not any(full[flag] for flag in spec.change_flags):
            raise _fail(action, "바뀐 것이 없다(`changes` 비어 있음)")
    if _serialized_size(full) > AUDIT_DETAILS_MAX_BYTES:
        raise _fail(action, f"`details`가 {AUDIT_DETAILS_MAX_BYTES}바이트를 넘는다")
    return full


def record(
    session: Session,
    *,
    actor: Actor,
    action: str,
    target_id: int,
    target_name: str,
    details: Mapping[str, Any],
) -> None:
    """감사 행 한 건을 **호출한 쪽의 트랜잭션**에 INSERT한다(커밋·롤백 없음).

    `target_type`은 행위 표가 정한다. `details`에는 `target_name`을 넣지 않고 인자로 준다.
    """
    full = validate_details(action, target_name, details)
    if type(target_id) is not int or target_id < 1:
        raise _fail(action, "`target_id`가 양의 정수가 아니다")
    if isinstance(actor, CurrentUser):
        actor_user_id: int | None = actor.id
        actor_source = "user"
    elif isinstance(actor, CliActor):
        actor_user_id, actor_source = None, "cli"
    else:
        raise _fail(action, "행위자가 CurrentUser도 서버 명령 표식도 아니다")
    repo.insert_entry(
        session,
        actor_user_id=actor_user_id,
        actor_source=actor_source,
        action=action,
        target_type=ACTIONS[action].target_type,
        target_id=target_id,
        details=full,
    )


# --- F1 목록 ----


def _day_start_kst(day: date) -> datetime | None:
    """한국 시간 그날 00:00을 UTC로. 표현할 수 없는 아주 이른 날짜(0001-01-01)는 None(하한 없음)."""
    try:
        return datetime(day.year, day.month, day.day, tzinfo=KST).astimezone(UTC)
    except OverflowError:
        return None


def list_logs(
    session: Session,
    *,
    date_from: date | None,
    date_to: date | None,
    actor_user_id: int | None,
    target_type: str | None,
    target_id: int | None,
    action: str | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    """F1: 한국 시간 기준 `from`은 그날 00:00부터, `to`는 그날 24:00 전까지(그날 포함)."""
    occurred_from = _day_start_kst(date_from) if date_from is not None else None
    occurred_before = None
    if date_to is not None and date_to < date.max:
        occurred_before = _day_start_kst(date_to + timedelta(days=1))
    rows, total = repo.list_entries(
        session,
        occurred_from=occurred_from,
        occurred_before=occurred_before,
        actor_user_id=actor_user_id,
        target_type=target_type,
        target_id=target_id,
        action=action,
        limit=limit,
        offset=offset,
    )
    names = display_names(session, [r["actor_user_id"] for r in rows if r["actor_user_id"]])
    items = [
        {
            "id": int(r["id"]),
            "occurred_at": to_kst_iso(r["occurred_at"]),
            "actor": (
                {"id": int(r["actor_user_id"]), "display_name": names.get(r["actor_user_id"], "")}
                if r["actor_user_id"] is not None
                else None
            ),
            "actor_source": r["actor_source"],
            "action": r["action"],
            "target_type": r["target_type"],
            "target_id": int(r["target_id"]),
            "details": dict(r["details"]),
        }
        for r in rows
    ]
    session.rollback()  # 읽기뿐이라 트랜잭션을 돌려준다.
    return items, total
