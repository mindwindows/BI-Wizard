"""수식 2단계의 DB 없이 도는 단위 시험: 동시 실행 제한, 뷰 대조 메모리 상태, 실패 사유, 정의
게이트, 정적 검사."""

from __future__ import annotations

import ast
import threading
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError

from app import ddl
from app.core.errors import AppError, ErrorCode, definition_busy, formula_circular, formula_invalid
from app.core.limits import GLOBAL_HEAVY_READ_LIMIT, HeavyReadLimiter
from app.core.startup_check import StartupReport
from app.ddl.dynamic import _check_view_select
from app.formula.reconcile import failure_reason
from app.formula.status import ViewStatus

APP = Path(__file__).resolve().parent.parent / "app"


# --- 무거운 읽기 제한 (07 §5) ----


def test_global_limit_is_two_and_stays_conservative_for_the_larger_pool():
    # 풀 10+5 중 일반 요청용 연결을 충분히 남기는 보수값(상향 여부는 후속). 값 자체는 바꾸지 않았다.
    assert GLOBAL_HEAVY_READ_LIMIT == 2


def test_limiter_counts_released_slots_even_when_the_work_raises():
    limiter = HeavyReadLimiter()
    with pytest.raises(RuntimeError), limiter.slot():
        assert limiter.active == 1
        raise RuntimeError("작업 실패")
    assert limiter.active == 0
    with limiter.slot(), limiter.slot():
        assert limiter.active == 2
        with pytest.raises(AppError) as busy, limiter.slot():
            pass
        assert busy.value.code == ErrorCode.PREVIEW_BUSY and busy.value.status_code == 429
    assert limiter.active == 0


def test_same_user_cannot_run_two_previews_but_other_users_can():
    limiter = HeavyReadLimiter(global_limit=3)
    with limiter.slot(user_id=7):
        with pytest.raises(AppError) as busy, limiter.slot(user_id=7):
            pass
        assert busy.value.details == {"retry_after": 2}
        with limiter.slot(user_id=8):
            pass
    with limiter.slot(user_id=7):  # 끝나면 다시 된다
        pass


def test_limiter_is_thread_safe_under_contention():
    limiter = HeavyReadLimiter(global_limit=2)
    peak = 0
    lock = threading.Lock()
    inside = 0
    rejected = 0
    barrier = threading.Barrier(8)

    def work():
        nonlocal peak, inside, rejected
        barrier.wait()
        try:
            with limiter.slot():
                with lock:
                    inside += 1
                    peak = max(peak, inside)
                threading.Event().wait(0.05)
                with lock:
                    inside -= 1
        except AppError:
            with lock:
                rejected += 1

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak <= 2 and rejected >= 1 and limiter.active == 0


# --- 뷰 대조 메모리 상태 (06 §5, 05 H1·D9) ----


def test_view_status_counts_failures_and_updates_the_health_report():
    report = StartupReport()
    status = ViewStatus()
    status.bind(report)
    status.ok(1)
    status.ok(2)
    status.fail(3, "LOCK_TIMEOUT: 다른 작업이 진행 중이라 뷰를 만들지 못했습니다.")
    assert (report.views, report.views_failed_count) == (3, 1)
    (failure,) = status.failures()
    assert failure.dataset_id == 3 and isinstance(failure.since, datetime)
    first_since = failure.since
    status.fail(3, "DB_ERROR: 다시 실패")
    assert status.failures()[0].since == first_since  # 계속 실패 중이면 처음 시각을 유지한다
    assert status.failed_ids() == [3]
    status.ok(3)  # 다시 만들기에 성공하면 실패 목록에서 빠진다
    assert (report.views, report.views_failed_count) == (3, 0) and status.failures() == []


def test_view_status_does_not_overwrite_the_report_before_anything_is_recorded():
    report = StartupReport(views=3, views_failed_count=1)
    ViewStatus().bind(report)
    assert (report.views, report.views_failed_count) == (3, 1)


# --- 실패 사유 (SQL·상수·비밀 금지) ----


class _FakeOrig(Exception):
    def __init__(self, code: str) -> None:
        super().__init__({"C": code, "M": "secret message with 비밀상수 and SELECT"})


