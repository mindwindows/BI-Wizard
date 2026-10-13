"""수식 AST(07 §1). 열은 **열 번호**(`dataset_columns.id`)로 참조하므로 열 이름이 바뀌어도 깨지지
않는다.

- 노드는 불변이다. `start`·`end`(원문 위치)와 `depth`는 비교·해시·저장에 들어가지 않는다
  (그래서 "수식 보기 글자를 다시 읽어도 같은 AST"를 `==`로 확인할 수 있다).
- 연산자도 `Call`이다(`+`, `-`, `*`, `/`, `=`, `<>`, `<`, `<=`, `>`, `>=`, `&`, 부호 `neg`).
  함수 이름은 대문자로 정규화한다. 사용자가 읽는 글자는 `textview.render_text`가 만든다.
- 저장 형식(`formulas.ast` jsonb)은 `ast_to_json`/`ast_from_json`이고, `ast_hash`는 그 정규 JSON의
  sha256이다. 숫자는 쓴 모양 그대로(`1.50`) 십진 문자열로 저장한다.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from app.formula.errors import FormulaError, make_issue

NEG_NAME = "neg"  # 단항 마이너스 연산자의 이름
# 수식 한 개의 AST 깊이 상한. SQLAlchemy 컴파일러의 재귀 한도(함수 한 겹이 약 10프레임)에
# 여유를 두고 정했다.
MAX_AST_DEPTH = 40
MAX_EXPANDED_DEPTH = 40  # 참조한 계산 열을 펼친 뒤의 깊이(analyze가 확인)


@dataclass(frozen=True, slots=True)
class Node:
    start: int = field(default=-1, compare=False, kw_only=True, repr=False)
    end: int = field(default=-1, compare=False, kw_only=True, repr=False)
    depth: int = field(default=1, compare=False, kw_only=True, repr=False)


@dataclass(frozen=True, slots=True)
class Num(Node):
    value: Decimal


@dataclass(frozen=True, slots=True)
class Text(Node):
    value: str  # NFC 정규화된 글자(따옴표 안의 `""`는 이미 `"` 하나로 풀렸다)


@dataclass(frozen=True, slots=True)
class Bool(Node):
    value: bool


@dataclass(frozen=True, slots=True)
class Col(Node):
    column_id: int


@dataclass(frozen=True, slots=True)
class Call(Node):
    name: str
    args: tuple[Node, ...]


@dataclass(frozen=True, slots=True)
class ColName(Node):
    """이름 해석 전의 열 참조(파서 출력에만 있다). 저장되는 AST에는 없다."""

    name: str


@dataclass(frozen=True, slots=True)
class Bad(Node):
    """오류 복구용 자리 표시(이름 해석 실패 등). 저장되는 AST에는 없다."""


def call(name: str, args: tuple[Node, ...], *, start: int, end: int) -> Call:
    """깊이를 계산해 `Call`을 만든다. 깊이 상한을 넘으면 `FormulaError`."""
    depth = 1 + max((a.depth for a in args), default=0)
    if depth > MAX_AST_DEPTH:
        raise FormulaError(make_issue("TOO_DEEP", start, end, max=MAX_AST_DEPTH))
    return Call(name=name, args=args, start=start, end=end, depth=depth)


def strip_positions(node: Node) -> Node:
    """원문 위치(`start`·`end`)를 지운 복사본. 다른 수식의 AST를 펼칠 때 위치가 섞이지 않게 한다."""
    if isinstance(node, Call):
        args = tuple(strip_positions(a) for a in node.args)
        return Call(name=node.name, args=args, depth=node.depth)
    if isinstance(node, Num):
        return Num(value=node.value)
    if isinstance(node, Text):
        return Text(value=node.value)
    if isinstance(node, Bool):
        return Bool(value=node.value)
    if isinstance(node, Col):
        return Col(column_id=node.column_id)
    return node


def children(node: Node) -> tuple[Node, ...]:
    return node.args if isinstance(node, Call) else ()


def walk(node: Node):
    """모든 노드를 깊이 우선으로 낸다(반복문이라 재귀 한도와 무관)."""
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(children(current)))


def column_ids(node: Node) -> list[int]:
    """AST가 직접 참조하는 열 번호(처음 나온 순서, 중복 제거)."""
    seen: dict[int, None] = {}
    for item in walk(node):
        if isinstance(item, Col):
            seen.setdefault(item.column_id, None)
    return list(seen)


# --- 저장 형식 ----


def ast_to_json(node: Node) -> dict[str, Any]:
    if isinstance(node, Num):
        return {"t": "num", "v": format(node.value, "f")}
    if isinstance(node, Text):
        return {"t": "text", "v": node.value}
    if isinstance(node, Bool):
        return {"t": "bool", "v": node.value}
    if isinstance(node, Col):
        return {"t": "col", "id": node.column_id}
    if isinstance(node, Call):
        return {"t": "call", "n": node.name, "a": [ast_to_json(a) for a in node.args]}
    raise TypeError(f"저장할 수 없는 노드: {type(node).__name__}")


def ast_from_json(data: Any, *, _depth: int = 1) -> Node:
    """저장된 JSON에서 AST를 복원한다. 모양이 틀리면 `ValueError`."""
    if _depth > MAX_AST_DEPTH:
        raise ValueError("AST가 너무 깊다.")
    if not isinstance(data, dict):
        raise ValueError("AST 노드는 객체여야 한다.")
    kind = data.get("t")
    if kind == "num":
        value = data.get("v")
        if not isinstance(value, str):
            raise ValueError("숫자 노드의 값은 문자열이어야 한다.")
        try:
            number = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("숫자 노드의 값이 올바르지 않다.") from exc
        if not number.is_finite():
            raise ValueError("유한한 숫자만 쓸 수 있다.")
        return Num(value=number)
    if kind == "text":
        if not isinstance(data.get("v"), str):
            raise ValueError("글자 노드의 값은 문자열이어야 한다.")
        return Text(value=data["v"])
    if kind == "bool":
        if not isinstance(data.get("v"), bool):
            raise ValueError("참거짓 노드의 값은 true/false여야 한다.")
        return Bool(value=data["v"])
    if kind == "col":
        column_id = data.get("id")
        if isinstance(column_id, bool) or not isinstance(column_id, int) or column_id < 1:
            raise ValueError("열 노드의 번호는 1 이상의 정수여야 한다.")
        return Col(column_id=column_id)
    if kind == "call":
        name, args = data.get("n"), data.get("a")
        if not isinstance(name, str) or not isinstance(args, list):
            raise ValueError("호출 노드는 이름(n)과 인수 목록(a)이 필요하다.")
        parsed = tuple(ast_from_json(a, _depth=_depth + 1) for a in args)
        depth = 1 + max((a.depth for a in parsed), default=0)
        return Call(name=name, args=parsed, depth=depth)
    raise ValueError("알 수 없는 AST 노드 종류.")


def ast_canonical_json(node: Node) -> str:
    return json.dumps(ast_to_json(node), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def ast_hash(node: Node) -> str:
    """정규 JSON의 sha256 16진수(`formulas.ast_hash`)."""
    return hashlib.sha256(ast_canonical_json(node).encode("utf-8")).hexdigest()
