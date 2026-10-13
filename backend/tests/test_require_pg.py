"""CI 전용 시험 옵션 `REQUIRE_PG=1`(03b 17-1 결정 7): PG 시험 환경이 없을 때 건너뛰지 않고 실패.

미설정이면 기존처럼 건너뛴다. 이 변수는 시험을 실행하는 환경에서만 읽으며 `.env`·`.env.example`·
compose에는 없다.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import pg_unavailable, require_pg_enabled

BACKEND = Path(__file__).resolve().parent.parent
PG_TEST = "tests/test_startup_check.py::test_pg_bi_app_passes_all_checks"


@pytest.mark.parametrize(
    ("environ", "enabled"),
    [
        ({}, False),
        ({"REQUIRE_PG": ""}, False),
        ({"REQUIRE_PG": "0"}, False),
        ({"REQUIRE_PG": "true"}, False),
        ({"REQUIRE_PG": "1"}, True),
    ],
)
def test_only_exact_one_enables_require_pg(environ, enabled):
    assert require_pg_enabled(environ) is enabled


def test_pg_unavailable_skips_by_default_and_fails_when_required():
    with pytest.raises(pytest.skip.Exception):
        pg_unavailable("환경 없음", require=False)
    with pytest.raises(pytest.fail.Exception) as error:
        pg_unavailable("환경 없음", require=True)
    assert "REQUIRE_PG=1" in str(error.value)


def _run_pg_test_without_database(require: str | None) -> subprocess.CompletedProcess[str]:
    """PostgreSQL 접속 정보가 없는 환경에서 `pg` 시험 하나를 실제로 실행한다."""
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("POSTGRES_", "REQUIRE_PG"))
    }
    if require is not None:
        env["REQUIRE_PG"] = require
    return subprocess.run(  # noqa: S603 - 인자는 이 파일의 상수뿐이다
        [sys.executable, "-m", "pytest", PG_TEST, "-p", "no:cacheprovider", "-o", "addopts="],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_missing_database_is_skipped_without_require_pg():
    result = _run_pg_test_without_database(None)
    assert result.returncode == 0, result.stdout
    assert "1 skipped" in result.stdout and "failed" not in result.stdout


def test_missing_database_fails_with_require_pg():
    result = _run_pg_test_without_database("1")
    assert result.returncode == 1, result.stdout
    # 환경이 없는 것은 fixture 준비 단계의 실패라 pytest가 "error"로 센다(종료 코드 1, CI 실패).
    assert "1 error" in result.stdout and "REQUIRE_PG=1" in result.stdout
    assert "skipped" not in result.stdout
