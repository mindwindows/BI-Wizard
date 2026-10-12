"""함수 사전의 구조와 등록부(07 §2, 03b 5-2 K6).

**함수 추가 = `FunctionSpec` 한 개 + `cases`.** 파서·C0 검사·변환기·도움말은 사전을 읽기만 하므로
고치지
않는다(`tests/test_formula_registry.py`가 시험에서 임시 함수를 등록해 끝까지 동작함을 보인다).

한 항목이 정하는 것
- `signature`: 인수 목록. `Param.type`은 `number`·`text`·`boolean`·`date` 또는 `T`(허용 목록 안에서
  모든
  `T` 인수가 같은 종류). 마지막 인수만 `repeat=True`(0번 이상 반복)일 수 있다. `const`는 "직접 쓴
  상수만".
- `returns`: 형 또는 `T`(묶인 종류).
- `null_policy`: `propagate`(어느 인수라도 비면 결과도 빔; 프레임워크가 감싼다. SQL 식이 이미 NULL을
  전파하면 `native_null=True`), `skip`(NULL을 건너뛰는 합계용, FU-1에서는 쓰지 않음),
  `custom`(IF·IFERROR처럼
  `to_sql_custom`이 값 식과 오류 식을 직접 만든다).
- `error_when`: (코드, 조건 식) 목록. 평가 순서는 인수 오류 > 인수 빈 값 > 자기 조건. 조건이 참이면
  값은 NULL.
  `self_guarded=True`면 `to_sql`이 이미 조건일 때 NULL을 돌려주므로(예: `NULLIF`) 프레임워크가 값을
  감싸지 않는다.
- `to_sql(ctx, args)`: 인수의 `Compiled`를 받아 값 식을 돌려준다. 상수·NULL은 `ctx.lit`만 쓴다.
- `rewrite`: 컴파일 때 AST를 다른 AST로 바꾸는 항목(`SUMTAG`). `to_sql`이 없다.
- `sqlite`: SQLite로도 평가할 수 있는가(1단계 시험이 쓴다. 운영과는 무관).
- `cases`: 시험 사례(필수). `help_ko`·`excel_diff`: 도움말과 엑셀 차이 문구(자동완성·도움말이
  여기서 생성).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.sql.elements import ColumnElement

from app.formula.cases import ERROR, OK, REJECT, Case
from app.formula.columns import ColumnInfo
from app.formula.context import Compiled, ConvertContext
from app.formula.errors import CELL_ERROR_MESSAGES_KO
from app.formula.literals import BOOLEAN, DATE, NUMBER, TEXT
from app.formula.nodes import Call, Node

TYPES = (NUMBER, TEXT, BOOLEAN, DATE)
UNKNOWN = "unknown"  # 오류 복구 중인 값의 형(추가 오류를 만들지 않는다)
TYPE_VARIABLE = "T"
TYPE_NAMES_KO = {NUMBER: "숫자", TEXT: "글자", BOOLEAN: "참/거짓", DATE: "날짜"}

NULL_POLICIES = ("propagate", "skip", "custom")
_FUNCTION_NAME = re.compile(r"[A-Z][A-Z0-9_.]*")

ToSql = Callable[[ConvertContext, Sequence[Compiled]], ColumnElement[Any]]
ToSqlCustom = Callable[[ConvertContext, Sequence[Compiled]], Compiled]
Condition = Callable[[ConvertContext, Sequence[Compiled]], ColumnElement[Any]]
Rewrite = Callable[[Call, Callable[[str], Sequence[ColumnInfo]]], Node]


class RegistryError(ValueError):
    """사전 항목이 규칙을 어김(등록 때 거부)."""


@dataclass(frozen=True)
class ConstRule:
    """ "직접 쓴 상수만" 허용하는 인수의 조건."""

    kind: str  # "integer" | "text"
    min: int | None = None
    max: int | None = None
    max_length: int | None = None


@dataclass(frozen=True)
class Param:
    name: str
    type: str
    allowed: frozenset[str] | None = None  # type == "T"일 때 허용 종류(없으면 4종 전부)
    repeat: bool = False
    const: ConstRule | None = None


@dataclass(frozen=True)
class ErrorRule:
    code: str
    when: Condition


@dataclass(frozen=True)
class FunctionSpec:
    name: str
    signature: tuple[Param, ...]
    returns: str
    null_policy: str
    excel_diff: str
    help_ko: str
    cases: tuple[Case, ...]
    kind: str = "function"  # "function" | "operator"
    symbol: str | None = None  # 연산자 글자(`+`, `neg`는 `-`)
    syntax: str | None = None  # 연산자: "infix" | "prefix"
    level: int | None = (
        None  # 연산자 우선순위(클수록 먼저 묶임): 비교 1 < & 2 < + - 3 < * / 4 < 부호 5
    )
    error_when: tuple[ErrorRule, ...] = ()
    to_sql: ToSql | None = None
    to_sql_custom: ToSqlCustom | None = None
    rewrite: Rewrite | None = None
    native_null: bool = False
    self_guarded: bool = False
    sqlite: bool = False

    # --- 인수 개수 ----
    @property
    def min_args(self) -> int:
        return sum(1 for p in self.signature if not p.repeat)

    @property
    def max_args(self) -> int | None:
        return None if any(p.repeat for p in self.signature) else len(self.signature)

    def param_for(self, index: int) -> Param:
        """`index`번째(0부터) 인수의 규칙. 반복 인수는 그 뒤 모든 위치에 적용된다."""
        if index < len(self.signature):
            return self.signature[index]
        return self.signature[-1]

    def arity_text(self) -> str:
        low, high = self.min_args, self.max_args
        if high is None:
            return f"{low}개 이상"
        return f"{low}개" if low == high else f"{low}~{high}개"


def describe_signature(spec: FunctionSpec) -> str:
    """도움말용 인수 모양 글자(예: `ROUND(수, 자릿수)`, `숫자 + 숫자`)."""
    names = [p.name + ("…" if p.repeat else "") for p in spec.signature]
    if spec.kind == "operator" and spec.syntax == "infix":
        return f" {spec.symbol} ".join(names[:2])
    if spec.kind == "operator":
        return f"{spec.symbol}{names[0]}"
    return f"{spec.name}({', '.join(names)})"


def _display_name(spec: FunctionSpec) -> str:
    if spec.kind == "function":
        return spec.name
    return f"{spec.symbol}(부호)" if spec.syntax == "prefix" else str(spec.symbol)


def describe_returns(spec: FunctionSpec) -> str:
    return "인수와 같은 종류" if spec.returns == TYPE_VARIABLE else TYPE_NAMES_KO[spec.returns]


def spec_problems(spec: FunctionSpec) -> list[str]:
    """사전 항목의 **완결성**을 검사한다(07 §2-1 필드 전부와 `cases`). 문제 목록을 돌려준다."""
    problems: list[str] = []
    who = f"{spec.name!r}"
    if spec.kind not in ("function", "operator"):
        problems.append(f"{who}: kind가 function/operator가 아니다.")
    if spec.kind == "function" and not _FUNCTION_NAME.fullmatch(spec.name):
        problems.append(f"{who}: 함수 이름은 대문자 영문·숫자·밑줄·점이어야 한다.")
    if spec.kind == "operator" and (not spec.symbol or spec.syntax not in ("infix", "prefix")):
        problems.append(f"{who}: 연산자는 symbol과 syntax(infix/prefix)가 필요하다.")
    if spec.kind == "operator" and spec.level is None:
        problems.append(f"{who}: 연산자는 level이 필요하다.")
    if not spec.signature:
        problems.append(f"{who}: signature가 비었다.")
    for index, param in enumerate(spec.signature):
        if param.type not in (*TYPES, TYPE_VARIABLE):
            problems.append(f"{who}: 인수 {param.name!r}의 type이 올바르지 않다.")
        if param.repeat and index != len(spec.signature) - 1:
            problems.append(f"{who}: 반복 인수는 마지막이어야 한다.")
        if param.allowed is not None and (
            param.type != TYPE_VARIABLE or not param.allowed <= set(TYPES)
        ):
            problems.append(f"{who}: allowed는 type T에만, 4종 안에서 쓴다.")
        if param.const is not None and param.const.kind not in ("integer", "text"):
            problems.append(f"{who}: const.kind가 올바르지 않다.")
    if spec.returns not in (*TYPES, TYPE_VARIABLE):
        problems.append(f"{who}: returns가 올바르지 않다.")
    if spec.returns == TYPE_VARIABLE and not any(p.type == TYPE_VARIABLE for p in spec.signature):
        problems.append(f"{who}: returns가 T인데 T 인수가 없다.")
    if spec.null_policy not in NULL_POLICIES:
        problems.append(f"{who}: null_policy가 올바르지 않다.")
    for rule in spec.error_when:
        if rule.code not in CELL_ERROR_MESSAGES_KO:
            problems.append(f"{who}: 알 수 없는 오류 코드 {rule.code!r}.")
        if not callable(rule.when):
            problems.append(f"{who}: error_when 조건이 호출 가능하지 않다.")
    implementations = [spec.to_sql, spec.to_sql_custom, spec.rewrite]
    if sum(1 for item in implementations if item is not None) != 1:
        problems.append(f"{who}: to_sql, to_sql_custom, rewrite 중 정확히 하나가 필요하다.")
    if (spec.null_policy == "custom") != (spec.to_sql_custom is not None):
        problems.append(f"{who}: null_policy=custom은 to_sql_custom과 함께여야 한다.")
    if spec.rewrite is not None and spec.error_when:
        problems.append(f"{who}: rewrite 항목은 error_when을 쓰지 않는다.")
    if not spec.excel_diff.strip():
        problems.append(f"{who}: excel_diff가 비었다(차이가 없으면 '같음'이라고 쓴다).")
    if not spec.help_ko.strip():
        problems.append(f"{who}: help_ko가 비었다.")
    problems += _case_problems(spec)
    return problems


def _case_problems(spec: FunctionSpec) -> list[str]:
    who = f"{spec.name!r}"
    problems: list[str] = []
    cases = spec.cases
    if not cases:
        return [f"{who}: cases가 비었다(시험 사례는 필수)."]
    for case in cases:
        if case.expect not in (OK, ERROR, REJECT):
            problems.append(f"{who}: 사례 {case.expression!r}의 expect가 올바르지 않다.")
        if case.expect != OK and not case.error:
            problems.append(f"{who}: 사례 {case.expression!r}에 기대 오류 코드가 없다.")
        if case.expect == ERROR and case.error not in CELL_ERROR_MESSAGES_KO:
            problems.append(f"{who}: 사례 {case.expression!r}의 셀 오류 코드가 올바르지 않다.")
        for column_type in case.cols.values():
            if column_type not in ("number", "text", "date", "boolean", "choice"):
                problems.append(f"{who}: 사례 {case.expression!r}의 열 종류가 올바르지 않다.")
        for column_name in case.row:
            if column_name not in case.cols:
                problems.append(f"{who}: 사례 {case.expression!r}의 값이 선언되지 않은 열이다.")
    if not any(c.expect == OK for c in cases):
        problems.append(f"{who}: 정상 값 사례(ok)가 하나도 없다.")
    for rule in spec.error_when:
        if not any(c.expect == ERROR and c.error == rule.code for c in cases):
            problems.append(f"{who}: 오류 {rule.code}를 확인하는 사례(err)가 없다.")
    if (
        spec.null_policy == "propagate"
        and spec.rewrite is None
        and not any(c.expect == OK and c.value is None and c.cols for c in cases)
    ):
        problems.append(f"{who}: 빈 값이 전파되는 사례(열 값 없음 -> 빈 값)가 없다.")
    if any(p.const is not None for p in spec.signature) and not any(
        c.expect == REJECT for c in cases
    ):
        problems.append(f"{who}: 상수 조건을 어기면 거부되는 사례(reject)가 없다.")
    return problems


@dataclass
class FunctionRegistry:
    """함수 사전. `default_registry()`가 FU-1 세트를 채운 새 등록부를 돌려준다."""

    _specs: dict[str, FunctionSpec] = field(default_factory=dict)

    def register(self, spec: FunctionSpec) -> FunctionSpec:
        """항목을 등록한다. 완결성 검사를 통과해야 하고 이름이 겹치면 거부한다."""
        problems = spec_problems(spec)
        if problems:
            raise RegistryError("; ".join(problems))
        if spec.name in self._specs:
            raise RegistryError(f"{spec.name!r}은(는) 이미 등록되어 있다.")
        self._specs[spec.name] = spec
        return spec

    def copy(self) -> FunctionRegistry:
        return FunctionRegistry(dict(self._specs))

    def get(self, name: str) -> FunctionSpec | None:
        """이름(대문자)으로 찾는다. 연산자 이름(`+`, `neg` 등)도 같은 방식으로 찾는다."""
        return self._specs.get(name)

    def get_function(self, name: str) -> FunctionSpec | None:
        """사용자가 `이름(…)`으로 부를 수 있는 함수만 찾는다(대소문자 무시)."""
        spec = self._specs.get(name.upper())
        return spec if spec is not None and spec.kind == "function" else None

    def specs(self) -> list[FunctionSpec]:
        return list(self._specs.values())

    def function_names(self) -> list[str]:
        return sorted(s.name for s in self._specs.values() if s.kind == "function")

    def completeness_problems(self) -> list[str]:
        """등록된 모든 항목을 다시 검사한다(시험이 부른다)."""
        return [p for spec in self._specs.values() for p in spec_problems(spec)]

    def describe(self) -> list[dict[str, str]]:
        """05 D1 `functions[]`: `{name, signature, returns, help_ko, excel_diff}`.

        사전에서 자동 생성한다.
        """
        return [
            {
                "name": _display_name(spec),
                "signature": describe_signature(spec),
                "returns": describe_returns(spec),
                "help_ko": spec.help_ko,
                "excel_diff": spec.excel_diff,
            }
            for spec in self._specs.values()
        ]
