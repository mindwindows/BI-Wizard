"""정적 표의 `MetaData` 한 곳과 Alembic 비교 필터.

- `metadata`: `public` schema의 **정적 표**(팀, 사용자, 데이터셋 정의 등)만 등록한다.
  권한 관리 표(`users`, `teams`, `team_members`, revision 0003), 데이터셋·열 정의 표(0004),
  수식 표(`formulas`, `formula_deps`, 0005), Superset 등록 표(`superset_datasets`,
  `superset_dashboards`, 0006), 감사 기록 표(`audit_log`, 0007), 기준값 표(`reference_items`,
  `reference_values`, 0009)가 있다. 표를 추가하면
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
    BigInteger,
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
    Numeric,
    PrimaryKeyConstraint,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    column,
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
# FU-2b `0008`이 archived를 추가했고 deleted는 영구 삭제 단위가 CHECK를 바꿔 추가한다.
DATASET_STATUSES = ("active", "archived")
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
    CheckConstraint("status IN ('active', 'archived')", name="status"),
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

# --- 수식 표(06 §2, revision 0005) ----
# `column_id`는 `kind='formula'`인 열이어야 한다(앱이 확인). `ast`는 열 번호 참조 JSON이다.
formulas = Table(
    "formulas",
    metadata,
    Column("column_id", Integer, ForeignKey("dataset_columns.id"), primary_key=True),
    Column("expression", Text, nullable=False),  # 보관용 원문(화면 표시에는 쓰지 않는다)
    Column("ast", JSON().with_variant(JSONB(), "postgresql"), nullable=False),
    Column("ast_hash", Text, nullable=False),
)

formula_deps = Table(
    "formula_deps",
    metadata,
    Column("column_id", Integer, ForeignKey("dataset_columns.id"), nullable=False),
    Column("depends_on_column_id", Integer, ForeignKey("dataset_columns.id"), nullable=False),
    PrimaryKeyConstraint("column_id", "depends_on_column_id"),
    CheckConstraint("column_id <> depends_on_column_id", name="not_self"),
)

# --- Superset 등록 표(06 §2, revision 0006) ----
# 동기 상태 열거. 값 추가는 CHECK 교체로 한다(06 §1).
SYNC_STATUSES = ("pending", "registered", "failed")

superset_datasets = Table(
    "superset_datasets",
    metadata,
    Column("dataset_id", Integer, ForeignKey("datasets.id"), primary_key=True),
    Column("superset_dataset_id", Integer, nullable=True),  # 등록 전 NULL
    Column("display_name", Text, nullable=False),
    Column("sync_status", Text, nullable=False, server_default="pending"),
    Column("synced_at", DateTime(timezone=True), nullable=True),
    Column("last_error", Text, nullable=True),  # 사유 요약만(SQL·비밀·응답 본문 금지)
    CheckConstraint("sync_status IN ('pending', 'registered', 'failed')", name="sync_status"),
)

superset_dashboards = Table(
    "superset_dashboards",
    metadata,
    Column("id", Integer, Identity(), primary_key=True),
    Column("name", Text, nullable=False),
    # `uuid` 형은 값을 항상 소문자 정규형(하이픈 36자)으로 저장한다. CHECK는 한 번 더 두는
    # 방어선이다.
    Column("embedded_uuid", Uuid, nullable=False),
    Column("is_active", Boolean, nullable=False, server_default=true()),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("embedded_uuid"),
    # 정규식 연산자(~)와 ::text 캐스트는 PostgreSQL 전용이라 SQLite 시험용 create_all에서는 만들지
    # 않는다(`ddl_if`). 실제 DB에서는 revision 0006이 같은 제약을 만든다.
    CheckConstraint(
        "embedded_uuid::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'",
        name="embedded_uuid_format",
    ).ddl_if(**_PG_ONLY),
)

# --- 감사 기록 표(06 §2-1, revision 0007) ----
# 행위 목록의 원본은 04 §5-1이다. 새 행위는 값 한 줄 + 이 CHECK 교체(새 revision) + `app/audit`의
# 허용 키 표 한 줄 + 시험이다. `app/audit/actions.py`가 같은 17개 이름을 쓰는지 시험이 대조한다.
AUDIT_ACTIONS = (
    "dataset.create",
    "dataset.update",
    "dataset.archive",
    "dataset.restore",
    "column.add",
    "column.update",
    "formula_column.add",
    "formula_column.update",
    "team.create",
    "team.update",
    "member.set",
    "member.remove",
    "user.create",
    "user.update",
    "user.bootstrap_admin",
    "dashboard.create",
    "dashboard.update",
    # FU-3(`0009`): 기준값 항목 추가·연도 값 추가·정정(17 -> 20).
    "reference.create",
    "reference_value.add",
    "reference_value.update",
)
AUDIT_TARGET_TYPES = ("team", "user", "dataset", "dashboard", "reference")
AUDIT_ACTOR_SOURCES = ("user", "cli")
# 감사 `details`의 크기 안전망(바이트). 앱 규칙은 허용 키·길이 상한으로 이보다 훨씬 작게 지킨다.
AUDIT_DETAILS_MAX_BYTES = 4000

audit_log = Table(
    "audit_log",
    metadata,
    # 행이 계속 쌓이는 유일한 표라 bigint. identity라 INSERT 권한만으로 번호가 붙는다
    # (시퀀스 GRANT 없음).
    Column("id", BigInteger, Identity(), primary_key=True),
    Column("occurred_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    # 사용자 번호만 둔다(표시 이름은 조회 때 users에서 읽는다). 서버 명령(cli)이면 NULL.
    Column("actor_user_id", Integer, ForeignKey("users.id"), nullable=True),
    Column("actor_source", Text, nullable=False),
    Column("action", Text, nullable=False),
    Column("target_type", Text, nullable=False),
    # 여러 표를 가리키므로 외래키가 없다.
    Column("target_id", BigInteger, nullable=False),
    Column(
        "details",
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        server_default="{}",  # DEFAULT '{}' (빈 객체)
    ),
    CheckConstraint(column("action").in_(AUDIT_ACTIONS), name="action"),
    CheckConstraint(column("target_type").in_(AUDIT_TARGET_TYPES), name="target_type"),
    CheckConstraint(column("actor_source").in_(AUDIT_ACTOR_SOURCES), name="actor_source"),
    CheckConstraint(
        "(actor_source = 'user' AND actor_user_id IS NOT NULL) "
        "OR (actor_source = 'cli' AND actor_user_id IS NULL)",
        name="actor_consistency",
    ),
    # jsonb 함수·`::text` 캐스트는 PostgreSQL 전용이라 SQLite 시험용 create_all에서는 만들지 않는다
    # (`ddl_if`). 실제 DB에서는 revision 0007이 같은 제약을 만든다.
    CheckConstraint("jsonb_typeof(details) = 'object'", name="details_object").ddl_if(**_PG_ONLY),
    # 4000은 AUDIT_DETAILS_MAX_BYTES와 같다(시험이 대조한다). SQL에 변수를 넣지 않으려고
    # 리터럴로 쓴다.
    CheckConstraint("octet_length(details::text) <= 4000", name="details_size").ddl_if(**_PG_ONLY),
)
# 인덱스 3개(06 §2-1): 기간·기본 정렬, 행위자 필터, 대상 필터. `action` 필터는 인덱스 없이 건다.
Index(
    "ix_audit_log_occurred_at_id",
    audit_log.c.occurred_at.desc(),
    audit_log.c.id.desc(),
)
Index(
    "ix_audit_log_actor_user_id_occurred_at_id",
    audit_log.c.actor_user_id,
    audit_log.c.occurred_at.desc(),
    audit_log.c.id.desc(),
)
Index(
    "ix_audit_log_target_type_target_id_occurred_at_id",
    audit_log.c.target_type,
    audit_log.c.target_id,
    audit_log.c.occurred_at.desc(),
    audit_log.c.id.desc(),
)

# --- 기준값 표(06 §2-2, revision 0009) ----
# 전역 기준값: 항목(`reference_items`)마다 연도별 숫자 값 하나(`reference_values`). 열 단위 UPDATE
# 권한(값 열·설명 열만)과 불변 열은 revision의 GRANT가 강제한다. 범위·정규식 CHECK는 PostgreSQL
# 전용(`char_length`, 무한대 비교)이라 SQLite 시험용 create_all에서는 만들지 않는다(`ddl_if`).
REFERENCE_NAME_MAX_LENGTH = 50  # ck_reference_items_name_length와 같은 값(시험이 대조한다)
REFERENCE_DESCRIPTION_MAX_LENGTH = 200  # 앱 검증(DB 제약 없음)
REFERENCE_YEAR_MIN = 1900  # ck_reference_values_year와 같은 값
REFERENCE_YEAR_MAX = 9999

reference_items = Table(
    "reference_items",
    metadata,
    Column("id", Integer, Identity(), primary_key=True),
    Column("name", Text, nullable=False),  # 불변(이름 변경 없음)
    Column("description", Text, nullable=True),
    Column("created_by", Integer, ForeignKey("users.id"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("name"),
    CheckConstraint("char_length(name) BETWEEN 1 AND 50", name="name_length").ddl_if(**_PG_ONLY),
)

reference_values = Table(
    "reference_values",
    metadata,
    Column("id", Integer, Identity(), primary_key=True),
    Column("item_id", Integer, ForeignKey("reference_items.id"), nullable=False),
    Column("year", Integer, nullable=False),
    Column("number_value", Numeric, nullable=False),
    Column("created_by", Integer, ForeignKey("users.id"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("item_id", "year"),
    CheckConstraint("year BETWEEN 1900 AND 9999", name="year"),
    # NaN은 PostgreSQL에서 모든 수보다 크게 비교되므로 NaN·±Infinity를 함께 거른다.
    CheckConstraint(
        "number_value > '-Infinity' AND number_value < 'Infinity'", name="finite"
    ).ddl_if(**_PG_ONLY),
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