def test_failure_reasons_are_codes_with_short_summaries_and_never_leak_details():
    secret_error = DBAPIError.instance(
        "CREATE VIEW x AS SELECT 'SECRET'", None, _FakeOrig("42601"), Exception
    )
    reasons = {
        "LOCK_TIMEOUT": failure_reason(definition_busy()),
        "FORMULA_INVALID": failure_reason(formula_invalid([{"message": "비밀"}])),
        "FORMULA_INVALID2": failure_reason(formula_circular(["가", "나", "가"])),
        "VIEW_VERIFY_FAILED": failure_reason(ddl.DdlVerificationError("비밀 내용")),
        "DB_ERROR": failure_reason(secret_error),
        "DB_UNAVAILABLE": failure_reason(TimeoutError("socket timed out SELECT SECRET")),
        "UNEXPECTED": failure_reason(RuntimeError("password=hunter2")),
    }
    for code, reason in reasons.items():
        assert reason.split(":")[0] == code.rstrip("2"), (code, reason)
        for leaked in ("SECRET", "SELECT", "비밀", "hunter2", "CREATE"):
            assert leaked not in reason, (code, reason)
    assert "42601" in reasons["DB_ERROR"]
    lock = DBAPIError.instance("x", None, _FakeOrig("55P03"), Exception)
    assert failure_reason(lock).startswith("LOCK_TIMEOUT:")


# --- 뷰 정의 허용 목록 게이트 (DB 없이) ----


def _own(dataset_id: int = 5) -> sa.TableClause:
    return sa.table(f"ds_{dataset_id}", sa.column("row_id"), sa.column("c_1"), schema="bi_data")


def test_view_select_gate_accepts_the_shape_the_planner_builds():
    own = _own()
    select = sa.select(
        own.c.row_id.label("row_id"),
        sa.cast(sa.bindparam("lit", "x", type_=sa.Text), sa.Text).label("team"),
    ).select_from(own)
    assert _check_view_select(select, 5) == ["row_id", "team"]


@pytest.mark.parametrize(
    "build",
    [
        lambda own: sa.select(own.c.row_id.label("row_id"), sa.text("1")).select_from(own),
        lambda own: sa.select(
            own.c.row_id.label("row_id"), sa.literal_column("1").label("c_1")
        ).select_from(own),
        lambda own: sa.select(
            sa.select(own.c.row_id).scalar_subquery().label("row_id")
        ).select_from(own),
        lambda own: sa.select(own.c.row_id.label("evil")).select_from(own),
        lambda own: sa.select(
            own.c.row_id.label("row_id"), own.c.row_id.label("row_id")
        ).select_from(own),
        lambda own: sa.select(
            own.c.row_id.label("row_id"), sa.bindparam("x", object()).label("c_1")
        ).select_from(own),
        lambda own: sa.select(
            sa.table("ds_6", sa.column("row_id"), schema="bi_data").c.row_id
        ).select_from(sa.table("ds_6", sa.column("row_id"), schema="bi_data")),
        lambda own: sa.select(
            sa.table("ds_5", sa.column("row_id"), schema="public").c.row_id.label("row_id")
        ),
        lambda own: sa.select(own.c.row_id.label("row_id")).select_from(
            own.join(sa.table("ds_7", sa.column("row_id"), schema="bi_data"), sa.true())
        ),
        # 허용 목록 밖 SQL 함수(R1)
        lambda own: sa.select(
            own.c.row_id.label("row_id"), sa.func.pg_sleep(10).label("c_1")
        ).select_from(own),
        lambda own: sa.select(
            own.c.row_id.label("row_id"), sa.func.pg_catalog.pg_sleep(10).label("c_1")
        ).select_from(own),
        lambda own: sa.select(
            own.c.row_id.label("row_id"), sa.func.pg_read_file("/etc/passwd").label("c_1")
        ).select_from(own),
        lambda own: sa.select(
            own.c.row_id.label("row_id"), sa.func.abs(sa.func.pg_sleep(1)).label("c_1")
        ).select_from(own),
    ],
)
def test_view_select_gate_rejects_anything_outside_the_allow_list(build):
    with pytest.raises((ddl.DdlNotAllowedError, ddl.DdlNameError)):
        _check_view_select(build(_own()), 5)


