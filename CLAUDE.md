# BI-Wizard — Claude Code 진입점

## 먼저 읽을 문서
1. `docs/project-brief.md` — 요구사항 기준 문서. "미결정 사항"은 임의로 정하지 않고 사용자에게 묻는다.
2. `docs/AI_AGENT_DEVELOPMENT_GUIDE_요약.md` — 팀 웹서버 운영 가이드. 브리프와 충돌하면 이 문서를 우선하고, 충돌 사실을 사용자에게 알린다.
3. `docs/claude-code-cloud-harness.md` — 클라우드 세션 작업 환경
4. `AGENTS.md` — 환경·Skill·변경 규칙. Gate ②에서 생성되며, 생성 전에는 없다.

## 하네스: BI-Wizard 개발

**목표:** Gate 순서(RESEARCH & DECIDE → ENVIRONMENT BOOTSTRAP → MODULARIZE → 기능 개발)대로 개발하고, 각 Gate는 사용자 승인 후에만 다음으로 넘어간다.

**호출 조건:** 조사, 환경 구축, 설계, 기능 구현, 검증, 리뷰 등 개발 작업을 요청받으면 `bi-wizard-dev` 스킬을 사용한다. 단순 질문에는 직접 답해도 된다.

**핵심 규칙**
- 미결정 사항(브리프 5절)은 사용자에게 묻고, 답을 받은 뒤 진행한다.
- 파괴적 명령(`.env` 삭제, `rm -rf`, `git clean -fdx`, `git reset --hard`, `docker compose down -v`)은 실행하지 않는다. 필요하면 먼저 묻는다.
- `main`에 직접 커밋하거나 푸시하지 않는다.
- 클라우드 세션은 Linux이므로 BAT 파일은 작성만 하고 실행 검증은 사용자에게 요청한다.

**변경 이력**
| 날짜 | 변경 내용 | 대상 | 사유 |
| --- | --- | --- | --- |
| 2026-10-11 | Harness v2로 최초 구성 | 전체 | 개발 에이전트 팀 구축 |
| 2026-10-11 | Azure OpenAI 처리 방침 변경: 변수 유지·N/A 금지 → 제외(변수·`/health/azure-openai` 미생성, 체크리스트 "해당 없음"). bi-review는 미결정/결정 항목 검사 문구 갱신 | `.claude/agents/env-engineer.md`, `backend-dev.md`, `.claude/skills/env-bootstrap`, `bi-wizard-dev`, `bi-review` | 브리프 5절 1번 "제외" 결정(사용자, 2026-10-11) 반영 |
| 2026-10-11 | 마이그레이션 결정(D1~D7, `docs/decisions/03-migration-tool.md`) 반영: Alembic, 일회성 `migrate` 서비스, tmpfs 테스트 DB(profile), Superset 별도 DB·읽기 전용 계정, 마이그레이션 안 고정 SQL만 허용(보간 금지), `downgrade` 필수와 왕복 테스트, `DROP` 사용자 확인(D2 연기). bi-review에 마이그레이션 점검 항목(7-1) 추가 | `.claude/agents/env-engineer.md`, `qa-engineer.md`, `architect.md`, `backend-dev.md`, `.claude/skills/env-bootstrap`, `qa-verification`, `backend-fastapi`, `bi-review`, `feature-unit`, `modularize`, `bi-wizard-dev` | 마이그레이션 도구·실행 방식 사용자 결정(2026-10-11) 반영 |
| 2026-10-11 | 미결정 4번 결정 반영(`docs/decisions/03a-deploy-environment.md`): Superset은 compose 정식 서비스(6.1.0 고정), Redis/Valkey 제외, 메인 플랫폼 URL 하위 경로(`APP_BASE_PATH`, `SUPERSET_APP_ROOT`), 메모리 8GB. "운영자 확인 중/로컬 compose 한정" 문구 삭제, 하위 경로 + Embedded 검증·메모리 실측·`mem_limit` 점검 추가, 프런트 API 경로를 `${APP_BASE_PATH}/api`로 변경, 배포 협의 목록(`docs/deploy-coordination.md`) 도입 | `.claude/agents/env-engineer.md`, `architect.md`, `qa-engineer.md`, `frontend-dev.md`, `reviewer.md`, `.claude/skills/env-bootstrap`, `bi-wizard-dev`, `bi-review`, `qa-verification`, `backend-fastapi`, `frontend-react-aggrid` | 브리프 5절 4번 "결정됨"과 사전 제안 6개 승인(사용자, 2026-10-11) 반영 |
| 2026-10-11 | 읽기 전용 계정·접두 전환·앱 계정 조건 승인 반영(`docs/decisions/03-migration-tool.md`, `03a`): 매 기동 멱등 `db-bootstrap`(`backend/bootstrap/`, `initdb.d` 미사용)과 순서, 역할·DB 이름 상수(`bi_readonly`, `superset_meta`, `superset`)·비밀번호 변수 2개, **D3 예외 2: `backend/bootstrap/`에서 비밀번호 리터럴 두 곳의 psql `:'var'`만 허용(식별자 보간 금지)**, `APP_PROXY_STRIP_PREFIX`(기본 `false`, `true`/`false` 모두 검증), Gate ④ 진입 전 최소 권한 앱 계정 분리 필수와 슈퍼유저 접속 시 bi-review 차단, QA 임시 env 파일 규칙, 패키지는 허용형 라이선스만(LGPL 드라이버 금지) | `.claude/skills/bi-review`, `env-bootstrap`, `qa-verification`, `backend-fastapi`, `modularize`, `bi-wizard-dev`, `.claude/agents/env-engineer.md`, `qa-engineer.md`, `architect.md` | 사용자 승인(2026-10-11) 반영 |
