# Gate 진행 상태

## 다음 세션 인계 (2026-10-11 작성, 2026-10-12 갱신)

### 세션 시작 시 첫 확인
- `git fetch origin` 뒤 `git log -1`이 `origin/harness/setup` 최신 커밋과 같은지 확인한다. **다르면 다른 작업 전에 동기화(`git checkout -B harness/setup origin/<최신>` 등)부터 사용자에게 승인받는다.** 로컬에 미반영 커밋이 없는지 먼저 확인하고, 강제 push는 하지 않는다.
- 동기화했다면 에이전트·스킬 정의(`.claude/agents`, `.claude/skills`)가 세션 시작 시점의 옛 버전일 수 있다. **새 세션으로 다시 시작하도록 사용자에게 알린다**(이전 세션에서 로컬이 옛 커밋이라 정의 파일이 haiku였던 사례가 있었다).
- 작업 브랜치는 계속 `harness/setup`이다. `claude/sharp-goldberg-hzsd6c` 브랜치는 건드리지 않는다.

### 현재 상태
- **브랜치:** `harness/setup`. `main`에 직접 커밋·푸시하지 않는다. PR #2·#3은 `main`에 merge가 끝났다. merge된 PR에는 새 커밋이 붙지 않으므로 작업 단위가 끝나 `main` 반영이 필요하면 **새 PR**이 필요하다(요청받을 때만 만든다).
- **Gate ①** 승인. **Gate ②** 조건부 승인(보류 2건 아래). **Gate ③** 승인(FU-1 범위, 2026-10-11, `docs/decisions/03b` 6절). `04~08`은 모두 "상태: 승인(2026-10-11, 03b 6절)"로 기록돼 있고 합계 787줄이다(EW 결과 반영 뒤, FU-1 기준 약 800줄 이내). **Gate ④**는 대기이며 진입 전 환경 작업(EW)이 진행 중이다.
- **EW-1(앱 계정 분리) 완료·검증 통과**(QA 11항목 통과, reviewer 차단 0건, 아래 "EW-1 결과"). 목록 밖 추가 항목은 소급 승인됐다(2026-10-11, `CLAUDE.md` 변경 이력).
- 코드 상태: backend는 `bi_app`, migrate는 `bi_owner`로만 접속한다. revision은 `0001`(baseline, 의도적 no-op)과 `0002`(`bi_data` 권한)뿐이고 정적 표는 아직 없다. 인증 스텁 엔드포인트와 업무 기능 코드는 없다(`AUTH_STUB_ENABLED` 시작 거부 논리만 있음).
- **EW-3(Superset 계정·역할) 구현·검증 완료**: `superset-init`이 `migrate`·`db-bootstrap` 완료 뒤 `sync_permissions → ensure_roles → ensure_accounts`를 앱 컨텍스트 스크립트로 실행한다. 역할 `bi_service`(4)·`bi_guest_issuer`(2)·`bi_author`(Gamma 복사본, 처음에만)·`bi_author_schema`(1), 계정 `bi_service`·`bi_guest_issuer`(기본 이름). `.env.example` 30개(Secret 10개). backend는 설정 로딩만(HTTP 호출 코드는 FU-1e). `bi_guest`(권한 4개)와 `GUEST_TOKEN_VALIDATOR_HOOK`은 EW-4에서 구현됐다(아래 "EW-4 결과").

### 다음 할 일 (사용자 지시를 받은 뒤 이 순서로, 단위마다 보고하고 멈춘다)
1. ~~EW-1·EW-3·EW-4·EW-5·EW-6·EW-7~~ **모두 완료(2026-10-12).** EW-5~7 결과는 아래 "EW-5~7 결과"와 03b 13절. **사용자 확인 대기 항목이 있다(03b 13-3).** Gate ④ 진입(FU-1 착수)은 사용자 승인 뒤에 한다.
2. **FU-1로 이월(EW-4 결정):** 훅의 "포털 등록 표의 embedded uuid만 허용" 검사는 등록 표가 FU-1에서 생기므로 훅의 확장 지점(`superset/superset_config.py`의 `_EXTRA_GUEST_TOKEN_CHECKS`, 현재 빈 목록)에 FU-1e에서 넣는다. backend가 보내는 embedded uuid는 정규 형식(하이픈 있는 36자)이어야 훅의 uuid 형식 검사를 통과한다. 강제 복구 건수를 포털 점검 화면에 노출할지는 FU-1 단계에서 정한다(현재는 `docker compose logs superset-init`의 `경고:`·`점검 요약`으로만 확인). 발급 API 사용자별 429 속도 제한과 backend 시작 자가 점검(슈퍼유저·`CREATEROLE`·`CREATEDB` 거부, 03b BY3)은 FU-1a·1e 구현분이다.
3. **FU-1 착수(1a→1e):** 착수 때 AP-15(lark, 프런트 라우터, AG Grid Community, Superset Embedded SDK)를 버전·라이선스 확인 후 사용자에게 요청한다. 단위 구성은 `docs/decisions/04-modules.md`, 첫 단위부터 `feature-unit` 절차. **착수 전에 에이전트 모델 재판단**이 필요한지 사용자가 정한다(현재 7개 모두 sonnet, 호출 시 모델 변경 금지).
4. **이월:** EW-2(업로드 상한, `APP_UPLOAD_MAX_MB`, nginx `client_max_body_size`, `python-multipart`·`openpyxl`·`defusedxml`)는 엑셀 가져오기 단위에서 요청한다. 후속 기능 단위 목록은 04 끝의 절.
5. **main 반영:** PR #2·#3은 merge가 끝났다. 현재 `harness/setup`의 EW-3~7 변경을 `main`에 반영하려면 **새 PR**이 필요하다(요청받을 때만 만든다).

### 미결 항목
- **미결정 8번(포털 사용자 인증 방식):** 운영자 답 대기(`docs/operator-questions.md` 20개, 핵심 10개). 정해질 때까지 스텁 신원으로 진행하고, 운영 어댑터는 Gate ④ 중 교체한다. 각 방식의 새 환경변수는 정해질 때 따로 승인받는다.
- **Gate ② 보류 2건:** BAT 6종 실행 검증(사내 환경), Jenkinsfile의 Jenkins 실제 실행(`docs/deploy-coordination.md` 6번 확인 후). BAT는 `docs/windows-bat-verification.md` 기준으로 사용자 PC 검증을 요청한다(EW-1 이후 Secret 8개·`AUTH_STUB_ENABLED` 추가 반영됨).
- **운영 DB 슈퍼유저 문제:** db-bootstrap은 슈퍼유저 접속이 필요하다(역할·스키마·메타 DB 생성). 관리형 운영 DB에서 줄 수 없으면 DBA가 한 번 수행하는 대안이 필요하다(`deploy-coordination.md` 29번). 운영 DB `log_statement`가 `ddl`/`all`이면 비밀번호가 서버 로그에 남을 수 있어 확인한다. 35번(첫 관리자 생성 명령을 운영 서버에서 실행 가능한지), 36번(`AUTH_STUB_ENABLED` 운영 설정)도 운영자 협의 항목이다.
- **미검증 항목:** `FOR NO KEY UPDATE`·`FOR SHARE` 잠금과 굶음 시나리오(1b·1c 첫 시험), `ON CONFLICT DO NOTHING RETURNING`과 pg8000 `rowcount`, 실제 엑셀 클립보드 형식, 일부 차트 유형의 `bi_guest` 표시(P5: 6가지를 FU-1e에서 직접 시험), `superset-init` 구현 방법(A-22·A-26), Superset 경유 `statement_timeout`, 비밀번호 변경 후 Superset 연결 유지, 정적 표 권한 매트릭스(첫 실제 표 revision `0003` 이후 실제 표로 재확인).
- **04~08 3차 검토 미실시:** 2차 검토 반영분은 architect 자체 정합성 확인만 했다. `skills/admin-cleanup/SKILL.md`는 설계 문서 기준 초안이며 FU-1b·1d 구현 뒤 실제 DB로 검증해야 한다.
- 합성 샘플(`docs/samples/`) 기준 수치다. 실제 팀 데이터로 검증한 것이 아니다.

### 주의 사항
- **에이전트 모델:** 정의 파일(`.claude/agents/*.md`)대로 쓴다. 현재 7개 모두 sonnet이며 호출 시 `model`을 바꾸지 않는다. 이전 세션에서는 하네스가 정의를 캐시해 env-engineer가 haiku로 실행돼 중단하고 정의와 같은 `sonnet`을 명시해 다시 호출했다. 새 세션에서는 정의가 그대로 적용돼야 하며 호출 정보에 실제 모델이 나온다. 다르면 사용자에게 알린다.
- **사전 승인 규칙(2026-10-11 다듬음):** 사전 승인 필수 = 새 환경변수, 새 의존성, 운영 가이드 기준선과 다른 설정, 권한을 넓히는 변경, 에이전트 모델 변경. 적용 후 보고 허용 = 권한을 줄이거나 비밀·로그 노출을 막는 보안 강화 변경이며, 보고서에 "적용 후 보고 항목" 목록을 따로 표시한다. 상세는 `CLAUDE.md`, `.claude/skills/bi-wizard-dev/SKILL.md`.
- **파괴적 명령 금지:** `.env` 삭제, `rm -rf`, `git clean -fdx`, `git reset --hard`, `docker compose down -v`, `docker volume prune`, 일괄 삭제. 시험 정리는 이름을 명시한 `docker rm`/`docker volume rm`만 쓰고, 볼륨 `bi-wizard_postgres_data`와 이미지는 건드리지 않는다. QA는 사용자의 `.env`를 만들거나 바꾸지 않고 `_workspace/qa/`의 임시 env 파일과 전용 compose 프로젝트명을 쓴다. 비밀값은 문서·로그에 쓰지 않는다.
- **Docker:** 클라우드 세션에서 데몬이 꺼져 있으면 `dockerd`를 백그라운드로 직접 띄운다(`service docker start`는 ulimit 오류가 난 적 있음). BAT는 작성만 하고 실행 검증은 사용자에게 요청한다.
- **작업 폴더:** `_workspace/`는 git 제외이고 컨테이너와 함께 사라진다. 필요한 실험 기록은 `docs/research/`로 옮겼다(README 참조). 옛 문서가 가리키는 `_workspace/gate3/facts*.md`, `round*-options.md`는 보관하지 않았다. 새 시험은 `_workspace/`에서 하고 남길 것만 docs로 옮긴다.
- **커밋 규칙:** 한국어 메시지, 해당 Gate/EW 명시, 끝에 Co-Authored-By와 Claude-Session 줄(시스템 안내대로). `main`은 건드리지 않고 `harness/setup`에만 푸시한다.
- **라이선스:** 운영 런타임 의존성은 허용형(MIT·BSD·Apache·PSF)만. 개발·테스트 전용과 업스트림 이미지 내부의 LGPL·MPL은 수정·재배포하지 않으면 허용. GPL·AGPL·EUPL·비오픈소스는 금지. Gamma/`PUBLIC_ROLE_LIKE` 금지는 guest 역할에만 적용(작성자 역할은 Gamma 복사본).
- **먼저 읽을 문서:** `CLAUDE.md` → `docs/project-brief.md` → `docs/decisions/03b`(6절)·`03c` → `04~08` → `AGENTS.md`, `skills/local-environment/SKILL.md`.


