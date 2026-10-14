"""기준값 시험 공용 도구(FU-3): 항목·값을 소유자 연결로 심고 API로 부르는 짧은 함수들."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import sqlalchemy as sa

from app.db_metadata import reference_items, reference_values
from tests.conftest import Db


def add_item(db: Db, name: str, user_id: int, description: str | None = None) -> int:
    """항목 하나를 직접 만든다(API·감사를 거치지 않는 시험 준비용)."""
    with db.writer.begin() as conn:
        return conn.execute(
            sa.insert(reference_items)
            .values(name=name, description=description, created_by=user_id)
            .returning(reference_items.c.id)
        ).scalar_one()


def add_value(db: Db, item_id: int, year: int, value: Any, user_id: int) -> int:
    with db.writer.begin() as conn:
        return conn.execute(
            sa.insert(reference_values)
            .values(
                item_id=item_id, year=year, number_value=Decimal(str(value)), created_by=user_id
            )
            .returning(reference_values.c.id)
        ).scalar_one()


def set_value(db: Db, value_id: int, value: Any) -> None:
    """값을 직접 바꾼다(정정 API를 거치지 않는 시험 준비용: 소유자 연결)."""
    with db.writer.begin() as conn:
        conn.execute(
            sa.update(reference_values)
            .where(reference_values.c.id == value_id)
            .values(number_value=Decimal(str(value)))
        )


def value_rows(db: Db) -> list[dict[str, Any]]:
    return db.rows(reference_values, reference_values.c.id)


def item_rows(db: Db) -> list[dict[str, Any]]:
    return db.rows(reference_items, reference_items.c.id)


def api_add_item(call, name: str, description: str | None = None, login: str = "admin"):
    body: dict[str, Any] = {"name": name}
    if description is not None:
        body["description"] = description
    return call(login, "POST", "/api/reference-items", json=body)


def api_add_value(call, item_id: int, year: int, value: str, login: str = "admin"):
    return call(
        login, "POST", f"/api/reference-items/{item_id}/values", json={"year": year, "value": value}
    )


def api_update_value(call, item_id: int, value_id: int, value: str, login: str = "admin"):
    return call(
        login,
        "PATCH",
        f"/api/reference-items/{item_id}/values/{value_id}",
        json={"value": value},
    )
