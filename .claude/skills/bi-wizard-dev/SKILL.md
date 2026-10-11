---
name: bi-wizard-dev
description: BI-Wizard 개발을 Gate 순서(RESEARCH & DECIDE → ENVIRONMENT BOOTSTRAP → MODULARIZE → 기능 개발)대로 진행하는 오케스트레이터. 조사, 환경 구축, 설계, 기능 구현, 검증, 리뷰 요청이나 "다시 실행", "재실행", "이어서", "다음 Gate", "기능 추가", "수정", "보완" 같은 후속 요청에 사용한다. 단순 질문에는 쓰지 않는다.
---

# bi-wizard-dev — Gate 기반 개발 오케스트레이터

## 목표
각 Gate의 산출물을 사용자가 확인하고 승인한 뒤에만 다음 Gate로 넘어간다. 승인되지 않은 선택은 문서나 코드에 확정하지 않는다.

## 0단계: 시작 전 점검
1. `docs/gate-status.md`를 읽는다. 없으면 아직 Gate ① 전이다.
2. 다음 문서를 읽는다: `docs/project-brief.md`, `docs/AI_AGENT_DEVELOPMENT_GUIDE_요약.md`, `docs/claude-code-cloud-harness.md`, `AGENTS.md`(있을 때).
3. 브리프와 운영 가이드가 충돌하면 운영 가이드를 따르고, 충돌 사실을 사용자에게 알린다.
4. 현재 Gate와 요청이 맞는지 확인한다. 승인되지 않은 Gate의 작업을 요청받으면 먼저 승인 상태를 알린다.

## Gate 공통 절차
1. 해당 Gate의 에이전트를 실행하고, 산출물은 `_workspace/`에 받는다.
2. 사용자에게 요약, 추천안, 열린 질문을 제시한다. 긴 내용은 파일 경로로 안내한다.
3. 사용자의 승인을 기다린다. 승인하지 않았으면 다음 단계로 넘어가지 않는다.
4. 승인된 결과는 아래 "산출물 위치 규칙"에 따라 `docs/`로 옮겨 커밋한다. 결정 사항은 `docs/gate-status.md`에 기록한다.
5. 다음 Gate로 넘어가기 전에 사용자에게 다음 단계를 한 줄로 알린다.

## Gate별 실행

| Gate | 실행 모드 | 에이전트 | 승인 전 산출물 | 승인 후 위치 |
| --- | --- | --- | --- | --- |
| ① RESEARCH & DECIDE | 서브에이전트 병렬 2건, 이후 리뷰 | researcher ×2 (디자인, 기술 Reference), reviewer | 디자인 2~3안, Reference 3~5개 비교표 | `docs/decisions/01-design-direction.md`, `docs/decisions/02-tech-reference.md` |
| ② ENVIRONMENT BOOTSTRAP | 지속형 협업 (생성·검증) | architect(마이그레이션 도구 제안), env-engineer ⇄ qa-engineer, reviewer | Environment Ready 체크리스트 결과, BAT 검증 요청서 | 저장소 파일(compose, Dockerfile, `.env.example`, `AGENTS.md` 등). `docs/decisions/03-migration-tool.md`, `docs/decisions/03a-deploy-environment.md`, `docs/deploy-coordination.md` |
| ③ MODULARIZE | 서브에이전트 생성 후 리뷰 | researcher(공식 문서 사실 확인), architect, reviewer | 사실 확인 결과(`_workspace/gate3/facts.md`), 모듈 경계, 기능↔Skill 대응표, API 계약 초안, 데이터 모델, 수식 엔진, Superset 임베딩, 기능 단위 순서 | `docs/decisions/04-modules.md`, `05-api-contract.md`, `06-data-model.md`, `07-formula-engine.md`, `08-superset-embedding.md` |
| ④ 기능 개발 | 지속형 협업 + 기능 단위마다 리뷰 | backend-dev, frontend-dev, qa-engineer (상시), reviewer (단위 완료 시) | 기능 단위별 코드·테스트·Skill | 저장소 파일(`backend/`, `frontend/`, `skills/<기능>/`). 완료 후 커밋 |

