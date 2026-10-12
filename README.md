# BI-Wizard

엑셀 데이터를 가져와 데이터셋을 만들고, 수식 열과 Superset 대시보드로 분석하는 사내 포털입니다. 현재는 **Gate ② 환경 구축** 단계라서 업무 기능은 없고, 누구나 같은 명령으로 실행·검증할 수 있는 환경만 있습니다. 요구사항은 `docs/project-brief.md`, 팀 웹서버 운영 가이드는 `docs/AI_AGENT_DEVELOPMENT_GUIDE_요약.md`입니다.

> **DB 계정 분리 (EW-1):** Gate ②에서는 PostgreSQL 슈퍼유저(`POSTGRES_USER`)를 앱과 마이그레이션 계정으로 함께 썼습니다(Gate ② 한정 구성). 이 구성은 해소되어, 이제 `POSTGRES_USER`/`POSTGRES_PASSWORD`는 **PostgreSQL 이미지의 슈퍼유저 전용**입니다(이미지 초기화, healthcheck, `db-bootstrap`만 씁니다. 운영 가이드의 `POSTGRES_USER`=앱 계정 의미와 다른 의도적 차이입니다). `migrate`는 `bi_owner`(비밀번호 `POSTGRES_OWNER_PASSWORD`), `backend`는 `bi_app`(비밀번호 `POSTGRES_APP_PASSWORD`)로 접속하고, 계정 이름은 코드 상수입니다.

## 구성

| 서비스 | 역할 |
| --- | --- |
| `postgres` | PostgreSQL 16 (앱 DB + Superset 메타 DB) |
| `db-bootstrap` | (일회성, 슈퍼유저로 접속하는 유일한 서비스) 계정 `bi_owner`·`bi_app`·`bi_readonly`·`superset_meta`, 빈 schema `bi_data`, Superset 메타 DB 생성 |
| `migrate` | (일회성) Alembic 마이그레이션 실행 (`bi_owner`) |
| `backend` | FastAPI (`/api/health`, `/api/health/db`) (`bi_app`) |
| `frontend` | 포털 정적 파일 + nginx (로컬에서 메인 플랫폼 프록시 역할) |
| `superset-init`, `superset` | Apache Superset 6.1.0 (초기화 일회성 + 웹). `superset-init`은 `migrate` 완료 뒤에 시작해 업무 데이터 연결, 역할 5개(`bi_service`, `bi_guest_issuer`, `bi_author`, `bi_author_schema`, `bi_guest`), 서비스·발급 전용 계정 2개를 매 기동 멱등으로 맞춥니다 |

포털과 Superset은 메인 플랫폼의 **URL 하위 경로** 아래에서 서비스됩니다(기본 예시: `/bi-wizard`, `/bi-wizard/superset`). 실제 값은 웹서버 배포 때 운영자와 정합니다.

## 준비물
- Docker Engine과 Docker Compose v2 (Windows는 Docker Desktop 또는 호환 도구)
- Windows에서 BAT를 쓰려면 `curl.exe`(Windows 10 이후 기본 포함)

## 최소 실행 절차 (Windows)
1. 저장소를 받고 `.env.example`을 `.env`로 복사합니다. `.env`는 Git에 올라가지 않습니다.
   ```
   copy .env.example .env
   ```
2. `.env`에서 **비어 있는 Secret 10개**를 서로 다른 값으로 채웁니다: `POSTGRES_PASSWORD`(이미지 슈퍼유저), `POSTGRES_APP_PASSWORD`(backend), `POSTGRES_OWNER_PASSWORD`(migrate), `POSTGRES_READONLY_PASSWORD`, `SUPERSET_DB_PASSWORD`, `SUPERSET_SECRET_KEY`, `GUEST_TOKEN_JWT_SECRET`, `SUPERSET_ADMIN_PASSWORD`, `SUPERSET_SERVICE_PASSWORD`(Superset 서비스 계정), `SUPERSET_GUEST_ISSUER_PASSWORD`(Superset 입장권 발급 전용 계정).
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

**Superset 계정 변수(EW-3):** `SUPERSET_SERVICE_USER`(기본 `bi_service`), `SUPERSET_GUEST_ISSUER_USER`(기본 `bi_guest_issuer`)와 두 비밀번호는 `superset-init`이 서비스 계정·발급 전용 계정을 만들 때 쓰며 backend도 받습니다(사용은 FU-1e). 세 계정 이름(관리자 포함)은 서로 달라야 하고 **서비스 계정 이름은 바꾸지 않습니다**. 비밀번호를 바꾸면 `docker compose up -d`로 반영됩니다. 이 변수가 없는 예전 `.env`는 `up`이 `required variable … is missing`으로 멈추므로 `.env.example`에서 4줄을 추가하고 비밀번호 2개를 채우세요. 같은 이름의 기존 Superset 계정이 표식(이름 `BI-Wizard`, 이메일 `<이름>@localhost`) 없이 있으면 `superset-init`이 아무것도 바꾸지 않고 실패하므로 `.env`의 계정 이름을 바꾸거나 `skills/local-environment/SKILL.md`의 "표식 없는 기존 계정 정리"를 따릅니다. 입장권 유효 시간(`GUEST_TOKEN_JWT_EXP_SECONDS`)이 300초가 아니면 `superset-init`이 실패합니다. `docker compose logs superset-init`에서 `경고:`(표식이 있는 서비스·발급 계정의 허용 밖 역할을 제거해 강제 복구한 경우)와 마지막 `점검 요약: 강제 복구 N건`을 확인할 수 있습니다. 임베딩 대시보드용 guest 역할은 `bi_guest`(권한 4개)이고 입장권 요청은 Superset의 검증 훅이 점검합니다. 로그에서 `점검 필요: 역할 bi_author`가 보이면 `skills/local-environment/SKILL.md`의 "Superset 업그레이드 점검"을 따릅니다.

