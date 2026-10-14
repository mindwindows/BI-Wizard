"""마이그레이션 왕복 시험 틀 (D5, D6): upgrade -> downgrade -> upgrade 후 스냅샷을 비교한다.

테스트 DB(compose profile `test`의 `postgres-test`)에서 실행한다. db-bootstrap 직후의 빈 DB가
출발점이다.
```
docker compose --profile test up -d --wait postgres-test
docker compose --profile test run --rm --no-deps -e PGHOST=postgres-test db-bootstrap
docker compose --profile test run --rm --no-deps -e POSTGRES_HOST=postgres-test migrate \
    python -m migrations.roundtrip
```
순서: 스냅샷 A(base) -> upgrade head -> 스냅샷 B -> `alembic check` ->
downgrade 0007(CHECK 두 개만 옛 정의로, 표·권한 그대로) -> upgrade head(B와 같아야 함) ->
downgrade 0006(감사 기록 표만 사라짐) -> upgrade head(B와 같아야 함) ->
downgrade 0005(등록 표·감사 기록 표가 사라짐) -> upgrade head(B와 같아야 함) ->
downgrade 0004(수식·등록·감사 기록 표가 사라짐) -> upgrade head(B와 같아야 함) ->
downgrade 0003(0003 표·권한은 남고 0004~0007 표·권한이 사라짐.
0008은 표·권한 없이 CHECK 두 개만 교체) ->
upgrade head(B와 같아야 함) -> downgrade base ->
스냅샷 A'(A와 같아야 함) -> upgrade head -> 스냅샷 B'(B와 같아야 함).
접속은 `bi_owner`(비밀번호 `POSTGRES_OWNER_PASSWORD`)이다.

안전장치: DB의 현재 revision이 base(없음)가 아니면 아무것도 하지 않고 종료한다(이미 쓰고 있는 DB에서
`downgrade`를 돌리지 않는다. 운영 DB에서 downgrade는 쓰지 않는다).

스냅샷은 SQLAlchemy 구성요소(카탈로그 표 정의, Inspector)로만 읽는다. 정규화 항목(03c X-29):
schema ACL이 NULL인 것과 소유자 명시의 차이, 비어 있는 `alembic_version`(표가 남는 것).
복원 대상이 아닌 것: db-bootstrap이 만든 역할·멤버십·`bi_data` schema·`public` CREATE 권한
(출발 상태에 이미 있다).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, cast, func, select

from app.config import get_settings
from app.db import build_database_url

Snapshot = dict[str, Any]

_MANAGED_ROLES = ("bi_owner", "bi_app", "bi_readonly")
_SCHEMAS = ("public", "bi_data")


def _catalog(name: str, *columns: str) -> sa.TableClause:
    return sa.table(name, *[sa.column(c) for c in columns], schema="pg_catalog")


_PG_CLASS = _catalog("pg_class", "oid", "relname", "relkind", "relowner", "relnamespace", "relacl")
_PG_NAMESPACE = _catalog("pg_namespace", "oid", "nspname", "nspowner", "nspacl")
_PG_ROLES = _catalog(
    "pg_roles",
    "rolname",
    "rolsuper",
    "rolinherit",
    "rolcreaterole",
    "rolcreatedb",
    "rolcanlogin",
    "rolbypassrls",
    "rolconfig",
)
_PG_AUTH_MEMBERS = _catalog(
    "pg_auth_members", "roleid", "member", "admin_option", "inherit_option", "set_option"
)
_PG_ATTRIBUTE = _catalog("pg_attribute", "attrelid", "attname", "attnum", "attisdropped", "attacl")
_PG_DEFAULT_ACL = _catalog(
    "pg_default_acl", "defaclrole", "defaclnamespace", "defaclobjtype", "defaclacl"
)


def _acl(value: Any) -> list[str] | None:
    """`{a=UC/b,c=U/b}` 텍스트를 정렬된 목록으로 바꾼다(항목 순서 차이를 없앤다). NULL은 None."""
    if value is None:
        return None
    return sorted(part for part in str(value).strip("{}").split(",") if part)


def take_snapshot(engine: Engine) -> Snapshot:
    """역할 속성, 멤버십, schema/관계 ACL·소유자, 기본 권한, `public` 표 구조를 읽는다."""
    with engine.connect() as conn:
        owner_of = func.pg_get_userbyid
        text_type = sa.Text
        roles = conn.execute(
            select(
                _PG_ROLES.c.rolname,
                _PG_ROLES.c.rolsuper,
                _PG_ROLES.c.rolinherit,
                _PG_ROLES.c.rolcreaterole,
                _PG_ROLES.c.rolcreatedb,
                _PG_ROLES.c.rolcanlogin,
                _PG_ROLES.c.rolbypassrls,
                cast(_PG_ROLES.c.rolconfig, text_type),
            ).where(_PG_ROLES.c.rolname.in_(_MANAGED_ROLES))
        )
        memberships = conn.execute(
            select(
                owner_of(_PG_AUTH_MEMBERS.c.roleid),
                owner_of(_PG_AUTH_MEMBERS.c.member),
                _PG_AUTH_MEMBERS.c.admin_option,
                _PG_AUTH_MEMBERS.c.inherit_option,
                _PG_AUTH_MEMBERS.c.set_option,
            ).where(owner_of(_PG_AUTH_MEMBERS.c.member).in_(_MANAGED_ROLES))
        )
        schemas = conn.execute(
            select(
                _PG_NAMESPACE.c.nspname,
                owner_of(_PG_NAMESPACE.c.nspowner),
                cast(_PG_NAMESPACE.c.nspacl, text_type),
            ).where(_PG_NAMESPACE.c.nspname.in_(_SCHEMAS))
        )
        relations = conn.execute(
            select(
                _PG_NAMESPACE.c.nspname,
                _PG_CLASS.c.relname,
                _PG_CLASS.c.relkind,
                owner_of(_PG_CLASS.c.relowner),
                cast(_PG_CLASS.c.relacl, text_type),
            )
            .join(_PG_NAMESPACE, _PG_NAMESPACE.c.oid == _PG_CLASS.c.relnamespace)
            .where(_PG_NAMESPACE.c.nspname.in_(_SCHEMAS))
        )
        # 열 단위 권한(GRANT UPDATE (열) …)은 relacl에 없고 attacl에만 있다(0003부터 사용).
        column_acl = conn.execute(
            select(
                _PG_NAMESPACE.c.nspname,
                _PG_CLASS.c.relname,
                _PG_ATTRIBUTE.c.attname,
                cast(_PG_ATTRIBUTE.c.attacl, text_type),
            )
            .join(_PG_CLASS, _PG_CLASS.c.oid == _PG_ATTRIBUTE.c.attrelid)
            .join(_PG_NAMESPACE, _PG_NAMESPACE.c.oid == _PG_CLASS.c.relnamespace)
            .where(
                _PG_NAMESPACE.c.nspname.in_(_SCHEMAS),
                _PG_ATTRIBUTE.c.attnum > 0,
                _PG_ATTRIBUTE.c.attisdropped.is_(False),
                _PG_ATTRIBUTE.c.attacl.is_not(None),
            )
        )
        default_acl = conn.execute(
            select(
                owner_of(_PG_DEFAULT_ACL.c.defaclrole),
                func.coalesce(_PG_NAMESPACE.c.nspname, "(global)"),
                _PG_DEFAULT_ACL.c.defaclobjtype,
                cast(_PG_DEFAULT_ACL.c.defaclacl, text_type),
            ).select_from(
                _PG_DEFAULT_ACL.outerjoin(
                    _PG_NAMESPACE, _PG_NAMESPACE.c.oid == _PG_DEFAULT_ACL.c.defaclnamespace
                )
            )
        )
        snap: Snapshot = {
            "roles": sorted([*r[:7], _acl(r[7])] for r in roles),
            "memberships": sorted([str(x) for x in r] for r in memberships),
            "schemas": sorted([r[0], r[1], _acl(r[2])] for r in schemas),
            "relations": sorted([r[0], r[1], r[2], r[3], _acl(r[4])] for r in relations),
            "column_acl": sorted([r[0], r[1], r[2], _acl(r[3])] for r in column_acl),
            "default_acl": sorted([r[0], r[1], r[2], _acl(r[3])] for r in default_acl),
        }
        inspector = sa.inspect(conn)
        tables: dict[str, Any] = {}
        for table in sorted(inspector.get_table_names(schema="public")):
            tables[table] = {
                "columns": [
                    [c["name"], str(c["type"]), c["nullable"], str(c.get("default"))]
                    for c in inspector.get_columns(table, schema="public")
                ],
                "pk": inspector.get_pk_constraint(table, schema="public")["constrained_columns"],
                "fks": sorted(
                    str([f["constrained_columns"], f["referred_table"], f["referred_columns"]])
                    for f in inspector.get_foreign_keys(table, schema="public")
                ),
                "indexes": sorted(
                    str([i["name"], i["column_names"], i["unique"]])
                    for i in inspector.get_indexes(table, schema="public")
                ),
                # CHECK 제약(0008이 두 개를 교체하므로 정의까지 비교한다)
                "checks": sorted(
                    [c["name"], " ".join(c["sqltext"].split())]
                    for c in inspector.get_check_constraints(table, schema="public")
                ),
            }
        snap["public_tables"] = tables
        version = None
        if "alembic_version" in tables:
            table = sa.table("alembic_version", sa.column("version_num"), schema="public")
            version = sorted(r[0] for r in conn.execute(select(table.c.version_num)))
        snap["alembic_version"] = version
    return snap


def normalize(snapshot: Snapshot) -> Snapshot:
    """복원 대상이 아닌 차이를 없앤다: schema ACL NULL -> 소유자 명시, 빈 alembic_version."""
    result: Snapshot = {key: value for key, value in snapshot.items()}
    result["schemas"] = [
        [name, owner, acl if acl is not None else [f"{owner}=UC/{owner}"]]
        for name, owner, acl in snapshot["schemas"]
    ]
    result["relations"] = [
        row
        for row in snapshot["relations"]
        # 버전 표와 그 기본키 인덱스(alembic_version_pkc)는 downgrade 뒤에도 빈 채로 남는다.
        if not (row[0] == "public" and row[1] in {"alembic_version", "alembic_version_pkc"})
    ]
    result["public_tables"] = {
        name: value
        for name, value in snapshot["public_tables"].items()
        if name != "alembic_version"
    }
    result["alembic_version"] = snapshot["alembic_version"] or None
    return result


def diff(left: Snapshot, right: Snapshot) -> list[str]:
    """두 (정규화된) 스냅샷의 차이를 사람이 읽을 목록으로 돌려준다. 같으면 빈 목록."""
    problems: list[str] = []
    for key in sorted(set(left) | set(right)):
        a, b = left.get(key), right.get(key)
        if a == b:
            continue
        if isinstance(a, list) and isinstance(b, list):
            only_a = [row for row in a if row not in b]
            only_b = [row for row in b if row not in a]
            problems.append(f"{key}: 왼쪽에만 {only_a}, 오른쪽에만 {only_b}")
        else:
            problems.append(f"{key}: {a!r} != {b!r}")
    return problems


def _bi_data_acl(snapshot: Snapshot) -> list[str]:
    for name, owner, acl in normalize(snapshot)["schemas"]:
        if name == "bi_data":
            return [*acl, f"owner={owner}"]
    return []


def _has_default_acl(snapshot: Snapshot) -> bool:
    return any(
        role == "bi_app" and schema == "bi_data" and "bi_readonly=r/bi_app" in (acl or [])
        for role, schema, _kind, acl in snapshot["default_acl"]
    )


def expect_bootstrap_state(snapshot: Snapshot) -> list[str]:
    """db-bootstrap이 만든 출발 상태(역할 속성, 멤버십, bi_data 소유자)를 확인한다."""
    problems: list[str] = []
    roles = {row[0]: row for row in snapshot["roles"]}
    for name in _MANAGED_ROLES:
        row = roles.get(name)
        # row: 이름, 슈퍼유저, 상속, ROLE 생성, DB 생성, 로그인, RLS 우회, 설정
        if row is None:
            problems.append(f"역할 {name} 없음(db-bootstrap을 먼저 실행하세요)")
        elif row[1] or row[3] or row[4] or row[6] or not row[5]:
            problems.append(f"역할 {name}의 속성이 기대와 다름: {row[1:7]}")
    config = roles.get("bi_readonly", [None] * 8)[7] or []
    for expected in ("default_transaction_read_only=on", "statement_timeout=30s"):
        if expected not in config:
            problems.append(f"bi_readonly 설정에 {expected} 없음: {config}")
    if ["bi_app", "bi_owner", "False", "True", "False"] not in snapshot["memberships"]:
        problems.append(
            f"bi_owner는 bi_app의 INHERIT TRUE, SET FALSE 멤버여야 함: {snapshot['memberships']}"
        )
    owners = {row[0]: row[1] for row in snapshot["schemas"]}
    if owners.get("bi_data") != "bi_owner":
        problems.append(f"bi_data 소유자가 bi_owner가 아님: {owners.get('bi_data')}")
    return problems


def expect_privileges(snapshot: Snapshot, *, granted: bool) -> list[str]:
    """0002 권한이 head에서는 있고 base에서는 없는지 확인한다."""
    acl = _bi_data_acl(snapshot)
    problems: list[str] = []
    for expected in ("bi_app=UC/bi_owner", "bi_readonly=U/bi_owner"):
        if (expected in acl) is not granted:
            problems.append(
                f"bi_data ACL에 {expected}가 {'없음' if granted else '남아 있음'}: {acl}"
            )
    if _has_default_acl(snapshot) is not granted:
        problems.append(
            "bi_data 기본 권한(bi_app -> bi_readonly SELECT)이 "
            + ("없음" if granted else "남아 있음")
        )
    return problems


# 정적 표가 `bi_app`에 주는 권한(06 §2). 표 단위 ACL 문자: a INSERT, r SELECT, d DELETE, w UPDATE.
# UPDATE는 열 단위라 표 ACL에는 없고 열 ACL(`w`)에만 있다.
# 0003(권한 관리 표), 0004(데이터셋·열 정의 표), 0005(수식 표), 0006(Superset 등록 표),
# 0007(감사 기록 표)로 나눠 revision 단위 왕복을 확인한다.
ACCESS_TABLE_ACL = {
    "users": "bi_app=ar/bi_owner",
    "teams": "bi_app=ar/bi_owner",
    "team_members": "bi_app=ard/bi_owner",
}
ACCESS_COLUMN_ACL = {
    ("users", "display_name"),
    ("users", "is_admin"),
    ("users", "is_active"),
    ("teams", "name"),
    ("teams", "is_active"),
    ("team_members", "role"),
}
DATASET_TABLE_ACL = {
    "datasets": "bi_app=ar/bi_owner",
    "dataset_columns": "bi_app=ar/bi_owner",
}
DATASET_COLUMN_ACL = {
    ("datasets", "name"),
    ("datasets", "date_unit"),
    ("datasets", "base_date_column_id"),
    ("datasets", "status"),
    ("datasets", "def_version"),
    ("datasets", "def_hash"),
    ("dataset_columns", "display_name"),
    ("dataset_columns", "type"),
    ("dataset_columns", "required"),
    ("dataset_columns", "rules"),
    ("dataset_columns", "tag"),
    ("dataset_columns", "position"),
}
FORMULA_TABLE_ACL = {
    "formulas": "bi_app=ar/bi_owner",
    "formula_deps": "bi_app=ard/bi_owner",
}
FORMULA_COLUMN_ACL = {
    ("formulas", "expression"),
    ("formulas", "ast"),
    ("formulas", "ast_hash"),
}
SUPERSET_TABLE_ACL = {
    "superset_datasets": "bi_app=ar/bi_owner",
    "superset_dashboards": "bi_app=ar/bi_owner",
}
SUPERSET_COLUMN_ACL = {
    ("superset_datasets", "superset_dataset_id"),
    ("superset_datasets", "display_name"),
    ("superset_datasets", "sync_status"),
    ("superset_datasets", "synced_at"),
    ("superset_datasets", "last_error"),
    ("superset_dashboards", "name"),
    ("superset_dashboards", "is_active"),
}
# 0007: 읽기와 추가만(UPDATE·DELETE·TRUNCATE 없음, 열 단위 권한도 없음, 시퀀스 GRANT도 없음).
AUDIT_TABLE_ACL = {"audit_log": "bi_app=ar/bi_owner"}
AUDIT_COLUMN_ACL: set[tuple[str, str]] = set()
STATIC_TABLE_ACL = {
    **ACCESS_TABLE_ACL,
    **DATASET_TABLE_ACL,
    **FORMULA_TABLE_ACL,
    **SUPERSET_TABLE_ACL,
    **AUDIT_TABLE_ACL,
}
STATIC_COLUMN_ACL = (
    ACCESS_COLUMN_ACL
    | DATASET_COLUMN_ACL
    | FORMULA_COLUMN_ACL
    | SUPERSET_COLUMN_ACL
    | AUDIT_COLUMN_ACL
)


def expect_static_privileges(
    snapshot: Snapshot,
    *,
    granted: bool,
    table_acl: dict[str, str] | None = None,
    column_acl: set[tuple[str, str]] | None = None,
) -> list[str]:
    """정적 표와 `bi_app` 권한(표·열 단위)이 head에는 정확히 있고 base에는 없는지 확인한다.

    기본은 모든 정적 표(0003 + 0004 + 0005 + 0006 + 0007)다. 0008은 표·권한을 바꾸지 않고
    CHECK 두 개만 교체하므로 이 목록에 항목이 없다. `table_acl`/`column_acl`로 revision
    하나의
    표만
    볼 수 있다.
    `bi_readonly`와 PUBLIC에는 아무 권한도 없어야 한다.
    """
    expected_tables = STATIC_TABLE_ACL if table_acl is None else table_acl
    expected_columns = STATIC_COLUMN_ACL if column_acl is None else column_acl
    problems: list[str] = []
    relations = {
        r[1]: r for r in snapshot["relations"] if r[0] == "public" and r[1] in expected_tables
    }
    if not granted:
        if relations:
            problems.append(f"정적 표가 남아 있음: {sorted(relations)}")
        if any(r[0] == "public" and r[1] in expected_tables for r in snapshot["column_acl"]):
            problems.append("정적 표의 열 권한이 남아 있음")
        return problems
    for name, expected in expected_tables.items():
        row = relations.get(name)
        if row is None:
            problems.append(f"정적 표 {name} 없음")
            continue
        acl = row[4] or []
        # 소유자 항목은 PostgreSQL 버전마다 문자가 다르다(17부터 m 추가). bi_app 항목만 정확히 본다.
        others = [entry for entry in acl if not entry.startswith("bi_owner=")]
        if others != [expected]:
            problems.append(f"{name} 표 ACL이 기대와 다름: {acl}")
    actual_columns = {
        (r[1], r[2]): r[3] for r in snapshot["column_acl"] if r[0] == "public" and r[1] in relations
    }
    if set(actual_columns) != expected_columns:
        problems.append(f"열 단위 UPDATE 권한 열이 기대와 다름: {sorted(actual_columns)}")
    for key, acl in actual_columns.items():
        if acl != ["bi_app=w/bi_owner"]:
            problems.append(f"{key} 열 ACL이 기대와 다름: {acl}")
    return problems


def expect_archive_checks(snapshot: Snapshot, *, archived: bool) -> list[str]:
    """0008의 두 CHECK 정의: head에서는 `archived`와 보관·복구 행위가 허용되고 0007에서는 아니다.

    제약 이름은 `op.f`로 한 번만 붙어야 한다(`ck_datasets_ck_datasets_status` 같은 이중 이름 금지).
    """
    problems: list[str] = []
    tables = snapshot["public_tables"]
    names = {t: {c[0]: c[1] for c in tables[t]["checks"]} for t in ("datasets", "audit_log")}
    for table, name, marker in (
        ("datasets", "ck_datasets_status", "'archived'"),
        ("audit_log", "ck_audit_log_action", "'dataset.archive'"),
    ):
        text = names[table].get(name)
        if text is None:
            problems.append(f"{table}.{name} 제약이 없다")
            continue
        if (marker in text) != archived:
            problems.append(f"{name} 정의가 기대와 다름(archived={archived}): {text}")
    if archived:
        restore = names["audit_log"].get("ck_audit_log_action", "")
        if "'dataset.restore'" not in restore:
            problems.append("ck_audit_log_action에 dataset.restore가 없다")
    doubled = [n for t in names.values() for n in t if n.count("ck_") > 1]
    if doubled:
        problems.append(f"제약 이름이 이중으로 붙었다: {doubled}")
    return problems


def _current_revision(engine: Engine) -> str | None:
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def main() -> int:
    backend_dir = Path(__file__).resolve().parent.parent
    config = Config(str(backend_dir / "alembic.ini"))
    heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) != 1:
        print(f"[roundtrip] 실패: head가 {len(heads)}개입니다: {heads}", file=sys.stderr)
        return 1

    engine = sa.create_engine(
        build_database_url(get_settings(), "owner"), poolclass=sa.pool.NullPool
    )
    current = _current_revision(engine)
    if current is not None:
        print(
            f"[roundtrip] 중단: DB의 현재 revision이 {current}입니다. "
            "빈 테스트 DB(profile test)에서만 실행하세요.",
            file=sys.stderr,
        )
        return 2

    failures: list[str] = []

    def step(name: str, problems: list[str]) -> None:
        failures.extend(f"{name}: {p}" for p in problems)
        print(f"[roundtrip] {name}: {'실패 ' + str(len(problems)) + '건' if problems else '통과'}")

    base0 = take_snapshot(engine)
    step("출발 상태(db-bootstrap)", expect_bootstrap_state(base0))
    step("출발 상태 권한 없음", expect_privileges(base0, granted=False))
    step("출발 상태 정적 표 없음", expect_static_privileges(base0, granted=False))

    command.upgrade(config, "head")
    head1 = take_snapshot(engine)
    step("upgrade 후 권한", expect_privileges(head1, granted=True))
    step("upgrade 후 정적 표 권한", expect_static_privileges(head1, granted=True))
    try:
        command.check(config)
        step("alembic check", [])
    except Exception as error:
        step("alembic check", [f"{type(error).__name__}: {error}"])

    step("upgrade 후 0008 CHECK 정의", expect_archive_checks(head1, archived=True))

    # 0008(CHECK 두 개 교체) 한 단계만: 내리면 0007 상태(옛 정의), 올리면 head와 같다. 표·권한은
    # 바뀌지 않는다. 보관 행·보관 감사 행이 있을 때의 거부는 pytest(PostgreSQL)가 확인한다.
    command.downgrade(config, "0007")
    step8 = take_snapshot(engine)
    step("0008 downgrade 후 옛 CHECK 정의", expect_archive_checks(step8, archived=False))
    step("0008 downgrade 후 정적 표 권한 유지", expect_static_privileges(step8, granted=True))
    step("0008 downgrade 후 bi_data 권한 유지", expect_privileges(step8, granted=True))
    command.upgrade(config, "head")
    step("0008 재 upgrade 후 상태 복원", diff(normalize(head1), normalize(take_snapshot(engine))))

    # 0007(감사 기록 표) 한 단계만: 내리면 0006 상태(감사 기록 표만 사라짐), 올리면 head와 같다.
    # 주의: downgrade는 감사 기록 전체를 지운다(빈 시험 DB 전용, 03b 29-3 사용자 승인 2026-10-14).
    command.downgrade(config, "0006")
    step7 = take_snapshot(engine)
    step(
        "0007 downgrade 후 0006 정적 표 권한 유지",
        expect_static_privileges(
            step7,
            granted=True,
            table_acl={
                **ACCESS_TABLE_ACL,
                **DATASET_TABLE_ACL,
                **FORMULA_TABLE_ACL,
                **SUPERSET_TABLE_ACL,
            },
            column_acl=(
                ACCESS_COLUMN_ACL | DATASET_COLUMN_ACL | FORMULA_COLUMN_ACL | SUPERSET_COLUMN_ACL
            ),
        ),
    )
    step(
        "0007 downgrade 후 감사 기록 표 없음",
        expect_static_privileges(
            step7, granted=False, table_acl=AUDIT_TABLE_ACL, column_acl=AUDIT_COLUMN_ACL
        ),
    )
    step("0007 downgrade 후 bi_data 권한 유지", expect_privileges(step7, granted=True))
    command.upgrade(config, "head")
    step("0007 재 upgrade 후 상태 복원", diff(normalize(head1), normalize(take_snapshot(engine))))

    # 0006(Superset 등록 표) 한 단계만: 0005까지 내리면 0005 상태(등록·감사 기록 표가 사라짐),
    # 올리면 head와 같다.
    command.downgrade(config, "0005")
    step6 = take_snapshot(engine)
    step(
        "0006 downgrade 후 0005 정적 표 권한 유지",
        expect_static_privileges(
            step6,
            granted=True,
            table_acl={**ACCESS_TABLE_ACL, **DATASET_TABLE_ACL, **FORMULA_TABLE_ACL},
            column_acl=ACCESS_COLUMN_ACL | DATASET_COLUMN_ACL | FORMULA_COLUMN_ACL,
        ),
    )
    step(
        "0006 downgrade 후 등록·감사 기록 표 없음",
        expect_static_privileges(
            step6,
            granted=False,
            table_acl={**SUPERSET_TABLE_ACL, **AUDIT_TABLE_ACL},
            column_acl=SUPERSET_COLUMN_ACL | AUDIT_COLUMN_ACL,
        ),
    )
    step("0006 downgrade 후 bi_data 권한 유지", expect_privileges(step6, granted=True))
    command.upgrade(config, "head")
    step("0006 재 upgrade 후 상태 복원", diff(normalize(head1), normalize(take_snapshot(engine))))

    # 0005(수식 표) 한 단계만: 0004까지 내리면 0004 상태(수식·등록·감사 기록 표가 사라짐),
    # 올리면 head와 같다.
    command.downgrade(config, "0004")
    step5 = take_snapshot(engine)
    step(
        "0005 downgrade 후 0004 정적 표 권한 유지",
        expect_static_privileges(
            step5,
            granted=True,
            table_acl={**ACCESS_TABLE_ACL, **DATASET_TABLE_ACL},
            column_acl=ACCESS_COLUMN_ACL | DATASET_COLUMN_ACL,
        ),
    )
    step(
        "0005 downgrade 후 수식·등록·감사 기록 표 없음",
        expect_static_privileges(
            step5,
            granted=False,
            table_acl={**FORMULA_TABLE_ACL, **SUPERSET_TABLE_ACL, **AUDIT_TABLE_ACL},
            column_acl=FORMULA_COLUMN_ACL | SUPERSET_COLUMN_ACL | AUDIT_COLUMN_ACL,
        ),
    )
    step("0005 downgrade 후 bi_data 권한 유지", expect_privileges(step5, granted=True))
    command.upgrade(config, "head")
    step("0005 재 upgrade 후 상태 복원", diff(normalize(head1), normalize(take_snapshot(engine))))

    # 0004(데이터셋·열 정의 표) 한 단계: 0003까지 내리면 0003 상태(권한 관리 표만), 올리면
    # head와 같다.
    command.downgrade(config, "0003")
    mid = take_snapshot(engine)
    step(
        "0004 downgrade 후 0003 정적 표 권한 유지",
        expect_static_privileges(
            mid, granted=True, table_acl=ACCESS_TABLE_ACL, column_acl=ACCESS_COLUMN_ACL
        ),
    )
    step(
        "0004 downgrade 후 데이터셋 표 없음",
        expect_static_privileges(
            mid,
            granted=False,
            table_acl={
                **DATASET_TABLE_ACL,
                **FORMULA_TABLE_ACL,
                **SUPERSET_TABLE_ACL,
                **AUDIT_TABLE_ACL,
            },
            column_acl=(
                DATASET_COLUMN_ACL | FORMULA_COLUMN_ACL | SUPERSET_COLUMN_ACL | AUDIT_COLUMN_ACL
            ),
        ),
    )
    step("0004 downgrade 후 bi_data 권한 유지", expect_privileges(mid, granted=True))
    command.upgrade(config, "head")
    step("0004 재 upgrade 후 상태 복원", diff(normalize(head1), normalize(take_snapshot(engine))))

    command.downgrade(config, "base")
    base2 = take_snapshot(engine)
    step("downgrade 후 출발 상태 복원", diff(normalize(base0), normalize(base2)))

    command.upgrade(config, "head")
    head3 = take_snapshot(engine)
    step("재 upgrade 후 상태 복원", diff(normalize(head1), normalize(head3)))
    engine.dispose()

    for failure in failures:
        print(f"[roundtrip] {failure}", file=sys.stderr)
    print(
        "[roundtrip] " + ("실패" if failures else "통과: upgrade -> downgrade -> upgrade 왕복 일치")
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
