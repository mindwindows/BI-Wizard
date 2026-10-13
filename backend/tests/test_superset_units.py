"""superset 모듈의 작은 부품 시험: 이름·SQL 규칙, 속도 제한, 서킷 브레이커, 상수, 정적 규칙."""

import re
import threading
from pathlib import Path

import pytest

from app.ddl.names import DdlNameError
from app.superset import constants
from app.superset.breaker import CircuitBreaker
from app.superset.errors import REASON_SUMMARY, summarize
from app.superset.naming import VIRTUAL_SQL_PATTERN, column_label, superset_name, virtual_sql
from app.superset.ratelimit import SlidingWindowLimiter
from app.superset.tokens import canonical_uuid
from tests.superset_helpers import Clock

APP = Path(__file__).resolve().parent.parent / "app"
REPO_ROOT = Path(__file__).resolve().parents[2]


# --- 이름·SQL ----


@pytest.mark.parametrize("dataset_id", [1, 2, 42, 1234567])
def test_virtual_sql_is_the_single_fixed_template(dataset_id):
    sql = virtual_sql(dataset_id)
    assert sql == f"SELECT * FROM bi_data.dv_{dataset_id}"  # noqa: S608 - 기대값 비교
    assert re.fullmatch(r"^SELECT \* FROM bi_data\.dv_[1-9][0-9]*$", sql)
    assert VIRTUAL_SQL_PATTERN.fullmatch(sql)


@pytest.mark.parametrize("bad", [0, -1, "1; DROP", True, 1.5, None])
def test_virtual_sql_rejects_non_positive_integers(bad):
    with pytest.raises(DdlNameError):
        virtual_sql(bad)


def test_virtual_sql_is_built_in_one_place_only():
    """`SELECT * FROM`을 만드는 코드는 naming.py 한 곳뿐이다(AP-2)."""
    hits = [
        path.relative_to(APP).as_posix()
        for path in APP.rglob("*.py")
        if "SELECT * FROM" in path.read_text(encoding="utf-8")
    ]
    assert hits == ["superset/naming.py"]


def test_superset_name_format():
    assert superset_name("영업팀", "월간 매출") == "[영업팀] 월간 매출"


def test_column_labels():
    names = {5: "매출", 6: "비용"}
    assert column_label("team", names) == (True, "팀")
    assert column_label("row_id", names) == (True, "행 번호")
    assert column_label("c_5", names) == (True, "매출")
    assert column_label("c_99", names) == (False, None)  # 정의에 없는 번호는 Superset 값을 유지
    assert column_label("other", names) == (False, None)
    assert column_label("c_5x", names) == (False, None)
    long = column_label("c_5", {5: "가" * 2000})[1]
    assert long is not None and len(long) == 1024


def test_canonical_uuid_is_lowercase_hyphenated():
    value = "AAAAAAAA-2222-3333-4444-555555555555"
    assert canonical_uuid(value) == value.lower()
    assert len(canonical_uuid(value)) == 36


# --- 상수 ----


def test_constants_match_approved_values():
    assert constants.GUEST_TOKEN_EXPIRES_IN == 300
    assert constants.GUEST_TOKEN_RATE_LIMIT == 30
    assert constants.GUEST_TOKEN_RATE_WINDOW_SECONDS == 60
    assert constants.DATABASE_NAME == "BI-Wizard (read-only)"
    assert constants.SCHEMA == "bi_data"
    assert constants.SYNC_DEBOUNCE_SECONDS == 3.0
    assert constants.LOGIN_RETRY_BACKOFF_SECONDS == 30
    assert (constants.BREAKER_FAILURE_THRESHOLD, constants.BREAKER_COOLDOWN_SECONDS) == (3, 30)


def test_database_name_matches_superset_init_constant():
    roles = REPO_ROOT / "superset" / "bi_roles.py"
    if not roles.exists():  # `docker build --target test backend` 이미지에는 superset/가 없다
        pytest.skip("superset/bi_roles.py가 없다(backend만 있는 빌드 컨텍스트)")
    found = re.search(r'^DATABASE_NAME = "(.*)"', roles.read_text(encoding="utf-8"), re.M)
    assert found is not None and found.group(1) == constants.DATABASE_NAME


# --- 속도 제한 ----


def test_limiter_allows_exactly_the_limit_then_blocks():
    clock = Clock()
    limiter = SlidingWindowLimiter(limit=3, window_seconds=60, clock=clock)
    assert [limiter.acquire(1) for _ in range(3)] == [None, None, None]
    retry = limiter.acquire(1)
    assert retry == 60


def test_limiter_is_per_user():
    clock = Clock()
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60, clock=clock)
    assert limiter.acquire(1) is None
    assert limiter.acquire(1) is not None
    assert limiter.acquire(2) is None  # 다른 사용자는 영향이 없다


