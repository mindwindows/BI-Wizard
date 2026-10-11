"""FastAPI 애플리케이션 팩토리."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import Engine

from app.config import Settings, get_settings
from app.db import create_db_engine
from app.health import router as health_router

logger = logging.getLogger(__name__)

# 라우트는 항상 /api 아래에 둔다. 하위 경로(APP_BASE_PATH)는 root_path로 처리한다.
API_PREFIX = "/api"


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
    app.include_router(health_router, prefix=API_PREFIX)
    return app
