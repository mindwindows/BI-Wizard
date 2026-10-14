"""기준값 표 DB 권한·제약 시험(06 §4-2 "FU-3 권한 매트릭스 시험 행"). 실제 PostgreSQL 필요.

정상: `bi_app`의 두 표 SELECT·INSERT(시퀀스 권한 없이), 값 열·설명 열 UPDATE, 새 감사 행위 3개와
`target_type='reference'` 감사 INSERT. 부정: 불변 열 UPDATE·DELETE·TRUNCATE·DDL 거부(42501),
`bi_readonly`의 직접 SELECT 거부, CHECK(연도 1899·10000, NaN·±Infinity, 이름 빈 글자·51자)·UNIQUE
(`name`, `item_id`+`year`)·FK 위반, 새 감사 CHECK(`reference.delete`·
`target_type='reference_x'`) 거부.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, delete, func, insert, select, update
from sqlalchemy.exc import DBAPIError

from app.audit.actions import ACTIONS
from app.db_metadata import audit_log, reference_items, reference_values, users
from tests.test_static_acl import (
    CHECK_VIOLATION,
    FOREIGN_KEY_VIOLATION,
    INSUFFICIENT_PRIVILEGE,
    UNIQUE_VIOLATION,
    sqlstate,
)


@pytest.fixture
def seeded(pg_owner_engine: Engine, clean_pg) -> dict[str, int]:
    with pg_owner_engine.begin() as conn:
        user = conn.execute(
            insert(users).values(login_id="ref", display_name="기준값").returning(users.c.id)
        ).scalar_one()
        item = conn.execute(
            insert(reference_items)
            .values(name="전기요금", description="설명", created_by=user)
            .returning(reference_items.c.id)
        ).scalar_one()
        value = conn.execute(
            insert(reference_values)
            .values(item_id=item, year=2026, number_value=Decimal("12.5"), created_by=user)
            .returning(reference_values.c.id)
        ).scalar_one()
    return {"user": user, "item": item, "value": value}


def run(engine: Engine, statement) -> None:
    with engine.begin() as conn:
        conn.execute(statement)


def state(owner: Engine) -> tuple:
    with owner.connect() as conn:
        return (
            conn.execute(select(reference_items).order_by(reference_items.c.id)).all(),
            conn.execute(select(reference_values).order_by(reference_values.c.id)).all(),
        )


# --- 정상 ----


def test_bi_app_inserts_reads_and_updates_only_the_value_and_description(
    seeded, pg_app_engine, pg_owner_engine
):
    with pg_app_engine.begin() as conn:  # 시퀀스 GRANT 없이 identity 번호가 붙는다
        item = conn.execute(
            insert(reference_items)
            .values(name="수도요금", created_by=seeded["user"])
            .returning(reference_items.c.id)
        ).scalar_one()
        value = conn.execute(
            insert(reference_values)
            .values(item_id=item, year=1900, number_value=Decimal("1"), created_by=seeded["user"])
            .returning(reference_values.c.id)
        ).scalar_one()
        conn.execute(
            update(reference_values)
            .where(reference_values.c.id == value)
            .values(number_value=Decimal("2.50"))
        )
        conn.execute(
            update(reference_items)
            .where(reference_items.c.id == item)
            .values(description="바뀐 설명")
        )
        assert conn.execute(select(func.count()).select_from(reference_values)).scalar_one() == 2
    with pg_owner_engine.connect() as conn:
        row = conn.execute(select(reference_values).where(reference_values.c.id == value)).one()
        assert row.number_value == Decimal("2.50") and row.year == 1900
        description = conn.execute(
            select(reference_items.c.description).where(reference_items.c.id == item)
        ).scalar_one()
        assert description == "바뀐 설명"


def test_bi_app_inserts_the_new_audit_actions_for_target_type_reference(
    seeded, pg_app_engine, pg_owner_engine
):
    for action in ("reference.create", "reference_value.add", "reference_value.update"):
        assert ACTIONS[action].target_type == "reference"
        run(
            pg_app_engine,
            insert(audit_log).values(
                actor_source="user",
                actor_user_id=seeded["user"],
                action=action,
                target_type="reference",
                target_id=seeded["item"],
                details={"target_name": "전기요금"},
            ),
        )
    with pg_owner_engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(audit_log)).scalar_one() == 3


# --- 부정: 권한 ----


IMMUTABLE_ITEM = {"id": 999, "name": "다른 이름", "created_by": 1, "created_at": sa.func.now()}
IMMUTABLE_VALUE = {
    "id": 999,
    "item_id": 1,
    "year": 2027,
    "created_by": 1,
    "created_at": sa.func.now(),
}


@pytest.mark.parametrize("column", IMMUTABLE_ITEM)
def test_bi_app_cannot_update_immutable_item_columns(
    seeded, pg_app_engine, pg_owner_engine, column
):
    before = state(pg_owner_engine)
    with pytest.raises(DBAPIError) as error:
        run(
            pg_app_engine,
            update(reference_items).values(**{column: IMMUTABLE_ITEM[column]}),
        )
    assert sqlstate(error.value) == INSUFFICIENT_PRIVILEGE
    assert state(pg_owner_engine) == before


@pytest.mark.parametrize("column", IMMUTABLE_VALUE)
def test_bi_app_cannot_update_immutable_value_columns(
    seeded, pg_app_engine, pg_owner_engine, column
):
    before = state(pg_owner_engine)
    with pytest.raises(DBAPIError) as error:
        run(
            pg_app_engine,
            update(reference_values).values(**{column: IMMUTABLE_VALUE[column]}),
        )
    assert sqlstate(error.value) == INSUFFICIENT_PRIVILEGE
    assert state(pg_owner_engine) == before


@pytest.mark.parametrize("table", [reference_items, reference_values])
def test_bi_app_cannot_delete_truncate_or_alter_the_reference_tables(
    seeded, pg_app_engine, pg_owner_engine, table
):
    before = state(pg_owner_engine)
    statements = (
        delete(table),
        sa.schema.DDL(f"TRUNCATE TABLE {table.name}"),
        sa.schema.DDL(f"DROP TABLE {table.name}"),
        sa.schema.DDL(f"ALTER TABLE {table.name} DISABLE TRIGGER ALL"),
        sa.schema.DDL(f"CREATE INDEX ix_evil ON {table.name} (id)"),
    )
    for statement in statements:
        with pytest.raises(DBAPIError) as error:
            run(pg_app_engine, statement)
        assert sqlstate(error.value) == INSUFFICIENT_PRIVILEGE, str(statement)
    assert state(pg_owner_engine) == before


def test_bi_readonly_cannot_read_the_reference_tables_directly(
    seeded, pg_readonly_engine, pg_owner_engine
):
    for table in (reference_items, reference_values):
        with pytest.raises(DBAPIError) as error, pg_readonly_engine.connect() as conn:
            conn.execute(select(table))
        assert sqlstate(error.value) == INSUFFICIENT_PRIVILEGE
        with pytest.raises(DBAPIError) as error, pg_readonly_engine.connect() as conn:
            conn.execute(select(table.c.id))  # 열 하나만 읽어도 거부된다
        assert sqlstate(error.value) == INSUFFICIENT_PRIVILEGE
    with pg_owner_engine.connect() as conn:
        for table in ("reference_items", "reference_values"):
            for name in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES"):
                granted = conn.execute(
                    select(func.has_table_privilege("bi_readonly", table, name))
                ).scalar()
                assert granted is False, (table, name)
            acl = conn.execute(
                sa.text("SELECT relacl::text FROM pg_class WHERE relname = :n"), {"n": table}
            ).scalar_one()
            assert not any(
                part.startswith("=") for part in acl.strip("{}").split(",")
            )  # PUBLIC 없음


# --- 부정: CHECK·UNIQUE·FK ----


@pytest.mark.parametrize(
    ("year", "ok"),
    [(1899, False), (1900, True), (9999, True), (10000, False), (0, False), (-1, False)],
)
def test_year_check_accepts_only_1900_to_9999(seeded, pg_app_engine, year, ok):
    statement = insert(reference_values).values(
        item_id=seeded["item"], year=year, number_value=Decimal(1), created_by=seeded["user"]
    )
    if ok:
        run(pg_app_engine, statement)
        return
    with pytest.raises(DBAPIError) as error:
        run(pg_app_engine, statement)
    assert sqlstate(error.value) == CHECK_VIOLATION
    assert "ck_reference_values_year" in str(error.value.orig)


@pytest.mark.parametrize("text", ["NaN", "Infinity", "-Infinity"])
def test_value_check_rejects_nan_and_infinity(seeded, pg_app_engine, pg_owner_engine, text):
    """PostgreSQL에서 NaN은 모든 수보다 크게 비교되므로 NaN·±Infinity를 함께 거른다."""
    for engine in (pg_app_engine, pg_owner_engine):
        with pytest.raises(DBAPIError) as error:
            run(
                engine,
                insert(reference_values).values(
                    item_id=seeded["item"],
                    year=2030,
                    number_value=Decimal(text),
                    created_by=seeded["user"],
                ),
            )
        assert sqlstate(error.value) == CHECK_VIOLATION
        assert "ck_reference_values_finite" in str(error.value.orig)
    with pytest.raises(DBAPIError) as error:  # 정정(UPDATE)도 같은 CHECK가 막는다
        run(
            pg_app_engine,
            update(reference_values)
            .where(reference_values.c.id == seeded["value"])
            .values(number_value=Decimal(text)),
        )
    assert sqlstate(error.value) == CHECK_VIOLATION


def test_value_check_accepts_large_and_precise_numbers(seeded, pg_app_engine):
    for year, value in (
        (2030, Decimal("9" * 38)),
        (2031, Decimal("-" + "9" * 38)),
        (2032, Decimal("0." + "1" * 38)),
        (2033, Decimal("0")),
    ):
        run(
            pg_app_engine,
            insert(reference_values).values(
                item_id=seeded["item"], year=year, number_value=value, created_by=seeded["user"]
            ),
        )


@pytest.mark.parametrize(
    ("name", "ok"), [("가", True), ("가" * 50, True), ("", False), ("가" * 51, False)]
)
def test_item_name_length_check(seeded, pg_app_engine, name, ok):
    statement = insert(reference_items).values(name=name, created_by=seeded["user"])
    if ok:
        run(pg_app_engine, statement)
        return
    with pytest.raises(DBAPIError) as error:
        run(pg_app_engine, statement)
    assert sqlstate(error.value) == CHECK_VIOLATION
    assert "ck_reference_items_name_length" in str(error.value.orig)


def test_duplicate_name_and_duplicate_item_year_are_unique_violations(seeded, pg_app_engine):
    with pytest.raises(DBAPIError) as error:
        run(
            pg_app_engine,
            insert(reference_items).values(name="전기요금", created_by=seeded["user"]),
        )
    assert sqlstate(error.value) == UNIQUE_VIOLATION
    assert "uq_reference_items_name" in str(error.value.orig)
    with pytest.raises(DBAPIError) as error:
        run(
            pg_app_engine,
            insert(reference_values).values(
                item_id=seeded["item"],
                year=2026,
                number_value=Decimal(1),
                created_by=seeded["user"],
            ),
        )
    assert sqlstate(error.value) == UNIQUE_VIOLATION
    assert "uq_reference_values_item_id_year" in str(error.value.orig)


def test_foreign_keys_reject_unknown_item_and_user(seeded, pg_app_engine):
    for statement, constraint in (
        (
            insert(reference_values).values(
                item_id=999999, year=2030, number_value=Decimal(1), created_by=seeded["user"]
            ),
            "fk_reference_values_item_id_reference_items",
        ),
        (
            insert(reference_values).values(
                item_id=seeded["item"], year=2030, number_value=Decimal(1), created_by=999999
            ),
            "fk_reference_values_created_by_users",
        ),
        (
            insert(reference_items).values(name="새 항목", created_by=999999),
            "fk_reference_items_created_by_users",
        ),
    ):
        with pytest.raises(DBAPIError) as error:
            run(pg_app_engine, statement)
        assert sqlstate(error.value) == FOREIGN_KEY_VIOLATION
        assert constraint in str(error.value.orig)


def test_new_audit_checks_reject_unknown_action_and_target_type(seeded, pg_app_engine):
    base = {
        "actor_source": "user",
        "actor_user_id": seeded["user"],
        "action": "reference.create",
        "target_type": "reference",
        "target_id": 1,
        "details": {"target_name": "x"},
    }
    for override, constraint in (
        ({"action": "reference.delete"}, "ck_audit_log_action"),
        ({"action": "reference_value.remove"}, "ck_audit_log_action"),
        ({"target_type": "reference_x"}, "ck_audit_log_target_type"),
        ({"target_type": "reference_value"}, "ck_audit_log_target_type"),
    ):
        with pytest.raises(DBAPIError) as error:
            run(pg_app_engine, insert(audit_log).values(**{**base, **override}))
        assert sqlstate(error.value) == CHECK_VIOLATION
        assert constraint in str(error.value.orig)


def test_the_reference_tables_are_in_public_and_owned_by_bi_owner(seeded, pg_owner_engine):
    with pg_owner_engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT tablename, tableowner, schemaname FROM pg_tables "
                "WHERE tablename IN ('reference_items', 'reference_values')"
            )
        ).all()
    assert {(r.tablename, r.tableowner, r.schemaname) for r in rows} == {
        ("reference_items", "bi_owner", "public"),
        ("reference_values", "bi_owner", "public"),
    }
