"""기록 대상 표를 쓰는 service 함수가 감사 표에 있는지 점검한다(04 §5-1 시험 단정, 소스 정적 분석).

기록 대상 표(`users` `teams` `team_members` `datasets` `dataset_columns`
`superset_dashboards`)를 쓰는 함수는 다음 중 하나여야 한다.
- 04 §5-1 표의 15개 행위를 기록하는 service 함수(함수 안에 그 행위 이름이 정확히 한 번 있다)
- 정의 변경 진입점(`apply_definition_change`, B4·B5·B6·D4·D5가 한 곳에서 기록한다)
- 정의 변경 진입점 안에서만 불리는 helper(진입점의 기록에 포함된다)
- 제외 목록: 시험용 사용자 시드, 버전을 올리지 않는 뷰 재생성(`bump=False`)
새 쓰기 경로가 생기면 이 시험이 실패해 행위 표에 추가하도록 알려 준다(감사 없는 변경 방지).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from app.audit.actions import ACTIONS

APP = Path(__file__).resolve().parent.parent / "app"
RECORDED_TABLES = {
    "users",
    "teams",
    "team_members",
    "datasets",
    "dataset_columns",
    "superset_dashboards",
}
WRITE_FUNCTIONS = {"insert", "update", "delete", "pg_insert", "sqlite_insert"}

# 04 §5-1 표: 행위 -> service 함수 (모듈 경로는 app/ 기준)
RECORDERS = {
    "dataset.create": "dataset.service.create_dataset",
    "dataset.update": "dataset.service.update_dataset",
    "column.add": "dataset.service.add_column",
    "column.update": "dataset.service.update_column",
    "formula_column.add": "formula.service.create_formula_column",
    "formula_column.update": "formula.service.update_formula",
    "team.create": "access.service.create_team",
    "team.update": "access.service.update_team",
    "member.set": "access.service.set_member",
    "member.remove": "access.service.remove_member",
    "user.create": "access.service.create_user",
    "user.update": "access.service.update_user",
    "user.bootstrap_admin": "access.service.create_first_admin",
    "dashboard.create": "superset.service.create_dashboard",
    "dashboard.update": "superset.service.update_dashboard",
}
ENTRY_POINT = "dataset.definition.apply_definition_change"
# 정의 변경 진입점 안에서만 불리는 helper: 진입점의 기록에 포함된다(따로 기록하지 않는다)
ENTRY_HELPERS = {
    "dataset.service.add_formula_column",
    "dataset.service.set_formula_result_type",
    "dataset.service.clear_column_tag",
}
# 제외: 시험용 사용자 시드(개발·시험 전용), 시작 시 뷰 재생성·재시도(정의 불변)
EXCLUDED = {
    "access.service.seed_stub_data",
    "formula.reconcile.rebuild",
    "formula.reconcile.retry",
    "formula.reconcile.reconcile_one",
    "formula.reconcile.reconcile_all",
}


@dataclass
class Fn:
    name: str  # app 기준 점 경로
    node: ast.FunctionDef
    calls: set[str] = field(default_factory=set)  # 해석된 호출 대상(점 경로)


def module_name(path: Path) -> str:
    return ".".join(path.relative_to(APP).with_suffix("").parts)


def parse_modules() -> dict[str, ast.Module]:
    return {
        module_name(p): ast.parse(p.read_text(encoding="utf-8"))
        for p in sorted(APP.rglob("*.py"))
        if "__pycache__" not in p.parts
    }


def import_aliases(module: str, tree: ast.Module) -> dict[str, str]:
    """이름 -> 점 경로(`app.` 접두 제거). `from app.x import repo`/`... service as y`/`import`."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app"):
            base = node.module.removeprefix("app").lstrip(".")
            for item in node.names:
                aliases[item.asname or item.name] = f"{base}.{item.name}".lstrip(".")
    return aliases


def collect() -> tuple[dict[str, Fn], set[str]]:
    """모든 함수(중첩 포함, 바깥 함수에 합친다)와 기록 대상 표를 직접 쓰는 repo 함수 집합."""
    modules = parse_modules()
    functions: dict[str, Fn] = {}
    repo_writers: set[str] = set()
    for module, tree in modules.items():
        aliases = import_aliases(module, tree)
        package = module.rsplit(".", 1)[0] if "." in module else module
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            fn = Fn(f"{module}.{node.name}", node)
            functions[fn.name] = fn
            writes = False
            for inner in ast.walk(node):
                if not isinstance(inner, ast.Call):
                    continue
                func = inner.func
                # 표를 쓰는 SQLAlchemy 구문: insert(users) / update(users) / users.insert()
                if (
                    isinstance(func, ast.Name)
                    and func.id in WRITE_FUNCTIONS
                    and inner.args
                    and isinstance(inner.args[0], ast.Name)
                    and inner.args[0].id in RECORDED_TABLES
                ):
                    writes = True
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr in WRITE_FUNCTIONS
                    and isinstance(func.value, ast.Name)
                    and func.value.id in RECORDED_TABLES
                ):
                    writes = True
                # 호출 대상 해석
                if isinstance(func, ast.Name):
                    target = aliases.get(func.id, f"{module}.{func.id}")
                    fn.calls.add(target)
                elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                    base = aliases.get(func.value.id)
                    if base is not None:
                        fn.calls.add(f"{base}.{func.attr}")
            if module.endswith(".repo") and writes:
                repo_writers.add(fn.name)
        _ = package
    return functions, repo_writers


