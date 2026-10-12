"""런타임 동적 DDL(`ddl`): `bi_data` schema의 `ds_`/`dv_`/`de_` 객체를 만드는 유일한 모듈(04 §2-1).

이름 규칙은 `names`, 실행은 `dynamic`이다. 사용 규칙은 `dynamic.py` 머리말과 `bi-review` 7-4.
"""

from app.ddl.dynamic import (
    ALLOWED_DDL_ELEMENTS,
    VIEW_KINDS,
    add_period_rules,
    add_raw_column,
    create_dataset_table,
    create_view,
    drop_period_rules,
    drop_view,
    run_ddl,
    view_column_names,
)
from app.ddl.names import (
    ALLOWED_OBJECT_KINDS,
    DYNAMIC_SCHEMA,
    DdlError,
    DdlExecutionError,
    DdlNameError,
    DdlNotAllowedError,
    DdlVerificationError,
    check_dynamic_name,
    check_object_kind,
    column_name,
    dataset_table_name,
    error_column_name,
    error_view_name,
    period_check_name,
    period_index_name,
    view_name,
)

__all__ = [
    "ALLOWED_DDL_ELEMENTS",
    "ALLOWED_OBJECT_KINDS",
    "DYNAMIC_SCHEMA",
    "VIEW_KINDS",
    "DdlError",
    "DdlExecutionError",
    "DdlNameError",
    "DdlNotAllowedError",
    "DdlVerificationError",
    "add_period_rules",
    "add_raw_column",
    "check_dynamic_name",
    "check_object_kind",
    "column_name",
    "create_dataset_table",
    "create_view",
    "dataset_table_name",
    "drop_period_rules",
    "drop_view",
    "error_column_name",
    "error_view_name",
    "period_check_name",
    "period_index_name",
    "run_ddl",
    "view_column_names",
    "view_name",
]
