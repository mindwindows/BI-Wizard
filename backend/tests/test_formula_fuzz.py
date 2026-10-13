"""무작위 수식(씨앗 고정): 어떤 입력에서도 컴파일이 예외를 내지 않고, 통과한 수식은 안전하게
렌더되며 수식 보기가 왕복한다.

DB 없이 실행한다. 실제 PostgreSQL에서의 DB 예외 0건·미리보기-뷰 일치는 `test_formula_pg.py`가 같은
생성기로 확인한다.
"""

import pytest
import sqlalchemy as sa

from app.formula import compile_formula, render_literal_sql, render_text
from app.formula.nodes import ast_from_json, ast_hash
from tests.formula_fuzz import FUZZ_COLUMNS, FormulaGenerator
from tests.test_formula_cases import _constants_outside_cast


@pytest.mark.parametrize("seed", [11, 12, 13])
def test_random_formulas_compile_render_and_roundtrip(seed):
    formulas = FormulaGenerator(seed).formulas(150)
    accepted = 0
    for expression in formulas:
        result = compile_formula(expression, FUZZ_COLUMNS)  # 예외가 나면 실패
        if not result.ok:
            assert result.issues and all(i.start >= 0 and i.end >= i.start for i in result.issues)
            continue
        accepted += 1
        error = result.error if result.error is not None else sa.cast(sa.null(), sa.SmallInteger())
        rendered = render_literal_sql(sa.select(result.value.label("v"), error.label("e")))
        assert _constants_outside_cast(rendered) == [], (expression, rendered)
        # 수식 보기 왕복, 저장 형식 왕복
        text = render_text(result.ast, FUZZ_COLUMNS)
        again = compile_formula(text, FUZZ_COLUMNS, build_sql=False)
        assert again.ok and again.ast == result.ast, (expression, text)
        restored = ast_from_json(result.ast_json)
        assert restored == result.ast and ast_hash(restored) == result.ast_hash
        # 결과 형이 하나로 정해지고, 원본 열만 읽는다
        assert result.result_type in {"number", "text", "boolean", "date"}
        assert set(result.source_columns) <= {c.id for c in FUZZ_COLUMNS}
    assert accepted >= 100
