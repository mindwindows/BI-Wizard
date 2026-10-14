"""마이그레이션 규칙(D2, D3, D5) 정적 점검과 오프라인 SQL 생성 점검. DB 없이 실행한다.

DB가 필요한 점검(`alembic check`, 왕복 스냅샷 비교, 권한 상태)은 compose profile `test`의
테스트 DB에서 `python -m migrations.roundtrip`으로 실행한다(skills/local-environment/SKILL.md).
"""

import ast
import re
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND = Path(__file__).resolve().parent.parent
VERSIONS = BACKEND / "migrations" / "versions"
EXECUTORS = {"execute", "exec_driver_sql"}
TEXT_WRAPPERS = {"text"}  # sa.text("고정문"), text("고정문")

# D2 안전장치(AP-11, "정적 표 대상"): `public` 정적 표 마이그레이션의 DROP(op.drop_*, SQL의 DROP)은
# 사용자 확인 기록이 있어야 한다. `downgrade()`의 op.drop_table도 DROP이다.
# 동적 객체(`bi_data` schema의 ds_*, dv_*, de_*)는 마이그레이션 대상이 아니므로
# test_migrations_do_not_manage_bi_data_objects가 막는다.
# 확인을 받았다면 {"revision 파일 이름": "DROP 확인: 사용자 승인 (날짜, 근거)"} 형태로
# 여기에 기록한다. **확인이 아직 없는 항목**은 `DROP_PENDING_PREFIX`로 시작하는 문구로 기록하며
# 승인으로 읽지 않는다(문구에 "사용자 승인"을 쓰지 않는다). 지금은 대기 항목이 없고(0007은
# 2026-10-14 승인), 아래 `test_no_pending_drop_confirmations`가 대기 항목이 생기는 것을 막는다.
DROP_PENDING_PREFIX = "사용자 확인 대기("
DROP_APPROVED: dict[str, str] = {
    # 0003 downgrade()의 op.drop_table 3개(team_members, teams, users)는 06 §6의 표 역순 삭제다.
    # 새 승인이 아니라 기존 D2 규칙의 적용이며, Gate ③ 06 §6 승인(2026-10-11)과
    # FU-1 계획 승인(03b 15-2, 2026-10-12)에 포함된다.
    "20261012_0003_users_teams_members.py": (
        "DROP 확인: 사용자 승인 (2026-10-11 Gate ③ 06 §6 승인, 2026-10-12 FU-1 계획 승인 "
        "03b 15-2, 06 §6 downgrade 표 역순 삭제 3개: "
        "team_members, teams, users. 정적 표 대상, 동적 객체 아님)"
    ),
    # 0004 downgrade()의 op.drop_constraint 1개(순환 FK)와 op.drop_table 2개(dataset_columns,
    # datasets)는 06 §6의 표 역순 삭제다. 새 승인이 아니라 기존 D2 규칙의 적용이며, Gate ③ 06 §6
    # 승인(2026-10-11)과 FU-1 계획 승인(03b 15-2, 2026-10-12), 1b 진행 지시(03b 17-2)에 포함된다.
    "20261012_0004_datasets_columns.py": (
        "DROP 확인: 사용자 승인 (2026-10-11 Gate ③ 06 §6 승인, 2026-10-12 FU-1 계획 승인 "
        "03b 15-2, 1b 진행 03b 17-2, 06 §6 downgrade 표 역순 삭제: 순환 FK "
        "fk_datasets_id_dataset_columns 해제, dataset_columns, datasets. "
        "정적 표 대상, 동적 객체 아님)"
    ),
    # 0005 downgrade()의 op.drop_table 2개(formula_deps, formulas)는 06 §6의 표 역순 삭제다. 새
    # 승인이 아니라 기존 D2 규칙의 적용이며, Gate ③ 06 §6 승인(2026-10-11)과 FU-1 계획 승인(03b
    # 15-2, 2026-10-12), 1d 진행 지시(03b 19-2)에 포함된다.
    "20261012_0005_formulas.py": (
        "DROP 확인: 사용자 승인 (2026-10-11 Gate ③ 06 §6 승인, 2026-10-12 FU-1 계획 승인 "
        "03b 15-2, 1d 진행 03b 19-2, 06 §6 downgrade 표 역순 삭제: formula_deps, formulas. "
        "정적 표 대상, 동적 객체 아님)"
    ),
    # 0006 downgrade()의 op.drop_table 2개(superset_dashboards, superset_datasets)는 06 §6의 표 역순
    # 삭제다(두 표는 서로 참조하지 않는다). 새 승인이 아니라 기존 D2 규칙의 적용이며, Gate ③ 06 §6
    # 승인(2026-10-11)과 FU-1 계획 승인(03b 15-2, 2026-10-12), 1e 착수 승인(03b 21-3, 23)에
    # 포함된다.
    "20261012_0006_superset.py": (
        "DROP 확인: 사용자 승인 (2026-10-11 Gate ③ 06 §6 승인, 2026-10-12 FU-1 계획 승인 "
        "03b 15-2, 1e 착수 승인 03b 21-3·23, 06 §6 downgrade 표 삭제: superset_dashboards, "
        "superset_datasets. 정적 표 대상, 동적 객체 아님)"
    ),
    # 0007 downgrade()의 op.drop_table 1개(audit_log). 03b 29-1 ④의 "DROP 없음"은 upgrade() 기준으로
    # 읽었고, downgrade()의 DROP은 사용자가 2026-10-14에 승인했다(03b 29-3).
    "20261013_0007_audit_log.py": (
        "DROP 확인: 사용자 승인 (2026-10-14, 03b 29-3 답: 0007 downgrade()의 "
        "op.drop_table(audit_log) 1개. 정적 표 대상, 동적 객체 아님. downgrade는 감사 기록 전체를 "
        "지우므로 운영에서는 하지 않고 실행 전 백업 필수)"
    ),
}

