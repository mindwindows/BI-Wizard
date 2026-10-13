"""데이터셋 하나의 Superset 동기화 절차(멱등, 08 §2-1)와 대조(시작 점검)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.dataset.service import SyncSource
from app.ddl.names import column_name
from app.superset.client import DatasetApi
from app.superset.constants import DATABASE_NAME, SCHEMA
from app.superset.errors import SupersetRejected
from app.superset.naming import column_label, superset_name, virtual_sql


@dataclass(frozen=True)
class SyncPlan:
    """동기화가 Superset에 만들어야 하는 모습: 이름, 고정 SQL, 열 표시 이름."""

    dataset_id: int
    name: str
    sql: str
    display_names: dict[int, str]

    @classmethod
    def from_source(cls, source: SyncSource) -> SyncPlan:
        return cls(
            dataset_id=source.dataset_id,
            name=superset_name(source.team_name, source.name),
            sql=virtual_sql(source.dataset_id),
            display_names={column_id: label for column_id, label in source.columns},
        )

    def labels_for(self, superset_columns: list[dict]) -> dict[str, str]:
        """Superset 열 이름 -> 우리가 정한 표시 이름(정의에 없는 열은 빠진다)."""
        labels: dict[str, str] = {}
        for column in superset_columns:
            has, label = column_label(column["column_name"], self.display_names)
            if has and label is not None:
                labels[column["column_name"]] = label
        return labels


def _find_existing(api: DatasetApi, plan: SyncPlan, stored_id: int | None) -> int | None:
    """포털이 보관한 번호 → 고정 SQL 조회 순서로 이미 등록된 데이터셋을 찾는다."""
    if stored_id is not None:
        found = api.get(stored_id)
        if found is not None and found["sql"] == plan.sql:
            return stored_id
    hits = api.find_by_sql(plan.sql, SCHEMA)
    if hits:
        return min(int(hit["id"]) for hit in hits)
    return None


def sync_dataset(
    api: DatasetApi,
    plan: SyncPlan,
    *,
    stored_id: int | None,
    on_created: Callable[[int], None],
) -> int:
    """찾기 → (없으면) 만들기 → 새로고침 → 전체 열 표시 이름 갱신. Superset 데이터셋 번호를
    돌려준다.

    같은 데이터셋을 다시 돌려도 Superset에 하나만 있다(고정 SQL로 찾고, 중복 이름 422는 같은 SQL이면
    채택). 사유는 `SupersetUnavailable`/`SupersetRejected`의 코드로만 나온다.
    """
    database_id = api.database_id()
    existing = _find_existing(api, plan, stored_id)
    created = False
    if existing is None:
        new_id = api.create(database_id=database_id, schema=SCHEMA, name=plan.name, sql=plan.sql)
        if new_id is None:  # 같은 이름이 이미 있다: 같은 SQL이면 채택하고, 아니면 이름 충돌이다.
            same = [
                int(hit["id"])
                for hit in api.find_by_name(plan.name, SCHEMA)
                if hit.get("sql") == plan.sql
            ]
            if not same:
                raise SupersetRejected("NAME_CONFLICT")
            existing = min(same)
        else:
            existing = new_id
            created = True
            on_created(new_id)  # 곧바로 번호를 기록한다(크래시 뒤 중복 등록 방지)
    if not created:
        api.refresh(existing)  # 뷰의 열 변화 반영(새로 만든 데이터셋은 방금 열을 읽었다)
    for attempt in range(2):
        current = api.get(existing)
        if current is None:
            raise SupersetRejected("BAD_RESPONSE")
        database_name = current["database_name"]
        if database_name is not None and database_name != DATABASE_NAME:
            raise SupersetRejected("DB_MISMATCH")
        labels = plan.labels_for(current["columns"])
        ok = api.put_names(
            existing, table_name=plan.name, columns=current["columns"], labels=labels
        )
        if ok:
            return existing
        # "열이 없다"는 422: 방금 읽은 열이 그새 바뀐 것이다. 다시 읽고 한 번 더 보낸다.
        if attempt == 1:
            raise SupersetRejected("REJECTED_422")
    raise SupersetRejected("REJECTED_422")  # pragma: no cover


def is_in_sync(api: DatasetApi, plan: SyncPlan, stored_id: int | None) -> bool:
    """`registered` 데이터셋이 아직 맞는지 읽기만 해서 확인한다(시작 점검 ①, 결정 E).

    이름·SQL·열 수(정의의 모든 열이 Superset에 있는가)·열 표시 이름이 다 같으면 참이다.
    """
    if stored_id is None:
        return False
    current = api.get(stored_id)
    if current is None or current["sql"] != plan.sql or current["table_name"] != plan.name:
        return False
    by_name = {c["column_name"]: c for c in current["columns"]}
    expected = {"team", "row_id", *(column_name(cid) for cid in plan.display_names)}
    if set(by_name) != expected:
        return False
    return all(
        by_name[name]["verbose_name"] == label
        for name, label in plan.labels_for(current["columns"]).items()
    )
