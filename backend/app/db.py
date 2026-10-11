"""PostgreSQL 연결. 드라이버는 pg8000(BSD-3)이며 URL은 URL.create로 만든다."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL

from app.config import Settings


def build_database_url(settings: Settings) -> URL:
    """접속 URL을 만든다. 문자열을 이어 붙이지 않아 비밀번호의 특수문자도 안전하다."""
    return URL.create(
        drivername="postgresql+pg8000",
        username=settings.postgres_user,
        password=settings.postgres_password.get_secret_value(),
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
    )


def create_db_engine(settings: Settings) -> Engine:
    return create_engine(
        build_database_url(settings),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=0,
        connect_args={"timeout": 5},
    )
