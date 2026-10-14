"""Superset 동기 상태·대시보드 연결·입장권 API(05 §2-5 E1~E6). 보호 라우터라 `current_user`가
붙는다.

- E1·E3·E6은 인증된 활성 사용자 누구나, E2·E4·E5는 관리자만(`require_admin`) 쓴다. 권한 검사는
  의존성이라
  본문·쿼리 검증보다 먼저 실행된다.
- E6은 포털 대시보드 `id`만 받는다(본문이 있으면 422). `rls`·Superset 번호·uuid는 받지 않는다.
  응답은 `Cache-Control: no-store`이고 토큰은 로그에 남지 않는다.
- 동기화는 요청 처리 중에 Superset을 부르지 않는다. E2는 `pending` 표시와 큐 투입만 하고
  접수(202)한다.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.auth import CurrentUser, CurrentUserDep
from app.auth.permissions import require_admin
from app.core.deps import get_session
from app.core.errors import FieldErrorCode, validation_failed
from app.core.pagination import LIST_LIMIT_DEFAULT, LIST_LIMIT_MAX, Page
from app.core.ports import DatasetSyncPort, run_dataset_sync_request
from app.superset import service
from app.superset.runtime import SupersetServices
from app.superset.schemas import (
    DashboardCreate,
    DashboardOut,
    DashboardUpdate,
    GuestTokenOut,
    SupersetDatasetOut,
    SyncAccepted,
    SyncRequest,
    SyncStatus,
)

router = APIRouter(tags=["superset"])

SessionDep = Annotated[Session, Depends(get_session)]
AdminDep = Depends(require_admin)
# E4·E5는 행위자(감사 기록)가 필요해 의존성의 사용자를 받는다. 권한 검사는 본문 검증보다 먼저다.
AdminUser = Annotated[CurrentUser, Depends(require_admin)]
LimitParam = Annotated[int, Query(ge=1, le=LIST_LIMIT_MAX)]
OffsetParam = Annotated[int, Query(ge=0)]
# E1 데이터셋 번호 필터 상한(쿼리 길이 보호).
_MAX_FILTER_IDS = 200


def get_dataset_sync(request: Request) -> DatasetSyncPort:
    return request.app.state.dataset_sync


def get_services(request: Request) -> SupersetServices | None:
    return request.app.state.superset


SyncDep = Annotated[DatasetSyncPort, Depends(get_dataset_sync)]
ServicesDep = Annotated[SupersetServices | None, Depends(get_services)]


async def require_empty_body(request: Request, user: CurrentUserDep) -> None:
    """E6: 본문이 없어야 한다(있으면 422). 인증이 먼저(401·403)이고 첫 조각만 보고 판단한다."""
    del user  # 인증 의존성을 본문 검사보다 먼저 풀기 위한 인자
    async for chunk in request.stream():
        if chunk:
            raise validation_failed([("body", FieldErrorCode.BAD_FORMAT)])


def _parse_ids(dataset_id: list[int] | None, dataset_ids: str | None) -> list[int] | None:
    ids: list[int] = list(dataset_id or [])
    if dataset_ids:
        try:
            ids.extend(int(part) for part in dataset_ids.split(",") if part.strip())
        except ValueError:
            raise validation_failed([("dataset_ids", FieldErrorCode.BAD_FORMAT)]) from None
    if dataset_id is None and not dataset_ids:
        return None
    if len(ids) > _MAX_FILTER_IDS or any(i < 1 for i in ids):
        raise validation_failed([("dataset_ids", FieldErrorCode.OUT_OF_RANGE)])
    return sorted(set(ids))


@router.get("/superset/datasets")
def list_sync_states(
    user: CurrentUserDep,
    session: SessionDep,
    dataset_id: Annotated[list[int] | None, Query()] = None,
    dataset_ids: Annotated[str | None, Query(max_length=2000)] = None,
    team_id: int | None = None,
    sync_status: SyncStatus | None = None,
    limit: LimitParam = LIST_LIMIT_DEFAULT,
    offset: OffsetParam = 0,
) -> Page[SupersetDatasetOut]:
    """E1: 데이터셋별 동기 상태(읽기). 등록 행이 없으면 `pending`, `last_error`는 관리자만."""
    items, total = service.list_sync_states(
        session,
        user,
        dataset_ids=_parse_ids(dataset_id, dataset_ids),
        team_id=team_id,
        sync_status=sync_status,
        limit=limit,
        offset=offset,
    )
    return Page[SupersetDatasetOut](
        items=[SupersetDatasetOut(**item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/superset/sync", status_code=202, dependencies=[AdminDep])
def request_sync(
    session: SessionDep,
    sync: SyncDep,
    body: SyncRequest | None = None,
) -> SyncAccepted:
    """E2: 동기화를 접수한다(관리자). 결과는 E1로 확인한다. Superset이 멈춰 있어도 접수는
    성공한다."""
    targets = service.resolve_sync_targets(session, body.dataset_ids if body else None)
    session.close()
    for dataset_id in targets:
        run_dataset_sync_request(sync, dataset_id)
    return SyncAccepted(accepted=targets)


@router.get("/dashboards")
def list_dashboards(
    user: CurrentUserDep,
    session: SessionDep,
    include_inactive: bool = False,
    limit: LimitParam = LIST_LIMIT_DEFAULT,
    offset: OffsetParam = 0,
) -> Page[DashboardOut]:
    """E3: 연결된 대시보드 목록(읽기). `include_inactive`는 관리자만 쓸 수 있다."""
    items, total = service.list_dashboards(
        session, user, include_inactive=include_inactive, limit=limit, offset=offset
    )
    return Page[DashboardOut](
        items=[DashboardOut(**item) for item in items], total=total, limit=limit, offset=offset
    )


@router.post("/dashboards", status_code=201)
def create_dashboard(body: DashboardCreate, session: SessionDep, admin: AdminUser) -> DashboardOut:
    """E4: 대시보드 등록(관리자). uuid는 앞뒤 공백을 지우고 소문자로 바꿔 저장한다."""
    return DashboardOut(
        **service.create_dashboard(session, admin, name=body.name, embedded_uuid=body.embedded_uuid)
    )


@router.patch("/dashboards/{dashboard_id}")
def update_dashboard(
    dashboard_id: int, body: DashboardUpdate, session: SessionDep, admin: AdminUser
) -> DashboardOut:
    """E5: 이름·활성 변경(관리자). uuid는 바꿀 수 없다."""
    sent = body.model_fields_set
    return DashboardOut(
        **service.update_dashboard(
            session,
            admin,
            dashboard_id,
            name=body.name if "name" in sent else None,
            is_active=body.is_active if "is_active" in sent else None,
        )
    )


@router.post(
    "/dashboards/{dashboard_id}/guest-token",
    dependencies=[Depends(require_empty_body)],
)
def issue_guest_token(
    dashboard_id: int,
    user: CurrentUserDep,
    session: SessionDep,
    services: ServicesDep,
    response: Response,
) -> GuestTokenOut:
    """E6: 입장권 발급(읽기). 활성 대시보드의 등록 uuid로만 발급하고 사용자별 속도 제한이 있다."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    result = service.issue_guest_token(
        session,
        user,
        dashboard_id,
        issuer=services.issuer if services else None,
        limiter=services.limiter if services else None,
    )
    return GuestTokenOut(**result)
