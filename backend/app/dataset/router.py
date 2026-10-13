"""데이터셋·열 정의 API(05 §2-2 B1~B6).

보호 라우터라 `register_routers`가 `current_user`를 붙인다.

- B1·B3는 인증된 활성 사용자 누구나(타 팀 포함) 읽는다.
- B2는 `team_id` 팀의 정의 담당자만, B4~B6은 그 데이터셋 팀의 정의 담당자만 쓴다. 관리자라도 그 팀의
  `definer`가 아니면 거부한다(06 §4-1). B4~B6의 권한 검사는 의존성이라 본문 검증보다 먼저 실행된다.
  B2는 팀이 본문에 있어 본문 검증 뒤에 검사한다.
- 정의가 바뀌어 커밋된 뒤에만 `DatasetSyncPort`로 동기화를 요청한다(백그라운드, 실패해도 응답은
  그대로).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy.orm import Session

from app.auth import CurrentUserDep
from app.auth.permissions import can_define
from app.core.deps import get_session
from app.core.errors import forbidden
from app.core.pagination import LIST_LIMIT_DEFAULT, LIST_LIMIT_MAX, Page
from app.core.ports import DatasetSyncPort, DefinitionHooks, run_dataset_sync_request
from app.dataset import service
from app.dataset.schemas import (
    ColumnCreate,
    ColumnOut,
    ColumnResult,
    ColumnUpdate,
    DatasetCreate,
    DatasetDetailOut,
    DatasetOut,
    DatasetUpdate,
)

router = APIRouter(tags=["dataset"])

SessionDep = Annotated[Session, Depends(get_session)]
LimitParam = Annotated[int, Query(ge=1, le=LIST_LIMIT_MAX)]
OffsetParam = Annotated[int, Query(ge=0)]


def get_dataset_sync(request: Request) -> DatasetSyncPort:
    return request.app.state.dataset_sync


def get_definition_hooks(request: Request) -> DefinitionHooks:
    return request.app.state.definition_hooks


SyncDep = Annotated[DatasetSyncPort, Depends(get_dataset_sync)]
HooksDep = Annotated[DefinitionHooks, Depends(get_definition_hooks)]


def require_dataset_definer(dataset_id: int, user: CurrentUserDep, session: SessionDep) -> int:
    """정의(팀) 권한: 데이터셋이 없으면 404, 그 팀의 정의 담당자가 아니면 403(관리자도 같다)."""
    team_id = service.get_dataset_team_id(session, dataset_id)
    if not can_define(user, team_id):
        raise forbidden()
    return dataset_id


DefinerDep = Depends(require_dataset_definer)


@router.get("/datasets")
def list_datasets(
    user: CurrentUserDep,
    session: SessionDep,
    team_id: int | None = None,
    limit: LimitParam = LIST_LIMIT_DEFAULT,
    offset: OffsetParam = 0,
) -> Page[DatasetOut]:
    """B1: 데이터셋 목록. 내 소속 팀 먼저, 다음 팀 이름·데이터셋 이름 순서."""
    items, total = service.list_datasets(session, user, team_id=team_id, limit=limit, offset=offset)
    return Page[DatasetOut](items=items, total=total, limit=limit, offset=offset)


@router.post("/datasets", status_code=201)
def create_dataset(
    body: DatasetCreate,
    user: CurrentUserDep,
    session: SessionDep,
    hooks: HooksDep,
    sync: SyncDep,
    background: BackgroundTasks,
) -> DatasetDetailOut:
    """B2: 데이터셋 만들기(등록 + 원본 표 생성이 한 트랜잭션)."""
    if not can_define(user, body.team_id):
        raise forbidden()
    dataset_id = service.create_dataset(
        session, hooks, user, team_id=body.team_id, name=body.name, date_unit=body.date_unit
    )
    background.add_task(run_dataset_sync_request, sync, dataset_id)
    return DatasetDetailOut(**service.get_dataset_detail(session, user, dataset_id))


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: int, user: CurrentUserDep, session: SessionDep) -> DatasetDetailOut:
    """B3: 데이터셋 상세(팀, 열, 내 권한)."""
    return DatasetDetailOut(**service.get_dataset_detail(session, user, dataset_id))


@router.patch("/datasets/{dataset_id}", dependencies=[DefinerDep])
def update_dataset(
    dataset_id: int,
    body: DatasetUpdate,
    user: CurrentUserDep,
    session: SessionDep,
    hooks: HooksDep,
    sync: SyncDep,
    background: BackgroundTasks,
) -> DatasetDetailOut:
    """B4: 이름·날짜 단위·기준 날짜 열 변경(`expected_version` 필수)."""
    sent = body.model_fields_set
    changed, _version = service.update_dataset(
        session,
        hooks,
        dataset_id,
        actor=user,
        expected_version=body.expected_version,
        name=body.name if "name" in sent else None,
        date_unit=body.date_unit if "date_unit" in sent else None,
        base_given="base_date_column_id" in sent,
        base_date_column_id=body.base_date_column_id,
    )
    if changed:
        background.add_task(run_dataset_sync_request, sync, dataset_id)
    return DatasetDetailOut(**service.get_dataset_detail(session, user, dataset_id))


@router.post("/datasets/{dataset_id}/columns", status_code=201, dependencies=[DefinerDep])
def add_column(
    dataset_id: int,
    body: ColumnCreate,
    user: CurrentUserDep,
    session: SessionDep,
    hooks: HooksDep,
    sync: SyncDep,
    background: BackgroundTasks,
) -> ColumnResult:
    """B5: 원본 열 추가(계산 열은 D4)."""
    result = service.add_column(
        session,
        hooks,
        dataset_id,
        actor=user,
        expected_version=body.expected_version,
        display_name=body.display_name,
        column_type=body.type,
        required=body.required,
        raw_rules=body.rules,
        raw_tag=body.tag,
        position=body.position,
    )
    background.add_task(run_dataset_sync_request, sync, dataset_id)
    return ColumnResult(column=ColumnOut(**result.column), def_version=result.def_version)


@router.patch("/datasets/{dataset_id}/columns/{col_id}", dependencies=[DefinerDep])
def update_column(
    dataset_id: int,
    col_id: int,
    body: ColumnUpdate,
    user: CurrentUserDep,
    session: SessionDep,
    hooks: HooksDep,
    sync: SyncDep,
    background: BackgroundTasks,
) -> ColumnResult:
    """B6: 표시 이름·필수·규칙·태그·순서 변경. `type`·`kind`는 바꿀 수 없다."""
    fields = set(body.model_fields_set) - {"expected_version"}
    result = service.update_column(
        session,
        hooks,
        dataset_id,
        col_id,
        actor=user,
        expected_version=body.expected_version,
        fields=fields,
        values=body.model_dump(),
    )
    if result.changed:
        background.add_task(run_dataset_sync_request, sync, dataset_id)
    return ColumnResult(column=ColumnOut(**result.column), def_version=result.def_version)
