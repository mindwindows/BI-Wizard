"""수식·점검 API(05 §2-4 D1~D10). 보호 라우터라 `register_routers`가 `current_user`를 붙인다.

- D1·D6·D7·D8은 인증된 활성 사용자 누구나(타 팀 포함) 읽는다.
- D2~D5는 그 데이터셋 팀의 정의 담당자만(관리자라도 소속 `definer`가 아니면 403, 06 §4-1). 권한
  검사는 의존성이라 본문 검증보다 먼저 실행된다.
- D9·D10은 관리자 전용이다.
- 정의가 바뀌어 커밋된 뒤에만 `DatasetSyncPort`로 동기화를 요청한다(실패해도 응답은 그대로).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.auth import CurrentUserDep
from app.auth.permissions import can_define, require_admin
from app.core.deps import get_session
from app.core.errors import forbidden
from app.core.limits import HeavyReadLimiter
from app.core.pagination import LIST_LIMIT_DEFAULT, LIST_LIMIT_MAX, Page
from app.core.ports import DatasetSyncPort, DefinitionHooks, run_dataset_sync_request
from app.core.timefmt import to_kst_iso
from app.dataset import service as dataset_service
from app.formula import reconcile, service
from app.formula.schemas import (
    CheckOut,
    FormulaCheckBody,
    FormulaCreate,
    FormulaCreatedOut,
    FormulaErrorCellOut,
    FormulaErrorSummaryOut,
    FormulaUpdate,
    FormulaUpdatedOut,
    FormulaViewOut,
    FunctionCatalogOut,
    PreviewOut,
    ViewFailureOut,
    ViewsRetryBody,
    ViewsRetryOut,
    ViewsStatusOut,
)
from app.formula.status import ViewStatus

router = APIRouter(tags=["formula"])

SessionDep = Annotated[Session, Depends(get_session)]
LimitParam = Annotated[int, Query(ge=1, le=LIST_LIMIT_MAX)]
OffsetParam = Annotated[int, Query(ge=0)]


def get_hooks(request: Request) -> DefinitionHooks:
    return request.app.state.definition_hooks


def get_sync(request: Request) -> DatasetSyncPort:
    return request.app.state.dataset_sync


def get_limiter(request: Request) -> HeavyReadLimiter:
    return request.app.state.heavy_reads


def get_status(request: Request) -> ViewStatus:
    return request.app.state.view_status


def get_engine(request: Request) -> Engine:
    return request.app.state.engine


HooksDep = Annotated[DefinitionHooks, Depends(get_hooks)]
SyncDep = Annotated[DatasetSyncPort, Depends(get_sync)]
LimiterDep = Annotated[HeavyReadLimiter, Depends(get_limiter)]
StatusDep = Annotated[ViewStatus, Depends(get_status)]
EngineDep = Annotated[Engine, Depends(get_engine)]


def require_dataset_definer(dataset_id: int, user: CurrentUserDep, session: SessionDep) -> int:
    """정의(팀) 권한: 데이터셋이 없으면 404, 그 팀의 정의 담당자가 아니면 403(관리자도 같다)."""
    team_id = dataset_service.get_dataset_team_id(session, dataset_id)
    if not can_define(user, team_id):
        raise forbidden()
    # 권한 검사가 연 트랜잭션을 돌려준다. 이어지는 본문 읽기·계산이 새 트랜잭션(읽기 전용 설정
    # 포함)을 처음부터 연다.
    session.rollback()
    return dataset_id


DefinerDep = Depends(require_dataset_definer)


@router.get("/formulas/functions")
def get_functions() -> FunctionCatalogOut:
    """D1: 함수 사전에서 자동 생성한 도움말과 셀 오류 문구."""
    return FunctionCatalogOut(**service.functions_catalog())


@router.post("/datasets/{dataset_id}/formulas/check", dependencies=[DefinerDep])
def check_formula(dataset_id: int, body: FormulaCheckBody, session: SessionDep) -> CheckOut:
    """D2: 수식 검사. C0 검사 실패도 200(`ok=false`)이다."""
    return CheckOut(**service.check(session, dataset_id, body.expression, body.column_id))


@router.post("/datasets/{dataset_id}/formulas/preview", dependencies=[DefinerDep])
def preview_formula(
    dataset_id: int,
    body: FormulaCheckBody,
    user: CurrentUserDep,
    session: SessionDep,
    limiter: LimiterDep,
) -> PreviewOut:
    """D3: 저장 없이 일부 행을 계산한다(읽기 전용, 5초, 사용자당 동시 1건 + 전역 상한)."""
    return PreviewOut(
        **service.preview(
            session,
            limiter,
            user_id=user.id,
            dataset_id=dataset_id,
            expression=body.expression,
            column_id=body.column_id,
        )
    )


@router.post("/datasets/{dataset_id}/formulas", status_code=201, dependencies=[DefinerDep])
def create_formula(
    dataset_id: int,
    body: FormulaCreate,
    session: SessionDep,
    hooks: HooksDep,
    sync: SyncDep,
    background: BackgroundTasks,
) -> FormulaCreatedOut:
    """D4: 계산 열 만들기(열 -> 수식·의존·뷰 -> `def_hash`가 한 트랜잭션)."""
    saved = service.create_formula_column(
        session,
        hooks,
        dataset_id,
        expected_version=body.expected_version,
        display_name=body.display_name,
        expression=body.expression,
        tag=body.tag,
        position=body.position,
    )
    background.add_task(run_dataset_sync_request, sync, dataset_id)
    column = dataset_service.get_column_dict(session, dataset_id, saved.column_id)
    return FormulaCreatedOut(column=column, def_version=saved.def_version)


@router.put("/datasets/{dataset_id}/formulas/{col_id}", dependencies=[DefinerDep])
def update_formula(
    dataset_id: int,
    col_id: int,
    body: FormulaUpdate,
    session: SessionDep,
    hooks: HooksDep,
    sync: SyncDep,
    background: BackgroundTasks,
) -> FormulaUpdatedOut:
    """D5: 수식 고치기. 결과 형이 바뀌면 `result_type_changed`가 true다."""
    saved = service.update_formula(
        session,
        hooks,
        dataset_id,
        col_id,
        expected_version=body.expected_version,
        expression=body.expression,
    )
    if saved.def_version != body.expected_version:  # 바뀐 경우에만 동기화를 요청한다
        background.add_task(run_dataset_sync_request, sync, dataset_id)
    column = dataset_service.get_column_dict(session, dataset_id, saved.column_id)
    return FormulaUpdatedOut(
        column=column,
        def_version=saved.def_version,
        result_type_changed=saved.result_type_changed,
    )


@router.get("/datasets/{dataset_id}/formulas/{col_id}")
def get_formula(dataset_id: int, col_id: int, session: SessionDep) -> FormulaViewOut:
    """D6: 수식 보기(현재 열 이름으로 풀어 쓴 형태, 원문 없음)."""
    return FormulaViewOut(**service.view_formula(session, dataset_id, col_id))


@router.get("/checks/formula-errors")
def list_formula_errors(
    session: SessionDep,
    limiter: LimiterDep,
    limit: LimitParam = LIST_LIMIT_DEFAULT,
    offset: OffsetParam = 0,
) -> Page[FormulaErrorSummaryOut]:
    """D7: 오류 칸이 있는 계산 열 목록(S5)."""
    items, total = service.error_summaries(session, limiter, limit=limit, offset=offset)
    return Page[FormulaErrorSummaryOut](items=items, total=total, limit=limit, offset=offset)


@router.get("/datasets/{dataset_id}/formula-errors")
def list_dataset_formula_errors(
    dataset_id: int,
    session: SessionDep,
    limiter: LimiterDep,
    column_id: int | None = None,
    limit: LimitParam = LIST_LIMIT_DEFAULT,
    offset: OffsetParam = 0,
) -> Page[FormulaErrorCellOut]:
    """D8: 데이터셋의 오류 칸 목록."""
    dataset_service.get_dataset_team_id(session, dataset_id)  # 없으면 404
    items, total = service.error_cells(
        session, limiter, dataset_id, column_id, limit=limit, offset=offset
    )
    return Page[FormulaErrorCellOut](items=items, total=total, limit=limit, offset=offset)


@router.get("/checks/views", dependencies=[Depends(require_admin)])
def get_views_status(session: SessionDep, status: StatusDep) -> ViewsStatusOut:
    """D9: 뷰 대조 결과(`/health` 필드와 같은 집계)."""
    failures = status.failures()
    names = {
        f.dataset_id: dataset_service.get_dataset_name(session, f.dataset_id) for f in failures
    }
    session.rollback()
    return ViewsStatusOut(
        views=status.views,
        views_failed_count=status.failed_count,
        failed=[
            ViewFailureOut(
                dataset_id=f.dataset_id,
                dataset_name=names[f.dataset_id] or "",
                reason=f.reason,
                since=to_kst_iso(f.since),
            )
            for f in failures
        ],
    )


@router.post("/checks/views/retry", dependencies=[Depends(require_admin)])
def retry_views(
    body: ViewsRetryBody, engine: EngineDep, hooks: HooksDep, status: StatusDep
) -> ViewsRetryOut:
    """D10: 실패한 뷰를 요청 안에서 끝까지 다시 만든다(해시가 같아도 다시 만든다)."""
    rebuilt = reconcile.retry(engine, hooks, status, body.dataset_ids)
    return ViewsRetryOut(rebuilt=rebuilt, views_failed_count=status.failed_count)
