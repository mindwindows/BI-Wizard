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
- 서비스: `postgres`, `backend`, `frontend`, 그리고 확인 후 추가되는 Superset 관련 서비스
- Health: `/health`, `/health/db`를 업무 API보다 먼저 만든다. `/health/azure-openai`는 브리프 5절 1번 결과에 따른다.
- Frontend 컨테이너에는 전체 `.env`를 넘기지 않는다. API는 상대경로 `/api`와 프록시로 연결한다.
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

## 미결정 사항 반영 방식
- **Azure OpenAI (브리프 5절 1번):** 변수 이름은 유지하고 "미결정 1번" 주석을 단다. 답이 나오기 전에는 Health 경로에서 설정 로딩과 Connectivity Test를 구분해 두기만 한다.
- **Superset과 캐시 서비스 (브리프 5절 4번):** 로컬 `compose.yml`에만 넣는다. 팀 웹서버 구성은 운영자 확인 전까지 확정하지 않는다. Redis 대체로 Valkey를 쓸 수 있으나 라이선스 확인은 사용자 승인 후에 한다.

## Environment Ready 체크리스트
모두 통과해야 Gate ③으로 넘어간다.

- [ ] `.env.example`: canonical 변수 목록과 주석이 있고, 중복 의미의 변수가 없다.
- [ ] `.env`: `.gitignore`에 있다. Repository, Frontend, 이미지에 Secret이 없다.
- [ ] Backend, Frontend Dockerfile이 각각 빌드된다.
- [ ] `compose.yml`: postgres, backend, frontend가 정의되어 있고, DB healthcheck와 volume이 있다.
- [ ] Compose 시작과 종료가 실제로 성공한다. (Docker 데몬이 필요하다. 불가하면 `qa-verification` 절차를 따른다.)
- [ ] Frontend에서 FastAPI로 최소 통신이 된다.
- [ ] Backend에서 PostgreSQL 연결 상태를 실제로 확인한다.
- [ ] Azure OpenAI 검증 경로: 설정 로딩과 Connectivity Test가 구분되어 있다. (미결정 1번 반영 전에는 "보류"로 표시)
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
- Azure OpenAI 항목을 임의로 N/A 처리하지 않는다.

## 관련 Skill
- `local-environment` (저장소의 `skills/local-environment/SKILL.md`): 사용자와 AI가 쓰는 실행 절차
- `qa-verification`: 기동과 Health 검증 절차
- `product-skill-authoring`: 제품 Skill 작성 형식
