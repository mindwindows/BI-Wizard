"""AST(형이 붙은 트리) -> (값 식, 오류 식) SQLAlchemy 표현식(07 §1 3단계, §3, §3-1).

- 참조한 계산 열은 이미 펼쳐져 있어(`analyze.TNode`) 각 식은 원본 열(`c_<번호>`)만 읽는다.
- 문자열 조립·`text()`·`exec_driver_sql` 없음. 상수와 NULL은 모두 `ctx.lit`(리터럴 렌더러 접점)을
  거친다.
- 값 식: 오류 칸이면 NULL. 오류 식: 정상·빈 값이면 NULL, 오류면 셀 오류 코드(smallint). 오류가 날
  수 없는
  식은 `error=None`이다. 평가 순서는 인수 오류 > 인수 빈 값 > 자기 조건이고, `IF`는 고른 쪽만,
  `IFERROR`는 오류 칸이면 대체값 / 빈 값은 그대로(사전 항목의 `to_sql_custom`).
- 같은 트리가 여러 곳에서 공유되므로 변환 결과도 공유한다(DAG). 그래서 SQL 글자 수는 트리를 펼친
  크기가
  될 수 있어, 노드마다 **펼친 SQL 크기를 산술로 계산**해 `MAX_SQL_NODES`를 넘으면 `TOO_COMPLEX`로
  거부한다.
- 상수만으로 된 부분식(`1/0`, `LEFT("a",-1)`, `DATE(0,1,1)`)의 오류 조건은 `Probe`로 모았다가 DB
  상수
  `SELECT`로 평가한다(`run_const_probes`). PostgreSQL이 상수식은 쓰이지 않는 `CASE` 갈래에서도 계획
  시간에
  실패할 수 있기 때문이다(07 §3). 값 식은 실행하지 않고 사전의 조건 식만 쓰므로 이중 구현이 아니다.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.sql.elements import ColumnElement

from app.formula.analyze import TNode, literal_value
from app.formula.context import Compiled, ConvertContext
from app.formula.errors import CONSTANT_ERROR_REASONS_KO, FormulaError, FormulaIssue, make_issue
from app.formula.literals import SMALLINT

MAX_SQL_NODES = 50_000  # 변환 결과 SQL 트리(공유 부분 중복 포함)의 노드 수 상한 [제안]

ConstProbe = Callable[[Sequence[ColumnElement[Any]]], Sequence[Any]]


class SqlSizer:
    """SQLAlchemy 표현식 트리의 펼친 크기(공유 부분은 쓰인 횟수만큼 센다). 메모로 선형 시간."""

    def __init__(self) -> None:
        self._memo: dict[int, tuple[Any, int]] = {}

    def size(self, element: Any) -> int:
        cached = self._memo.get(id(element))
        if cached is not None:
            return cached[1]
        total = 1 + sum(self.size(child) for child in element.get_children())
        self._memo[id(element)] = (element, total)  # element를 붙잡아 id가 재사용되지 않게 한다
        return total


@dataclass(frozen=True)
class Probe:
    """상수 부분식의 오류 조건 하나."""

    node: TNode
    code: str
    condition: ColumnElement[Any]


class Converter:
    def __init__(self, ctx: ConvertContext, *, max_sql_nodes: int = MAX_SQL_NODES) -> None:
        self.ctx = ctx
        self.max_sql_nodes = max_sql_nodes
        self.probes: list[Probe] = []
        self._memo: dict[int, tuple[TNode, Compiled]] = {}
        self._sizer = SqlSizer()

    def convert(self, node: TNode) -> Compiled:
        cached = self._memo.get(id(node))
        if cached is not None:
            return cached[1]
        result = self._convert(node)
        if node.kind == "call" and (literal := literal_value(node)) is not None:
            result = dataclasses.replace(result, const=literal)  # 부호 붙은 상수(-2)도 상수로 본다
        total = self._sizer.size(result.value)
        if result.error is not None:
            total += self._sizer.size(result.error)
        if total > self.max_sql_nodes:
            raise FormulaError(make_issue("TOO_COMPLEX", node.start, node.end))
        self._memo[id(node)] = (node, result)
        return result

    def _convert(self, node: TNode) -> Compiled:
        lit = self.ctx.lit
        if node.kind == "num":
            return Compiled(lit.number(node.value), None, node.type, node.value)
        if node.kind == "text":
            return Compiled(lit.text(node.value), None, node.type, node.value)
        if node.kind == "bool":
            return Compiled(lit.boolean(node.value), None, node.type, node.value)
        if node.kind == "col":
            assert node.column_id is not None  # noqa: S101
            return Compiled(self.ctx.source(node.column_id), None, node.type)
        if node.kind == "call" and node.spec is not None:
            return self._convert_call(node)
        raise ValueError("변환할 수 없는 노드(오류가 있는 수식은 변환하지 않는다).")

    def _convert_call(self, node: TNode) -> Compiled:
        spec = node.spec
        assert spec is not None  # noqa: S101
        args = [self.convert(a) for a in node.args]
        if spec.rewrite is not None:
            raise ValueError(f"{spec.name}은(는) 컴파일 때 바꿔 써야 한다(변환 대상이 아니다).")
        if spec.to_sql_custom is not None:
            return dataclasses.replace(spec.to_sql_custom(self.ctx, args), type=node.type)
        assert spec.to_sql is not None  # noqa: S101
        lit = self.ctx.lit
        raw = spec.to_sql(self.ctx, args)
        conditions = [rule.when(self.ctx, args) for rule in spec.error_when]
        if node.const and node.start >= 0:
            self.probes.extend(
                Probe(node, rule.code, cond)
                for rule, cond in zip(spec.error_when, conditions, strict=True)
            )
        nullable = [a.value.is_(None) for a in args if a.const is None]
        # --- 값 식 ----
        whens: list[tuple[Any, Any]] = []
        if spec.null_policy == "propagate" and not spec.native_null and nullable:
            whens.append((sa.or_(*nullable), self.ctx.null(node.type)))
        if conditions and not spec.self_guarded:
            whens.append((sa.or_(*conditions), self.ctx.null(node.type)))
        value = sa.case(*whens, else_=raw) if whens else raw
        # --- 오류 식 ----
        parts: list[ColumnElement[Any]] = [a.error for a in args if a.error is not None]
        if conditions:
            error_whens: list[tuple[Any, Any]] = []
            if spec.null_policy != "skip" and len(args) > 1 and nullable:
                error_whens.append((sa.or_(*nullable), self.ctx.null(SMALLINT)))
            error_whens += [
                (cond, lit.code(rule.code))
                for rule, cond in zip(spec.error_when, conditions, strict=True)
            ]
            parts.append(sa.case(*error_whens))
        error = None
        if parts:
            error = parts[0] if len(parts) == 1 else sa.func.coalesce(*parts)
        return Compiled(value, error, node.type)


def run_const_probes(probes: Sequence[Probe], probe: ConstProbe) -> list[FormulaIssue]:
    """상수 부분식의 오류 조건을 DB 상수 SELECT로 평가해 참인 것을 `CONSTANT_ERROR`로 돌려준다.

    안쪽 상수 부분식이 이미 오류면 그것을 품은 바깥 식은 평가하지 않는다(안쪽 오류가 바깥 식의 상수
    평가를
    깨뜨릴 수 있고, 안쪽 오류만 알려 주면 충분하다). 높이 순으로 한 번에 묶어 DB 왕복을 줄인다.
    """
    issues: list[FormulaIssue] = []
    errored: set[int] = set()
    tainted_memo: dict[int, bool] = {}

    def tainted(node: TNode) -> bool:
        """이 노드 **아래**에 오류가 확정된 상수 부분식이 있는가."""
        cached = tainted_memo.get(id(node))
        if cached is None:
            cached = any(id(a) in errored or tainted(a) for a in node.args)
            tainted_memo[id(node)] = cached
        return cached

    by_height: dict[int, list[Probe]] = {}
    for item in probes:
        by_height.setdefault(item.node.height, []).append(item)
    for height in sorted(by_height):
        tainted_memo.clear()
        pending = [
            p for p in by_height[height] if not tainted(p.node) and id(p.node) not in errored
        ]
        if not pending:
            continue
        results = _evaluate(pending, probe)
        for item, result in zip(pending, results, strict=True):
            if id(item.node) in errored:
                continue
            if result is None:  # 평가 자체가 실패
                issues.append(make_issue("CONSTANT_PROBE_FAILED", item.node.start, item.node.end))
                errored.add(id(item.node))
            elif result:
                reason = CONSTANT_ERROR_REASONS_KO[item.code]
                issues.append(
                    make_issue("CONSTANT_ERROR", item.node.start, item.node.end, reason=reason)
                )
                errored.add(id(item.node))
    return issues


def _evaluate(pending: Sequence[Probe], probe: ConstProbe) -> list[Any]:
    """한 번에 평가하고, 실패하면 하나씩 평가한다(실패한 것은 `None`)."""
    conditions = [p.condition for p in pending]
    try:
        values = list(probe(conditions))
    except Exception:  # DB 오류의 종류는 모른다. 하나씩 다시 시도한다.
        values = []
    if len(values) == len(conditions):
        return [bool(v) if v is not None else False for v in values]
    results: list[Any] = []
    for condition in conditions:
        try:
            (value,) = list(probe([condition]))
            results.append(bool(value) if value is not None else False)
        except Exception:
            results.append(None)
    return results