@pytest.mark.parametrize(
    "value",
    [
        "a\x00b",
        "a\\b",
        "a\nb",
        "a\tb",
        "a" + chr(0x200B) + "b",
        "a" + chr(0x2028) + "b",
        "a\ud800b",
    ],
    ids=["nul", "backslash", "newline", "tab", "zero-width", "line-separator", "surrogate"],
)
def test_view_select_gate_rejects_text_binds_with_forbidden_characters(value):
    own = _own()
    select = sa.select(
        own.c.row_id.label("row_id"), sa.bindparam("x", value, type_=sa.Text).label("c_1")
    ).select_from(own)
    with pytest.raises(ddl.DdlNotAllowedError):
        _check_view_select(select, 5)


def _with_column(expression):
    own = _own()
    return sa.select(own.c.row_id.label("row_id"), expression.label("c_1")).select_from(own)


def _part_cases():
    own = _own()
    return {
        "custom-op": own.c.c_1.op("; DROP TABLE x; --")(own.c.row_id),
        "custom-op-bind": own.c.c_1.op("@@")(
            sa.cast(sa.bindparam("lit", "x", type_=sa.Text), sa.Text)
        ),
        "custom-unary-op": sa.sql.expression.UnaryExpression(
            own.c.c_1, operator=sa.sql.operators.custom_op("!!")
        ),
        "extract-field": sa.extract("epoch from now()) --", own.c.c_1),
        "extract-other-field": sa.extract("epoch", own.c.c_1),
        "callable-bind": sa.cast(
            sa.bindparam("lit", callable_=lambda: "x", type_=sa.Text), sa.Text
        ),
        "decimal-nan": sa.cast(sa.bindparam("lit", Decimal("NaN"), type_=sa.Numeric), sa.Numeric),
        "decimal-inf": sa.cast(
            sa.bindparam("lit", Decimal("Infinity"), type_=sa.Numeric), sa.Numeric
        ),
        "decimal-huge-exponent": sa.cast(
            sa.bindparam("lit", Decimal("1E+999999"), type_=sa.Numeric), sa.Numeric
        ),
        "decimal-tiny-exponent": sa.cast(
            sa.bindparam("lit", Decimal("1E-999999"), type_=sa.Numeric), sa.Numeric
        ),
        "decimal-39-digits": sa.cast(
            sa.bindparam("lit", Decimal("1E+38"), type_=sa.Numeric), sa.Numeric
        ),
        "int-too-big": sa.cast(sa.bindparam("lit", 10**40, type_=sa.Numeric), sa.Numeric),
    }


@pytest.mark.parametrize("case", sorted(_part_cases()))
def test_view_select_gate_rejects_sqlalchemy_parts_that_render_raw_text(case):
    expression = _part_cases()[case]
    with pytest.raises(ddl.DdlNotAllowedError):
        _check_view_select(_with_column(expression), 5)


@pytest.mark.parametrize("case", sorted(_part_cases()))
def test_create_view_run_ddl_rejects_the_same_parts_before_any_statement(case):
    from sqlalchemy.schema import CreateView

    view = CreateView(_with_column(_part_cases()[case]), "dv_5", schema="bi_data")
    with pytest.raises(ddl.DdlNotAllowedError):
        ddl.run_ddl(None, view)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "build",
    [
        lambda own: sa.extract("year", own.c.c_1),
        lambda own: sa.extract("month", own.c.c_1),
        lambda own: sa.extract("day", own.c.c_1),
        lambda own: own.c.c_1 + own.c.row_id,
        lambda own: (
            own.c.c_1 == sa.cast(sa.bindparam("lit", Decimal("1E+3"), type_=sa.Numeric), sa.Numeric)
        ),
        lambda own: sa.cast(
            sa.bindparam("lit", Decimal("0.00000001"), type_=sa.Numeric), sa.Numeric
        ),
        lambda own: sa.cast(sa.bindparam("lit", Decimal("-12.50"), type_=sa.Numeric), sa.Numeric),
        lambda own: sa.cast(sa.bindparam("lit", Decimal("1" * 38), type_=sa.Numeric), sa.Numeric),
        lambda own: sa.cast(sa.bindparam("lit", 7, type_=sa.SmallInteger), sa.SmallInteger),
        lambda own: sa.cast(sa.bindparam("lit", True, type_=sa.Boolean), sa.Boolean),
    ],
)
def test_view_select_gate_still_accepts_what_formula_builds(build):
    own = _own()
    select = sa.select(own.c.row_id.label("row_id"), build(own).label("c_1")).select_from(own)
    assert _check_view_select(select, 5) == ["row_id", "c_1"]