### EW-3 결과 (2026-10-12, env-engineer 구현, qa-engineer 독립 검증 2회, reviewer 점검 2회, 차단 0건)
- **검증 통과(QA):** 새 설치(빈 볼륨)에서 `superset-init`이 `migrate` 완료 뒤 시작해 성공, 기존 볼륨 재기동·재실행 멱등, 서비스·발급·작성자 권한 시험(03c X-22·X-28 재현), 변조 복구, 비밀번호 변경 반영(특수문자 포함), 로그·`ps`·`docker inspect` 비밀번호 0건, `APP_PROXY_STRIP_PREFIX` true/false 동일, `superset-init` 메모리(최대 약 193MiB/1g), backend 설정 로딩 시험. 정적: `ci-validate-env.sh` 통과, `test-ci-validate-env.sh` 97개 실패 0, backend 테스트 129개 통과.
- **마지막(2차 수정) 변경분은 env-engineer 자체 컨테이너 시험 + 오케스트레이터 코드 확인으로만 검증했고 별도 QA 재실행은 하지 않았다.** 대상: `bi_author` 0개 복사 분기 제거, 역할 0개 기존 계정 표식 검사, 이메일 충돌 사전 거부, `sync_permissions` 대소문자 무시 조회, 문서 정정. EW-6 통합 검증에서 다시 확인한다.
- **미시험:** `migrate` 실패 때 `superset-init` 미기동(정적 확인만), 08 §2-1 0행 "USAGE 없이도 schema_access 생성" 실측 재현(구현자 실측만), 하위 경로 + Embedded 재검증(EW-4 몫), BAT 실행.


### EW-4 결과 (2026-10-12, env-engineer 구현, qa-engineer 독립 검증, reviewer 점검 차단 0건)
- **qa-engineer 12항목 통과(실패 0):** 새 설치·재기동 멱등, 역할 권한 수(bi_service 4, bi_guest_issuer 2, bi_author 95, bi_author_schema 1, bi_guest 4, Public 0), **6가지 차트(선·막대·표·큰 숫자·원형·혼합) 모두 `bi_guest` 입장권으로 임베딩 화면 정상 표시(추가 권한 요구 없음, 관리자 화면과 같은 값)**, 기간 필터(`can_time_range`) 동작과 제거 시 403·APPLY 비활성 대조, X-25 부정 시험 재현(목록·생성·수정·삭제·SQL Lab·내보내기·다른 대시보드·만료·변조·`alg=none`·틀린 aud 차단), 훅 거부(rls·리소스 0/2개·숫자 id·user 누락 등 400), 강제 복구(Admin·Gamma 부여 후 복구, 경고·`점검 요약`), 표식 없는 계정 충돌은 exit 1·불변, EW-3 2차 수정분 4가지 재확인, 불변 시험(목록 변조·PUBLIC_ROLE_LIKE·GUEST_ROLE_NAME·Public 권한 → 실패), `APP_PROXY_STRIP_PREFIX` true/false 동일, 로그·ps·inspect의 비밀번호·토큰 0건.
- **알려진 한계 재확인(08 §3-2):** 저장된 질의를 바꾼 chart/data 요청은 200(열 단위 접근 제어 불가, 방어선은 `bi_readonly`), 직접 서명 토큰은 훅을 우회(그래서 backend에 서명 키가 없다). `/datasets` 응답에 가상 데이터셋 SQL이 보인다(불변식 범위).
- **FU-1e 이월:** 위 "다음 할 일" 3번.
- **미시험:** 5분 넘는 SDK 자동 갱신과 사용자별 429(FU-1e 구현분), 브라우저 포털 화면(상태 코드까지만), BAT 실행.


### EW-5~7 결과 (2026-10-12)
- **EW-3 확인 3건 반영(03b 12-1):** `bi-review` 7-2에 두 항목 추가(입장권 유효 시간, 표식 계정에만 강제 복구)와 `CLAUDE.md` 이력, `superset-init`의 `GUEST_TOKEN_JWT_EXP_SECONDS` 적용값 300 가드, 표식 없는 기존 계정은 역할과 관계없이 거부(운영자 정리 절차는 `skills/local-environment/SKILL.md`).
- **EW-5(문서·하네스 정리):** 04~08에 EW-1·3·4 결과 반영(합계 787줄), `.claude/agents`·`.claude/skills` 낡은 문구 정리(D2·앱 계정·업로드 상한·9~11번 결정됨, Gate ④ 진입 조건), `CLAUDE.md` 변경 이력 갱신.
- **EW-6(qa-engineer 통합 검증, 미시험 이월 포함, 실패 0):** 빈 볼륨 새 설치 전체 기동(순서 postgres → db-bootstrap → migrate → backend / superset-init → superset → frontend, superset-init 약 81초), EW-1 재확인(슈퍼유저 접속 0건, 권한 매트릭스, statement_timeout psql 30.14초·Superset 경유 30.1초 취소, db-bootstrap 멱등, 왕복 테스트와 `alembic check`, 스텁 시작 거부), EW-3·4 재확인(역할·계정 멱등, 서비스·발급·작성자 권한), 새 가드 2건, 6가지 차트 임베딩(STRIP false/true 모두), 훅 거부, X-25 부정 시험 86·13·14개 동일, **이월 5건 확인**(`migrate` 없이도 `schema_access` 생성, `migrate` 실패 시 backend·superset-init·superset 미기동, `superset-init` 실패 시 `superset` 미기동, 5분 초과 SDK 자동 갱신 400초 확인, 비밀번호 변경 후 Superset 연결 유지), 로그·`ps`·`docker inspect`의 비밀번호·토큰 0건. `docker stats`: 상시 서비스 idle 합계 약 333MiB, 렌더 중 약 424MiB(8GiB의 약 5%), 한도 합계 4.75GiB(8GiB의 59%), OOMKilled 없음, `superset-init` 최대 약 213MiB.
- **EW-7(reviewer 최종 점검): 차단 0건.** 슈퍼유저 접속 없음, D3 예외 범위, Secret 로그 0건, 스텁 시작 거부 통과, 사전 승인 필수 범주의 승인 밖 변경 없음(새 환경변수 30개 모두 승인 목록에 근거 있음, 새 의존성 없음, 모델 7개 sonnet).
- **지적 처리:** 낡은 문구·상태 서술 정리(M1·M2), 적용 후 보고 항목 기록(M3, 03b 13절), `qa-verification` 정리 명령 수정, `bat` 검증 문서·08·deploy-coordination 갱신. **미처리(사용자 확인 대기, 03b 13-3):** `roles.sql`의 기존 `bi_app`·`bi_owner` 슈퍼유저 속성 재차단(R1), `superset` 컨테이너 종료 지연(exit 137), `superset-init` 컨테이너가 `unhealthy`로 표시되는 현상.


| Gate | 상태 | 승인일 | 승인 내용 | 관련 문서 |
| --- | --- | --- | --- | --- |
| ① RESEARCH & DECIDE | 승인 | 2026-10-11 | 디자인: C(3분할 작업공간) 기본 + 데이터셋 목록·권한 관리·가져오기 앞 두 단계는 B(콘솔형). 기준 해상도 1920×1080, Inspector는 접기·폭 조절. Reference 5개 모두 확보(지목 파일만) | `docs/decisions/01-design-direction.md`, `docs/decisions/02-tech-reference.md`, `references/` |
| ② ENVIRONMENT BOOTSTRAP | 승인(조건부) | 2026-10-11 | 마이그레이션 결정(D1~D7), 배포 환경 사전 제안, 읽기 전용 계정 제안, Gate ② 결과 결정 8건 반영 후 조건부 승인. **보류 2건:** BAT 6종 실행 검증(사내 환경에서 검증), Jenkinsfile CI의 Jenkins 실제 실행(Jenkins 실행 환경 확인 후). 보류 항목과 해소 시점은 아래 "Gate ② 보류 항목" | `docs/decisions/03-migration-tool.md`, `docs/decisions/03a-deploy-environment.md`, `docs/deploy-coordination.md` |
| ③ MODULARIZE | **승인** (FU-1 범위) | 2026-10-11 | FU-1 범위의 04~08 승인, 합계 함수 빈 칸 전파, 지원 차트 6가지, 에이전트 모델 3개 sonnet 변경, §9-2 제안·§10 기능 축소 승인, AP-1·2·5·9·10·11·12·13·14·16 승인(AP-15는 FU-1 착수 때 요청). 상세 `03b` 6절 | `docs/decisions/04-modules.md` ~ `08-superset-embedding.md` |
| ④ 기능 개발 | 대기 (진입 전 EW-1·EW-3~EW-7 완료·검증 통과, 사용자 확인과 FU-1 착수 승인 대기) | - | - | - |

