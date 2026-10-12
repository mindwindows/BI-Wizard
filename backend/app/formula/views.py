"""데이터셋 정의 -> 뷰 `dv_<번호>`(값)·`de_<번호>`(오류 판정) 정의(07 §3-1, §8, 06 §3-4).

순수한 계산이다(DB 접속 없음). 실행은 `ddl.create_view`가 한다.

- `dv_<번호>`: `team`(팀 코드 상수, 계산 열이 없어도 있다), `row_id`, 이어서 열 번호 오름차순으로
  원본 열(`ds_<번호>`의 열 그대로)과 계산 열(값 식). 오류 칸의 값은 NULL이다.
- `de_<번호>`: `row_id`, 이어서 계산 열마다 `e_<열 번호>`(smallint, NULL = 정상 또는 빈 값, 값 = 셀
  오류 코드 1~3).
- 정의 해시: 두 SELECT를 리터럴 렌더러로 그린 글자의 sha256이다. 함수 사전·규칙이 바뀌어 SQL이
  달라지면 해시가 달라져 시작할 때 해당 뷰만 다시 만들어진다(07 §8). 표시 이름은 뷰 열이 번호라
  해시에 영향이 없다.
- 완화책 ③(07 §4-3)의 확인 질의는 뷰 정의에 실제로 들어간 글자 상수(팀 코드 포함)를 모아 만든다.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import pg8000
from sqlalchemy.sql.expression import TableClause

from app.dataset.service import DefinitionView
from app.db_metadata import DYNAMIC_SCHEMA
from app.ddl import column_name, dataset_table_name, error_column_name, error_view_name, view_name
from app.formula.api import CompileResult, ConstProbe, compile_formula
from app.formula.columns import ColumnInfo
from app.formula.errors import FormulaIssue
from app.formula.literals import LITERALS, render_literal_sql
from app.formula.nodes import ast_from_json
from app.formula.repo import StoredFormula
from app.formula.textview import render_text

HASH_VERSION = "view-v1"
_ECHO_CHUNK = 50  # 확인 SELECT 하나에 담는 글자 상수 수

_RAW_SQL_TYPES: dict[str, type[sa.types.TypeEngine]] = {
    "text": sa.Text,
    "choice": sa.Text,
    "number": sa.Numeric,
    "date": sa.Date,
    "boolean": sa.Boolean,
}


class FormulaCompileFailure(Exception):
    """저장된 수식이나 편집 중인 수식을 컴파일하지 못했다. 어느 열인지와 문제 목록을 담는다."""

    def __init__(self, column_id: int | None, column_name_: str, issues: Sequence[FormulaIssue]):
        super().__init__("수식 컴파일 실패")
        self.column_id = column_id
        self.column_name = column_name_
        self.issues = tuple(issues)


@dataclass(frozen=True)
class ViewPlan:
    """뷰 두 개의 정의와 해시, 확인 질의."""

    dataset_id: int
    results: Mapping[int, CompileResult]  # 계산 열 번호 -> 컴파일 결과
    dv: sa.Select
    de: sa.Select
    def_hash: str
    echo_dv: tuple[tuple[sa.Select, tuple[str, ...]], ...]
    echo_de: tuple[tuple[sa.Select, tuple[str, ...]], ...]


def source_table(defn: DefinitionView) -> TableClause:
    """`ds_<번호>`를 가리키는 가벼운 표 설명(원본 열만, 열 이름은 열 번호로만 만든다)."""
    columns = [
        sa.column(column_name(c.id), _RAW_SQL_TYPES[c.type]())
        for c in defn.columns
        if c.kind == "raw"
    ]
    return sa.table(
        dataset_table_name(defn.dataset_id),
        sa.column("row_id", sa.BigInteger),
        *columns,
        schema=DYNAMIC_SCHEMA,
    )


def source_columns(defn: DefinitionView, ds: TableClause) -> dict[int, Any]:
    return {c.id: ds.c[column_name(c.id)] for c in defn.columns if c.kind == "raw"}


def build_column_infos(
    defn: DefinitionView, stored: Mapping[int, StoredFormula]
) -> list[ColumnInfo]:
    """수식 엔진이 보는 열 목록. 계산 열은 저장된 AST를 복원해 붙인다(번호 오름차순)."""
    infos: list[ColumnInfo] = []
    for column in defn.columns:
        ast = None
        if column.kind == "formula" and column.id in stored:
            try:
                ast = ast_from_json(stored[column.id].ast)
            except ValueError:
                ast = None  # 깨진 저장 수식: compile_all이 문제로 알린다
        infos.append(
            ColumnInfo(
                id=column.id,
                name=column.display_name,
                type=column.type,
                kind=column.kind,
                tag=column.tag,
                formula=ast,
            )
        )
    return infos


def compile_all(
    infos: Sequence[ColumnInfo],
    sources: Mapping[int, Any],
    probe: ConstProbe | None,
) -> dict[int, CompileResult]:
    """모든 계산 열을 저장된 AST에서 다시 컴파일한다(열 이름·태그·참조한 수식의 변화를 반영).

    저장된 AST를 현재 열 이름으로 풀어 쓴 글자(`render_text`)를 다시 읽어 컴파일하므로 왕복이
    깨지면(시험이 확인) 여기서 알 수 있다. 하나라도 실패하면 `FormulaCompileFailure`다.
    """
    results: dict[int, CompileResult] = {}
    for info in infos:
        if not info.is_formula:
            continue
        if info.formula is None:
            raise FormulaCompileFailure(
                info.id,
                info.name,
                [FormulaIssue("FORMULA_MISSING", "이 열의 수식이 저장되어 있지 않습니다.", 0, 0)],
            )
        text = render_text(info.formula, infos)
        result = compile_formula(
            text, infos, column_id=info.id, source_columns=sources, const_probe=probe
        )
        if not result.ok:
            raise FormulaCompileFailure(info.id, info.name, result.issues)
        results[info.id] = result
    return results


def text_constants(statement: sa.Select) -> list[str]:
    """SELECT에 실제로 들어간 글자 상수(중복 제거, 정렬)."""
    params = statement.compile(dialect=pg8000.dialect()).params
    return sorted({v for v in params.values() if isinstance(v, str)})


def echo_selects(
    values: Sequence[str],
) -> tuple[tuple[sa.Select, tuple[str, ...]], ...]:
    """완화책 ③ 확인 질의: 글자 상수만 담은 SELECT와 기대 값(입력과 같아야 한다)."""
    chunks = [values[i : i + _ECHO_CHUNK] for i in range(0, len(values), _ECHO_CHUNK)]
    return tuple(
        (
            sa.select(*[LITERALS.text(v).label(f"k{i}") for i, v in enumerate(chunk)]),
            tuple(chunk),
        )
        for chunk in chunks
    )


def build_plan(
    defn: DefinitionView,
    ds: TableClause,
    results: Mapping[int, CompileResult],
) -> ViewPlan:
    """뷰 두 개의 SELECT와 정의 해시를 만든다."""
    dv_columns: list[Any] = [
        LITERALS.text(defn.team_code).label("team"),
        ds.c.row_id.label("row_id"),
    ]
    de_columns: list[Any] = [ds.c.row_id.label("row_id")]
    for column in defn.columns:  # 번호 오름차순
        label = column_name(column.id)
        if column.kind == "raw":
            dv_columns.append(ds.c[label].label(label))
            continue
        result = results[column.id]
        assert result.value is not None  # noqa: S101 - compile_all은 SQL까지 만든다
        dv_columns.append(result.value.label(label))
        error = result.error if result.error is not None else LITERALS.null("smallint")
        de_columns.append(error.label(error_column_name(column.id)))
    dv = sa.select(*dv_columns).select_from(ds)
    de = sa.select(*de_columns).select_from(ds)
    payload = json.dumps(
        [
            HASH_VERSION,
            view_name(defn.dataset_id),
            render_literal_sql(dv),
            error_view_name(defn.dataset_id),
            render_literal_sql(de),
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return ViewPlan(
        dataset_id=defn.dataset_id,
        results=results,
        dv=dv,
        de=de,
        def_hash=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        echo_dv=echo_selects(text_constants(dv)),
        echo_de=echo_selects(text_constants(de)),
    )