### Gate ①: RESEARCH & DECIDE
- `docs/gate-status.md`를 이 시점에 생성한다(형식은 아래 참조). 이 파일은 Gate ①을 시작할 때 처음 만든다.
- researcher 두 명을 병렬로 실행한다. 한 명은 디자인, 한 명은 Reference를 맡는다.
- 두 결과를 reviewer가 교차 검증한다. 특히 라이선스와 출처를 확인한다.
- 사용자에게 디자인 2~3안과 Reference 3~5개를 비교표로 보여준다. 추천안은 근거와 함께 제시하되 선택은 사용자가 한다.
- **브리프 5절 5번(디자인 방향)** 은 이 Gate에서 사용자가 고른다.
- 사용자가 디자인과 Reference를 고르면 `docs/decisions/`에 기록하고 Gate ②로 넘어간다.

### Gate ②: ENVIRONMENT BOOTSTRAP
- DB 마이그레이션은 **Alembic**으로 결정됐다(D1~D7, `docs/decisions/03-migration-tool.md`). env-engineer가 `migrate` 서비스, tmpfs 테스트 DB(profile), Superset 별도 DB와 읽기 전용 계정을 반영한다. D2는 Gate ③, D6의 Jenkins 적용은 Jenkins 실행 환경 확인 후 정한다.
- env-engineer는 **파일을 만들기 전에** 사전 제안(하위 경로 환경변수 이름, 메모리 배분, 하위 경로 구성 확인 결과 등)을 메인에게 올리고, 메인이 사용자 승인을 받은 뒤에 만든다.
- env-engineer가 환경을 만들고, qa-engineer가 `qa-verification` 스킬에 따라 검증한다. 둘은 SendMessage로 문제를 주고받는다.
- Environment Ready 체크리스트(`env-bootstrap` 스킬)가 모두 통과하거나, 실패 항목에 사용자 승인이 난 뒤에만 Gate ③으로 넘어간다.
- **미결정 4번(팀 웹서버의 Superset 운영 조건)은 "결정됨"이다(2026-10-11).** 추가 컨테이너 운영이 허용되어 Superset은 `compose.yml`의 정식 서비스이고, Redis/Valkey는 제외하며, BI-Wizard는 메인 플랫폼의 URL 하위 경로(`APP_BASE_PATH`, `SUPERSET_APP_ROOT`)로 서비스되고, 메모리는 프로젝트 전체 8GB로 시작한다(`docs/decisions/03a-deploy-environment.md`). 웹서버 배포 때 관리자와 맞출 항목은 `docs/deploy-coordination.md`에 모은다. 새로 알게 된 협의 항목은 이 파일에 추가한다.
- **미결정 1번(Azure OpenAI 항목 처리)은 "제외"로 결정됐다(2026-10-11).** `.env.example`에 Azure OpenAI 변수를 넣지 않고 `/health/azure-openai`를 만들지 않으며, 체크리스트 항목은 "해당 없음"이다.
- BAT 파일은 작성만 하고, 실행 검증 요청서를 사용자에게 준다.

