"""수식 엔진의 공개 인터페이스(2단계: DB 통합·뷰·API·차분 시험이 쓴다). 순수 로직이며 DB를 모른다.

사용 순서
1. `ColumnInfo` 목록을 만든다(데이터셋의 모든 열. 계산 열은 저장된 AST를 `ast_from_json`으로 복원해
  `formula`에).
2. `check_formula(...)`: 편집기 검사(05 D2). `compile_formula(...)`: 저장·미리보기·뷰용 식까지
  만든다.
3. 결과의 `value`/`error` 표현식을 `select(...)`에 넣어 **그대로 실행**하면 미리보기(상수는 바인드),
   `literals.render_literal_sql(select(...))`로 렌더하면 뷰 정의와 같은 글자(해시·`CreateView`용)다.
4. 저장: `result.ast_json`/`ast_hash`(`formulas.ast`·`ast_hash`), `result.deps`(`formula_deps`).
5. 수식 보기: `render_text(ast, columns)`. 오류 칸 문구: `errors.CELL_ERROR_MESSAGES_KO`.

가정(2단계가 확인해야 하는 것)
- `source_columns`를 주지 않으면 원본 열은 `sa.column("c_<번호>", 형)`(표 없음)이다. 실제 뷰에서는
  `ds_<번호>` 표의 열 객체 매핑을 넘긴다.
- `const_probe`가 없으면 상수 부분식 오류(`1/0` 등) 검사를 건너뛰고 `const_probe_skipped=True`로
  표시한다.
  저장·미리보기 경로는 반드시 DB 상수 `SELECT`로 평가하는 `const_probe`를 넘겨야 한다
  (`ConstProbe`: 참/거짓 조건 식 목록 -> 결과 목록; 읽기 전용 트랜잭션에서 한 번의 `SELECT`).
- 위치(`start`/`end`)는 원문의 코드포인트 번호다(`errors.py`).
- `column_id`: 편집 중인 기존 계산 열의 번호(자기 참조·순환 기준). 새 열이면 `None`이고 새 열의
  태그는
  `tag`로 준다(기존 열의 태그는 `ColumnInfo.tag`가 우선한다).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa
from sqlalchemy.sql.elements import ColumnElement

from app.ddl.names import column_name
from app.formula.analyze import MAX_EXPANDED_NODES, NEW_COLUMN_ID, Analysis, TNode
from app.formula.columns import ColumnInfo, is_supported_column_type
from app.formula.context import ConvertContext
from app.formula.convert import ConstProbe, Converter, run_const_probes
from app.formula.errors import FormulaError, FormulaIssue, make_issue
from app.formula.functions import build_default_registry, get_default_registry
from app.formula.literals import LITERALS, Literals
from app.formula.nodes import (
    MAX_EXPANDED_DEPTH,
    Call,
    Node,
    Text,
    ast_canonical_json,
    ast_hash,
    ast_to_json,
    column_ids,
    walk,
)
from app.formula.parser import parse_expression
from app.formula.registry import FunctionRegistry
from app.formula.textview import render_text

_SQL_TYPES: dict[str, type[sa.types.TypeEngine]] = {
    "number": sa.Numeric,
    "text": sa.Text,
    "boolean": sa.Boolean,
    "date": sa.Date,
}


@dataclass(frozen=True)
class CompileResult:
    ok: bool
    issues: tuple[FormulaIssue, ...] = ()
    result_type: str | None = None  # number | text | boolean | date
    ast: Node | None = None  # 열 번호로 해석된 AST(SUMTAG는 펼치지 않은 저장 형태)
    deps: tuple[int, ...] = ()  # 직접 참조하는 열 번호(`SUMTAG` 펼침 포함, 처음 나온 순서)
    source_columns: tuple[int, ...] = ()  # 펼친 식이 읽는 원본 열 번호(오름차순)
    sumtag_columns: Mapping[str, tuple[int, ...]] = field(default_factory=dict)
    functions_used: frozenset[str] = frozenset()
    node_count: int = 0  # 펼친 AST 노드 수
    value: ColumnElement[Any] | None = None
    error: ColumnElement[Any] | None = None  # None이면 오류가 날 수 없는 식
    const_probe_skipped: bool = False

    @property
    def ast_json(self) -> dict[str, Any]:
        if self.ast is None:
            raise ValueError("AST가 없다(수식에 오류가 있다).")
        return ast_to_json(self.ast)

    @property
    def ast_hash(self) -> str:
        if self.ast is None:
            raise ValueError("AST가 없다(수식에 오류가 있다).")
        return ast_hash(self.ast)

    def check_response(self, columns: Sequence[ColumnInfo]) -> dict[str, Any]:
        """05 D2 응답 모양.

        `{ok, result_type, refs[{column_id, display_name}], errors[{code, message, start, end}]}`.
        """
        names = {c.id: c.name for c in columns}
        return {
            "ok": self.ok,
            "result_type": self.result_type if self.ok else None,
            "refs": [
                {"column_id": cid, "display_name": names[cid]} for cid in self.deps if cid in names
            ],
            "errors": [issue.as_dict() for issue in self.issues],
        }


def _failure(issues: Sequence[FormulaIssue], length: int, **extra: Any) -> CompileResult:
    """위치가 없는 오류는 수식 전체 구간으로 맞추고 위치순으로 정렬한다."""
    fixed = [
        i if i.start >= 0 else FormulaIssue(i.code, i.message, 0, length, i.path) for i in issues
    ]
    fixed.sort(key=lambda i: (i.start, i.end, i.code))
    return CompileResult(ok=False, issues=tuple(fixed), **extra)


def _default_source(columns: Mapping[int, ColumnInfo]):
    def source(column_id: int) -> ColumnElement[Any]:
        info = columns[column_id]
        return sa.column(column_name(column_id), _SQL_TYPES[info.formula_type]())

    return source


def _raw_columns(root: TNode) -> tuple[int, ...]:
    seen: set[int] = set()
    found: set[int] = set()
    stack = [root]
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        if node.kind == "col" and node.column_id is not None:
            found.add(node.column_id)
        stack.extend(node.args)
    return tuple(sorted(found))


def _sumtag_columns(
    analysis: Analysis, ast: Node, registry: FunctionRegistry
) -> dict[str, tuple[int, ...]]:
    """수식 속 `rewrite` 항목(`SUMTAG`)의 태그 -> 지금 포함하는 열 번호.

    수식 보기의 "포함 열 목록"에 쓴다.
    """
    found: dict[str, tuple[int, ...]] = {}
    for item in walk(ast):
        if not isinstance(item, Call) or len(item.args) != 1 or not isinstance(item.args[0], Text):
            continue
        spec = registry.get(item.name)
        if spec is not None and spec.rewrite is not None:
            tag = item.args[0].value
            found[tag] = tuple(c.id for c in analysis.columns_with_tag(tag))
    return found


def compile_formula(
    expression: str,
    columns: Sequence[ColumnInfo],
    *,
    column_id: int | None = None,
    tag: str | None = None,
    column_name_hint: str | None = None,
    registry: FunctionRegistry | None = None,
    source_columns: Mapping[int, ColumnElement[Any]] | None = None,
    const_probe: ConstProbe | None = None,
    build_sql: bool = True,
    literals: Literals = LITERALS,
) -> CompileResult:
    """수식 글자를 검사(C0)하고 (값 식, 오류 식)까지 만든다. 오류가 있으면 `ok=False`와 `issues`.

    단계: 파싱 -> 열 이름 해석 -> `SUMTAG` 바꿔 쓰기 -> 순환·사슬 검사 -> 형 검사(참조한 계산 열은
    펼침)
    -> 크기 상한 -> 변환 -> 상수 부분식 오류 검사. 수식에 문제가 있어도 예외 대신 `issues`로
    돌려준다.
    """
    registry = registry or get_default_registry()
    length = len(expression) if isinstance(expression, str) else 0
    try:
        parsed = parse_expression(expression)
    except FormulaError as exc:
        return _failure(exc.issues, length)

    existing = {c.id: c for c in columns}
    root_id = column_id if column_id is not None else NEW_COLUMN_ID
    own = existing.get(root_id)
    root_tag = own.tag if own is not None else tag
    root_name = column_name_hint or (own.name if own is not None else "이 열")
    analysis = Analysis(registry, columns, root_id=root_id, root_tag=root_tag, root_name=root_name)
    issues: list[FormulaIssue] = []

    try:
        resolved = analysis.resolve(parsed, issues)
        rewritten = analysis.rewrite(resolved, issues)
        order = analysis.check_graph(rewritten, issues, (0, length))
        if order is None:
            return _failure(issues, length)
        analysis.build_references(order)
        root = analysis.build(rewritten, issues)
        if root.size > MAX_EXPANDED_NODES:
            issues.append(
                make_issue("TOO_MANY_NODES", 0, length, max=MAX_EXPANDED_NODES, count=root.size)
            )
        if issues:
            return _failure(issues, length)
    except RecursionError:  # 깊이 상한이 막지만 방어한다
        return _failure([make_issue("TOO_DEEP", 0, length, max=MAX_EXPANDED_DEPTH)], length)

    base: dict[str, Any] = {
        "result_type": root.type,
        "ast": resolved,
        "deps": tuple(column_ids(rewritten)),
        "source_columns": _raw_columns(root),
        "sumtag_columns": _sumtag_columns(analysis, resolved, registry),
        "functions_used": frozenset(analysis.functions_used),
        "node_count": root.size,
    }
    if not build_sql:
        return CompileResult(ok=True, **base)

    by_id = {c.id: c for c in columns if is_supported_column_type(c.type)}
    source = _source_lookup(source_columns, by_id)
    converter = Converter(ConvertContext(lit=literals, source=source))
    try:
        compiled = converter.convert(root)
    except FormulaError as exc:
        return _failure(exc.issues, length)
    except RecursionError:
        return _failure([make_issue("TOO_DEEP", 0, length, max=MAX_EXPANDED_DEPTH)], length)
    skipped = False
    if converter.probes:
        if const_probe is None:
            skipped = True
        else:
            probe_issues = run_const_probes(converter.probes, const_probe)
            if probe_issues:
                return _failure(probe_issues, length)
    return CompileResult(
        ok=True,
        value=compiled.value,
        error=compiled.error,
        const_probe_skipped=skipped,
        **base,
    )


def _source_lookup(source_columns: Mapping[int, ColumnElement[Any]] | None, by_id):
    if source_columns is None:
        return _default_source(by_id)

    def source(column_id: int) -> ColumnElement[Any]:
        return source_columns[column_id]

    return source


def check_formula(
    expression: str,
    columns: Sequence[ColumnInfo],
    *,
    column_id: int | None = None,
    tag: str | None = None,
    registry: FunctionRegistry | None = None,
    const_probe: ConstProbe | None = None,
) -> CompileResult:
    """편집기 검사(05 D2).

    `const_probe`를 주면 상수 부분식 오류까지, 없으면 DB 없이 정적 검사만 한다.
    """
    return compile_formula(
        expression,
        columns,
        column_id=column_id,
        tag=tag,
        registry=registry,
        const_probe=const_probe,
        build_sql=const_probe is not None,
    )


__all__ = [
    "CompileResult",
    "ConstProbe",
    "FunctionRegistry",
    "ast_canonical_json",
    "build_default_registry",
    "check_formula",
    "compile_formula",
    "get_default_registry",
    "render_text",
]
