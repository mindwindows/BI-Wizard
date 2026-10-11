# BI-Wizard 프로젝트 브리프

작성일: 2026-10-11 (개정: 팀 웹서버 운영 가이드 반영)
출처:
- claude.ai 채팅 "Excel to dashboard web application"(2026-10-10)에서 논의·확인된 요구사항
- 팀 웹서버 운영자가 안내한 「AI Agent 개발 지침서」(이하 "운영 가이드") — 원문은 `docs/AI_AGENT_DEVELOPMENT_GUIDE_요약.md`

Claude Code는 claude.ai 채팅을 읽지 못하므로, 이 문서를 프로젝트 요구사항의 기준으로 삼는다.
**"결정됨"과 "미결정"을 구분해 두었다. 미결정 항목은 임의로 정하지 말고 사용자에게 질문할 것.**
운영 가이드와 이 문서가 충돌하면 운영 가이드를 우선하되, 충돌 사실을 사용자에게 알린다.

---

## 1. 목적과 배경

- 사내에 대시보드 수요는 많지만 매번 개발자가 만들고 있다. 요청이 일회성이거나 요구가 자주 바뀌어 개발자가 이 업무를 부담스러워한다.
- 목표: 의뢰자(비개발자)가 직접 데이터를 정의·입력하고 대시보드를 만들 수 있는 **셀프서비스 웹 서비스**.
- 현재 방식: 여러 담당자가 Teams에서 엑셀 파일을 공유·동시 편집하며 실적·진행현황을 수동 관리 중. 이를 **권한 있는 사용자가 웹에서 입력하면 대시보드에 반영**되는 구조로 바꾼다.
- 회사에 Power BI Pro 라이선스가 없어 Power BI 기반 방안은 제외됐다.
- 최종적으로 **팀 웹서버에서 서비스**한다. 따라서 운영 가이드의 공통 기술 기준·저장소 구조·실행 계약을 처음부터 따른다.

## 2. 핵심 흐름

```
칸(열) 정의 → 엑셀식 수식 정의 → 원본(raw) 데이터만 입력 → SQL 뷰 자동 생성 → Superset 대시보드
            ↑
   엑셀 업로드(Lists식 가져오기 마법사)로도 테이블 생성·적재 가능
```

## 3. 운영 가이드에서 가져온 고정 기준

### 3.1 공통 기술 기준
| 항목 | 기준 | 이 프로젝트 적용 |
|---|---|---|
| 실행 환경 | Desktop Web 우선 (PC 브라우저, 높은 정보 밀도, 마우스/키보드 효율) | 그대로 적용. 입력 그리드·데이터셋 정의 화면 모두 데스크톱 기준 |
| Backend | **FastAPI 고정**, REST 기본 | FastAPI (Django 후보 제외) |
| Database | **PostgreSQL 고정** | 그대로 적용 |
| AI | Azure OpenAI 고정 (AI 호출 시) | 이 프로젝트는 운영 중 LLM 미사용 → 5절 미결정 사항 참고 |
| Frontend | HTML / Vue / React 중 선택 | React (AG Grid Community와 함께 사용하기로 논의됨) |
| Local Runtime | Docker Compose, Root의 `compose.yml` 단일 진입점 | 그대로 적용 |
| CI/CD | Jenkins, Root의 `Jenkinsfile` (Pipeline as Code) | 그대로 적용 |

기본 경계: **Frontend → FastAPI → PostgreSQL**. 브라우저에서 DB를 직접 호출하지 않는다.
Superset은 이 경계 밖의 별도 서비스이며, 포털에는 Embedded SDK(guest token)로만 들어온다. guest token 발급은 FastAPI가 담당한다.