## 미결정 사항 (브리프 5절)
| 번호 | 질문 | 상태 | 답변 |
| --- | --- | --- | --- |
| 1 | Azure OpenAI 항목 처리 | 결정됨(제외) | 제외 (2026-10-11, 사용자 결정). `.env.example`에서 Azure OpenAI 변수를 빼고 `/health/azure-openai`는 만들지 않으며, Environment Ready 체크리스트의 해당 항목은 "해당 없음" |
| 2 | 수식 범위 첫 버전 | 결정됨 (세부는 07) | 같은 행 계산, 이전 행 참조(누적합·증감), 같은 데이터셋 안 집계를 지원(Superset 차트로 대신 가능한 집계는 수식에서 제외 가능, 07에서 제안). 기준값은 "이름 + 값 + 적용 시작일" 기준값 표를 두고 수식에서 이름으로 부르며 행의 기준 날짜에 맞는 값을 쓴다. VLOOKUP식 키 매칭과 일반 데이터셋 사이 수식 참조는 첫 버전 제외. master 탭은 수식이 아니라 "공통 요약 양식"으로 구현. 데이터셋마다 "기준 날짜 열" 지정 필요(필수/권장은 2라운드 질문). (2026-10-11, 사용자 결정, `docs/decisions/03b-gate3-round-decisions.md`) |
| 3 | 새 데이터셋 생성 권한 | 결정됨 (세부는 06) | 팀(의뢰자)이 직접 만드는 것이 기본. "정의 담당자"(데이터셋 생성 + 열·수식 편집)와 "입력자"(데이터 입력만)를 분리. 팀 단위 소유이며 팀과 팀 소속은 포털 안에서 관리자가 지정하고 관리자는 팀·소속 관리를 맡는다. 인증된 포털 사용자는 모든 팀의 데이터와 계산 수식을 볼 수 있다(팀 단위 열람 제한 불필요). 기준값 표와 공통 요약 양식의 편집 권한은 관리자 기본안, 옵션은 2라운드 질문. (2026-10-11, 사용자 결정, 03b) |
| 4 | 팀 웹서버 Superset 운영 조건 | 결정됨 | 추가 컨테이너 운영 허용, Superset은 `compose.yml` 정식 서비스. Redis/Valkey 제외. 메인 플랫폼의 URL 하위 경로로 서비스. 메모리는 프로젝트 전체 합계 8GB로 시작(부족하면 증설 요청) (2026-10-11, 사용자 결정, `docs/decisions/03a-deploy-environment.md`). 배포 때 관리자와 맞출 항목은 `docs/deploy-coordination.md` |
| 5 | 디자인 방향 | 결정 | C(3분할 작업공간) 기본 + 데이터셋 목록·권한 관리·가져오기 앞 두 단계는 B(콘솔형) (2026-10-11, Gate ①) |
| 6 | 수식 미리보기·자동완성을 위한 저장 전 수식 평가 경로 | 결정됨 (세부는 07) | C0 정적 검사(문법·열 이름·타입·순환, 자동완성)를 기본으로, 값 미리보기는 C1-a(뷰와 같은 변환기로 원본 전체를 계산하고 일부 행 표시, 읽기 전용 트랜잭션 + 타임아웃). (2026-10-11, 2라운드 W7, 03b 2-3) |
| 7 | Superset 차트 작성 화면(Explore)을 포털에서 어떻게 제공할지 | 결정됨 | Superset 일반 화면을 새 창 링크로 열고 별도 로그인(8번 인증 결정 후 자동 연동을 목표로, iframe은 X-18 결과 후 판단). 각 팀 정의 담당자가 작성, 작성자 역할은 Gamma 복사본 + schema 보조 역할 (2026-10-11, 3라운드, 03b 3-1) |
| 8 | 포털 사용자 인증과 신원 출처 | 방식 미결정, 진행 방식 결정 | 인증은 `current_user` 한 곳으로 모으고 로컬에서는 스텁 신원으로 B 이후 라운드를 진행(U1 승인, 2026-10-11). 방식(헤더/토큰/자체 로그인/SSO)은 운영자 확인 후 결정하고 운영 어댑터는 Gate ④ 중 교체. 운영자 질문 20개는 `docs/operator-questions.md`(핵심 10개 표시), 사용자가 검토·전달. 새 환경변수는 각 방식이 정해질 때 따로 승인 |
| 9 | 동시 편집 정책 | 결정됨 | 행 편집은 칸 단위 값 비교 갱신, 붙여넣기·가져오기는 충돌 시 전부 취소, 정의 편집은 데이터셋 단위 직렬화 + 정의 버전 확인. 같은 기간 행은 기본 하나만(끌 수 있음), 기간 수정은 허용 + 확인창, 기준 날짜 열 타입 변경 금지 (2026-10-11, 3라운드, 03b 3-4) |
| 10 | Superset 데이터셋·대시보드 등록 방식 | 결정됨 | 데이터셋 등록·열 새로고침은 서버의 Superset 서비스 계정(읽기 쉬운 이름의 가상 데이터셋, `httpx`), 차트·대시보드는 사람, 임베드 켜기는 관리자 수동. 새 변수 `SUPERSET_SERVICE_USER`/`SUPERSET_SERVICE_PASSWORD` (2026-10-11, 3라운드, 03b 3-3) |
| 11 | 삭제 정책 | 결정됨 | 행·열·수식·데이터셋은 보관/사용 중지가 기본, 영구 삭제는 관리자만. 표·뷰 `DROP`은 보관 후 30일 뒤에만, 열 `DROP COLUMN`은 관리자 확인 후 즉시. 팀·사용자는 비활성화만, 참조 중인 값 삭제는 막지 않고 점검 화면 표시, 공통 지표·기준값 이름 완전 삭제는 관리자만 (2026-10-11, 3라운드, 03b 3-5) |

## Gate ② 결정 사항: DB 마이그레이션 (2026-10-11, `docs/decisions/03-migration-tool.md`)
| 번호 | 항목 | 상태 | 결정 |
| --- | --- | --- | --- |
| D1 | 마이그레이션 도구 | 결정 | Alembic |
| D2 | 동적 객체(사용자 데이터셋 테이블·수식 뷰) 분리 방식 | **결정 (Gate ③ 2라운드, 2026-10-11)** | **전용 schema 하나(S-1)**: 사용자 데이터 표와 수식 뷰는 `bi_data`(이름 상수)에, 포털 정적 표는 `public`에. 읽기 전용 계정은 schema 단위 기본 권한, 뷰 재생성은 서버 시작 시 정의 해시 비교(실패는 헬스 체크). 상세 03b 2-3·2-6. 그때까지 `DROP` 사용자 확인 안전장치는 유지 |
| D3 | 마이그레이션 raw SQL 허용 범위 | 결정 | 마이그레이션 디렉터리 안에서만 고정 SQL 문(`op.execute` 등) 허용, 변수 보간(f-string, `%`, `.format()`, `+`) 금지. 그 밖의 코드는 기존 SQL 문자열 조립 금지 규칙 · **예외 2(`backend/bootstrap/`)의 비밀번호 리터럴 범위가 앱 계정 비밀번호까지 확대(3라운드 승인, 식별자 보간 금지는 유지)** |
| D4 | 마이그레이션 실행 위치 | 결정 | backend 이미지를 재사용하는 일회성 `migrate` 서비스. `backend`는 `migrate` 성공 완료 후에만 시작(`depends_on`) |
| D5 | 되돌리기 정책 | 결정 | 모든 마이그레이션에 `downgrade` 작성, 빈 DB에서 upgrade → downgrade → upgrade 왕복 테스트. 운영 중 문제는 수정 마이그레이션 추가로 대응 · **3라운드 승인: 첫 실제 revision의 `downgrade()`가 `bi_data` schema를 지우지 않으므로 왕복 테스트는 "정적 표·권한 상태 복원" 기준(03-migration-tool.md 3라운드 반영)** |
| D6 | 빈 DB 검증 방식 | 결정 (Jenkins 적용은 추후) | tmpfs 테스트 전용 PostgreSQL 서비스를 compose profile로 정의(평소 미기동), 정리는 `-v` 없는 `docker compose down`. **Jenkins 적용은 Jenkins 실행 환경(Docker 사용 가능 여부) 확인 후 결정** |
| D7 | Superset 메타데이터 DB | 결정 | 같은 PostgreSQL 컨테이너 안의 별도 데이터베이스. Superset의 업무 데이터 연결은 읽기 전용 DB 계정 |

## Gate ② 진행 메모
- 마이그레이션 결정(D1~D7)과 사전 제안 6개가 모두 승인됐다(`docs/decisions/03-migration-tool.md`, `docs/decisions/03a-deploy-environment.md`). 승인 내용: 변수 `APP_BASE_PATH`·`SUPERSET_APP_ROOT`(예시 값 `/bi-wizard`, `/bi-wizard/superset`, "운영자 확인 필요" 표시), 포털의 프록시 접두 처리는 설정값만으로 전환(Superset은 접두 유지 전달), 로컬 검증은 frontend nginx가 메인 플랫폼 프록시를 재현, 메모리 배분과 Valkey 제외, Superset `6.1.0` 고정과 하위 경로 + Embedded 검증, 마이그레이션 디렉터리 `backend/migrations/`.
- 미결정 1번 "제외", 미결정 4번 "결정됨"이다. Azure OpenAI 변수·Health 경로·체크리스트 항목은 만들지 않고, Superset은 `compose.yml`의 정식 서비스이며 Redis/Valkey는 두지 않는다.
- **하위 경로 버그가 재현되면** Superset 내부 코드는 수정하지 않고, 대안과 각 영향을 정리해 보고한 뒤 멈춘다.
- **5MB 엑셀 샘플로 backend 메모리를 실측**해 보고하고(Gate ② 검증), 결과를 `docs/deploy-coordination.md` 5번에 기록한다.
- **읽기 전용 계정 제안 승인(2026-10-11):** 매 기동 멱등 `db-bootstrap`(`backend/bootstrap/`, `initdb.d` 미사용), D3 예외(비밀번호 리터럴의 psql `:'var'`만, 식별자 보간 금지. 2026-10-11 3라운드에서 앱 계정 비밀번호까지 포함하도록 문구 변경 승인), 이름 고정 `bi_readonly`/`superset_meta`/`superset`, 비밀번호 변수 `POSTGRES_READONLY_PASSWORD`/`SUPERSET_DB_PASSWORD`. 앱 계정은 Gate ②에서 `POSTGRES_USER`를 쓰며, 분리 조건은 아래 Gate ③ 인계 사항.
- **접두 처리 전환 변수 `APP_PROXY_STRIP_PREFIX` 승인:** 기본값 `false`(접두 유지 전달). Gate ② 검증에서 `true`/`false` 두 값 모두로 로컬 동작을 확인한다. 배포 협의 권장 사항은 `docs/deploy-coordination.md` 2번.
- **QA 환경 파일 규칙 승인:** QA는 `.env`를 만들거나 수정하지 않고 `_workspace/qa/`의 비밀이 아닌 더미 값 임시 env 파일을 `--env-file`로 지정한다.
- **현재 단계:** env-engineer ⇄ qa-engineer 구축·검증 단계 진행 중. 완료 후 Environment Ready 결과, `docker stats` 실측, 하위 경로 + Embedded 검증, BAT 검증 요청서를 보고한다.

## Gate ② 결과 (2026-10-11, 커밋 `4fbf7ad` 기준 qa-engineer 독립 재검증, reviewer 리뷰)
| Environment Ready 항목 | 결과 | 근거 |
| --- | --- | --- |
| `.env.example` canonical, 중복 없음 | 통과 | 26개(EW-1에서 `AUTH_STUB_ENABLED`, `POSTGRES_APP_PASSWORD`, `POSTGRES_OWNER_PASSWORD` 추가), Azure/Redis/Valkey/Celery 없음, `ci-validate-env.sh` 네거티브 18종 |
| `.env` Secret 보호 | 통과 | 추적 파일에 Secret 없음, `.env`/`.env.*` 무시(`!.env.example`) |
| backend·frontend·superset Dockerfile 빌드 | 통과 | test/build 타깃 포함 |
| compose 구성(healthcheck, volume, `mem_limit`, 순서) | 통과 | 8개 서비스, 합계 상시 4.75GiB/테스트 포함 6.875GiB, 태그 고정 |
| 시작·종료 | 통과 | `up`/`down`(-v 없음) 반복, 데이터와 계정 유지 |
| `migrate` 성공 후에만 `backend` 시작 | 통과 | 순서 시각 확인, `migrate` 강제 실패 시 backend 미시작 |
| Frontend ↔ FastAPI, Backend → PostgreSQL | 통과 | 포털 화면 API/DB 정상(HTTP 200) |
| Azure OpenAI 검증 경로 | 해당 없음 | 변수·`/health/azure-openai`(404) 없음 |
| db-bootstrap(멱등, 볼륨 유지, 비밀번호 변경, 빈 값 실패, 읽기 전용) | 통과 | 로그에 비밀번호 0건 |
| Superset 메타 DB 분리, 읽기 전용 연결 | 통과 | `superset` DB 소유 `superset_meta`, 등록 연결 `bi_readonly`, `allow_dml=false`, 명령줄·로그에 비밀번호 없음 |
| 마이그레이션 왕복(tmpfs, profile `test`) | 통과(제한) | upgrade→downgrade→upgrade 성공. baseline이 빈 revision이라 검증 범위는 `alembic_version` 기록뿐 |
| **하위 경로**(`APP_PROXY_STRIP_PREFIX` false/true 각각) | 통과 | 포털, API, Superset 로그인·화면 이동, 접두 밖 404, 재빌드 없는 전환 |
| **Embedded iframe** | **환경 검증 완료(하위 경로 + Gamma 대조 실험), 운영 역할은 Gate ③에서 정의** | 기본 guest 역할 `Public`에는 권한이 없어 `…/api/v1/me/roles/` 403이다. 하위 경로가 원인이 아니다(루트+Public도 실패, 하위 경로+Gamma는 성공). Gamma는 대조 실험에만 썼고 운영 설정에는 쓰지 않는다. 운영 역할은 최소 권한 커스텀 역할로 Gate ③에서 정의 |
| 메모리(`mem_limit`, 실측, 5MB 샘플) | 통과 | `docs/deploy-coordination.md` 5번 |
| BAT 6종 | 부분(보류: 사내 환경에서 검증) | 작성과 정적 검증 완료. 실행 검증은 보류(아래 "Gate ② 보류 항목") |
| Jenkinsfile CI | 부분(보류: Jenkins 실행 환경 확인 후) | 6단계 정적 확인, 각 단계 명령은 로컬에서 통과. Jenkins 실제 실행은 보류 |
| `skills/local-environment`, README, AGENTS.md | 통과 | 실행한 명령과 대조 |

