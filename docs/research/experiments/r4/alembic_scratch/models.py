"""X-29 가짜 정적 모델 (teams, datasets, dataset_columns). X29_MODEL 환경변수로 변형한다."""
import os
from sqlalchemy import MetaData, Table, Column, Integer, BigInteger, Text, String, ForeignKey, Identity

MODEL = os.environ.get("X29_MODEL", "base")
metadata = MetaData()

teams = Table("teams", metadata,
              Column("id", Integer, Identity(), primary_key=True),
              Column("name", Text, nullable=False),
              )

_ds_cols = [
    Column("id", Integer, Identity(), primary_key=True),
    Column("team_id", Integer, ForeignKey("teams.id"), nullable=False),
    Column("display_name", Text, nullable=False),
]
if MODEL != "drop_col":
    _ds_cols.append(Column("def_version", Integer, nullable=False, server_default="1"))
if MODEL == "add_col":
    _ds_cols.append(Column("owner_note", Text))
if MODEL == "type_change":
    _ds_cols = [c if c.name != "display_name" else Column("display_name", String(50), nullable=False) for c in _ds_cols]
if MODEL == "int_to_bigint":
    _ds_cols = [c if c.name != "team_id" else Column("team_id", BigInteger, ForeignKey("teams.id"), nullable=False) for c in _ds_cols]
datasets = Table("datasets", metadata, *_ds_cols)

dataset_columns = Table("dataset_columns", metadata,
                        Column("id", Integer, Identity(), primary_key=True),
                        Column("dataset_id", Integer, ForeignKey("datasets.id"), nullable=False),
                        Column("internal_name", Text, nullable=False),
                        )
if MODEL == "add_table":
    Table("audit_log", metadata, Column("id", Integer, Identity(), primary_key=True), Column("what", Text))
