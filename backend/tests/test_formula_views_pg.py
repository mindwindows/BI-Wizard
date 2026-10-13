"""뷰 생성·권한·정의 해시·완화책 시험(07 §4·§8, 06 §3-4·§4-2). 실제 PostgreSQL 필요.

런타임 DDL은 `bi_app`으로 실행한다(03b 5-2 Z6). 주입 방어는 층별로 시험한다(07 §4-4):
- L0 전체 구성: 완화책 ① 세션 설정 고정 + ② 역슬래시 등 거부 + ③ 생성 후 읽기 확인.
- L1 ②를 끄고 ①만, L2 ①을 끄고 서버 설정을 `off`로 바꾼 시나리오 A에서 ③만,
- L3 렌더러 단독(`on`·`off` 두 설정).
판정은 "효과 0건"이다: `bi_data.evil`이 없고, `public.t` 행 수가 그대로이며, 뷰의 글자 값이 입력과
같거나 롤백 뒤 변경 전 상태다.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import pg8000
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app import ddl
from app.config import Settings
from app.core.db_errors import sqlstate
from app.dataset import service as dataset_service
from app.db import build_database_url, create_db_engine
from app.db_metadata import DYNAMIC_SCHEMA
from app.ddl.dynamic import RenderedSelect
from app.formula import literals, repo
from app.formula.hook import make_probe
from app.formula.literals import LITERALS, render_literal_sql
from app.formula.views import (
    build_column_infos,
    build_plan,
    compile_all,
    echo_selects,
    source_columns,
    source_table,
    text_constants,
)
from app.main import create_app
from tests.api_helpers import make_caller
from tests.conftest import Db
from tests.formula_api_helpers import (
    add_column,
    add_formula,
    dataset_hash,
    err,
    insert_rows,
    make_dataset,
    post_formula,
    put_formula,
    version,
    view_rows,
)
from tests.formula_injection_cases import BACKSLASH_CASES, INJECTION_CASES, formula_of


@pytest.fixture
def db(pg_app_engine, pg_owner_engine, clean_pg):
    yield Db("pg", pg_app_engine, pg_owner_engine)


@pytest.fixture
def ds(api, world):
    dataset = make_dataset(api, world, "뷰 시험")
    return {
        "id": dataset["id"],
        "매출": add_column(api, dataset["id"], "매출")["id"],
        "비용": add_column(api, dataset["id"], "비용")["id"],
        "이름": add_column(api, dataset["id"], "이름", "text")["id"],
    }


def columns_of(db: Db, view: str) -> list[tuple[str, str]]:
    return [
        (c["name"], str(c["type"]))
        for c in sa.inspect(db.engine).get_columns(view, schema=DYNAMIC_SCHEMA)
    ]


# --- 구성: dv_·de_ 모양 ----


def test_every_dataset_has_dv_with_team_column_even_without_formulas(api, db, world):
    dataset = make_dataset(api, world, "수식 없음")
    assert columns_of(db, f"dv_{dataset['id']}") == [("team", "TEXT"), ("row_id", "BIGINT")]
    assert columns_of(db, f"de_{dataset['id']}") == [("row_id", "BIGINT")]
    column = add_column(api, dataset["id"], "값")
    assert [n for n, _ in columns_of(db, f"dv_{dataset['id']}")] == [
        "team",
        "row_id",
        f"c_{column['id']}",
    ]
    insert_rows(db, dataset["id"], [{column["id"]: 3}])
    (row,) = view_rows(db, dataset["id"])
    assert row["team"] == "team_a" and row[f"c_{column['id']}"] == 3  # 팀 열은 팀 코드 상수


def test_no_datasets_means_no_views(db):
    assert sa.inspect(db.engine).get_view_names(schema=DYNAMIC_SCHEMA) == []


def test_view_columns_follow_column_number_order_and_types(api, db, ds):
    calc = add_formula(api, ds["id"], "계산", "[매출] + 1")
    late = add_column(api, ds["id"], "뒤에 추가", "date")
    names = [n for n, _ in columns_of(db, f"dv_{ds['id']}")]
    expected = ["team", "row_id"] + [
        f"c_{cid}" for cid in sorted([ds["매출"], ds["비용"], ds["이름"], calc["id"], late["id"]])
    ]
    assert names == expected
    types = dict(columns_of(db, f"dv_{ds['id']}"))
    assert types[f"c_{calc['id']}"] == "NUMERIC" and types[f"c_{late['id']}"] == "DATE"
    assert dict(columns_of(db, f"de_{ds['id']}"))[f"e_{calc['id']}"] == "SMALLINT"


def test_dv_values_are_null_for_error_cells_and_de_carries_the_code(api, db, ds):
    calc = add_formula(api, ds["id"], "비율", "[매출] / [비용]")
    insert_rows(
        db,
        ds["id"],
        [
            {ds["매출"]: 1, ds["비용"]: 0},
            {ds["매출"]: None, ds["비용"]: 1},
            {ds["매출"]: 4, ds["비용"]: 2},
        ],
    )
    values = [r[f"c_{calc['id']}"] for r in view_rows(db, ds["id"])]
    codes = [r[f"e_{calc['id']}"] for r in view_rows(db, ds["id"], "de")]
    assert values[0] is None and codes[0] == 1  # 오류 칸: 값 NULL + E1
    assert values[1] is None and codes[1] is None  # 빈 값: 값 NULL, 오류 없음
    assert float(values[2]) == 2.0 and codes[2] is None


def test_adding_a_raw_column_replaces_the_view_in_place_but_a_type_change_recreates_it(
    api, db, ds, monkeypatch
):
    def view_oid():
        with db.writer.connect() as conn:
            return conn.execute(
                sa.text("SELECT oid FROM pg_class WHERE oid = to_regclass(:name)"),
                {"name": f"bi_data.dv_{ds['id']}"},
            ).scalar_one()

    calc = add_formula(api, ds["id"], "계산", "[매출] + 1")
    first = view_oid()
    add_column(api, ds["id"], "추가")  # 끝에 열 추가: CREATE OR REPLACE
    assert view_oid() == first
    response = put_formula(api, ds["id"], calc["id"], '[이름] & "가"')  # 형 변경: DROP + CREATE
    assert response.status_code == 200
    assert view_oid() != first
    assert dict(columns_of(db, f"dv_{ds['id']}"))[f"c_{calc['id']}"] == "TEXT"


# --- 정의 해시 ----


def recompute_hash(db: Db, dataset_id: int) -> str:
    with Session(db.writer) as session:
        defn = dataset_service.read_definition(session, dataset_id)
        stored = repo.load_formulas(session, dataset_id)
        infos = build_column_infos(defn, stored)
        ds = source_table(defn)
        results = compile_all(infos, source_columns(defn, ds), make_probe(session))
        return build_plan(defn, ds, results).def_hash


def test_def_hash_is_the_hash_of_the_rendered_view_definitions(api, db, ds):
    add_formula(api, ds["id"], "계산", 'IF([매출] > 1, "많음", "적음") & [이름]')
    assert dataset_hash(db, ds["id"]) == recompute_hash(db, ds["id"])


def test_def_hash_changes_with_the_formula_but_not_with_display_names_or_positions(api, db, ds):
    calc = add_formula(api, ds["id"], "계산", "[매출] + 1")
    base = dataset_hash(db, ds["id"])
    renamed = api(
        "definer",
        "PATCH",
        f"/api/datasets/{ds['id']}/columns/{calc['id']}",
        json={"expected_version": version(api, ds["id"]), "display_name": "새 이름", "position": 7},
    )
    assert renamed.status_code == 200
    assert dataset_hash(db, ds["id"]) == base  # 뷰 열이 번호라 표시 이름·순서는 해시에 영향이 없다
    assert put_formula(api, ds["id"], calc["id"], "[매출] + 2").status_code == 200
    assert dataset_hash(db, ds["id"]) != base
    assert dataset_hash(db, ds["id"]) == recompute_hash(db, ds["id"])


def test_equal_hash_skips_view_ddl_and_a_changed_hash_runs_it(api, db, ds, monkeypatch):
    calls: list[tuple[str, int]] = []
    real = ddl.create_view

    def spy(conn, kind, dataset_id, *args, **kwargs):
        calls.append((kind, dataset_id))
        return real(conn, kind, dataset_id, *args, **kwargs)

    monkeypatch.setattr(ddl, "create_view", spy)
    calc = add_formula(api, ds["id"], "계산", "[매출] + 1")
    assert calls == [("dv", ds["id"]), ("de", ds["id"])]
    calls.clear()
    # 열 이름·순서 변경과 데이터셋 이름 변경은 뷰를 다시 만들지 않는다(정의 해시가 같다).
    for body in ({"display_name": "다른 이름"}, {"position": 9}):
        response = api(
            "definer",
            "PATCH",
            f"/api/datasets/{ds['id']}/columns/{calc['id']}",
            json={"expected_version": version(api, ds["id"]), **body},
        )
        assert response.status_code == 200
    api(
        "definer",
        "PATCH",
        f"/api/datasets/{ds['id']}",
        json={"expected_version": version(api, ds["id"]), "name": "새 이름"},
    )
    assert calls == []
    add_column(api, ds["id"], "새 원본 열")
    assert calls == [("dv", ds["id"]), ("de", ds["id"])]


# --- 런타임 DDL은 bi_app, 권한 ----


def test_runtime_ddl_runs_as_bi_app_and_owners_are_as_designed(api, db, ds, monkeypatch):
    seen: list[str] = []
    real = ddl.create_view

    def spy(conn, kind, dataset_id, *args, **kwargs):
        seen.append(conn.execute(sa.select(sa.func.current_user())).scalar_one())
        return real(conn, kind, dataset_id, *args, **kwargs)

    monkeypatch.setattr(ddl, "create_view", spy)
    add_formula(api, ds["id"], "계산", "[매출] + 1")
    assert seen == ["bi_app", "bi_app"]
    pg_class = sa.table(
        "pg_class",
        sa.column("relname"),
        sa.column("relkind"),
        sa.column("relowner"),
        sa.column("relnamespace"),
        schema="pg_catalog",
    )
    namespace = sa.table(
        "pg_namespace",
        sa.column("oid"),
        sa.column("nspname"),
        sa.column("nspowner"),
        schema="pg_catalog",
    )
    with db.writer.connect() as conn:
        owners = {
            r.relname: r.owner
            for r in conn.execute(
                sa.select(
                    pg_class.c.relname, sa.func.pg_get_userbyid(pg_class.c.relowner).label("owner")
                )
                .join(namespace, namespace.c.oid == pg_class.c.relnamespace)
                .where(namespace.c.nspname == "bi_data", pg_class.c.relkind.in_(["r", "v"]))
            )
        }
        schema_owner = conn.execute(
            sa.select(sa.func.pg_get_userbyid(namespace.c.nspowner)).where(
                namespace.c.nspname == "bi_data"
            )
        ).scalar_one()
    assert schema_owner == "bi_owner"
    assert owners == {
        f"ds_{ds['id']}": "bi_app",
        f"dv_{ds['id']}": "bi_app",
        f"de_{ds['id']}": "bi_app",
    }


def test_bi_readonly_reads_views_but_cannot_change_dynamic_objects(api, db, ds, pg_readonly_engine):
    calc = add_formula(api, ds["id"], "계산", "[매출] + 1")
    insert_rows(db, ds["id"], [{ds["매출"]: 2}])
    with pg_readonly_engine.connect() as conn:
        dv = sa.table(
            f"dv_{ds['id']}", sa.column("team"), sa.column(f"c_{calc['id']}"), schema="bi_data"
        )
        rows = conn.execute(sa.select(dv)).all()
        assert [tuple(r) for r in rows] == [("team_a", 3)]
        de = sa.table(f"de_{ds['id']}", sa.column("row_id"), schema="bi_data")
        assert conn.execute(sa.select(de)).all()
    forbidden = [
        f"INSERT INTO bi_data.ds_{ds['id']} (row_id) VALUES (999)",  # noqa: S608
        f"UPDATE bi_data.ds_{ds['id']} SET row_id = 7",  # noqa: S608
        f"DELETE FROM bi_data.ds_{ds['id']}",  # noqa: S608
        f"DROP VIEW bi_data.dv_{ds['id']}",
        f"DROP VIEW bi_data.de_{ds['id']}",
        f"DROP TABLE bi_data.ds_{ds['id']}",
        f"CREATE OR REPLACE VIEW bi_data.dv_{ds['id']} AS SELECT 1 AS team",
        "CREATE TABLE bi_data.evil (a int)",
        "CREATE VIEW bi_data.evil AS SELECT 1",
        "CREATE TABLE public.evil (a int)",
    ]
    for statement in forbidden:
        with pytest.raises(DBAPIError), pg_readonly_engine.begin() as conn:
            conn.execute(sa.text(statement))
    with db.writer.connect() as conn:  # 아무것도 바뀌지 않았다
        assert (
            conn.execute(
                sa.select(sa.func.count()).select_from(sa.table(f"ds_{ds['id']}", schema="bi_data"))
            ).scalar_one()
            == 1
        )


def test_bi_app_cannot_create_in_public(db):
    with pytest.raises(DBAPIError) as error, db.engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE public.evil_app (a int)"))
    assert sqlstate(error.value) == "42501"


# --- 완화책 ① 세션 설정 고정 ----


def superuser_engine(pg_env):
    values = pg_env.values
    if not values.get("POSTGRES_USER") or not values.get("POSTGRES_PASSWORD"):
        pytest.fail("시험 DB 관리자 접속 정보가 없다(POSTGRES_USER/POSTGRES_PASSWORD)")
    return create_engine(
        pg_env.url(values["POSTGRES_USER"], values["POSTGRES_PASSWORD"]),
        poolclass=sa.pool.NullPool,
    )


@pytest.fixture
def role_setting_off(pg_env):
    """시험 DB에서만: bi_app의 세션 기본값을 `standard_conforming_strings=off`로 바꾸고 되돌린다."""
    admin = superuser_engine(pg_env)
    with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        assert conn.execute(sa.text("SHOW fsync")).scalar_one() == "off"  # tmpfs 시험 DB 확인

    def apply(value):
        with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            if value is None:
                conn.execute(sa.text("ALTER ROLE bi_app RESET standard_conforming_strings"))
            else:
                conn.execute(
                    sa.text(f"ALTER ROLE bi_app SET standard_conforming_strings = {value}")
                )

    yield apply
    apply(None)
    admin.dispose()


def show_scs(engine) -> str:
    with engine.connect() as conn:
        return conn.execute(sa.text("SHOW standard_conforming_strings")).scalar_one()


def test_engine_pins_standard_conforming_strings_on_even_if_the_role_default_is_off(
    pg_settings: Settings, role_setting_off
):
    role_setting_off("off")
    plain = create_engine(build_database_url(pg_settings, "app"), poolclass=sa.pool.NullPool)
    pinned = create_db_engine(pg_settings)
    try:
        assert show_scs(plain) == "off"  # startup_params가 없으면 서버 설정을 따른다
        assert show_scs(pinned) == "on"  # 완화책 ①: 연결 때 on으로 고정
        # 연결 시작 매개변수라 세션 안에서 바뀌지 않는다(풀의 다른 연결도 같다).
        assert pinned.dialect.name == "postgresql"
    finally:
        plain.dispose()
        pinned.dispose()


def test_startup_self_check_rejects_a_non_on_setting(pg_settings, role_setting_off):
    from app.core.startup_check import StartupCheckError, check_standard_conforming_strings

    role_setting_off("off")
    plain = create_engine(build_database_url(pg_settings, "app"), poolclass=sa.pool.NullPool)
    try:
        with plain.connect() as conn, pytest.raises(StartupCheckError):
            check_standard_conforming_strings(conn)
    finally:
        plain.dispose()
    pinned = create_db_engine(pg_settings)
    try:
        with pinned.connect() as conn:
            check_standard_conforming_strings(conn)  # 고정된 엔진은 통과
    finally:
        pinned.dispose()


# --- 완화책 ③ 생성 후 읽기 확인과 롤백 ----


def make_view_select(dataset_id: int, text_value: str, column_id: int = 900):
    ds = sa.table(f"ds_{dataset_id}", sa.column("row_id", sa.BigInteger), schema=DYNAMIC_SCHEMA)
    return sa.select(
        ds.c.row_id.label("row_id"), LITERALS.text(text_value).label(f"c_{column_id}")
    ).select_from(ds)


def test_verification_failure_rolls_back_the_view_and_everything_in_the_transaction(api, db, ds):
    select = make_view_select(ds["id"], "정상 값")
    with pytest.raises(ddl.DdlVerificationError), db.engine.begin() as conn:
        ddl.create_view(
            conn,
            "dv",
            ds["id"],
            select,
            render=render_literal_sql,
            echo=[(sa.select(LITERALS.text("정상 값").label("k0")), ("다른 값",))],
        )
    assert "dv_" + str(ds["id"]) in sa.inspect(db.engine).get_view_names(schema=DYNAMIC_SCHEMA)
    # 위 시험의 dv_는 데이터셋 생성 때 만든 것이다. 롤백이 만든 것을 되돌렸음을 열로 확인한다.
    assert [n for n, _ in columns_of(db, f"dv_{ds['id']}")][:2] == ["team", "row_id"]
    assert "c_900" not in [n for n, _ in columns_of(db, f"dv_{ds['id']}")]


def test_verification_checks_the_view_columns_after_creation(api, db, ds, monkeypatch):
    from app.ddl import dynamic

    select = make_view_select(ds["id"], "값")
    real = dynamic._check_view_select
    monkeypatch.setattr(dynamic, "_check_view_select", lambda s, i: [*real(s, i), "c_901"])
    with pytest.raises(ddl.DdlVerificationError), db.engine.begin() as conn:
        ddl.create_view(conn, "dv", ds["id"], select, render=render_literal_sql)


def test_create_view_rejects_definitions_outside_the_allow_list(api, db, ds):
    other = ds["id"] + 1000
    own = sa.table(f"ds_{ds['id']}", sa.column("row_id"), schema=DYNAMIC_SCHEMA)
    bad = {
        "다른 표": sa.select(
            sa.table(f"ds_{other}", sa.column("row_id"), schema="bi_data").c.row_id.label("row_id")
        ),
        "public 표": sa.select(
            sa.table("users", sa.column("id"), schema="public").c.id.label("row_id")
        ),
        "text()": sa.select(own.c.row_id.label("row_id"), sa.text("1")).select_from(own),
        "literal_column": sa.select(
            own.c.row_id.label("row_id"), sa.literal_column("1").label("c_1")
        ).select_from(own),
        "서브쿼리": sa.select(
            own.c.row_id.label("row_id"), sa.select(own.c.row_id).scalar_subquery().label("c_1")
        ).select_from(own),
        "규칙 밖 열 이름": sa.select(own.c.row_id.label("evil")).select_from(own),
        "허용 밖 바인드": sa.select(
            own.c.row_id.label("row_id"), sa.bindparam("x", object()).label("c_1")
        ).select_from(own),
    }
    for label, select in bad.items():
        with pytest.raises((ddl.DdlNotAllowedError, ddl.DdlNameError)), db.engine.begin() as conn:
            ddl.create_view(conn, "dv", ds["id"], select, render=render_literal_sql)
        assert label
    with pytest.raises(ddl.DdlNotAllowedError), db.engine.begin() as conn:
        ddl.create_view(
            conn, "dx", ds["id"], make_view_select(ds["id"], "a"), render=render_literal_sql
        )


def test_view_ddl_errors_are_raised_without_the_sql_text_or_the_original_exception(db, ds):
    """뷰 정의 SQL에는 수식 상수가 들어 있으므로 DB 오류를 SQL 없이 다시 올린다."""
    import pg8000.dbapi

    from app.ddl import dynamic

    secret = "비밀상수-XYZ"
    leaking = DBAPIError.instance(
        f"CREATE VIEW bi_data.dv_1 AS SELECT CAST('{secret}' AS TEXT)",
        None,
        pg8000.dbapi.ProgrammingError({"C": "42601", "M": "syntax error"}),
        pg8000.dbapi.ProgrammingError,
    )
    original = dynamic.run_ddl

    def broken(conn, element):
        raise leaking

    dynamic.run_ddl = broken
    try:
        with pytest.raises(ddl.DdlExecutionError) as caught, db.engine.begin() as conn:
            ddl.create_view(
                conn,
                "dv",
                ds["id"],
                make_view_select(ds["id"], "값", 902),
                render=render_literal_sql,
            )
    finally:
        dynamic.run_ddl = original
    error = caught.value
    assert error.sqlstate == "42601" and error.__cause__ is None and error.__suppress_context__
    assert secret not in str(error) and "CREATE" not in str(error)


# --- X-26 주입 사례 회귀(층별) ----


@pytest.fixture
def victim(pg_owner_engine):
    with pg_owner_engine.begin() as conn:
        conn.execute(sa.text("DROP TABLE IF EXISTS public.t"))
        conn.execute(sa.text("CREATE TABLE public.t (v text)"))
        conn.execute(sa.text("INSERT INTO public.t VALUES ('a'), ('b'), ('c')"))
        conn.execute(sa.text("GRANT ALL ON public.t TO bi_app"))
    yield pg_owner_engine
    with pg_owner_engine.begin() as conn:
        conn.execute(sa.text("DROP TABLE IF EXISTS public.t"))
        conn.execute(sa.text("DROP TABLE IF EXISTS bi_data.evil"))


def assert_no_effect(owner) -> None:
    with owner.connect() as conn:
        assert conn.execute(sa.text("SELECT count(*) FROM public.t")).scalar_one() == 3
        assert conn.execute(sa.text("SELECT to_regclass('bi_data.evil')")).scalar_one() is None, (
            "bi_data.evil이 만들어졌다"
        )
        assert conn.execute(sa.text("SELECT to_regclass('public.evil')")).scalar_one() is None


def column_value(db: Db, dataset_id: int, column_id: int):
    return view_rows(db, dataset_id)[0][f"c_{column_id}"]


@pytest.mark.parametrize("name", sorted(INJECTION_CASES))
def test_l0_injection_cases_have_no_effect_and_round_trip_or_are_rejected(
    api, db, ds, victim, name
):
    payload = INJECTION_CASES[name]
    insert_rows(db, ds["id"], [{ds["매출"]: 1}])
    before = (version(api, ds["id"]), dataset_hash(db, ds["id"]))
    response = post_formula(api, ds["id"], "주입", formula_of(payload))
    if "\\" in payload:  # 완화책 ②: 역슬래시는 C0가 거부한다
        assert response.status_code == 422, name
        assert err(response)["code"] == "FORMULA_INVALID"
        assert err(response)["details"]["errors"][0]["code"] == "TEXT_CONSTANT_INVALID"
        assert (version(api, ds["id"]), dataset_hash(db, ds["id"])) == before
    else:  # 정상 입력은 하나의 글자로 왕복한다(추가 문장 없음)
        assert response.status_code == 201, response.text
        column_id = response.json()["column"]["id"]
        assert column_value(db, ds["id"], column_id) == payload, name
    assert_no_effect(victim)


@pytest.mark.parametrize("name", sorted(BACKSLASH_CASES))
def test_l0_backslash_inputs_are_rejected_by_c0(api, db, ds, victim, name):
    response = post_formula(api, ds["id"], "역슬래시", formula_of(BACKSLASH_CASES[name]))
    assert response.status_code == 422
    assert err(response)["details"]["errors"][0]["code"] == "TEXT_CONSTANT_INVALID"
    check = api(
        "definer",
        "POST",
        f"/api/datasets/{ds['id']}/formulas/check",
        json={"expression": formula_of(BACKSLASH_CASES[name])},
    )
    assert check.json()["ok"] is False
    assert_no_effect(victim)


@pytest.fixture
def lenient_c0(monkeypatch):
    """완화책 ②를 끈다: 역슬래시 거부 규칙만 빼고 나머지 글자 규칙은 그대로 둔다."""
    original = literals.text_constant_problem

    def without_backslash_rule(value: str):
        return original(value.replace("\\", ""))

    monkeypatch.setattr(literals, "text_constant_problem", without_backslash_rule)
    monkeypatch.setattr("app.formula.analyze.text_constant_problem", without_backslash_rule)
    # 게이트의 방어 중복(ddl 쪽 글자 상수 검사)도 같은 규칙만 끈다.
    from app.ddl import dynamic

    gate_original = dynamic._text_bind_problem
    monkeypatch.setattr(
        dynamic, "_text_bind_problem", lambda value: gate_original(value.replace("\\", ""))
    )


@pytest.mark.parametrize("name", sorted(BACKSLASH_CASES))
def test_l1_without_mitigation_two_the_pinned_session_setting_alone_is_safe(
    api, db, ds, victim, lenient_c0, name
):
    """L1: ②를 끄고 ①만. 역슬래시가 글자 그대로 들어가 입력과 같은 값으로 왕복하고 효과가 없다."""
    payload = BACKSLASH_CASES[name]
    assert show_scs(db.engine) == "on"
    response = post_formula(api, ds["id"], "L1", formula_of(payload))
    assert response.status_code == 201, response.text
    insert_rows(db, ds["id"], [{ds["매출"]: 1}])
    assert column_value(db, ds["id"], response.json()["column"]["id"]) == payload
    assert_no_effect(victim)


@pytest.fixture
def unpinned_engine(pg_settings, pg_env, role_setting_off):
    """① 없는 엔진: `startup_params` 없이 만들고 첫 연결 때 서버 설정(on)으로 방언이 굳게 한다."""
    engine = create_engine(build_database_url(pg_settings, "app"), pool_size=5, max_overflow=0)
    with engine.connect() as conn:  # 방언이 `standard_conforming_strings=on`을 보고 굳는다
        assert conn.execute(sa.text("SHOW standard_conforming_strings")).scalar_one() == "on"
    assert engine.dialect._backslash_escapes is False
    yield engine
    engine.dispose()


INJECTING_BACKSLASH_CASES = ["P4", "P5", "P6", "P10"]


@pytest.mark.parametrize("name", INJECTING_BACKSLASH_CASES)
def test_l2_server_setting_changed_after_the_dialect_was_fixed_only_the_readback_protects(
    api,
    db,
    ds,
    victim,
    lenient_c0,
    unpinned_engine,
    role_setting_off,
    stub_settings,
    sync,
    caplog,
    name,
):
    """L2(시나리오 A): ① 없음 + ② 없음 + 서버 설정 off. ③(재읽기 확인)이 롤백한다."""
    insert_rows(db, ds["id"], [{ds["매출"]: 1}])
    role_setting_off("off")
    unpinned_engine.dispose()  # 새 연결은 off, 방언은 on으로 굳은 채(시나리오 A)
    assert show_scs(unpinned_engine) == "off"
    app = create_app(stub_settings, engine=unpinned_engine, dataset_sync=sync)
    before = (version(api, ds["id"]), dataset_hash(db, ds["id"]))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = make_caller(client)(
            "definer",
            "POST",
            f"/api/datasets/{ds['id']}/formulas",
            json={
                "expected_version": before[0],
                "display_name": "L2",
                "expression": formula_of(BACKSLASH_CASES[name]),
            },
        )
    assert response.status_code != 201, response.text  # 만들어지지 않는다
    assert "DELETE" not in response.text and "evil" not in response.text
    # 뷰 정의 SQL에는 수식 상수가 들어 있다: DB 오류가 나도 로그에 SQL·상수가 남지 않는다.
    for leaked in ("CREATE", "VIEW", "evil", "DELETE FROM", "bi_data.ds_"):
        assert leaked not in caplog.text, leaked
    assert (version(api, ds["id"]), dataset_hash(db, ds["id"])) == before  # 롤백 뒤 변경 전 상태
    assert_no_effect(victim)
    with db.writer.connect() as conn:
        count = conn.execute(
            sa.text(
                "SELECT count(*) FROM dataset_columns WHERE dataset_id = :i AND kind = 'formula'"
            ),
            {"i": ds["id"]},
        ).scalar_one()
    assert count == 0


def test_l2_readback_detects_a_silently_altered_string(
    api, db, ds, lenient_c0, unpinned_engine, role_setting_off
):
    """주입이 아니어도 `a\\b`가 `\\b`(역행 문자)로 바뀌어 들어가면 ③이 불일치를 잡는다."""
    role_setting_off("off")
    unpinned_engine.dispose()
    select = make_view_select(ds["id"], "a\\b", 901)
    echoes = echo_selects(text_constants(select))
    with pytest.raises(ddl.DdlVerificationError):
        with unpinned_engine.begin() as conn:
            ddl.create_view(conn, "dv", ds["id"], select, render=render_literal_sql, echo=echoes)
    assert "c_901" not in [n for n, _ in columns_of(db, f"dv_{ds['id']}")]


@pytest.mark.parametrize("setting", ["on", "off"])
@pytest.mark.parametrize("name", sorted(BACKSLASH_CASES))
def test_l3_renderer_alone_is_consistent_when_dialect_and_session_agree(
    db, victim, lenient_c0, setting, name
):
    """L3: 렌더러 단독. 방언의 역슬래시 처리와 세션 설정이 같으면 입력 그대로 왕복한다."""
    payload = BACKSLASH_CASES[name]
    dialect = pg8000.dialect()
    dialect._backslash_escapes = setting == "off"
    with db.engine.connect() as conn:
        conn.execute(sa.select(sa.func.set_config("standard_conforming_strings", setting, True)))
        statement = sa.select(LITERALS.text(payload).label("k0"))
        row = conn.execute(RenderedSelect(statement, render_literal_sql, dialect)).one()
        assert row[0] == payload
        conn.rollback()
    assert_no_effect(victim)


def test_l3_a_mismatch_between_dialect_and_session_would_corrupt_or_inject(db, victim, lenient_c0):
    """대조군: 방언과 세션 설정이 어긋나면 값이 달라진다(그래서 ①이 필요하다)."""
    payload = "a\\b"
    dialect = pg8000.dialect()
    dialect._backslash_escapes = False  # on으로 알고 렌더
    with db.engine.connect() as conn:
        conn.execute(sa.select(sa.func.set_config("standard_conforming_strings", "off", True)))
        statement = sa.select(LITERALS.text(payload).label("k0"))
        row = conn.execute(RenderedSelect(statement, render_literal_sql, dialect)).one()
        assert row[0] != payload
        conn.rollback()
    assert_no_effect(victim)