## Gate ② 결과 결정 (2026-10-11, 사용자)
| 번호 | 항목 | 결정 | 반영 위치 |
| --- | --- | --- | --- |
| 1 | 사후 승인 | BAT 영문(ASCII) 변환, frontend·postgres·backend 포트의 `127.0.0.1` 게시, 변수 4개(`SUPERSET_SECRET_KEY`, `GUEST_TOKEN_JWT_SECRET`, `SUPERSET_ADMIN_USER`, `SUPERSET_ADMIN_PASSWORD`) 승인. 웹서버에서는 메인 플랫폼 프록시 위치에 따라 `FRONTEND_HOST`를 바꿔야 할 수 있다는 점을 배포 협의 목록에 추가. **하네스 규칙 신설:** 새 환경변수 추가, 운영 가이드 기준선과 다른 설정, 에이전트 모델 변경은 적용 전에 사용자 승인을 받는다 | `docs/deploy-coordination.md` 20번, `CLAUDE.md`, `bi-wizard-dev`, 에이전트 정의 |
| 2 | 에이전트 모델 | 정의 파일은 유지했다(당시 env-engineer, qa-engineer, frontend-dev는 haiku). **2026-10-11 Gate ③ 승인 때 세 에이전트를 sonnet으로 바꾸는 것을 승인했다(`CLAUDE.md` 변경 이력).** 호출 시 모델 변경은 사전 승인 없이 하지 않는다. 이번 Gate ② 호출 때 바꾼 에이전트와 사유는 보고했다. **Gate ④ 시작 전에 모델 판단을 다시 한다** | 아래 "모델 변경 기록", `CLAUDE.md` |
| 3 | Embedded guest 역할 | 최소 권한 커스텀 역할로 한다. 권한 목록은 Gate ③에서 데이터 모델과 함께 정한다. `Gamma`와 `PUBLIC_ROLE_LIKE`는 운영 설정에 쓰지 않는다. **이 금지는 임베딩 대시보드를 보는 guest 역할에만 적용(2026-10-11 3라운드 확정)**, 작성자 역할은 Gamma 복사본 + schema 보조 역할 | Gate ② 결과 표, Gate ③ 인계, `bi-review` |
| 4 | 로고 이중 접두 | 그대로 둔다(알려진 문제). 수정이 포함된 Superset 정식 릴리스가 나오면 버전을 올리고 하위 경로 검증을 다시 한다 | `docs/deploy-coordination.md` 13번 |
| 5 | Scarf | `superset_config.py`의 CSP에서 Scarf 호스트 제거, 효과 없는 `SCARF_ANALYTICS` 변수 삭제. 변경 후 Superset 화면과 임베딩(Gamma 대조 조건) 재확인 | `superset/superset_config.py`, `compose.yml`, `docs/deploy-coordination.md` 18번 |
| 6 | 라이선스 | "주의" 항목 모두 허용. 원칙: 운영 런타임에 포함되는 우리 코드의 의존성은 허용형만 사용한다. 개발·테스트 전용 도구와 업스트림 공식 이미지 내부 구성요소는 약한 카피레프트(LGPL, MPL)를 수정·재배포하지 않는 조건으로 허용한다. GPL·AGPL·EUPL 등 강한 카피레프트와 비오픈소스 라이선스는 위치와 관계없이 금지한다. 허용 목록은 "배포 전 회사 오픈소스 정책 확인"으로 기록 | `docs/project-brief.md` 4.1, `gate-research`, `bi-review`, `docs/deploy-coordination.md` 22~25번 |
| 7 | favicon | 포털 favicon 404 수정(`frontend/index.html`에 `data:,` 아이콘). Superset 404 오류 페이지 일러스트의 접두 누락은 알려진 문제로 기록 | `frontend/index.html`, `docs/deploy-coordination.md` 21번 |
| 8 | 볼륨 정리 | 시험용 볼륨을 이름을 지정해 삭제하는 것을 이번 한 번만 허용. `bi-wizard_postgres_data`는 삭제하지 않음. 이름 없는 볼륨은 어떤 컨테이너·메인 볼륨과도 연결되지 않은 것만 삭제. 일괄 삭제 명령 금지, 이미지 유지 | 아래 "볼륨 정리 기록" |

## Gate ② 보류 항목 (조건부 승인, 2026-10-11)
| 항목 | 상태 | 보류 사유 | 해소 시점 | 관련 문서 |
| --- | --- | --- | --- | --- |
| BAT 6종 실행 검증 | 보류(사내 환경에서 검증) | 개인 PC는 디스크 여유가 부족하고, BAT가 실제로 쓰일 사내 환경은 라이선스 문제로 Docker Desktop을 쓸 수 없어 개인 PC 검증의 실익이 작다(사용자 판단). 같은 동작의 `docker compose` 명령은 Linux에서 모두 검증했다 | 사내 워크스테이션으로 옮길 때 또는 팀 웹서버 배포를 준비할 때. 그 전에 사내 환경의 컨테이너 실행 방식(Podman, BAT 안의 `wsl` 경유 등)을 확인하고 필요하면 BAT를 그 방식에 맞게 고친다 | `docs/windows-bat-verification.md`, `docs/deploy-coordination.md` 26번 |
| Jenkinsfile CI의 Jenkins 실제 실행 | 보류(Jenkins 실행 환경 확인 후) | Jenkins 실행 환경(Docker 사용 가능 여부 등) 미확인 | `docs/deploy-coordination.md` 6번 확인 후. D6(마이그레이션 왕복 테스트의 Jenkins 적용)도 같이 정한다 | `Jenkinsfile`, `docs/deploy-coordination.md` 6번 |

### 재검증 결과 (결정 5·7 반영 후, 프로젝트 `envfix`, STRIP=false)
- Superset 컨테이너 기동 healthy, `superset_config.py` 로드 오류 없음(CSP `img-src`에 scarf 호스트 없음 확인).
- 포털: `/favicon.ico` 404 사라짐, 4xx·콘솔 오류 0건.
- Scarf: 브라우저가 낸 요청 13건이 모두 CSP에 막힘(전송 0건). Google Fonts 2건은 전송됨(막지 않음). 콘솔에 CSP 위반 경고가 남는다(예상된 부수 효과).
- Superset 화면(로그인, 홈, 대시보드·차트·데이터셋·DB 목록, SQL Lab, 대시보드 상세) 정상. 기존 알려진 404(로고 이중 접두, `service-worker.js`, 404 페이지 일러스트)만 남음.
- 기본 설정(guest 역할 `Public`)에서 Embedded는 기존과 같이 403으로 실패(예상). **Gamma 대조 실험**(시험 전용 override로 `GUEST_ROLE_NAME="Gamma"`, 커밋하지 않음)에서는 iframe에 대시보드가 표시되고 4xx 0건.
- `scripts/ci-validate-env.sh` 통과.

### 알려진 문제 (Gate ② 승인 후에도 유지)
- Superset 6.1.0 하위 경로: 로그인 화면 로고 이중 접두 404, 404 오류 페이지 일러스트 접두 누락, `service-worker.js` 404(이미지에 파일 없음). 기능 영향 없음. 수정 릴리스가 나오면 업그레이드와 하위 경로 재검증(`docs/deploy-coordination.md` 13·21번).
- Google Fonts 외부 요청은 막지 않았다(`docs/deploy-coordination.md` 18번).

### 모델 변경 기록
- 정의 파일 모델: env-engineer, qa-engineer, frontend-dev = haiku. 그 밖의 에이전트는 정의 그대로.
- 이번 Gate ② 구축·검증에서 호출 시 `sonnet`으로 바꾼 에이전트: **env-engineer, qa-engineer** (haiku → sonnet). reviewer는 정의 파일이 이미 sonnet이라 변경이 아니다. 사유: nginx 하위 경로 프록시, Superset 하위 경로, compose 의존 순서(db-bootstrap → migrate → backend) 등 구성이 복잡하고 독립 검증의 신뢰도가 필요했다. **이 변경은 사전 승인 없이 이뤄졌다**(사용자 지적, 2026-10-11). 앞으로는 적용 전에 승인을 받는다. frontend-dev는 아직 호출하지 않았다. 판단은 Gate ④ 시작 전에 다시 한다.

### 볼륨 정리 기록
이번 한 번에 한해 허용된 정리(2026-10-11). 이름을 지정해 `docker volume rm`만 썼고 일괄 삭제 명령과 이미지 삭제는 쓰지 않았다. 삭제 전 시험 프로젝트 `envfix`를 `-v` 없이 내렸고 컨테이너는 0개였다.
- **삭제 전:** 이름 있는 볼륨 8개(`bi-wizard_postgres_data`, `qaclean_`, `qafail_`, `qaspecial_`, `qafinal_`, `qaroot_`, `envfix_`, `envroot_` `postgres_data`)와 이름 없는 볼륨 6개(총 14개). 이름 없는 6개는 `docker ps -a --filter volume=<이름>` 결과 연결된 컨테이너 0개, 메인 볼륨과 다른 이름임을 확인했다.
- **삭제:** 시험용 7개와 이름 없는 6개(13개).
- **삭제 후 남은 볼륨:** `bi-wizard_postgres_data` 1개. 이미지는 그대로 유지(예: `bi-wizard-*:local`, `apache/superset:6.1.0`, CA 오버레이 태그 `python:3.12.15-slim-bookworm`, `node:22.23.3-alpine`).

## Gate ③ 진행 계획 (승인, 2026-10-11)
- **사실 확인:** researcher가 공식 문서·소스 원문으로 확인하고(`_workspace/gate3/facts.md`, 발췌는 `_workspace/gate3/sources/`), reviewer가 출처와 본문을 대조한다. researcher 정의는 "사용자 요청 시 어느 Gate에서든 공식 문서 사실 확인 가능"으로 고쳤다. reviewer는 웹을 읽지 못하므로 발췌 파일과 Superset 6.1.0 이미지에서 꺼낸 소스를 대조한다.
- **산출물:** `docs/decisions/04-modules.md`, `05-api-contract.md`, `06-data-model.md`, `07-formula-engine.md`, `08-superset-embedding.md`. 문서 사이 용어·필드 일관성은 reviewer 점검 기준이다.
- **미결정 8~11번 추가:** 8 포털 사용자 인증과 신원 출처, 9 동시 편집 정책, 10 Superset 데이터셋·대시보드 등록 방식, 11 삭제 정책.
- **결정 라운드:**

