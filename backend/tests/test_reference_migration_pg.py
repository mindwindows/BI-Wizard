"""0009 `downgrade` 사전 점검 시험(06 §6 `0009` downgrade, 03b 32-3 C-3·D12). 실제 PostgreSQL 필요.

- 기준값을 읽는 뷰(`pg_depend` 의존)가 있으면 거부하고 **아무것도 바꾸지 않는다**(표·CHECK·뷰·
  `alembic_version` 불변). 같은 의존이 `DROP TABLE`도 막으므로 `CASCADE`는 쓰지 않는다.
- 새 감사 행(`reference.create`·`reference_value.add`·`reference_value.update`)이 하나만 있어도
  거부한다(감사 기록은 지우지 않는다).
- 둘 다 없으면 성공해 두 표가 사라지고 CHECK가 옛 정의(17개·4개)로 돌아오며, 다시 올리면 head와
  권한·구조가 같다.
- 한계(문서화): 서버 밖에서 `bi_owner`가 직접 넣은 기준값 행은 감사 행이 없어 점검하지 못한다.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

from app.config import get_settings
from app.db_metadata import audit_log
from migrations.roundtrip import take_snapshot
from tests.audit_helpers import Ctx
from tests.conftest import Db
from tests.formula_api_helpers import add_formula
from tests.reference_helpers import add_item, add_value
from tests.test_reference_pg import make_ref_dataset, seed_item

BACKEND = Path(__file__).resolve().parent.parent

PG_DEPEND_CHECK = (
    "SELECT count(*) FROM pg_depend d "
    "JOIN pg_rewrite r ON r.oid = d.objid "
    "JOIN pg_class c ON c.oid = r.ev_class "
    "WHERE d.classid = 'pg_rewrite'::regclass "
    "AND d.refclassid = 'pg_class'::regclass "
    "AND d.refobjid = 'public.reference_values'::regclass "
    "AND c.relkind = 'v'"
)
NEW_ACTIONS = ("reference.create", "reference_value.add", "reference_value.update")


@pytest.fixture
def db(pg_app_engine, pg_owner_engine, clean_pg):
    yield Db("pg", pg_app_engine, pg_owner_engine)


@pytest.fixture
def migration_env(pg_env, pg_owner_engine, clean_pg):
    config = Config(str(BACKEND / "alembic.ini"))
    with pytest.MonkeyPatch.context() as mp:
        pg_env.apply(mp)
        yield config
        command.upgrade(config, "head")  # 어떤 결과로 끝나도 head로 되돌려 다음 시험이 쓴다
    get_settings.cache_clear()


def _revision(engine: Engine) -> str:
    with engine.connect() as conn:
        return conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()


def _state(engine: Engine) -> dict:
    """downgrade가 건드릴 수 있는 것 전부: revision, 두 표, 제약 정의, 뷰, 감사 행."""
    with engine.connect() as conn:
        checks = dict(
            conn.execute(
                sa.text(
                    "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conname IN ('ck_audit_log_action', 'ck_audit_log_target_type')"
                )
            ).all()
        )
        tables = [
            r[0]
            for r in conn.execute(
                sa.text(
                    "SELECT tablename FROM pg_tables WHERE tablename LIKE 'reference\\_%' "
                    "ORDER BY 1"
                )
            )
        ]
        views = [
            r[0]
            for r in conn.execute(
                sa.text("SELECT viewname FROM pg_views WHERE schemaname = 'bi_data' ORDER BY 1")
            )
        ]
        rows = {
            name: conn.execute(sa.text(f"SELECT count(*) FROM {name}")).scalar_one()  # noqa: S608
            for name in tables
        }
        audits = conn.execute(sa.select(sa.func.count()).select_from(audit_log)).scalar_one()
        return {
            "revision": _revision(engine),
            "checks": checks,
            "tables": tables,
            "views": views,
            "rows": rows,
            "audits": audits,
        }


def seed_audit(engine: Engine, action: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            sa.insert(audit_log).values(
                actor_source="cli",
                action=action,
                target_type="reference" if action in NEW_ACTIONS else "dataset",
                target_id=1,
                details={},
            )
        )


def test_downgrade_refuses_while_a_view_reads_reference_values_and_changes_nothing(
    ctx: Ctx, db: Db, migration_env, pg_owner_engine
):
    ds = make_ref_dataset(ctx)
    seed_item(ctx, "전기요금", {2026: "1"})  # 감사 행 없이 소유자로 심는다(뷰만이 거부 이유)
    add_formula(ctx.call, ds["id"], "요금", 'REF("전기요금")')
    with pg_owner_engine.connect() as conn:
        assert conn.execute(sa.text(PG_DEPEND_CHECK)).scalar_one() >= 2  # dv_와 de_ 둘 다
    before = _state(pg_owner_engine)
    snapshot = take_snapshot(pg_owner_engine)
    with pytest.raises(Exception, match="뷰가 있습니다") as error:
        command.downgrade(migration_env, "0008")
    assert "아무것도 바꾸지 않았습니다" in str(error.value)
    assert _state(pg_owner_engine) == before
    assert before["revision"] == "0009" and before["tables"] == [
        "reference_items",
        "reference_values",
    ]
    assert "reference_value.update" in before["checks"]["ck_audit_log_action"]
    assert take_snapshot(pg_owner_engine) == snapshot  # 권한·구조도 그대로
    with pg_owner_engine.connect() as conn:  # 뷰는 여전히 읽힌다
        assert conn.execute(sa.text(f"SELECT count(*) FROM bi_data.dv_{ds['id']}")).scalar() == 0  # noqa: S608


def test_the_dependency_check_is_empty_without_the_view_and_downgrade_then_succeeds(
    ctx: Ctx, db: Db, migration_env, pg_owner_engine
):
    """양성 대조: 뷰를 지우면 점검 결과가 비고(`CASCADE` 없이) downgrade가 성공한다."""
    ds = make_ref_dataset(ctx)
    seed_item(ctx, "전기요금", {2026: "1"})
    add_formula(ctx.call, ds["id"], "요금", 'REF("전기요금")')
    with pg_owner_engine.connect() as conn:
        assert conn.execute(sa.text(PG_DEPEND_CHECK)).scalar_one() >= 2
    with pg_owner_engine.begin() as conn:  # 뷰만 지운다(감사 행에는 reference 행위가 없다)
        conn.execute(sa.text(f"DROP VIEW bi_data.de_{ds['id']}"))
        conn.execute(sa.text(f"DROP VIEW bi_data.dv_{ds['id']}"))
    with pg_owner_engine.connect() as conn:
        assert conn.execute(sa.text(PG_DEPEND_CHECK)).scalar_one() == 0
    command.downgrade(migration_env, "0008")
    state = _state(pg_owner_engine)
    assert state["revision"] == "0008" and state["tables"] == []
    assert "reference.create" not in state["checks"]["ck_audit_log_action"]
    assert "'reference'" not in state["checks"]["ck_audit_log_target_type"]
    assert state["checks"]["ck_audit_log_action"].count("::text") == 17
    assert state["checks"]["ck_audit_log_target_type"].count("::text") == 4


@pytest.mark.parametrize("action", NEW_ACTIONS)
def test_downgrade_refuses_while_reference_audit_rows_exist_even_without_any_view(
    migration_env, pg_owner_engine, action
):
    seed_audit(pg_owner_engine, "dataset.create")  # 옛 행위의 감사 행은 있어도 된다
    seed_audit(pg_owner_engine, action)
    before = _state(pg_owner_engine)
    assert before["views"] == []
    with pytest.raises(Exception, match="감사 기록이 있습니다") as error:
        command.downgrade(migration_env, "0008")
    assert "아무것도 바꾸지 않았습니다" in str(error.value)
    assert _state(pg_owner_engine) == before
    assert before["audits"] == 2  # 감사 기록은 지워지지 않았다


def test_downgrade_succeeds_without_views_and_audit_rows_and_restores_everything_on_upgrade(
    migration_env, pg_owner_engine
):
    seed_audit(pg_owner_engine, "dataset.create")
    at_head = take_snapshot(pg_owner_engine)
    command.downgrade(migration_env, "0008")
    at_0008 = take_snapshot(pg_owner_engine)
    assert _state(pg_owner_engine)["revision"] == "0008"
    # 기준값 표·권한이 사라지고 CHECK 두 개만 옛 정의다. 나머지 권한은 그대로다.
    for key in ("roles", "memberships", "schemas", "default_acl"):
        assert at_0008[key] == at_head[key], key
    gone = {r[1] for r in at_head["relations"]} - {r[1] for r in at_0008["relations"]}
    assert {"reference_items", "reference_values"} <= gone
    assert all(name.startswith(("reference_", "uq_reference", "pk_reference")) for name in gone), (
        gone
    )
    assert {(r[1], r[2]) for r in at_head["column_acl"]} - {
        (r[1], r[2]) for r in at_0008["column_acl"]
    } == {("reference_items", "description"), ("reference_values", "number_value")}
    command.upgrade(migration_env, "head")
    assert take_snapshot(pg_owner_engine) == at_head  # 올리면 head와 완전히 같다
    assert _state(pg_owner_engine)["audits"] == 1


def test_known_limit_reference_rows_inserted_outside_the_server_are_not_detected(
    ctx: Ctx, migration_env, pg_owner_engine
):
    """서버 밖에서 `bi_owner`가 직접 넣은 기준값 행은 감사 행이 없어 점검하지 못한다(06 §6 한계).

    그래서 downgrade가 성공하고 그 행은 표와 함께 사라진다. 운영에서는 downgrade를 하지 않는다.
    """
    item = add_item(Db("pg", pg_owner_engine, pg_owner_engine), "직접 넣음", ctx.uid("admin"))
    add_value(Db("pg", pg_owner_engine, pg_owner_engine), item, 2026, "1", ctx.uid("admin"))
    command.downgrade(migration_env, "0008")
    assert _state(pg_owner_engine)["tables"] == []