@pytest.mark.parametrize(
    "build",
    [
        lambda: sa.cast(sa.bindparam("lit", callable_=lambda: "x", type_=sa.Text), sa.Text),
        lambda: sa.cast(sa.bindparam("lit", "a", callable_=lambda: "b", type_=sa.Text), sa.Text),
        lambda: sa.cast(sa.column("a").op("||")("y"), sa.Text),
        lambda: sa.extract("year", sa.cast(sa.bindparam("lit", "x", type_=sa.Text), sa.Text)),
    ],
)
def test_echo_select_gate_rejects_the_same_parts(build):
    from app.ddl.dynamic import _check_echo_select

    with pytest.raises(ddl.DdlNotAllowedError):
        _check_echo_select(sa.select(build().label("k0")))


def test_echo_select_gate_accepts_a_plain_text_constant():
    from app.ddl.dynamic import _check_echo_select

    text = sa.cast(sa.bindparam("lit", "x", type_=sa.Text), sa.Text)
    _check_echo_select(sa.select(text.label("k0")))


def test_allowed_ddl_elements_include_views_only_through_the_gate():
    from sqlalchemy.schema import CreateView, DropView

    assert CreateView in ddl.ALLOWED_DDL_ELEMENTS and DropView in ddl.ALLOWED_DDL_ELEMENTS
    with pytest.raises(ddl.DdlNameError):  # 번호 규칙 밖 이름
        view = sa.Table("evil", sa.MetaData(), schema="bi_data")
        ddl.run_ddl(None, DropView(view))  # type: ignore[arg-type]
    with pytest.raises(ddl.DdlNotAllowedError):  # 구체화 뷰
        ddl.run_ddl(
            None, DropView(sa.Table("dv_1", sa.MetaData(), schema="bi_data"), materialized=True)
        )  # type: ignore[arg-type]
    with pytest.raises(ddl.DdlNotAllowedError):  # schema 밖
        ddl.run_ddl(None, DropView(sa.Table("dv_1", sa.MetaData(), schema="public")))  # type: ignore[arg-type]


def test_view_kinds_use_only_the_numbered_name_rules():
    assert ddl.VIEW_KINDS["dv"](12) == "dv_12" and ddl.VIEW_KINDS["de"](12) == "de_12"
    assert set(ddl.VIEW_KINDS) == {"dv", "de"}
    with pytest.raises(ddl.DdlNameError):
        ddl.VIEW_KINDS["dv"](0)


# --- 정적 검사 ----

# 변환기·사전이 쓰는 SQL 함수의 검토된 목록. 새 SQL 함수를 쓰면 이 시험이 실패한다: bi_data 객체나
# 시스템 함수 호출로 번지지 않는지 검토한 뒤 여기에 더한다(`bi-review` 7-4).
# 뷰 정의 게이트의 허용 목록(`ddl.VIEW_ALLOWED_FUNCTIONS`)이 단일 출처다. formula가 뷰 밖
# (서비스의 시험·읽기 보조)에서만 쓰는 함수만 여기에 더한다.
SERVICE_ONLY_SQL_FUNCTIONS = {"count", "set_config", "pg_typeof"}
REVIEWED_SQL_FUNCTIONS = set(ddl.VIEW_ALLOWED_FUNCTIONS) | SERVICE_ONLY_SQL_FUNCTIONS


def _func_names(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "func"
        ):
            names.add(node.attr)
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "func"
        ):
            names.add(node.attr)
    return names


def test_sql_functions_used_by_the_formula_package_are_on_the_reviewed_list():
    used: set[str] = set()
    for path in sorted((APP / "formula").glob("*.py")):
        used |= _func_names(path)
    assert used <= REVIEWED_SQL_FUNCTIONS, used - REVIEWED_SQL_FUNCTIONS


