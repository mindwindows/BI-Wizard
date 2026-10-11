# AI Agent 개발 지침서

## 기술 스택

|항목|값|
|-|-|
|실행 환경|Desktop Web|
|Backend|FastAPI|
|Database|PostgreSQL|
|AI|Azure OpenAI|
|Frontend|HTML / Vue / React|
|Local Runtime|Docker Compose|
|CI/CD|Jenkins|

## 0\. 모든 프로젝트의 공통 기술 기준

*기술 선택 논의를 매번 처음부터 하지 않는다*

* **TARGET · Desktop Web 우선**
PC 브라우저 기반 업무용 Web Application을 기본으로 한다. 모바일보다 넓은 화면, 높은 정보 밀도, 마우스/키보드 작업 효율을 우선한다.
* **BACKEND · FastAPI 고정**
Python 기반 FastAPI를 API 서버의 기본으로 사용한다. REST를 기본으로 하고 실시간 기능이 필요할 때만 WebSocket/SSE를 검토한다.
* **DATABASE · PostgreSQL 고정**
업무 데이터의 기본 저장소는 PostgreSQL이다. 기존 ORM/Migration 구성이 있으면 그대로 유지하고 신규 프로젝트에서만 필요한 조합을 제안한다.
* **AI · Azure OpenAI 고정**
LLM/Embedding/Agent 관련 AI 호출은 Azure OpenAI를 사용한다. Key/Endpoint/Deployment 정보는 Backend 환경변수로 관리한다.
* **FRONTEND · 목적에 따라 선택**
HTML/CSS/JavaScript, Vue.js, React 중 프로젝트 성격에 맞게 선택한다. 단, 기존 프로젝트라면 특별한 이유 없이 Framework를 교체하지 않는다.
* **NODE.JS · 개발·빌드 환경**
Node.js는 Vue/React의 package/build/runtime tooling에 사용한다. Node.js 자체를 Frontend Framework와 혼동하지 않는다.
* **LOCAL RUNTIME · Docker Compose 표준**
신규 프로젝트의 Local 실행 진입점은 Root의 `compose.yml`로 고정한다. `docker compose up -d --build` 한 번으로 필요한 서비스가 올라오는 상태를 목표로 한다.
* **CONFIG · .env 변수명 고정**
`.env.example`을 변수명 기준 원본으로 사용한다. 같은 의미의 환경변수를 다른 이름으로 중복 추가하지 않고 환경별로 **이름은 유지하고 값만 변경**한다.
* **CI/CD · Jenkins Pipeline as Code**
CI/CD는 Jenkins를 기본으로 하며 Pipeline은 Root의 `Jenkinsfile`로 관리한다. Jenkins UI에는 Agent/Credential 등 최소 설정만 둔다.
* **Desktop Browser** — 화면 · 사용자 입력 · 표/그래프 · Viewer · 업무 조작 ↓
* **Frontend** — HTML/JS 또는 Vue/React · 상태 관리 · API 호출 ↓
* **FastAPI Backend** — Business Logic · 검증 · DB/AI 접근 단일 통로 ↓
* **PostgreSQL / Azure OpenAI** — 영속 데이터 / LLM·Embedding·Agent

> 기본 경계: Frontend → FastAPI → PostgreSQL / Azure OpenAI. 특별한 이유가 없는 한 브라우저에서 DB 또는 Azure OpenAI를 직접 호출하지 않는다.

## 1. RESEARCH \& DECIDE — 최신 디자인과 기술 Reference를 AI와 함께 찾고 고른다

*사용자가 후보를 미리 알 필요는 없다 · AI가 먼저 조사하고 근거를 제시*

#### DESIGN RESEARCH · 최신 디자인을 AI가 먼저 찾는다

“세련되게 해줘”에서 끝내지 않는다. AI가 현재 시점의 유사 Desktop Web, 업무용 Dashboard, Viewer, Editor 등을 검색하고 **서로 다른 2\~3개의 디자인 방향**으로 정리해 사용자가 비교할 수 있게 한다.