**Gate ② 때 만든 DB 볼륨이 이미 있는 PC:** `.env`에 `POSTGRES_APP_PASSWORD`, `POSTGRES_OWNER_PASSWORD`, `AUTH_STUB_ENABLED=false`를 추가한 뒤 `scripts\start-local.bat`(또는 `docker compose up -d --build`)만 하면 됩니다. `db-bootstrap`이 새 계정을 만들고 기존 `alembic_version` 표의 소유자를 `bi_owner`로 바꾸며, `migrate`가 새 revision(`0002`)을 적용합니다. 데이터는 지워지지 않습니다.

BAT의 출력은 ASCII 영어로 `[OK]`, `[FAIL]`, `[MISSING]`, `[EMPTY]`처럼 표시됩니다(일부 Windows cmd에서 UTF-8 BAT가 오동작할 수 있어 영문만 씁니다). BAT 대신 같은 동작의 명령: `docker compose up -d --build` / `docker compose ps` / `docker compose logs -f backend` / `docker compose down`. **`docker compose down -v`는 쓰지 않습니다**(DB 데이터가 사라집니다).

## 자주 바꾸는 값
- `.env`의 `APP_BASE_PATH`, `SUPERSET_APP_ROOT`: 하위 경로. 앞 `/` 필수, 뒤 `/`와 `.`/`..` 세그먼트 금지. **빈 값(루트 배포)은 `APP_BASE_PATH`만 허용**하고 `SUPERSET_APP_ROOT`는 비울 수 없습니다. 바꾼 뒤 `scripts\restart-local.bat`.
- `APP_PROXY_STRIP_PREFIX`: 프록시가 접두를 떼고 전달하면 `true`, 유지하면 `false`(기본). 바꾼 뒤 다시 시작하면 됩니다(이미지 재빌드 불필요). backend는 `${APP_BASE_PATH}/api/…`와 접두 없는 `/api/…`를 모두 받으며, 이 값은 프록시(nginx)가 보내는 경로를 바꿉니다.
- `AUTH_STUB_ENABLED`: 인증 스텁(시험용 사용자로 접속자를 흉내 내는 임시 기능) 스위치. 기본 `false`. 값은 `true`/`false`로 씁니다(그 밖의 값은 CI의 `scripts/ci-validate-env.sh`가 `.env.example`에서 거부합니다). `true`는 개발·시험 전용이라서 `APP_ENV`가 `.env`에 **명시적으로** `local` 또는 `test`일 때만 backend가 시작하고, 그 밖의 값(`production`, `staging`, 빈 값, 설정 없음)에서는 시작을 거부합니다. 스텁 로그인 화면·API는 아직 없습니다(FU-1a).
- `FRONTEND_HOST`: 기본 `127.0.0.1`(이 PC에서만 접속). 같은 LAN에 열려면 `0.0.0.0`이지만 그러면 Superset 관리자 로그인 화면도 LAN에 노출됩니다.
- 포트가 겹치면 `FRONTEND_PORT`, `POSTGRES_PORT`, `BACKEND_PORT`를 바꿉니다.

## 테스트와 검증
```
docker build --target test backend      # ruff + pytest
docker build --target test frontend     # eslint + tsc + vitest
docker compose config --quiet           # compose 구성 검증
```
`docker build --target test backend`의 pytest는 DB 없이 마이그레이션 규칙(head 1개, 고정 SQL, DROP 확인 기록, 오프라인 SQL)과 스텁 스위치 판정을 확인합니다. DB가 필요한 `alembic check`와 마이그레이션 왕복 테스트(빈 테스트 DB), 하위 경로 전환, 문제 해결은 `skills/local-environment/SKILL.md`를 보세요.

## 폴더
```
backend/    FastAPI, Alembic(migrations/), db-bootstrap(bootstrap/), Dockerfile
frontend/   React(Vite) 정적 빌드, nginx 설정 템플릿, Dockerfile
superset/   Superset 6.1.0 위에 PostgreSQL 드라이버와 고정 설정을 얹는 Dockerfile
scripts/    start/stop/restart/logs/health-check/validate-env .bat, CI용 ci-validate-env.sh(와 그 네거티브 시험 test-ci-validate-env.sh)
skills/     제품 기능 사용설명서 (local-environment부터)
docs/       요구사항 브리프, 운영 가이드, 결정 기록, Gate 진행 상태
references/ 선택된 Reference 소스
```
AI 도구와 기여 규칙은 `AGENTS.md`를 보세요.

## 알아 둘 점
- Superset 컨테이너는 gunicorn 워커 1개를 주기적으로 재시작하지 않습니다(재시작 순간 502가 나기 때문). 메모리 누수 보호는 `mem_limit`과 `restart: unless-stopped`에 맡기므로, 한도에 닿으면 컨테이너가 재시작되며 그동안 요청이 실패할 수 있습니다.
- frontend 컨테이너의 nginx 마스터 프로세스는 root로 실행됩니다. 공식 nginx 이미지의 기본 동작이며 의도적인 선택입니다(필요하면 `nginx-unprivileged` 이미지로 전환할 수 있습니다).
