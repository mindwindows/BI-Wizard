"""수식 API 시험(실제 PostgreSQL) 공용 도구: 데이터셋·열·계산 열을 API로 만드는 짧은 함수들."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import sqlalchemy as sa

from app.db_metadata import DYNAMIC_SCHEMA, datasets
from tests.api_helpers import World
from tests.conftest import Db

Api = Callable[..., Any]


def err(response) -> dict[str, Any]:
    return response.json()["error"]


def make_dataset(
    api: Api, world: World, name: str = "수식 시험", date_unit: str = "month"
) -> dict[str, Any]:
    response = api(
        "definer",
        "POST",
        "/api/datasets",
        json={"team_id": world.team_a, "name": name, "date_unit": date_unit},
    )
    assert response.status_code == 201, response.text
    return response.json()


def version(api: Api, dataset_id: int) -> int:
    return api("definer", "GET", f"/api/datasets/{dataset_id}").json()["def_version"]


def add_column(
    api: Api, dataset_id: int, name: str, column_type: str = "number", **extra: Any
) -> dict[str, Any]:
    response = api(
        "definer",
        "POST",
        f"/api/datasets/{dataset_id}/columns",
        json={
            "expected_version": version(api, dataset_id),
            "display_name": name,
            "type": column_type,
            **extra,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["column"]


def add_formula(
    api: Api, dataset_id: int, name: str, expression: str, **extra: Any
) -> dict[str, Any]:
    response = post_formula(api, dataset_id, name, expression, **extra)
    assert response.status_code == 201, response.text
    return response.json()["column"]


def post_formula(api: Api, dataset_id: int, name: str, expression: str, **extra: Any):
    return api(
        "definer",
        "POST",
        f"/api/datasets/{dataset_id}/formulas",
        json={
            "expected_version": version(api, dataset_id),
            "display_name": name,
            "expression": expression,
            **extra,
        },
    )


def put_formula(api: Api, dataset_id: int, column_id: int, expression: str, **extra: Any):
    return api(
        "definer",
        "PUT",
        f"/api/datasets/{dataset_id}/formulas/{column_id}",
        json={
            "expected_version": extra.pop("expected_version", version(api, dataset_id)),
            "expression": expression,
        },
    )


def insert_rows(db: Db, dataset_id: int, rows: list[dict[int, Any]]) -> list[int]:
    """원본 표에 행을 직접 넣는다(열 번호 -> 값). `row_id` 목록을 돌려준다."""
    columns = sorted({cid for row in rows for cid in row})
    table = sa.table(
        f"ds_{dataset_id}",
        sa.column("row_id"),
        *[sa.column(f"c_{cid}") for cid in columns],
        schema=DYNAMIC_SCHEMA,
    )
    ids = []
    with db.engine.begin() as conn:
        for row in rows:
            ids.append(
                conn.execute(
                    sa.insert(table)
                    .values({f"c_{cid}": value for cid, value in row.items()})
                    .returning(table.c.row_id)
                ).scalar_one()
            )
    return ids


def view_rows(db: Db, dataset_id: int, view: str = "dv") -> list[dict[str, Any]]:
    """`dv_`/`de_` 뷰의 모든 행(읽기 전용 계정이 아니라 시험 도구)."""
    table = sa.Table(
        f"{view}_{dataset_id}", sa.MetaData(), autoload_with=db.engine, schema="bi_data"
    )
    with db.engine.connect() as conn:
        return [dict(r) for r in conn.execute(sa.select(table).order_by(table.c.row_id)).mappings()]


def dataset_hash(db: Db, dataset_id: int) -> str:
    with db.writer.connect() as conn:
        return conn.execute(
            sa.select(datasets.c.def_hash).where(datasets.c.id == dataset_id)
        ).scalar_one()