def test_formula_modules_never_execute_ddl_or_raw_sql():
    """뷰 DDL은 ddl 모듈만 실행한다: formula는 DDL 구문 이름도, execute_text류도 쓰지 않는다."""
    banned = {"CreateView", "DropView", "CreateTable", "DropTable", "Operations", "exec_driver_sql"}
    for path in sorted((APP / "formula").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            name = getattr(node, "id", None) or getattr(node, "attr", None)
            assert name not in banned, (path.name, name)


def _raw_echo(value: str):
    """`Literals`를 거치지 않고 만든 확인 질의(1차 방어가 없는 상황)."""
    bind = sa.bindparam("lit", value, type_=sa.Text, unique=True)
    return sa.select(sa.cast(bind, sa.Text).label("k0"))


def test_confirmation_queries_may_only_hold_text_constants():
    """완화책 ③ 확인 질의(`RenderedSelect`)는 FROM 없는 `CAST(글자 상수) AS k<n>`만 받는다."""
    from app.ddl.dynamic import RenderedSelect
    from app.formula import LITERALS, render_literal_sql

    good = sa.select(LITERALS.text("가").label("k0"), LITERALS.text("나").label("k1"))
    assert RenderedSelect(good, render_literal_sql).selectable is good
    own = sa.table("ds_1", sa.column("row_id"), schema="bi_data")
    bad = [
        sa.select(own.c.row_id),  # FROM이 있다
        sa.select(sa.text("1")),  # text()
        sa.select(LITERALS.number(1).label("k0")),  # 글자가 아닌 상수
        sa.select(sa.func.pg_sleep(1).label("k0")),  # 함수 호출
        sa.select(LITERALS.text("가")),  # 이름 없는 열
        sa.select(LITERALS.text("가").label("evil")),  # k<n> 이름이 아니다
        _raw_echo("a\\b"),  # 역슬래시
        _raw_echo("a\x00b"),  # NUL
        sa.select(),  # 열이 없다
        "SELECT 1",  # Select 객체가 아니다
    ]
    for statement in bad:
        with pytest.raises(ddl.DdlNotAllowedError):
            RenderedSelect(statement, render_literal_sql)  # type: ignore[arg-type]


def _echo_statement():
    from app.formula import LITERALS

    return sa.select(LITERALS.text("O'Brien").label("k0"), LITERALS.text("가나").label("k1"))


def _compile_echo(render):
    from sqlalchemy.dialects.postgresql import pg8000

    from app.ddl.dynamic import RenderedSelect

    return str(RenderedSelect(_echo_statement(), render).compile(dialect=pg8000.dialect()))


def test_rendered_confirmation_query_with_the_allowed_shape_and_same_values_is_accepted():
    from app.formula import render_literal_sql

    sql = _compile_echo(render_literal_sql)
    assert sql == "SELECT CAST('O''Brien' AS TEXT) AS k0, CAST('가나' AS TEXT) AS k1"


_GOOD_ECHO = "SELECT CAST('O''Brien' AS TEXT) AS k0, CAST('가나' AS TEXT) AS k1"


@pytest.mark.parametrize(
    "rendered",
    [
        "SELECT pg_sleep(10)",
        "SELECT pg_sleep(10); " + _GOOD_ECHO,
        _GOOD_ECHO + "; DROP TABLE public.t",
        _GOOD_ECHO + " FROM public.users",
        _GOOD_ECHO + " -- ",
        "SELECT CAST('O''Brien' AS TEXT) AS k0",  # 칸이 모자란다
        _GOOD_ECHO + ", CAST('x' AS TEXT) AS k2",  # 칸이 남는다
        "SELECT CAST('가나' AS TEXT) AS k1, CAST('O''Brien' AS TEXT) AS k0",  # 순서가 다르다
        "SELECT CAST('OBrien' AS TEXT) AS k0, CAST('가나' AS TEXT) AS k1",  # 값이 다르다
        "SELECT CAST('O''Brien' AS TEXT) AS k0,CAST('가나' AS TEXT) AS k1",  # 모양이 다르다
        "SELECT CAST('O'Brien' AS TEXT) AS k0, CAST('가나' AS TEXT) AS k1",  # 따옴표가 깨졌다
        "SELECT CAST('x'' || (SELECT 1) || ''' AS TEXT) AS k0, CAST('가나' AS TEXT) AS k1",
        _GOOD_ECHO.replace("SELECT", "select"),
        "",
    ],
)
def test_an_injected_render_function_cannot_make_the_confirmation_query_run_anything_else(rendered):
    with pytest.raises(ddl.DdlNotAllowedError):
        _compile_echo(lambda statement, dialect: rendered)


def test_rendered_confirmation_query_is_checked_with_the_backslash_rules_of_the_dialect():
    from sqlalchemy.dialects.postgresql import pg8000

    from app.ddl.dynamic import RenderedSelect, check_rendered_echo

    statement = _raw_echo("a\\b")

    def render(select, dialect):  # 1차 방어(역슬래시 거부)를 거치지 않고 렌더한다
        return str(select.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))

    plain = pg8000.dialect()  # standard_conforming_strings=on: 역슬래시는 그대로
    escaping = pg8000.dialect()
    escaping._backslash_escapes = True  # off: 역슬래시를 두 개로 쓴다
    assert check_rendered_echo(render(statement, plain), statement, plain)
    assert check_rendered_echo(render(statement, escaping), statement, escaping)
    # 방언의 믿음과 다르게 렌더되면(on으로 렌더하고 off로 읽음) 값이 달라 거부한다.
    with pytest.raises(ddl.DdlNotAllowedError):
        check_rendered_echo(render(statement, plain), statement, escaping)
    # 짝 없는 역슬래시는 off 방언에서 거부한다.
    with pytest.raises(ddl.DdlNotAllowedError):
        check_rendered_echo("SELECT CAST('a\\' AS TEXT) AS k0", statement, escaping)
    # `dialect`를 주면 연결의 방언과 상관없이 그 방언으로 렌더하고 확인한다.
    with pytest.raises(ddl.DdlNotAllowedError):  # 확인 질의 자체는 역슬래시를 받지 않는다
        RenderedSelect(statement, render, escaping)
    plain_echo = _echo_statement()
    sql = str(RenderedSelect(plain_echo, render, escaping).compile(dialect=plain))
    assert sql.startswith("SELECT CAST('O''Brien' AS TEXT) AS k0")