### Gate ③: MODULARIZE
- architect가 산출물을 만들고 reviewer가 리뷰한다.
- 이 Gate에서 사용자에게 **미결정 2번(수식 범위 첫 버전)**, **3번(새 데이터셋 생성 권한)**, **6번(저장 전 수식 평가 경로)**, **7번(Explore 제공 방식)**, **8번(포털 사용자 인증과 신원 출처)**, **9번(동시 편집 정책)**, **10번(Superset 데이터셋·대시보드 등록 방식)**, **11번(삭제 정책)**, 그리고 **마이그레이션 D2(동적 객체 분리 방식)**, 앱 계정 분리, guest 역할 권한 목록, RLS `clause` 규칙, `CREATE VIEW` 리터럴 처리, 업로드 상한을 질문한다. 옵션과 영향을 함께 준다.
- **결정 라운드(0~5)** 순서를 따른다(`modularize` 스킬, `docs/gate-status.md`의 "Gate ③ 진행 계획"). 0라운드는 researcher의 공식 문서 사실 확인이고 reviewer가 출처와 본문을 대조한다. 라운드마다 질문을 올린 뒤 멈추고, 답을 받으면 바로 `gate-status.md`와 해당 decisions 문서에 기록한다. 8번(인증) 답이 늦으면 2번을 먼저 진행하고 8번에 의존하는 3번과 이후 항목은 8번 답을 받은 뒤 진행한다.
- 사실 확인을 위해 메인이 Superset 6.1.0 소스를 이미지에서 꺼내 `_workspace/gate3/sources/superset-6.1.0/`에 둔다(reviewer와 researcher가 읽을 수 있게).
- Gate ① 원본 대조 인계 사항과 `CREATE VIEW` 렌더링 근거(PostgreSQL·SQLAlchemy 공식 문서 확인)는 `docs/gate-status.md`의 "Gate ③ 인계 사항"을 따른다.
- API 계약과 모듈 경계는 승인 후에만 `docs/decisions/`에 확정한다. 이후 계약 변경은 사용자 승인이 필요하다.

### Gate ④: 기능 개발
- **진입 조건:** Gate ③에서 설계한 최소 권한 앱 계정 분리가 완료되어 있어야 한다(`docs/gate-status.md` 인계 사항). backend가 슈퍼유저로 접속하면 `bi-review`가 차단한다.
- 기능 단위 목록은 Gate ③에서 승인된 순서를 따른다. 한 번에 한 단위만 진행한다.
- 단위마다 다음 순서를 따른다.
  1. backend-dev, frontend-dev가 계약을 확인하고 테스트를 포함해 구현한다.
  2. qa-engineer가 모듈이 끝날 때마다 바로 검증한다.
  3. 기능 Skill(`skills/<기능>/SKILL.md`)과 연관 Skill을 갱신한다.
  4. 회귀 테스트를 실행한다.
  5. reviewer가 읽기 전용으로 리뷰한다. 메인이 변경 파일과 diff를 `_workspace/review/`에 넣어 준다.
  6. 발견된 차단·중요 항목을 고친 뒤 사용자에게 단위 완료를 보고하고 승인을 받는다.
- 기능 코드만 바뀌고 Skill이 갱신되지 않았으면 완료로 보지 않는다.

## 산출물 위치 규칙
| 위치 | 용도 | Git |
| --- | --- | --- |
| `_workspace/` | 임시 작업물, 승인 전 초안 | 제외 (`.gitignore`) |
| `docs/decisions/` | 사용자가 승인한 Gate 결과 | 커밋 |
| `docs/gate-status.md` | Gate 진행 상태와 승인 기록 | 커밋 |
| `references/` (루트) | 선택된 공개 소스의 기록과 출처 | 커밋 |
| `skills/` (루트) | 제품 기능 사용설명서 (운영 가이드 5절) | 커밋 |
| `.claude/` | 개발용 하네스 (에이전트, 스킬, 설정) | 커밋 |

`skills/`(제품 사용설명서)와 `.claude/skills/`(개발 하네스)를 섞지 않는다.

## docs/gate-status.md 형식
```markdown
# Gate 진행 상태

| Gate | 상태 | 승인일 | 승인 내용 | 관련 문서 |
| --- | --- | --- | --- | --- |
| ① RESEARCH & DECIDE | 진행 중 | - | - | - |
| ② ENVIRONMENT BOOTSTRAP | 대기 | - | - | - |
| ③ MODULARIZE | 대기 | - | - | - |
| ④ 기능 개발 | 대기 | - | - | - |

## 미결정 사항 (브리프 5절)
| 번호 | 질문 | 상태 | 답변 |
| --- | --- | --- | --- |
| 1 | Azure OpenAI 항목 처리 | 미결정 | - |
| 2 | 수식 범위 첫 버전 | 미결정 | - |
| 3 | 새 데이터셋 생성 권한 | 미결정 | - |
| 4 | 팀 웹서버 Superset 운영 조건 | 미결정 | - |
| 5 | 디자인 방향 | 미결정 | - |
```
위 표는 `docs/gate-status.md`를 **최초 생성할 때의 초기 상태 예시**다. 현재 상태(결정된 항목, 6·7번 추가 등)는 `docs/gate-status.md`가 정본이다.

