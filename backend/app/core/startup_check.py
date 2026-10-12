"""backend 시작 자가 점검(04 §2-1 core, 03b 3-6 BY3, 03b 15-2).

앱 시작(lifespan)에서 `bi_app` 접속으로 아래를 확인하고 하나라도 어긋나면 **시작을 거부**한다
(fail-closed, `StartupCheckError`). 모든 질의는 SQLAlchemy Core 표현식이고 `pg_catalog`는
`table()/column()`으로 읽는다(`text()`·`exec_driver_sql` 금지).

1. 접속 역할 속성: SUPERUSER, CREATEROLE, CREATEDB, REPLICATION, BYPASSRLS 중 하나라도 있으면 거부.
   (db-bootstrap이 앞의 셋은 매 기동 다시 막지만 뒤의 둘은 막지 않으므로 여기서 확인한다.)
2. `standard_conforming_strings=on` (수식 글자 상수 완화책의 전제, 07 §4-3).
3. `bi_data` 객체 종류: 표·뷰·인덱스·제약만 있어야 한다. 열이 소유한 `Identity` 시퀀스
   (`row_id`)는 예외(AP-10). 독립 시퀀스·함수·그 밖의 타입·구체화 뷰 등은 거부한다
   (03c X-15 권한 상승 경로).
4. `bi_app`이 `public` schema에 `CREATE` 권한을 가지면 거부(03b 17-1 결정 5, 이전에는 경고).
5. 정적 `MetaData`의 표와 열이 DB에 있는지. alembic head와의 일치 확인은 대신하지 않는다:
   `bi_app`은 `alembic_version`을 읽을 수 없다(06 §4-2, 의도된 권한). `migrate` 서비스가 성공해야
   backend가 시작하는 compose 순서(D4)가 head 적용을 보장하고, 여기서는 표·열 존재로 확인한다.

점검이 채우는 **메모리 값**(`StartupReport`)이 `/health`의 `views`, `views_failed_count`,
`public_create`, `db_timezone`이 된다(05 H1, DB 비접속 유지). 오류 메시지에는 비밀을 넣지 않는다.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import (
    Connection,
    Engine,
    Text,
    cast,
    column,
    exists,
    func,
    inspect,
    literal,
    select,
    table,
)
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError

from app.db_metadata import DYNAMIC_SCHEMA, metadata

logger = logging.getLogger(__name__)

# 접속 재시도(DB가 아직 올라오지 않은 시작 순서 대비). 환경변수로 만들지 않는다.
CONNECT_ATTEMPTS = 10
CONNECT_DELAY_SECONDS = 2.0

# (pg_roles 열, 사용자에게 보이는 이름). 하나라도 true이면 시작을 거부한다.
FORBIDDEN_ROLE_ATTRIBUTES: tuple[tuple[str, str], ...] = (
    ("rolsuper", "SUPERUSER"),
    ("rolcreaterole", "CREATEROLE"),
    ("rolcreatedb", "CREATEDB"),
    ("rolreplication", "REPLICATION"),
    ("rolbypassrls", "BYPASSRLS"),
)

# `bi_data`에 있어도 되는 pg_class.relkind: r 표, v 뷰, i 인덱스. (S 시퀀스는 Identity만 따로 허용)
ALLOWED_RELKINDS = frozenset({"r", "v", "i"})
_RELKIND_NAMES = {
    "r": "표",
    "v": "뷰",
    "i": "인덱스",
    "S": "시퀀스",
    "m": "구체화 뷰",
    "c": "복합 타입",
    "f": "외부 표",
    "p": "분할 표",
    "I": "분할 인덱스",
    "t": "TOAST 표",
}
_MAX_LISTED = 10

_PG = "pg_catalog"
_pg_roles = table(
    "pg_roles",
    column("rolname"),
    column("rolsuper"),
    column("rolcreaterole"),
    column("rolcreatedb"),
    column("rolreplication"),
    column("rolbypassrls"),
    schema=_PG,
)
_pg_namespace = table("pg_namespace", column("oid"), column("nspname"), schema=_PG)
_pg_class = table(
    "pg_class",
    column("oid"),
    column("relname"),
    column("relkind"),
    column("relnamespace"),
    schema=_PG,
)
_pg_depend = table(
    "pg_depend",
    column("classid"),
    column("objid"),
    column("refclassid"),
    column("refobjid"),
    column("deptype"),
    schema=_PG,
)
_pg_proc = table("pg_proc", column("proname"), column("pronamespace"), schema=_PG)
_pg_type = table(
    "pg_type",
    column("oid"),
    column("typname"),
    column("typnamespace"),
    column("typtype"),
    column("typrelid"),
    column("typelem"),
    column("typcategory"),
    schema=_PG,
)


class StartupCheckError(RuntimeError):
    """시작 자가 점검 실패. 메시지는 비밀 없이 무엇이 문제인지만 적는다."""


@dataclass
class StartupReport:
    """점검이 채우는 메모리 값(`/health` 본문). 개수·불리언·시간대만 담는다(공개 응답)."""

    views: int = 0
    views_failed_count: int = 0
    public_create: bool | None = None
    db_timezone: str | None = None


def forbidden_attributes(attributes: dict[str, Any]) -> list[str]:
    """역할 속성 사전에서 허용되지 않는 속성 이름을 모은다. 알 수 없는 값(None)도 거부로 본다."""
    return [label for key, label in FORBIDDEN_ROLE_ATTRIBUTES if attributes.get(key) is not False]


def check_role_attributes(conn: Connection) -> None:
    columns = [column_name for column_name, _ in FORBIDDEN_ROLE_ATTRIBUTES]
    row = conn.execute(
        select(_pg_roles.c.rolname, *[_pg_roles.c[name] for name in columns]).where(
            _pg_roles.c.rolname == func.current_user()
        )
    ).first()
    if row is None:
        raise StartupCheckError("접속 중인 DB 역할의 속성을 확인하지 못해 시작하지 않는다.")
    bad = forbidden_attributes({name: row._mapping[name] for name in columns})
    if bad:
        raise StartupCheckError(
            f"DB 접속 역할 {row._mapping['rolname']}에 허용되지 않는 속성이 있어 시작하지 않는다: "
            f"{', '.join(bad)} (최소 권한 계정만 쓸 수 있다)."
        )


def check_standard_conforming_strings(conn: Connection) -> None:
    value = conn.execute(select(func.current_setting("standard_conforming_strings"))).scalar_one()
    if value != "on":
        raise StartupCheckError(
            "standard_conforming_strings가 on이 아니라 시작하지 않는다(글자 상수 완화책의 전제)."
        )


def unexpected_dynamic_objects(
    relations: list[tuple[int, str, str, bool]],
    types: list[tuple[int, str, str, int, int, str]],
    functions: list[str],
) -> list[str]:
    """`bi_data`에 있는 객체 중 허용 목록 밖인 것의 설명 목록(순수 함수, DB 없이 시험한다).

    - relations: (oid, 이름, relkind, identity_sequence 여부)
    - types: (oid, 이름, typtype, typrelid, typelem, typcategory)
    - functions: 함수 이름
    """
    found: list[str] = []
    allowed_class_oids: set[int] = set()
    for oid, name, relkind, owned_identity in relations:
        if relkind in ALLOWED_RELKINDS:
            if relkind in {"r", "v"}:
                allowed_class_oids.add(oid)
        elif relkind == "S" and owned_identity:
            continue
        else:
            found.append(f"{_RELKIND_NAMES.get(relkind, '알 수 없는 객체')} {name}")
    allowed_type_oids: set[int] = set()
    for oid, _name, typtype, typrelid, _typelem, _category in types:
        if typtype == "c" and typrelid in allowed_class_oids:
            allowed_type_oids.add(oid)  # 표·뷰의 행 타입은 표·뷰가 만든다.
    for _oid, name, _typtype, _typrelid, typelem, category in types:
        if _oid in allowed_type_oids:
            continue
        if category == "A" and typelem in allowed_type_oids:
            continue  # 행 타입의 배열 타입도 표·뷰가 만든다.
        found.append(f"타입 {name}")
    found.extend(f"함수 {name}" for name in functions)
    return found


def check_bi_data_objects(conn: Connection) -> None:
    namespace = (
        select(_pg_namespace.c.oid)
        .where(_pg_namespace.c.nspname == DYNAMIC_SCHEMA)
        .scalar_subquery()
    )
    identity_owned = exists(
        select(1).where(
            _pg_depend.c.objid == _pg_class.c.oid,
            _pg_depend.c.classid == func.to_regclass(cast(literal("pg_catalog.pg_class"), Text)),
            _pg_depend.c.deptype == "i",
        )
    )
    relations = [
        (int(r[0]), str(r[1]), str(r[2]), bool(r[3]))
        for r in conn.execute(
            select(_pg_class.c.oid, _pg_class.c.relname, _pg_class.c.relkind, identity_owned).where(
                _pg_class.c.relnamespace == namespace
            )
        )
    ]
    types = [
        (int(r[0]), str(r[1]), str(r[2]), int(r[3]), int(r[4]), str(r[5]))
        for r in conn.execute(
            select(
                _pg_type.c.oid,
                _pg_type.c.typname,
                _pg_type.c.typtype,
                _pg_type.c.typrelid,
                _pg_type.c.typelem,
                _pg_type.c.typcategory,
            ).where(_pg_type.c.typnamespace == namespace)
        )
    ]
    functions = [
        str(r[0])
        for r in conn.execute(
            select(_pg_proc.c.proname).where(_pg_proc.c.pronamespace == namespace)
        )
    ]
    found = unexpected_dynamic_objects(relations, types, functions)
    if found:
        listed = ", ".join(found[:_MAX_LISTED])
        more = f" 외 {len(found) - _MAX_LISTED}개" if len(found) > _MAX_LISTED else ""
        raise StartupCheckError(
            f"{DYNAMIC_SCHEMA}에 허용되지 않는 객체가 있어 시작하지 않는다"
            f"(표·뷰·인덱스·제약만 허용): {listed}{more}"
        )


def missing_static_columns(
    expected: dict[str, set[str]], actual: dict[str, set[str] | None]
) -> list[str]:
    """정적 표·열 중 DB에 없는 것의 설명 목록. actual[표] = None이면 표가 없다."""
    missing = []
    for name in sorted(expected):
        columns = actual.get(name)
        if columns is None:
            missing.append(f"표 {name}")
            continue
        missing.extend(f"열 {name}.{col}" for col in sorted(expected[name] - columns))
    return missing


def check_static_tables(conn: Connection) -> None:
    inspector = inspect(conn)
    expected = {t.name: {c.name for c in t.columns} for t in metadata.sorted_tables}
    actual: dict[str, set[str] | None] = {}
    for name in expected:
        if inspector.has_table(name):
            actual[name] = {c["name"] for c in inspector.get_columns(name)}
        else:
            actual[name] = None
    missing = missing_static_columns(expected, actual)
    if missing:
        raise StartupCheckError(
            "정적 표가 DB와 맞지 않아 시작하지 않는다(migrate가 끝났는지 확인): "
            + ", ".join(missing[:_MAX_LISTED])
        )


def read_public_create(conn: Connection) -> bool:
    return bool(
        conn.execute(
            select(func.has_schema_privilege(func.current_user(), "public", "CREATE"))
        ).scalar_one()
    )


def read_db_timezone(conn: Connection) -> str:
    return str(conn.execute(select(func.current_setting("TimeZone"))).scalar_one())


def collect_report(conn: Connection) -> StartupReport:
    """점검을 모두 실행한다. 어긋나면 `StartupCheckError`, 통과하면 `/health`용 값을 돌려준다."""
    check_role_attributes(conn)
    check_standard_conforming_strings(conn)
    check_bi_data_objects(conn)
    check_static_tables(conn)
    report = StartupReport(
        public_create=read_public_create(conn), db_timezone=read_db_timezone(conn)
    )
    if report.public_create:
        # `bi_app`이 public에 객체를 만들 수 있으면 정적 표 영역에 임의 객체를 둘 수 있다
        # (06 §4-2 기대: false). 03b 17-1 결정 5: 경고가 아니라 시작 거부다.
        raise StartupCheckError(
            "bi_app이 public schema에 CREATE 권한을 가지고 있어 시작하지 않는다"
            "(PUBLIC의 CREATE 회수 여부를 확인하세요)."
        )
    return report


def _sqlstate(exc: DBAPIError) -> str | None:
    args = getattr(exc.orig, "args", ())
    if args and isinstance(args[0], dict):
        code = args[0].get("C")
        return str(code) if code else None
    return None


def _is_connection_problem(exc: Exception) -> bool:
    """DB가 아직 안 올라왔거나 연결이 끊긴 경우만 재시도 대상이다(권한·인증 오류는 즉시 실패)."""
    if isinstance(exc, InterfaceError | OperationalError):
        return True
    if isinstance(exc, DBAPIError):
        code = _sqlstate(exc)
        return code is not None and (code.startswith("08") or code in {"57P03", "57P01"})
    return False


def run_startup_checks(
    engine: Engine,
    *,
    attempts: int = CONNECT_ATTEMPTS,
    delay: float = CONNECT_DELAY_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> StartupReport:
    """접속해 점검을 실행한다. 연결 문제만 재시도하고, 점검 실패는 바로 `StartupCheckError`다."""
    for attempt in range(1, attempts + 1):
        try:
            with engine.connect() as conn:
                return collect_report(conn)
        except StartupCheckError:
            raise
        except Exception as exc:
            if not _is_connection_problem(exc):
                # 원인 메시지에 접속 정보가 있을 수 있어 클래스 이름만 남기고 시작을 거부한다.
                raise StartupCheckError(
                    f"시작 자가 점검을 실행하지 못해 시작하지 않는다({type(exc).__name__})."
                ) from None
            logger.warning(
                "DB 연결 실패로 시작 자가 점검을 다시 시도한다(%d/%d): %s",
                attempt,
                attempts,
                type(exc).__name__,
            )
            if attempt < attempts:
                sleep(delay)
    raise StartupCheckError(
        f"DB에 연결하지 못해 시작 자가 점검을 마치지 못했다({attempts}회 시도). "
        "postgres와 migrate가 끝났는지 확인하세요."
    )
