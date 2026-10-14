"""기준값 로직(05 §2-8 R1~R5, 06 §2-2·§5). 트랜잭션은 여기서 명시적으로 commit/rollback한다.

- 쓰기(R2·R4·R5)는 `reference_items` 행 하나만 `FOR NO KEY UPDATE`로 잡고 `datasets`·`ds_`·
  `dataset_columns`·`superset_*`는 건드리지 않는다(06 §5). 같은 항목에 대한 관리자 쓰기끼리만 서로
  기다린다. 락 대기 초과·교착은 503 `WRITE_BUSY`다.
- 판정 순서: 항목·값 없음 404 -> 값 규칙 422 -> 중복 409 -> 쓰기. R5의 "숫자로 같은 값"은
  404·422 뒤,
  쓰기 앞이다(롤백 후 200, 감사 0건).
- 감사 기록(04 §5-1): 쓰기 함수 끝(커밋 앞)에서 `audit.record`를 정확히 한 번 부른다. 변경이 없거나
  실패·롤백이면 기록도 없다(같은 트랜잭션). `reference_value.update`의 `value_from`·`value_to`는
  기준값(포털 전역 설정값)이며 행 값이 아니다(06 §2-1 ③ 예외).
- 이 모듈은 `formula`·`dataset`을 import하지 않는다. 수식 엔진은 `item_ids_by_name`·`get_item`만
  읽는다(04 §2-2).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

from sqlalchemy import func, literal, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app import audit
from app.auth import CurrentUser
from app.auth.names import display_names
from app.core.db_errors import is_lock_conflict
from app.core.errors import AppError, already_exists, not_found, validation_failed, write_busy
from app.core.timefmt import to_kst_iso
from app.reference import repo
from app.reference import values as rules

# 기준값 쓰기의 락 대기 한도(행 쓰기와 같은 값, 06 §5, PostgreSQL `lock_timeout` 표기).
WRITE_LOCK_TIMEOUT = "3000ms"

_VALUE_TAKEN = "이미 그 연도의 값이 있습니다. 값을 바꾸려면 정정을 쓰세요."
_NAME_TAKEN = "이미 사용 중인 기준값 항목 이름입니다."


# --- 공통 ----


@contextmanager
def _write(session: Session) -> Iterator[None]:
    """쓰기 트랜잭션 경계: 어떤 오류든 롤백하고, 락 대기 초과·교착은 `WRITE_BUSY`로 바꾼다."""
    try:
        if session.get_bind().dialect.name == "postgresql":
            session.execute(
                select(func.set_config("lock_timeout", literal(WRITE_LOCK_TIMEOUT), True))
            )
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


def _user_ref(names: dict[int, str], user_id: int) -> dict[str, Any]:
    return {"id": int(user_id), "display_name": names.get(int(user_id), "")}


def _item_dict(row: Any, names: dict[int, str]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "name": row["name"],
        "description": row["description"],
        "value_count": int(row["value_count"]),
        "year_min": int(row["year_min"]) if row["year_min"] is not None else None,
        "year_max": int(row["year_max"]) if row["year_max"] is not None else None,
        "created_by": _user_ref(names, row["created_by"]),
        "created_at": to_kst_iso(row["created_at"]),
    }


def _value_dict(row: Any, names: dict[int, str]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "item_id": int(row["item_id"]),
        "year": int(row["year"]),
        "value": rules.decimal_text(Decimal(row["number_value"])),
        "created_by": _user_ref(names, row["created_by"]),
        "created_at": to_kst_iso(row["created_at"]),
    }


def _validate_value(raw: str) -> Decimal:
    value, code = rules.parse_value(raw)
    if code is not None:
        raise validation_failed([("value", code)])
    assert value is not None  # noqa: S101 - 코드가 없으면 값이 있다
    return value


# --- 수식 엔진이 읽는 함수(읽기 전용) ----


def item_ids_by_name(session: Session) -> dict[str, int]:
    """항목 이름(NFC) -> 번호. `formula`가 컴파일 때 쓰는 유일한 길이다(잠금 없는 SELECT)."""
    return repo.name_to_id(session)


def get_item(session: Session, item_id: int) -> dict[str, Any]:
    """항목 번호와 이름(없으면 404). 정정 영향 조회(R6)가 쓴다."""
    row = repo.get_item(session, item_id)
    if row is None:
        raise not_found()
    return {"id": int(row["id"]), "name": row["name"]}


# --- R1·R3 읽기 ----


def list_items(session: Session, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    rows = repo.list_items(session, limit, offset)
    total = repo.count_items(session)
    names = display_names(session, [r["created_by"] for r in rows])
    items = [_item_dict(r, names) for r in rows]
    session.rollback()
    return items, total


def list_values(
    session: Session, item_id: int, limit: int, offset: int
) -> tuple[list[dict[str, Any]], int]:
    if repo.get_item(session, item_id) is None:
        session.rollback()
        raise not_found()
    rows = repo.list_values(session, item_id, limit, offset)
    total = repo.count_values(session, item_id)
    names = display_names(session, [r["created_by"] for r in rows])
    items = [_value_dict(r, names) for r in rows]
    session.rollback()
    return items, total


# --- R2 항목 추가 ----


def create_item(
    session: Session, actor: CurrentUser, *, name: str, description: str | None
) -> dict[str, Any]:
    """R2: 항목 추가(`INSERT … ON CONFLICT (name) DO NOTHING`, 같은 이름이면 409)."""
    with _write(session):
        row = repo.insert_item(session, name=name, description=description, created_by=actor.id)
        if row is None:
            raise already_exists("name", _NAME_TAKEN)
        audit.record(
            session,
            actor=actor,
            action="reference.create",
            target_id=int(row["id"]),
            target_name=row["name"],
            details={"description_length": len(description) if description else 0},
        )
        created = _item_dict(
            {**row, "value_count": 0, "year_min": None, "year_max": None},
            {actor.id: actor.display_name},
        )
        session.commit()
    return created


# --- R4 연도 값 추가 ----


def add_value(
    session: Session, actor: CurrentUser, item_id: int, *, year: int, value: str
) -> dict[str, Any]:
    """R4: 연도 값 추가. 순서: 항목 잠금(404) -> 값 규칙(422) -> 중복(409) -> INSERT -> 감사."""
    with _write(session):
        item = repo.lock_item(session, item_id)
        if item is None:
            raise not_found()
        problems: list[tuple[str, str]] = []
        year_code = rules.year_problem(year)
        if year_code is not None:
            problems.append(("year", year_code))
        number, value_code = rules.parse_value(value)
        if value_code is not None:
            problems.append(("value", value_code))
        if problems:
            raise validation_failed(problems)
        assert number is not None  # noqa: S101
        row = repo.insert_value(
            session, item_id=item_id, year=year, value=number, created_by=actor.id
        )
        if row is None:
            raise already_exists("year", _VALUE_TAKEN)
        out = _value_dict(row, {actor.id: actor.display_name})
        audit.record(
            session,
            actor=actor,
            action="reference_value.add",
            target_id=item_id,
            target_name=item["name"],
            details={"year": year, "value": out["value"]},
        )
        session.commit()
    return out


# --- R5 정정 ----


def update_value(
    session: Session, actor: CurrentUser, item_id: int, value_id: int, *, value: str
) -> dict[str, Any]:
    """R5: 정정. 순서: 항목 잠금(404) -> 값 조회(404) -> 값 규칙(422) -> 같은 값이면
    롤백·200 -> UPDATE -> 감사. 마지막 쓰기가 이기며 이전·이후 값이 감사에 남는다."""
    with _write(session):
        item = repo.lock_item(session, item_id)
        if item is None:
            raise not_found()
        current = repo.get_value(session, item_id, value_id)
        if current is None:
            raise not_found()
        number = _validate_value(value)
        previous = Decimal(current["number_value"])
        names = display_names(session, [current["created_by"]])
        if number == previous:  # 숫자로 같은 값(1.0과 1.00도 같다): 아무것도 바꾸지 않는다
            out = {
                "value": _value_dict(current, names),
                "previous_value": rules.decimal_text(previous),
                "changed": False,
            }
            session.rollback()  # 잠금 해제
            return out
        row = repo.update_value(session, value_id, number)
        result = _value_dict(row, names)
        audit.record(
            session,
            actor=actor,
            action="reference_value.update",
            target_id=item_id,
            target_name=item["name"],
            details={
                "year": int(row["year"]),
                "value_from": rules.decimal_text(previous),
                "value_to": result["value"],
            },
        )
        out = {"value": result, "previous_value": rules.decimal_text(previous), "changed": True}
        session.commit()
    return out
