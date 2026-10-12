"""C0 정적 검사(07 §1 2단계, §3, §7): 이름 해석, 컴파일 때 바꿔 쓰기(`SUMTAG`), 순환, 형 검사.

결과는 **형이 붙은 트리(`TNode`)**다. 참조한 계산 열은 이미 그 열의 트리로 **펼쳐져(인라인)**
있어서 변환기가
원본 열만 읽는 식을 만든다. 오류는 `FormulaIssue` 목록으로 모으되 한 군데가 틀려도 다른 오류를 계속
찾는다
(틀린 값의 형은 `UNKNOWN`이라 연쇄 오류를 만들지 않는다).

규칙 요약
- 형은 `number`·`text`·`boolean`·`date`. 자동 변환 없음(숫자-글자, 날짜-글자 모두 안내 문구와 함께
  거부).
- 상수 규칙: 글자 상수는 NFC 정규화 뒤 200자 이하, NUL·서로게이트·역슬래시·제어·서식 문자 거부.
  숫자 상수는 38자리 이하.
- 상한(07 §7·§4-2 [제안]): 펼친 노드 2,000개, 깊이 40, 참조 사슬 10단계.
"""

from __future__ import annotations

import difflib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.formula.columns import ColumnInfo, is_supported_column_type
from app.formula.cycles import MAX_CHAIN_DEPTH, analyze_graph
from app.formula.errors import FormulaError, FormulaIssue, make_issue
from app.formula.literals import (
    NUMBER,
    TEXT,
    normalize_text_constant,
    number_problem,
    text_constant_problem,
)
from app.formula.nodes import (
    MAX_EXPANDED_DEPTH,
    NEG_NAME,
    Bad,
    Bool,
    Call,
    Col,
    ColName,
    Node,
    Num,
    Text,
    call,
    column_ids,
    strip_positions,
    walk,
)
from app.formula.registry import (
    TYPE_NAMES_KO,
    TYPE_VARIABLE,
    TYPES,
    UNKNOWN,
    FunctionRegistry,
    FunctionSpec,
    Param,
)

MAX_EXPANDED_NODES = 2000  # 펼친 노드 수(07 §1 [제안])
NEW_COLUMN_ID = 0  # 아직 번호가 없는 새 계산 열의 임시 번호


@dataclass(frozen=True, slots=True, eq=False)
class TNode:
    """형이 붙은 트리 노드. 참조한 계산 열의 트리는 여러 곳에서 **공유**된다(DAG)."""

    kind: str  # "num" | "text" | "bool" | "col" | "call" | "bad"
    type: str
    value: Any = None  # 상수 값
    column_id: int | None = None  # kind == "col"
    spec: FunctionSpec | None = None
    args: tuple[TNode, ...] = ()
    start: int = -1  # 이 식이 **현재 수식**의 노드일 때만 원문 위치가 있다(-1이면 펼쳐진 다른 수식)
    end: int = -1
    size: int = 1  # 펼친 노드 수
    depth: int = 1
    const: bool = False  # 열을 읽지 않는 부분식
    height: int = 0  # 상수 호출 부분식의 높이(상수 검사 순서)


def display_name(spec: FunctionSpec) -> str:
    return spec.name if spec.kind == "function" else f"'{spec.symbol}'"


def literal_value(node: TNode) -> Any:
    """직접 쓴 상수(부호 포함)의 값. 계산식·열이면 None."""
    if node.kind in ("num", "text", "bool"):
        return node.value
    if node.kind == "call" and node.spec is not None and node.spec.name == NEG_NAME:
        inner = node.args[0]
        if inner.kind == "num":
            return -inner.value
    return None


def _conversion_hint(expected: str, actual: str) -> str:
    if expected == TEXT and actual == NUMBER:
        return " 숫자를 글자로 자동으로 바꾸지 않습니다."
    if expected == NUMBER and actual == TEXT:
        return " 글자를 숫자로 자동으로 바꾸지 않습니다."
    if "date" in (expected, actual) and TEXT in (expected, actual):
        return (
            " 날짜와 글자는 직접 바꾸거나 비교할 수 없습니다. 날짜는 DATE(연, 월, 일)로 만드세요."
        )
    return ""


def _mismatch_hint(types: Sequence[str]) -> str:
    present = set(types)
    if {"date", TEXT} <= present:
        return " 날짜와 글자는 직접 비교할 수 없습니다. 날짜는 DATE(연, 월, 일)로 만드세요."
    if {NUMBER, TEXT} <= present:
        return " 숫자와 글자는 자동으로 바뀌지 않습니다."
    return ""


