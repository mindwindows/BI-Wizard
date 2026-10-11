"""정적 표의 `MetaData` 한 곳과 Alembic 비교 필터.

- `metadata`: `public` schema의 **정적 표**(팀, 사용자, 데이터셋 정의 등)만 등록한다.
  지금(EW-1)은 표가 없다. 표를 추가하면 revision(`backend/migrations/versions/`)과 함께
  여기에 모델을 추가한다. 동적 객체(`bi_data` schema의 `ds_<번호>` 표, `dv_<번호>`·`de_<번호>`
  뷰)는 런타임 DDL 모듈이 만들며 이 `MetaData`에 넣지 않는다
  (docs/decisions/03-migration-tool.md D2, 06-data-model.md §6).
- `include_name`, `include_object`: `alembic check`/`--autogenerate`가 동적 객체를 삭제 후보로
  보지 않게 하는 안전망이다. 기본 설정(`include_schemas=False`)에서는 `bi_data`가 비교 대상이
  아니므로 이중 안전장치다(03c X-29).
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import MetaData

# 제약·인덱스 이름 규칙(autogenerate가 같은 이름을 만들게 한다).
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)

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
