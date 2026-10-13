"""동적 객체 이름 규칙(04 부록 A, 06 §1): 번호로만 만들고 규칙 밖은 거부한다. DB 없이 실행."""

import pytest

from app import ddl
from app.db_metadata import is_dynamic_name


def test_names_are_built_from_numbers_only():
    assert ddl.dataset_table_name(7) == "ds_7"
    assert ddl.view_name(7) == "dv_7"
    assert ddl.error_view_name(7) == "de_7"
    assert ddl.column_name(12) == "c_12"
    assert ddl.error_column_name(12) == "e_12"
    assert ddl.period_index_name(7) == "ux_ds_7_period"
    assert ddl.period_check_name(7) == "ck_ds_7_period"


def test_built_names_follow_the_static_dynamic_name_rule():
    for name in (ddl.dataset_table_name(3), ddl.view_name(3), ddl.error_view_name(3)):
        assert is_dynamic_name(name)


@pytest.mark.parametrize("bad", [0, -1, True, False, 1.0, "1", None, "7; DROP TABLE x", [1]])
def test_number_must_be_a_positive_integer(bad):
    for builder in (
        ddl.dataset_table_name,
        ddl.view_name,
        ddl.error_view_name,
        ddl.column_name,
        ddl.error_column_name,
        ddl.period_index_name,
        ddl.period_check_name,
    ):
        with pytest.raises(ddl.DdlNameError):
            builder(bad)


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("ds_1", "table"),
        ("ds_123", "table"),
        ("dv_1", "view"),
        ("de_9", "view"),
        ("c_5", "column"),
        ("e_5", "column"),
        ("row_id", "column"),
        ("team", "column"),
        ("ux_ds_4_period", "index"),
        ("ck_ds_4_period", "constraint"),
        ("ds_1", None),
        ("ux_ds_4_period", None),
    ],
)
def test_valid_names_pass(name, kind):
    assert ddl.check_dynamic_name(name, kind) == name


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("ds_0", "table"),
        ("ds_01", "table"),
        ("ds_", "table"),
        ("ds_1 ", "table"),
        ("ds_1;", "table"),
        ('ds_1"', "table"),
        ("DS_1", "table"),
        ("bi_data.ds_1", "table"),
        ("evil", "table"),
        ("public.users", None),
        ("users", None),
        ("dv_1", "table"),  # 종류가 다르다
        ("ds_1", "view"),
        ("c_0", "column"),
        ("매출", "column"),
        ("ux_ds_1_period", "constraint"),
        ("ck_ds_1_period", "index"),
        ("ds_" + "9" * 70, "table"),  # 식별자 63자 초과
        (None, None),
        (5, "table"),
    ],
)
def test_names_outside_the_rule_are_refused(name, kind):
    with pytest.raises(ddl.DdlNameError):
        ddl.check_dynamic_name(name, kind)


def test_object_kind_allow_list_is_tables_views_indexes_constraints():
    assert ddl.ALLOWED_OBJECT_KINDS == {"table", "view", "index", "constraint"}
    for kind in ("table", "view", "index", "constraint"):
        assert ddl.check_object_kind(kind) == kind
    for kind in ("function", "sequence", "type", "schema", "role", "grant", "trigger", "extension"):
        with pytest.raises(ddl.DdlNotAllowedError):
            ddl.check_object_kind(kind)
