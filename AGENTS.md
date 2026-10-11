# AGENTS.md — 환경·Skill·변경 규칙

사람과 모든 AI 도구가 같은 규칙을 읽는다. 요구사항 기준은 `docs/project-brief.md`, 운영 가이드는 `docs/AI_AGENT_DEVELOPMENT_GUIDE_요약.md`(브리프와 충돌하면 운영 가이드가 우선하고 충돌 사실을 사용자에게 알린다)다. 브리프 5절의 미결정 사항은 임의로 정하지 말고 사용자에게 묻는다. 현재 상태는 `docs/gate-status.md`다.

## 1. 환경 (Gate ② 결과)
- **실행 진입점은 루트 `compose.yml` 하나다.** 시작 `docker compose up -d --build`, 종료 `docker compose down`. 같은 동작의 Windows BAT는 `scripts/`에 있다. 사용법과 문제 해결은 `skills/local-environment/SKILL.md`를 읽고 추측하지 않는다.
- 서비스: `postgres`, `db-bootstrap`(일회성), `migrate`(일회성), `backend`, `frontend`, `superset-init`(일회성), `superset`, 그리고 profile `test`의 `postgres-test`(tmpfs). 순서는 `postgres → db-bootstrap → migrate → backend`, `db-bootstrap → superset-init → superset`.
- 모든 서비스에 `mem_limit`이 있다(합계 8GB 안, `docs/decisions/03a-deploy-environment.md`). 한도는 `compose.yml`에 고정하고 변수화하지 않는다. Redis/Valkey/Celery는 두지 않는다(필요해지면 사용자와 재논의).
- Health: `${APP_BASE_PATH}/api/health`, `${APP_BASE_PATH}/api/health/db`, `${SUPERSET_APP_ROOT}/health`. `/health/azure-openai`는 만들지 않는다.
- **Gate ② 한정 구성:** `POSTGRES_USER`(이미지 슈퍼유저)를 앱·`migrate` 계정으로 쓴다. 최소 권한 앱 계정 분리는 Gate ③에서 D2와 함께 설계하고 **Gate ④ 진입 전에 완료해야 한다.** Gate ④에서 backend가 슈퍼유저로 접속하면 리뷰에서 차단된다.
- 이 환경이 통과한 상태(Environment Ready)가 기능 개발의 전제다.
- frontend의 nginx 마스터가 root로 실행되는 것은 **의도적 선택**(공식 nginx 이미지 기본)이다. 필요하면 `nginx-unprivileged` 이미지로 전환할 수 있다.
- `FRONTEND_HOST` 기본값은 `127.0.0.1`이다(Superset 관리자 로그인이 LAN에 노출되지 않게). 컨테이너 내부 바인딩 변수(`BACKEND_HOST` 등)와는 다른 의미다.
- Superset 텔레메트리 끄기(`SCARF_ANALYTICS=false`)는 `compose.yml`의 고정값이다. gunicorn은 워커 1개이며 주기적 재시작(`WORKER_MAX_REQUESTS`)을 쓰지 않는다.