| 라운드 | 항목 | 비고 |
| --- | --- | --- |
| 0 | 공식 문서 사실 확인 | 결정 없음 (완료) |
| 1 | 8번(인증), B(3번 생성 권한), A(2번 수식 범위) | **결정 완료(2026-10-11, 아래 "Gate ③ 1라운드 결정")**. 8번 답이 늦으면 A를 먼저 진행하고, 8번에 의존하는 B와 이후 항목은 8번 답을 받은 뒤 진행 |
| 2 | C(6번 평가 경로), D2 | **결정 완료(2026-10-11, 아래 "Gate ③ 2라운드 결정")**. 둘 다 A 뒤. D2 하위 결정(뷰 재생성 방식, `bi_readonly` `SELECT` 부여 방식) 포함 |
| 3 | 앱 계정 분리, D(7번 Explore), 9~11번 | 앱 계정은 D2 뒤 |
| 4 | Embedded guest 역할 권한 목록, RLS `clause` 규칙, `CREATE VIEW` 리터럴 처리, 업로드 상한 | guest 역할은 7번과 D2 뒤 |
| 5 | 인계 설계 일괄 확인(`target_metadata`·`include_object`, 붙여넣기 파서 규격, 순환 검사 방식, Baserow 참고 범위)과 문서 초안 승인 | `target_metadata`는 D2와 앱 계정 뒤 |

- Gate ④ 시작 전: 앱 계정 분리 완료, 에이전트 모델 재판단.

### Gate ③ 1라운드 결정 (2026-10-11, 사용자) — 상세는 `docs/decisions/03b-gate3-round-decisions.md`
| 번호 | 항목 | 결정 |
| --- | --- | --- |
| U1 | 일정 | 인증은 `current_user` 한 곳으로 모으고 로컬 스텁 신원으로 B 이후 라운드를 진행. 팀 소속은 포털에서 관리하므로 메인 플랫폼 팀 정보에 의존하지 않음 |
| U2 | 운영자 질문 | `docs/operator-questions.md`에 20개 저장, 핵심 10개(1, 2, 5, 7, 8, 9, 13, 14, 15, 16번) 표시. 사용자가 검토해 직접 답하고 남은 것은 사용자가 운영자에게 전달 |
| U4 | 새 환경변수 | 각 방식이 정해지는 시점에 따로 승인 |
| U5, U6, B | 생성 권한 | 팀이 직접 만드는 것이 기본. 정의 담당자 / 입력자 분리. 팀 단위 소유, 팀·소속은 포털에서 관리자가 지정. 관리자는 팀·소속 관리. 인증된 모든 사용자가 모든 팀의 데이터와 계산 수식을 열람 |
| 새 요구 | 계산 근거 공개 | 데이터를 보는 사람이 각 계산 열의 수식도 볼 수 있어야 함 |
| A | 수식 범위 | 같은 행, 이전 행 참조, 같은 데이터셋 집계 지원 / 기준값 표(이름+값+적용 시작일, 이름으로 호출, 행의 기준 날짜로 값 선택, 과거 결과 보존) / VLOOKUP·일반 데이터셋 간 참조 제외 / master 탭은 "공통 요약 양식"(관리자가 공통 지표 정의, 팀이 최종값 열 연결, 포털이 모아 요약 데이터 생성, 합산·비교는 Superset) |
| U10 | 다중 데이터셋 | 차트 합치기 불필요, 한 대시보드에 나란히 배치. 공통 열(기준 날짜, 팀) 이름·형식 통일 방안 설계, Superset 필터 조건은 researcher 확인 |
| U11 | 참조 열 | 입력 검증용 참조 열을 첫 버전에 포함 |
| 이후 | U3, U8, U12, U13 | 계획대로 이후 라운드 |

**영향 정리(4라운드 I, G):** 열람 제한(RLS)이 필요 없으므로 guest token의 `rls`는 빈 목록으로 고정 가능하고(스키마상 빈 배열 통과, 런타임 확인 전), I는 `clause` 생성 규칙이 아니라 "`rls` 항상 빈 목록" 규칙과 강제 방법으로 줄어든다. G는 단일 최소 권한 커스텀 역할로 충분하며 `Public`은 계속 비운다. 권한 목록 확정은 런타임 실험이 필요하다. 자세한 내용은 03b 1-6.

**2라운드 열린 질문:** Q-R1 기준값 표·공통 요약 양식 편집 권한, Q-R2 기준 날짜 열 필수/권장.

### Gate ③ 2라운드 결정 (2026-10-11, 사용자) — 상세는 `docs/decisions/03b-gate3-round-decisions.md` 2절
| 번호 | 결정 |
| --- | --- |
| 업무 현실 | 팀 탭은 "행 = 항목, 열 = 월". 데이터 단위는 월이 가장 흔하고 일부 연, 최소 단위는 일(시각 없음). 5개 팀, 팀당 10개 이내(최대 약 50). 기준값은 숫자와 글자 모두 |
| 저장·입력 | "한 기간 = 한 행, 항목 = 열"로 고정. 입력 화면도 같음. 행·열 전환 보기는 첫 버전 제외(나중에 추가할 수 있게 설계를 막지 않음) |
| 이관 | ~~웹 밖의 명령줄 전처리 도구~~ → **4라운드(2026-10-11)에서 범위 제외**: 기존 팀 탭은 자동 변환하지 않고 새 시스템에서 데이터셋을 처음부터 다시 정의한다. 웹 가져오기는 "표 형태"만(유지) |
| 날짜 단위 | 데이터셋마다 날짜 단위(일/월/연) 속성, 기준 날짜는 기간의 첫날로 저장, 입력 화면이 단위에 맞게 표시·검증 |
| W1 D2 | 전용 schema 하나(S-1) |
| W2 | (a) schema 단위 기본 권한 부여 (b) 서버 시작 시 정의 해시 비교 후 재생성, 실패는 헬스 체크 |
| W3 | 이전 행·기준값·공통 요약 연결에 쓸 때만 기준 날짜 열 필수, 날짜만 저장 |
| W5 | 규모는 X-9 실험 조건. **기준값은 첫 버전부터 숫자와 글자 모두 지원(기준값마다 형식 지정, 수식 엔진이 형식 검사) — 추천안(숫자만)과 다른 결정** |
| W6 | 최종값은 기간 행마다 있는 값, 최종값 열 → 공통 지표 연결 유지 |
| W7 C | C0 + C1-a |
| W8 | 기준값·공통 지표 양식은 관리자, 최종값 연결은 팀 정의 담당자 |
| W9 | 추가만 가능(보존 조건 포함), 아직 쓰이지 않은 값은 관리자 정정 가능 |
| W10 | 입력 때 확인 + 점검 화면 |
| W11 | 3라운드로 미룸(D Explore와 함께) |
| W12 | 팀 열 자동 추가 + 날짜 형식 통일 (X-5 결과에 따라 날짜 열 이름 통일로 바뀔 수 있음) |
| 열람 정렬 | 전체 열람 유지, 포털 목록은 소속 팀 데이터셋 상단 정렬. 대시보드 팀 필터 기본값을 소속 팀으로 둘 수 있는지 3라운드 검토 |
| B | B1~B10 기본값 승인. B7 사실상 해당 없음, B9 기본값대로 |
| 실험 | X-1, X-2, X-5, X-7, X-8, X-9(5팀 × 10개), X-11, X-13 승인. 클라우드 세션 안에서만, 끝나면 이름 지정으로 정리(일괄 삭제 금지), 결과는 다음 보고와 `docs/decisions/03c-gate3-experiment-results.md` |

**3라운드:** F 앱 계정 분리, D(7번) Explore 제공 방식, W11 데이터셋 이름, 9 동시 편집, 10 Superset 등록 방식, 11 삭제 정책, 팀 필터 기본값.

**실험 결과(2026-10-11):** 승인된 8건을 모두 수행하고 시험 객체를 이름을 지정해 정리했다(볼륨 `g3x_postgres_data` 삭제, `bi-wizard_postgres_data` 유지). 상세는 `docs/decisions/03c-gate3-experiment-results.md`. 요약: DDL은 PostgreSQL 16.10에서 롤백된다(X-1), 읽기 전용 트랜잭션은 임시 객체 생성도 막는다(X-2), 값 선택 필터는 열 이름이 같아야 하고 날짜 필터는 열 이름이 달라도 차트에 시간 필터가 있으면 동작한다(X-5), 뷰 교체 DDL은 열린 읽기를 기다리고 그 뒤의 새 읽기를 막는다(X-7), backend와 Superset은 DB 시간대를 그대로 따르며 compose DB는 Asia/Seoul이다(X-8), 5팀×10개 규모에서 요약 뷰는 수십 ms이다(X-9), 열 타입 변경은 의존 뷰가 막는다(X-11), 뷰를 가상 데이터셋으로 한글 이름으로 등록할 수 있다(X-13).

### Gate ③ 2라운드 준비 (2026-10-11)
- **사실 확인(Q22, Q25~Q30, Q32~Q36):** researcher 2명이 확인하고 reviewer 2명이 원문과 대조했다(`_workspace/gate3/facts-db-r2.md`, `facts-superset-r2.md`, Git 제외). 모델 변경 없음.
- **핵심 사실:** 대시보드 값 선택 필터(팀 등)는 필터 설정의 열 이름을 각 차트 데이터셋에서 정확히 찾고 없으면 조용히 건너뛴다. 날짜 필터는 열 이름 없이 `time_range`만 보내고 각 차트의 시간 조건이 해석한다. 서로 다른 데이터셋 차트를 한 대시보드에 두는 데 코드상 제약이 없다. 물리 데이터셋에는 표시 이름 전용 필드가 없다. 확보한 PostgreSQL 문서에 DDL별 롤백 서술은 없다(런타임 실험 후보).
- **옵션 비교안:** `_workspace/gate3/round2-options.md` (C 평가 경로, E D2와 하위 결정 및 새 객체 위치, Q-R1, Q-R2, 공통 열 통일, 질문 W1~W12, 기본값 B1~B10, 실험 후보). reviewer가 3회 검토했다. 사용자 결정은 아직 없다.

### Gate ③ 0라운드 결과 (2026-10-11)
- **수행:** researcher 2명(DB 쪽, Superset 쪽)이 Q1~Q21을 확인하고, reviewer 2명이 2차에 걸쳐 원문과 대조했다. architect가 1라운드 옵션 비교안을 쓰고 reviewer가 2차에 걸쳐 검토했다. 모델은 정의 파일 그대로(sonnet)이며 변경하지 않았다.
- **근거 원문:** 공식 문서 호스트(postgresql.org, docs.sqlalchemy.org, superset.apache.org 등)는 세션에서 열리지 않았다. 대신 GitHub 원문(PostgreSQL REL_16_STABLE sgml, SQLAlchemy `rel_2_1_4`, Alembic `rel_1_20_0`, Starlette 1.7.0, uvicorn 0.54.0, FastAPI 0.143.0, Superset 6.1.0 태그, Flask-AppBuilder v5.0.2)과 PyPI sdist(openpyxl 3.1.5)를 내려받고, Superset 6.1.0 소스는 이미지에서 꺼내 `_workspace/gate3/sources/`에 두었다. WebFetch 발췌는 근거로 쓰지 않았다.
- **한계:** PostgreSQL 문서는 REL_16_STABLE(16.15) 기준이며 우리 버전 16.10과 마이너 차이가 있다. 확인하지 못한 항목(예: `CREATE VIEW`를 지명한 bind parameter 불가 문장, 기반 열 타입 변경의 뷰 영향, `CURRENT_DATE`의 시간대, embedded 최소 권한 집합, CSRF)은 `부분 확인`으로 남겼다. 일부는 런타임 실험이 필요하다.
- **산출물 위치(Git 제외, `_workspace/gate3/`):** `facts-questions.md`, `facts-db.md`, `facts-superset.md`, `round1-options.md`, `sources/`. 결정이 확정되면 `docs/decisions/04~08`에 근거로 옮긴다.