상태는 `대기`, `진행 중`, `승인 대기`, `승인`, `완료` 중 하나를 쓴다.

## 미결정 사항 규칙
- 브리프 5절의 항목은 에이전트가 정하지 않는다. 필요한 Gate에서 사용자에게 묻는다.
- 답을 받으면 `docs/gate-status.md`의 미결정 표와 관련 `docs/decisions/` 파일에 기록한다.
- 에이전트가 답 없이 구현해야 하는 상황이면 `BLOCKED: 미결정 n번`으로 보고받고, 그 부분만 멈춘다. 나머지 작업은 계속한다.

## 사전 승인 규칙 (2026-10-11 사용자 결정)
- **새 환경변수 추가, 운영 가이드 기준선과 다른 설정, 에이전트 모델 변경은 적용 전에 사용자 승인을 받는다.**
- 새 환경변수: `.env.example`에 승인 목록 밖의 변수를 추가하려면 이름, 의미, 이유를 먼저 제안한다. 사후 보고로 대신하지 않는다.
- 운영 가이드 기준선과 다른 설정: 예) 포트 게시 범위, 인코딩·BAT 형식, 기본 설정과 다른 보안·네트워크 값. 차이와 이유를 먼저 제안한다.
- 에이전트 모델 변경: 정의 파일(`.claude/agents/*.md`)의 모델을 유지하고, 호출 시 `model`을 바꾸지 않는다. 바꿔야 하면 에이전트, 사유, 비용 영향을 먼저 제안한다. Gate ④ 시작 전에 모델 판단을 다시 한다.
- 승인받지 못한 상태에서 적용했다면(긴급 포함) 즉시 사용자에게 보고하고 되돌릴지 묻는다.

## Git 규칙
- `main`에 직접 커밋하거나 푸시하지 않는다.
- 작업은 기능 브랜치에서 한다. 사용자가 지정한 브랜치가 있으면 그 브랜치를 쓴다.
- 승인된 Gate 결과마다 커밋한다. 커밋 메시지는 한국어로 쓰고 Gate 이름을 넣는다.
- PR은 사용자가 요청할 때만 만든다.

## 오류 처리
- 에이전트가 실패하면 한 번 다시 실행한다. 또 실패하면 원인을 사용자에게 보고하고, 결과 없이 진행하지 않는다.
- 사용량 한도, 인증 만료, 권한 거부처럼 다시 시도해도 결과가 같은 실패는 반복하지 않는다. 사용자에게 알리고 기다린다.
- Docker 데몬 문제는 `qa-verification` 스킬의 절차를 따른다.

## 재실행과 후속 요청
- 이미 승인된 Gate를 다시 열려면 사용자의 명시적 요청이 필요하다. 다시 연 Gate는 `docs/gate-status.md`에 `재승인 필요`로 표시한다.
- 일부만 고치라는 요청이면 해당 에이전트와 단계만 다시 실행한다.
- 새 입력을 받았으면 기존 `_workspace/` 결과를 `_workspace/archive-<날짜>/`로 옮긴 뒤 새로 실행한다.

## 테스트 시나리오
- **정상 흐름:** 새 세션에서 "BI-Wizard 개발 시작"을 요청한다. 오케스트레이터가 `docs/gate-status.md`가 없음을 확인하고, Gate ①을 시작하며 파일을 만든 뒤 researcher 두 명을 병렬 실행하는지 확인한다.
- **오류 흐름:** 사용자가 승인하지 않고 "다음 Gate 진행해"라고 요청한다. 오케스트레이터가 승인 상태를 알리고 다음 Gate를 시작하지 않는지 확인한다.
- **미결정 흐름:** Gate ③에서 수식 범위를 임의로 정하려는 시도가 있으면, 오케스트레이터가 사용자에게 질문하고 구현을 멈추는지 확인한다.
