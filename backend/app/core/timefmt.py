"""시각 표기(05 §1): ISO 8601 `+09:00`. 한국 표준시는 일광절약시간이 없어 고정 오프셋을 쓴다."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def to_kst_iso(value: datetime) -> str:
    """시각을 `2026-10-12T09:30:00+09:00` 형태로 바꾼다. 시간대가 없으면 UTC로 본다(SQLite 시험)."""
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(KST).replace(microsecond=0).isoformat()
