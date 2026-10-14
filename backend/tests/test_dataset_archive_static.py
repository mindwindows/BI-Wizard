"""보관 상태 판정이 모든 쓰기 경로를 지나가는지 소스로 점검한다(DB 없음, 04 §5, 05 §2-2).

`lock_dataset`(`FOR NO KEY UPDATE`)와 `lock_dataset_shared`(`FOR SHARE`)를 부르는 곳은
허용 목록뿐이다.
새 쓰기 경로가 `datasets` 행을 잠그면 이 시험이 깨져서 보관 판정(`DATASET_ARCHIVED`)과 시험을
같이 넣도록 알려 준다. 판정 자리가 "잠금 직후, 버전 비교보다 앞"인지도 소스 순서로 확인한다.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent.parent / "app"

# 잠금 함수 -> 부를 수 있는 함수(app/ 기준 점 경로). 보관 판정이 필요한 곳은 주석에 적었다.
LOCK_CALLERS = {
    "lock_dataset": {
        # 정의 변경 진입점: bump=True면 보관 판정(B4 B5 B6 D4 D5), bump=False(뷰 재생성)는 판정 없음
        "dataset.definition.apply_definition_change",
        # B7·B8: 보관·복구는 status만 바꾸므로 보관 판정이 아니라 같은 상태 판정을 한다
        "dataset.service._lock_for_status",
    },
    "lock_dataset_shared": {
        # 행 쓰기 C2 C3 C4의 공통 첫 단계: 보관 판정
        "dataset.service.lock_row_context",
    },
}
# 정의 변경 진입점을 부르는 곳: 새 호출자가 bump=True로 불리면 이 목록과 시험에 추가해야 한다.
ENTRY_POINT_CALLERS_BUMPING = {
    "dataset.service.update_dataset",  # B4
    "dataset.service.add_column",  # B5
    "dataset.service.update_column",  # B6
    "formula.service.create_formula_column",  # D4
    "formula.service.update_formula",  # D5
}
ENTRY_POINT_CALLERS_NOT_BUMPING = {"formula.reconcile.rebuild"}  # 시작 대조·D10: 정의가 안 바뀜
ROW_CONTEXT_CALLERS = {  # lock_row_context 호출자 = 행 쓰기 C2 C3 C4
    "entry.service.create_row",
    "entry.service.update_row",
    "entry.service.paste_rows",
}


def module_name(path: Path) -> str:
    return ".".join(path.relative_to(APP).with_suffix("").parts)


def functions() -> dict[str, ast.FunctionDef]:
    found = {}
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                found[f"{module_name(path)}.{node.name}"] = node
    return found


def callee_name(call: ast.Call) -> str:
    func = call.func
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")


def callers_of(name: str) -> set[str]:
    return {
        qualified
        for qualified, node in functions().items()
        if any(isinstance(n, ast.Call) and callee_name(n) == name for n in ast.walk(node))
        and not qualified.endswith(f".{name}")
    }


@pytest.mark.parametrize("lock", LOCK_CALLERS)
def test_datasets_row_lock_functions_are_called_only_from_the_allowed_places(lock):
    assert callers_of(lock) == LOCK_CALLERS[lock], (
        f"{lock}의 호출자가 바뀌었다. 새 쓰기 경로라면 보관 판정(DATASET_ARCHIVED)과 시험을 같이 "
        "넣고 이 허용 목록을 고치세요."
    )


def test_row_writes_go_through_lock_row_context_and_nothing_else_locks_shared():
    assert callers_of("lock_row_context") == ROW_CONTEXT_CALLERS


def test_the_definition_entry_point_has_only_known_callers_and_the_bump_flag_is_explicit():
    bumping, not_bumping = set(), set()
    for qualified, node in functions().items():
        for call in (n for n in ast.walk(node) if isinstance(n, ast.Call)):
            if callee_name(call) != "apply_definition_change":
                continue
            keywords = {k.arg: k.value for k in call.keywords}
            flag = keywords.get("bump")
            if isinstance(flag, ast.Constant) and flag.value is False:
                not_bumping.add(qualified)
            else:  # 기본값(True)이거나 식이다: 보관 판정이 적용되는 쪽으로 센다
                bumping.add(qualified)
    assert bumping == ENTRY_POINT_CALLERS_BUMPING
    assert not_bumping == ENTRY_POINT_CALLERS_NOT_BUMPING


def _line_of(function: ast.FunctionDef, predicate) -> int:
    lines = [n.lineno for n in ast.walk(function) if predicate(n)]
    assert lines, "찾는 문장이 없다"
    return min(lines)


def is_archived_check(node: ast.AST) -> bool:
    """`… == "archived"` 비교를 포함하는 if."""
    return isinstance(node, ast.If) and any(
        isinstance(n, ast.Constant) and n.value == "archived" for n in ast.walk(node.test)
    )


def raises_dataset_archived(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and callee_name(node) == "dataset_archived"


def reads_version(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Subscript)
        and isinstance(node.slice, ast.Constant)
        and node.slice.value == "def_version"
    )


@pytest.mark.parametrize(
    "qualified", ["dataset.definition.apply_definition_change", "dataset.service.lock_row_context"]
)
def test_archived_check_comes_right_after_the_lock_and_before_any_version_comparison(qualified):
    function = functions()[qualified]
    lock = _line_of(
        function,
        lambda n: (
            isinstance(n, ast.Call) and callee_name(n) in {"lock_dataset", "lock_dataset_shared"}
        ),
    )
    check = _line_of(function, is_archived_check)
    raised = _line_of(function, raises_dataset_archived)
    version = _line_of(function, reads_version)
    assert lock < check <= raised < version, (lock, check, raised, version)


def test_archive_and_restore_never_use_the_definition_entry_point_hooks_or_ddl():
    """B7·B8은 status 한 칸과 감사만 쓴다: 진입점·훅·ddl·동기 요청을 부르지 않는다."""
    forbidden = {
        "apply_definition_change",
        "run",  # hooks.run
        "create_view",
        "drop_view",
        "run_ddl",
        "add_raw_column",
        "create_dataset_table",
        "request_dataset_sync",
        "request_team_sync",
        "structure_hash",
    }
    fns = functions()
    for qualified in (
        "dataset.service.archive_dataset",
        "dataset.service.restore_dataset",
        "dataset.service._lock_for_status",
        "dataset.service._status_transaction",
    ):
        called = {callee_name(n) for n in ast.walk(fns[qualified]) if isinstance(n, ast.Call)}
        assert not (called & forbidden), (qualified, called & forbidden)
    router = ast.parse((APP / "dataset" / "router.py").read_text(encoding="utf-8"))
    for node in router.body:
        if isinstance(node, ast.FunctionDef) and node.name in {
            "archive_dataset",
            "restore_dataset",
        }:
            args = {a.arg for a in node.args.args}
            assert not (args & {"sync", "hooks", "background"}), node.name  # 동기·훅 의존성 없음
