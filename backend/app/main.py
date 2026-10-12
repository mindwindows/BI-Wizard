"""FastAPI 애플리케이션 팩토리."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import Engine

from app.access.router import router as access_router
from app.auth import current_user
from app.auth.db_reader import DbUserReader
from app.auth.guard import DEV_STUB_PATHS, check_public_routers
from app.auth.stub import build_stub_adapter
from app.auth.stub import router as stub_router
from app.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.ports import DatasetSyncPort, DefinitionHooks, NoopDatasetSync
from app.core.request_id import RequestIdMiddleware
from app.core.startup_check import run_startup_checks
from app.dataset.router import router as dataset_router
from app.db import create_db_engine
from app.health import router as health_router

logger = logging.getLogger(__name__)

# 라우트는 항상 /api 아래에 둔다. 하위 경로(APP_BASE_PATH)는 root_path로 처리한다.
API_PREFIX = "/api"

# 모듈 라우터를 등록하는 유일한 곳(04 §2, §5). 모듈을 추가하면 아래 둘 중 한 목록에만 넣는다.
# - 공개: 인증 없이 열리는 라우터. `/health`, `/health/db`(H1·H2)뿐이다(`auth.guard.PUBLIC_PATHS`).
# - 보호: 라우터 전체에 `current_user`가 붙는다. 모든 업무 API(읽기 포함)가 여기에 들어간다.
# - 개발: 인증 스텁이 켜진 설정에서만 붙는 `/dev/*`(DV1~DV3). `guard.DEV_STUB_PATHS` 밖의
#   경로는 거부한다.
PUBLIC_ROUTERS: tuple[APIRouter, ...] = (health_router,)
PROTECTED_ROUTERS: tuple[APIRouter, ...] = (access_router, dataset_router)
DEV_ROUTERS: tuple[APIRouter, ...] = (stub_router,)


def register_routers(
    app: FastAPI,
    *,
    public: tuple[APIRouter, ...] = PUBLIC_ROUTERS,
    protected: tuple[APIRouter, ...] = PROTECTED_ROUTERS,
    dev: tuple[APIRouter, ...] = (),
) -> None:
    check_public_routers(public, API_PREFIX)
    check_public_routers(dev, API_PREFIX, allowed=DEV_STUB_PATHS)
    for router in (*public, *dev):
        app.include_router(router, prefix=API_PREFIX)
    for router in protected:
        app.include_router(router, prefix=API_PREFIX, dependencies=[Depends(current_user)])


def create_app(
    settings: Settings | None = None,
    engine: Engine | None = None,
    dataset_sync: DatasetSyncPort | None = None,
    definition_hooks: DefinitionHooks | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.engine = engine or create_db_engine(settings)
        try:
            # 시작 자가 점검(core): 어긋나면 예외로 시작을 거부한다(블로킹이라 스레드에서 실행).
            app.state.startup_report = await run_in_threadpool(run_startup_checks, app.state.engine)
        except BaseException:
            app.state.engine.dispose()
            raise
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
    # 사용자 조회는 DB(`users`+`team_members`)다. 신원 어댑터는 스텁이 켜진 설정에서만 연결하고,
    # 아니면 None이라 current_user는 항상 401이다(운영 어댑터는 8번 결정 뒤 교체, fail-closed).
    app.state.user_reader = DbUserReader()
    app.state.identity_adapter = (
        build_stub_adapter(settings) if settings.auth_stub_enabled else None
    )
    app.state.dataset_sync = dataset_sync or NoopDatasetSync()
    # 정의 변경 훅 등록부(04 §3). 1b에는 등록된 훅이 없다. formula 모듈이 1d에서 등록한다.
    app.state.definition_hooks = definition_hooks or DefinitionHooks()
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)
    register_routers(app, dev=DEV_ROUTERS if settings.auth_stub_enabled else ())
    return app
