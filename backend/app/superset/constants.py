"""`superset` 모듈의 코드 상수(환경변수로 만들지 않는다, AP-12)."""

from __future__ import annotations

import httpx

from app.db_metadata import DYNAMIC_SCHEMA

# Superset에 등록된 업무 데이터 연결의 표시 이름. `superset/bi_roles.py`의 `DATABASE_NAME`과 같은
# 값이어야
# 한다(`tests/test_superset_constants.py`가 대조한다). 번호는 환경에 따라 달라 이름으로 조회한다.
DATABASE_NAME = "BI-Wizard (read-only)"
# 가상 데이터셋의 schema.
SCHEMA = DYNAMIC_SCHEMA

# 입장권 유효 시간(초). 상수이며 backend는 토큰을 해석하지 않는다(AP-1). `superset-init`이
# Superset의
# 적용값 300을 가드한다(`bi_roles.GUEST_TOKEN_EXP_SECONDS`).
GUEST_TOKEN_EXPIRES_IN = 300

# 입장권 발급 속도 제한(승인 03b 23-1 C): 사용자당 슬라이딩 윈도 60초에 30회.
# 저장은 프로세스 메모리이므로 backend 워커가 여러 개면 한도가 워커별로 걸린다(실효 한도 = 워커 수
# 배).
# 지금은 워커 1개 전제다(`app/__main__.py`). 워커를 늘리면 저장소를 재설계한다(08 §4).
GUEST_TOKEN_RATE_LIMIT = 30
GUEST_TOKEN_RATE_WINDOW_SECONDS = 60.0

# 서비스 계정(등록·새로고침이 느릴 수 있음)과 발급 계정의 타임아웃. 자동 재시도는 하지 않는다.
SERVICE_TIMEOUT = httpx.Timeout(connect=2.0, read=15.0, write=5.0, pool=5.0)
ISSUER_TIMEOUT = httpx.Timeout(connect=2.0, read=5.0, write=5.0, pool=2.0)
HEALTH_TIMEOUT = httpx.Timeout(connect=2.0, read=3.0, write=3.0, pool=2.0)

# 발급 호출의 동시 실행 수(요청 스레드 풀을 Superset 장애가 다 붙잡지 않게 한다, P4).
ISSUER_MAX_CONCURRENT = 4

# 서킷 브레이커: 연결 실패·시간 초과·5xx가 연속 이 횟수이면 일정 시간 호출을 건너뛴다.
BREAKER_FAILURE_THRESHOLD = 3
BREAKER_COOLDOWN_SECONDS = 30.0

# Superset 준비 확인(`{root}/health`)과 복구 재시도 간격.
STARTUP_HEALTH_INTERVAL_SECONDS = 10.0
STARTUP_HEALTH_MAX_WAIT_SECONDS = 600.0
RETRY_INTERVAL_SECONDS = 60.0

# 사유 요약(`last_error`) 최대 길이.
LAST_ERROR_MAX_LENGTH = 200
