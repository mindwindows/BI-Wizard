"""마이그레이션 규칙(D3, D5) 정적 점검과 오프라인 SQL 생성 점검. DB 없이 실행한다."""

import ast
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND = Path(__file__).resolve().parent.parent
VERSIONS = BACKEND / "migrations" / "versions"
EXECUTORS = {"execute", "exec_driver_sql"}


def _alembic_config() -> Config:
    return Config(str(BACKEND / "alembic.ini"))


def test_single_head_and_baseline():
    script = ScriptDirectory.from_config(_alembic_config())
    assert script.get_heads() == ["0001"]


def test_every_revision_defines_upgrade_and_downgrade():
    for path in VERSIONS.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
        assert {"upgrade", "downgrade"} <= names, path.name


def test_migration_sql_has_no_interpolation():
    """D3: execute 계열에는 보간 없는 문자열 상수만 넘길 수 있다."""
    for path in VERSIONS.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in EXECUTORS:
                assert node.args, path.name
                first = node.args[0]
                assert isinstance(first, ast.Constant), f"{path.name}: SQL 보간 금지"
                assert isinstance(first.value, str), path.name


def test_offline_upgrade_and_downgrade_generate_sql(capsys):
    config = _alembic_config()
    command.upgrade(config, "head", sql=True)
    assert "alembic_version" in capsys.readouterr().out
    command.downgrade(config, "head:base", sql=True)
    assert "alembic_version" in capsys.readouterr().out