* **AI가 조사할 것** — 레이아웃, 정보 위계, Navigation, Panel 구조, Table/Filter, Interaction, 밀도, 시각 언어
* **AI가 설명할 것** — 각 방향의 참고 사례 · 장점/단점 · 우리 프로젝트에 가져올 요소 · 피할 요소 · 추천 이유

#### TECH REFERENCE · Reference 후보도 AI가 찾는다

사용자가 Blender, Bonsai 같은 후보를 알고 있을 때만 참고하는 방식이 아니다. AI가 프로젝트의 핵심 기능을 기준으로 관련 프로그램, 오픈소스, GitHub 저장소, 라이브러리를 직접 찾아 **3\~5개의 후보**를 비교한다.

* **비교 기준** — 우리 기능과의 관련성, 참고할 구조/알고리즘, 기술 스택, 유지보수 상태, License, 통합 난이도
* **사용자가 결정할 것** — 어떤 Reference를 실제 프로젝트에 확보할지, 여러 후보 중 무엇을 우선 참고할지

#### DECISION GATE · 검색 → 설명 → 논의 → 선택

AI는 검색 결과를 바로 적용하지 않는다. 디자인과 기술 Reference 모두 먼저 비교표와 추천안을 보여주고, 사용자가 질문하거나 조합할 수 있게 한다. **선택이 끝난 뒤에만** 실제 설계와 Reference 확보 단계로 넘어간다.

* **좋은 방식** — “A 디자인의 Layout + B 디자인의 상세 Panel”, “Reference 1의 구조 + Reference 3의 알고리즘”처럼 조합 가능
* **금지** — 검색 없이 최신이라고 단정, 첫 검색 결과를 무조건 적용, 합의 전 대규모 소스 다운로드/도입
* **DESIGN OUTPUT · 디자인 방향 2\~3안**
각 안마다 참고 사례, 화면 구성, 시각적 특징, 업무 UX 적합성, 장단점, 적용/비적용 요소를 정리한다.
* **REFERENCE OUTPUT · 기술 Reference 3\~5개**
각 후보마다 무엇을 참고할지, 유지 상태, 라이선스, 예상 활용 범위와 위험을 정리한다.
* **USER DECISION · 사용자는 후보를 보고 선택**
사용자가 미리 최신 UI나 오픈소스를 알 필요가 없다. AI가 탐색과 1차 평가를 맡고 사용자는 목적에 맞는 방향을 판단한다.

## 2. ENVIRONMENT BOOTSTRAP — 기능 개발 전에 개발환경부터 완성한다

*첫 번째 Deliverable은 업무 기능이 아니라 “누구나 같은 방식으로 실행·검증 가능한 환경”*

> \*\*Environment Gate\*\*
>
> Frontend 선택과 큰 기술 방향이 정해지면 \*\*실제 업무 Feature 개발을 잠시 멈추고 개발환경을 먼저 구축\*\*한다. 새 PC에서 Repository를 받은 사람이 Secret/환경값만 설정한 뒤 동일한 명령으로 Frontend, FastAPI, PostgreSQL을 실행하고 상태를 확인할 수 있어야 한다. 이 Gate를 통과하기 전에는 실제 업무 기능 개발로 넘어가지 않는다.

