"""정적 표의 `MetaData` 한 곳과 Alembic 비교 필터.

- `metadata`: `public` schema의 **정적 표**(팀, 사용자, 데이터셋 정의 등)만 등록한다.
  지금은 권한 관리 표 3개(`users`, `teams`, `team_members`, revision 0003)가 있다. 표를 추가하면
  revision(`backend/migrations/versions/`)과 함께 여기에 모델을 추가한다. 쓰기 책임은 소유
  모듈(04 §2-2)이 지고, 이 파일은 정의만 둔다(04 §2-1 core). 동적 객체(`bi_data` schema의
  `ds_<번호>` 표, `dv_<번호>`·`de_<번호>` 뷰)는 런타임 DDL 모듈이 만들며 이 `MetaData`에
  넣지 않는다(docs/decisions/03-migration-tool.md D2, 06-data-model.md §6).
- `include_name`, `include_object`: `alembic check`/`--autogenerate`가 동적 객체를 삭제 후보로
  보지 않게 하는 안전망이다. 기본 설정(`include_schemas=False`)에서는 `bi_data`가 비교 대상이
  아니므로 이중 안전장치다(03c X-29).
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    Table,
    Text,
    UniqueConstraint,
    false,
    func,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB

# 제약·인덱스 이름 규칙(autogenerate가 같은 이름을 만들게 한다).
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)

# --- 권한 관리 표(06 §2, revision 0003) ----
# 열 단위 UPDATE 권한과 불변 열(login_id, code, team_id, user_id)은 revision의 GRANT가 강제한다.
# 정규식 CHECK는 PostgreSQL 전용 연산자(~)라 SQLite 시험용 create_all에서는 만들지 않는다
# (`ddl_if`). 실제 DB에서는 revision 0003이 같은 제약을 만든다.
_PG_ONLY = {"dialect": "postgresql"}

# `teams.code` 형식(06 §2, 05 A3). 서비스 검증(app/access)도 같은 식을 쓴다.
TEAM_CODE_PATTERN = "^[a-z0-9_]{1,32}$"
TEAM_ROLES = ("definer", "entry")

users = Table(
    "users",
    metadata,
    Column("id", Integer, Identity(), primary_key=True),
    Column("login_id", Text, nullable=False),
    Column("display_name", Text, nullable=False),
    Column("is_admin", Boolean, nullable=False, server_default=false()),
    Column("is_active", Boolean, nullable=False, server_default=true()),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("login_id"),
)

teams = Table(
    "teams",
    metadata,
    Column("id", Integer, Identity(), primary_key=True),
    Column("code", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("is_active", Boolean, nullable=False, server_default=true()),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("code"),
    UniqueConstraint("name"),
    # 식은 TEAM_CODE_PATTERN과 같다(시험이 대조한다). SQL에 변수를 넣지 않으려고 리터럴로 쓴다.
    CheckConstraint("code ~ '^[a-z0-9_]{1,32}$'", name="code_format").ddl_if(**_PG_ONLY),
)

team_members = Table(
    "team_members",
    metadata,
    Column("team_id", Integer, ForeignKey("teams.id"), nullable=False),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("role", Text, nullable=False),
    PrimaryKeyConstraint("team_id", "user_id"),
    CheckConstraint("role IN ('definer', 'entry')", name="role"),
    Index("ix_team_members_user_id", "user_id"),
)

# --- 데이터셋·열 정의 표(06 §2, revision 0004) ----
# 열거 값은 PostgreSQL enum이 아니라 `text` + 이름 있는 CHECK다(06 §1). 값 추가는 CHECK 교체로 한다.
DATE_UNITS = ("day", "month", "year")
DATASET_STATUSES = ("active",)  # archived·deleted는 보관·삭제 단위가 CHECK를 바꿔 추가한다
COLUMN_TYPES = ("text", "number", "date", "boolean", "choice")
COLUMN_KINDS = ("raw", "formula")

datasets = Table(
    "datasets",
    metadata,
    Column("id", Integer, Identity(), primary_key=True),
    Column("team_id", Integer, ForeignKey("teams.id"), nullable=False),
    Column("name", Text, nullable=False),
    Column("date_unit", Text, nullable=False),
    # NULL = 기준 날짜 열 없음. 같은 데이터셋의 열만 가리키도록 아래 복합 FK가 보장한다.
    Column("base_date_column_id", Integer, nullable=True),
    Column("status", Text, nullable=False, server_default="active"),
    Column("def_version", Integer, nullable=False, server_default="1"),
    # 1d 전에는 구조 해시, 1d부터 뷰 DDL 해시(06 §5).
    Column("def_hash", Text, nullable=False),
    Column("created_by", Integer, ForeignKey("users.id"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("team_id", "name"),
    CheckConstraint("date_unit IN ('day', 'month', 'year')", name="date_unit"),
    CheckConstraint("status IN ('active')", name="status"),
    # 순환 FK(datasets <-> dataset_columns)라 표 생성 뒤에 추가한다(use_alter). SQLite 시험용
    # create_all에서는 만들지 않는다(`ddl_if`); 실제 DB에서는 revision 0004가 만든다.
    ForeignKeyConstraint(
        ["id", "base_date_column_id"],
        ["dataset_columns.dataset_id", "dataset_columns.id"],
        name="fk_datasets_id_dataset_columns",
        use_alter=True,
    ).ddl_if(**_PG_ONLY),
)

dataset_columns = Table(
    "dataset_columns",
    metadata,
    Column("id", Integer, Identity(), primary_key=True),
    Column("dataset_id", Integer, ForeignKey("datasets.id"), nullable=False),
    Column("display_name", Text, nullable=False),
    Column("type", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("required", Boolean, nullable=False, server_default=false()),
    # number {min, max, decimals} / text {max_length} / date {min, max} / choice {options[]}
    Column("rules", JSON().with_variant(JSONB(), "postgresql"), nullable=True),
    Column("tag", Text, nullable=True),
    Column("position", Integer, nullable=False),
    UniqueConstraint("dataset_id", "id"),  # 복합 FK(datasets.base_date_column_id)의 대상
    UniqueConstraint("dataset_id", "display_name"),
    CheckConstraint("type IN ('text', 'number', 'date', 'boolean', 'choice')", name="type"),
    CheckConstraint("kind IN ('raw', 'formula')", name="kind"),
    # 계산 열은 필수일 수 없고 선택 목록 형이 아니다. 원본 열은 제한 없음.
    CheckConstraint("kind = 'raw' OR (NOT required AND type <> 'choice')", name="formula_shape"),
)

# 동적 객체가 놓이는 schema(이름은 코드 상수).
DYNAMIC_SCHEMA = "bi_data"
# 동적 객체 이름 규칙: 원본 표 ds_<번호>, 수식 뷰 dv_<번호>, 오류 판정 보조 뷰 de_<번호>.
_DYNAMIC_NAME = re.compile(r"(ds|dv|de)_[0-9]+")


def is_dynamic_name(name: str | None) -> bool:
    return bool(name) and _DYNAMIC_NAME.fullmatch(name or "") is not None


def include_name(name: str | None, type_: str, parent_names: dict[str, str | None]) -> bool:
    """Alembic `include_name` 훅: 이름 수준에서 `bi_data`와 동적 객체 이름을 제외한다."""
    if type_ == "schema":
        return name != DYNAMIC_SCHEMA
    if parent_names.get("schema_name") == DYNAMIC_SCHEMA:
        return False
    if type_ == "table" and is_dynamic_name(name):
        return False
    return True


def include_object(
    obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any
) -> bool:
    """Alembic `include_object` 훅: 객체 수준 안전망(이름 필터를 통과한 동적 객체를 거른다)."""
    if type_ == "table":
        if getattr(obj, "schema", None) == DYNAMIC_SCHEMA:
            return False
        if is_dynamic_name(name):
            return False
    return True
