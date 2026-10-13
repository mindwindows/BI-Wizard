"""수식 보기(`text`): AST -> **현재 열 이름으로 풀어 쓴** 읽기 전용 글자(07 §9, 03b 1-6).

- 원문(`formulas.expression`)이 아니라 AST에서 만들므로 열 이름이 바뀌어도 항상 최신이다.
- 정규 형태: 함수 이름 대문자, 연산자 앞뒤 공백 한 칸, 인수 구분 `, `, 필요한 괄호만 쓴다.
- 이 글자를 다시 읽으면(열 이름이 같으면) **같은 AST**가 나온다(왕복 시험이 확인한다). `SUMTAG`는
  펼치지 않고 `SUMTAG("태그")` 그대로 보여 준다(펼친 열 목록은 `api.sumtag_columns`).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from app.formula.columns import ColumnInfo
from app.formula.nodes import Bool, Call, Col, Node, Num, Text
from app.formula.registry import FunctionRegistry

_FORBIDDEN_IN_NAME = frozenset('[]"')


def render_text(
    node: Node,
    columns: Sequence[ColumnInfo],
    registry: FunctionRegistry | None = None,
) -> str:
    """AST를 읽을 수 있는 수식 글자로 쓴다. 알 수 없는 열 번호면 `KeyError`."""
    if registry is None:
        from app.formula.functions import get_default_registry

        registry = get_default_registry()
    names = {c.id: c.name for c in columns}
    return _render(node, names.__getitem__, registry)


def _quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _level(node: Node, registry: FunctionRegistry) -> int:
    """연산자 호출의 우선순위. 연산자가 아니면(값·함수 호출) 가장 높은 값."""
    if isinstance(node, Call):
        spec = registry.get(node.name)
        if spec is not None and spec.kind == "operator" and spec.level is not None:
            return spec.level
    return 99


def _render(node: Node, name_of: Callable[[int], str], registry: FunctionRegistry) -> str:
    if isinstance(node, Num):
        return format(node.value, "f")
    if isinstance(node, Text):
        return _quote(node.value)
    if isinstance(node, Bool):
        return "TRUE" if node.value else "FALSE"
    if isinstance(node, Col):
        name = name_of(node.column_id)
        if _FORBIDDEN_IN_NAME & set(name) or any(ord(ch) < 32 for ch in name):
            raise ValueError('열 이름에 [ ] " 나 제어 문자가 있어 수식으로 쓸 수 없다.')
        return f"[{name}]"
    if not isinstance(node, Call):
        raise TypeError(f"수식 보기로 쓸 수 없는 노드: {type(node).__name__}")
    spec = registry.get(node.name)
    if (
        spec is not None
        and spec.kind == "operator"
        and spec.syntax == "infix"
        and len(node.args) == 2
    ):
        level = spec.level or 0
        left, right = node.args
        left_text = _render(left, name_of, registry)
        right_text = _render(right, name_of, registry)
        if _level(left, registry) < level:
            left_text = f"({left_text})"
        if _level(right, registry) <= level:
            right_text = f"({right_text})"
        return f"{left_text} {spec.symbol} {right_text}"
    if (
        spec is not None
        and spec.kind == "operator"
        and spec.syntax == "prefix"
        and len(node.args) == 1
    ):
        operand = node.args[0]
        text = _render(operand, name_of, registry)
        if _level(operand, registry) < (spec.level or 0):
            text = f"({text})"
        return f"{spec.symbol}{text}"
    arguments = ", ".join(_render(a, name_of, registry) for a in node.args)
    return f"{node.name}({arguments})"
