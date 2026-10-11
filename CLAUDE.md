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
- **새 환경변수, 새 의존성, 운영 가이드 기준선과 다른 설정, 권한을 넓히는 변경, 에이전트 모델 변경은 적용 전에 사용자 승인을 받는다.** 권한을 줄이거나 비밀·로그 노출을 막는 보안 강화 변경만 적용 후 보고를 허용하며, 보고서에 "적용 후 보고 항목" 목록으로 따로 표시한다. (에이전트 정의 모델: 모든 에이전트가 sonnet이다. 2026-10-11 사용자 승인으로 env-engineer·qa-engineer·frontend-dev를 haiku에서 sonnet으로 바꿨다. 호출 시 모델 변경은 금지)
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
| 2026-10-11 | bi-review D5에 "업무 객체가 없는 baseline revision은 사유를 적은 의도적 no-op 허용, 첫 실제 객체 revision부터 실질 `downgrade()` 요구" 예외 추가 | `.claude/skills/bi-review` | Gate ② reviewer 의견(빈 baseline revision 판정) 반영 |
| 2026-10-11 | Gate ② 결과 결정 8건 반영: 사전 승인 규칙 신설(새 환경변수·운영 가이드 기준선과 다른 설정·에이전트 모델 변경은 적용 전 사용자 승인), 라이선스 원칙 재정의(운영 런타임 의존성은 허용형만, 개발·테스트 전용과 업스트림 이미지 내부의 LGPL·MPL은 수정·재배포하지 않으면 허용, 강한 카피레프트·비오픈소스는 금지), Embedded guest 역할 결정(최소 권한 커스텀 역할, `Gamma`/`PUBLIC_ROLE_LIKE` 운영 사용 금지), Scarf CSP 제거와 `SCARF_ANALYTICS` 삭제. bi-review에 7-2(guest 역할·Scarf) 추가 | `CLAUDE.md`, `.claude/skills/bi-wizard-dev`, `bi-review`, `gate-research`, `backend-fastapi`, `.claude/agents/env-engineer.md`, `backend-dev.md`, `frontend-dev.md`, `reviewer.md` | Gate ② 결과에 대한 사용자 결정(2026-10-11) 반영 |
| 2026-10-11 | Gate ③ 계획 승인 반영: researcher를 "사용자 요청 시 어느 Gate에서든 공식 문서 사실 확인"으로 확장(사실 확인 규칙·`_workspace/gate3/facts.md`), reviewer에 사실 확인 교차 검증·문서 간 일관성 점검 추가, Gate ③ 산출물을 `docs/decisions/04~08` 5개로 확장하고 결정 라운드(0~5) 명시, 미결정 8~11번(인증, 동시 편집, Superset 등록 방식, 삭제 정책) 추가 | `.claude/agents/researcher.md`, `reviewer.md`, `architect.md`, `.claude/skills/modularize`, `bi-wizard-dev`, `bi-review` | Gate ③ 진행 계획 사용자 승인(2026-10-11) 반영 |
| 2026-10-11 | Gate ③ 3라운드 결정 반영(`docs/decisions/03b` 3절): 앱 계정 분리(`bi_owner`/`bi_app`, `POSTGRES_USER` 의미 축소는 운영 가이드와의 의도적 차이), D3 예외 2 문구를 비밀번호 리터럴 범위로 일반화(식별자 보간 금지 유지), D5·B10 의미 변경, 새 변수 `POSTGRES_APP_PASSWORD`·`POSTGRES_OWNER_PASSWORD`·`SUPERSET_SERVICE_USER`·`SUPERSET_SERVICE_PASSWORD`와 `httpx` 승인, Gamma 금지는 guest 역할에만 적용(작성자 역할은 Gamma 복사본), 미결정 7·9·10·11번 결정 | `.claude/skills/bi-review`, `env-bootstrap`, `backend-fastapi`, `AGENTS.md`, `docs/` | 3라운드 사용자 결정(2026-10-11) 반영 |
| 2026-10-11 | Gate ③ 4라운드 결정 반영(`docs/decisions/03b` 4절): guest 역할 `bi_guest`와 `superset-init` 생성·`GUEST_TOKEN_VALIDATOR_HOOK`·발급 전용 Superset 계정 변수 2개·`APP_UPLOAD_MAX_MB` 승인, db-bootstrap `GRANT bi_app TO bi_owner WITH INHERIT TRUE, SET FALSE` 한 줄 승인, 브리프 4.7 이탈(pandas 미사용), `bi-review` 7-4 런타임 동적 DDL 규칙(내장 구성요소만·`text()` 금지·객체 종류 허용 목록) 추가, 기존 엑셀 이관 전처리 도구 범위 제외, 합성 샘플 `docs/samples/` | `.claude/skills/bi-review`, `backend-fastapi`, `env-bootstrap`, `docs/` | 4라운드 사용자 결정(2026-10-11) 반영 |
| 2026-10-11 | Gate ③을 첫 기능 단위(FU-1) 범위로 축소(`docs/decisions/03b` 5절): 04~08은 FU-1 필요 범위만 약 800줄 이내, 후속 항목은 문서 끝 절에 나열, 인증 스텁 시작 거부 차단 규칙 `bi-review` 7-5 추가, 브리프 4.3 역할별 열 편집 권한 기능 축소 기록, EW는 FU-1 필요 항목만 | `.claude/skills/bi-review`, `docs/` | FU-1 범위 축소 사용자 결정(2026-10-11) 반영 |
| 2026-10-11 | 에이전트 모델 변경(사전 승인 AP-17): `env-engineer`·`qa-engineer`·`frontend-dev` 정의 파일 `haiku` → `sonnet`. 사유: Gate ②에서 권한·compose 의존 순서·하위 경로 프록시처럼 복잡한 환경 작업이 haiku로는 부족해 호출 때 sonnet으로 올려 썼던 점, 권한 설정(계정 분리, 권한 매트릭스)의 보안 영향, FU-1 화면 복잡도(입력 그리드, 붙여넣기 파서, 수식 편집기, 3분할 작업공간). 비용 영향은 호출 수에 비례하며 정량 근거는 없음 | `.claude/agents/env-engineer.md`, `qa-engineer.md`, `frontend-dev.md`, `CLAUDE.md` | Gate ③ 초안 검토 결정(2026-10-11) |
| 2026-10-11 | Gate ③ 승인(FU-1 범위): 04~08 "승인", AP-1·2·5·9·10·11·12·13·14·16 승인(`docs/decisions/03b` 6절). `bi-review` 7-1 D2를 "정적 표 대상"으로 좁힘, 7-2에 guest 권한 목록 파일 규칙·서버의 입장권 직접 서명 금지 추가, 7-4에 가상 데이터셋 SQL 고정 규칙과 소유 표에 연결된 `Identity()` 시퀀스 예외 추가, 7-5에 `AUTH_STUB_ENABLED` 기본 꺼짐 + `APP_ENV` 명시·허용 목록 규칙 반영 | `.claude/skills/bi-review`, `docs/` | Gate ③ 승인 및 AP 승인(2026-10-11) 반영 |
| 2026-10-11 | EW-1 구현 반영: 앱 계정 분리(`bi_owner`/`bi_app`) 완료로 "Gate ② 한정 구성"·"구현은 Gate ④ 진입 전" 문구를 구현 완료 상태로 갱신하고, `bi-review` 앱 계정 항목을 "backend·migrate 슈퍼유저 접속 차단"으로 확정 | `.claude/skills/bi-review`, `env-bootstrap`, `backend-fastapi`, `.claude/agents/env-engineer.md` | EW-1 reviewer 점검(낡은 문구 지적) 반영 |
| 2026-10-11 | 사전 승인 규칙 다듬기: 사전 승인 필수 = 새 환경변수·새 의존성·운영 가이드 기준선과 다른 설정·권한을 넓히는 변경·에이전트 모델 변경. 적용 후 보고 허용 = 권한을 줄이거나 비밀·로그 노출을 막는 보안 강화 변경(보고서에 "적용 후 보고 항목" 목록 필수). EW-1에서 목록 밖에 추가한 항목(`hide_input_in_errors`, `REVOKE` 2줄과 `bi_data` 소유자 지정, `log_min_error_statement` 설정, `AUTH_STUB_ENABLED` compose 필수 처리, `scripts/test-ci-validate-env.sh`)을 소급 승인 | `CLAUDE.md`, `.claude/skills/bi-wizard-dev`, `bi-review`, `.claude/agents/env-engineer.md`, `backend-dev.md`, `frontend-dev.md`, `reviewer.md` | 사용자 결정(2026-10-11, EW-1 결과 검토) |