### 3.2 개발 진행 순서 (운영 가이드의 Gate)
1. **RESEARCH & DECIDE** — 디자인 방향 2~3안, 기술 Reference 3~5개를 AI가 먼저 조사·비교 → 사용자 선택 후에만 다음 단계.
   - 기술 구성은 채팅에서 상당 부분 정해졌으므로(4.7절), 이 단계의 주된 대상은 **디자인 방향**과 **세부 Reference**(예: Lists식 가져오기 UI, 수식 편집기 UI 참고 사례).
   - 금지: 검색 없이 "최신"이라고 단정, 첫 검색 결과를 그대로 적용, 합의 전 대규모 소스 다운로드.
2. **ENVIRONMENT BOOTSTRAP** — 업무 기능 개발 전에 실행·검증 환경을 먼저 완성. 3.4절 체크리스트를 모두 통과해야 기능 개발로 넘어간다.
3. **MODULARIZE** — 기능 모듈 경계와 Skill 경계를 먼저 설계.
4. **기능 개발** — Feature Code + Test + Skill을 하나의 작업 단위로 진행.

### 3.3 저장소 기준 구조
```text
BI-Wizard/
├─ backend/            # FastAPI (app/, tests/, Dockerfile)
├─ frontend/           # React (src/, Dockerfile)
├─ scripts/            # start/stop/restart/logs/health-check/validate-env .bat
├─ skills/             # 기능별 운영 Skill (local-environment/SKILL.md 부터)
├─ references/         # 선택된 Reference만 보관 (출처·목적·License·Version/Commit·참고 위치 기록)
├─ docs/               # 이 브리프, 운영 가이드 원문 등
├─ .claude/            # Claude Code용 하네스(에이전트·스킬) — 아래 주의 참고
├─ compose.yml
├─ .env.example        # 변수명 기준 원본 (Git 관리, Secret 값 없음)
├─ .env                # 로컬 실제 값 (Git 제외)
├─ .gitignore
├─ Jenkinsfile
├─ AGENTS.md           # 환경/Skill/변경 규칙
├─ CLAUDE.md           # Claude Code 진입점 — AGENTS.md와 이 브리프를 읽도록 안내
└─ README.md           # 신규 개발자 최소 실행 절차
```

주의 — 두 종류의 "skills"를 구분한다:
- `skills/` (저장소 루트): 운영 가이드가 요구하는 **제품 기능의 사용설명서**. 사람과 모든 AI 도구가 읽는 문서이며, 기능 코드와 항상 동기화한다.
- `.claude/skills/`, `.claude/agents/`: revfactory/harness가 만드는 **개발용 에이전트 팀 정의**. 제품 기능 문서가 아니다.
- 클라우드 Claude Code가 자동으로 읽는 파일 목록에 `CLAUDE.md`와 `.claude/` 하위는 있지만 `AGENTS.md`는 없다. 따라서 `CLAUDE.md`에서 `AGENTS.md`를 읽도록 명시한다.

### 3.4 실행·검증 계약
- 시작: `docker compose up -d --build` / 종료: `docker compose down`
- 서비스: 최소 `postgres / backend / frontend` + 이 프로젝트에 필요한 Superset 관련 서비스. DB Health Check 후 Backend가 시작되도록 의존성 정의.
- Health Check: `/health`, `/health/db` 를 업무 API보다 먼저 만든다. Superset 컨테이너 상태도 같은 방식으로 확인할 수 있게 한다.
- Frontend 컨테이너에는 전체 `.env`를 넘기지 않는다. API 주소는 상대경로 `/api` + 프록시 방식.
- Jenkinsfile 초기 Stage: Checkout → Env Validation → Backend Lint/Test → Frontend Lint/Test/Build → `docker compose config` → Docker Build. 실패 시 이후 단계 중단.
- Windows BAT 5종(start / stop / restart / logs / health-check) + validate-env 제공.
  - 클라우드 Claude Code 세션은 Ubuntu 리눅스이므로 **BAT 파일은 작성만 가능하고 세션 안에서 실행 검증은 불가**하다. BAT 검증은 사용자의 Windows PC에서 한다.

