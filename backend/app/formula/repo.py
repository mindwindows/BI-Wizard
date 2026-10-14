"""`formulas` `formula_deps` 데이터 접근(SQLAlchemy 표현식만, `text()` 금지).

트랜잭션 경계(commit/rollback)는 service가 정한다. 열 정의(`dataset_columns`)는 dataset 모듈의
것이라 읽기만 하고 쓰기는 dataset service 함수로만 한다(04 §5). 이 파일이 쓰는 정적 표는
`formulas`와 `formula_deps`뿐이다.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, insert, select, update
from sqlalchemy.orm import Session

from app.db_metadata import dataset_columns, formula_deps, formulas


@dataclass(frozen=True)
class StoredFormula:
    """`formulas` 한 줄. `ast`는 열 번호 참조 JSON이다."""

    column_id: int
    expression: str  # 보관용 원문(화면 표시에는 쓰지 않는다)
    ast: Any
    ast_hash: str


def load_formulas(session: Session, dataset_id: int) -> dict[int, StoredFormula]:
    """데이터셋의 모든 수식(열 번호 -> 저장된 수식)."""
    stmt = (
        select(formulas.c.column_id, formulas.c.expression, formulas.c.ast, formulas.c.ast_hash)
        .join(dataset_columns, dataset_columns.c.id == formulas.c.column_id)
        .where(dataset_columns.c.dataset_id == dataset_id)
    )
    return {
        int(r.column_id): StoredFormula(int(r.column_id), r.expression, r.ast, r.ast_hash)
        for r in session.execute(stmt)
    }


def reference_candidates(session: Session) -> list[tuple[int, int, Any]]:
    """`REF`가 들어 있을 수 있는 저장 수식: (데이터셋 번호, 열 번호, AST JSON).

    사전 거름은 보관용 원문에 `REF`가 든 행뿐이다(대소문자 무시, 정확한 판정은 AST로 한다). 읽기
    전용 질의 하나이며 새 표·열이 없다(05 §2-8 R6 방안 (a)).
    """
    stmt = (
        select(dataset_columns.c.dataset_id, formulas.c.column_id, formulas.c.ast)
        .join(dataset_columns, dataset_columns.c.id == formulas.c.column_id)
        .where(dataset_columns.c.kind == "formula", formulas.c.expression.icontains("REF"))
        .order_by(dataset_columns.c.dataset_id, formulas.c.column_id)
    )
    return [(int(r.dataset_id), int(r.column_id), r.ast) for r in session.execute(stmt)]


def load_deps(session: Session, dataset_id: int) -> dict[int, tuple[int, ...]]:
    """데이터셋의 의존(계산 열 -> 직접 읽는 열 번호, 오름차순)."""
    stmt = (
        select(formula_deps.c.column_id, formula_deps.c.depends_on_column_id)
        .join(dataset_columns, dataset_columns.c.id == formula_deps.c.column_id)
        .where(dataset_columns.c.dataset_id == dataset_id)
        .order_by(formula_deps.c.column_id, formula_deps.c.depends_on_column_id)
    )
    found: dict[int, list[int]] = {}
    for r in session.execute(stmt):
        found.setdefault(int(r.column_id), []).append(int(r.depends_on_column_id))
    return {k: tuple(v) for k, v in found.items()}


def insert_formula(session: Session, stored: StoredFormula) -> None:
    session.execute(
        insert(formulas).values(
            column_id=stored.column_id,
            expression=stored.expression,
            ast=stored.ast,
            ast_hash=stored.ast_hash,
        )
    )


def update_formula(session: Session, stored: StoredFormula) -> None:
    session.execute(
        update(formulas)
        .where(formulas.c.column_id == stored.column_id)
        .values(expression=stored.expression, ast=stored.ast, ast_hash=stored.ast_hash)
    )


def replace_deps(session: Session, column_id: int, deps: Collection[int]) -> None:
    """한 계산 열의 의존 목록을 통째로 다시 쓴다(SUMTAG 펼침이 바뀌면 달라진다)."""
    session.execute(delete(formula_deps).where(formula_deps.c.column_id == column_id))
    for dep in sorted(set(deps)):
        session.execute(insert(formula_deps).values(column_id=column_id, depends_on_column_id=dep))