def test_limiter_recovers_after_window_and_retry_after_counts_down():
    clock = Clock()
    limiter = SlidingWindowLimiter(limit=2, window_seconds=60, clock=clock)
    limiter.acquire(1)
    clock.advance(10)
    limiter.acquire(1)
    clock.advance(20)  # 첫 기록은 30초 전, 둘째는 20초 전
    assert limiter.acquire(1) == 30  # 가장 오래된 기록이 윈도를 벗어날 때까지
    clock.advance(30)
    assert limiter.acquire(1) is None  # 첫 기록이 빠져 한 칸이 난다
    assert limiter.acquire(1) is not None


def test_rejected_requests_are_not_recorded():
    """거절된 요청을 계속 보내도 윈도가 밀리지 않아 영원히 막히지 않는다."""
    clock = Clock()
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60, clock=clock)
    limiter.acquire(1)
    for _ in range(50):
        clock.advance(1)
        assert limiter.acquire(1) is not None
    clock.advance(10)  # 첫 통과 기록으로부터 60초가 지났다
    assert limiter.acquire(1) is None


def test_limiter_retry_after_is_at_least_one_second():
    clock = Clock()
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60, clock=clock)
    limiter.acquire(1)
    clock.advance(59.9)
    assert limiter.acquire(1) == 1


def test_limiter_is_thread_safe_at_the_limit():
    limiter = SlidingWindowLimiter(limit=30, window_seconds=60)
    passed = []

    def worker():
        passed.append(limiter.acquire(7) is None)

    threads = [threading.Thread(target=worker) for _ in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(passed) == 30


def test_limiter_forgets_idle_users():
    clock = Clock()
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60, clock=clock)
    limiter.acquire(1)
    clock.advance(61)
    limiter.forget_idle()
    assert limiter._hits == {}


# --- 서킷 브레이커 ----


def test_breaker_opens_after_consecutive_failures_and_recovers_after_cooldown():
    clock = Clock()
    breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=30, clock=clock)
    for _ in range(2):
        breaker.record_failure()
    assert breaker.allow()
    breaker.record_failure()
    assert not breaker.allow() and breaker.is_open
    clock.advance(29)
    assert not breaker.allow()
    clock.advance(2)
    assert breaker.allow()  # 반열림: 한 번 시도한다
    breaker.record_failure()  # 실패하면 곧바로 다시 열린다
    assert not breaker.allow()
    clock.advance(31)
    assert breaker.allow()
    breaker.record_success()
    breaker.record_failure()
    assert breaker.allow()  # 성공이 연속 실패를 끊었다


def opened_breaker(clock: Clock) -> CircuitBreaker:
    breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=30, clock=clock)
    for _ in range(3):
        breaker.record_failure()
    assert not breaker.allow()
    return breaker