Environment Ready 체크리스트(전부 통과 시 기능 개발 시작):
`.env.example` 변수명 확정 / `.env` Secret 보호 / Backend·Frontend Dockerfile 빌드 / compose 실행·DB healthcheck·volume / compose 시작·종료 성공 / Frontend↔FastAPI 통신 / PostgreSQL 연결 / BAT 5종 / Jenkinsfile CI Gate / `skills/local-environment/SKILL.md` / README·AGENTS.md
(운영 가이드의 "Azure OpenAI 검증 경로" 항목은 5절 미결정 사항 1번 결과에 따른다.)

### 3.5 환경변수 규칙
- `.env.example`이 변수명 기준 원본이다. 운영 가이드의 canonical name(`APP_*`, `FRONTEND_*`, `BACKEND_*`, `POSTGRES_*`, `LOG_LEVEL`, `TZ` 등)을 그대로 쓴다.
- 같은 의미를 다른 이름으로 만들지 않는다. 환경별 이름 분리(`LOCAL_DB_HOST` 등) 금지 — 이름은 고정, 값만 환경별로 바꾼다.
- Superset 등 이 프로젝트가 새로 필요로 하는 변수는 기존 변수와 의미가 겹치는지 먼저 확인한 뒤 추가하고, `.env.example → Backend Settings → compose.yml → Jenkinsfile → README/Skill → Test` 영향 여부를 함께 확인한다.
- Secret(DB Password 등)은 Repository, Dockerfile/Image, Frontend Bundle에 넣지 않는다.

### 3.6 Skill 규칙 (운영 가이드 5절)
- 사용자 관점에서 독립적으로 수행 가능한 주요 기능마다 `skills/<기능>/SKILL.md`를 둔다. (예상 단위: 엑셀 가져오기, 데이터셋 정의, 수식 열, 데이터 입력, 대시보드 연결, 권한 관리 — 확정은 MODULARIZE 단계에서)
- 각 Skill 필수 항목: 목적 / 사용 조건 / 입력 / 출력 / 실행 방법 / 관련 UI·API·command·DB / 실패 시 확인 방법 / 검증 방법 / 연관 Skill
- **Feature Code ↔ Skill ↔ Related Skills ↔ Regression Test는 항상 같이 움직인다.** 기능 코드만 바뀌고 Skill이 갱신되지 않으면 작업 완료로 보지 않는다.
- 주요 기능은 사람이 직접 실행할 수 있는 방법(BAT/CLI/REST API)과 AI가 조작할 수 있는 인터페이스(API/CLI 우선)를 함께 제공한다.

## 4. 제품 요구사항 (채팅에서 결정됨)

### 4.1 운영 조건
- **운영 단계에서 LLM을 사용하지 않는다.** (개발 단계에서의 LLM 활용은 무관)
- 권한을 부여받은 사용자만 이용한다.
- 모든 구성 요소는 사내 사용에 문제없는 **허용적(permissive) 라이선스**만 사용한다.

### 4.2 엑셀 가져오기 (SharePoint Lists 방식 참고)
- 업로드 → 시트·범위 선택(헤더 행 자동 탐지, 사용자 수정 가능)
- 열별 타입 추론 → 제안 화면 → 사용자 확인·수정(열 이름 변경, 제외, 타입 변경)
- 확인 시 PostgreSQL에 테이블 생성, 메타데이터(소유자·원본 파일·생성일·스키마)를 별도 등록 테이블에 기록
- 같은 양식 재업로드 시 저장된 스키마로 자동 적재(추가/교체 선택)
- 범위: Lists와 마찬가지로 **표 형태 범위**만 대상. 병합 셀·다단 헤더 보고서형 엑셀의 자동 해석은 범위 밖.

### 4.3 데이터셋 정의 (코드 없이, "워드에서 칸 만들듯")
- 지원 타입: 텍스트·숫자·날짜·참/거짓·선택 목록·다른 데이터셋 참조(lookup)
- 검증: 필수·범위·정규식·유일성
- 열 추가·이름 변경·순서 변경, 역할별 열 편집 권한
- 데이터가 이미 있는 열의 타입 변경은 **변환 미리보기 후 사용자 확인**을 거친다.

