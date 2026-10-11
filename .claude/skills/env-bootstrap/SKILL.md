---
name: env-bootstrap
description: Gate ② ENVIRONMENT BOOTSTRAP에서 실행 환경(compose.yml, Dockerfile, .env.example, health 경로, BAT 6종, Jenkinsfile)을 만들고 Environment Ready 체크리스트로 점검하는 절차. env-engineer가 사용한다. 환경변수 추가나 서비스 구성 변경 시에도 사용한다.
---

# env-bootstrap — 실행 환경 구축 절차

## 목적
새 PC에서 저장소를 받은 사람이 Secret 값만 설정하면 같은 명령으로 Frontend, FastAPI, PostgreSQL을 실행하고 상태를 확인할 수 있게 한다. 이 단계를 통과하기 전에는 업무 기능을 만들지 않는다.

## 실행 계약 (운영 가이드 2절, 브리프 3.4절)
- 시작: `docker compose up -d --build`
- 종료: `docker compose down` (볼륨 삭제 옵션 금지)
- 서비스: `postgres`, `migrate`(일회성), `backend`, `frontend`, 그리고 확인 후 추가되는 Superset 관련 서비스. 테스트 전용 PostgreSQL 서비스는 compose profile `test`에만 있다.
- Health: `/health`, `/health/db`를 업무 API보다 먼저 만든다. `/health/azure-openai`는 만들지 않는다(브리프 5절 1번 결정: 제외).
- Frontend 컨테이너에는 전체 `.env`를 넘기지 않는다. API는 호스트 없는 상대경로 `${APP_BASE_PATH}/api`와 프록시로 연결한다(하위 경로 배포, 아래 "하위 경로 배포와 메모리").
- BAT 6종: `start-local.bat`, `stop-local.bat`, `restart-local.bat`, `logs-local.bat`, `health-check.bat`, `validate-env.bat`. Linux 세션에서는 작성만 한다.

