"""수식 로직(05 §2-4 D1~D8, 07). 트랜잭션은 여기서 명시적으로 commit/rollback한다.

- 검사(D2)·미리보기(D3)는 읽기 전용 트랜잭션(`transaction_read_only`)과 트랜잭션별
  `statement_timeout`(5초) 안에서 실행한다. 미리보기는 상수를 바인드로 보내고(뷰는 리터럴 렌더)
  사용자 SQL이 없다: 변환기가 SQLAlchemy 표현식으로 만든다. 실제 방어선은 이 구조이고 읽기 전용
  지정은 이중 장치다(07 §5, X-2).
- 계산 열 만들기(D4)·고치기(D5)는 dataset의 정의 변경 진입점 안에서 한다: 잠금 -> 버전 확인 -> 수식
  컴파일 -> 열 행 추가/형 갱신(dataset service) -> **훅**(수식·의존·뷰, `hook.py`) -> `def_hash`.
- DB 예외는 사용자에게 `FORMULA_RUNTIME_ERROR`로만 정규화하고 클래스 이름·SQLSTATE만 로그에 남긴다
  (SQL·상수·입력 값 금지).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app import ddl
from app.core.db_errors import sqlstate
from app.core.errors import (
    formula_invalid,
    formula_runtime_error,
    not_found,
)
from app.core.limits import HeavyReadLimiter
from app.core.ports import DefinitionHooks
from app.dataset import definition as dataset_definition
from app.dataset import service as dataset_service
from app.dataset.service import DefinitionView
from app.formula import repo
from app.formula.api import check_formula, compile_formula
from app.formula.columns import ColumnInfo
from app.formula.errors import CELL_ERROR_BY_NUMBER, CELL_ERROR_MESSAGES_KO
from app.formula.functions import get_default_registry
from app.formula.hook import (
    PENDING_KEY,
    PendingFormula,
    failure_to_error,
    is_postgresql,
    make_probe,
)
from app.formula.literals import LITERALS
from app.formula.nodes import ast_from_json, column_ids
from app.formula.textview import render_text
from app.formula.views import (
    FormulaCompileFailure,
    build_column_infos,
    source_columns,
    source_table,
)

logger = logging.getLogger(__name__)

PREVIEW_ROWS = 20  # 07 §5 [제안, 03b 2-5 B5]
READ_STATEMENT_TIMEOUT = "5000ms"  # 07 §5 [제안 값]: 미리보기·오류 칸 조회의 문장 시간 제한
QUERY_CANCELED = "57014"


# --- 공통 ----


def harden_read(session: Session) -> None:
    """이 트랜잭션을 읽기 전용으로 하고 문장 시간 제한을 건다(PostgreSQL). 다른 엔진은 건너뛴다."""
    if not is_postgresql(session):
        return
    session.execute(sa.select(sa.func.set_config("transaction_read_only", "on", True)))
    session.execute(
        sa.select(sa.func.set_config("statement_timeout", READ_STATEMENT_TIMEOUT, True))
    )


@dataclass(frozen=True)
class Context:
    """수식 처리가 읽는 데이터셋 정의 한 장면."""

    defn: DefinitionView
    stored: Mapping[int, repo.StoredFormula]
    infos: list[ColumnInfo]

    def column(self, column_id: int) -> ColumnInfo | None:
        return next((c for c in self.infos if c.id == column_id), None)


def load_context(session: Session, dataset_id: int) -> Context:
    defn = dataset_service.read_definition(session, dataset_id)
    stored = repo.load_formulas(session, dataset_id)
    return Context(defn, stored, build_column_infos(defn, stored))


def require_formula_column(ctx: Context, column_id: int) -> ColumnInfo:
    column = ctx.column(column_id)
    if column is None or not column.is_formula:
        raise not_found()
    return column


def format_result(value_type: str | None, value: Any) -> Any:
    """결과 값을 응답 값으로(05 §1, 제안 7항 ⑤): 숫자 십진 문자열, 참거짓 JSON 불리언, 날짜 ISO."""
    if value is None:
        return None
    if value_type == "number":
        return format(Decimal(value), "f")
    if value_type == "date":
        return value.isoformat()
    if value_type == "boolean":
        return bool(value)
    return str(value)


def _error_code(number: Any) -> str | None:
    if number is None:
        return None
    return CELL_ERROR_BY_NUMBER.get(int(number), "E?")


# --- D1 ----


def functions_catalog() -> dict[str, Any]:
    """D1: 함수 사전에서 자동 생성한 도움말과 셀 오류 문구."""
    return {
        "functions": get_default_registry().describe(),
        "cell_errors": dict(CELL_ERROR_MESSAGES_KO),
    }


# --- D2 검사 ----


def check(
    session: Session, dataset_id: int, expression: str, column_id: int | None
) -> dict[str, Any]:
    """D2: 수식을 검사한다. C0 검사 실패도 오류가 아니라 `ok=false` 응답이다."""
    harden_read(session)
    ctx = load_context(session, dataset_id)
    if column_id is not None:
        require_formula_column(ctx, column_id)
    probe = make_probe(session) if is_postgresql(session) else None
    result = check_formula(expression, ctx.infos, column_id=column_id, const_probe=probe)
    session.rollback()
    return result.check_response(ctx.infos)


# --- D3 미리보기 ----


def preview(
    session: Session,
    limiter: HeavyReadLimiter,
    *,
    user_id: int,
    dataset_id: int,
    expression: str,
    column_id: int | None,
) -> dict[str, Any]:
    """D3: 저장하지 않고 일부 행을 계산한다. 같은 변환기의 식을 바인드로 읽기 전용 실행한다."""
    with limiter.slot(user_id=user_id):
        harden_read(session)
        ctx = load_context(session, dataset_id)
        if column_id is not None:
            require_formula_column(ctx, column_id)
        ds = source_table(ctx.defn)
        result = compile_formula(
            expression,
            ctx.infos,
            column_id=column_id,
            source_columns=source_columns(ctx.defn, ds),
            const_probe=make_probe(session) if is_postgresql(session) else None,
        )
        if not result.ok:
            session.rollback()
            raise formula_invalid([issue.as_dict() for issue in result.issues])
        assert result.value is not None  # noqa: S101 - build_sql=True
        error = result.error if result.error is not None else LITERALS.null("smallint")
        base_id = ctx.defn.base_date_column_id
        period = ds.c[ddl.column_name(base_id)] if base_id is not None else None
        order = [period.desc(), ds.c.row_id.desc()] if period is not None else [ds.c.row_id.desc()]
        rows_stmt = (
            sa.select(
                ds.c.row_id,
                (period if period is not None else LITERALS.null("date")).label("period"),
                result.value.label("v"),
                error.label("e"),
            )
            .select_from(ds)
            .order_by(*order)
            .limit(PREVIEW_ROWS)
        )
        every = (
            sa.select(result.value.label("v"), error.label("e")).select_from(ds).subquery("calc")
        )
        counts_stmt = sa.select(
            sa.func.count(),
            sa.func.count(every.c.e),
            sa.func.count().filter(sa.and_(every.c.v.is_(None), every.c.e.is_(None))),
        ).select_from(every)
        try:
            rows = session.execute(rows_stmt).all()
            total, error_count, empty_count = session.execute(counts_stmt).one()
        except DBAPIError as exc:
            session.rollback()
            logger.warning(
                "미리보기 계산 실패: %s (sqlstate=%s, dataset_id=%s)",
                type(exc).__name__,
                sqlstate(exc),
                dataset_id,
            )
            raise formula_runtime_error() from None
        session.rollback()
        return {
            "result_type": result.result_type,
            "rows": [
                {
                    "row_id": int(r.row_id),
                    "period": r.period.isoformat() if r.period is not None else None,
                    "value": format_result(result.result_type, r.v),
                    "error": _error_code(r.e),
                }
                for r in rows
            ],
            "total_rows": int(total),
            "error_count": int(error_count),
            "empty_count": int(empty_count),
            "def_version": ctx.defn.def_version,
        }


# --- D4·D5 저장 ----


@dataclass(frozen=True)
class FormulaSaved:
    column_id: int
    def_version: int
    result_type_changed: bool = False


def _compile_for_save(
    session: Session,
    ctx: Context,
    expression: str,
    *,
    column_id: int | None,
    tag: str | None,
    display_name: str | None,
):
    ds = source_table(ctx.defn)
    result = compile_formula(
        expression,
        ctx.infos,
        column_id=column_id,
        tag=tag,
        column_name_hint=display_name,
        source_columns=source_columns(ctx.defn, ds),
        const_probe=make_probe(session) if is_postgresql(session) else None,
    )
    if not result.ok:
        failure = FormulaCompileFailure(column_id, display_name or "", result.issues)
        raise failure_to_error(failure, edited_column_id=column_id)
    return result


def create_formula_column(
    session: Session,
    hooks: DefinitionHooks,
    dataset_id: int,
    *,
    expected_version: int,
    display_name: str,
    expression: str,
    tag: str | None,
    position: int | None,
) -> FormulaSaved:
    """D4: 계산 열 만들기. 열 행 추가 -> 훅(수식·의존·뷰) -> `def_hash`, 한 트랜잭션."""

    def change(_locked: RowMapping) -> tuple[bool, dict[str, Any]]:
        ctx = load_context(session, dataset_id)
        clean_tag = _tag_or_none(tag)
        result = _compile_for_save(
            session, ctx, expression, column_id=None, tag=clean_tag, display_name=display_name
        )
        assert result.result_type is not None  # noqa: S101 - ok=True
        column_id = dataset_service.add_formula_column(
            session,
            dataset_id,
            display_name=display_name,
            result_type=result.result_type,
            raw_tag=tag,
            position=position,
        )
        session.info[PENDING_KEY] = PendingFormula(column_id, expression, result)
        return True, {"column_id": column_id}

    outcome = dataset_definition.apply_definition_change(
        session, hooks, dataset_id, expected_version=expected_version, change=change
    )
    return FormulaSaved(outcome.result["column_id"], outcome.def_version)


def update_formula(
    session: Session,
    hooks: DefinitionHooks,
    dataset_id: int,
    column_id: int,
    *,
    expected_version: int,
    expression: str,
) -> FormulaSaved:
    """D5: 계산 열의 수식 고치기. 결과 형이 바뀌면 같은 진입점이 `type`을 갱신한다."""

    def change(_locked: RowMapping) -> tuple[bool, dict[str, Any]]:
        ctx = load_context(session, dataset_id)
        column = require_formula_column(ctx, column_id)
        result = _compile_for_save(
            session, ctx, expression, column_id=column_id, tag=None, display_name=column.name
        )
        stored = ctx.stored.get(column_id)
        type_changed = result.result_type != column.type
        if stored is not None and stored.ast_hash == result.ast_hash and not type_changed:
            return False, {"changed": False}  # 같은 수식: 버전을 올리지 않는다
        session.info[PENDING_KEY] = PendingFormula(column_id, expression, result)
        return True, {"type_changed": type_changed}

    outcome = dataset_definition.apply_definition_change(
        session, hooks, dataset_id, expected_version=expected_version, change=change
    )
    return FormulaSaved(
        column_id, outcome.def_version, bool(outcome.result.get("type_changed", False))
    )


def _tag_or_none(tag: str | None) -> str | None:
    """컴파일에 알릴 새 열의 태그(검증은 dataset service가 한다: 잘못된 태그는 거기서 422)."""
    return tag.strip() if isinstance(tag, str) and tag.strip() else None


# --- D6 수식 보기 ----


def _error_count(session: Session, dataset_id: int, column_id: int) -> int:
    """계산 열의 오류 칸 수(`de_` 뷰). 뷰가 없거나 읽지 못하면 0이다(뷰 점검 D9가 알린다)."""
    error_column = sa.column(ddl.error_column_name(column_id))
    view = sa.table(ddl.error_view_name(dataset_id), error_column, schema=ddl.DYNAMIC_SCHEMA)
    try:
        with session.begin_nested():
            return int(
                session.execute(
                    sa.select(sa.func.count(error_column)).select_from(view)
                ).scalar_one()
            )
    except DBAPIError as exc:
        logger.warning(
            "오류 칸 수를 읽지 못했다: %s (sqlstate=%s, dataset_id=%s)",
            type(exc).__name__,
            sqlstate(exc),
            dataset_id,
        )
        return 0


def view_formula(session: Session, dataset_id: int, column_id: int) -> dict[str, Any]:
    """D6: 현재 열 이름으로 풀어 쓴 수식. 원문(`expression`)은 응답에 없다."""
    harden_read(session)
    ctx = load_context(session, dataset_id)
    column = require_formula_column(ctx, column_id)
    stored = ctx.stored.get(column_id)
    if stored is None or column.formula is None:
        raise not_found()
    text = render_text(column.formula, ctx.infos)
    names = {c.id: c for c in ctx.infos}
    refs = [
        {"column_id": cid, "display_name": names[cid].name, "kind": names[cid].kind}
        for cid in column_ids(ast_from_json(stored.ast))
        if cid in names
    ]
    result = compile_formula(text, ctx.infos, column_id=column_id, build_sql=False)
    tag_ids = sorted({cid for ids in result.sumtag_columns.values() for cid in ids})
    response = {
        "column_id": column_id,
        "text": text,
        "refs": refs,
        "tag_columns": [names[cid].name for cid in tag_ids if cid in names],
        "error_count": _error_count(session, dataset_id, column_id),
    }
    session.rollback()
    return response


# --- D7·D8 오류 칸 점검 ----


def _error_counts(session: Session, dataset_id: int, column_ids_: Sequence[int]) -> dict[int, int]:
    """데이터셋 하나의 계산 열별 오류 칸 수(한 번의 SELECT). 뷰를 읽지 못하면 빈 사전."""
    columns = {cid: sa.column(ddl.error_column_name(cid)) for cid in column_ids_}
    view = sa.table(ddl.error_view_name(dataset_id), *columns.values(), schema=ddl.DYNAMIC_SCHEMA)
    statement = sa.select(*[sa.func.count(columns[cid]).label(f"n{cid}") for cid in column_ids_])
    try:
        with session.begin_nested():
            row = session.execute(statement.select_from(view)).one()
    except DBAPIError as exc:
        if sqlstate(exc) == QUERY_CANCELED:
            raise formula_runtime_error() from None
        logger.warning(
            "오류 칸 수를 읽지 못했다: %s (sqlstate=%s, dataset_id=%s)",
            type(exc).__name__,
            sqlstate(exc),
            dataset_id,
        )
        return {}
    return {cid: int(row._mapping[f"n{cid}"]) for cid in column_ids_}


def error_summaries(
    session: Session, limiter: HeavyReadLimiter, *, limit: int, offset: int
) -> tuple[list[dict[str, Any]], int]:
    """D7: 오류 칸이 있는 계산 열 목록(데이터셋·열 단위)."""
    with limiter.slot():
        harden_read(session)
        items: list[dict[str, Any]] = []
        grouped: dict[int, list[Mapping[str, Any]]] = {}
        order: list[int] = []
        for row in dataset_service.list_formula_columns(session):
            if row["dataset_id"] not in grouped:
                grouped[row["dataset_id"]] = []
                order.append(row["dataset_id"])
            grouped[row["dataset_id"]].append(row)
        for dataset_id in order:
            rows = grouped[dataset_id]
            counts = _error_counts(session, dataset_id, [r["column_id"] for r in rows])
            for r in rows:
                if counts.get(r["column_id"], 0) > 0:
                    items.append(
                        {
                            "dataset_id": dataset_id,
                            "dataset_name": r["dataset_name"],
                            "team_name": r["team_name"],
                            "column_id": r["column_id"],
                            "column_name": r["column_name"],
                            "error_count": counts[r["column_id"]],
                        }
                    )
        session.rollback()
        return items[offset : offset + limit], len(items)


def error_cells(
    session: Session,
    limiter: HeavyReadLimiter,
    dataset_id: int,
    column_id: int | None,
    *,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    """D8: 데이터셋의 오류 칸 목록(열 순서, 같은 열은 행 번호 순)."""
    with limiter.slot():
        harden_read(session)
        ctx = load_context(session, dataset_id)
        if column_id is not None:
            require_formula_column(ctx, column_id)
        targets = [
            c.id for c in ctx.infos if c.is_formula and (column_id is None or c.id == column_id)
        ]
        ds = source_table(ctx.defn)
        base_id = ctx.defn.base_date_column_id
        period = ds.c[ddl.column_name(base_id)] if base_id is not None else None
        counts = _error_counts(session, dataset_id, targets) if targets else {}
        total = sum(counts.values())
        items: list[dict[str, Any]] = []
        skip, take = offset, limit
        for target in targets:
            n = counts.get(target, 0)
            if take <= 0:
                break
            if skip >= n:
                skip -= n
                continue
            error_column = sa.column(ddl.error_column_name(target))
            view = sa.table(
                ddl.error_view_name(dataset_id),
                sa.column("row_id"),
                error_column,
                schema=ddl.DYNAMIC_SCHEMA,
            )
            statement = (
                sa.select(
                    view.c.row_id,
                    (period if period is not None else LITERALS.null("date")).label("period"),
                    error_column.label("e"),
                )
                .select_from(view.join(ds, ds.c.row_id == view.c.row_id))
                .where(error_column.is_not(None))
                .order_by(view.c.row_id)
                .limit(take)
                .offset(skip)
            )
            try:
                fetched = session.execute(statement).all()
            except DBAPIError as exc:
                session.rollback()
                logger.warning(
                    "오류 칸 목록 조회 실패: %s (sqlstate=%s, dataset_id=%s)",
                    type(exc).__name__,
                    sqlstate(exc),
                    dataset_id,
                )
                raise formula_runtime_error() from None
            for r in fetched:
                code = _error_code(r.e) or "E?"
                items.append(
                    {
                        "row_id": int(r.row_id),
                        "period": r.period.isoformat() if r.period is not None else None,
                        "column_id": target,
                        "error": code,
                        "message": CELL_ERROR_MESSAGES_KO.get(code, ""),
                    }
                )
            take -= len(fetched)
            skip = 0
        session.rollback()
        return items, total
