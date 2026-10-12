"""함수 사전(07 §2): 항목 완결성 검사와 "함수 추가 = 항목 1개 + cases" 증명. DB 없이 실행한다."""

from dataclasses import replace

import pytest
import sqlalchemy as sa

from app.formula import (
    ColumnInfo,
    FunctionRegistry,
    FunctionSpec,
    build_default_registry,
    compile_formula,
    get_default_registry,
    render_text,
)
from app.formula.cases import err, ok, reject
from app.formula.literals import NUMBER, TEXT
from app.formula.registry import (
    ConstRule,
    ErrorRule,
    Param,
    RegistryError,
    describe_returns,
    describe_signature,
    spec_problems,
)
from tests.formula_helpers import standard_columns
from tests.formula_runner import evaluate_case

# 07 §2-2의 FU-1 함수 세트(연산자는 기호로).
FU1_FUNCTIONS = {
    "IF", "AND", "OR", "NOT", "IFERROR", "ROUND", "ROUNDUP", "ROUNDDOWN", "ABS", "MIN", "MAX",
    "SUM", "LEFT", "RIGHT", "LEN", "TRIM", "YEAR", "MONTH", "DATE", "SUMTAG",
}  # fmt: skip
FU1_OPERATORS = {"+", "-", "*", "/", "=", "<>", "<", "<=", ">", ">=", "&", "neg"}


def test_default_registry_has_exactly_the_fu1_function_set():
    registry = get_default_registry()
    assert set(registry.function_names()) == FU1_FUNCTIONS
    operators = {s.name for s in registry.specs() if s.kind == "operator"}
    assert operators == FU1_OPERATORS
    assert len(registry.specs()) == len(FU1_FUNCTIONS) + len(FU1_OPERATORS)


def test_every_entry_is_complete():
    assert get_default_registry().completeness_problems() == []


def test_every_entry_has_all_fields_of_07_2_1():
    for spec in get_default_registry().specs():
        assert spec.name and spec.signature and spec.returns
        assert spec.null_policy in {"propagate", "skip", "custom"}
        assert spec.excel_diff.strip() and spec.help_ko.strip()
        assert len(spec.cases) >= 4, f"{spec.name}: cases가 너무 적다"
        # to_sql / to_sql_custom / rewrite 중 정확히 하나
        assert sum(x is not None for x in (spec.to_sql, spec.to_sql_custom, spec.rewrite)) == 1
        for rule in spec.error_when:
            assert callable(rule.when) and rule.code in {"E1", "E2", "E3"}


def test_case_counts_per_function_are_reported_and_cover_every_function():
    counts = {s.name: len(s.cases) for s in get_default_registry().specs()}
    assert min(counts.values()) >= 4
    # K6 핵심 함수 전부에 사례가 있다.
    for name in FU1_FUNCTIONS | FU1_OPERATORS:
        assert counts[name] >= 4, name


def test_fu1_null_policy_never_uses_skip_and_min_max_sum_propagate():
    registry = get_default_registry()
    assert all(s.null_policy != "skip" for s in registry.specs())
    for name in ("MIN", "MAX", "SUM", "SUMTAG"):
        assert registry.get(name).null_policy == "propagate"
    assert {registry.get(n).null_policy for n in ("IF", "IFERROR")} == {"custom"}


def test_error_codes_per_function_match_07_2_2():
    registry = get_default_registry()
    codes = {s.name: tuple(r.code for r in s.error_when) for s in registry.specs() if s.error_when}
    assert codes == {"/": ("E1",), "LEFT": ("E2",), "RIGHT": ("E2",), "DATE": ("E3",)}


def test_function_lookup_is_case_insensitive_but_operators_are_not_callable():
    registry = get_default_registry()
    assert registry.get_function("round").name == "ROUND"
    assert registry.get_function("+") is None
    assert registry.get_function("neg") is None
    assert registry.get_function("NEG") is None
    assert registry.get("neg").kind == "operator"