## 환경변수 규칙
- `.env.example`이 변수명 기준 원본이다. 운영 가이드의 canonical name을 쓴다. 예: `APP_NAME`, `FRONTEND_PORT`, `BACKEND_PORT`, `POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `LOG_LEVEL`, `TZ`
- 같은 의미의 새 이름을 만들지 않는다. 예: `OPENAI_URL`, `AOAI_ENDPOINT`는 금지.
- 환경별 이름 분리를 하지 않는다. 예: `LOCAL_DB_HOST`는 금지.
- Secret은 Repository, Dockerfile, 이미지, Frontend 번들에 넣지 않는다.

### 새 변수 추가 순서
1. 기존 변수와 의미가 겹치는지 확인한다.
2. `.env.example` → Backend Settings → `compose.yml` → `Jenkinsfile` → README와 Skill → Test 순서로 영향을 확인한다.
3. 결과를 PR 설명이 아니라 커밋 메시지나 변경 요약에 기록한다.

## 미결정·결정 사항 반영 방식
- **Azure OpenAI (브리프 5절 1번, 결정됨: 제외):** `.env.example`에서 `AZURE_OPENAI_*` 변수를 뺀다. `/health/azure-openai`는 만들지 않는다. Environment Ready 체크리스트의 해당 항목은 "해당 없음"으로 표시한다. 이후 LLM 사용이 생기면 사용자 승인 후에 다시 논의한다.
- **Superset (브리프 5절 4번, 결정됨):** `compose.yml`의 **정식 서비스**다. 이미지는 `6.1.0`으로 고정한다. **Redis/Valkey는 두지 않는다**(Superset 기본 캐시가 메타데이터 DB). 필요해 보이면 추가하지 말고 메인에게 알린다. 실제 하위 경로 값과 프록시 접두 처리 같은 배포 협의 항목은 `docs/deploy-coordination.md`에 추가한다.

## 하위 경로 배포와 메모리 (`docs/decisions/03a-deploy-environment.md`)
- **변수:** `APP_BASE_PATH`(포털 하위 경로)와 `SUPERSET_APP_ROOT`(Superset 하위 경로, Superset 공식 변수명 그대로)만 쓴다. 형식은 루트 배포는 빈 값, 아니면 앞 `/` 필수·뒤 `/` 금지다. 두 값은 독립 값이며 한쪽에서 다른 쪽을 파생하지 않는다. 같은 의미의 다른 이름을 만들지 않는다. `.env.example`에는 예시 값 `/bi-wizard`, `/bi-wizard/superset`과 "운영자 확인 필요" 주석을 둔다. 프런트 컨테이너에는 `APP_BASE_PATH`만 공개 설정으로 넘긴다.
- **프록시 접두 처리:** 포털(frontend·backend)은 접두를 떼고 넘기는 방식과 그대로 넘기는 방식을 **설정값만으로** 전환할 수 있게 구성한다. Superset은 접두를 **떼지 않고 그대로** 넘긴다(6.1.0은 접두로 시작하지 않는 요청에 404).
- **로컬 재현:** 로컬 검증은 경로 값을 `/bi-wizard`, `/bi-wizard/superset`으로 둔다(빈 값 아님). frontend nginx가 메인 플랫폼 프록시 역할을 재현하고, 사용자 브라우저가 Superset 경로에 직접 접근할 수 있어야 한다.
- **API 경로:** 프런트는 `${APP_BASE_PATH}/api`로 호출한다(호스트 없는 상대경로). `/api`나 `/superset`을 코드에 하드코딩하지 않는다.
- **Superset:** 이미지 `6.1.0` 고정, 하위 경로는 공식 문서상 BETA다. `GUEST_TOKEN_JWT_SECRET`, `SECRET_KEY`는 `.env` Secret으로 덮어쓴다(기본값은 자리표시 값). 설정은 환경변수에서 읽는 고정 `superset_config.py`로 전달한다. **하위 경로 버그가 재현되면 Superset 내부 코드를 수정하지 말고**, 대안과 각 영향을 정리해 메인에게 보고하고 멈춘다.
- **메모리:** `compose.yml`에 `mem_limit`을 고정한다(postgres 1.5GB, superset 2.0GB, backend 1.0GB, frontend 256MB, migrate 512MB, superset-init 1.0GB, postgres-test 512MB). 합계는 8GB 안이다. Redis/Valkey와 Celery는 두지 않는다. 숫자는 추정이므로 기동 후 `docker stats`로 실측해 보고한다.

## 마이그레이션 구성 (`docs/decisions/03-migration-tool.md`)
- **도구:** Alembic(D1). backend 이미지에 패키지를 추가하고 마이그레이션 디렉터리(제안: `backend/migrations/`)와 설정 골격을 둔다. 업무 테이블 revision은 만들지 않는다. 왕복 테스트를 돌릴 수 있도록 업무 테이블이 없는 기준(baseline) revision 하나(`upgrade`와 `downgrade` 모두 동작)만 둔다.
- **`migrate` 서비스(D4):** backend 이미지를 재사용해 `alembic upgrade head`를 실행하고 종료한다(`restart` 없음). `postgres`의 `service_healthy` 이후에 시작한다. `backend`는 `migrate`의 `service_completed_successfully`와 `postgres`의 `service_healthy`에 의존한다. 앱 코드가 시작 시 마이그레이션을 실행하지 않는다.
- **테스트 DB(D6):** `profiles: ["test"]`인 테스트 전용 PostgreSQL 서비스를 정의한다. 데이터는 `tmpfs`에 두고 크기를 제한한다. 정리는 `docker compose --profile test down`이며 `-v`는 쓰지 않는다. Jenkins 적용은 Jenkins 실행 환경 확인 후 별도 결정이므로 Jenkinsfile 초기 Stage에는 넣지 않는다.
- **Superset(D7):** 메타데이터는 같은 PostgreSQL 컨테이너 안의 **별도 데이터베이스**다. 업무 데이터 연결은 **읽기 전용 계정**을 쓴다. 계정 생성은 환경변수를 SQL에 보간하지 않는 방식으로 한다(PostgreSQL 초기화 스크립트 쪽 등, 방식은 사전 제안으로 사용자 승인을 받는다). 마이그레이션 안의 SQL은 고정 문자열만 허용한다(D3).
- 동적 객체(사용자 데이터셋 테이블, 수식 뷰)의 분리 방식(D2)은 Gate ③에서 정한다. 그 전에는 `DROP`이 포함된 자동 생성 초안을 적용하지 않는다.

## Environment Ready 체크리스트
모두 통과해야 Gate ③으로 넘어간다.

- [ ] `.env.example`: canonical 변수 목록과 주석이 있고, 중복 의미의 변수가 없다.
- [ ] `.env`: `.gitignore`에 있다. Repository, Frontend, 이미지에 Secret이 없다.
- [ ] Backend, Frontend Dockerfile이 각각 빌드된다.
- [ ] `compose.yml`: postgres, backend, frontend가 정의되어 있고, DB healthcheck와 volume이 있다.
- [ ] Compose 시작과 종료가 실제로 성공한다. (Docker 데몬이 필요하다. 불가하면 `qa-verification` 절차를 따른다.)
- [ ] `migrate` 서비스가 성공 완료된 뒤에만 `backend`가 시작된다(`depends_on` 조건). `migrate`를 실패시켰을 때 `backend`가 시작되지 않는지도 확인한다.
- [ ] 마이그레이션 왕복 테스트: tmpfs 테스트 DB(profile `test`)에서 upgrade → downgrade → upgrade가 성공한다. 정리는 `-v` 없는 `docker compose down`이다.
- [ ] Superset 메타데이터 DB가 별도 데이터베이스이고, Superset의 업무 데이터 연결이 읽기 전용 계정이다. (Superset은 `compose.yml`의 정식 서비스, 이미지 `6.1.0`.)
- [ ] **하위 경로 + Embedded 동작:** 경로 값을 `/bi-wizard`, `/bi-wizard/superset`으로 두고 frontend nginx 프록시를 거쳐 다음을 확인한다. 포털 페이지와 정적 파일이 `${APP_BASE_PATH}/` 아래에서 열린다. `${APP_BASE_PATH}/api/health`가 응답한다. Superset 로그인 화면과 정적 파일이 `${SUPERSET_APP_ROOT}/` 아래에서 열린다(중복 접두 `/…/superset/superset/…`가 없다). Embedded 대시보드(`/embedded/<id>`)가 iframe으로 열린다. 포털의 접두 처리 설정값을 전환해도 동작한다. 재현되는 버그가 있으면 Superset 내부 코드를 수정하지 않고 대안과 영향을 보고한다.
- [ ] 메모리: 모든 서비스에 `mem_limit`이 있고 합계가 8GB 안이다. `docker stats` 실측값과 5MB급 엑셀 샘플의 backend 사용량을 보고했다.
- [ ] Frontend에서 FastAPI로 최소 통신이 된다.
- [ ] Backend에서 PostgreSQL 연결 상태를 실제로 확인한다.
- [ ] Azure OpenAI 검증 경로: **해당 없음** (브리프 5절 1번 결정: 제외. 변수와 Health 경로를 만들지 않았는지만 확인한다.)
- [ ] BAT 6종이 있다. 실행 검증은 사용자 PC에서 한다.
- [ ] Jenkinsfile: Validation, Test, Build, Compose, Docker Build 단계가 있다.
- [ ] `skills/local-environment/SKILL.md`: 실행, 종료, 로그, Health Check, 문제 해결이 있다.
- [ ] `README.md`와 `AGENTS.md`: 신규 개발자와 AI가 같은 규칙을 읽는다.

체크리스트 결과는 항목별로 통과, 실패, 미실행, 보류로 표시하고 근거를 함께 쓴다.

## Jenkinsfile 초기 Stage
Checkout → Env Validation → Backend Lint/Test → Frontend Lint/Test/Build → `docker compose config` → Docker Build. 앞 단계가 실패하면 뒤 단계는 실행하지 않는다.

## 금지 사항
- `docker compose down -v`, `.env` 삭제, `rm -rf`를 쓰지 않는다.
- BAT 파일을 Linux에서 실행하지 않는다.
- 사용자 승인 없이 Azure OpenAI 변수나 `/health/azure-openai`를 다시 추가하지 않는다(브리프 5절 1번: 제외로 결정됨).

## 관련 Skill
- `local-environment` (저장소의 `skills/local-environment/SKILL.md`): 사용자와 AI가 쓰는 실행 절차
- `qa-verification`: 기동과 Health 검증 절차
- `product-skill-authoring`: 제품 Skill 작성 형식