* **SINGLE ENTRY · compose.yml이 Local 실행 기준**
Root의 `compose.yml`을 Local Runtime의 Single Entry Point로 사용한다. PostgreSQL, FastAPI, Frontend와 필요한 인프라를 하나의 실행 절차로 관리한다.
* **ENV CONTRACT · 환경변수 이름을 프로젝트 표준으로**
`.env.example`에 canonical name을 정의한다. 새 변수가 필요하면 기존 변수와 의미가 겹치는지 먼저 확인하고 이름을 임의로 바꾸지 않는다.
* **LOCAL CONTROL · Windows BAT로 조작 표준화**
`start / stop / restart / logs / health-check` BAT를 제공한다. 사용자와 AI가 같은 명령을 사용해 환경을 조작하도록 한다.
* **HEALTH · 기능보다 먼저 Health Check**
FastAPI 기본 상태, PostgreSQL 연결, Azure OpenAI 설정/연결 상태를 분리해 확인할 수 있는 Health Check를 만든다.
* **CI BASELINE · Jenkinsfile 뼈대를 먼저 구축**
운영 Deploy가 정해지지 않았더라도 Checkout → Validation → Test → Build → Compose/Docker 검증까지의 CI Pipeline을 프로젝트 시작 시 만든다.
* **AI OPERABILITY · 개발환경도 Skill로 문서화**
`skills/local-environment/SKILL.md`에 실행, 종료, 로그, Health Check, 문제 해결과 연관 Skill을 작성해 AI가 실행법을 추측하지 않게 한다.

### 표준 Repository Baseline

*프로젝트 시작 직후 만들어둘 최소 구조*

```text
project/
├─ backend/
│  ├─ app/
│  ├─ tests/
│  └─ Dockerfile
├─ frontend/
│  ├─ src/
│  └─ Dockerfile
├─ scripts/
│  ├─ start-local.bat
│  ├─ stop-local.bat
│  ├─ restart-local.bat
│  ├─ logs-local.bat
│  ├─ health-check.bat
│  └─ validate-env.bat
├─ skills/
│  └─ local-environment/
│     └─ SKILL.md
├─ references/
├─ compose.yml
├─ .env.example             # 변수명 기준 원본 · Git 관리
├─ .env                     # Local 실제 값 · Git 제외
├─ .gitignore
├─ Jenkinsfile              # Pipeline as Code
├─ AGENTS.md                # 환경/Skill/변경 규칙
└─ README.md                # 신규 개발자 최소 실행 절차
```

### 고정 환경변수 Naming Convention

*이름은 고정 · Local/DEV/STAGE/PROD는 값만 변경*

### .env.example · Canonical Names

*Secret 값은 작성하지 않음*

```ini
# Application
APP\_NAME=
APP\_ENV=local
APP\_DEBUG=true

# Frontend
FRONTEND\_HOST=0.0.0.0
FRONTEND\_PORT=5173

# Backend
BACKEND\_HOST=0.0.0.0
BACKEND\_PORT=8000

# PostgreSQL
POSTGRES\_HOST=postgres
POSTGRES\_PORT=5432
POSTGRES\_DB=
POSTGRES\_USER=
POSTGRES\_PASSWORD=

# Azure OpenAI
AZURE\_OPENAI\_ENDPOINT=
AZURE\_OPENAI\_API\_KEY=
AZURE\_OPENAI\_API\_VERSION=
AZURE\_OPENAI\_CHAT\_DEPLOYMENT=
AZURE\_OPENAI\_EMBEDDING\_DEPLOYMENT=

# Logging / Runtime
LOG\_LEVEL=INFO
TZ=Asia/Seoul
```

* **같은 의미의 새 이름 금지** — `OPENAI\_URL`, `AOAI\_ENDPOINT`, `AZURE\_URL`처럼 기존 의미를 다른 이름으로 다시 만들지 않는다.
* **환경별 이름 분리 금지** — `LOCAL\_DB\_HOST`, `PROD\_DB\_HOST`를 만들지 않는다. 코드에서는 `POSTGRES\_HOST` 하나만 보고 환경이 값을 주입한다.
* **Secret은 Git/Frontend에서 제외** — `.env`, Azure OpenAI Key, DB Password를 Repository, Dockerfile/Image, Frontend Bundle에 포함하지 않는다.
* **새 변수 추가 시 동기화** — `.env.example → Backend Settings → compose.yml → Jenkinsfile/Credential Mapping → README/Skill → Test` 영향 여부를 함께 확인한다.

### Local Runtime / Health / CI 기본 계약

*개발자와 AI가 공통으로 사용할 실행 인터페이스*

#### COMPOSE · 한 명령으로 전체 실행