def test_describe_matches_the_d1_contract_and_is_generated_from_the_registry():
    entries = get_default_registry().describe()
    assert len(entries) == len(get_default_registry().specs())
    for entry in entries:
        assert set(entry) == {"name", "signature", "returns", "help_ko", "excel_diff"}
        assert all(isinstance(v, str) and v for v in entry.values())
    by_name = {e["name"]: e for e in entries}
    assert by_name["ROUND"]["signature"] == "ROUND(수, 자릿수)"
    assert by_name["MIN"]["signature"] == "MIN(수, 수, 수…)"
    assert by_name["+"]["signature"] == "수 + 수"
    assert by_name["IF"]["returns"] == "인수와 같은 종류"
    assert by_name["DATE"]["returns"] == "날짜"
    assert by_name["-(부호)"]["signature"] == "-수"
    assert "엑셀" in by_name["IFERROR"]["excel_diff"] or "빈 값" in by_name["IFERROR"]["excel_diff"]


def test_describe_helpers():
    spec = get_default_registry().get("LEFT")
    assert describe_signature(spec) == "LEFT(글자, 개수)"
    assert describe_returns(spec) == "글자"


# --- 완결성 검사가 결함을 잡는다 ----

_GOOD = FunctionSpec(
    name="DOUBLE",
    signature=(Param("수", NUMBER),),
    returns=NUMBER,
    null_policy="propagate",
    native_null=True,
    to_sql=lambda ctx, a: a[0].value * ctx.lit.number(2),
    excel_diff="같음",
    help_ko="숫자를 두 배로 만듭니다.",
    cases=(
        ok("DOUBLE(2)", 4),
        ok("DOUBLE([a])", 6, cols={"a": "number"}, row={"a": 3}),
        ok("DOUBLE([a])", None, cols={"a": "number"}, row={}),
        reject('DOUBLE("a")', "ARG_TYPE"),
    ),
)


def test_good_temporary_spec_is_complete():
    assert spec_problems(_GOOD) == []


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        ({"help_ko": " "}, "help_ko"),
        ({"excel_diff": ""}, "excel_diff"),
        ({"cases": ()}, "cases"),
        ({"cases": (reject("DOUBLE(1, 2)", "ARG_COUNT"),)}, "정상 값 사례"),
        ({"cases": (ok("DOUBLE(2)", 4), reject('DOUBLE("a")', "ARG_TYPE"))}, "빈 값이 전파"),
        ({"name": "double"}, "대문자"),
        ({"name": "2X"}, "대문자"),
        ({"signature": ()}, "signature"),
        ({"returns": "list"}, "returns"),
        ({"returns": "T"}, "T 인수가 없다"),
        ({"null_policy": "maybe"}, "null_policy"),
        ({"null_policy": "custom"}, "to_sql_custom"),
        ({"to_sql": None}, "정확히 하나"),
        ({"rewrite": lambda node, tags: node}, "정확히 하나"),
        ({"kind": "macro"}, "kind"),
        ({"kind": "operator"}, "symbol"),
        (
            {"error_when": (ErrorRule("E9", lambda ctx, a: a[0].value > 0),)},
            "알 수 없는 오류 코드",
        ),
        (
            {"error_when": (ErrorRule("E1", lambda ctx, a: a[0].value > 0),)},
            "오류 E1를 확인하는 사례",
        ),
        (
            {
                "signature": (Param("수", NUMBER, const=ConstRule("integer", 0, 5)),),
                "cases": _GOOD.cases[:3],
            },
            "reject",
        ),
        ({"signature": (Param("수", NUMBER, repeat=True), Param("수", NUMBER))}, "마지막"),
        ({"signature": (Param("수", "list"),)}, "type"),
        (
            {"cases": (*_GOOD.cases, ok("DOUBLE([z])", 1, cols={"a": "number"}, row={"z": 1}))},
            "선언되지 않은 열",
        ),
        ({"cases": (*_GOOD.cases, ok("DOUBLE([a])", 1, cols={"a": "money"}))}, "열 종류"),
    ],
)
def test_completeness_check_catches_defects(change, fragment):
    problems = spec_problems(replace(_GOOD, **change))
    assert any(fragment in p for p in problems), problems


def test_register_rejects_incomplete_and_duplicate_entries():
    registry = build_default_registry()
    with pytest.raises(RegistryError):
        registry.register(replace(_GOOD, cases=()))
    registry.register(_GOOD)
    with pytest.raises(RegistryError, match="이미 등록"):
        registry.register(_GOOD)
    with pytest.raises(RegistryError, match="이미 등록"):
        registry.register(replace(_GOOD, name="ROUND"))


# --- 함수 추가 = 항목 1개 + cases (파서·C0·변환기 수정 없음) ----


def _registry_with_double() -> FunctionRegistry:
    registry = build_default_registry()
    registry.register(_GOOD)
    return registry


