"""수식 2단계의 DB 없이 도는 단위 시험: 동시 실행 제한, 뷰 대조 메모리 상태, 실패 사유, 정의
게이트, 정적 검사."""

from __future__ import annotations

import ast
import threading
from datetime import datetime
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


def test_global_limit_is_two_so_three_pool_connections_stay_free():
    assert GLOBAL_HEAVY_READ_LIMIT == 2  # 풀 5개(max_overflow 0) 중 일반 요청용 3개를 남긴다


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
    ],
)
def test_view_select_gate_rejects_anything_outside_the_allow_list(build):
    with pytest.raises((ddl.DdlNotAllowedError, ddl.DdlNameError)):
        _check_view_select(build(_own()), 5)


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
REVIEWED_SQL_FUNCTIONS = {
    # 사전(변환기)
    "abs", "btrim", "ceil", "char_length", "coalesce", "floor", "greatest", "least", "left",
    "lower", "make_date", "mod", "nullif", "regexp_replace", "right", "round", "sign", "trunc",
    "extract", "date_part", "length",
    # 서비스(시험·읽기 보조)
    "count", "set_config", "pg_typeof",
}  # fmt: skip


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


def test_confirmation_queries_may_only_hold_text_constants():
    """완화책 ③ 확인 질의(`RenderedSelect`)는 FROM 없는 `CAST(글자 상수)` SELECT만 받는다."""
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
        "SELECT 1",  # Select 객체가 아니다
    ]
    for statement in bad:
        with pytest.raises(ddl.DdlNotAllowedError):
            RenderedSelect(statement, render_literal_sql)  # type: ignore[arg-type]
