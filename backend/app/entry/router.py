"""입력 그리드 API(05 §2-3 C1~C4). 보호 라우터라 `register_routers`가 `current_user`를 붙인다.

- C1(읽기)은 인증된 활성 사용자 누구나(타 팀 포함). 잠금 없음.
- C2~C4는 그 데이터셋 팀의 `입력(팀)` = 팀의 `entry` 또는 `definer`다. 관리자라도 팀 소속이 아니면
  거부한다(06 §4-1). 권한 검사는 의존성이라 본문 검증·크기 검사보다 먼저 실행된다.
- C4는 본문을 직접 읽어 크기(1MiB)와 행 수(5,000)를 센다. 넘으면 413 `PAYLOAD_TOO_LARGE`(JSON)다.
  앞단 nginx의 기본 요청 상한(1m)이 먼저 413을 내면 JSON이 아닐 수 있다(프런트가 둘 다 처리).
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.auth import CurrentUserDep
from app.auth.permissions import can_enter
from app.core.deps import get_session
from app.core.errors import forbidden, payload_too_large
from app.core.pagination import LIST_LIMIT_DEFAULT, LIST_LIMIT_MAX
from app.core.ports import RowViewPort
from app.dataset import service as dataset_service
from app.entry import service
from app.entry.schemas import (
    PasteBody,
    PasteResult,
    RowCreate,
    RowPatch,
    RowResult,
    RowsPage,
)

router = APIRouter(tags=["entry"])

SessionDep = Annotated[Session, Depends(get_session)]
LimitParam = Annotated[int, Query(ge=1, le=LIST_LIMIT_MAX)]
OffsetParam = Annotated[int, Query(ge=0)]


def get_row_view(request: Request) -> RowViewPort:
    return request.app.state.row_view


RowViewDep = Annotated[RowViewPort, Depends(get_row_view)]


def require_dataset_entry(dataset_id: int, user: CurrentUserDep, session: SessionDep) -> int:
    """입력(팀) 권한: 데이터셋이 없으면 404, 그 팀의 입력자·정의 담당자가 아니면 403."""
    team_id = dataset_service.get_dataset_team_id(session, dataset_id)
    if not can_enter(user, team_id):
        raise forbidden()
    # 권한 검사가 연 트랜잭션·연결을 돌려준다. 이어지는 본문 읽기(느린 클라이언트)가 풀(5개)을
    # 붙들면 다른 API까지 굶는다. 이후 service가 새 트랜잭션을 연다.
    session.rollback()
    return dataset_id


EntryDep = Depends(require_dataset_entry)


@router.get("/datasets/{dataset_id}/rows")
def list_rows(
    dataset_id: int,
    session: SessionDep,
    row_view: RowViewDep,
    order: Literal["asc", "desc"] = "asc",
    limit: LimitParam = LIST_LIMIT_DEFAULT,
    offset: OffsetParam = 0,
) -> RowsPage:
    """C1: 행 조회. `order`는 기준 날짜 열(없으면 `row_id`) 기준이다."""
    return RowsPage(
        **service.list_rows(
            session, dataset_id, order=order, limit=limit, offset=offset, row_view=row_view
        )
    )


@router.post("/datasets/{dataset_id}/rows", status_code=201, dependencies=[EntryDep])
def create_row(
    dataset_id: int, body: RowCreate, session: SessionDep, row_view: RowViewDep
) -> RowResult:
    """C2: 새 행. 원본 열만, 필수 열은 전부 있어야 한다."""
    row, version = service.create_row(
        session,
        dataset_id,
        expected_version=body.expected_version,
        cells=body.cells,
        row_view=row_view,
    )
    return RowResult(row=row, def_version=version)


@router.patch("/datasets/{dataset_id}/rows/{row_id}", dependencies=[EntryDep])
def update_row(
    dataset_id: int, row_id: int, body: RowPatch, session: SessionDep, row_view: RowViewDep
) -> RowResult:
    """C3: 칸 수정. 모든 칸이 가드이고 하나라도 충돌하면 전체 취소(`CELL_CONFLICT`)."""
    row, version = service.update_row(
        session,
        dataset_id,
        row_id,
        expected_version=body.expected_version,
        changes=body.changes,
        row_view=row_view,
    )
    return RowResult(row=row, def_version=version)


async def read_limited_body(request: Request, limit: int) -> bytes:
    """본문을 `limit` 바이트까지만 읽는다. 선언된 길이나 실제 읽은 길이가 넘으면 413."""
    too_large = payload_too_large(limit, "요청 크기가 너무 큽니다. 나누어 붙여넣으세요.")
    declared = request.headers.get("content-length", "")
    if declared.isascii() and declared.isdigit() and int(declared) > limit:
        raise too_large
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise too_large
        chunks.append(chunk)
    return b"".join(chunks)


def _bad_body(position: int) -> RequestValidationError:
    """JSON을 읽지 못한 본문: `field`는 오류 위치 번호 문자열이다(05 §1)."""
    return RequestValidationError(
        [{"type": "json_invalid", "loc": ("body", position), "msg": "JSON decode error"}]
    )


def parse_paste_body(raw: bytes) -> PasteBody:
    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError as error:
        raise _bad_body(error.pos) from None
    except (ValueError, RecursionError):  # 인코딩 오류, 너무 깊은 중첩
        raise _bad_body(0) from None
    rows = data.get("rows") if isinstance(data, dict) else None
    if isinstance(rows, list) and len(rows) > service.PASTE_MAX_ROWS:
        raise payload_too_large(
            service.PASTE_MAX_ROWS,
            f"한 번에 붙여넣을 수 있는 행은 {service.PASTE_MAX_ROWS:,}개까지입니다.",
        )
    try:
        return PasteBody.model_validate(data)
    except ValidationError as error:
        errors = error.errors(include_url=False, include_context=False, include_input=False)
        raise RequestValidationError(
            [{**item, "loc": ("body", *item["loc"])} for item in errors]
        ) from None


def _paste_request_schema() -> dict[str, Any]:
    """원시 `Request`를 받아 FastAPI가 본문 스키마를 모르므로 `PasteBody`를 직접 노출한다."""
    schema = PasteBody.model_json_schema()
    defs = schema.pop("$defs", {})
    schema["properties"]["rows"]["items"] = defs["PasteRow"]
    return schema


@router.post(
    "/datasets/{dataset_id}/rows/paste",
    dependencies=[EntryDep],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": _paste_request_schema()}},
        }
    },
)
async def paste_rows(dataset_id: int, request: Request, session: SessionDep) -> PasteResult:
    """C4: 붙여넣기 일괄. 한 트랜잭션, 충돌이 하나라도 있으면 전부 취소(`PASTE_CONFLICT`)."""
    body = parse_paste_body(await read_limited_body(request, service.PASTE_MAX_BYTES))
    result = await run_in_threadpool(
        service.paste_rows,
        session,
        dataset_id,
        expected_version=body.expected_version,
        column_ids=body.column_ids,
        rows=body.rows,
    )
    return PasteResult(**result)
