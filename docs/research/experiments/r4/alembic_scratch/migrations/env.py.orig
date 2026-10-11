"""Alembic 환경.

- 접속 URL은 `sqlalchemy.engine.URL.create`와 POSTGRES_* 환경변수로 만든다.
- 마이그레이션 안의 SQL은 보간 없는 고정 문자열만 쓴다(D3).
- D2(동적 객체 분리 방식)는 Gate ③에서 정한다. 그때까지 target_metadata는 비어 있고
  autogenerate 초안에 DROP이 있으면 적용하지 않고 사용자 확인을 받는다.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import get_settings
from app.db import build_database_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Gate ②에는 모델이 없다. Gate ③에서 정적 모델의 MetaData를 연결한다.
target_metadata = None


def run_migrations_offline() -> None:
    """DB에 접속하지 않고 SQL 스크립트만 만든다."""
    url = build_database_url(get_settings())
    context.configure(
        url=url.render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(build_database_url(get_settings()), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
