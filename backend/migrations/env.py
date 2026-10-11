"""Alembic 환경.

- 접속 URL은 `sqlalchemy.engine.URL.create`로 만든다. 계정은 코드 상수 `bi_owner`
  (정적 표 소유자)이고 비밀번호만 `POSTGRES_OWNER_PASSWORD`에서 읽는다.
  슈퍼유저(`POSTGRES_USER`)로는 접속하지 않는다.
- 마이그레이션 안의 SQL은 보간 없는 고정 문자열만 쓴다(D3).
- `target_metadata`는 정적 표의 `MetaData` 한 곳(`app/db_metadata.py`)이다. 동적 객체
  (`bi_data` schema의 `ds_*`, `dv_*`, `de_*`)는 비교 대상이 아니다: `include_schemas`는 기본값
  (False)이고, 안전망으로 `include_name`/`include_object`가 `bi_data`와 동적 객체 이름을
  제외한다(D2, 03c X-29).
- `alembic revision --autogenerate` 초안에 `DROP`이 있으면 적용하지 않고 사용자 확인을 받는다.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import get_settings
from app.db import build_database_url
from app.db_metadata import include_name, include_object, metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = metadata


def run_migrations_offline() -> None:
    """DB에 접속하지 않고 SQL 스크립트만 만든다(접속 정보와 비밀번호가 필요 없다)."""
    context.configure(
        url="postgresql+pg8000://",
        target_metadata=target_metadata,
        # 오프라인 SQL 출력 전용이다(사용자 입력 없음, bi-review 7-4의 런타임 동적 DDL 대상 아님).
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_name=include_name,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(
        build_database_url(get_settings(), "owner"),
        poolclass=pool.NullPool,
    )
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_name=include_name,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
