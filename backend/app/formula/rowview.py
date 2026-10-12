"""`RowViewPort` 구현(04 §3, 07 §3-1): `dv_`와 `de_`를 `row_id`로 결합해 계산 열 값과 오류 칸을
준다.

- 값은 `dv_<번호>`의 `c_<번호>`다. 오류 칸은 뷰가 NULL을 돌려주므로 값만으로는 빈 값과 구별되지
  않는다. 구별은 `de_<번호>`의 `e_<번호>`(셀 오류 코드)로 한다: 코드가 있으면 `errors`에
  들어간다.
- 미리보기와 같은 변환기로 만든 뷰를 읽으므로 미리보기와 값이 같다(차분 시험이 확인한다).
- 뷰를 읽지 못하면(만들기에 실패해 뷰가 없는 데이터셋 등) 요청을 깨뜨리지 않고 계산 열을 빈 값으로
  돌려준다. 원인은 로그(클래스·SQLSTATE만)와 뷰 점검(D9)이 알린다.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence

import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.db_errors import sqlstate
from app.core.ports import ComputedRow
from app.db_metadata import DYNAMIC_SCHEMA
from app.ddl import column_name, error_column_name, error_view_name, view_name
from app.formula.errors import CELL_ERROR_BY_NUMBER

logger = logging.getLogger(__name__)


class FormulaRowView:
    """`RowViewPort`의 formula 구현."""

    def read_computed(
        self,
        session: Session,
        dataset_id: int,
        row_ids: Sequence[int],
        column_ids: Sequence[int],
    ) -> Mapping[int, ComputedRow]:
        if not row_ids or not column_ids:
            return {}
        values = {cid: sa.column(column_name(cid)) for cid in column_ids}
        errors = {cid: sa.column(error_column_name(cid)) for cid in column_ids}
        dv = sa.table(
            view_name(dataset_id), sa.column("row_id"), *values.values(), schema=DYNAMIC_SCHEMA
        )
        de = sa.table(
            error_view_name(dataset_id),
            sa.column("row_id"),
            *errors.values(),
            schema=DYNAMIC_SCHEMA,
        )
        statement = (
            sa.select(
                dv.c.row_id,
                *[values[cid].label(f"v{cid}") for cid in column_ids],
                *[errors[cid].label(f"e{cid}") for cid in column_ids],
            )
            .select_from(dv.join(de, de.c.row_id == dv.c.row_id))
            .where(dv.c.row_id.in_(list(row_ids)))
        )
        try:
            with session.begin_nested():
                rows = session.execute(statement).mappings().all()
        except DBAPIError as exc:
            logger.warning(
                "계산 열을 읽지 못했다: %s (sqlstate=%s, dataset_id=%s)",
                type(exc).__name__,
                sqlstate(exc),
                dataset_id,
            )
            return {}
        result: dict[int, ComputedRow] = {}
        for row in rows:
            result[int(row["row_id"])] = ComputedRow(
                values={cid: row[f"v{cid}"] for cid in column_ids},
                errors={
                    cid: CELL_ERROR_BY_NUMBER.get(int(row[f"e{cid}"]), "E?")
                    for cid in column_ids
                    if row[f"e{cid}"] is not None
                },
            )
        return result
