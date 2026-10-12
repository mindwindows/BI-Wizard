"""입력 그리드 로직(05 §2-3 C1~C4, 06 §3·§5). 트랜잭션은 여기서 명시적으로 commit/rollback한다.

쓰기(C2~C4)의 공통 순서:
1. dataset service가 `datasets` 행을 `FOR SHARE`로 잠그고 `expected_version`을 확인한다(06 §5).
   정의 변경(`FOR NO KEY UPDATE`)과는 서로 기다리고 행 쓰기끼리는 막지 않는다. 락 대기 한도는
   코드 상수 `lock_timeout`이고 넘기거나 교착이면 503 `WRITE_BUSY`다.
2. 값을 열 타입으로 해석·재검증한다(`values.parse_cell`). 위반은 모아서 한 번에 422로 답한다.
3. 쓴다. 잠금 순서는 항상 `datasets` 행 → `ds_` 행이다.
4. 응답용 행을 같은 트랜잭션에서 읽고 커밋한다(계산 열은 `RowViewPort`).
오류는 롤백하고 올린다: 아무것도 반영되지 않는다.

칸 단위 값 비교 갱신(C3·C4): 단일 `UPDATE … WHERE row_id = … AND 칸 가드`와 `rowcount`로 충돌을
판정한다(`repo.update_guarded`). 가드는 "지금 값이 읽었던 값이거나 이미 바꾸려는 값"이다.
0행이면 다시 읽어 원인을 구분한다(행 없음 / 칸 충돌).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import TableClause

from app.core.db_errors import is_lock_conflict, sqlstate
from app.core.errors import (
    AppError,
    FieldErrorCode,
    cell_conflict,
    paste_conflict,
    period_conflict,
    row_not_found,
    validation_failed_items,
    write_busy,
)
from app.core.ports import ComputedRow, RowViewPort
from app.dataset import service as dataset_service
from app.dataset.service import RowColumn, RowContext
from app.ddl import column_name
from app.entry import repo
from app.entry.values import CellSpec, format_value, parse_cell

# 붙여넣기 요청 상한(승인 A안, 03b 6-2): 5,000행, 본문 1MiB. 코드 상수(새 환경변수 아님).
PASTE_MAX_ROWS = 5_000
PASTE_MAX_BYTES = 1_048_576
# 응답에 담는 항목 수 상한(오류 목록이 요청 크기에 비례해 커지는 것을 막는다).
MAX_VALIDATION_ITEMS = 200
MAX_CONFLICT_ITEMS = 1_000
_KEY_ECHO_LIMIT = 40  # 필드 이름에 되돌려 쓰는 사용자 키의 최대 글자 수

Problem = dict[str, Any]
ChangeMap = dict[int, tuple[Any, Any]]  # 열 번호 -> (expected, value)


# --- 공통 ----


@contextmanager
def _row_write(session: Session) -> Iterator[None]:
    """쓰기 트랜잭션 경계: 어떤 오류든 롤백하고, 락 대기 초과·교착은 `WRITE_BUSY`로 바꾼다."""
    try:
        yield
    except AppError:
        session.rollback()
        raise
    except DBAPIError as error:
        session.rollback()
        if is_lock_conflict(error):
            raise write_busy() from None
        raise
    except BaseException:
        session.rollback()
        raise


def _spec(ctx: RowContext, column: RowColumn) -> CellSpec:
    is_base = column.id == ctx.base_date_column_id
    return CellSpec(
        column_id=column.id,
        type=column.type,
        required=column.required or is_base,  # 기준 날짜 열은 DB NOT NULL이라 필수로 취급(05 C2)
        rules=column.rules,
        is_base=is_base,
        date_unit=ctx.date_unit,
    )


def _raw_columns(ctx: RowContext) -> dict[int, RowColumn]:
    return {c.id: c for c in ctx.columns if c.kind == "raw"}


def _formula_ids(ctx: RowContext) -> set[int]:
    return {c.id for c in ctx.columns if c.kind != "raw"}


def _echo(key: str) -> str:
    return key if len(key) <= _KEY_ECHO_LIMIT else key[:_KEY_ECHO_LIMIT] + "…"


def _column_key(key: str) -> int | None:
    """`cells`의 키(열 번호 글자)를 정수로. 정규 표기(`"12"`)가 아니면 None."""
    if not key.isascii() or not key.isdigit() or len(key) > 18 or str(int(key)) != key:
        return None
    return int(key)


def _check_value(spec: CellSpec, raw: Any) -> tuple[Any, str | None]:
    """값을 해석하고 필수 여부까지 판정한다: (저장 값, 필드 코드)."""
    value, code = parse_cell(spec, raw)
    if code is None and value is None and spec.required:
        return None, FieldErrorCode.REQUIRED
    return value, code


def _changed_value(
    spec: CellSpec, raw_value: Any, raw_expected: Any
) -> tuple[Any, Any, str | None, str | None]:
    """기존 칸의 변경 해석: (value, expected, value 코드, expected 코드).

    이전 값과 같은 값은 규칙 위반이어도 오류가 아니다(규칙을 바꾸기 전에 들어간 값, 06 §3-2).
    """
    expected, expected_code = parse_cell(spec, raw_expected, check_rules=False)
    if expected_code is not None:
        return None, None, None, FieldErrorCode.BAD_FORMAT
    loose, loose_code = parse_cell(spec, raw_value, check_rules=False)
    if loose_code is None and loose == expected:
        return expected, expected, None, None
    value, code = _check_value(spec, raw_value)
    return value, expected, code, None


# --- 행 만들기 (읽기) ----


def _computed(
    session: Session, ctx: RowContext, row_ids: Sequence[int], row_view: RowViewPort
) -> Mapping[int, ComputedRow]:
    formula_ids = sorted(_formula_ids(ctx))
    if not formula_ids or not row_ids:
        return {}
    return row_view.read_computed(session, ctx.dataset_id, list(row_ids), formula_ids)


def _row_dict(
    ctx: RowContext, db_row: Mapping[str, Any], computed: ComputedRow | None
) -> dict[str, Any]:
    cells: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for column in ctx.columns:
        if column.kind == "raw":
            cells[str(column.id)] = format_value(column.type, db_row[column_name(column.id)])
            continue
        # 계산 열: 값은 RowViewPort가 준다. 오류 칸은 값 null + errors(05 §1 Row).
        value = computed.values.get(column.id) if computed else None
        cells[str(column.id)] = format_value(column.type, value)
        if computed is not None and column.id in computed.errors:
            errors[str(column.id)] = computed.errors[column.id]
    return {"row_id": int(db_row["row_id"]), "cells": cells, "errors": errors}


def _rows_out(
    session: Session,
    ctx: RowContext,
    db_rows: Sequence[Mapping[str, Any]],
    row_view: RowViewPort,
) -> list[dict[str, Any]]:
    computed = _computed(session, ctx, [int(r["row_id"]) for r in db_rows], row_view)
    return [_row_dict(ctx, r, computed.get(int(r["row_id"]))) for r in db_rows]


def _one_row(
    session: Session, ctx: RowContext, tbl: TableClause, row_id: int, row_view: RowViewPort
) -> dict[str, Any]:
    db_row = repo.get_row(session, tbl, row_id)
    if db_row is None:  # 방금 쓴 행이다. 일어나지 않는다.
        raise row_not_found()
    return _rows_out(session, ctx, [db_row], row_view)[0]


# --- C1 ----


def list_rows(
    session: Session,
    dataset_id: int,
    *,
    order: Literal["asc", "desc"],
    limit: int,
    offset: int,
    row_view: RowViewPort,
) -> dict[str, Any]:
    """C1: 행 조회. 잠금 없음. 정렬은 기준 날짜 열(없으면 `row_id`)."""
    ctx = dataset_service.read_row_context(session, dataset_id)
    tbl = repo.dynamic_table(ctx)
    total = repo.count_rows(session, tbl)
    db_rows = repo.select_rows(
        session,
        tbl,
        order_column_id=ctx.base_date_column_id,
        descending=order == "desc",
        limit=limit,
        offset=offset,
    )
    items = _rows_out(session, ctx, db_rows, row_view)
    session.rollback()  # 읽기 전용: 트랜잭션을 바로 닫는다.
    return {
        "def_version": ctx.def_version,
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# --- C2 ----


def _parse_create(
    ctx: RowContext, cells: Mapping[str, Any]
) -> tuple[dict[int, Any], list[Problem]]:
    raw_columns = _raw_columns(ctx)
    formula_ids = _formula_ids(ctx)
    problems: list[Problem] = []
    for key in cells:
        column_id = _column_key(key)
        if column_id in formula_ids:
            problems.append({"field": f"cells.{key}", "code": FieldErrorCode.READ_ONLY})
        elif column_id not in raw_columns:
            problems.append({"field": f"cells.{_echo(key)}", "code": FieldErrorCode.BAD_FORMAT})
    values: dict[int, Any] = {}
    for column_id, column in raw_columns.items():
        value, code = _check_value(_spec(ctx, column), cells.get(str(column_id)))
        if code is not None:
            problems.append({"field": f"cells.{column_id}", "code": code})
        elif value is not None:
            values[column_id] = value
    return values, problems


def _period_conflict_error(
    session: Session, ctx: RowContext, tbl: TableClause, period: date
) -> AppError:
    base_id = ctx.base_date_column_id
    assert base_id is not None  # noqa: S101 - 기간 충돌은 기준 날짜 열이 있을 때만 난다
    return period_conflict(
        [
            {
                "row_id": repo.find_by_period(session, tbl, base_id, period),
                "column_id": base_id,
                "current": period.isoformat(),
            }
        ]
    )


def create_row(
    session: Session,
    dataset_id: int,
    *,
    expected_version: int,
    cells: Mapping[str, Any],
    row_view: RowViewPort,
) -> tuple[dict[str, Any], int]:
    """C2: 새 행 하나. 필수 열이 모두 있어야 저장한다(임시 행은 화면 메모리, 05 §2-3)."""
    with _row_write(session):
        ctx = dataset_service.lock_row_context(session, dataset_id, expected_version)
        values, problems = _parse_create(ctx, cells)
        if problems:
            raise validation_failed_items(problems[:MAX_VALIDATION_ITEMS])
        tbl = repo.dynamic_table(ctx)
        base_id = ctx.base_date_column_id
        row_id = repo.insert_row(session, tbl, values, skip_period_conflict=base_id is not None)
        if row_id is None:
            assert base_id is not None  # noqa: S101
            raise _period_conflict_error(session, ctx, tbl, values[base_id])
        row = _one_row(session, ctx, tbl, row_id, row_view)
        session.commit()
    return row, ctx.def_version


# --- C3 ----


@dataclass
class _Cell:
    column_id: int
    current: Any


def _guarded_update(
    session: Session, tbl: TableClause, ctx: RowContext, row_id: int, changes: ChangeMap
) -> tuple[Literal["ok", "missing", "conflict"], list[_Cell]]:
    """가드 갱신 한 번 + 0행일 때의 원인 구분. 충돌이면 충돌한 칸의 현재 값을 함께 돌려준다."""
    for _attempt in range(2):
        if repo.update_guarded(session, tbl, row_id, changes) == 1:
            return "ok", []
        current = repo.get_row(session, tbl, row_id)
        if current is None:
            return "missing", []
        bad = [
            _Cell(cid, current[column_name(cid)])
            for cid, (expected, value) in changes.items()
            if current[column_name(cid)] != expected and current[column_name(cid)] != value
        ]
        if bad:
            return "conflict", bad
        # 다시 읽어 보니 모든 칸이 가드에 맞는다: 읽는 사이 값이 또 바뀐 경우라 한 번 더 시도한다.
    return "conflict", [_Cell(cid, current[column_name(cid)]) for cid in changes]


def _column_type(ctx: RowContext, column_id: int) -> str:
    return next(c.type for c in ctx.columns if c.id == column_id)


def _parse_changes(ctx: RowContext, changes: Sequence[Any]) -> tuple[ChangeMap, list[Problem]]:
    raw_columns = _raw_columns(ctx)
    formula_ids = _formula_ids(ctx)
    parsed: ChangeMap = {}
    problems: list[Problem] = []
    seen: set[int] = set()
    for index, change in enumerate(changes):
        column_id = change.column_id
        where = f"changes.{index}"
        duplicate = column_id in seen
        seen.add(column_id)
        if column_id in formula_ids:
            problems.append({"field": f"{where}.column_id", "code": FieldErrorCode.READ_ONLY})
        elif column_id not in raw_columns or duplicate:
            problems.append({"field": f"{where}.column_id", "code": FieldErrorCode.BAD_FORMAT})
        else:
            value, expected, code, expected_code = _changed_value(
                _spec(ctx, raw_columns[column_id]), change.value, change.expected
            )
            if expected_code is not None:
                problems.append({"field": f"{where}.expected", "code": expected_code})
            elif code is not None:
                problems.append({"field": f"{where}.value", "code": code})
            else:
                parsed[column_id] = (expected, value)
    return parsed, problems


def update_row(
    session: Session,
    dataset_id: int,
    row_id: int,
    *,
    expected_version: int,
    changes: Sequence[Any],
    row_view: RowViewPort,
) -> tuple[dict[str, Any], int]:
    """C3: 기존 행의 칸 수정. 한 요청의 칸 전부가 가드이고 하나라도 충돌하면 전체 취소."""
    with _row_write(session):
        ctx = dataset_service.lock_row_context(session, dataset_id, expected_version)
        parsed, problems = _parse_changes(ctx, changes)
        if problems:
            raise validation_failed_items(problems[:MAX_VALIDATION_ITEMS])
        tbl = repo.dynamic_table(ctx)
        base_id = ctx.base_date_column_id
        try:
            status, bad = _guarded_update(session, tbl, ctx, row_id, parsed)
        except IntegrityError as error:
            if base_id is None or base_id not in parsed or not _is_unique_violation(error):
                raise
            period = parsed[base_id][1]
            session.rollback()  # 위반한 트랜잭션은 이미 중단됐다. 새 트랜잭션에서 기존 행을 찾는다.
            raise _period_conflict_error(session, ctx, tbl, period) from None
        if status == "missing":
            raise row_not_found()
        if status == "conflict":
            raise cell_conflict(
                [
                    {
                        "row_id": row_id,
                        "column_id": cell.column_id,
                        "current": format_value(_column_type(ctx, cell.column_id), cell.current),
                    }
                    for cell in bad
                ]
            )
        row = _one_row(session, ctx, tbl, row_id, row_view)
        session.commit()
    return row, ctx.def_version


def _is_unique_violation(error: IntegrityError) -> bool:
    # PostgreSQL 23505. SQLite(DB 없는 시험)는 메시지로 구분한다.
    return sqlstate(error) == "23505" or "UNIQUE constraint failed" in str(error.orig)


# --- C4 ----


@dataclass
class _PasteExisting:
    index: int
    row_id: int
    changes: ChangeMap


@dataclass
class _PasteNew:
    index: int
    values: dict[int, Any]
    period: date | None = None


@dataclass
class _PasteParse:
    existing: list[_PasteExisting] = field(default_factory=list)
    new: list[_PasteNew] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)


def _paste_specs(
    ctx: RowContext, column_ids: Sequence[int], problems: list[Problem]
) -> list[CellSpec]:
    raw_columns = _raw_columns(ctx)
    formula_ids = _formula_ids(ctx)
    specs: list[CellSpec] = []
    seen: set[int] = set()
    for position, column_id in enumerate(column_ids):
        field_name = f"column_ids.{position}"
        if column_id in formula_ids:
            problems.append({"field": field_name, "code": FieldErrorCode.READ_ONLY})
        elif column_id not in raw_columns or column_id in seen:
            problems.append({"field": field_name, "code": FieldErrorCode.BAD_FORMAT})
        else:
            seen.add(column_id)
            specs.append(_spec(ctx, raw_columns[column_id]))
    return specs


def _parse_paste(ctx: RowContext, column_ids: Sequence[int], rows: Sequence[Any]) -> _PasteParse:
    out = _PasteParse()
    specs = _paste_specs(ctx, column_ids, out.problems)
    if out.problems:  # 열 목록이 틀렸으면 행 해석은 의미가 없다.
        return out
    # 새 행은 필수 열(기준 날짜 열 포함)이 모두 붙여넣는 열 안에 있어야 한다.
    chosen = {s.column_id for s in specs}
    missing_required = [
        c.id
        for c in ctx.columns
        if c.kind == "raw" and _spec(ctx, c).required and c.id not in chosen
    ]
    seen_rows: set[int] = set()
    for index, row in enumerate(rows):
        if len(row.values) != len(specs):
            out.problems.append(
                {"field": f"rows.{index}.values", "code": FieldErrorCode.BAD_FORMAT}
            )
            continue
        if row.row_id is None:
            _parse_new_row(ctx, specs, index, row, missing_required, out)
        else:
            if row.row_id in seen_rows:
                out.problems.append(
                    {"field": f"rows.{index}.row_id", "code": FieldErrorCode.BAD_FORMAT}
                )
                continue
            seen_rows.add(row.row_id)
            _parse_existing_row(specs, index, row, out)
    return out


def _parse_new_row(
    ctx: RowContext,
    specs: Sequence[CellSpec],
    index: int,
    row: Any,
    missing_required: Sequence[int],
    out: _PasteParse,
) -> None:
    values: dict[int, Any] = {}
    failed = False
    for spec, raw in zip(specs, row.values, strict=True):
        value, code = _check_value(spec, raw)
        if code is not None:
            out.problems.append({"row_index": index, "column_id": spec.column_id, "code": code})
            failed = True
        elif value is not None:
            values[spec.column_id] = value
    for column_id in missing_required:
        out.problems.append(
            {"row_index": index, "column_id": column_id, "code": FieldErrorCode.REQUIRED}
        )
        failed = True
    if not failed:
        base_id = ctx.base_date_column_id
        out.new.append(_PasteNew(index, values, values.get(base_id) if base_id else None))


def _parse_existing_row(specs: Sequence[CellSpec], index: int, row: Any, out: _PasteParse) -> None:
    if row.expected is None:
        out.problems.append({"field": f"rows.{index}.expected", "code": FieldErrorCode.REQUIRED})
        return
    if len(row.expected) != len(specs):
        out.problems.append({"field": f"rows.{index}.expected", "code": FieldErrorCode.BAD_FORMAT})
        return
    changes: ChangeMap = {}
    for spec, raw, raw_expected in zip(specs, row.values, row.expected, strict=True):
        value, expected, code, expected_code = _changed_value(spec, raw, raw_expected)
        code = expected_code or code
        if code is not None:
            out.problems.append({"row_index": index, "column_id": spec.column_id, "code": code})
        elif value == expected:
            continue  # 바뀌지 않은 칸은 쓰지도, 가드로 쓰지도 않는다.
        elif spec.is_base:
            # 기존 행의 기간은 붙여넣기로 바꿀 수 없다(기간 이동은 C3 단건, 05 C4 규칙).
            out.problems.append(
                {"row_index": index, "column_id": spec.column_id, "code": FieldErrorCode.READ_ONLY}
            )
        else:
            changes[spec.column_id] = (expected, value)
    out.existing.append(_PasteExisting(index, row.row_id, changes))


def paste_rows(
    session: Session,
    dataset_id: int,
    *,
    expected_version: int,
    column_ids: Sequence[int],
    rows: Sequence[Any],
) -> dict[str, Any]:
    """C4: 붙여넣기. 한 트랜잭션, 충돌이 하나라도 있으면 끝에서 전부 취소한다.

    처리 순서는 고정이다: 기존 행 `row_id` 오름차순 갱신 → 새 행 기간 오름차순(기준 날짜 열이
    없으면 입력 순) 삽입. 모든 붙여넣기가 같은 순서로 잠금을 잡아 교착을 막는다(06 §5).
    충돌은 첫 건에서 멈추지 않고 모아 한 번에 `PASTE_CONFLICT`로 돌려준다.
    """
    with _row_write(session):
        ctx = dataset_service.lock_row_context(session, dataset_id, expected_version)
        parsed = _parse_paste(ctx, column_ids, rows)
        if parsed.problems:
            raise validation_failed_items(parsed.problems[:MAX_VALIDATION_ITEMS])
        tbl = repo.dynamic_table(ctx)
        base_id = ctx.base_date_column_id
        conflicts: list[dict[str, Any]] = []

        present = repo.existing_row_ids(session, tbl, [e.row_id for e in parsed.existing])
        updated = 0
        for item in sorted(parsed.existing, key=lambda e: e.row_id):
            missing = {
                "row_index": item.index,
                "row_id": item.row_id,
                "column_id": None,
                "kind": "row_missing",
                "current": None,
            }
            if item.row_id not in present:
                conflicts.append(missing)
                continue
            if not item.changes:
                continue
            status, bad = _guarded_update(session, tbl, ctx, item.row_id, item.changes)
            if status == "ok":
                updated += 1
            elif status == "missing":
                conflicts.append(missing)
            else:
                conflicts.extend(
                    {
                        "row_index": item.index,
                        "row_id": item.row_id,
                        "column_id": cell.column_id,
                        "kind": "cell",
                        "current": format_value(_column_type(ctx, cell.column_id), cell.current),
                    }
                    for cell in bad
                )

        created: list[dict[str, int]] = []
        new_rows = (
            sorted(parsed.new, key=lambda n: (n.period or date.min, n.index))
            if base_id is not None
            else parsed.new
        )
        for item in new_rows:
            row_id = repo.insert_row(
                session, tbl, item.values, skip_period_conflict=base_id is not None
            )
            if row_id is not None:
                created.append({"index": item.index, "row_id": row_id})
                continue
            assert base_id is not None and item.period is not None  # noqa: S101
            conflicts.append(
                {
                    "row_index": item.index,
                    "row_id": repo.find_by_period(session, tbl, base_id, item.period),
                    "column_id": base_id,
                    "kind": "period",
                    "current": item.period.isoformat(),
                }
            )

        if conflicts:
            conflicts.sort(key=lambda c: (c["row_index"], c["column_id"] or 0))
            raise paste_conflict(conflicts[:MAX_CONFLICT_ITEMS])
        session.commit()
    created.sort(key=lambda c: c["index"])
    return {
        "updated": updated,
        "created": len(created),
        "created_rows": created,
        "def_version": ctx.def_version,
    }