### Gate ③ 3라운드 결정 (2026-10-11, 사용자: "3라운드는 모두 추천안대로 확정")
상세 원문과 근거는 `docs/decisions/03b-gate3-round-decisions.md` 3절.

| 항목 | 결정 |
| --- | --- |
| 차트 작성 (D, Y3·Y4) | Superset 일반 화면 새 창 링크 + 별도 로그인, 8번 후 자동 연동 목표, iframe은 X-18 후 판단. 각 팀 정의 담당자가 작성. 작성자 역할은 Gamma 복사본 커스텀 역할 + schema 단위 보조 역할. **Gate ②의 "Gamma·PUBLIC_ROLE_LIKE 운영 금지"는 임베딩 대시보드를 보는 guest 역할에만 적용(명시).** 불변식: Superset에 등록된 데이터는 모두 공개 |
| 계정 분리 (F, Y1·Y2) | 역할 2개 `bi_owner`, `bi_app`. 승인: 빈 schema 생성을 db-bootstrap으로 이동(D5 의미 변경 포함), B10 변경(등록·물리 객체·권한 한 트랜잭션). `bi_readonly` 권한 부여 위치(Y1 ㄴ)는 X-14 후 재질문. 새 변수 `POSTGRES_APP_PASSWORD`, `POSTGRES_OWNER_PASSWORD`. `POSTGRES_USER` 의미 축소는 운영 가이드 기준선과의 의도적 차이(`deploy-coordination.md` 29번). D3 예외 2는 새 계정 비밀번호까지 포함하되 `backend/bootstrap/` 비밀번호 리터럴로 한정, 식별자 보간 금지 유지. 구현은 Gate ④ 진입 전 |
| Superset 등록·이름·필터 (Y5·Y6·Y7) | 데이터셋 등록·새로고침은 서버 서비스 계정, 차트·대시보드는 사람, 임베드 켜기는 관리자 수동. `httpx`, `SUPERSET_SERVICE_USER`/`SUPERSET_SERVICE_PASSWORD` 승인. 읽기 쉬운 이름의 가상 데이터셋. 팀 필터는 모두 같은 기본값으로 시작, 소속 팀 기본값은 X-21 후 재판단 |
| 동시 편집 (Y8·Y9) | 03b 3-4 참조 (칸 단위 값 비교, 전부 취소, 데이터셋 단위 직렬화, 기간 규칙, 기준 날짜 열 타입 변경 금지 = 브리프 4.3 기능 축소) |
| 삭제 (Y10~Y12) | 03b 3-5 참조 (보관 기본, 영구 삭제 관리자만, 표·뷰 DROP 보관 후 30일, 열 DROP COLUMN 관리자 확인 후 즉시) |
| 기본값·승인 (BY1~BY11, Y13) | BY1~BY11 모두 이의 없음(`TZ=Asia/Seoul` 유지, 날짜 열 이름 통일 안 함 + 작성자 안내문에 "차트에 시간 필터 필요"). 뷰 재생성 실패는 기존 `/health` 본문에 표시. D5 해석 변경 수용. 실험 X-14, X-15, X-17, X-18, X-20, X-21, X-22, X-23, X-24 승인(X-16 불필요, X-19는 8번 후). X-18에서 `frame_options`/CSP 변경이 필요해지면 결과와 함께 따로 승인 요청. 조건부 설정 변경(작성자 역할 `can_set_embedded`, `superset-init` 확장, backend의 `SUPERSET_APP_ROOT` 전달)은 필요해지는 시점에 내용과 이유를 보고하고 적용 |

**4라운드:** G guest 역할 권한, I RLS 규칙, J `CREATE VIEW` 리터럴, H 업로드 한도, 인계 설계.

### FU-1용 Gate ④ 전 환경 작업(EW) 계획 (제안, 2026-10-11, 실행 요청 아님)
03b 5-4에 따라 FU-1에 필요한 것만 넣었다. **EW-2(업로드 상한)는 엑셀 가져오기 단위로 이월.** 담당은 env-engineer(구현), qa-engineer(검증), reviewer(점검), 모델은 정의 파일 그대로이며 재판단은 제안만 한다(아래). 실행은 Gate ③ 승인 후 별도 요청으로 한다.

| 단위 | 내용 | 선행 | 승인·보고 시점 | 검증 |
| --- | --- | --- | --- | --- |
| EW-1 계정 분리 | db-bootstrap: `bi_owner`·`bi_app` 생성(비밀번호 리터럴 2개), 빈 `bi_data`(소유 `bi_owner`), `GRANT bi_app TO bi_owner WITH INHERIT TRUE, SET FALSE` 한 줄, (AP-5) `public` 스키마 `CREATE`를 `bi_owner`에 부여, (AP-9) `bi_readonly` `statement_timeout`. compose: `migrate`→`bi_owner`, `backend`→`bi_app`. `.env.example`·backend 설정·`ci-validate-env.sh`·`validate-env.bat`·Jenkinsfile Credential 매핑·README·`skills/local-environment`·`AGENTS.md`·`deploy-coordination.md` 갱신. 마이그레이션 틀: 정적 `MetaData` + `target_metadata` + `include_name`/`include_object` + `alembic check`/`alembic heads` 개수 검사, `test_migrations.py`의 D2 규칙·`get_heads()` 단정 갱신, 왕복 스냅샷 시험 틀. **인증 스텁 켜기 설정(AP-13 `AUTH_STUB_ENABLED` 후보)과 운영 판별 방식 확정**(승인 후 `.env.example`·시작 거부 시험은 FU-1a 코드와 함께) | 없음(03c X-14·X-15·X-29로 방식 확인) | 착수 요청, AP-5·AP-9·AP-10·AP-13, 모델 재판단 승인 | 권한 매트릭스 시험, 비슈퍼유저 접속, `bi_owner` 왕복, db-bootstrap 멱등·비밀번호 변경·빈 값 실패, `bi-review` 차단 확인 |
| EW-3 Superset 계정 | 서비스 계정 변수(`SUPERSET_SERVICE_USER`/`_PASSWORD`)와 발급 전용 계정 변수 2개(이름 확정), `superset-init` 확장(`sync_permissions` → 서비스 역할 4권한 → 발급 역할 → 작성자 역할[`bi_author` Gamma 복사본 + `bi_author_schema`] → 계정 멱등 생성), backend→Superset 내부 주소·`SUPERSET_APP_ROOT` 전달(AP-12) | EW-1, 08 승인, `superset-init` 구현 방법 확인(A-22·A-26) | 내용·이유 보고 후 적용, 변수 이름 확정 | 계정·역할 권한 시험(03c X-22·X-28 재현), 로그에 비밀번호 0건 |
| EW-4 guest 역할 | `GUEST_ROLE_NAME=bi_guest`, 권한 목록 파일(필수 3 + `can_time_range Api` 1, 조건부 2 기본 제외), 생성 스크립트(없는 권한이면 시작 실패, 생성 후 재읽기 비교), `GUEST_TOKEN_VALIDATOR_HOOK`(확인: `rls` 비어 있음·resource 1개 dashboard·임베드 uuid 일치), 불변 시험(`Public` 0개, `PUBLIC_ROLE_LIKE` 미설정), `bi-review` 7-2 확장(AP-1) | EW-3 | 08 승인 때 | 하위 경로 + Embedded 재검증(STRIP true/false), 부정 시험, 차트 유형 스모크 |
| EW-5 문서·하네스 | `CLAUDE.md` 변경 이력, `bi-review`(7-1 D3 예외 2·D5 문구, 7-2 확장, 7-4 AP-10), `env-bootstrap`·`backend-fastapi`·`modularize` 문구, `gate-status.md`, 04~08 확정본 | EW-1~4 | 승인된 변경만 | reviewer 점검 |
| EW-6 통합 검증 | qa-engineer: `docker compose config`, `ci-validate-env.sh` 네거티브 케이스, STRIP true/false, `docker stats` 재측정(DC 5번), 권한 매트릭스 | EW-1~4 | 결과 보고 | Environment Ready 재확인 |
| EW-7 reviewer | 슈퍼유저 접속 없음, D3 예외 2 범위, Secret 로그 0건, `httpx` 라이선스, 스텁 시작 거부 | EW-6 | 차단·중요 0건 | `bi-review` |
- 순서: EW-1 → EW-3 → EW-4 → EW-5 → EW-6 → EW-7. 이월: EW-2 업로드 한도(`APP_UPLOAD_MAX_MB`, nginx `client_max_body_size`, `python-multipart`·`openpyxl`·`defusedxml`)는 엑셀 가져오기 단위(FU-7)에서 요청. 앱 코드(시작 자가 점검, `/health` 필드, 스텁 시작 거부, 정적 `MetaData` 연결)는 FU-1a~ 단위의 backend-dev 몫이다.
- **에이전트 모델 재판단(제안만, 승인 전에는 바꾸지 않음):** ① EW-1 착수 전: env-engineer·qa-engineer(정의 haiku). EW-1은 권한·db-bootstrap·compose 의존 순서·권한 매트릭스가 얽혀 있어 sonnet이 안전하다는 판단 후보. 정의 파일 변경이 필요하고 승인이 필요하다. ② FU-1 착수 전: frontend-dev(정의 haiku)는 입력 그리드·붙여넣기 파서 상태 기계·수식 편집기·3분할 작업공간 복잡도에 비해 약할 수 있다는 판단 후보. backend-dev·architect·reviewer·researcher(sonnet)는 유지. 비용 영향은 호출 수에 비례(정량 근거 없음).

### Gate ③ 진행 방식 변경: FU-1 범위로 축소 (2026-10-11, 사용자)
상세 원문은 `docs/decisions/03b-gate3-round-decisions.md` 5절. **1~4절 결정은 모두 유효**하다.

| 항목 | 내용 |
| --- | --- |
| FU-1 포함 | 데이터셋 만들기(열 정의·검증·기준 날짜 열·날짜 단위), 팀·정의 담당자·입력자 권한(인증 스텁), 입력 그리드(한 기간=한 행, 붙여넣기, 칸 단위 동시 편집), 같은 행 수식·수식 보기·미리보기, Superset 데이터셋 등록(서비스 계정)·임베딩 대시보드 보기 |
| FU-1 제외(후속 단위) | 기준값 표, 이전 행 참조, 같은 데이터셋 집계, 엑셀 가져오기, 참조 열, 공통 요약, 보관·삭제 정책, 변경 기록 |
| 결정 | K2 팀 단위·여러 팀(브리프 4.3 열 권한 후속 미룸, 권한 화면 팀×사용자), K3 스텁(운영에서 켜지면 시작 거부, `bi-review` 7-5), K6 핵심 함수 + 같은 행 SUM + 열 구분 태그 조건 합산 + 함수 사전 구조, K7 미입력 유지·대소문자 무시·오류 칸 구별 표시, Z6 (가) + 완화책 3가지 + `bi_app` 실행 + 회귀 시험, K12 (나)(A-27 확인 후), K11 ㄷ 수동 계정, 미리보기·뷰 불일치 0건 합격 기준 |
| 04~08 | FU-1 범위만 약 800줄 이내, 후속 항목은 문서 끝 "후속 기능 단위에서 결정" 절에 나열 |
| EW | EW-1, EW-3, EW-4, EW-5, EW-6, EW-7만. EW-2(업로드 상한)는 가져오기 단위로. 모델 재판단은 제안만 |

