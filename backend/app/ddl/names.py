"""동적 객체 이름 규칙(04 부록 A, 06 §1). 이름은 **번호로만** 만든다.

사용자가 입력한 글자(데이터셋·열 표시 이름 등)는 식별자에 쓰지 않는다. 이 파일의 규칙 함수가
이름을 만드는 유일한 길이고, 실행 쪽(`dynamic.py`)은 이름을 `check_dynamic_name`으로 다시 확인한다.
번호는 양의 정수여야 한다(`bool`·문자열·0·음수는 거부).
"""

from __future__ import annotations

import re

from app.db_metadata import DYNAMIC_SCHEMA

__all__ = [
    "ALLOWED_OBJECT_KINDS",
    "DYNAMIC_SCHEMA",
    "DdlError",
    "DdlNameError",
    "DdlNotAllowedError",
    "DdlVerificationError",
    "check_dynamic_name",
    "check_object_kind",
    "column_name",
    "dataset_table_name",
    "error_column_name",
    "error_view_name",
    "period_check_name",
    "period_index_name",
    "view_name",
]

# 만들 수 있는 객체 종류의 허용 목록(`bi-review` 7-4, 03c X-15). 열이 소유한 Identity 시퀀스
# (`row_id`)는 표에 딸려 만들어지는 것이라 독립 객체로 만들지 않는다.
ALLOWED_OBJECT_KINDS = frozenset({"table", "view", "index", "constraint"})

_NUMBER = r"[1-9][0-9]*"
_NAME_PATTERNS = {
    "table": re.compile(rf"ds_{_NUMBER}"),
    "view": re.compile(rf"(?:dv|de)_{_NUMBER}"),
    "column": re.compile(rf"(?:c|e)_{_NUMBER}|row_id|team"),
    "index": re.compile(rf"ux_ds_{_NUMBER}_period"),
    "constraint": re.compile(rf"ck_ds_{_NUMBER}_period"),
}
_ANY_NAME = re.compile("|".join(p.pattern for p in _NAME_PATTERNS.values()))
_MAX_IDENTIFIER_LENGTH = 63  # PostgreSQL 식별자 최대 길이


class DdlError(Exception):
    """동적 DDL 모듈의 오류 기본형. 메시지에는 사용자 입력을 넣지 않는다."""


class DdlNameError(DdlError, ValueError):
    """이름 규칙 위반(번호가 아니거나 규칙 밖의 이름)."""


class DdlNotAllowedError(DdlError):
    """허용 목록 밖의 객체 종류·DDL 구문·schema."""


class DdlVerificationError(DdlError):
    """DDL 실행 뒤 다시 읽어 본 결과가 기대와 다름(호출한 트랜잭션을 롤백해야 한다)."""


def _number(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise DdlNameError(f"{label} 번호는 1 이상의 정수여야 한다.")
    return value


def dataset_table_name(dataset_id: int) -> str:
    """원본 표 `ds_<번호>`."""
    return f"ds_{_number(dataset_id, '데이터셋')}"


def view_name(dataset_id: int) -> str:
    """수식 뷰 `dv_<번호>`(1d에서 사용)."""
    return f"dv_{_number(dataset_id, '데이터셋')}"


def error_view_name(dataset_id: int) -> str:
    """오류 판정 보조 뷰 `de_<번호>`(1d에서 사용)."""
    return f"de_{_number(dataset_id, '데이터셋')}"


def column_name(column_id: int) -> str:
    """원본·계산 열 `c_<번호>`(번호 = `dataset_columns.id`)."""
    return f"c_{_number(column_id, '열')}"


def error_column_name(column_id: int) -> str:
    """오류 판정 열 `e_<번호>`(1d에서 사용)."""
    return f"e_{_number(column_id, '열')}"


def period_index_name(dataset_id: int) -> str:
    """기간 유일 인덱스 `ux_ds_<번호>_period`."""
    return f"ux_ds_{_number(dataset_id, '데이터셋')}_period"


def period_check_name(dataset_id: int) -> str:
    """기간 첫날 CHECK 제약 `ck_ds_<번호>_period`."""
    return f"ck_ds_{_number(dataset_id, '데이터셋')}_period"


def check_dynamic_name(name: object, kind: str | None = None) -> str:
    """규칙에 맞는 이름만 통과시킨다. `kind`(table·view·column·index·constraint)면 그 종류만."""
    if not isinstance(name, str) or len(name) > _MAX_IDENTIFIER_LENGTH:
        raise DdlNameError("동적 객체 이름 규칙에 맞지 않는다.")
    pattern = _NAME_PATTERNS[kind] if kind is not None else _ANY_NAME
    if pattern.fullmatch(name) is None:
        raise DdlNameError("동적 객체 이름 규칙에 맞지 않는다.")
    return name


def check_object_kind(kind: str) -> str:
    """만들려는 객체 종류가 허용 목록(표·뷰·인덱스·제약) 안인지 확인한다."""
    if kind not in ALLOWED_OBJECT_KINDS:
        raise DdlNotAllowedError(f"허용되지 않는 객체 종류: {kind!r}")
    return kind