# D5: upgrade/downgrade가 비어 있는 revision은 원칙적으로 미구현으로 본다.
# 만들 업무 객체가 없는 baseline처럼 의도적인 no-op만 revision id로 허용한다.
# (모듈 docstring에 사유가 있어야 한다.)
INTENTIONAL_NOOP = {"0001"}

DROP_SQL = re.compile(r"\bDROP\b", re.IGNORECASE)


def _alembic_config() -> Config:
    return Config(str(BACKEND / "alembic.ini"))


def _revision_files() -> list[Path]:
    return sorted(VERSIONS.glob("*.py"))


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    return getattr(func, "id", "")


def _is_fixed_sql(node: ast.expr) -> bool:
    """보간 없는 문자열 상수이거나 sa.text("상수")인가."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return True
    if isinstance(node, ast.Call) and _call_name(node) in TEXT_WRAPPERS:
        return bool(node.args) and _is_fixed_sql(node.args[0]) and not node.keywords
    return False


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    return next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)


def _revision_id(tree: ast.Module) -> str:
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "revision":
            return ast.literal_eval(node.value)
    raise AssertionError("revision 변수가 없다")


def _is_trivial_body(func: ast.FunctionDef) -> bool:
    for stmt in func.body:
        if isinstance(stmt, ast.Pass):
            continue
        if isinstance(stmt, ast.Return) and (
            stmt.value is None
            or (isinstance(stmt.value, ast.Constant) and stmt.value.value is None)
        ):
            continue
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            continue
        return False
    return True


def _raises_not_implemented(func: ast.FunctionDef) -> bool:
    for node in ast.walk(func):
        if isinstance(node, ast.Raise) and node.exc is not None:
            target = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
            if getattr(target, "id", "") == "NotImplementedError":
                return True
    return False


def _docstring_nodes(tree: ast.Module) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.FunctionDef | ast.ClassDef) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                ids.add(id(first.value))
    return ids


def _drop_findings(tree: ast.Module) -> list[str]:
    findings = []
    docstrings = _docstring_nodes(tree)  # docstring은 SQL이 아니다.
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _call_name(node).startswith("drop_"):
            findings.append(f"{_call_name(node)}(), 줄 {node.lineno}")
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
            and DROP_SQL.search(node.value)
        ):
            findings.append(f"SQL 문자열의 DROP, 줄 {node.lineno}")
    return findings


def _drop_findings_in(function: ast.FunctionDef) -> list[str]:
    """함수 하나 안의 DROP(op.drop_*, SQL 문자열의 DROP)."""
    findings = []
    for node in ast.walk(function):
        if isinstance(node, ast.Call) and _call_name(node).startswith("drop_"):
            findings.append(f"{_call_name(node)}(), 줄 {node.lineno}")
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and DROP_SQL.search(node.value)
        ):
            findings.append(f"SQL 문자열의 DROP, 줄 {node.lineno}")
    return findings


def test_single_head():
    """head가 둘이면 두 브랜치가 동시에 revision을 추가한 것이다(병합 필요). DB 없이 검사한다."""
    heads = ScriptDirectory.from_config(_alembic_config()).get_heads()
    assert len(heads) == 1, f"head가 {len(heads)}개: {heads}"
    assert heads == ["0007"]


def test_revision_chain_baseline_privileges_access_then_dataset_tables():
    script = ScriptDirectory.from_config(_alembic_config())
    assert [r.revision for r in script.walk_revisions()] == [
        "0007",
        "0006",
        "0005",
        "0004",
        "0003",
        "0002",
        "0001",
    ]
    assert script.get_revision("0001").down_revision is None
    assert script.get_revision("0002").down_revision == "0001"
    assert script.get_revision("0003").down_revision == "0002"
    assert script.get_revision("0004").down_revision == "0003"
    assert script.get_revision("0005").down_revision == "0004"
    assert script.get_revision("0006").down_revision == "0005"
    assert script.get_revision("0007").down_revision == "0006"


def test_every_revision_defines_upgrade_and_downgrade():
    for path in _revision_files():
        names = {n.name for n in _parse(path).body if isinstance(n, ast.FunctionDef)}
        assert {"upgrade", "downgrade"} <= names, path.name


def test_migration_sql_has_no_interpolation():
    """D3: execute 계열에는 보간 없는 문자열 상수 또는 sa.text("상수")만 넘길 수 있다."""
    for path in _revision_files():
        for node in ast.walk(_parse(path)):
            if isinstance(node, ast.Call) and _call_name(node) in EXECUTORS:
                assert node.args, path.name
                assert _is_fixed_sql(node.args[0]), f"{path.name} 줄 {node.lineno}: SQL 보간 금지"


@pytest.mark.parametrize(
    ("source", "allowed"),
    [
        ('op.execute("SELECT 1")', True),
        ('op.execute(sa.text("SELECT 1"))', True),
        ('op.execute(text("SELECT 1"))', True),
        ('op.execute(f"SELECT {x}")', False),
        ('op.execute("SELECT %s" % x)', False),
        ('op.execute("SELECT {}".format(x))', False),
        ('op.execute("SELECT " + x)', False),
        ('op.execute(sa.text(f"SELECT {x}"))', False),
        ('op.execute(sa.text("SELECT :a").bindparams(a=1))', False),
    ],
)
def test_fixed_sql_detector(source, allowed):
    call = ast.parse(source).body[0].value
    assert _is_fixed_sql(call.args[0]) is allowed


def _is_approved(note: str) -> bool:
    return "DROP 확인: 사용자 승인" in note


def _is_pending(note: str) -> bool:
    """확인 대기 표시. 승인 문구가 섞여 있으면 대기가 아니다(승인으로 오인되는 기록을 막는다)."""
    return note.startswith(DROP_PENDING_PREFIX) and "사용자 승인" not in note


def test_drop_requires_recorded_user_approval():
    """D2: DROP(op.drop_*, SQL DROP)이 있으면 사용자 확인 기록(DROP_APPROVED)이 있어야 한다.

    기록은 승인("DROP 확인: 사용자 승인") 또는 명시적 확인 대기("사용자 확인 대기(")다. 기록이 아예
    없거나 어느 쪽도 아니면 실패한다.
    """
    for path in _revision_files():
        findings = _drop_findings(_parse(path))
        if findings:
            approval = DROP_APPROVED.get(path.name, "")
            assert _is_approved(approval) or _is_pending(approval), (
                f"{path.name}: DROP 발견({'; '.join(findings)}). 사용자 확인 기록이 필요하다."
            )


def test_no_pending_drop_confirmations():
    """확인 대기 DROP은 없다. 0007(03b 29-3)은 2026-10-14에 승인됐다.

    새 대기 항목이 조용히 생기지 않게 하고(대기 문구는 이 시험을 깨뜨린다), 모든 DROP 기록이
    승인 문구인지 확인한다.
    """
    pending = {name for name, note in DROP_APPROVED.items() if _is_pending(note)}
    assert pending == set()
    assert all(_is_approved(note) for note in DROP_APPROVED.values()), "승인이 아닌 DROP 기록"
    assert "2026-10-14" in DROP_APPROVED["20261013_0007_audit_log.py"]


def test_0007_drop_is_only_in_downgrade_never_in_upgrade():
    """0007은 upgrade()에 DROP이 없다(새 표와 인덱스만 추가, 03b 29-1 ④). DROP은 downgrade뿐."""
    tree = _parse(next(p for p in _revision_files() if "_0007_" in p.name))
    assert _drop_findings_in(_function(tree, "upgrade")) == []
    assert _drop_findings_in(_function(tree, "downgrade")) != []


def test_drop_detector_flags_drop_calls_and_sql():
    tree = ast.parse('op.drop_table("t")\nop.execute("DROP VIEW v")\nop.execute("SELECT 1")\n')
    assert len(_drop_findings(tree)) == 2


def _bi_data_findings(tree: ast.Module) -> list[str]:
    """`bi_data` 객체를 만들고 바꾸고 지우는 문장(허용: GRANT, REVOKE, ALTER DEFAULT PRIVILEGES)."""
    findings = []
    docstrings = _docstring_nodes(tree)
    allowed = re.compile(r"^\s*(GRANT|REVOKE|ALTER\s+DEFAULT\s+PRIVILEGES)\b", re.IGNORECASE)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
            and "bi_data" in node.value
            and not allowed.match(node.value)
        ):
            findings.append(f"bi_data를 다루는 SQL이 권한 부여가 아님, 줄 {node.lineno}")
        if isinstance(node, ast.keyword) and node.arg in {
            "schema",
            "referent_schema",
            "source_schema",
        }:
            if isinstance(node.value, ast.Constant) and node.value.value == "bi_data":
                findings.append(f"schema='bi_data' 인자, 줄 {node.value.lineno}")
    return findings


def test_migrations_do_not_manage_bi_data_objects():
    """D2: 동적 객체의 schema(`bi_data`)에는 권한만 부여한다. 표·뷰를 만들거나 지우지 않는다."""
    for path in _revision_files():
        findings = _bi_data_findings(_parse(path))
        assert not findings, f"{path.name}: {'; '.join(findings)}"


def test_bi_data_detector():
    def findings(src):
        return _bi_data_findings(ast.parse(src))

    assert findings('op.execute("GRANT USAGE ON SCHEMA bi_data TO bi_app")') == []
    adp = "ALTER DEFAULT PRIVILEGES FOR ROLE x IN SCHEMA bi_data GRANT SELECT ON TABLES TO y"
    assert findings(f'op.execute("{adp}")') == []
    assert findings('op.execute("CREATE TABLE bi_data.ds_1 (id int)")')
    assert findings('op.execute("DROP TABLE bi_data.ds_1")')
    assert findings('op.create_table("t", schema="bi_data")')


def test_static_metadata_has_no_dynamic_or_bi_data_tables():
    from app.db_metadata import is_dynamic_name, metadata

    for table in metadata.tables.values():
        assert table.schema is None, f"{table.name}: 정적 표는 public(schema 없음)에 둔다"
        assert not is_dynamic_name(table.name), f"{table.name}: 동적 객체 이름 규칙과 겹친다"


@pytest.mark.parametrize(
    ("name", "type_", "parents", "expected"),
    [
        ("bi_data", "schema", {}, False),
        ("public", "schema", {}, True),
        (None, "schema", {}, True),
        ("ds_1", "table", {"schema_name": "bi_data"}, False),
        ("anything", "table", {"schema_name": "bi_data"}, False),
        ("ds_12", "table", {"schema_name": None}, False),
        ("dv_3", "table", {"schema_name": None}, False),
        ("de_3", "table", {"schema_name": None}, False),
        ("datasets", "table", {"schema_name": None}, True),
        ("ds_x", "table", {"schema_name": None}, True),
        ("users", "table", {"schema_name": "public"}, True),
        ("ix_users_login_id", "index", {"schema_name": None, "table_name": "users"}, True),
    ],
)
def test_include_name_hook_excludes_dynamic_objects(name, type_, parents, expected):
    from app.db_metadata import include_name

    assert include_name(name, type_, parents) is expected


def test_include_object_hook_excludes_dynamic_objects():
    from sqlalchemy import Column, Integer, MetaData, Table

    from app.db_metadata import include_object

    meta = MetaData()
    dynamic = Table("anything", meta, Column("id", Integer), schema="bi_data")
    numbered = Table("ds_7", meta, Column("id", Integer))
    static = Table("datasets", meta, Column("id", Integer))
    assert include_object(dynamic, "anything", "table", True, None) is False
    assert include_object(numbered, "ds_7", "table", True, None) is False
    assert include_object(static, "datasets", "table", True, None) is True
    assert include_object(static.c.id, "id", "column", True, None) is True


def test_empty_revisions_are_rejected_unless_intentional_baseline():
    """D5: pass/NotImplementedError만 있는 revision은 미구현이다. 의도적 baseline만 예외다."""
    for path in _revision_files():
        tree = _parse(path)
        revision = _revision_id(tree)
        for name in ("upgrade", "downgrade"):
            func = _function(tree, name)
            assert not _raises_not_implemented(func), f"{path.name}: {name}()이 미구현"
            if _is_trivial_body(func):
                assert revision in INTENTIONAL_NOOP, f"{path.name}: {name}()이 비어 있다"
                assert ast.get_docstring(tree), (
                    f"{path.name}: 의도적 no-op의 사유(docstring)가 없다"
                )


def test_trivial_body_detector():
    def body(src):
        return _function(ast.parse(src), "f")

    assert _is_trivial_body(body("def f():\n    pass\n"))
    assert _is_trivial_body(body("def f():\n    return None\n"))
    assert not _is_trivial_body(body("def f():\n    op.create_table('t')\n"))
    assert _raises_not_implemented(body("def f():\n    raise NotImplementedError\n"))
    assert _raises_not_implemented(body("def f():\n    raise NotImplementedError('x')\n"))


def test_offline_upgrade_and_downgrade_generate_sql(capsys):
    """오프라인 SQL 생성은 DB 접속 정보와 비밀번호 없이 된다(env.py 오프라인 경로)."""
    config = _alembic_config()
    command.upgrade(config, "head", sql=True)
    upgrade_sql = capsys.readouterr().out
    assert "alembic_version" in upgrade_sql
    assert "GRANT USAGE, CREATE ON SCHEMA bi_data TO bi_app" in upgrade_sql
    assert "GRANT USAGE ON SCHEMA bi_data TO bi_readonly" in upgrade_sql
    assert (
        "ALTER DEFAULT PRIVILEGES FOR ROLE bi_app IN SCHEMA bi_data "
        "GRANT SELECT ON TABLES TO bi_readonly"
    ) in upgrade_sql
    # 0003: 정적 표 3개와 명시 GRANT(열 단위 UPDATE 포함).
    for table in ("users", "teams", "team_members"):
        assert f"CREATE TABLE {table} (" in upgrade_sql
    assert (
        "GRANT SELECT, INSERT, UPDATE (display_name, is_admin, is_active) ON users TO bi_app"
        in (upgrade_sql)
    )
    assert "GRANT SELECT, INSERT, UPDATE (name, is_active) ON teams TO bi_app" in upgrade_sql
    assert "GRANT SELECT, INSERT, UPDATE (role), DELETE ON team_members TO bi_app" in upgrade_sql
    # 0004: 데이터셋·열 정의 표, 순환 FK(표 생성 뒤 추가), 명시 GRANT(열 단위 UPDATE, DELETE 없음).
    for table in ("datasets", "dataset_columns"):
        assert f"CREATE TABLE {table} (" in upgrade_sql
    assert upgrade_sql.index("CREATE TABLE dataset_columns (") < upgrade_sql.index(
        "ADD CONSTRAINT fk_datasets_id_dataset_columns FOREIGN KEY(id, base_date_column_id)"
    )
    assert "REFERENCES dataset_columns (dataset_id, id)" in upgrade_sql
    assert (
        "GRANT SELECT, INSERT, UPDATE (name, date_unit, base_date_column_id, status, "
        "def_version, def_hash) ON datasets TO bi_app"
    ) in upgrade_sql
    assert (
        "GRANT SELECT, INSERT, UPDATE (display_name, type, required, rules, tag, position) "
        "ON dataset_columns TO bi_app"
    ) in upgrade_sql
    # 0005: 수식 표와 명시 GRANT(열 단위 UPDATE, formulas에 DELETE 없음).
    for table in ("formulas", "formula_deps"):
        assert f"CREATE TABLE {table} (" in upgrade_sql
    assert "GRANT SELECT, INSERT, UPDATE (expression, ast, ast_hash) ON formulas TO bi_app" in (
        upgrade_sql
    )
    assert "GRANT SELECT, INSERT, DELETE ON formula_deps TO bi_app" in upgrade_sql
    assert "CONSTRAINT ck_formula_deps_not_self CHECK (column_id <> depends_on_column_id)" in (
        upgrade_sql
    )
    # 0006: Superset 등록 표와 명시 GRANT(열 단위 UPDATE, DELETE 없음), 소문자 정규형 uuid CHECK.
    for table in ("superset_datasets", "superset_dashboards"):
        assert f"CREATE TABLE {table} (" in upgrade_sql
    assert (
        "GRANT SELECT, INSERT, UPDATE (superset_dataset_id, display_name, sync_status, "
        "synced_at, last_error) ON superset_datasets TO bi_app"
    ) in upgrade_sql
    assert "GRANT SELECT, INSERT, UPDATE (name, is_active) ON superset_dashboards TO bi_app" in (
        upgrade_sql
    )
    assert "CONSTRAINT uq_superset_dashboards_embedded_uuid UNIQUE (embedded_uuid)" in upgrade_sql
    # 0007: 감사 기록 표, CHECK 6개, 인덱스 3개, 읽기·추가만 주는 GRANT 한 줄.
    assert "CREATE TABLE audit_log (" in upgrade_sql
    assert "id BIGINT GENERATED BY DEFAULT AS IDENTITY" in upgrade_sql
    for check in (
        "action",
        "target_type",
        "actor_source",
        "actor_consistency",
        "details_object",
        "details_size",
    ):
        assert f"CONSTRAINT ck_audit_log_{check} CHECK" in upgrade_sql
    assert "CREATE INDEX ix_audit_log_occurred_at_id ON audit_log (occurred_at DESC, id DESC)" in (
        upgrade_sql
    )
    assert "GRANT SELECT, INSERT ON audit_log TO bi_app" in upgrade_sql
    command.downgrade(config, "head:base", sql=True)
    downgrade_sql = capsys.readouterr().out
    assert downgrade_sql.index("DROP TABLE audit_log") < downgrade_sql.index(
        "DROP TABLE superset_dashboards"
    )
    assert downgrade_sql.index("DROP TABLE superset_dashboards") < downgrade_sql.index(
        "DROP TABLE superset_datasets"
    )
    assert downgrade_sql.index("DROP TABLE superset_datasets") < downgrade_sql.index(
        "DROP TABLE formula_deps"
    )
    assert downgrade_sql.index("DROP TABLE formula_deps") < downgrade_sql.index(
        "DROP TABLE formulas"
    )
    assert downgrade_sql.index("DROP TABLE formulas") < downgrade_sql.index(
        "DROP CONSTRAINT fk_datasets_id_dataset_columns"
    )
    assert downgrade_sql.index("DROP CONSTRAINT fk_datasets_id_dataset_columns") < (
        downgrade_sql.index("DROP TABLE dataset_columns")
    )
    assert downgrade_sql.index("DROP TABLE dataset_columns") < downgrade_sql.index(
        "DROP TABLE datasets"
    )
    assert "alembic_version" in downgrade_sql
    assert "REVOKE USAGE, CREATE ON SCHEMA bi_data FROM bi_app" in downgrade_sql
    assert "REVOKE USAGE ON SCHEMA bi_data FROM bi_readonly" in downgrade_sql
    assert "REVOKE SELECT ON TABLES FROM bi_readonly" in downgrade_sql


def test_privilege_revision_downgrade_mirrors_upgrade():
    """0002: downgrade가 upgrade의 권한을 하나씩 회수한다(실질 구현, 빈 함수 아님)."""
    path = next(p for p in _revision_files() if "_0002_" in p.name)
    tree = _parse(path)
    assert not _is_trivial_body(_function(tree, "upgrade"))
    assert not _is_trivial_body(_function(tree, "downgrade"))
    grants = [
        n.args[0].value
        for n in ast.walk(_function(tree, "upgrade"))
        if isinstance(n, ast.Call) and _call_name(n) == "execute"
    ]
    revokes = [
        n.args[0].value
        for n in ast.walk(_function(tree, "downgrade"))
        if isinstance(n, ast.Call) and _call_name(n) == "execute"
    ]
    assert len(grants) == len(revokes) == 3
    assert all("GRANT" in g for g in grants)
    assert all("REVOKE" in r for r in revokes)


def _execute_args(path: Path, function: str) -> list[str]:
    return [
        n.args[0].value
        for n in ast.walk(_function(_parse(path), function))
        if isinstance(n, ast.Call) and _call_name(n) == "execute"
    ]


def _access_revision() -> Path:
    return next(p for p in _revision_files() if "_0003_" in p.name)


def test_access_tables_revision_has_real_downgrade_and_explicit_grants():
    """0003: upgrade가 표를 만들고 명시 GRANT를 주며, downgrade가 표를 외래키 역순으로 지운다."""
    tree = _parse(_access_revision())
    assert not _is_trivial_body(_function(tree, "upgrade"))
    assert not _is_trivial_body(_function(tree, "downgrade"))
    grants = _execute_args(_access_revision(), "upgrade")
    assert len(grants) == 3 and all(g.startswith("GRANT ") for g in grants)
    # 권한을 넓히는 문장 금지: PUBLIC·bi_readonly 부여, ALL.
    joined = " ".join(grants).upper()
    assert "PUBLIC" not in joined and "BI_READONLY" not in joined and "ALL" not in joined.split()
    assert all(g.endswith(" TO bi_app") for g in grants)
    drops = [
        (n.args[0].value, node.lineno)
        for node in ast.walk(_function(tree, "downgrade"))
        if isinstance(node, ast.Call) and _call_name(node) == "drop_table"
        for n in [node]
    ]
    assert [name for name, _ in drops] == ["team_members", "teams", "users"]


def _dataset_revision() -> Path:
    return next(p for p in _revision_files() if "_0004_" in p.name)


def _formula_revision() -> Path:
    return next(p for p in _revision_files() if "_0005_" in p.name)


def _superset_revision() -> Path:
    return next(p for p in _revision_files() if "_0006_" in p.name)


def _audit_revision() -> Path:
    return next(p for p in _revision_files() if "_0007_" in p.name)


def test_revisions_create_exactly_the_static_metadata_tables():
    """revision들이 만드는 표 이름은 정적 MetaData와 같다(alembic check는 DB 왕복 시험이 한다)."""
    from app.db_metadata import metadata

    created = [
        n.args[0].value
        for path in (
            _access_revision(),
            _dataset_revision(),
            _formula_revision(),
            _superset_revision(),
            _audit_revision(),
        )
        for n in ast.walk(_function(_parse(path), "upgrade"))
        if isinstance(n, ast.Call) and _call_name(n) == "create_table"
    ]
    assert sorted(created) == sorted(metadata.tables)


def test_dataset_revision_has_real_downgrade_explicit_grants_and_late_circular_fk():
    """0004: 순환 FK는 표 생성 뒤에 추가하고 downgrade는 FK를 먼저 끊고 역순으로 지운다."""
    tree = _parse(_dataset_revision())
    assert not _is_trivial_body(_function(tree, "upgrade"))
    assert not _is_trivial_body(_function(tree, "downgrade"))
    upgrade_calls = [
        _call_name(n) for n in ast.walk(_function(tree, "upgrade")) if isinstance(n, ast.Call)
    ]
    assert upgrade_calls.count("create_table") == 2
    assert upgrade_calls.count("create_foreign_key") == 1
    ordered = [c for c in upgrade_calls if c in {"create_table", "create_foreign_key"}]
    assert ordered == ["create_table", "create_table", "create_foreign_key"]
    grants = _execute_args(_dataset_revision(), "upgrade")
    assert len(grants) == 2 and all(g.startswith("GRANT SELECT, INSERT, UPDATE (") for g in grants)
    assert all(g.endswith(" TO bi_app") for g in grants)
    joined = " ".join(grants).upper()
    assert "PUBLIC" not in joined and "BI_READONLY" not in joined and "DELETE" not in joined
    # 불변 열은 UPDATE 권한 목록에 없다.
    assert "team_id" not in grants[0] and "created_by" not in grants[0]
    assert "dataset_id" not in grants[1] and "kind" not in grants[1].split("UPDATE")[1]
    downgrade_calls = [
        (_call_name(n), n.args[0].value if n.args and isinstance(n.args[0], ast.Constant) else None)
        for n in ast.walk(_function(tree, "downgrade"))
        if isinstance(n, ast.Call)
    ]
    assert downgrade_calls == [
        ("drop_constraint", "fk_datasets_id_dataset_columns"),
        ("drop_table", "dataset_columns"),
        ("drop_table", "datasets"),
    ]


def test_formula_revision_has_real_downgrade_and_minimal_grants():
    """0005: 열 단위 UPDATE만 주고(`column_id` 불변) formulas에 DELETE를 주지 않는다."""
    tree = _parse(_formula_revision())
    assert not _is_trivial_body(_function(tree, "upgrade"))
    assert not _is_trivial_body(_function(tree, "downgrade"))
    grants = _execute_args(_formula_revision(), "upgrade")
    assert grants == [
        "GRANT SELECT, INSERT, UPDATE (expression, ast, ast_hash) ON formulas TO bi_app",
        "GRANT SELECT, INSERT, DELETE ON formula_deps TO bi_app",
    ]
    joined = " ".join(grants).upper()
    assert "PUBLIC" not in joined and "BI_READONLY" not in joined and "ALL" not in joined.split()
    downgrade_calls = [
        (_call_name(n), n.args[0].value if n.args and isinstance(n.args[0], ast.Constant) else None)
        for n in ast.walk(_function(tree, "downgrade"))
        if isinstance(n, ast.Call)
    ]
    assert downgrade_calls == [("drop_table", "formula_deps"), ("drop_table", "formulas")]


def test_superset_revision_has_real_downgrade_and_minimal_grants():
    """0006: 열 단위 UPDATE만 주고(`dataset_id`·`id`·`embedded_uuid` 불변) DELETE를 주지 않는다."""
    tree = _parse(_superset_revision())
    assert not _is_trivial_body(_function(tree, "upgrade"))
    assert not _is_trivial_body(_function(tree, "downgrade"))
    grants = _execute_args(_superset_revision(), "upgrade")
    assert grants == [
        "GRANT SELECT, INSERT, UPDATE (superset_dataset_id, display_name, sync_status, "
        "synced_at, last_error) ON superset_datasets TO bi_app",
        "GRANT SELECT, INSERT, UPDATE (name, is_active) ON superset_dashboards TO bi_app",
    ]
    joined = " ".join(grants).upper()
    assert "PUBLIC" not in joined and "BI_READONLY" not in joined and "ALL" not in joined.split()
    assert "DELETE" not in joined and "TRUNCATE" not in joined
    downgrade_calls = [
        (_call_name(n), n.args[0].value if n.args and isinstance(n.args[0], ast.Constant) else None)
        for n in ast.walk(_function(tree, "downgrade"))
        if isinstance(n, ast.Call)
    ]
    assert downgrade_calls == [
        ("drop_table", "superset_dashboards"),
        ("drop_table", "superset_datasets"),
    ]


def _constraint_sql(table_name: str, name: str) -> str:
    """정적 MetaData가 만드는 CHECK의 SQL 식(공백 한 칸으로 정리)."""
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateTable

    from app.db_metadata import metadata

    ddl = str(CreateTable(metadata.tables[table_name]).compile(dialect=postgresql.dialect()))
    match = re.search(rf"CONSTRAINT {name} CHECK \((.*)\)(?:,|\n)", ddl)
    assert match, name
    return " ".join(match.group(1).split())


def test_audit_revision_has_real_downgrade_minimal_grant_and_no_upgrade_drop():
    """0007: 읽기·추가 GRANT 한 줄(시퀀스·열 단위·PUBLIC·bi_readonly 없음), upgrade에 DROP 없음."""
    tree = _parse(_audit_revision())
    assert not _is_trivial_body(_function(tree, "upgrade"))
    assert not _is_trivial_body(_function(tree, "downgrade"))
    grants = _execute_args(_audit_revision(), "upgrade")
    assert grants == ["GRANT SELECT, INSERT ON audit_log TO bi_app"]
    joined = " ".join(grants).upper()
    for forbidden in ("UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER", "ALL", "PUBLIC"):
        assert forbidden not in joined.replace(",", " ").split(), forbidden
    assert "BI_READONLY" not in joined and "SEQUENCE" not in joined and "(" not in joined
    assert _drop_findings_in(_function(tree, "upgrade")) == []
    downgrade_calls = [
        (_call_name(n), n.args[0].value if n.args and isinstance(n.args[0], ast.Constant) else None)
        for n in ast.walk(_function(tree, "downgrade"))
        if isinstance(n, ast.Call)
    ]
    assert downgrade_calls == [("drop_table", "audit_log")]
    # 인덱스 3개와 CHECK 6개를 만든다.
    upgrade_calls = [
        _call_name(n) for n in ast.walk(_function(tree, "upgrade")) if isinstance(n, ast.Call)
    ]
    assert upgrade_calls.count("create_table") == 1
    assert upgrade_calls.count("create_index") == 3
    assert upgrade_calls.count("CheckConstraint") == 6


def test_audit_revision_checks_match_static_metadata_and_audit_actions():
    """revision의 CHECK 문장은 정적 MetaData와 같고, 행위 목록은 `audit.actions`와 같다."""
    from app.audit.actions import ACTIONS
    from app.db_metadata import (
        AUDIT_ACTIONS,
        AUDIT_ACTOR_SOURCES,
        AUDIT_DETAILS_MAX_BYTES,
        AUDIT_TARGET_TYPES,
    )

    assert tuple(ACTIONS) == AUDIT_ACTIONS and len(AUDIT_ACTIONS) == 15
    assert {spec.target_type for spec in ACTIONS.values()} <= set(AUDIT_TARGET_TYPES)
    assert set(AUDIT_TARGET_TYPES) == {spec.target_type for spec in ACTIONS.values()}
    assert AUDIT_ACTOR_SOURCES == ("user", "cli")
    tree = _parse(_audit_revision())
    in_revision: dict[str, str] = {}
    for node in ast.walk(_function(tree, "upgrade")):
        if isinstance(node, ast.Call) and _call_name(node) == "CheckConstraint":
            sql = ast.literal_eval(node.args[0]) if isinstance(node.args[0], ast.Constant) else None
            if sql is None:  # 문자열 이어 붙이기(암묵 연결은 Constant 하나로 합쳐진다)
                raise AssertionError("CHECK는 보간 없는 문자열 상수여야 한다")
            name_call = next(k.value for k in node.keywords if k.arg == "name")
            in_revision[name_call.args[0].value] = " ".join(sql.split())
    assert set(in_revision) == {
        f"ck_audit_log_{n}"
        for n in (
            "action",
            "target_type",
            "actor_source",
            "actor_consistency",
            "details_object",
            "details_size",
        )
    }
    for full_name, sql in in_revision.items():
        assert sql == _constraint_sql("audit_log", full_name), full_name
    assert f"<= {AUDIT_DETAILS_MAX_BYTES}" in in_revision["ck_audit_log_details_size"]


def test_audit_indexes_match_between_metadata_and_revision():
    from app.db_metadata import audit_log

    names = {i.name for i in audit_log.indexes}
    assert names == {
        "ix_audit_log_occurred_at_id",
        "ix_audit_log_actor_user_id_occurred_at_id",
        "ix_audit_log_target_type_target_id_occurred_at_id",
    }
    source = _audit_revision().read_text(encoding="utf-8")
    for name in names:
        assert f'"{name}"' in source
    # 이름 길이는 PostgreSQL 식별자 한도(63바이트) 안이다.
    assert all(len(n.encode()) <= 63 for n in names)


def test_static_metadata_constraint_names_follow_convention():
    """제약 이름 규칙(NAMING_CONVENTION): CHECK는 이름 있는 제약, FK·PK·UNIQUE·인덱스 이름 확정."""
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateTable

    from app.db_metadata import metadata

    ddl = {
        name: str(CreateTable(table).compile(dialect=postgresql.dialect()))
        for name, table in metadata.tables.items()
    }
    assert "CONSTRAINT pk_users PRIMARY KEY (id)" in ddl["users"]
    assert "CONSTRAINT uq_users_login_id UNIQUE (login_id)" in ddl["users"]
    assert "CONSTRAINT uq_teams_code UNIQUE (code)" in ddl["teams"]
    assert "CONSTRAINT uq_teams_name UNIQUE (name)" in ddl["teams"]
    assert "CONSTRAINT ck_teams_code_format CHECK" in ddl["teams"]
    assert "CONSTRAINT pk_team_members PRIMARY KEY (team_id, user_id)" in ddl["team_members"]
    assert "CONSTRAINT ck_team_members_role CHECK" in ddl["team_members"]
    assert "CONSTRAINT fk_team_members_team_id_teams FOREIGN KEY" in ddl["team_members"]
    assert "CONSTRAINT fk_team_members_user_id_users FOREIGN KEY" in ddl["team_members"]
    index_names = {i.name for t in metadata.tables.values() for i in t.indexes}
    assert index_names == {
        "ix_team_members_user_id",
        "ix_audit_log_occurred_at_id",
        "ix_audit_log_actor_user_id_occurred_at_id",
        "ix_audit_log_target_type_target_id_occurred_at_id",
    }
    # 0004 표: 열거는 text + 이름 있는 CHECK, 이름 유일 범위는 팀(데이터셋 이름)·데이터셋(열 이름).
    assert "CONSTRAINT uq_datasets_team_id_name UNIQUE (team_id, name)" in ddl["datasets"]
    assert "CONSTRAINT ck_datasets_date_unit CHECK" in ddl["datasets"]
    assert "CONSTRAINT ck_datasets_status CHECK" in ddl["datasets"]
    assert "CONSTRAINT fk_datasets_team_id_teams FOREIGN KEY" in ddl["datasets"]
    assert "CONSTRAINT fk_datasets_created_by_users FOREIGN KEY" in ddl["datasets"]
    assert "fk_datasets_id_dataset_columns" not in ddl["datasets"]  # 순환 FK는 뒤에 추가한다
    cols = ddl["dataset_columns"]
    assert "CONSTRAINT uq_dataset_columns_dataset_id_id UNIQUE (dataset_id, id)" in cols
    assert (
        "CONSTRAINT uq_dataset_columns_dataset_id_display_name UNIQUE (dataset_id, display_name)"
        in cols
    )
    for name in ("type", "kind", "formula_shape"):
        assert f"CONSTRAINT ck_dataset_columns_{name} CHECK" in cols
    assert "rules JSONB" in cols
    # 0005 표: 열 하나에 수식 하나(기본키 = 외래키), 의존은 자기 자신을 가리킬 수 없다.
    formulas_ddl = ddl["formulas"]
    assert "CONSTRAINT pk_formulas PRIMARY KEY (column_id)" in formulas_ddl
    assert "CONSTRAINT fk_formulas_column_id_dataset_columns FOREIGN KEY" in formulas_ddl
    assert "ast JSONB NOT NULL" in formulas_ddl
    deps_ddl = ddl["formula_deps"]
    assert "CONSTRAINT pk_formula_deps PRIMARY KEY (column_id, depends_on_column_id)" in deps_ddl
    assert "CONSTRAINT ck_formula_deps_not_self CHECK" in deps_ddl
    assert "CONSTRAINT fk_formula_deps_column_id_dataset_columns FOREIGN KEY" in deps_ddl
    assert "CONSTRAINT fk_formula_deps_depends_on_column_id_dataset_columns FOREIGN KEY" in deps_ddl
    # 0006 표: 데이터셋마다 동기 상태 한 줄(기본키 = 외래키), 임베드 uuid는 유일·소문자 정규형.
    sync_ddl = ddl["superset_datasets"]
    assert "CONSTRAINT pk_superset_datasets PRIMARY KEY (dataset_id)" in sync_ddl
    assert "CONSTRAINT fk_superset_datasets_dataset_id_datasets FOREIGN KEY" in sync_ddl
    assert "CONSTRAINT ck_superset_datasets_sync_status CHECK" in sync_ddl
    assert "sync_status TEXT DEFAULT 'pending' NOT NULL" in sync_ddl
    dash_ddl = ddl["superset_dashboards"]
    assert "CONSTRAINT pk_superset_dashboards PRIMARY KEY (id)" in dash_ddl
    assert "CONSTRAINT uq_superset_dashboards_embedded_uuid UNIQUE (embedded_uuid)" in dash_ddl
    assert "CONSTRAINT ck_superset_dashboards_embedded_uuid_format CHECK" in dash_ddl
    assert "embedded_uuid UUID NOT NULL" in dash_ddl
    # 0007 표: 감사 기록은 추가만 하는 표(bigint identity), 행위자는 users 외래키, 대상은 FK 없음.
    audit_ddl = ddl["audit_log"]
    assert "id BIGINT GENERATED BY DEFAULT AS IDENTITY" in audit_ddl
    assert "CONSTRAINT pk_audit_log PRIMARY KEY (id)" in audit_ddl
    assert "CONSTRAINT fk_audit_log_actor_user_id_users FOREIGN KEY(actor_user_id)" in audit_ddl
    assert audit_ddl.count("FOREIGN KEY") == 1  # target_id는 여러 표를 가리키므로 외래키 없음
    assert "details JSONB DEFAULT '{}' NOT NULL" in audit_ddl
    assert "target_id BIGINT NOT NULL" in audit_ddl


def test_team_code_check_matches_python_pattern():
    """DB의 CHECK 식과 서비스의 형식 검사가 같은 정규식이다."""
    from app.db_metadata import TEAM_CODE_PATTERN, teams

    checks = [c for c in teams.constraints if getattr(c, "name", None) == "ck_teams_code_format"]
    assert len(checks) == 1
    assert TEAM_CODE_PATTERN in str(checks[0].sqltext)