class _NoDatabase:
    """어떤 DB 호출도 하면 시험이 실패하는 연결(`create_view`가 실행 전에 거부함을 보인다)."""

    def __init__(self) -> None:
        from sqlalchemy.dialects.postgresql import pg8000

        self.dialect = pg8000.dialect()

    def __getattr__(self, name: str):
        raise AssertionError(f"실행 전에 거부해야 하는데 연결의 {name}을 불렀다")


def _plan_select(dataset_id: int = 5):
    from app.formula import LITERALS

    own = sa.table(f"ds_{dataset_id}", sa.column("row_id"), schema="bi_data")
    return sa.select(own.c.row_id.label("row_id"), LITERALS.text("값").label("c_1")).select_from(
        own
    )


def test_create_view_rejects_a_render_mismatch_before_touching_the_database():
    from app.formula import render_literal_sql

    def tampered(statement, dialect):
        return render_literal_sql(statement, dialect).replace("'값'", "'다른 값'")

    with pytest.raises(ddl.DdlVerificationError):
        ddl.create_view(_NoDatabase(), "dv", 5, _plan_select(), render=tampered)  # type: ignore[arg-type]


def test_create_view_requires_the_exact_definition_not_just_a_suffix_after_some_as():
    from app.formula import render_literal_sql

    def only_the_part_after_a_column_alias(statement, dialect):
        full = render_literal_sql(statement, dialect)
        assert " AS " in full  # 열 별칭의 ` AS `
        return full.partition(" AS ")[2]  # 정의 중간 ` AS ` 뒤 일부뿐인 글자

    with pytest.raises(ddl.DdlVerificationError):
        ddl.create_view(
            _NoDatabase(),  # type: ignore[arg-type]
            "dv",
            5,
            _plan_select(),
            render=only_the_part_after_a_column_alias,
        )


def test_create_view_rejects_a_function_outside_the_allow_list_before_touching_the_database():
    from app.formula import render_literal_sql

    own = sa.table("ds_5", sa.column("row_id"), schema="bi_data")
    select = sa.select(own.c.row_id.label("row_id"), sa.func.pg_sleep(30).label("c_1")).select_from(
        own
    )
    with pytest.raises(ddl.DdlNotAllowedError):
        ddl.create_view(_NoDatabase(), "dv", 5, select, render=render_literal_sql)  # type: ignore[arg-type]