### 4.4 데이터 입력 화면
- **AG Grid Community**로 직접 개발 (NocoDB 등 라이선스 문제가 있는 도구는 쓰지 않음)
- 새 데이터 수집이 생기면 코드 작성 없이 새 데이터셋을 만들어 운영할 수 있어야 한다.
- AG Grid Community에는 여러 셀 범위 선택·클립보드 붙여넣기·.xlsx 내보내기·행 그룹/피벗이 **없다**(Enterprise 기능). 엑셀에서 여러 행을 복사해 붙여넣는 동작은 브라우저 paste 이벤트로 탭 구분 텍스트를 파싱해 **직접 구현**한다. `ag-grid-enterprise` 패키지는 사용하지 않는다.

### 4.5 엑셀식 수식 열 → SQL 뷰
- 사용자는 열마다 엑셀 함수처럼 수식을 입력한다. 원본 열만 입력하면 수식 열은 자동 계산된다.
- 백엔드는 수식을 파싱해 SQL 식으로 변환하고, 원본 테이블 위에 수식 열이 포함된 **뷰**를 만든다. Superset은 이 뷰를 데이터셋으로 읽는다.
- 파서: lark(MIT) 위에 직접 작성. 기성 엑셀 수식 라이브러리 중 EUPL 등 비허용적 라이선스가 있으므로 쓰지 않는다.
- SQL 생성: SQLAlchemy로 하며 문자열 직접 조립은 하지 않는다.
- 고려 사항: 수식 편집기 사용성(열 이름 자동 완성, 오류를 SQL 용어가 아닌 말로 표시), 엑셀과의 의미 차이(날짜 연산, 빈 셀, 문자열 비교), 순환 참조 검출, 열 이름 변경 시 수식 연쇄 수정.
- 열 하나의 수식으로 표현되지 않는 변환(가로로 펼쳐진 월별 열 → 세로 변환, 여러 단계 정제 파이프라인)은 초기 범위 밖.

### 4.6 대시보드
- **Apache Superset 채택 확정** (사용자 결정, 2026-10-11).
- 대시보드 빌더는 직접 만들지 않는다. **Apache Superset을 차트 엔진으로만** 사용하고, Superset 내부 코드는 수정하지 않는다.
- 자체 포털(업로드 마법사, 데이터셋 목록, 입력 화면, 권한 관리)을 개발하고, Superset 대시보드는 Embedded SDK(guest token)로 포털에 넣는다.
- Superset 차트 작성 화면(Explore)은 노코드이며, SQL이 필요한 것은 데이터셋 준비 등 관리자 측 작업이다.
- Superset의 한계: 차트 하나 = 데이터셋 하나. 표를 넘나드는 분석은 뷰(조인)로 미리 만들어야 한다. Power Query에 해당하는 변환 기능은 없다.

### 4.7 기술 구성과 라이선스
| 역할 | 구성 요소 | 라이선스 |
|---|---|---|
| DB | PostgreSQL | PostgreSQL License |
| 포털 백엔드 | Python + **FastAPI**, SQLAlchemy | PSF / MIT / MIT |
| 엑셀 처리 | openpyxl, pandas, rapidfuzz(열 이름 유사도) | MIT / BSD-3 / MIT |
| 수식 파서 | lark | MIT |
| 프론트엔드 | React, AG Grid Community | MIT / MIT |
| 시각화 | Apache Superset, Embedded SDK | Apache 2.0 |
| SSO | Flask-AppBuilder(Superset), Authlib | BSD-3 |
| 리버스 프록시 | Nginx 또는 Caddy | BSD-2 / Apache 2.0 |
| 컨테이너 | Docker Engine(서버) / Docker Compose | Apache 2.0 |
| CI | Jenkins | MIT |