## 2. 환경변수
- `.env.example`이 이름 기준 원본이다. 운영 가이드의 canonical name(`APP_*`, `FRONTEND_*`, `BACKEND_*`, `POSTGRES_*`, `LOG_LEVEL`, `TZ`)을 그대로 쓰고, 같은 의미의 새 이름을 만들지 않는다. 환경별 이름 분리(`LOCAL_DB_HOST` 등) 금지: 이름은 고정하고 값만 바꾼다.
- Azure OpenAI 변수(`AZURE_OPENAI_*`)는 없다(브리프 5절 1번: 제외). LLM 사용이 생기면 사용자 승인 후에만 추가한다.
- 이 프로젝트의 추가 변수: `APP_BASE_PATH`, `APP_PROXY_STRIP_PREFIX`, `SUPERSET_APP_ROOT`, `POSTGRES_READONLY_PASSWORD`, `SUPERSET_DB_PASSWORD`, `SUPERSET_SECRET_KEY`, `GUEST_TOKEN_JWT_SECRET`, `SUPERSET_ADMIN_USER`, `SUPERSET_ADMIN_PASSWORD`. 읽기 전용 역할 `bi_readonly`, Superset 메타 역할 `superset_meta`, 메타 DB `superset`의 **이름은 코드 상수**이며 변수로 만들지 않는다.
- **새 변수를 추가할 때** 이 순서로 영향을 확인하고 변경 요약(커밋 메시지)에 기록한다.
  1. `.env.example` (이름, 주석, Secret이면 빈 값)
  2. backend Settings (`backend/app/config.py`) 와 테스트
  3. `compose.yml` — 필요한 서비스의 `environment:`에만 넣는다
  4. `scripts/ci-validate-env.sh`의 `REQUIRED`(Secret이면 `SECRETS`도)와 `Jenkinsfile`(Credential 매핑이 필요한지)
  5. `scripts/validate-env.bat`, `README.md`, `skills/local-environment/SKILL.md`
  6. 테스트
- **Secret**(DB 비밀번호, Superset 키, 관리자 비밀번호)은 Repository, Dockerfile, 이미지, Frontend 번들, 로그에 넣지 않는다. `.env`는 Git 제외다. **Frontend 컨테이너에는 전체 `.env`를 넘기지 않는다**(공개 설정만 `environment:`에 명시). 컨테이너마다 필요한 변수만 전달한다.

## 3. 하위 경로 배포와 프록시
- 포털은 메인 플랫폼의 URL 하위 경로로 서비스된다. 프런트 API 호출은 `${basePath}/api/…`(호스트 없는 상대경로)이고 `/api`, `/superset`, `/bi-wizard`를 코드에 하드코딩하지 않는다(`/api` 구간은 `frontend/src/config.ts` 한 곳).
- 경로 값 규칙: 앞 `/` 필수, 뒤 `/`·`//`·`.`/`..` 세그먼트·개행 금지. **빈 값(루트 배포)은 `APP_BASE_PATH`에만 허용**하고 `SUPERSET_APP_ROOT`는 비울 수 없다. 검증은 `backend/app/config.py`, `frontend/src/config.ts`, nginx 시작 스크립트, `scripts/ci-validate-env.sh`가 같은 규칙으로 한다.
- `APP_PROXY_STRIP_PREFIX`(기본 `false`)로 포털의 접두 처리(유지/제거)를 **설정값만으로** 전환한다. 코드를 바꾸거나 이미지를 다시 빌드하지 않는다.
- **Superset 경로는 접두를 떼지 않고 그대로 전달한다**(Superset 6.1.0 요구). 이미지 태그 `6.1.0`을 바꾸지 않는다. 하위 경로 지원은 공식 문서상 BETA이므로 문제가 보이면 **Superset 내부 코드를 수정하지 말고** 대안과 영향을 정리해 보고한다.
- 로컬 검증 값은 `/bi-wizard`, `/bi-wizard/superset`이다. 실제 값은 웹서버 배포 때 관리자와 정하며, 배포 때 맞출 항목은 `docs/deploy-coordination.md`에 모은다.

