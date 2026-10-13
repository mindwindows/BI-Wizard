"""Skill `dataset-definition`의 "수식 한도에 걸릴 때 나오는 쉬운 말" 표가 코드 문구와 같은지 본다.

표와 `errors.py`의 문구, 한도 숫자가 어긋나면 실패한다(03b 21-1).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.formula import cycles, nodes, parser
from app.formula.analyze import MAX_EXPANDED_NODES
from app.formula.convert import MAX_SQL_NODES
from app.formula.errors import CELL_ERROR_MESSAGES_KO, make_issue
from app.formula.literals import MAX_NUMBER_DIGITS, MAX_TEXT_CONSTANT_LENGTH, text_constant_problem

SKILL = Path(__file__).resolve().parents[2] / "skills" / "dataset-definition" / "SKILL.md"
HEADING = "### 수식 한도에 걸릴 때 나오는 쉬운 말"

pytestmark = pytest.mark.skipif(
    not SKILL.parent.parent.is_dir(),
    reason="저장소 skills/ 폴더가 없는 환경(backend만 복사한 이미지)",
)


def _rows() -> dict[str, tuple[str, str]]:
    """표의 '한도' 칸 -> (코드 칸, 문구 칸)."""
    text = SKILL.read_text(encoding="utf-8")
    assert HEADING in text, "Skill에 한도 문구 절이 없다"
    section = text.split(HEADING, 1)[1].split("\n## ", 1)[0]
    rows = {}
    for line in section.splitlines():
        if line.startswith("| ") and not line.startswith(("| 한도", "| ---")):
            cells = [cell.strip() for cell in line.strip().strip("|").split(" | ")]
            assert len(cells) == 4, line
            rows[cells[0]] = (cells[1], cells[2])
    return rows


def _expected() -> dict[str, tuple[str, str]]:
    def message(code: str, **values) -> str:
        return f"`{make_issue(code, 0, 1, **values).message}`"

    deep = message("TOO_DEEP", max=nodes.MAX_AST_DEPTH)
    return {
        f"수식 {parser.MAX_EXPRESSION_LENGTH:,}자": (
            "`TOO_LONG`",
            message("TOO_LONG", max=parser.MAX_EXPRESSION_LENGTH, length=2500),
        ),
        f"글자 상수 {MAX_TEXT_CONSTANT_LENGTH}자": (
            "`TEXT_CONSTANT_INVALID`",
            message(
                "TEXT_CONSTANT_INVALID",
                reason=text_constant_problem("a" * (MAX_TEXT_CONSTANT_LENGTH + 1)),
            ),
        ),
        f"AST 깊이 {nodes.MAX_AST_DEPTH}": ("`TOO_DEEP`", deep),
        f"항 {nodes.MAX_AST_DEPTH + 1}개 이상 덧셈": ("`TOO_DEEP`", deep),
        f"참조 사슬 {cycles.MAX_CHAIN_DEPTH}단계": (
            "`CHAIN_TOO_LONG`",
            message("CHAIN_TOO_LONG", max=cycles.MAX_CHAIN_DEPTH),
        ),
        f"펼친 노드 {MAX_EXPANDED_NODES:,}개": (
            "`TOO_MANY_NODES`",
            message("TOO_MANY_NODES", max=MAX_EXPANDED_NODES, count=2500),
        ),
        f"변환 SQL 노드 {MAX_SQL_NODES // 10_000}만": (
            "`TOO_COMPLEX`",
            message("TOO_COMPLEX"),
        ),
        f"숫자 {MAX_NUMBER_DIGITS}자리": ("`NUMBER_INVALID`", message("NUMBER_INVALID")),
        "`DATE` 범위 0001-01-01~9999-12-31": ("`E3`(셀 오류)", f"`{CELL_ERROR_MESSAGES_KO['E3']}`"),
    }


def test_limit_message_table_matches_the_code():
    assert _rows() == _expected()


def test_depth_limits_are_the_same_so_one_message_covers_both():
    assert nodes.MAX_AST_DEPTH == nodes.MAX_EXPANDED_DEPTH
