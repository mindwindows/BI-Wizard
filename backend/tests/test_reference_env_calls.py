"""`REF` 환경(`ReferenceEnv`) 전달 시험(07 §3-2 "컴파일 호출 지점 6곳", DB 없음).

- `formula` 패키지 안의 `compile_formula`·`check_formula`·`compile_all` 호출은 모두 `env=`를 넘긴다
  (AST 검사). 호출 지점을 빠뜨리면 조용히 `REF_UNKNOWN`이 나오지 않고 `REF`를 만나는 즉시
  `RuntimeError`로 크게 실패한다.
- `REF`의 C0 오류(위치·코드), 상수 부분식 제외(`reads_row`), 항목 번호 정수 상수 렌더러 규칙.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.formula import (
    ColumnInfo,
    ReferenceEnv,
    check_formula,
    compile_formula,
    get_default_registry,
    render_literal_sql,
    render_text,
)
from app.formula.errors import FormulaIssue
from app.formula.literals import LITERALS, LiteralError
from app.formula.registry import FunctionRegistry, FunctionSpec, Param, spec_problems
from app.formula.views import compile_all
from tests.formula_helpers import SqliteProbe

FORMULA = Path(__file__).resolve().parent.parent / "app" / "formula"
GUARDED = {"compile_formula", "check_formula", "compile_all"}

COLUMNS = [
    ColumnInfo(1, "일자", "date"),
    ColumnInfo(2, "사용량", "number"),
    ColumnInfo(3, "메모", "text"),
]
ENV = ReferenceEnv({"전기요금": 7, "수도요금": 9}, base_date_column_id=1)


def calls_of(path: Path) -> list[tuple[str, ast.Call]]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in GUARDED:
                found.append((name, node))
    return found


def test_every_compile_call_in_the_formula_package_passes_env():
    seen: dict[str, int] = {}
    for path in sorted(FORMULA.glob("*.py")):
        for name, node in calls_of(path):
            where = f"{path.name} 줄 {node.lineno}: {name}()"
            assert not node.args[2:] or name == "compile_all", (
                f"{where}: 위치 인수로 env를 넘기지 않는다"
            )
            for keyword in node.keywords:
                assert keyword.arg is not None, f"{where}: **kwargs로 env를 숨기지 않는다"
            env = [k for k in node.keywords if k.arg == "env"]
            assert len(env) == 1, f"{where}에 env= 가 없다"
            value = env[0].value
            assert not (isinstance(value, ast.Constant) and value.value is None), (
                f"{where}: env=None 상수는 REF를 막는 우회다"
            )
            seen[path.name] = seen.get(path.name, 0) + 1
    # 07 §3-2의 호출 지점이 실제로 있다(정확한 횟수는 단정하지 않는다: 늘어도 위 검사가 지킨다)
    for needed in ("service.py", "hook.py", "reconcile.py", "views.py", "api.py"):
        assert seen.get(needed, 0) >= 1, f"{needed}에 컴파일 호출이 없다(호출 지점이 사라졌다)"
    assert seen["service.py"] >= 4  # check·preview·save·view_formula


def test_the_six_call_sites_build_their_env_with_the_shared_helper():
    for name in ("service.py", "hook.py", "reconcile.py"):
        source = (FORMULA / name).read_text(encoding="utf-8")
        assert "load_env" in source, name
    env_module = (FORMULA / "refenv.py").read_text(encoding="utf-8")
    assert "item_ids_by_name" in env_module and "base_date_column_id" in env_module


def test_compile_all_requires_the_env_keyword():
    parameter = inspect.signature(compile_all).parameters["env"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty  # 기본값이 없어 빠뜨리면 TypeError
    with pytest.raises(TypeError):
        compile_all([], {}, None)  # type: ignore[call-arg]


@pytest.mark.parametrize("build_sql", [False, True])
def test_ref_without_an_environment_fails_loudly(build_sql):
    with pytest.raises(RuntimeError, match="ReferenceEnv"):
        compile_formula('REF("전기요금")', COLUMNS, build_sql=build_sql)
    with pytest.raises(RuntimeError, match="ReferenceEnv"):
        compile_formula('[사용량] * REF("전기요금") + 1', COLUMNS, build_sql=False)
    with pytest.raises(RuntimeError, match="ReferenceEnv"):
        check_formula('REF("전기요금")', COLUMNS)


def test_formulas_without_ref_do_not_need_an_environment():
    assert compile_formula("[사용량] * 2", COLUMNS, build_sql=False).ok
    assert check_formula("[사용량] + 1", COLUMNS).ok
    assert compile_formula("[사용량] * 2", COLUMNS, env=ENV, build_sql=False).ok


# --- C0 오류 ----


def issues(expression: str, env: ReferenceEnv = ENV, columns=COLUMNS) -> list[FormulaIssue]:
    return list(compile_formula(expression, columns, build_sql=False, env=env).issues)


def test_ref_ok_with_a_known_item_and_a_base_date_column():
    result = compile_formula('REF("전기요금")', COLUMNS, build_sql=False, env=ENV)
    assert result.ok and result.result_type == "number"
    assert result.deps == ()  # formula_deps에 간선을 만들지 않는다
    assert "REF" in result.functions_used


def test_unknown_item_points_at_the_argument_and_suggests_close_names():
    (issue,) = issues('REF("전기요금_B팀")')
    assert (issue.code, issue.start, issue.end) == ("REF_UNKNOWN", 4, 13)
    assert "'전기요금_B팀' 기준값 항목을 찾을 수 없습니다" in issue.message
    assert "비슷한 이름" in issue.message and "'전기요금'" in issue.message
    (far,) = issues('REF("zzzzzzzzzz")')
    assert far.code == "REF_UNKNOWN" and "비슷한 이름" not in far.message


def test_missing_base_date_column_points_at_the_whole_call():
    env = ReferenceEnv({"전기요금": 7}, base_date_column_id=None)
    (issue,) = issues('REF("전기요금")', env)
    assert (issue.code, issue.start, issue.end) == ("BASE_DATE_REQUIRED", 0, 11)
    assert "기준 날짜 열이 있는 데이터셋에서만" in issue.message
    assert "데이터셋 설정" in issue.message


def test_both_errors_are_reported_together():
    env = ReferenceEnv({}, base_date_column_id=None)
    codes = sorted(i.code for i in issues('REF("없음")', env))
    assert codes == ["BASE_DATE_REQUIRED", "REF_UNKNOWN"]


@pytest.mark.parametrize(
    "columns",
    [
        [ColumnInfo(1, "일자", "text"), ColumnInfo(2, "사용량", "number")],  # date가 아닌 열
        [ColumnInfo(2, "사용량", "number")],  # 번호는 있는데 열이 없다
        [ColumnInfo(1, "일자", "date", kind="formula"), ColumnInfo(2, "사용량", "number")],
    ],
    ids=["not-date", "missing-column", "calculated-column"],
)
def test_a_base_date_column_that_is_not_a_raw_date_column_counts_as_missing(columns):
    codes = [i.code for i in issues('REF("전기요금")', ENV, columns)]
    assert codes == ["BASE_DATE_REQUIRED"]


@pytest.mark.parametrize(
    ("expression", "code"),
    [
        ("REF()", "ARG_COUNT"),
        ('REF("전기요금", 2026)', "ARG_COUNT"),
        ('REF("전기요금", "수도요금")', "ARG_COUNT"),
        ("REF(1)", "ARG_TYPE"),
        ("REF(TRUE)", "ARG_TYPE"),
        ("REF([일자])", "ARG_TYPE"),
        ("REF([메모])", "CONST_REQUIRED"),
        ('REF("전기" & "요금")', "CONST_REQUIRED"),
        ('REF(IF(TRUE, "전기요금", "수도요금"))', "CONST_REQUIRED"),
        # 51자 이름은 항목이 될 수 없어 범위 오류와 함께 없는 이름으로도 보고된다(둘 다 정확히 단정)
        ('REF("' + "가" * 51 + '")', ["CONST_RANGE", "REF_UNKNOWN"]),
        ('REF("전기\\요금")', "TEXT_CONSTANT_INVALID"),
    ],
)
def test_argument_errors_use_the_existing_codes(expression, code):
    expected = code if isinstance(code, list) else [code]
    assert [i.code for i in issues(expression)] == expected, expression


def test_a_ref_name_is_compared_exactly_after_nfc():
    import unicodedata

    nfd = unicodedata.normalize("NFD", "전기요금")
    assert compile_formula(f'REF("{nfd}")', COLUMNS, build_sql=False, env=ENV).ok
    assert [i.code for i in issues('REF("전기요금 ")')] == ["REF_UNKNOWN"]  # 공백도 이름이다
    assert [i.code for i in issues('REF("전기요금".)')] != []  # 문법 오류


def test_ref_inside_other_functions_is_checked_too_and_text_round_trips():
    expression = 'IF([사용량] > 0, REF("전기요금"), REF("없는 이름"))'
    assert [i.code for i in issues(expression)] == ["REF_UNKNOWN"]
    ok = compile_formula('ROUND(REF("전기요금") * [사용량], 2)', COLUMNS, build_sql=False, env=ENV)
    assert ok.ok and ok.ast is not None
    text = render_text(ok.ast, COLUMNS)
    assert text == 'ROUND(REF("전기요금") * [사용량], 2)'
    again = compile_formula(text, COLUMNS, build_sql=False, env=ENV)
    assert again.ok and again.ast == ok.ast


# --- 상수 부분식이 아니다(`reads_row`) ----


def test_ref_is_never_a_constant_subexpression_so_the_constant_probe_ignores_it():
    """인수가 상수여도 행 데이터를 읽는 식이라 상수 오류 검사(DB 상수 SELECT) 대상이 아니다."""
    probe = SqliteProbe()
    try:
        for expression in ('REF("전기요금") / 0', '1 / REF("전기요금")', 'ABS(REF("전기요금"))'):
            result = compile_formula(
                expression,
                COLUMNS,
                const_probe=probe,
                source_columns={
                    1: sa.cast(sa.null(), sa.Date),
                    2: sa.cast(sa.null(), sa.Numeric),
                    3: sa.cast(sa.null(), sa.Text),
                },
                env=ENV,
            )
            assert result.ok, (expression, result.issues)  # CONSTANT_ERROR로 거부되지 않는다
    finally:
        probe.close()


def test_reference_uses_come_from_the_resolved_names_sorted_and_unique():
    result = compile_formula(
        'REF("수도요금") + REF("전기요금") + REF("수도요금")', COLUMNS, build_sql=False, env=ENV
    )
    assert [(u.item_id, u.base_column_id) for u in result.reference_uses] == [(7, 1), (9, 1)]
    assert compile_formula("[사용량]", COLUMNS, build_sql=False, env=ENV).reference_uses == ()


def test_compiled_ref_has_a_correlated_subquery_with_an_integer_constant_item_id():
    result = compile_formula(
        'REF("전기요금")',
        COLUMNS,
        env=ENV,
        source_columns={1: sa.column("c_1", sa.Date), 2: sa.column("c_2"), 3: sa.column("c_3")},
    )
    assert result.ok and result.value is not None and result.error is not None
    rendered = render_literal_sql(sa.select(result.value, result.error))
    assert "public.reference_values AS rv" in rendered
    assert "rv.item_id = CAST(7 AS INTEGER)" in rendered
    assert "EXTRACT(year FROM c_1)" in rendered and "CAST(4 AS SMALLINT)" in rendered
    assert "전기요금" not in rendered  # 이름은 SQL에 글자로 나가지 않는다(번호만)


# --- 항목 번호 정수 상수 렌더러(07 §4-1) ----


@pytest.mark.parametrize("value", [1, 7, 2**31 - 1])
def test_reference_id_renders_as_an_integer_cast(value):
    rendered = render_literal_sql(sa.select(LITERALS.reference_id(value)))
    assert rendered == f"SELECT CAST({value} AS INTEGER) AS anon_1"


@pytest.mark.parametrize("value", [0, -1, 2**31, True, False, "7", 7.0, None])
def test_reference_id_rejects_non_positive_non_integer_and_out_of_range(value):
    with pytest.raises(LiteralError):
        LITERALS.reference_id(value)  # type: ignore[arg-type]


def test_integer_bind_values_outside_the_database_range_are_rejected_when_rendering():
    from decimal import Decimal  # noqa: F401

    big = sa.cast(sa.bindparam("lit_1", 2**31, type_=sa.Integer), sa.Integer)
    with pytest.raises(LiteralError):
        render_literal_sql(sa.select(big))


# --- 사전 항목 규칙(확장점) ----


def test_ref_spec_is_complete_and_flagged_as_an_environment_function():
    spec = get_default_registry().get("REF")
    assert spec is not None and spec_problems(spec) == []
    assert spec.precheck is not None and spec.reads_row is True
    assert spec.null_policy == "custom" and spec.to_sql_custom is not None
    assert spec.returns == "number" and [p.type for p in spec.signature] == ["text"]
    assert spec.signature[0].const is not None and spec.signature[0].const.max_length == 50


def test_registry_rejects_environment_function_entries_that_break_the_rules():
    spec = get_default_registry().get("REF")
    assert spec is not None
    import dataclasses

    broken = [
        dataclasses.replace(spec, reads_row=False),  # 환경 함수는 상수 부분식이 아니다
        dataclasses.replace(
            spec, to_sql_custom=None, null_policy="propagate", to_sql=lambda c, a: None
        ),
    ]
    for item in broken:
        assert spec_problems(item), item
    assert isinstance(FunctionRegistry().copy(), FunctionRegistry) and FunctionSpec and Param
