"""목록 응답 공통 형태(05 §1 목록).

쿼리 `limit`(기본 50, 최대 200)·`offset`, 응답 `{items, total, limit, offset}`.
"""

from __future__ import annotations

from pydantic import BaseModel

LIST_LIMIT_DEFAULT = 50
LIST_LIMIT_MAX = 200


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int
