"""감사 기록 시험 공용 도구: 감사 행 읽기, 정적 표 스냅샷, 실패 주입."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.ports import DefinitionHooks
from app.db_metadata import (
    DYNAMIC_SCHEMA,
    audit_log,
    dataset_columns,
    datasets,
    formula_deps,
    formulas,
    reference_items,
    reference_values,
    superset_dashboards,
    superset_datasets,
    team_members,
    teams,
    users,
)
from app.formula.hook import FormulaDefinitionHook
from app.formula.status import ViewStatus
from app.main import create_app
from tests.api_helpers import World, make_caller
from tests.conftest import Db


def audit_rows(db: Db) -> list[dict[str, Any]]:
    """감사 행 전부(번호 순). 시험 도구라 소유자 연결로 읽는다."""
    return db.rows(audit_log, audit_log.c.id)


def audit_rows_of(db: Db, action: str) -> list[dict[str, Any]]:
    return [r for r in audit_rows(db) if r["action"] == action]


def static_snapshot(db: Db) -> tuple[Any, ...]:
    """감사 기록을 뺀 정적 표 전체와 동적 객체 이름. 롤백됐는지 비교하는 데 쓴다."""
    inspector = sa.inspect(db.engine)
    dynamic = sorted(
        [*inspector.get_table_names(schema=DYNAMIC_SCHEMA)]
        + [f"view:{n}" for n in inspector.get_view_names(schema=DYNAMIC_SCHEMA)]
    )
    return (
        db.rows(users, users.c.id),
        db.rows(teams, teams.c.id),
        db.rows(team_members, team_members.c.team_id, team_members.c.user_id),
        db.rows(datasets, datasets.c.id),
        db.rows(dataset_columns, dataset_columns.c.id),
        db.rows(formulas, formulas.c.column_id),
        db.rows(formula_deps, formula_deps.c.column_id, formula_deps.c.depends_on_column_id),
        db.rows(superset_datasets, superset_datasets.c.dataset_id),
        db.rows(superset_dashboards, superset_dashboards.c.id),
        db.rows(reference_items, reference_items.c.id),
        db.rows(reference_values, reference_values.c.id),
        dynamic,
    )


class InjectedFailure(RuntimeError):
    """시험이 일부러 일으킨 실패(응답은 500 INTERNAL_ERROR가 된다)."""


@contextmanager
def failing_commit(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """다음 `Session.commit()`을 실패시킨다(쓰기는 이미 끝났고 커밋만 안 된 중간 실패)."""

    def boom(self: Session) -> None:
        raise InjectedFailure("commit failure")

    with monkeypatch.context() as patch:  # 이 안에서 건 대체만 되돌린다(다른 fixture의 것은 둔다)
        patch.setattr(Session, "commit", boom)
        yield


@contextmanager
def failing_audit_insert(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """감사 INSERT만 실패시킨다(변경은 이미 실행된 뒤라 같이 롤백돼야 한다)."""

    def boom(*args: Any, **kwargs: Any) -> None:
        raise InjectedFailure("audit insert failure")

    with monkeypatch.context() as patch:
        patch.setattr("app.audit.repo.insert_entry", boom)
        yield


@dataclass
class Ctx:
    """감사 시험 한 건의 환경: 호출기, DB, 시험 세계, 훅 실패 스위치, 시나리오가 채우는 값."""

    call: Callable[..., Any]
    db: Db
    world: World
    boom_armed: dict[str, bool]
    vars: dict[str, Any] = field(default_factory=dict)

    def uid(self, login: str) -> int:
        return self.world.ids[login]


@pytest.fixture
def ctx(db: Db, world: World, stub_settings, sync) -> Iterator[Ctx]:
    """서버 오류(500)를 예외로 올리지 않는 클라이언트. 훅은 실제 formula 훅 + 실패 주입 훅.

    `tests/conftest.py`가 이 fixture를 가져와 audit 시험 파일이 함께 쓴다.
    """
    armed = {"on": False}
    hooks = DefinitionHooks()
    hooks.register(FormulaDefinitionHook(ViewStatus()))

    def boom(session, dataset_id):
        if armed["on"]:
            raise InjectedFailure("hook failure")
        return None

    hooks.register(boom)
    app = create_app(stub_settings, engine=db.engine, dataset_sync=sync, definition_hooks=hooks)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield Ctx(make_caller(client), db, world, armed)
