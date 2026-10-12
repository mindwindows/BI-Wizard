"""수식 엔진을 실제 PostgreSQL에서 실행한다(`pg_app_engine`: tmpfs 시험 DB의 `bi_app` 연결).

환경이 없으면 건너뛴다(`REQUIRE_PG=1`이면 실패, `skills/permission-management/SKILL.md` 8절).
1단계의 SQLite
시험이 넘긴 PostgreSQL 전용 함수(`make_date`·`regexp_replace`·`btrim`·`least` 등)의 `cases`를
여기서 모두
평가하고, 미리보기(바인드)와 뷰(리터럴 렌더)의 결과가 같은지 확인한다.
"""

import sqlalchemy as sa

from app.formula import compile_formula, get_default_registry
from app.formula.cases import REJECT
from tests.formula_helpers import standard_columns
from tests.formula_injection_cases import SAFE_RENDER_CASES, formula_of
from tests.formula_runner import differential_check, run_cases_on


def test_all_dictionary_cases_evaluate_on_postgresql(pg_app_engine):
    with pg_app_engine.connect() as connection:
        total, failures = run_cases_on(connection)
    assert total >= 200
    assert failures == [], "\n".join(failures)


def test_preview_and_view_renderings_agree_for_every_case(pg_app_engine):
    registry = get_default_registry()
    problems: list[str] = []
    checked = 0
    with pg_app_engine.connect() as connection:
        for spec in registry.specs():
            for case in spec.cases:
                if case.expect == REJECT:
                    continue
                checked += 1
                try:
                    message = differential_check(connection, case)
                except Exception as exc:
                    connection.rollback()
                    message = f"DB 예외 {type(exc).__name__}: {exc}"
                if message:
                    problems.append(f"{spec.name} | {case.expression} | {message}"[:300])
    assert checked >= 150
    assert problems == [], "\n".join(problems)


def test_injection_attempts_round_trip_as_one_string_on_postgresql(pg_app_engine):
    from app.formula import render_literal_sql

    with pg_app_engine.connect() as connection:
        for name, text in SAFE_RENDER_CASES.items():
            result = compile_formula(formula_of(text), standard_columns())
            assert result.ok, name
            rendered = render_literal_sql(sa.select(result.value.label("v")))
            assert connection.exec_driver_sql(rendered).scalar_one() == text, name
            assert connection.execute(sa.select(result.value)).scalar_one() == text, name


def test_random_formulas_never_raise_database_errors_and_agree(pg_app_engine):
    """무작위 수식 x 경계 값 행.

    DB 예외 0건, 미리보기(바인드)와 뷰(리터럴) 결과 일치, 값과 오류 코드 동시 존재 0건.
    """
    from tests.formula_fuzz import FUZZ_COLUMNS, FormulaGenerator, fuzz_rows
    from tests.formula_runner import fuzz_check

    rows = fuzz_rows(7)[:6]
    with pg_app_engine.connect() as connection:
        expressions = FormulaGenerator(21).formulas(70)
        accepted, _rejected, problems = fuzz_check(connection, expressions, rows, FUZZ_COLUMNS)
    assert accepted >= 45
    assert problems == [], "\n".join(problems[:10])
