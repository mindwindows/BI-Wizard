"""수식 엔진(`formula`, 04 §2-1, 07). 파서(lark) -> C0 검사 -> SQLAlchemy 표현식 변환 -> 수식 보기.

이 패키지의 1단계는 **DB를 모르는 순수 로직**이다. 공개 인터페이스와 가정은 `api.py`의 독스트링,
함수 추가 방법은 `registry.py`, 상수 렌더 규칙은 `literals.py`, 문법은 `parser.py`를 본다.
"""

from app.formula.api import (
    CompileResult,
    ConstProbe,
    check_formula,
    compile_formula,
    render_text,
)
from app.formula.cases import Case
from app.formula.columns import ColumnInfo
from app.formula.errors import (
    CELL_ERROR_BY_NUMBER,
    CELL_ERROR_MESSAGES_KO,
    FormulaError,
    FormulaIssue,
)
from app.formula.functions import build_default_registry, get_default_registry
from app.formula.literals import LITERALS, Literals, render_literal_sql
from app.formula.nodes import ast_from_json, ast_hash, ast_to_json
from app.formula.parser import parse_expression
from app.formula.registry import FunctionRegistry, FunctionSpec

__all__ = [
    "CELL_ERROR_BY_NUMBER",
    "CELL_ERROR_MESSAGES_KO",
    "LITERALS",
    "Case",
    "ColumnInfo",
    "CompileResult",
    "ConstProbe",
    "FormulaError",
    "FormulaIssue",
    "FunctionRegistry",
    "FunctionSpec",
    "Literals",
    "ast_from_json",
    "ast_hash",
    "ast_to_json",
    "build_default_registry",
    "check_formula",
    "compile_formula",
    "get_default_registry",
    "parse_expression",
    "render_literal_sql",
    "render_text",
]