### Gate ③ 3라운드 후속·4라운드 결정 (2026-10-11)
상세 원문과 근거는 `docs/decisions/03b-gate3-round-decisions.md` 4절.

| 항목 | 결정 |
| --- | --- |
| 3라운드 후속 | Z0: `bi_readonly` 읽기 권한은 마이그레이션에 유지 + db-bootstrap에 `GRANT bi_app TO bi_owner WITH INHERIT TRUE, SET FALSE` 한 줄 추가 승인. Z13: Superset 작성 화면은 새 창 유지. Z14: 팀 필터는 모두 같은 기본값 |
| G·I (Z1~Z5) | guest 권한은 최소 21개에서 X-25로 줄임, CSV·이미지 내보내기 불허. `superset-init`이 매 기동 멱등 생성, `GUEST_ROLE_NAME=bi_guest` 승인. guest token은 서버가 Superset 발급 API를 호출하고 발급 전용 새 Superset 계정(환경변수 2개 승인, `GUEST_TOKEN_JWT_AUDIENCE`는 필요할 때만), embedded uuid는 관리자 수동 입력. `rls`는 서버가 항상 빈 목록 + Superset 검증 훅(`superset_config.py` 설정 추가 승인). 유효 시간 기본 5분 |
| J (Z6·Z7) | Z6 기본값 "보류"(X-26 결과 후 (가) 내장 부품 + 검증 / (나) 별도 표 저장 중에서만 결정, (다) 금지 제외). Z7: 런타임 DDL은 SQLAlchemy 내장 구성요소만·한 모듈·`text()` 금지·객체 종류 허용 목록(표·뷰·인덱스·제약). `bi-review` 7-4 승인 |
| H (Z8~Z11) | 업로드 10MB, 새 환경변수 `APP_UPLOAD_MAX_MB` 하나로 공유, 로컬 nginx `client_max_body_size` 변경 승인. 전역 동시 1건 + 사용자당 1건, 행 100,000 / 열 100 / 셀 2,000,000 / 붙여넣기 5,000행, 발급 API 사용자별 속도 제한(429) 승인. 동기 처리 + 확정 때 재전송. 원본 파일은 이름·크기·해시 정보만 보관. 브리프 4.7 이탈 승인(pandas 미사용, openpyxl read-only) |
| 기본값·실험 | BZ1~BZ20 이의 없음. X-25~X-29 실행 승인. `tmpfs`/`mem_limit` 변경은 내용·이유 보고 후 적용 |
| 범위 변경 | 기존 엑셀 이관용 전처리 도구 제외(과거 자료 일괄 이관이 필요해지면 추가). U-1·U-2는 세션이 만든 합성 샘플(`docs/samples/`)로 대체하고 "실제 자료로 검증하지 않음"을 한계로 기록 |

## Gate ③ 인계 사항
Gate ① 원본 대조(`docs/decisions/02-tech-reference.md`)에서 나온 세 가지는 설계 전에 반영한다.
- **붙여넣기 파서의 따옴표 안 탭 처리:** react-datasheet-grid의 `parseTextPlainData`는 따옴표 안의 줄바꿈만 셀 내용으로 유지하고 **탭은 따옴표 안에서도 셀을 나눈다.** 한 줄짜리 따옴표 셀은 따옴표가 그대로 남는다. 그대로 이식하지 말고 탭·따옴표·`\r` 케이스를 요구사항과 테스트 기준으로 설계한다.
- **Baserow 순환 검사기의 f-string raw SQL:** `circular_reference_checker.py`는 SQL을 f-string으로 조립한다. SQL 문자열 조립 금지 원칙과 충돌하므로 알고리즘만 참고하고, 구현은 SQLAlchemy 표현식 또는 파이썬 그래프 탐색으로 설계한다.
- **Superset RLS `clause` 서버 미검증:** 서버는 `clause`를 검증하지 않는다(`api.py`의 TODO). `GUEST_TOKEN_VALIDATOR_HOOK` 검증 추가 여부와 `clause` 생성 규칙(정수 ID·화이트리스트 식별자, 문자열 값 처리)을 설계한다.

- **RLS `clause`와 `CREATE VIEW`의 SQL 문자열 렌더링 문제:** Superset guest token의 RLS `clause`는 SQL 문자열이고, 수식 속 문자열 리터럴이 뷰 정의(DDL)로 렌더링되는 지점이 생긴다. `CREATE VIEW`에 bind parameter를 쓸 수 없다는 근거는 2012년 메일링 스레드 요약뿐이다. **Gate ③에서 PostgreSQL 공식 문서와 SQLAlchemy 공식 문서로 근거를 확인한 뒤 설계한다.** 설계 전에는 확정하지 않는다.
- 수식 범위(2번)가 정해져야 `references/baserow/`에서 참고할 모듈 범위(lookup·집계 포함 여부)를 확정할 수 있다.
- **앱 계정 분리 (조건부 승인, 2026-10-11; EW-1에서 해소, 아래 "EW-1 결과" 참조):** Gate ②에서는 `POSTGRES_USER`(이미지 슈퍼유저)를 앱·migrate 계정으로 쓴다. 조건: (1) 최소 권한 앱 계정 분리는 Gate ③에서 D2와 함께 설계한다. (2) **Gate ④ 진입 전 분리 완료가 필수 조건**이다. (3) Gate ④에서 backend가 슈퍼유저로 접속하면 `bi-review`가 차단한다. (4) 계정을 나눌 때 `ALTER DEFAULT PRIVILEGES`의 `FOR ROLE` 생략 방식도 다시 정한다(생략하면 마이그레이션 실행 역할과 런타임 DDL 실행 역할이 같아야 하므로, 분리 시 어느 역할이 동적 객체를 만들고 `bi_readonly`에 어떻게 `SELECT`를 주는지 새로 설계).
- **D2 (동적 객체 분리 방식) 결정:** 데이터 모델과 함께 옵션(S 별도 schema, N 이름 규칙, R 등록 테이블 기반, D 별도 DB)을 비교해 사용자가 결정한다. 읽기 전용 계정(D7)의 동적 객체 `SELECT` 권한 부여 방식, 수식 → 뷰 변환 규칙 변경 시 기존 뷰 재생성 방식도 함께 정한다. 결정 전까지 자동 생성 초안의 `DROP`은 사용자 확인 없이 적용하지 않는다.
- **`bi_readonly` 권한 설계(QA 발견):** `default_transaction_read_only=on`은 세션에서 `SET`으로 풀 수 있는 안전장치일 뿐 방어선이 아니다. 실제 쓰기를 막는 것은 권한이다. Gate ③에서 `SELECT`를 부여할 때 `CREATE`나 쓰기 권한을 주지 않도록 설계에 명시한다.
- **왕복 테스트의 실질 범위(EW-1에서 해소: `0002`와 `python -m migrations.roundtrip`이 권한 상태 복원까지 검증):** baseline이 빈 revision이라 현재 왕복 테스트는 `alembic_version` 기록만 검증한다. 첫 실제 객체 revision에서 다시 수행하고 `downgrade()`를 실질 구현한다.
- **STRIP=true와 SPA 딥링크:** 접두 밖 루트는 정적 자산만 서빙한다. 플랫폼이 접두를 떼고 `/datasets/1` 같은 SPA 라우트를 넘기면 404가 된다. Gate ④에서 라우터를 넣을 때 STRIP=true에서만 루트 SPA fallback을 켤지 정한다.
- **Embedded guest 역할(구현·검증됨, EW-4·EW-6):** `bi_guest` 4권한(`superset/bi_roles.py`), 6가지 차트 임베딩 정상 표시, `Public` 0개, `Gamma`·`PUBLIC_ROLE_LIKE` 미사용(`bi-review`가 점검). 상세는 "EW-4 결과"와 03b 11절.
- **가져오기 구현 메모리:** 5MB 샘플 실측에서 openpyxl 일반 모드 265MB, read-only 45MB였다. 가져오기는 read-only 모드나 청크 처리를 쓰고 업로드 상한(5MB 이하 기준)과 동시 처리 수를 함께 정한다.
- **Alembic `target_metadata` 연결(EW-1에서 해소: `backend/app/db_metadata.py`로 연결됨):** 이전에는 `target_metadata=None`이라 `alembic revision --autogenerate`와 `alembic check`가 동작하지 않았다(D2가 정해지기 전에 `DROP`이 담긴 초안이 생기는 것을 막는 의도적 선택). EW-1에서 정적 모델 `MetaData`와 `include_object` 필터를 연결했다.
- **업로드 크기 상한:** 이 서비스가 다룰 데이터는 대용량이 아니고 현재 엑셀 파일은 5MB 이하다. Gate ② 검증에서 5MB급 샘플로 backend 사용량을 실측한 결과를 근거로 Gate ③에서 상한을 정한다. 프록시의 요청 본문 상한(`docs/deploy-coordination.md` 7번)과 맞춘다.
- **D6 Jenkins 적용:** Jenkins 실행 환경에서 Docker 사용 가능 여부를 확인한 뒤 정한다(Jenkinsfile의 초기 Stage에는 마이그레이션 왕복 테스트를 아직 넣지 않는다).
- **라이선스 점검 원칙(결정 6):** 새 의존성을 추가할 때 운영 런타임에 들어가는지, 개발·테스트 전용인지, 업스트림 공식 이미지 내부인지를 구분해 `bi-review`가 판정한다. 약한 카피레프트를 우리 코드의 운영 런타임 의존성에 추가하려면 사용자 확인이 필요하다.
- **Superset 업그레이드 조건:** 로고·일러스트 접두 수정이 포함된 정식 릴리스가 나오면 버전을 올리고 하위 경로(STRIP true/false)와 Embedded를 다시 검증한다(6.1.0 고정 결정 변경은 사용자 승인).

