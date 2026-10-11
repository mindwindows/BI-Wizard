"""Health 경로. 업무 API보다 먼저 만든다(`/health/azure-openai`는 만들지 않는다: 브리프 5절 1번)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request) -> dict[str, str]:
    """프로세스가 요청을 받을 수 있는지만 확인한다(DB를 건드리지 않는다)."""
    return {"status": "ok", "app": request.app.title}


@router.get("/health/db")
def health_db(request: Request) -> JSONResponse:
    """PostgreSQL에 실제로 접속해 `SELECT 1`을 실행한다."""
    try:
        with request.app.state.engine.connect() as connection:
            connection.execute(select(1)).scalar_one()
    except Exception:
        # 접속 정보가 응답에 새지 않도록 상세 원인은 로그에만 남긴다.
        logger.exception("DB health check failed")
        return JSONResponse(status_code=503, content={"status": "error", "database": "down"})
    return JSONResponse(status_code=200, content={"status": "ok", "database": "up"})