class Analysis:
    """수식 하나를 검사하는 상태(열 목록, 참조 트리 메모, 오류 모음)."""

    def __init__(
        self,
        registry: FunctionRegistry,
        columns: Sequence[ColumnInfo],
        *,
        root_id: int,
        root_tag: str | None,
        root_name: str,
    ) -> None:
        self.registry = registry
        self.columns = list(columns)
        self.by_id = {c.id: c for c in self.columns}
        self.by_name = {c.name: c for c in self.columns}
        self.root_id = root_id
        self.root_tag = root_tag
        self.root_name = root_name
        self.ref_trees: dict[int, TNode | None] = {}
        self._deps_cache: dict[int, tuple[int, ...]] = {}
        self.functions_used: set[str] = set()

    # --- 태그 ----
    def columns_with_tag(self, tag: str) -> list[ColumnInfo]:
        """태그가 같은 숫자 열(번호 순).

        편집 중인 새 열도 자기 태그가 같으면 들어가며, 그 경우는 순환으로 걸러진다.
        """
        found = [
            c
            for c in self.columns
            if c.tag == tag
            and c.id != self.root_id
            and is_supported_column_type(c.type)
            and c.formula_type == NUMBER
        ]
        if self.root_tag == tag:
            found.append(ColumnInfo(self.root_id, self.root_name, "number", tag=tag))
        return sorted(found, key=lambda c: c.id)

    # --- 이름 해석 ----
    def resolve(self, node: Node, issues: list[FormulaIssue]) -> Node:
        if isinstance(node, ColName):
            return self._resolve_name(node, issues)
        if isinstance(node, Call):
            args = tuple(self.resolve(a, issues) for a in node.args)
            if all(a is b for a, b in zip(args, node.args, strict=True)):
                return node
            return Call(name=node.name, args=args, start=node.start, end=node.end, depth=node.depth)
        return node

    def _resolve_name(self, node: ColName, issues: list[FormulaIssue]) -> Node:
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in node.name):
            issues.append(make_issue("COLUMN_NAME_INVALID", node.start, node.end))
            return Bad(start=node.start, end=node.end)
        if node.name == "":
            issues.append(make_issue("EMPTY_COLUMN_NAME", node.start, node.end))
            return Bad(start=node.start, end=node.end)
        column = self.by_name.get(node.name)
        if column is not None:
            return Col(column_id=column.id, start=node.start, end=node.end)
        suggest = self._suggest(node.name, list(self.by_name), quote="[{}]")
        issues.append(
            make_issue("UNKNOWN_COLUMN", node.start, node.end, name=node.name, suggest=suggest)
        )
        return Bad(start=node.start, end=node.end)

    @staticmethod
    def _suggest(name: str, choices: list[str], *, quote: str) -> str:
        folded = {c.casefold().strip(): c for c in choices}
        exact = folded.get(name.casefold().strip())
        close = [exact] if exact else difflib.get_close_matches(name, choices, n=3, cutoff=0.6)
        if not close:
            return ""
        return " 비슷한 이름: " + ", ".join(quote.format(c) for c in close)

    # --- 컴파일 때 바꿔 쓰기(SUMTAG) ----
    def rewrite(self, node: Node, issues: list[FormulaIssue]) -> Node:
        """`rewrite` 항목(예: `SUMTAG`)을 다른 AST로 바꾼다. 저장되는 AST는 바뀌지 않는다."""
        if not isinstance(node, Call):
            return node
        args = tuple(self.rewrite(a, issues) for a in node.args)
        try:
            current = call(node.name, args, start=node.start, end=node.end)
            spec = self.registry.get(node.name)
            if spec is not None and spec.rewrite is not None:
                return spec.rewrite(current, self.columns_with_tag)
            return current
        except FormulaError as exc:
            issues.extend(exc.issues)
            return Bad(start=node.start, end=node.end)

    # --- 순환·사슬 ----
    def stored_deps(self, column_id: int) -> tuple[int, ...]:
        """계산 열 하나가 저장된 수식에서 직접 참조하는 열(태그 펼침 포함)."""
        if column_id not in self._deps_cache:
            column = self.by_id[column_id]
            ast = self.rewrite(column.formula, []) if column.formula is not None else None
            self._deps_cache[column_id] = tuple(column_ids(ast)) if ast is not None else ()
        return self._deps_cache[column_id]

    def check_graph(
        self, root_ast: Node, issues: list[FormulaIssue], span: tuple[int, int]
    ) -> tuple[int, ...] | None:
        """순환·사슬 깊이를 검사한다. 오류가 없으면 참조한 계산 열을 의존 순서로 돌려준다."""
        root_refs = column_ids(root_ast)
        graph = analyze_graph(
            self.root_id,
            root_refs,
            lambda cid: cid in self.by_id and self.by_id[cid].is_formula,
            self.stored_deps,
        )
        if graph.cycle is not None:
            names = [self.root_name if c == self.root_id else self._name_of(c) for c in graph.cycle]
            at = self._cycle_reference_span(root_ast, graph.cycle[1])
            issues.append(make_issue("CIRCULAR", *(at or span), path_names=names))
            return None
        if graph.chain > MAX_CHAIN_DEPTH:
            issues.append(make_issue("CHAIN_TOO_LONG", *span, max=MAX_CHAIN_DEPTH))
            return None
        return graph.order

    def _name_of(self, column_id: int) -> str:
        column = self.by_id.get(column_id)
        return column.name if column is not None else f"열 {column_id}"

    @staticmethod
    def _cycle_reference_span(root_ast: Node, target_id: int) -> tuple[int, int] | None:
        """순환의 첫 고리를 이루는 열 참조가 수식 글자의 어디인지."""
        for item in walk(root_ast):
            if isinstance(item, Col) and item.column_id == target_id:
                return item.start, item.end
        return None

    # --- 참조한 계산 열을 펼칠 트리로 ----
    def build_references(self, order: Sequence[int]) -> None:
        """계산 열을 의존되는 쪽부터 한 번씩 분석해 트리를 메모한다.

        재귀가 수식 하나 안에 머문다.
        """
        for column_id in order:
            column = self.by_id[column_id]
            if column.formula is None:
                self.ref_trees[column_id] = None
                continue
            issues: list[FormulaIssue] = []
            ast = self.rewrite(strip_positions(column.formula), issues)
            tree = self.build(ast, issues) if not issues else None
            self.ref_trees[column_id] = tree if not issues else None

    # --- 형 검사 ----
    def build(self, node: Node, issues: list[FormulaIssue]) -> TNode:
        if isinstance(node, Num):
            problem = number_problem(node.value)
            if problem:
                issues.append(make_issue("NUMBER_INVALID", node.start, node.end))
            return TNode("num", NUMBER, node.value, start=node.start, end=node.end, const=True)
        if isinstance(node, Text):
            value = normalize_text_constant(node.value)
            reason = text_constant_problem(value)
            if reason:
                issues.append(
                    make_issue("TEXT_CONSTANT_INVALID", node.start, node.end, reason=reason)
                )
            return TNode("text", TEXT, value, start=node.start, end=node.end, const=True)
        if isinstance(node, Bool):
            return TNode("bool", "boolean", node.value, start=node.start, end=node.end, const=True)
        if isinstance(node, Col):
            return self._build_column(node, issues)
        if isinstance(node, Call):
            return self._build_call(node, issues)
        return TNode("bad", UNKNOWN, start=node.start, end=node.end)

    def _build_column(self, node: Col, issues: list[FormulaIssue]) -> TNode:
        column = self.by_id.get(node.column_id)
        bad = TNode("bad", UNKNOWN, start=node.start, end=node.end)
        if column is None:
            issues.append(make_issue("REF_MISSING", node.start, node.end, column_id=node.column_id))
            return bad
        if not is_supported_column_type(column.type):
            issues.append(
                make_issue("COLUMN_TYPE_UNSUPPORTED", node.start, node.end, name=column.name)
            )
            return bad
        if column.is_formula:
            tree = self.ref_trees.get(column.id)
            if tree is None:
                issues.append(
                    make_issue("REF_FORMULA_INVALID", node.start, node.end, name=column.name)
                )
                return bad
            return tree  # 펼침: 참조한 열의 트리를 그대로 쓴다(공유)
        return TNode(
            "col", column.formula_type, column_id=column.id, start=node.start, end=node.end
        )

    def _build_call(self, node: Call, issues: list[FormulaIssue]) -> TNode:
        targs = tuple(self.build(a, issues) for a in node.args)
        spec = self.registry.get(node.name)
        if spec is None or (spec.kind == "function" and node.name != node.name.upper()):
            suggest = self._suggest(node.name, self.registry.function_names(), quote="{}")
            issues.append(
                make_issue(
                    "UNKNOWN_FUNCTION", node.start, node.end, name=node.name, suggest=suggest
                )
            )
            return TNode("bad", UNKNOWN, start=node.start, end=node.end)
        self.functions_used.add(spec.name)
        result_type = self._check_call(node, spec, targs, issues)
        depth = 1 + max((t.depth for t in targs), default=0)
        if depth > MAX_EXPANDED_DEPTH:
            issues.append(make_issue("TOO_DEEP", node.start, node.end, max=MAX_EXPANDED_DEPTH))
            return TNode("bad", UNKNOWN, start=node.start, end=node.end)
        const = all(t.const for t in targs) and spec.rewrite is None
        height = 1 + max((t.height for t in targs), default=0) if const else 0
        return TNode(
            "call",
            result_type,
            spec=spec,
            args=targs,
            start=node.start,
            end=node.end,
            size=1 + sum(t.size for t in targs),
            depth=depth,
            const=const,
            height=height,
        )

    def _check_call(
        self, node: Call, spec: FunctionSpec, targs: tuple[TNode, ...], issues: list[FormulaIssue]
    ) -> str:
        label = display_name(spec)
        count = len(targs)
        high = spec.max_args
        if count < spec.min_args or (high is not None and count > high):
            issues.append(
                make_issue(
                    "ARG_COUNT",
                    node.start,
                    node.end,
                    name=label,
                    expected=spec.arity_text(),
                    actual=count,
                )
            )
            return self._declared_return(spec, {})
        bound: dict[str, str] = {}
        mixed: list[str] = []
        for index, (arg_ast, targ) in enumerate(zip(node.args, targs, strict=True)):
            param = spec.param_for(index)
            if targ.type == UNKNOWN:
                continue
            self._check_arg(label, index, param, targ, arg_ast, bound, mixed, issues)
        if mixed:
            issues.append(
                make_issue(
                    "TYPE_MISMATCH",
                    node.start,
                    node.end,
                    name=label,
                    types=" / ".join(dict.fromkeys(TYPE_NAMES_KO[t] for t in mixed)),
                    hint=_mismatch_hint(mixed),
                )
            )
        return self._declared_return(spec, bound)

    @staticmethod
    def _declared_return(spec: FunctionSpec, bound: dict[str, str]) -> str:
        if spec.returns == TYPE_VARIABLE:
            return bound.get(TYPE_VARIABLE, UNKNOWN)
        return spec.returns

    def _check_arg(
        self,
        label: str,
        index: int,
        param: Param,
        targ: TNode,
        arg_ast: Node,
        bound: dict[str, str],
        mixed: list[str],
        issues: list[FormulaIssue],
    ) -> None:
        position = index + 1
        if param.type == TYPE_VARIABLE:
            allowed = param.allowed or frozenset(TYPES)
            if targ.type not in allowed:
                expected = "·".join(TYPE_NAMES_KO[t] for t in TYPES if t in allowed)
                hint = ""
                if targ.type == TEXT and allowed == frozenset({NUMBER, "date"}):
                    hint = " 글자는 같은지(=, <>)만 비교할 수 있고 크기 비교는 쓸 수 없습니다."
                issues.append(
                    make_issue(
                        "ARG_TYPE",
                        arg_ast.start,
                        arg_ast.end,
                        name=label,
                        position=position,
                        expected=expected,
                        actual=TYPE_NAMES_KO[targ.type],
                        hint=hint,
                    )
                )
                return
            first = bound.setdefault(TYPE_VARIABLE, targ.type)
            if first != targ.type and not mixed:
                mixed.extend([first, targ.type])
            return
        if targ.type != param.type:
            issues.append(
                make_issue(
                    "ARG_TYPE",
                    arg_ast.start,
                    arg_ast.end,
                    name=label,
                    position=position,
                    expected=TYPE_NAMES_KO[param.type],
                    actual=TYPE_NAMES_KO[targ.type],
                    hint=_conversion_hint(param.type, targ.type),
                )
            )
            return
        if param.const is not None:
            self._check_const(label, position, param, targ, arg_ast, issues)

    @staticmethod
    def _check_const(
        label: str,
        position: int,
        param: Param,
        targ: TNode,
        arg_ast: Node,
        issues: list[FormulaIssue],
    ) -> None:
        rule = param.const
        assert rule is not None  # noqa: S101
        value = literal_value(targ)
        kind_ko = "정수" if rule.kind == "integer" else "글자"
        if value is None:
            issues.append(
                make_issue(
                    "CONST_REQUIRED",
                    arg_ast.start,
                    arg_ast.end,
                    name=label,
                    position=position,
                    kind=kind_ko,
                )
            )
            return
        if rule.kind == "integer":
            if value != value.to_integral_value() or (
                (rule.min is not None and value < rule.min)
                or (rule.max is not None and value > rule.max)
            ):
                low = f"{rule.min}" if rule.min is not None else "작은"
                high = f"{rule.max}" if rule.max is not None else "큰"
                issues.append(
                    make_issue(
                        "CONST_RANGE",
                        arg_ast.start,
                        arg_ast.end,
                        name=label,
                        position=position,
                        range=f"{low}~{high} 사이의 정수",
                    )
                )
        elif rule.max_length is not None and len(value) > rule.max_length:
            issues.append(
                make_issue(
                    "CONST_RANGE",
                    arg_ast.start,
                    arg_ast.end,
                    name=label,
                    position=position,
                    range=f"{rule.max_length}자 이하의 글자",
                )
            )