## 4. 마이그레이션과 DB 계정 (`docs/decisions/03-migration-tool.md`)
- 도구는 **Alembic**, 위치는 `backend/migrations/`. 실행은 일회성 `migrate` 서비스(`alembic upgrade head`)뿐이며 앱 코드는 시작 때 마이그레이션이나 `create_all`을 하지 않는다.
- 마이그레이션 안의 SQL은 **보간 없는 고정 문자열만** 쓴다(f-string, `%`, `.format()`, `+` 금지). 모든 revision에 `downgrade()`를 구현하고 빈 DB 왕복 테스트(`upgrade → downgrade → upgrade`)로 검증한다. 운영 중 문제는 되돌리기가 아니라 수정 마이그레이션 추가로 대응한다.
- **`DROP`이 있는 자동 생성 초안은 적용하지 않고 사용자 확인을 받는다**(D2 미결정, Gate ③). 확인했다면 변경 요약에 "DROP 확인: 사용자 승인"을 남긴다.
- 읽기 전용 계정과 Superset 메타 DB는 `db-bootstrap`(`backend/bootstrap/`)이 만든다. `initdb.d`를 쓰지 않는다. `roles.sql`의 psql `:'var'` 인용은 비밀번호 리터럴 두 곳에만 허용하고 식별자 보간은 금지다. `backend/migrations/`와 `backend/bootstrap/`(승인된 예외) 밖의 raw SQL은 금지이고, SQL 문자열 조립은 어디서도 금지다(SQLAlchemy 표현식 사용). `roles.sql`의 정적 규칙은 `scripts/ci-validate-env.sh`가 검사한다.
- `bi_readonly`의 `SELECT` 권한은 Gate ③에서 마이그레이션으로 부여한다.

## 5. 라이선스
- 허용형만 쓴다: MIT, BSD, Apache 2.0, PSF, PostgreSQL License. `ag-grid-enterprise`, AGPL, GPL, EUPL, Sustainable Use License, Redis 7.4 이후 라이선스는 금지다. 불분명하면 쓰지 말고 질문한다.
- 의존성을 추가하면 PyPI/npm 메타데이터로 라이선스를 확인해 변경 요약에 쓴다. 의존성은 버전을 고정한다(`backend/requirements*.txt`, `frontend/package-lock.json`). 이미지 태그에 `latest`를 쓰지 않는다.
- LGPL인 `psycopg2`/`psycopg`는 backend에 쓰지 않는다(backend는 pg8000, BSD-3). Superset 이미지(`superset/Dockerfile`)에만 `psycopg2-binary`를 둔다.

## 6. Skill 규칙
- 사용자 관점의 주요 기능마다 `skills/<기능>/SKILL.md`를 둔다(형식: `.claude/skills/product-skill-authoring`). 현재는 `skills/local-environment/`뿐이다.
- **Feature Code ↔ Skill ↔ 연관 Skill ↔ 회귀 테스트는 함께 바뀐다.** 코드나 환경만 바꾸고 Skill을 갱신하지 않으면 완료로 보지 않는다. 환경을 바꾸면 `skills/local-environment/SKILL.md`, `README.md`를 같은 작업에서 고친다.
- `.claude/`(개발 에이전트 정의)와 `skills/`(제품 사용설명서)는 다른 것이다.

## 7. 검증 명령
```
docker compose config --quiet                       # 구성 (CI는 sh scripts/ci-validate-env.sh 로 만든 더미 env 사용)
docker build --target test backend                  # ruff check/format, pytest
docker build --target test frontend                 # eslint, tsc, vitest
docker compose up -d --build && docker compose ps   # 기동 (Windows: scripts\start-local.bat, scripts\health-check.bat)
```
CI는 `Jenkinsfile`이다: Checkout → Env Validation → Backend Lint/Test → Frontend Lint/Test/Build → `docker compose config` → Docker Build. 앞 단계가 실패하면 뒤 단계는 실행하지 않는다.

## 8. 하지 않는 일
- `.env` 삭제, `rm -rf`, `git clean -fdx`, `git reset --hard`, `docker compose down -v`(볼륨 삭제)를 실행하거나 스크립트·문서에 쓰지 않는다. 필요하면 먼저 사용자에게 묻는다.
- `main`에 직접 커밋하거나 푸시하지 않는다.
- Dockerfile에서 `apt-get`을 쓰지 않는다. 특정 PC·세션에서만 필요한 빌드 우회(CA 인증서 등)는 저장소에 넣지 않는다.
- `scripts/*.bat`는 ASCII(영문)만 쓰고 CRLF, BOM 없음으로 유지한다. AI 세션(Linux)에서는 BAT를 실행하지 않는다. BAT 실행 검증은 사용자 Windows PC에서 한다.
- Superset 내부 코드를 수정하지 않는다(설정과 공식 CLI만 쓴다).
