"""마이그레이션 규칙(D2, D3, D5) 정적 점검과 오프라인 SQL 생성 점검. DB 없이 실행한다."""

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

# D2 안전장치: DROP이 들어 있는 revision은 사용자 확인 기록이 있어야 한다.
# 확인을 받았다면 {"revision 파일 이름": "DROP 확인: 사용자 승인 (날짜, 근거)"} 형태로
# 여기에 기록한다.
DROP_APPROVED: dict[str, str] = {}

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


def test_single_head_and_baseline():
    script = ScriptDirectory.from_config(_alembic_config())
    assert script.get_heads() == ["0001"]


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


def test_drop_requires_recorded_user_approval():
    """D2: DROP(op.drop_*, SQL DROP)이 있으면 사용자 확인 기록(DROP_APPROVED)이 있어야 한다."""
    for path in _revision_files():
        findings = _drop_findings(_parse(path))
        if findings:
            approval = DROP_APPROVED.get(path.name, "")
            assert "사용자 승인" in approval, (
                f"{path.name}: DROP 발견({'; '.join(findings)}). 사용자 확인 기록이 필요하다."
            )


def test_drop_detector_flags_drop_calls_and_sql():
    tree = ast.parse('op.drop_table("t")\nop.execute("DROP VIEW v")\nop.execute("SELECT 1")\n')
    assert len(_drop_findings(tree)) == 2


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
    config = _alembic_config()
    command.upgrade(config, "head", sql=True)
    assert "alembic_version" in capsys.readouterr().out
    command.downgrade(config, "head:base", sql=True)
    assert "alembic_version" in capsys.readouterr().out
