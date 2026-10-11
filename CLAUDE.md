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
