# BI-Wizard

엑셀 데이터를 가져와 데이터셋을 만들고, 수식 열과 Superset 대시보드로 분석하는 사내 포털입니다. 현재는 **Gate ② 환경 구축** 단계라서 업무 기능은 없고, 누구나 같은 명령으로 실행·검증할 수 있는 환경만 있습니다. 요구사항은 `docs/project-brief.md`, 팀 웹서버 운영 가이드는 `docs/AI_AGENT_DEVELOPMENT_GUIDE_요약.md`입니다.

> **Gate ② 한정 구성:** 이 환경에서는 PostgreSQL 슈퍼유저(`POSTGRES_USER`)를 앱과 마이그레이션 계정으로 함께 씁니다. **Gate ④ 진입 전에 최소 권한 앱 계정으로 분리해야 합니다.**

## 구성

| 서비스 | 역할 |
| --- | --- |
| `postgres` | PostgreSQL 16 (앱 DB + Superset 메타 DB) |
| `db-bootstrap` | (일회성) 읽기 전용 계정 `bi_readonly`, Superset 메타 DB 생성 |
| `migrate` | (일회성) Alembic 마이그레이션 실행 |
| `backend` | FastAPI (`/api/health`, `/api/health/db`) |
| `frontend` | 포털 정적 파일 + nginx (로컬에서 메인 플랫폼 프록시 역할) |
| `superset-init`, `superset` | Apache Superset 6.1.0 (초기화 일회성 + 웹) |

포털과 Superset은 메인 플랫폼의 **URL 하위 경로** 아래에서 서비스됩니다(기본 예시: `/bi-wizard`, `/bi-wizard/superset`). 실제 값은 웹서버 배포 때 운영자와 정합니다.

## 준비물
- Docker Engine과 Docker Compose v2 (Windows는 Docker Desktop 또는 호환 도구)
- Windows에서 BAT를 쓰려면 `curl.exe`(Windows 10 이후 기본 포함)

## 최소 실행 절차 (Windows)
1. 저장소를 받고 `.env.example`을 `.env`로 복사합니다. `.env`는 Git에 올라가지 않습니다.
   ```
   copy .env.example .env
   ```
2. `.env`에서 **비어 있는 Secret 6개**를 채웁니다: `POSTGRES_PASSWORD`, `POSTGRES_READONLY_PASSWORD`, `SUPERSET_DB_PASSWORD`, `SUPERSET_SECRET_KEY`, `GUEST_TOKEN_JWT_SECRET`, `SUPERSET_ADMIN_PASSWORD`.
   생성 예: `python -c "import secrets; print(secrets.token_urlsafe(32))"` 또는 `openssl rand -hex 32`. 값은 영문, 숫자, `-`, `_`만 쓰세요(`$`, `%`, `#`, 따옴표, 공백은 쓰지 않습니다). Secret은 저장소, 이미지, 프런트 번들에 넣지 않습니다.
3. 검증하고 시작합니다.
   ```
   scripts\validate-env.bat
   scripts\start-local.bat
   scripts\health-check.bat
   ```
   첫 기동은 이미지 빌드 때문에 몇 분 걸립니다.
4. 브라우저에서 엽니다.
   - 포털: `http://localhost:5173/bi-wizard/` (API와 DB 상태가 "정상"으로 보입니다)
   - Superset: `http://localhost:5173/bi-wizard/superset/` (`SUPERSET_ADMIN_USER`, `SUPERSET_ADMIN_PASSWORD`로 로그인)
5. 로그와 종료.
   ```
   scripts\logs-local.bat backend
   scripts\stop-local.bat
   ```

BAT의 출력은 ASCII 영어로 `[OK]`, `[FAIL]`, `[MISSING]`, `[EMPTY]`처럼 표시됩니다(일부 Windows cmd에서 UTF-8 BAT가 오동작할 수 있어 영문만 씁니다). BAT 대신 같은 동작의 명령: `docker compose up -d --build` / `docker compose ps` / `docker compose logs -f backend` / `docker compose down`. **`docker compose down -v`는 쓰지 않습니다**(DB 데이터가 사라집니다).

## 자주 바꾸는 값
- `.env`의 `APP_BASE_PATH`, `SUPERSET_APP_ROOT`: 하위 경로. 앞 `/` 필수, 뒤 `/`와 `.`/`..` 세그먼트 금지. **빈 값(루트 배포)은 `APP_BASE_PATH`만 허용**하고 `SUPERSET_APP_ROOT`는 비울 수 없습니다. 바꾼 뒤 `scripts\restart-local.bat`.
- `APP_PROXY_STRIP_PREFIX`: 프록시가 접두를 떼고 전달하면 `true`, 유지하면 `false`(기본). 바꾼 뒤 다시 시작하면 됩니다(이미지 재빌드 불필요). backend는 `${APP_BASE_PATH}/api/…`와 접두 없는 `/api/…`를 모두 받으며, 이 값은 프록시(nginx)가 보내는 경로를 바꿉니다.
- `FRONTEND_HOST`: 기본 `127.0.0.1`(이 PC에서만 접속). 같은 LAN에 열려면 `0.0.0.0`이지만 그러면 Superset 관리자 로그인 화면도 LAN에 노출됩니다.
- 포트가 겹치면 `FRONTEND_PORT`, `POSTGRES_PORT`, `BACKEND_PORT`를 바꿉니다.

## 테스트와 검증
```
docker build --target test backend      # ruff + pytest
docker build --target test frontend     # eslint + tsc + vitest
docker compose config --quiet           # compose 구성 검증
```
마이그레이션 왕복 테스트(빈 테스트 DB), 하위 경로 전환, 문제 해결은 `skills/local-environment/SKILL.md`를 보세요.

## 폴더
```
backend/    FastAPI, Alembic(migrations/), db-bootstrap(bootstrap/), Dockerfile
frontend/   React(Vite) 정적 빌드, nginx 설정 템플릿, Dockerfile
superset/   Superset 6.1.0 위에 PostgreSQL 드라이버와 고정 설정을 얹는 Dockerfile
scripts/    start/stop/restart/logs/health-check/validate-env .bat, CI용 ci-validate-env.sh
skills/     제품 기능 사용설명서 (local-environment부터)
docs/       요구사항 브리프, 운영 가이드, 결정 기록, Gate 진행 상태
references/ 선택된 Reference 소스
```
AI 도구와 기여 규칙은 `AGENTS.md`를 보세요.

## 알아 둘 점
- Superset 컨테이너는 gunicorn 워커 1개를 주기적으로 재시작하지 않습니다(재시작 순간 502가 나기 때문). 메모리 누수 보호는 `mem_limit`과 `restart: unless-stopped`에 맡기므로, 한도에 닿으면 컨테이너가 재시작되며 그동안 요청이 실패할 수 있습니다.
- frontend 컨테이너의 nginx 마스터 프로세스는 root로 실행됩니다. 공식 nginx 이미지의 기본 동작이며 의도적인 선택입니다(필요하면 `nginx-unprivileged` 이미지로 전환할 수 있습니다).