`docker compose up -d --build`를 기본 시작 명령으로 하고 `docker compose down`으로 종료한다. 서비스는 최소 **postgres / backend / frontend**로 구성하고 DB Health Check 후 Backend가 시작되도록 의존성을 정의한다.

* **Local Start** — scripts/start-local.bat → docker compose up -d --build
* **Local Stop / Log** — stop-local.bat / logs-local.bat / restart-local.bat

#### HEALTH · 상태를 명시적으로 확인

업무 API보다 먼저 상태 확인 경로를 만든다. Azure OpenAI는 단순 환경변수 로딩 상태와 실제 Connectivity Test를 구분해 외부 장애/비용과 애플리케이션 상태를 분리한다.

* **권장 Endpoint** — `/health` · `/health/db` · `/health/azure-openai`
* **검증** — Frontend 접속 → FastAPI → PostgreSQL → Azure OpenAI 설정/연결 순으로 확인

#### JENKINS CI · Deploy 전에도 Pipeline은 존재

운영 서버가 아직 없더라도 Jenkinsfile을 만들고 CI 최소 Gate를 구축한다. Pipeline 로직은 Jenkins UI가 아니라 Repository에서 버전 관리한다.

* **초기 Stage** — Checkout → Env Validation → Backend Lint/Test → Frontend Lint/Test/Build → `docker compose config` → Docker Build
* **실패 정책** — Validation/Test/Build가 실패하면 이후 단계와 Deploy를 진행하지 않는다.

### compose.yml Baseline 예시

*프로젝트별 세부값은 달라도 Service 이름과 실행 계약은 가능한 한 유지*

### compose.yml · Local Baseline

