"""X-29 실험용 env.py (저장소 backend/migrations/env.py 복사본을 변형 가능하게 고친 것).
환경변수: X29_TARGET=none|meta, X29_SCHEMAS=0|1, X29_FILTER=none|object|name|both, X29_COMPARE_TYPE=1|0, X29_TPM=0|1, X29_VERSION_SCHEMA=(빈값|스키마)
"""
from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import get_settings
from app.db import build_database_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

TARGET = os.environ.get("X29_TARGET", "none")
if TARGET == "meta":
    import models
    target_metadata = models.metadata
else:
    target_metadata = None

INCLUDE_SCHEMAS = os.environ.get("X29_SCHEMAS", "0") == "1"
FILTER = os.environ.get("X29_FILTER", "none")
COMPARE_TYPE = os.environ.get("X29_COMPARE_TYPE", "1") == "1"
TPM = os.environ.get("X29_TPM", "0") == "1"
VERSION_SCHEMA = os.environ.get("X29_VERSION_SCHEMA") or None
DYNAMIC_SCHEMA = "bi_data"


def include_name(name, type_, parent_names):
    if type_ == "schema":
        return name != DYNAMIC_SCHEMA
    return True


def include_object(obj, name, type_, reflected, compare_to):
    if reflected and getattr(obj, "schema", None) == DYNAMIC_SCHEMA:
        return False
    if type_ in ("column", "index", "unique_constraint", "foreign_key_constraint") and reflected:
        tbl = getattr(obj, "table", None)
        if tbl is not None and tbl.schema == DYNAMIC_SCHEMA:
            return False
    return True


def _kw():
    kw = dict(target_metadata=target_metadata, compare_type=COMPARE_TYPE, include_schemas=INCLUDE_SCHEMAS,
              transaction_per_migration=TPM)
    if FILTER in ("name", "both"):
        kw["include_name"] = include_name
    if FILTER in ("object", "both"):
        kw["include_object"] = include_object
    if VERSION_SCHEMA:
        kw["version_table_schema"] = VERSION_SCHEMA
    return kw


def run_migrations_offline() -> None:
    url = build_database_url(get_settings())
    context.configure(url=url.render_as_string(hide_password=False), literal_binds=True,
                      dialect_opts={"paramstyle": "named"}, **_kw())
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(build_database_url(get_settings()), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, **_kw())
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
