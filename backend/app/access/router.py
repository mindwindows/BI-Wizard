"""권한 관리 API(05 §2-1 A1~A9). 보호 라우터이므로 `register_routers`가 `current_user`를 붙인다.

A1·A2는 인증된 활성 사용자 누구나, A3~A9는 관리자만(`require_admin`) 쓴다. 권한 검사는 의존성이라
본문·쿼리 검증보다 먼저 실행된다(권한 없는 사용자는 입력 오류 내용을 알 수 없다).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.access import service
from app.access.schemas import (
    LIST_LIMIT_DEFAULT,
    LIST_LIMIT_MAX,
    MemberOut,
    MemberRoleIn,
    MembershipMe,
    MeOut,
    Page,
    TeamCreate,
    TeamOut,
    TeamUpdate,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.auth import CurrentUserDep
from app.auth.permissions import require_admin
from app.core.deps import get_session
from app.core.ports import DatasetSyncPort, run_sync_request

router = APIRouter(tags=["access"])

SessionDep = Annotated[Session, Depends(get_session)]
AdminDep = Depends(require_admin)
LimitParam = Annotated[int, Query(ge=1, le=LIST_LIMIT_MAX)]
OffsetParam = Annotated[int, Query(ge=0)]


def get_dataset_sync(request: Request) -> DatasetSyncPort:
    return request.app.state.dataset_sync


SyncDep = Annotated[DatasetSyncPort, Depends(get_dataset_sync)]


@router.get("/me")
def get_me(user: CurrentUserDep) -> MeOut:
    """A1: 내 정보와 소속 팀(작업 팀 선택에 쓴다)."""
    return MeOut(
        id=user.id,
        display_name=user.display_name,
        is_active=user.is_active,
        is_admin=user.is_admin,
        memberships=[
            MembershipMe(
                team_id=m.team_id, team_code=m.team_code, team_name=m.team_name, role=m.role
            )
            for m in user.memberships
        ],
    )


@router.get("/teams")
def list_teams(
    session: SessionDep,
    limit: LimitParam = LIST_LIMIT_DEFAULT,
    offset: OffsetParam = 0,
) -> Page[TeamOut]:
    """A2: 팀 목록(인증된 모든 사용자)."""
    items, total = service.list_teams(session, limit, offset)
    return Page[TeamOut](items=items, total=total, limit=limit, offset=offset)


@router.post("/teams", status_code=201, dependencies=[AdminDep])
def create_team(body: TeamCreate, session: SessionDep) -> TeamOut:
    """A3: 팀 만들기(코드는 불변)."""
    return TeamOut(**service.create_team(session, code=body.code, name=body.name))


@router.patch("/teams/{team_id}", dependencies=[AdminDep])
def update_team(
    team_id: int,
    body: TeamUpdate,
    session: SessionDep,
    sync: SyncDep,
    background: BackgroundTasks,
) -> TeamOut:
    """A4: 팀 이름 변경·비활성화. 이름이 바뀌면 커밋 뒤 팀 단위 동기화를 요청한다."""
    sent = body.model_fields_set
    change = service.update_team(
        session,
        team_id,
        name=body.name if "name" in sent else None,
        is_active=body.is_active if "is_active" in sent else None,
    )
    if change.name_changed:
        background.add_task(run_sync_request, sync, team_id)
    return TeamOut(**change.team)


@router.get("/users", dependencies=[AdminDep])
def list_users(
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    team_id: int | None = None,
    is_active: bool | None = None,
    limit: LimitParam = LIST_LIMIT_DEFAULT,
    offset: OffsetParam = 0,
) -> Page[UserOut]:
    """A5: 사용자 목록(검색·팀·활성 필터)."""
    items, total = service.list_users(
        session, q=q or None, team_id=team_id, is_active=is_active, limit=limit, offset=offset
    )
    return Page[UserOut](items=items, total=total, limit=limit, offset=offset)


@router.post("/users", status_code=201, dependencies=[AdminDep])
def create_user(body: UserCreate, session: SessionDep) -> UserOut:
    """A6: 사용자 사전 등록."""
    return UserOut(
        **service.create_user(
            session,
            login_id=body.login_id,
            display_name=body.display_name,
            is_admin=body.is_admin,
        )
    )


@router.patch("/users/{user_id}", dependencies=[AdminDep])
def update_user(user_id: int, body: UserUpdate, session: SessionDep) -> UserOut:
    """A7: 표시 이름·관리자·활성 변경. 마지막 활성 관리자는 해제·비활성할 수 없다."""
    sent = body.model_fields_set
    return UserOut(
        **service.update_user(
            session,
            user_id,
            display_name=body.display_name if "display_name" in sent else None,
            is_admin=body.is_admin if "is_admin" in sent else None,
            is_active=body.is_active if "is_active" in sent else None,
        )
    )


@router.put("/teams/{team_id}/members/{user_id}", dependencies=[AdminDep])
def put_member(team_id: int, user_id: int, body: MemberRoleIn, session: SessionDep) -> MemberOut:
    """A8: 소속 추가 또는 역할 변경."""
    return MemberOut(**service.set_member(session, team_id, user_id, body.role))


@router.delete("/teams/{team_id}/members/{user_id}", status_code=204, dependencies=[AdminDep])
def delete_member(team_id: int, user_id: int, session: SessionDep) -> Response:
    """A9: 소속 해제."""
    service.remove_member(session, team_id, user_id)
    return Response(status_code=204)