주의:
- **Redis**는 7.4부터 라이선스가 바뀌었다. 회사 정책상 문제가 되면 **Valkey**(BSD-3, Redis 호환)로 대체한다.
- **Docker Desktop**은 일정 규모 이상 기업에서 유료. 서버의 Docker Engine은 무관하며, 개발 PC는 Podman 등으로 대체 가능.
- DB 마이그레이션 도구는 운영 가이드("신규 프로젝트에서만 필요한 조합을 제안")에 따라 ENVIRONMENT BOOTSTRAP 단계에서 제안·확정한다. → **결정됨 (2026-10-11): Alembic.** 실행 방식과 규칙은 `docs/decisions/03-migration-tool.md` 참고.

### 4.8 제외한 도구
- Power BI(라이선스 없음), Metabase(AGPL, SSO·임베딩 유료), NocoDB(Sustainable Use License), Mathesar(GPLv3)

## 5. 미결정 사항 (임의로 정하지 말 것)

1. **Azure OpenAI 항목 처리**: 운영 가이드의 `.env.example`·Health Check(`/health/azure-openai`)·체크리스트에 Azure OpenAI가 포함되어 있으나, 이 프로젝트는 운영 중 LLM을 쓰지 않는다. 해당 항목을 (a) 빈 변수·N/A 처리로 남길지, (b) 제외할지 **웹서버 운영자 확인 후** 결정. → **결정됨 (제외, 2026-10-11, 사용자 결정)**:
   - `.env.example`에서 Azure OpenAI 변수(`AZURE_OPENAI_*`)를 뺀다.
   - `/health/azure-openai`는 만들지 않는다.
   - Environment Ready 체크리스트의 "Azure OpenAI 검증 경로" 항목은 **"해당 없음"** 으로 처리한다.
   - 운영 가이드의 기본 구성에서 벗어나는 의도적 차이다. 이후 LLM을 쓰게 되면 사용자 승인을 받아 다시 논의한다.
2. **수식 범위의 첫 버전**: 같은 행 안의 계산만 / 다른 표 참조(VLOOKUP류)까지 / 집계(SUMIF·롤업)까지. 사용자는 "라이선스 문제없이 가능한지"를 먼저 확인했고, 난이도는 추후 검토하기로 했다.
3. **새 데이터셋 생성 권한**: 편집자 전원 / 관리자(또는 팀별 담당자)로 제한.
4. **팀 웹서버의 Superset 운영 조건**: Superset 사용은 확정됐다. 다만 운영 가이드의 기본 서비스 구성은 postgres/backend/frontend이므로, 팀 웹서버에서 Superset(및 캐시용 Redis/Valkey)을 추가 서비스로 띄울 수 있는지, 포트·도메인·리소스 조건은 어떤지 **웹서버 운영자 확인**이 필요하다. 확인 전까지는 로컬 `compose.yml`에 Superset 서비스를 포함해 개발한다.
5. **디자인 방향**: 운영 가이드 1단계(RESEARCH & DECIDE)에서 2~3안을 비교한 뒤 사용자가 선택. → **결정됨 (2026-10-11, Gate ①)**: `docs/decisions/01-design-direction.md` 참고.
6. **수식 미리보기·자동완성을 위한 저장 전 수식 평가 경로** (Gate ① 조사에서 추가, **Gate ③에서 결정**): 수식 편집기의 라이브 결과 미리보기, 열 이름 자동완성, "예시 값" 후보는 저장 전에 수식을 평가하는 경로(예: 서버에서 샘플 행으로 평가)가 있어야 가능하다. 어떤 경로로 제공할지, 수식 범위(2번)와 어떻게 맞출지 정한다.
7. **Superset 차트 작성 화면(Explore)을 포털에서 어떻게 제공할지** (Gate ① 조사에서 추가, **Gate ③에서 결정**): Embedded SDK로 가능한 범위를 Superset 공식 문서로 확인한 뒤 결정한다. 4번(팀 웹서버 Superset 운영 조건)과 관련된다.