*개념 템플릿 · 실제 Dockerfile/Framework에 맞게 조정*

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES\_DB: ${POSTGRES\_DB}
      POSTGRES\_USER: ${POSTGRES\_USER}
      POSTGRES\_PASSWORD: ${POSTGRES\_PASSWORD}
    ports:
      - "${POSTGRES\_PORT}:5432"
    volumes:
      - postgres\_data:/var/lib/postgresql/data
    healthcheck:
      test: \["CMD-SHELL", "pg\_isready -U ${POSTGRES\_USER} -d ${POSTGRES\_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: ./backend
    env\_file:
      - .env
    ports:
      - "${BACKEND\_PORT}:8000"
    depends\_on:
      postgres:
        condition: service\_healthy

  frontend:
    build:
      context: ./frontend
    ports:
      - "${FRONTEND\_PORT}:5173"
    depends\_on:
      - backend

volumes:
  postgres\_data:
```

> Frontend Container에는 전체 `.env`를 전달하지 않는 것을 기본으로 한다. Browser에서 필요한 공개 설정만 제한적으로 전달하고, Azure OpenAI Key·DB Password 같은 Secret은 Backend에만 존재해야 한다. Frontend의 API 주소는 가능하면 relative `/api` + proxy/reverse proxy 방식으로 단순화한다.

### Environment Ready Checklist

*전부 통과하면 Feature 개발 시작*

* \[ ] **.env.example / Naming 확정**
canonical variable list와 주석이 있고 중복 의미 변수 없음
* \[ ] **.env / Secret 보호**
.gitignore 적용 · Repository/Frontend/Image에 Secret 없음
* \[ ] **Backend / Frontend Dockerfile**
각 이미지 Build 가능
* \[ ] **compose.yml**
postgres/backend/frontend 실행 · DB healthcheck · volume 정의
* \[ ] **Compose Start / Stop**
up -d --build / down 실제 성공
* \[ ] **Frontend ↔ FastAPI**
브라우저 접속과 최소 통신 확인
* \[ ] **PostgreSQL 연결**
Backend에서 실제 연결 상태 확인
* \[ ] **Azure OpenAI 검증 경로**
설정 로딩과 실제 Connectivity Test 구분
* \[ ] **BAT 5종**
start / stop / restart / logs / health-check
* \[ ] **Jenkinsfile CI**
Validation/Test/Build/Compose/Docker Build Gate 존재
* \[ ] **Local Environment Skill**
AI가 실행·중지·로그·Health Check 방법을 알 수 있음
* \[ ] **README / AGENTS.md**
신규 개발자와 AI가 같은 규칙을 읽음

## 4\. MODULARIZE — 기능 구조와 Skill 경계를 먼저 설계한다

*Reference/디자인 논의와 “어떻게 확장할지”를 분리해서 관리*

* **FEATURE BOUNDARY · 기능을 독립 모듈로 분리**
화면, API, Business Logic, Data Access를 기능 단위로 나누고 새로운 기능을 붙일 때 핵심 코드를 크게 건드리지 않도록 확장점을 만든다.
* **SKILL BOUNDARY · 모듈과 Skill의 대응관계 정의**
사용자 관점에서 독립적으로 수행 가능한 주요 Feature마다 대응 Skill을 둔다. 너무 작은 helper마다 Skill을 만들지는 않고 “AI가 하나의 작업으로 사용할 수 있는 기능 단위”를 기준으로 한다.
* **REFERENCE STORAGE · 선택한 Reference만 프로젝트에 확보**
논의 후 선택된 공개 소스만 `references/`에 받아두고 출처, 목적, License, Version/Commit, 참고할 위치를 기록해 이후 AI가 반복해서 확인할 수 있게 한다.

## 5. OPERATE — 사용자와 AI가 모두 조작할 수 있게 한다

*원본 프롬프트에서 크게 누락되기 쉬운 핵심 규칙*

* **HUMAN OPERABILITY · 실행 방법을 단순하게**
사용자가 직접 실행/중지/초기화/테스트할 수 있도록 필요하면 `.bat`, PowerShell, shell script, CLI, 관리 API 등을 제공한다.
* **AI OPERABILITY · AI도 기능을 사용할 수 있게**
AI가 화면 기능의 존재와 사용법을 추측하지 않도록 주요 기능마다 명확한 조작 방법과 Skill을 제공한다. 가능한 경우 API/CLI처럼 자동화 가능한 인터페이스를 우선한다.
* **SKILL AS CONTRACT · Skill은 살아있는 사용설명서**
기능의 목적, 입력, 출력, 실행법, 관련 API, 주의사항, 검증법, 연관 Skill을 포함한다. 코드가 바뀌면 Skill도 반드시 같이 바뀐다.

### AI Operability / Skill 공통 규칙

*메인 지침에 넣을 내용*

```text
\[AI Operability / Skill 규칙]

이 프로젝트는 사용자뿐 아니라 AI Agent도 주요 기능을 이해하고
가능한 범위에서 직접 조작할 수 있도록 개발한다.

1. 사용자가 직접 실행/중지/테스트해야 하는 기능에는 적절한 실행 방법을 제공한다.
   예: .bat / PowerShell / CLI / REST API / 개발용 command

2. AI가 기능을 이해하고 사용할 수 있도록 주요 기능마다 대응되는 Skill을 만든다.

3. 각 Skill에는 최소한 다음 내용을 작성한다.
   - 기능의 목적
   - 사용 조건 / 사전 요구사항
   - 입력
   - 출력
   - 실행 방법
   - 관련 UI / API / command / DB
   - 실패 시 확인 방법
   - 검증 방법
   - 연관 Skill

4. 새로운 기능 추가는 Feature Code + Test + Skill을 하나의 작업으로 취급한다.

5. 기존 기능을 수정할 때는 관련 Skill을 반드시 찾아 실제 변경사항과 동기화한다.

6. Skill을 수정하면 해당 Skill과 연관된 다른 Skill을 찾아 영향도를 확인한다.

7. 서로 연관된 기능과 Skill은 함께 회귀 테스트한다.

즉 아래가 항상 같이 움직여야 한다.
Feature Code ↔ Skill ↔ Related Skills ↔ Regression Test

기능 코드만 변경되고 Skill이 갱신되지 않았다면 작업 완료로 간주하지 않는다.