def writers() -> set[str]:
    """기록 대상 표를 쓰는 함수: repo 쓰기 함수를 부르거나, 그런 함수를 부르는 함수(전이).

    router·cli는 service를 부르는 쪽이라 뺀다(그쪽이 repo를 직접 부르는지는 따로 점검한다).
    """
    functions, repo_writers = collect()
    found: set[str] = set()
    changed = True
    while changed:
        changed = False
        for name, fn in functions.items():
            if name.endswith(".repo") or ".repo." in name or name in found:
                continue
            module = name.rsplit(".", 1)[0]
            if module.endswith((".router", ".schemas")) or module == "cli":
                continue
            if fn.calls & (repo_writers | found):
                found.add(name)
                changed = True
    return found


def test_every_recorded_table_writer_is_in_the_audit_table_or_explicitly_excluded():
    allowed = set(RECORDERS.values()) | {ENTRY_POINT} | ENTRY_HELPERS | EXCLUDED
    # formula/hook.py의 함수는 정의 변경 진입점 안에서 불리는 훅이다(audit을 안 쓰는지 따로 본다)
    unexpected = {name for name in writers() - allowed if not name.startswith("formula.hook.")}
    assert not unexpected, (
        f"기록 대상 표를 쓰는데 감사 표(04 §5-1)에 없는 함수: {sorted(unexpected)}. "
        "행위 표에 추가하거나 제외 목록에 사유와 함께 넣으세요."
    )


def test_the_allowed_functions_exist_and_write_recorded_tables():
    functions, _ = collect()
    found = writers()
    for name in [*RECORDERS.values(), ENTRY_POINT, *ENTRY_HELPERS, *EXCLUDED]:
        assert name in functions, f"{name}가 없다(이름이 바뀌었으면 이 표를 고치세요)"
    for name in [*RECORDERS.values(), ENTRY_POINT, *ENTRY_HELPERS]:
        assert name in found, f"{name}는 기록 대상 표를 쓰지 않는다(표가 낡았다)"


def string_constants(node: ast.AST) -> list[str]:
    return [
        n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]


@pytest.mark.parametrize(("action", "dotted"), RECORDERS.items())
def test_each_recorder_names_its_action_exactly_once(action, dotted):
    functions, _ = collect()
    node = functions[dotted].node
    assert string_constants(node).count(action) == 1, dotted
    # 직접 부르거나(AuditSpec 포함) 진입점에 서술을 넘긴다
    called = {
        n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
        for n in ast.walk(node)
        if isinstance(n, ast.Call)
    }
    assert called & {"record", "AuditSpec"}, dotted


def test_every_action_appears_in_exactly_one_place_in_app_code():
    """행위 이름 리터럴이 정의 표(actions.py)·CHECK(db_metadata) 밖에서 정확히 한 번씩 나온다."""
    modules = parse_modules()
    counts = dict.fromkeys(ACTIONS, 0)
    for module, tree in modules.items():
        if module in {"audit.actions", "db_metadata"}:
            continue
        for value in string_constants(tree):
            if value in counts:
                counts[value] += 1
    assert counts == dict.fromkeys(ACTIONS, 1), counts


def test_only_the_service_layer_records_and_only_via_the_audit_module():
    """repo·hook·formula 내부 helper·router는 `audit.record`를 부르지 않는다(호출당 한 번 규칙)."""
    modules = parse_modules()
    callers = set()
    for module, tree in modules.items():
        if module.startswith("audit."):
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                if n.func.attr == "record" and getattr(n.func.value, "id", "") == "audit":
                    callers.add(module)
    assert callers == {
        "access.service",
        "dataset.service",
        "dataset.definition",
        "superset.service",
    }, callers
    # formula·entry는 audit을 직접 부르지 않는다(04 §2-1). 진입점에 서술(AuditSpec)만 넘긴다.
    for module in modules:
        if module.startswith(("formula.", "entry.")):
            source = (APP / (module.replace(".", "/") + ".py")).read_text(encoding="utf-8")
            assert "audit.record" not in source and "import audit" not in source, module


def test_routers_and_cli_never_call_repo_functions_that_write_recorded_tables():
    functions, repo_writers = collect()
    for name, fn in functions.items():
        module = name.rsplit(".", 1)[0]
        if module.endswith(".router") or module == "cli":
            assert not (fn.calls & repo_writers), f"{name}: service를 거치지 않고 표를 쓴다"


def test_reconcile_never_bumps_the_version_and_hooks_never_record():
    """시작 시 재생성·재시도는 정의 불변이라 기록 대상이 아니다(bump=False). 훅은 audit을 모른다."""
    reconcile = (APP / "formula" / "reconcile.py").read_text(encoding="utf-8")
    tree = ast.parse(reconcile)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == (
            "apply_definition_change"
        ):
            keywords = {k.arg: k.value for k in node.keywords}
            assert (
                isinstance(keywords.get("bump"), ast.Constant) and keywords["bump"].value is False
            )
    hook = (APP / "formula" / "hook.py").read_text(encoding="utf-8")
    assert "audit" not in hook


def test_definition_entry_refuses_version_bump_without_an_audit_spec():
    """감사 서술 없이 정의 버전을 올리는 경로가 생기면 거부한다(fail-closed)."""
    from sqlalchemy.orm import Session

    from app.audit import AuditRecordError
    from app.core.ports import DefinitionHooks
    from app.dataset.definition import apply_definition_change

    with pytest.raises(AuditRecordError):
        apply_definition_change(
            Session(),  # 사용하기 전에 거부하므로 연결이 필요 없다
            DefinitionHooks(),
            1,
            expected_version=1,
            change=lambda locked: (True, {}),
        )
