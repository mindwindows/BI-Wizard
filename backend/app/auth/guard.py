"""라우터 조립 규칙의 검사: 공개 경로 밖의 모든 라우트는 `current_user`를 거쳐야 한다.

- 시작 때: 공개 목록에 넣은 라우터가 `PUBLIC_PATHS` 밖의 경로를 갖고 있으면 시작을 거부한다
  (`check_public_routers`, fail-closed). 보호 라우터는 조립 때 `current_user`가 전체에 붙는다.
- 시험에서: 앱의 모든 경로를 인증 없이 호출해 공개 경로 밖이 전부 401인지 확인한다
  (`tests/test_auth.py`). FastAPI 내부 라우트 구조에 기대지 않는 동작 기반 검사다.
"""

from __future__ import annotations

from collections.abc import Iterable

from fastapi import APIRouter
from fastapi.routing import APIRoute

# 인증 없이 열려 있는 경로(`/api` 뒤까지 포함, 05 §2-6 H1·H2). 다른 경로를 공개하려면 계약 변경이다.
PUBLIC_PATHS = frozenset({"/api/health", "/api/health/db"})


def check_public_routers(routers: Iterable[APIRouter], prefix: str) -> None:
    """공개 라우터의 모든 경로가 `PUBLIC_PATHS` 안인지 확인한다. 아니면 RuntimeError."""
    outside = []
    for router in routers:
        for route in router.routes:
            if isinstance(route, APIRoute):
                full_path = f"{prefix}{route.path}"
                if full_path not in PUBLIC_PATHS:
                    outside.append(full_path)
            else:  # 중첩 포함 라우터 등 확인할 수 없는 항목도 공개로 둘 수 없다.
                outside.append(repr(route))
    if outside:
        raise RuntimeError(f"공개 라우터에 인증이 필요한 경로가 섞여 있다: {sorted(outside)}")