def test_temporary_function_works_end_to_end_without_touching_engine_code():
    registry = _registry_with_double()
    columns = standard_columns()
    result = compile_formula("DOUBLE([매출]) + 1", columns, registry=registry)
    assert result.ok and result.result_type == "number"
    assert result.functions_used == {"DOUBLE", "+"}
    assert result.ast is not None
    assert render_text(result.ast, columns, registry) == "DOUBLE([매출]) + 1"
    # 이름이 사전에 없는 기본 등록부는 영향을 받지 않는다.
    assert compile_formula("DOUBLE([매출])", columns).issues[0].code == "UNKNOWN_FUNCTION"
    # 도움말은 사전에서 자동 생성된다.
    assert any(e["name"] == "DOUBLE" for e in registry.describe())
    # 타입·인수 개수 검사도 사전의 signature로 동작한다(C0 수정 없음).
    assert compile_formula('DOUBLE("a")', columns, registry=registry).issues[0].code == "ARG_TYPE"
    assert compile_formula("DOUBLE(1, 2)", columns, registry=registry).issues[0].code == "ARG_COUNT"


def test_temporary_function_cases_run_on_the_shared_runner():
    registry = _registry_with_double()
    engine = sa.create_engine("sqlite://")
    with engine.connect() as connection:
        for case in _GOOD.cases:
            evaluate_case(connection, case, typed_cast=False, registry=registry)
    engine.dispose()


def test_framework_adds_null_and_error_handling_to_a_new_entry():
    """사전 항목은 정상 입력의 값 식과 오류 조건만 쓴다.

    빈 값 전파와 오류 칸은 프레임워크가 만든다.
    """
    ratio = FunctionSpec(
        name="RATIO",
        signature=(Param("분자", NUMBER), Param("분모", NUMBER)),
        returns=NUMBER,
        null_policy="propagate",
        native_null=True,
        self_guarded=True,
        error_when=(ErrorRule("E1", lambda ctx, a: a[1].value == ctx.lit.number(0)),),
        to_sql=lambda ctx, a: a[0].value / sa.func.nullif(a[1].value, ctx.lit.number(0)),
        excel_diff="같음",
        help_ko="분자를 분모로 나눈 비율입니다.",
        cases=(
            ok("RATIO(6, 3)", 2),
            ok("RATIO([a], [b])", None, cols={"a": "number", "b": "number"}, row={"a": 1}),
            err("RATIO([a], [b])", "E1", cols={"a": "number", "b": "number"}, row={"a": 1, "b": 0}),
        ),
    )
    registry = build_default_registry()
    registry.register(ratio)
    result = compile_formula(
        "IFERROR(RATIO([매출], [비용]), -1)", standard_columns(), registry=registry
    )
    assert result.ok and result.error is None  # IFERROR가 오류를 흡수
    assert (
        compile_formula("RATIO([매출], [비용])", standard_columns(), registry=registry).error
        is not None
    )
    bad = compile_formula("RATIO(1, 0)", standard_columns(), registry=registry)
    assert bad.ok and bad.const_probe_skipped  # 상수 부분식 검사 대상에도 자동으로 들어간다


def test_registry_copy_is_independent():
    original = build_default_registry()
    copied = original.copy()
    copied.register(_GOOD)
    assert original.get("DOUBLE") is None and copied.get("DOUBLE") is _GOOD


def test_text_type_param_and_variable_type_entries_are_supported_by_the_same_structure():
    echo = FunctionSpec(
        name="ECHO",
        signature=(Param("값", "T"),),
        returns="T",
        null_policy="propagate",
        native_null=True,
        to_sql=lambda ctx, a: a[0].value,
        excel_diff="같음",
        help_ko="값을 그대로 돌려줍니다.",
        cases=(
            ok('ECHO("a")', "a"),
            ok("ECHO([n])", None, cols={"n": "number"}, row={}),
            ok("ECHO(1)", 1),
        ),
    )
    registry = build_default_registry()
    registry.register(echo)
    assert compile_formula('ECHO("a") & "b"', standard_columns(), registry=registry).ok
    assert (
        compile_formula('ECHO("a") + 1', standard_columns(), registry=registry).issues[0].code
        == "ARG_TYPE"
    )
    assert (
        compile_formula("ECHO(1) + 1", standard_columns(), registry=registry).result_type
        == "number"
    )
    assert TEXT == "text" and ColumnInfo
