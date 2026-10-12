"""FastAPI 애플리케이션 팩토리."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI
from sqlalchemy import Engine

from app.auth import current_user
from app.auth.guard import check_public_routers
from app.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.request_id import RequestIdMiddleware
from app.db import create_db_engine
from app.health import router as health_router

logger = logging.getLogger(__name__)

# 라우트는 항상 /api 아래에 둔다. 하위 경로(APP_BASE_PATH)는 root_path로 처리한다.
API_PREFIX = "/api"

# 모듈 라우터를 등록하는 유일한 곳(04 §2, §5). 모듈을 추가하면 아래 둘 중 한 목록에만 넣는다.
# - 공개: 인증 없이 열리는 라우터. `/health`, `/health/db`(H1·H2)뿐이다(`auth.guard.PUBLIC_PATHS`).
# - 보호: 라우터 전체에 `current_user`가 붙는다. 모든 업무 API(읽기 포함)가 여기에 들어간다.
PUBLIC_ROUTERS: tuple[APIRouter, ...] = (health_router,)
PROTECTED_ROUTERS: tuple[APIRouter, ...] = ()


def register_routers(
    app: FastAPI,
    *,
    public: tuple[APIRouter, ...] = PUBLIC_ROUTERS,
    protected: tuple[APIRouter, ...] = PROTECTED_ROUTERS,
) -> None:
    check_public_routers(public, API_PREFIX)
    for router in public:
        app.include_router(router, prefix=API_PREFIX)
    for router in protected:
        app.include_router(router, prefix=API_PREFIX, dependencies=[Depends(current_user)])


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.engine = engine or create_db_engine(settings)
        logger.info(
            "backend 시작: env=%s, 하위 경로=%r, 프록시가 접두를 떼는가=%s, 받는 API 접두=%s",
            settings.app_env,
            settings.app_base_path,
            settings.app_proxy_strip_prefix,
            settings.received_api_prefix,
        )
        if settings.auth_stub_enabled:
            logger.warning("인증 스텁이 켜져 있다(개발·시험 환경 전용, env=%s).", settings.app_env)
        try:
            yield
        finally:
            app.state.engine.dispose()

    docs_enabled = settings.app_debug
    app = FastAPI(
        title=settings.app_name,
        root_path=settings.app_base_path,
        lifespan=lifespan,
        docs_url=f"{API_PREFIX}/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json" if docs_enabled else None,
    )
    # 신원 어댑터와 사용자 조회는 FU-1a에서 연결한다. None이면 current_user는 항상 401이다.
    app.state.identity_adapter = None
    app.state.user_reader = None
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)
    register_routers(app)
    return app