### Gate ③ 3라운드 실험 결과 (2026-10-11)
승인된 실험 X-14, X-15, X-17, X-18, X-20, X-21, X-22, X-23, X-24를 수행했고 시험 객체를 이름을 지정해 정리했다(컨테이너 `g3x14-pg`와 `g3x-*` 7개, 네트워크 `g3x_default`, 볼륨 `g3x_postgres_data`. 남은 볼륨은 `bi-wizard_postgres_data` 하나). 상세는 `docs/decisions/03c-gate3-experiment-results.md`. 요약: `FOR ROLE`로 기본 권한을 정하려면 상속(INHERIT) 멤버십이 필요하고 A1·A2·A3 세 방식이 모두 동작(X-14, Y1 ㄴ 재질문 입력), 설계한 2계정 구성의 권한 매트릭스가 의도대로(남는 위험: 정적 표 `DELETE` 가능, `bi_app`의 함수 생성, `bi_readonly`의 TEMP; X-15), 뷰 교체 `lock_timeout`은 대기 중인 DDL 뒤의 새 읽기를 그만큼 지연시키고 정의가 같아도 락 대기하므로 해시 비교로 건너뛰어야 함(X-17), 칸 단위 값 비교·전부 취소·정의 버전 확인이 동작하고 붙여넣기는 id 순서로 갱신해야 교착이 없음(X-24), 같은 origin이면 기준선 이탈 없이 일반 화면 iframe 가능(다른 origin은 Embedded 포함 차단; X-18), Gamma 복사본 작성자 역할 동작과 `can_set_embedded`의 소유권 무시(X-20), `native_filters` URL로 팀 필터 값 지정 가능(필터 id 맵 모양만; X-21), 서비스 계정 최소 권한 4개와 이름 변경 안전(X-22), 데이터셋 삭제는 차트가 있어도 막히지 않음(X-23).

### Gate ③ 3라운드 준비 (2026-10-11)
- **사실 확인(DB Q40~44, Superset Q46~51):** researcher 2명이 확인하고 reviewer가 원문과 대조했다(`_workspace/gate3/facts-db-r3.md`, `facts-superset-r3.md`, Git 제외). Q40, Q47, Q49, Q51은 "부분 확인"(미검증 항목 명시). `flask-talisman` 패키지 버전은 확인하지 못했다. 모델 변경 없음.
- **옵션 비교안:** `_workspace/gate3/round3-options.md` (F 앱 계정, D Explore 제공과 팀 필터 기본값, W11, 9, 10, 11, 실험이 바꾸는 이전 결정 표, 질문 Y1~Y13, 기본값 BY1~BY11). reviewer가 2회 검토했다. 사용자 결정은 아직 없다.
- **미승인 실험 후보:** X-14~X-24(권한 부여 방식, 계정별 권한 매트릭스, Superset 일반 화면 iframe, 작성자 역할, 팀 필터 주소 지정, 서버의 Superset 등록 흐름, 삭제 후 남는 것, 동시 편집 DB 동작 등). 질문 Y13에서 승인 여부를 묻는다.
- **상태:** 3라운드 질문 보고 후 사용자 결정 대기.

### Gate ③ 4라운드 실험 결과 (2026-10-11)
승인된 X-25~X-29를 수행했고 시험 객체를 이름을 지정해 정리했다(컨테이너 `g3x-*`, `g3x26-*`, `g3x27-*`, 네트워크 `g3x_default`·`g3x27-net`, 볼륨 `g3x_postgres_data`; 남은 볼륨은 `bi-wizard_postgres_data` 하나). 상세는 `03c`의 4라운드 절. 요약: **guest 최소 권한 3개 + 기간 필터 1개 + 조건부 2개로 충분**, 불필요 14개(X-25), 열 단위 접근 제어는 Superset에서 불가능(방어선은 `bi_readonly`), **발급 전용 계정 최소 권한 1~2개, `GUEST_TOKEN_JWT_AUDIENCE` 불필요, 검증 훅은 발급 API 경로에서만 호출되어 직접 서명은 우회**(X-28), **`CreateView` + `literal`은 정상 구성에서 안전하나 `standard_conforming_strings` 세션 고정·역슬래시 등 거부·`CAST` 리터럴 규칙이 필요**, 별도 표 저장(나)도 가능, `text()` 없이 런타임 DDL 가능(X-26), `alembic check` 구성과 2계정 왕복 테스트 성공, db-bootstrap의 `GRANT bi_app TO bi_owner` 반복 실행은 오류 없음(X-29), 10MB 상한 메모리 판정과 변조 파일 방어(강화 사전 검사 필수, 전역 동시 1건 사실상 필수, 프록시 기본 1m은 1MiB 초과 413)(X-27). backend 이미지에 `python-multipart` 없음(업로드 구현 때 의존성 승인 필요).

### Gate ③ 4라운드 준비 (2026-10-11)
- **사실 근거:** 새 사실 확인은 하지 않고 0라운드(Q9~Q12, Q1~Q8, Q16~Q20)와 3라운드(Q46~Q51) 사실, 3라운드 실험(03c)을 재사용했다. 상태 표기("부분 확인", 추정)는 그대로 옮겼다. 추가로 메인이 프로젝트 backend 이미지(SQLAlchemy 2.1.4)에서 `sqlalchemy.sql.ddl.CreateView`/`DropView`/`CreateTableAs`의 존재를 import로 확인했다(2라운드 E-9의 "내장 구성요소 부재" 전제 중 CREATE VIEW 부분이 바뀜, GRANT 구성자는 별도). 확인 후보 A-18~A-26은 researcher 확인 대기.
- **옵션 비교안:** `_workspace/gate3/round4-options.md` (G guest 역할 권한, I guest token 발급·RLS, J 수식 속 글자 상수와 `CREATE VIEW`, H 업로드 한도, 인계 설계 (a)~(g), 3라운드 후속 재질문 Z0(Y1 ㄴ)·Z13(Y3 (다))·Z14(Y7), 질문 Z1~Z12, 기본값 BZ1~BZ20). reviewer가 1회 검토했고 지적을 반영했다. 사용자 결정은 아직 없다.
- **미승인 실험 후보:** X-25(guest 역할 권한 이분 탐색), X-26(글자 상수 렌더링), X-27(가져오기 한도), X-28(입장권 발급 방식), X-29(`alembic check`·왕복 테스트 틀). 사용자 자료 요청: U-1(Excel 클립보드 샘플), U-2(익명화한 엑셀 샘플).
- **상태:** 4라운드 질문 보고 후 사용자 결정 대기.

### Gate ③ 5라운드 준비 (2026-10-11)
- **내용:** `_workspace/gate3/round5-options.md`(Git 제외): K-1 결정 총정리표(영역 9개, 약 100행), K-2 충돌·빈틈 39건, K-3 04~08 문서별 목차·기능↔Skill 대응·작성 순서, K-4 질문 K1~K13(하위 포함 약 26건)과 기본값 BK1~BK51·승인 필요 목록 AP-1~11, K-5 초안 작성 계획(S0~S9), K-6 Gate ④ 진입 전 선행 작업(EW-1~7), K-7 열린 항목. reviewer가 2회 검토했고 지적을 반영했다. 사용자 결정은 아직 없다.
- **정정:** 인계 설계 4건은 4라운드 BZ12~BZ14로 이미 승인되어 5라운드 범위에서 제외된다. 5라운드는 "설계 일괄 확인(K)"과 04~08 초안 작성 계획이다.
- **상태:** 5라운드 질문 보고 후 사용자 결정 대기. 04~08 초안은 아직 작성하지 않았다.

### Gate ③ 04~08 초안 (FU-1 범위, 2026-10-11)
- **파일:** `docs/decisions/04-modules.md`(212줄), `05-api-contract.md`(150), `06-data-model.md`(143), `07-formula-engine.md`(164), `08-superset-embedding.md`(106). 합계 775줄(800줄 이내). 모두 "상태: 초안(승인 전)". 후속 항목은 각 문서 끝에 항목만 나열.
- **작성 순서:** 04 골격·부록 A 용어 사전 → 06·07·08(병렬) → 05 → 04 마무리 → reviewer 교차 검토. 에이전트 모델 변경 없음(architect·reviewer=sonnet).
- **검토:** reviewer 2회(1차: 차단 0·중요 10·권장 20, 2차: 차단 0·중요 6·권장 10)를 모두 반영했다. 3차 검토는 하지 않았다(2차 반영분은 architect 자체 정합 확인만).
- **A-27 확인:** 조건부 가능(서비스 계정이 전체 열 교체 `PUT`으로 표시 이름 설정, `columns`는 병합이 아니라 교체). 03c A-27, 04~08에 반영 완료.
- **사용자 확인이 필요한 [제안] 모음:** `04-modules.md` §9-2. 승인 필요 통합 표: §9-1. 기능 축소 기록: §10.

## EW-1 결과 (앱 계정 분리, 2026-10-11)
- **구현:** db-bootstrap(`bi_owner`·`bi_app`, 빈 `bi_data`, `GRANT bi_app TO bi_owner WITH INHERIT TRUE, SET FALSE`, `bi_readonly` `statement_timeout=30s`, `alembic_version` 소유자 이전), compose(`migrate`=`bi_owner`, `backend`=`bi_app`, 슈퍼유저 변수 미전달), revision `0002_bi_data_privileges`(권한 전용, 실질 `downgrade`), 정적 `MetaData`·`include_name`/`include_object`, 왕복 도구 `python -m migrations.roundtrip`, `AUTH_STUB_ENABLED`(기본 false) + `APP_ENV` 명시·허용목록{local,test} 시작 거부, `ci-validate-env.sh` 규칙과 네거티브 62케이스.
- **QA 검증(HEAD 7b96176, 11항목 모두 통과):** 이미지 빌드·ruff·pytest 105, 기동 순서와 migrate 실패 시 backend 미기동, backend=`bi_app`·migrate=`bi_owner` 접속, X-15 권한 매트릭스 일치, `statement_timeout` 30.2초 실측 취소(AP-9 효과 확인), `alembic check`·왕복·heads 1개, 스텁 스위치(production/빈 값/미설정/`Local`/`staging` 거부, `local`/`test` 통과), Gate ② 볼륨 재현 후 재기동(데이터 유지, `alembic_version` 소유자 `bi_owner`, 0002까지 상승), 비밀번호 변경 반영, 빈 값 fail closed, 로그의 비밀번호 0건, Superset 회귀 없음.
- **reviewer:** 차단 없음. 중요 2건(CI 주석 제거 우회, 낡은 문구)과 경미 항목을 반영했다(`ci-validate-env.sh` 보강 후 최종 HEAD에서 `ci-validate-env.sh` 통과, 네거티브 62케이스 실패 0은 메인이 재실행 확인. QA의 전체 시험은 보강 전 커밋 기준).
- **한계:** 정적 표 매트릭스는 시험용 표로 재현했다(0001·0002에는 정적 표 없음. `0003` 이후 실제 표로 재확인). 보강 후 CI 스크립트 변경분 외 전체 QA 재실행은 하지 않았다. BAT 실행 검증과 Jenkins 실제 실행은 보류 그대로. Superset 경유 `statement_timeout`·비밀번호 변경 후 Superset 연결 유지는 미확인. backend 스텁 거부는 compose에서 재시작 반복으로 나타난다.
- **사용자 확인이 필요한 사항:** env-engineer가 목록 밖에서 추가한 것 — `scripts/test-ci-validate-env.sh`(신규), pydantic `hide_input_in_errors=True`, `AUTH_STUB_ENABLED`의 compose 필수 처리(기존 `.env`는 변수 3개 추가 필요), `roles.sql`의 `REVOKE ALL ON SCHEMA bi_data FROM PUBLIC`·`REVOKE CREATE ON SCHEMA public FROM PUBLIC`·`ALTER SCHEMA bi_data OWNER TO bi_owner`·`SET LOCAL log_min_error_statement = panic`. 모두 권한을 줄이거나 Gate ② 볼륨 호환용이며 새 변수·의존성은 없다. 운영 DB에서 슈퍼유저를 줄 수 없을 때의 대안은 `deploy-coordination.md` 29번 협의 항목.
