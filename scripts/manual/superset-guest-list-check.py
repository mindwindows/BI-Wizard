#!/usr/bin/env python3
"""Superset guest 입장권 목록 API 회귀 스모크(수동 실행, CI에서 돌지 않는다).

무엇을 확인하나 (08 §3, 03b 24절)
  포털 E6(`POST {base}/api/dashboards/{포털 번호}/guest-token`)으로 받은 guest 입장권으로
  Superset 목록 API를 부르면 아래와 같아야 한다.
    1. `GET /api/v1/dashboard/` 200이고 결과가 토큰 대시보드 1개뿐(id가 --superset-dashboard-id)
    2. `GET /api/v1/chart/`     200이고 결과 0개
    3. `GET /api/v1/dataset/`   403
    4. 입장권 payload의 `exp - iat == 300`
  Superset 업그레이드, `bi_guest` 역할·훅·`PUBLIC_ROLE_LIKE` 변경 뒤에 다시 돌린다.

전제 (실제 Superset이 떠 있어야 한다)
  - 로컬 스택이 인증 스텁(`AUTH_STUB_ENABLED=true`, `APP_ENV=local`)으로 떠 있고, 포털 대시보드
    연결(S8)이 이미 등록되어 있으며 그 Superset 대시보드의 임베드가 켜져 있다.
  - --user는 대시보드를 볼 수 있는 더미 스텁 사용자의 로그인 ID다. 실제 계정이나 비밀번호를
    쓰지 않는다. 비밀값은 인자·환경변수·파일 어디에도 필요 없다.

출력
  건수·상태 코드·숫자·PASS/FAIL뿐이다. 입장권과 응답 본문은 출력하지 않고 저장하지도 않는다.
  종료 코드: 0 모두 통과, 1 하나라도 실패, 2 입장권을 받지 못함(전제 문제).

실행 방법 (표준 라이브러리만 쓴다. 저장소 루트에서)
  QA 더미 env로 스택을 띄운다(`_workspace/qa/`의 git 제외 임시 env 파일, 비밀은 더미 값).
  접두를 떼는 프록시 설정(`APP_PROXY_STRIP_PREFIX`) true와 false 두 가지로 각각 띄워 돌린다.
  **STRIP true의 전제:** 앞단 프록시가 접두를 떼고 backend·Superset으로 넘기는 구성이므로, 이 스크립트의
  `--origin`은 그 프록시 주소여야 하고, **대시보드의 Superset 쪽 허용 도메인(allowed_domains)에 그 프록시
  origin이 들어 있어야** 한다(없으면 임베드 HTML이 403이다. 목록 API 단정 자체는 영향이 없다).
  입장권의 `iat`·`exp`는 JSON 실수(float)로 올 수 있으며 스크립트는 정수·실수 모두 받는다.

    # 예: STRIP=true 스택(프런트 nginx가 http://127.0.0.1:37180 에서 응답)
    python3 scripts/manual/superset-guest-list-check.py \\
        --origin http://127.0.0.1:37180 --base-path /bi-wizard \\
        --portal-dashboard 1 --superset-dashboard-id 1 \\
        --cookie-name bi_stub_login --user stub-viewer --label strip-true

    # STRIP=false 스택으로 다시 띄운 뒤(down -v 쓰지 않는다: stop 후 env 파일만 바꿔 up -d)
    # 같은 명령을 --label strip-false 로 한 번 더 돌린다.

  인자 설명
    --origin               포털 origin(스킴+호스트+포트, 경로 없음)
    --base-path            `APP_BASE_PATH`(기본 /bi-wizard). 루트 배포면 빈 문자열 ""
    --portal-dashboard     포털 대시보드 번호(S8에서 등록한 번호, E6 경로에 쓴다)
    --superset-dashboard-id  Superset 쪽 그 대시보드의 숫자 id(Superset 화면 주소의 번호)
    --cookie-name          스텁 로그인 쿠키 이름(기본 bi_stub_login)
    --user                 스텁 사용자 로그인 ID(더미)
    --superset-root        Superset 하위 경로(기본 `<base-path>/superset`, `SUPERSET_APP_ROOT`)
    --label                출력에 붙일 이름(예: strip-true)
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import urllib.error
import urllib.request
from urllib.parse import quote, urlparse

EXPECTED_TOKEN_SECONDS = 300
TIMEOUT_SECONDS = 60

results: list[bool] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append(ok)
    suffix = f"  | {detail}" if (detail and not ok) else ""
    print(f"{'PASS' if ok else 'FAIL'} {name}{suffix}", flush=True)


def request(
    url: str, *, method: str = "GET", headers: dict[str, str] | None = None
) -> tuple[int, dict]:
    """상태 코드와 JSON 본문(없거나 JSON이 아니면 빈 dict)을 돌려준다. 본문은 출력하지 않는다."""
    if urlparse(url).scheme not in ("http", "https"):
        raise ValueError("http 또는 https 주소만 쓴다")
    req = urllib.request.Request(url, method=method, headers=headers or {})  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as exc:
        status, raw = exc.code, exc.read()
    try:
        body = json.loads(raw)
    except ValueError:
        body = {}
    return status, body if isinstance(body, dict) else {}


def token_times(token: str) -> tuple[float | None, float | None]:
    """입장권(JWT) payload의 iat·exp만 읽는다. 서명은 검증하지 않고 값은 출력하지 않는다."""
    try:
        payload = token.split(".")[1]
        decoded = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return decoded.get("iat"), decoded.get("exp")
    except (IndexError, ValueError):
        return None, None


def main() -> int:
    parser = argparse.ArgumentParser(description="Superset guest 목록 API 회귀 스모크(수동)")
    parser.add_argument("--origin", required=True)
    parser.add_argument("--base-path", default="/bi-wizard")
    parser.add_argument("--portal-dashboard", type=int, required=True)
    parser.add_argument("--superset-dashboard-id", type=int, required=True)
    parser.add_argument("--cookie-name", default="bi_stub_login")
    parser.add_argument("--user", required=True)
    parser.add_argument("--superset-root", default=None)
    parser.add_argument("--label", default="run")
    args = parser.parse_args()

    base = args.origin.rstrip("/") + args.base_path.rstrip("/")
    superset = args.origin.rstrip("/") + (
        args.superset_root.rstrip("/")
        if args.superset_root is not None
        else args.base_path.rstrip("/") + "/superset"
    )
    label = args.label

    status, body = request(
        f"{base}/api/dashboards/{args.portal_dashboard}/guest-token",
        method="POST",
        headers={"Cookie": f"{args.cookie_name}={quote(args.user, safe='')}"},
    )
    token = body.get("token") if status == 200 else None
    if not isinstance(token, str) or not token:
        print(f"FAIL [{label}] 포털 E6 입장권 발급 실패(상태 {status}). 전제를 확인한다.")
        return 2
    print(f"PASS [{label}] 포털 E6 200 (입장권은 출력하지 않는다)")

    iat, exp = token_times(token)
    seconds = (
        exp - iat
        if isinstance(iat, (int, float)) and isinstance(exp, (int, float))
        else None
    )
    check(
        f"[{label}] exp - iat == {EXPECTED_TOKEN_SECONDS}",
        seconds == EXPECTED_TOKEN_SECONDS,
        f"값={seconds}",
    )

    guest = {"X-GuestToken": token}

    status, body = request(f"{superset}/api/v1/dashboard/", headers=guest)
    result = body.get("result", []) if isinstance(body.get("result"), list) else []
    ids = [item.get("id") for item in result if isinstance(item, dict)]
    check(f"[{label}] guest GET /dashboard/ 200", status == 200, f"상태={status}")
    check(
        f"[{label}] 대시보드 1개(count={body.get('count')}, 결과 {len(result)}개)",
        len(result) == 1 and body.get("count") == 1,
        f"결과={len(result)}, count={body.get('count')}",
    )
    check(
        f"[{label}] 그 1개가 토큰 대시보드(id == {args.superset_dashboard_id})",
        ids == [args.superset_dashboard_id],
        f"id 목록={ids}",
    )

    status, body = request(f"{superset}/api/v1/chart/", headers=guest)
    result = body.get("result", []) if isinstance(body.get("result"), list) else []
    check(f"[{label}] guest GET /chart/ 200", status == 200, f"상태={status}")
    check(
        f"[{label}] 차트 0개(count={body.get('count')}, 결과 {len(result)}개)",
        len(result) == 0 and body.get("count") == 0,
        f"결과={len(result)}, count={body.get('count')}",
    )

    status, _ = request(f"{superset}/api/v1/dataset/", headers=guest)
    check(f"[{label}] guest GET /dataset/ 403", status == 403, f"상태={status}")

    passed = sum(results)
    print(f"{'PASS' if all(results) else 'SOME FAIL'} {passed}/{len(results)}")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
