"""Superset 등록·대시보드 연결·입장권 발급 로직(05 §2-5 E1~E6). 트랜잭션은 여기서 명시적으로
한다.

감사 기록(FU-2a, 04 §5-1): 대시보드 연결 등록(E4)·변경(E5)만 쓰기 함수 끝(커밋 앞)에서 한 번
기록한다. 값이 같은 E5는 쓰지도 기록하지도 않는다(0건). 입장권 발급(E6)·동기 상태 변경은 기록하지
않는다(03b 29-1 ②).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import audit
from app.auth.models import CurrentUser
from app.auth.permissions import is_admin
from app.core.errors import (
    AppError,
    FieldErrorCode,
    already_exists,
    forbidden,
    guest_token_rate_limited,
    not_found,
    superset_rejected,
    superset_unavailable,
    validation_failed,
)
from app.core.timefmt import to_kst_iso
from app.dataset import service as dataset_service
from app.superset import repo
from app.superset.constants import GUEST_TOKEN_EXPIRES_IN
from app.superset.errors import SupersetRejected, SupersetUnavailable
from app.superset.naming import superset_name
from app.superset.ratelimit import SlidingWindowLimiter
from app.superset.tokens import GuestTokenIssuer

_DUPLICATE_UUID = "이미 등록된 대시보드 번호입니다."


# --- E1·E2: 동기 상태 ----


def list_sync_states(
    session: Session,
    user: CurrentUser,
    *,
    dataset_ids: list[int] | None,
    team_id: int | None,
    sync_status: str | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    """E1: 데이터셋마다 동기 상태 한 줄. 등록 행이 없는 데이터셋은 `pending`이다.

    `last_error`(사유)는 관리자에게만 보인다. 목록은 팀 이름·데이터셋 이름순이다.
    """
    sources = dataset_service.list_sync_names(session, dataset_ids=dataset_ids, team_id=team_id)
    rows = repo.all_sync_rows(session)
    admin = is_admin(user)
    items: list[dict[str, Any]] = []
    for source in sources:
        row = rows.get(source.dataset_id)
        status = row["sync_status"] if row is not None else "pending"
        if sync_status is not None and status != sync_status:
            continue
        items.append(
            {
                "dataset_id": source.dataset_id,
                "superset_name": (
                    row["display_name"]
                    if row is not None
                    else superset_name(source.team_name, source.name)
                ),
                "sync_status": status,
                "synced_at": to_kst_iso(row["synced_at"]) if row and row["synced_at"] else None,
                "last_error": row["last_error"] if admin and row is not None else None,
            }
        )
    return items[offset : offset + limit], len(items)


def resolve_sync_targets(session: Session, dataset_ids: list[int] | None) -> list[int]:
    """E2: 동기화를 접수할 데이터셋 번호. 번호를 주면 모두 있어야 하고(없으면 404), 생략하면
    `pending`·`failed`·등록 행 없음 전부다."""
    if dataset_ids is not None:
        wanted = sorted(set(dataset_ids))
        found = {s.dataset_id for s in dataset_service.list_sync_names(session, dataset_ids=wanted)}
        if found != set(wanted):
            raise not_found()
        return wanted
    rows = repo.all_sync_rows(session)
    return sorted(
        s.dataset_id
        for s in dataset_service.list_sync_names(session)
        if rows.get(s.dataset_id) is None or rows[s.dataset_id]["sync_status"] != "registered"
    )


# --- E3~E5: 대시보드 연결 ----


def _dashboard_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "embedded_uuid": str(row["embedded_uuid"]),
        "is_active": bool(row["is_active"]),
    }


def list_dashboards(
    session: Session, user: CurrentUser, *, include_inactive: bool, limit: int, offset: int
) -> tuple[list[dict[str, Any]], int]:
    """E3: 활성 대시보드 목록. `include_inactive`는 관리자만 쓸 수 있다(비관리자는 403)."""
    if include_inactive and not is_admin(user):
        raise forbidden()
    rows, total = repo.list_dashboards(
        session, include_inactive=include_inactive, limit=limit, offset=offset
    )
    return [_dashboard_dict(r) for r in rows], total


def create_dashboard(
    session: Session, actor: CurrentUser, *, name: str, embedded_uuid: str
) -> dict[str, Any]:
    """E4: 대시보드 등록. 같은 번호는 409 `ALREADY_EXISTS`(`details.field=embedded_uuid`)."""
    value = uuid.UUID(embedded_uuid)
    if repo.find_dashboard_by_uuid(session, value) is not None:
        raise already_exists("embedded_uuid", _DUPLICATE_UUID)
    try:
        row = repo.insert_dashboard(session, name=name, embedded_uuid=value)
        # uuid는 E3가 모두에게 공개하는 값이라 기록해도 된다(04 §5-1).
        audit.record(
            session,
            actor=actor,
            action="dashboard.create",
            target_id=row["id"],
            target_name=row["name"],
            details={"embedded_uuid": str(row["embedded_uuid"])},
        )
        session.commit()
    except IntegrityError:
        session.rollback()
        if repo.find_dashboard_by_uuid(session, value) is not None:
            raise already_exists("embedded_uuid", _DUPLICATE_UUID) from None
        raise
    except BaseException:
        session.rollback()
        raise
    return _dashboard_dict(row)


def update_dashboard(
    session: Session,
    actor: CurrentUser,
    dashboard_id: int,
    *,
    name: str | None,
    is_active: bool | None,
) -> dict[str, Any]:
    """E5: 이름·활성 변경(uuid 불변). 둘 다 없으면 422, 없는 대상은 404.

    행을 잠가 쓰기 전 값을 읽고, 값이 같은 항목은 쓰지 않는다(전부 같으면 UPDATE도 감사 기록도
    없다). `is_active`가 `true`→`false`면 화면이 "연결 해제"로 읽는다.
    """
    wanted: dict[str, Any] = {}
    if name is not None:
        wanted["name"] = name
    if is_active is not None:
        wanted["is_active"] = is_active
    if not wanted:
        raise validation_failed([("body", FieldErrorCode.REQUIRED)])
    try:
        current = repo.get_dashboard(session, dashboard_id, lock=True)
        if current is None:
            session.rollback()
            raise not_found()
        values = {k: v for k, v in wanted.items() if current[k] != v}
        if not values:
            session.rollback()  # 바뀐 것이 없다: 쓰지도 기록하지도 않는다(잠금 해제)
            return _dashboard_dict(current)
        row = repo.update_dashboard(session, dashboard_id, values)
        audit.record(
            session,
            actor=actor,
            action="dashboard.update",
            target_id=dashboard_id,
            target_name=row["name"],
            details={"changes": {k: {"from": current[k], "to": v} for k, v in values.items()}},
        )
        session.commit()
    except AppError:
        raise
    except BaseException:
        session.rollback()
        raise
    return _dashboard_dict(row)


# --- E6: 입장권 ----


def issue_guest_token(
    session: Session,
    user: CurrentUser,
    dashboard_id: int,
    *,
    issuer: GuestTokenIssuer | None,
    limiter: SlidingWindowLimiter | None,
) -> dict[str, Any]:
    """E6: 사용자별 속도 제한 → 활성 대시보드 확인(없음·비활성 404) → Superset 발급.

    제한 검사는 404 판정보다 앞이다(없는 번호를 두드리는 정찰도 제한한다). 토큰은 반환값 외 어디에도
    남기지 않는다. Superset을 부르기 전에 DB 연결을 돌려준다.
    """
    if limiter is not None:
        retry_after = limiter.acquire(user.id)
        if retry_after is not None:
            raise guest_token_rate_limited(retry_after)
    row = repo.get_dashboard(session, dashboard_id)
    if row is None or not row["is_active"]:
        raise not_found()
    embedded_uuid = row["embedded_uuid"]
    session.close()  # HTTP 호출 동안 연결 풀(5개)을 점유하지 않는다.
    if issuer is None:
        raise superset_unavailable()
    try:
        token = issuer.issue(username=str(user.id), dashboard_uuid=embedded_uuid)
    except SupersetUnavailable:
        raise superset_unavailable() from None
    except SupersetRejected:
        raise superset_rejected() from None
    return {"token": token, "expires_in": GUEST_TOKEN_EXPIRES_IN}