def test_half_open_lets_exactly_one_probe_through_concurrently():
    clock = Clock()
    breaker = opened_breaker(clock)
    clock.advance(31)
    results: list[bool] = []
    start = threading.Barrier(16)

    def caller():
        start.wait()
        results.append(breaker.allow())

    threads = [threading.Thread(target=caller) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(results) == 1  # 시험 호출 1건만 통과하고 나머지는 결과가 날 때까지 막힌다
    assert breaker.is_open
    breaker.record_success()  # 시험 호출 성공: 닫힌다
    assert all(breaker.allow() for _ in range(5))


def test_half_open_probe_failure_reopens_for_another_cooldown_and_blocks_others():
    clock = Clock()
    breaker = opened_breaker(clock)
    clock.advance(31)
    assert breaker.allow()  # 시험 호출
    assert not breaker.allow()  # 진행 중에는 다른 호출을 막는다
    clock.advance(10)
    assert not breaker.allow()
    breaker.record_failure()  # 시험 실패: 쿨다운을 다시 센다
    assert not breaker.allow()
    clock.advance(29)
    assert not breaker.allow()
    clock.advance(2)
    assert breaker.allow() and not breaker.allow()  # 다시 한 건만


def test_half_open_does_not_stay_blocked_forever_if_the_probe_never_reports():
    clock = Clock()
    breaker = opened_breaker(clock)
    clock.advance(31)
    assert breaker.allow()  # 시험 호출이 나갔지만 결과가 기록되지 않는다(예기치 않은 예외 등)
    assert not breaker.allow()
    clock.advance(31)
    assert breaker.allow()  # 쿨다운만큼 지나면 다음 한 건을 다시 통과시킨다
    assert not breaker.allow()


def test_release_probe_frees_the_half_open_slot_without_recording_anything():
    clock = Clock()
    breaker = opened_breaker(clock)
    breaker.release_probe()  # 닫혀 있지 않지만 시험 호출이 없다: 아무 일도 없다
    assert not breaker.allow()
    clock.advance(31)
    assert breaker.allow() and not breaker.allow()  # 시험 호출 한 건
    breaker.release_probe()  # 로컬 오류로 끝났다: 성공도 실패도 아니다
    assert breaker.is_open
    assert breaker.allow()  # 다음 호출이 시험한다


# --- 사용자별 한도 기록의 정리 ----


def test_limiter_sweeps_idle_users_on_its_own_once_per_window():
    clock = Clock()
    limiter = SlidingWindowLimiter(limit=5, window_seconds=60, clock=clock)
    for user_id in range(100):
        assert limiter.acquire(user_id) is None
    assert limiter.tracked_users() == 100
    clock.advance(30)
    limiter.acquire(1000)
    assert limiter.tracked_users() == 101  # 윈도가 아직 안 지났으니 정리하지 않는다
    clock.advance(31)  # 처음 100명은 윈도가 지났다
    limiter.acquire(1001)  # 호출 경로가 스스로 정리한다(forget_idle을 따로 부르지 않는다)
    assert limiter.tracked_users() == 2  # 1000(윈도 안)과 방금의 1001
    assert limiter.acquire(1000) is None  # 정리가 아직 유효한 기록을 지우지 않았다


def test_limiter_sweep_keeps_the_limit_for_users_still_inside_the_window():
    clock = Clock()
    limiter = SlidingWindowLimiter(limit=2, window_seconds=60, clock=clock)
    assert limiter.acquire(1) is None and limiter.acquire(1) is None
    clock.advance(59)
    limiter.acquire(2)
    clock.advance(2)  # 사용자 1의 기록은 61초 전: 윈도가 지났다
    assert limiter.acquire(3) is None
    assert limiter.tracked_users() == 2  # 2와 3
    assert limiter.acquire(1) is None  # 새로 시작


# --- 사유 코드 ----


def test_reason_summaries_never_carry_free_text():
    for code, text in REASON_SUMMARY.items():
        assert re.fullmatch(r"[A-Z_0-9]+", code)
        assert "http" not in text and "SELECT" not in text
        assert summarize(code) == f"{code}: {text}"
        assert len(summarize(code)) <= constants.LAST_ERROR_MAX_LENGTH
    assert summarize("REJECTED_422").startswith("REJECTED_422: ")
    # 알 수 없는 글자는 요약에 옮기지 않는다(응답 본문 문구 등).
    assert summarize("SELECT * FROM secret; password=abc") == summarize("INTERNAL")
    assert summarize("REJECTED_422 secret") == summarize("INTERNAL")


# --- 정적 규칙 ----


def test_backend_has_no_jwt_signing_or_guest_secret():
    """AP-1: backend는 입장권을 직접 서명하지 않는다(서명 키·JWT 라이브러리·hmac 흔적 없음)."""
    banned = re.compile(
        r"GUEST_TOKEN_JWT_SECRET|import jwt|from jwt|jose|PyJWT|import hmac|from hmac|HS256|RS256",
        re.IGNORECASE,
    )
    hits = [p.name for p in APP.rglob("*.py") if banned.search(p.read_text(encoding="utf-8"))]
    assert hits == []
    requirements = (APP.parent / "requirements.txt").read_text(encoding="utf-8")
    assert not re.search(r"jwt|jose|authlib", requirements, re.IGNORECASE)


def test_superset_module_never_logs_response_bodies_or_tokens():
    """로그 호출에 응답 본문·토큰·예외 메시지를 넘기는 코드가 없다(클래스 이름과 사유 코드만)."""
    for path in (APP / "superset").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for call in re.findall(r"logger\.\w+\((?:.|\n)*?\)\n", text):
            assert ".text" not in call and "response" not in call.lower(), (path.name, call)
            assert "token" not in call.lower() or "토큰" in call, (path.name, call)
            assert "str(error)" not in call and "exc_info" not in call, (path.name, call)


def test_no_text_sql_in_superset_module():
    import ast

    for path in (APP / "superset").glob("*.py"):
        calls = {
            getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.Call)
        }
        assert not calls & {"text", "exec_driver_sql"}, path.name


# --- 연동 켜기 조건 ----


def test_integration_needs_all_five_settings(monkeypatch):
    from app.config import Settings
    from app.superset.runtime import build_superset_services, superset_configured
    from tests.superset_helpers import SUPERSET_ENV

    def settings_with(env: dict[str, str]) -> Settings:
        for name in SUPERSET_ENV:
            monkeypatch.delenv(name, raising=False)
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        return Settings()  # type: ignore[call-arg]

    assert superset_configured(settings_with(SUPERSET_ENV))
    assert build_superset_services(settings_with({})) is None
    for missing in SUPERSET_ENV:
        partial = {k: v for k, v in SUPERSET_ENV.items() if k != missing}
        settings = settings_with(partial)
        assert not superset_configured(settings), missing
        assert build_superset_services(settings) is None
    blank = dict(SUPERSET_ENV, SUPERSET_GUEST_ISSUER_PASSWORD="")
    assert not superset_configured(settings_with(blank))


def test_services_repr_does_not_show_passwords(make_settings):
    from app.superset.runtime import build_superset_services
    from tests.superset_helpers import ISSUER, SERVICE, SUPERSET_ENV

    services = build_superset_services(make_settings(**SUPERSET_ENV))
    assert services is not None
    text = repr(services) + repr(services.sessions)
    assert SERVICE[1] not in text and ISSUER[1] not in text
    services.stop()
