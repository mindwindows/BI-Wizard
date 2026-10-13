# FU-1 harness 운영 회고

작성일: 2026-10-13. 기준 커밋: `origin/main` `ab04245`(PR #5 병합 커밋, 내용 마지막 커밋 `b44abb7`).

**목적.** 이 프로젝트의 원래 목표인 "harness 에이전트 팀 구성·운영 학습"의 결과를 남긴다. 다른 계정이나 환경에서 다시 시작할 때 이 문서 하나로 운영 규칙을 복원할 수 있어야 한다.

**작성 원칙.** 저장소 기록(문서, 커밋, PR #5)에 근거가 있는 것만 적는다. 근거가 없으면 "기록 없음"이라고 쓴다. 추정은 적지 않는다. 규칙의 원문은 이 문서가 아니라 링크한 원문 위치가 기준이며, 이 문서와 원문이 다르면 원문을 따른다.

---

## 1. 운영 규칙 한 장 요약 (지금 유효한 규칙만)

### 1-1. 사전 승인 대상과 적용 후 보고의 경계
| 구분 | 내용 | 원문 |
| --- | --- | --- |
| 사전 승인 필수 | 새 환경변수, 새 의존성, 운영 가이드 기준선과 다른 설정, 권한을 넓히는 변경, 에이전트 모델 변경(호출 시 모델 변경 포함) | [CLAUDE.md](../../CLAUDE.md) 핵심 규칙, [03b 7-2](../decisions/03b-gate3-round-decisions.md) |
| 적용 후 보고 허용 | 권한을 줄이거나 비밀·로그 노출을 막는 보안 강화 변경만. 보고서에 "적용 후 보고 항목" 목록(변경 내용, 위치, 이유, 되돌리는 방법)을 따로 표시한다 | 같은 곳 |
| 경계 | 보안 강화라도 새 환경변수·새 의존성이면 사전 승인이 필요하다. 승인 목록 밖 추가는 구현 보고에서 따로 표시하고 사용자 확인을 받는다(소급 승인 사례 03b 7-1, "사용자 확인 대기" 절 9-3·11-3·13-3) | [03b 7-1·7-2](../decisions/03b-gate3-round-decisions.md) |
| 미결정 사항 | [브리프](../project-brief.md) 5절의 미결정은 임의로 정하지 않고 사용자에게 묻고, 답을 받은 뒤 진행한다 | [CLAUDE.md](../../CLAUDE.md) |

### 1-2. 파괴적 명령 금지 목록
`.env` 삭제, `rm -rf`, `git clean -fdx`, `git reset --hard`, `docker compose down -v`, `docker volume prune`, 일괄 삭제. 필요하면 먼저 사용자에게 묻는다. `docker volume prune`과 "일괄 삭제"는 [gate-status.md](../gate-status.md) 46행에만 있는 항목이다(CLAUDE.md·AGENTS.md 8절 목록에는 없음). 시험 정리는 이름을 명시한 `docker rm`/`docker volume rm`만 쓰고 볼륨 `bi-wizard_postgres_data`와 이미지는 건드린다고 gate-status 46행·[03b 27절 5](../decisions/03b-gate3-round-decisions.md)가 적었으나, [qa-verification](../../.claude/skills/qa-verification/SKILL.md) 금지 사항은 QA의 `docker volume rm` 자체를 금지한다(원문끼리 문구가 다르다. Gate ② 때 이름 지정 삭제는 "이번 한 번만" 허용됐다, gate-status 150행). 원문: [CLAUDE.md](../../CLAUDE.md), [AGENTS.md](../../AGENTS.md) 8절. 강제 push도 하지 않는다([gate-status.md](../gate-status.md) "세션 시작 시 첫 확인").

### 1-3. 비밀값 조건 (컨테이너 Env 등급 포함)
- 이미지(`docker image inspect`·`docker history`), 컨테이너 Cmd·Args, 로그, `ps`, 프런트 번들, 브라우저 저장소에는 비밀값 **0건**.
- **컨테이너 Env는 `.env`와 같은 보호 등급(호스트 Docker 권한자만 접근)으로 허용**한다. Env에는 compose가 변수로 넘기는 비밀번호가 설계상 들어 있다. 이전 보고의 "`docker inspect` 0건"은 Cmd·Entrypoint·Args 기준이었다.
- Docker secrets(파일 전달) 전환은 후속(새 `*_FILE` 변수는 승인 필요).
- 원문: [03b 28절 결정 2](../decisions/03b-gate3-round-decisions.md), [qa-verification](../../.claude/skills/qa-verification/SKILL.md) "최종 검증 규칙", [deploy-coordination.md](../deploy-coordination.md) 46번.

### 1-4. D3 규칙 (마이그레이션·bootstrap의 SQL)
- `backend/migrations/` 안에서만 고정 SQL 문 허용. **변수 보간(f-string, `%`, `.format()`, `+`) 금지.**
- 예외 2: `backend/bootstrap/roles.sql`에서 **비밀번호 리터럴(`PASSWORD :'var'`) 4곳**의 psql `:'var'`만 허용. 식별자 보간(`:"var"`, `format('%I')`)과 구문 보간은 금지. 비밀번호는 `\getenv`로 읽고 비면 실패(fail closed). 역할·DB·schema 이름은 상수 리터럴.
- 그 밖의 코드에서 SQL 문자열 조립은 어디서도 금지(SQLAlchemy 표현식). 런타임 동적 DDL은 SQLAlchemy 내장 구성요소만·`text()` 금지·객체 종류 허용 목록(`bi-review` 7-4).
- 원문: [03-migration-tool.md](../decisions/03-migration-tool.md), [AGENTS.md](../../AGENTS.md) 4절, [bi-review](../../.claude/skills/bi-review/SKILL.md), [gate-status.md](../gate-status.md) D3 행.

### 1-5. 브랜치·PR 규칙
| 규칙 | 근거 |
| --- | --- |
| `main`에 직접 커밋·푸시하지 않는다. 작업 브랜치는 `harness/setup`, `claude/sharp-goldberg-hzsd6c`는 건드리지 않는다 | [CLAUDE.md](../../CLAUDE.md), [AGENTS.md](../../AGENTS.md) 8절, [gate-status.md](../gate-status.md) |
| PR이 병합된 뒤에는 새 작업마다 `main` 최신에서 `harness/setup`을 다시 만든다(로컬에 미반영 커밋이 없을 때만) | [gate-status.md](../gate-status.md) "현재 상태" |
| PR 병합은 사용자가 한다(세션은 병합하지 않는다). PR을 만들기 전 `main`이 `harness/setup`에 포함되는지 확인한다 | [03b 27절](../decisions/03b-gate3-round-decisions.md) 결정 6, 이 세션의 사용자 지시 |
| **merge commit으로 병합, 병합 뒤 Delete branch 금지**(브랜치 `harness/setup`을 계속 쓰기 위함) | **저장소 문서에 규칙 원문 기록 없음.** 확인 가능한 사실은 `main`의 PR #2~#5 병합이 모두 `Merge pull request #N …` 병합 커밋 형태라는 것이다(병합 뒤 브랜치 잔존 여부는 저장소 기록에 없다). 규칙 자체는 이 세션의 사용자 지시에서 나왔다. 규칙 문서화는 "6. 다음에 다르게 할 점"에 올렸다 |
| 강제 push 금지, 로컬이 다르면 다른 작업 전에 동기화를 사용자에게 승인받는다 | [gate-status.md](../gate-status.md) "세션 시작 시 첫 확인", [03b 8절](../decisions/03b-gate3-round-decisions.md) |
| 커밋 메시지는 한국어, 해당 Gate/단위 명시, 끝에 시스템이 안내한 `Co-Authored-By`·`Claude-Session` 줄 | [gate-status.md](../gate-status.md) "커밋 규칙" |

### 1-6. 세션 시작 규칙
1. `git fetch origin` 뒤 `main`이 병합됐는지 확인한다. **새 세션은 `main`으로 시작해 `harness/setup`으로 전환하는 방식이 기본**이다(HEAD가 `origin/main` 최신인지, `git merge-base --is-ancestor origin/harness/setup origin/main`과 `git diff origin/harness/setup origin/main`이 비어 있는지 확인).
(PR 병합 뒤 기준 ref는 `origin/main`, [gate-status.md](../gate-status.md) 12행.)
2. 로컬이 `origin/harness/setup`과 다르면 다른 작업 전에 동기화를 사용자에게 승인받는다. 동기화했다면 `.claude/agents`·`.claude/skills` 정의가 세션 시작 시점의 옛 버전일 수 있으므로 **새 세션으로 다시 시작하도록 알린다.**
3. 읽는 순서: `CLAUDE.md` → `docs/project-brief.md` → `docs/gate-status.md`(다음 세션 인계) → `docs/decisions/03b`(15~28절) → `04~08` → `AGENTS.md`, `skills/local-environment/SKILL.md`.
4. 에이전트 정의 모델(7개 모두 sonnet)과 호출 정보에 나오는 실제 모델이 같은지 첫 호출 때 확인하고 다르면 사용자에게 알린다. 호출 때 `model`을 바꾸지 않는다.
- 원문: [gate-status.md](../gate-status.md) "다음 세션 인계"(세션 시작 시 첫 확인, 새 세션 시작 방법, 주의 사항).

### 1-7. 재검증 범위 규칙
- 최종 검증은 **마지막 커밋(해시를 보고에 적는다)** 기준으로 QA가 독립으로 돌린다: 실제 PG 전체 pytest(`REQUIRE_PG=1`, slow 포함, pg 변형 skip 0), 차분 전수, 프런트 전체, 실제 Superset 스모크(STRIP true·false), 비밀값 검사.
- **제품 영향 경로**(`backend/`, `frontend/`, `superset/`, nginx 설정, `compose.yml`, `Dockerfile`, 마이그레이션, `backend/bootstrap/`, 설정 파일)가 QA 뒤에 바뀌면 **전체 재검증.**
- 그 밖(`scripts/manual/`, `docs/`, 시험 보조 스크립트)만 바뀌면 **범위 재검증**: (1) 검증한 커밋..HEAD `git diff --stat`로 제품 영향 경로 0건 증명, (2) 바뀐 스크립트 실제 실행, (3) ruff·CI 검증 스크립트. 필요하면 항목 추가.
- 실패가 1건이라도 있으면 PR을 만들지 않고 멈춰 보고한다.
- 원문: [qa-verification](../../.claude/skills/qa-verification/SKILL.md) "최종 검증 규칙", [03b 27절 6, 28절 결정 1](../decisions/03b-gate3-round-decisions.md).

### 1-8. 커밋 전 자체 점검
누가 고치든(리드 포함) 커밋 전에 바뀐 `.py`는 `ruff check`와 `ruff format --check`(backend `pyproject.toml` 설정)를, 바뀐 프런트 파일은 lint와 typecheck를 직접 돌린다. `scripts/manual/` 같은 CI 밖 스크립트도 포함한다. 훅·설정 변경은 없는 문서 규칙이다. 원문: [bi-wizard-dev](../../.claude/skills/bi-wizard-dev/SKILL.md), [qa-verification](../../.claude/skills/qa-verification/SKILL.md).

### 1-9. QA 더미 env 규칙
QA는 사용자의 `.env`를 만들거나 수정하지 않는다. `_workspace/qa/`의 **비밀이 아닌 더미 값** 임시 env 파일을 `--env-file`로 지정하고 전용 compose 프로젝트명을 쓴다. BAT는 Linux에서 실행하지 않고 작성만 한다(실행 검증은 사용자 PC). 원문: [gate-status.md](../gate-status.md) "Gate ② 진행 메모"·"주의 사항", [qa-verification](../../.claude/skills/qa-verification/SKILL.md) 금지 사항, [CLAUDE.md](../../CLAUDE.md).

---

## 2. 규칙이 생긴 사건 목록 (사건 → 원인 → 바뀐 규칙)

| # | 사건 | 원인 | 바뀐 규칙 | 근거 |
| --- | --- | --- | --- | --- |
| 1 | 오래된 커밋에서 세션이 열려 에이전트 정의가 옛 버전이었다 | 새 세션이 `harness/setup`을 옛 커밋으로 여는 일이 반복됐다. 첫 하네스 커밋 `08c4ac0`의 정의 파일은 `env-engineer`·`qa-engineer`·`frontend-dev`가 `haiku`다(그 뒤 `sonnet`으로 승인 변경). **`08c4ac0`에서 세션이 열렸다는 사실 자체는 저장소 문서에 해시로 기록돼 있지 않다**(문서는 "로컬이 옛 커밋이라 정의 파일이 haiku였던 사례"라고만 적음) | 세션 시작 시 첫 확인(HEAD가 `origin/harness/setup` 최신인지), 새 세션은 `main`에서 시작해 `harness/setup`으로 전환, 동기화했다면 새 세션으로 재시작 | [gate-status.md](../gate-status.md) 6~8행, `git show 08c4ac0:.claude/agents/*.md` |
| 2 | 에이전트 모델 캐시: env-engineer가 `haiku`로 실행돼 중단하고 정의와 같은 `sonnet`을 명시해 다시 호출했다 | 하네스가 정의를 캐시했다(문서의 서술) | 호출 정보의 실제 모델을 정의와 대조하고 다르면 사용자에게 알린다. 호출 때 `model`을 바꾸지 않는다 | [gate-status.md](../gate-status.md) 43행 |
| 3 | 사전 승인 없는 변경 | (a) Gate ② 구축·검증 중 env-engineer·qa-engineer를 호출 때 `haiku`→`sonnet`으로 올렸다(사용자 지적, 2026-10-11). (b) 환경변수 4개와 포트·BAT 변경이 승인 전에 들어갔다. (c) EW-1에서 승인 목록 밖 항목(`hide_input_in_errors`, `REVOKE` 2줄과 `bi_data` 소유자 지정, `log_min_error_statement`, `AUTH_STUB_ENABLED` compose 필수 처리, `test-ci-validate-env.sh`)이 추가됐다 | 새 환경변수·운영 가이드 기준선과 다른 설정·에이전트 모델 변경은 적용 전 승인(Gate ② 결정 1), 그 뒤 EW-1 결과 검토에서 "사전 승인 필수 / 적용 후 보고 허용(보안 강화에 한함)"으로 다듬었다. 모델 변경은 정의 파일 변경을 사용자가 승인(AP-17) | [gate-status.md](../gate-status.md) 143·172행, [03b 7절](../decisions/03b-gate3-round-decisions.md), [CLAUDE.md](../../CLAUDE.md) 이력 |
| 4 | 서비스 계정 이름이 기존 사람·관리자 계정과 충돌하면 덮어쓸 수 있었다("탈취") | 원인은 **기록 없음**이다. 03b 9-2는 "사람·관리자 계정 덮어쓰기 방지" 검사를 적용 후 보고 항목으로 추가했다고만 적었고 "탈취"라는 단어는 기록에 없다. EW-3은 QA 2회·reviewer 2회를 거쳤고 그 반영 목록에 "대소문자 이름 충돌 거부"가 있다(`f8c495e` 커밋 메시지, gate-status 54행) | 대소문자 무시 이름 충돌 거부, 기존 계정 사전 검사(관리자·허용 밖 역할·표식 없는 역할 0개·이메일 충돌 거부). 이어서 EW-4에서 표식(전용 이메일·이름) 있는 계정만 강제 복구, EW-5에서 **표식 없는 기존 계정은 역할과 관계없이 거부**(비밀번호 재설정 없이 exit 1)로 확대 | [03b 9-2·10-1·12-1](../decisions/03b-gate3-round-decisions.md), `f8c495e` 커밋 메시지, [AGENTS.md](../../AGENTS.md) 2절 |
| 5 | QA 뒤 수정이 재검증 없이 넘어갔다(기록으로 확인되는 것은 EW-1, EW-3, 후보 1d 부분 실패 수정; 아래 2-1) | 수정 뒤 QA를 다시 돌리지 않고 자체 확인·코드 확인으로 대신했다 | 마지막 커밋 기준 QA 독립 전체 검증, 제품 영향 경로가 바뀌면 전체 재검증, 문서·스크립트만 바뀌면 범위 재검증(diff 0건 증명), 커밋 전 자체 점검 | [qa-verification](../../.claude/skills/qa-verification/SKILL.md), 아래 세부 |
| 6 | 비밀값 검사를 `docker inspect`의 Cmd만 확인하고 "0건"이라고 보고했다 | 이전 보고의 "0건"은 Cmd·Entrypoint·Args 기준이었다(03b 28절). 컨테이너 Env에는 compose가 넘기는 비밀번호가 설계상 있다 | 비밀값 조건을 대상별로 분리(이미지·Cmd·Args·로그·`ps`·번들·브라우저 저장소 0건 / Env는 `.env` 등급 허용)하고 이전 보고(1e-d·1e-f)를 정정 | [03b 28절 결정 2](../decisions/03b-gate3-round-decisions.md) |
| 7 | 최종 QA에서 보조 스크립트가 실패해 PR 없이 멈췄다 | `scripts/manual/superset-guest-list-check.py`가 입장권의 `iat`·`exp`를 정수로만 검사했는데 실제 값은 `300.0`(float)이었다. 제품 결함은 아니었다 | 재검증 범위를 제품 영향 경로 여부로 나눔(전체/범위), 컨테이너 Env 등급 결정, 커밋 전 자체 점검 | [03b 28절](../decisions/03b-gate3-round-decisions.md), `ddf8c0f`·`fcc8975` |
| 8 | 승인된 결정이 바뀐 뒤 하네스·문서에 낡은 문구가 남았다 | D2·앱 계정 분리·업로드 상한·9~11번 결정이 "Gate ③에서 정한다"로 남았다 | 결정이 바뀌면 같은 작업에서 `CLAUDE.md` 변경 이력과 관련 스킬·에이전트 문구를 갱신(EW-5 정리 단위가 따로 필요했다; EW-1에서도 낡은 문구 갱신 커밋 `eb74b76`이 있다) | [CLAUDE.md](../../CLAUDE.md) 2026-10-12 EW-5 행, [03b 13-1](../decisions/03b-gate3-round-decisions.md) |

### 2-1. "QA 뒤 수정의 미검증" 기록된 사례
요청 문구는 "3회"였다. 기록에서 **확인되는 것은 2회**이고, 세 번째 후보는 아래와 같다.
1. **EW-1**: 보강 뒤 CI 스크립트 변경분 외 전체 QA 재실행은 하지 않았다. 보강 후 `ci-validate-env.sh`·네거티브 62케이스는 메인이 재실행으로 확인했다(QA의 전체 시험은 보강 전 커밋 기준). 근거: [gate-status.md](../gate-status.md) EW-1 결과 "한계"(357~358행).
2. **EW-3**: 2차 수정분(`bi_author` 0개 복사 분기 제거, 역할 0개 기존 계정 표식 검사, 이메일 충돌 사전 거부, `sync_permissions` 대소문자 무시 조회, 문서 정정)은 env-engineer 자체 컨테이너 시험과 오케스트레이터 코드 확인으로만 검증했고 별도 QA 재실행은 하지 않았다. EW-6 통합 검증에서 다시 확인했다. 근거: [gate-status.md](../gate-status.md) 56행.
3. **후보: 1d 부분 실패 수정.** QA 재검증의 부분 실패 1건(긴 잠금 아래 문장 시간 초과가 422)은 "소규모 수정으로 처리"했다고만 적혀 있고(03b 20-1) 수정 뒤 QA 재실행 기록은 없다. 수정 커밋 `075c450`이 결과 기록 `17f91cd`보다 늦다(git log 순서). 세 번째 사례가 이것인지는 기록으로 확정할 수 없다.
- 참고: FU-1 최종 검증(`96a5974` 실패 → 수정 → 범위 재검증 `b44abb7` 통과)은 재검증이 이뤄졌으므로 미검증 사례가 아니다. 이 사건이 재검증 범위 규칙(1-7)을 만들었다.

---

## 3. 에이전트 역할별 관찰
에이전트 정의는 `.claude/agents/`(7개, 모두 `sonnet`). 아래는 기록에 있는 것만 적었다. "리드"는 메인 세션(오케스트레이터)이다.

| 에이전트 | 맡은 일 | 잘 된 점(기록) | 리드(또는 사용자)가 보완한 점(기록) |
| --- | --- | --- | --- |
| researcher | Gate ① 디자인·Reference 조사, 사용자 요청 시 공식 문서 사실 확인(Gate ③ 0·2·3라운드) | 2명 병렬로 Q1~Q21 등을 확인했고 reviewer가 원문과 대조했다([gate-status.md](../gate-status.md) 246행) | 공식 문서 호스트가 세션에서 열리지 않아 GitHub 원문·PyPI sdist·이미지에서 꺼낸 소스로 대체했다. "부분 확인" 항목을 명시로 남기고 일부는 런타임 실험으로 넘겼다(247~248행). 일부 패키지 버전(`flask-talisman`)은 확인하지 못했다(328행) |
| architect | 마이그레이션 도구 비교(Gate ②), 1·2라운드 옵션 비교안, 04~08 설계 문서 | 04~08을 FU-1 범위 약 800줄 이내(합계 775줄 초안, EW-5 뒤 787줄)로 작성 | reviewer 1차 지적(차단 0·중요 10·권장 20)과 2차(차단 0·중요 6·권장 10)를 반영. 2차 반영분은 3차 검토 없이 architect 자체 정합 확인만 했다(350행). 인계 설계 4건이 이미 승인돼 5라운드 범위에서 제외하는 정정이 필요했다(344행) |
| env-engineer | Gate ② 환경(compose·Dockerfile·BAT·Jenkinsfile), EW-1·3·4·5·8 | 계정 분리·Superset 계정·역할·검증 훅 구현을 QA와 반복 검증([gate-status.md](../gate-status.md) EW 결과 절) | 승인 목록 밖 추가가 반복돼 매번 "적용 후 보고 항목"으로 분리하고 사용자 확인을 받았다(03b 7-1, 9-2, 11-2, 13-2). EW-3 1차 수정의 권한 확대 분기(`bi_author` 0개면 Gamma에서 다시 복사)는 2차에서 제거했다(03b 9-2 정정). Gate ② 때 정의가 `haiku`였고 호출 때 `sonnet`으로 올려 쓴 사실은 사전 승인 없이 이뤄진 변경으로 기록됐다 |
| backend-dev | FastAPI 백엔드, 수식 엔진, 입장권 발급(1a~1e) | 1d 합격 기준 충족: 차분 시험 7,353개 수식 불일치 0, 주입 사례 회귀 고정([03b 20-1](../decisions/03b-gate3-round-decisions.md)) | reviewer 중요 지적(M1 렌더 문자열 실행 경로, M2 대조 순서, M3 `ROUNDUP` 정밀도, M5 거부 건수 단정)과 reviewer 지적은 수정 뒤 재확인으로 해소. QA 부분 실패(긴 잠금 아래 문장 시간 초과가 422)는 소규모 수정으로 처리(재검증 기록 없음). 연결 풀 고갈(5개 흐름 동시 열 추가)은 승인 필요라 사용자 결정으로 처리 |
| frontend-dev | React·AG Grid 화면, 붙여넣기 파서, 수식 편집기, Superset 임베딩 화면 | 붙여넣기 파서 `clipboard-cases.json` 42건, 화면 스크린샷을 `docs/screens/fu1/`에 보존 | 스크린샷에서 화면 문제 7건이 나와 수정(03b 19-1), 1e에서 화면 결함 보고(S9 좁은 칸 줄바꿈, 영어 403 본문 노출 등) 뒤 1e-f에서 수정. 모델은 `haiku`→`sonnet`으로 변경 승인(AP-17, 복잡한 화면 때문이라는 사유이며 정량 근거는 기록에 없음) |
| qa-engineer | 독립 검증(코드·테스트 수정 금지) | 최종 QA에서 보조 스크립트 float 실패 발견, 5개 흐름 동시 열 추가의 연결 풀 고갈 관찰, 빅넘버 헤더 40 vs 71.1k 차이를 같은 데이터로 확인하면 두 스택의 데이터가 달랐던 탓으로 확인(PR #5 본문) | QA가 코드를 고치지 않으므로 수정은 구현 에이전트·리드가 맡고 QA가 다시 검증하는 순환이 필요했다. 위 2-1의 사례가 이 순환이 생략된 곳이다(해석) |
| reviewer | 읽기 전용 점검(라이선스, 환경변수, Secret, SQL 조립, 사전 승인) | 기록이 있는 단위에서 차단 0건(Gate ② 리뷰의 차단 여부는 기록 확인 못 함), EW-7에서 새 환경변수 30개 모두 승인 근거와 대조, 모델 7개 sonnet 확인([gate-status.md](../gate-status.md) 71행) | 범위를 넘는 `bi-review` 규칙 확장 2건은 AP-1·AP-2 범위를 넘어 제거하고 사용자 승인으로 올렸다(03b 11-2 O1, 12-1). 웹을 읽지 못해 사실 확인 대조는 발췌 파일·이미지 소스에 한정됐다([gate-status.md](../gate-status.md) 181행) |

개별 에이전트의 응답 시간·토큰·호출 횟수는 **기록 없음.**

---

## 4. 수치 (기록에 있는 것만)

### 4-1. 단위별 검증·리뷰 라운드
| 단위 | QA | reviewer | 기록 위치 |
| --- | --- | --- | --- |
| Gate ① | 해당 없음(조사·교차검증) | 교차검증 수행(횟수 기록 없음) | 커밋 `39388d6` |
| Gate ② | qa-engineer 독립 재검증(`4fbf7ad` 기준, 횟수 기록 없음) | 리뷰(횟수 기록 없음) | [gate-status.md](../gate-status.md) "Gate ② 결과" |
| Gate ③ 0라운드 | — | researcher 2명 확인 후 reviewer 2명이 2차에 걸쳐 대조 | 246행 |
| Gate ③ 옵션안 reviewer 검토 | — | 1라운드 2차, 2라운드 3회, 3라운드 2회, 4라운드 1회, 5라운드 2회 | 243·329·338·343행 |
| Gate ③ 04~08 | — | 2회(1차 차단 0·중요 10·권장 20, 2차 차단 0·중요 6·권장 10), 3차 검토 미실시 | 350행 |
| EW-1 | 1회(11항목 통과) | 1회(중요 2건 반영) | 355~357행 |
| EW-3 | 2회(2차 수정분은 QA 재실행 없음, gate-status 56행) | 2회 | 54행, `f8c495e` |
| EW-4 | 1회(12항목 통과) | 1회(차단 0) | 60~61행 |
| EW-5~7 | EW-6 통합 검증 1회 | EW-7 최종 점검 1회(차단 0) | 67~71행 |
| EW-8 | 1회(실패 0) | 기록 없음 | 74행 |
| FU-1 단위 0 | 1회(실패 0) | 1회(차단 0·중요 4건 반영) | [03b 16-1](../decisions/03b-gate3-round-decisions.md) |
| 1a | 1회(실패 0) | 차단 0 | 같은 곳 |
| 1b·1c | 각 1회 + 1c 수정 뒤 pytest 1554 passed·프런트 361 passed(실행 주체 기록 없음; 독립 재검증은 03b 19-2에서 지시됐으나 결과 기록 없음) | 1b·1c 각 1회(차단 0) | [03b 18-1·19-2](../decisions/03b-gate3-round-decisions.md) |
| 1d | 1회 + 수정 후 8/9 항목 통과, 부분 실패 1건은 소규모 수정으로 처리(재검증 기록 없음) | 1차 + 수정 뒤 재확인(차단 0) | [03b 20-1](../decisions/03b-gate3-round-decisions.md) |
| 1e / 1e-f | 1e-d 1회(실패 0), 1e-f 1회(실패 0 + 관찰 1) | 1e 1회(차단 0·중요 1건) | [03b 24·26절](../decisions/03b-gate3-round-decisions.md) |
| 최종(FU-1 전체) | 전체 검증 `96a5974` 1회(실패 1: 보조 스크립트), 범위 재검증 `b44abb7` 1회(통과) | 기록 없음 | [03b 28절](../decisions/03b-gate3-round-decisions.md), PR #5 본문 |

"라운드"는 같은 단위에서 검증·리뷰·수정을 반복한 횟수를 뜻하지만, 단위별 반복 횟수를 일관되게 집계한 문서는 없다. 위 표는 문서에 횟수나 "N차"가 적힌 것만 모았다.

### 4-2. 검증 규모 (기록에 있는 시점별 값)
| 시점 | 백엔드 pytest | 프런트 vitest | 그 밖 |
| --- | --- | --- | --- |
| EW-1 | 105 | — | 네거티브 62케이스(CI 검증 스크립트) |
| EW-4 | — | — | `ci-validate-env` 시험 108개 |
| EW-8 | — | — | `ci-validate-env` 시험 116개 |
| 단위 0 | 165 | 43 | — |
| 1a | 629(pg 변형 포함) | — | — |
| 1b | 1194(실제 PG) | — | — |
| 1c | 1548→1554, skip 0 | 361 | 붙여넣기 파서 42건 |
| 1d | 2820(실제 PG), skip 98은 SQLite 전용 | 466 | 함수 cases 260, 차분 7,353 수식 |
| 1e 0단계 | 2861 | — | 차분 불일치 0·거부 296 |
| 1e-d | 3249 | — | 차트 6종 `bi_guest` 표시 |
| 1e-f | 3300 | 610(후속 614) | — |
| 최종 `96a5974` | **3310 passed**, skip 103(전부 SQLite 전용), pg 변형 skip 0 | **616 passed**, 빌드 뒤 static-checks 13 | 차분 전수 |

- 차분 시험(미리보기와 뷰 결과 대조) 규모: 수식 **7,353개**(통과 7,057, C0 거부 296), 데이터셋 79개, 비교 칸 **1,353,335**, 불일치 0, DB 예외 0([03b 20-1](../decisions/03b-gate3-round-decisions.md), PR #5).
- 메모리: 상시 서비스 idle 합계 약 333MiB, 렌더 중 약 424MiB(EW-6); 최종 합계 최대 약 0.59GB(`mem_limit` 합계 4.75GiB, 예산 8GB). PG 연결 실측 최대 22([deploy-coordination.md](../deploy-coordination.md) 45번).
- 연결 풀 상향 효과: 5개 흐름 동시 열 추가 503이 풀 5에서 23~26건 → 풀 10+5에서 0건(PR #5 본문).
- PR #5: 커밋 73개, 변경 파일 393개, +57,308/−173(GitHub PR 메타데이터). 병합 커밋 `ab04245`는 `origin/main` 기준.
- `superset-init` 소요: 새 설치 약 70~77초, 재기동 약 68초(03b 9-3), EW-6에서 약 81초.

### 4-3. 소요 시간
- 전체 기간(커밋 시각 기준): 첫 하네스 문서 커밋 `41226cd` 2026-10-11 08:13(KST) ~ PR #5 병합 2026-10-13 21:05(KST, 병합 커밋 `ab04245`). PR #5는 2026-10-13 11:36 UTC 생성, 12:05 UTC 병합.
- 최종 검증 구간의 커밋 시각(UTC): 전체 검증 대상 `96a5974` 06:36 → 수정 `ddf8c0f` 10:20 → `fcc8975` 11:27 → 인계 갱신 `b44abb7` 11:27. 이 시각 차이에는 QA 실행뿐 아니라 보고·사용자 결정 대기가 섞여 있다.
- **전체 재검증과 범위 재검증 각각의 소요 시간은 기록 없음.** 장비·실행 시간 로그를 문서나 PR 본문에 남기지 않았다.

---

## 5. 다른 환경에서 다시 시작하는 체크리스트
출처: [claude-code-cloud-harness.md](../claude-code-cloud-harness.md)(Docker 데몬 항목은 [gate-status.md](../gate-status.md) 47행). 해당 문서의 "다음 단계" 체크박스 4개는 모두 미체크 상태이며, 과거 실제로 수행한 결과는 **기록 없음**이다.

### 5-1. 환경 준비
- [ ] GitHub에 저장소를 먼저 만들고(클라우드 Claude Code 안에서는 새 저장소를 만들 수 없다), 사용 계정에 **Claude GitHub App**을 설치한다(저장소 범위는 선택 저장소로 한정 가능). 회사 계정으로 옮기면 GitHub 로그인 버튼 노출(조직 Owner의 GitHub 커넥터 설정)과 조직 정책의 클라우드 세션 허용 여부를 확인한다.
- [ ] 클라우드 환경 변수에 `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`을 추가한다(harness가 의존하는 agent teams가 기본 꺼져 있다). 변경은 새 세션부터 적용된다.
- [ ] 네트워크 수준 확인(기본 Trusted는 허용 목록만). 추가 패키지는 환경 설정의 Setup script에 넣어야 다음 세션에도 유지된다.
- [ ] 세션 VM은 Linux이므로 BAT는 작성만 하고 실행 검증은 사용자 PC에서 한다. 데몬이 꺼져 있으면 `dockerd`를 백그라운드로 직접 띄운다(`service docker start`는 ulimit 오류가 난 적 있음).

### 5-2. harness 스킬·에이전트 복사
- [ ] `revfactory/harness`의 `skills/harness`를 `.claude/skills/harness/`로 복사해 커밋한다(`/plugin` 경로는 클라우드 세션에서 쓸 수 없다).
- [ ] 이 저장소의 `.claude/agents/`(7개: architect, backend-dev, env-engineer, frontend-dev, qa-engineer, researcher, reviewer)와 `.claude/skills/`(backend-fastapi, bi-review, bi-wizard-dev, env-bootstrap, feature-unit, frontend-react-aggrid, gate-research, harness, modularize, product-skill-authoring, qa-verification)를 가져가고 에이전트 정의의 `model:`을 확인한다(전부 `sonnet`).
- [ ] `CLAUDE.md`(진입점 + 변경 이력), `docs/gate-status.md`(다음 세션 인계), `docs/project-brief.md`, `AGENTS.md`를 함께 옮긴다.
- [ ] 커밋 후 새 세션을 연다(정의는 세션 시작 시점 버전이 적용된다).

### 5-3. 세션 시작 메시지 예시
이 세션 시작 지시를 줄인 것이다(원본은 저장소에 없어 대조 불가. 형식은 "CLAUDE.md와 docs/gate-status.md의 '다음 세션 인계'를 먼저 읽고 시작").
```
CLAUDE.md와 docs/gate-status.md의 "다음 세션 인계"를 먼저 읽고 시작해 주십시오. 이번 세션의 범위는 <한 단위>입니다.

## 0. 시작 확인
- main에서 시작했는지 확인. git fetch 뒤 origin/harness/setup이 origin/main에 포함되는지(merge-base --is-ancestor)와
  diff가 비어 있는지 확인. 맞으면 git checkout -B harness/setup origin/main 후 push(fast-forward만, 강제 push 금지).
  하나라도 다르면 멈춰 보고.
- 에이전트 정의 모델(전부 sonnet)과 실제 보고 모델이 같은지 첫 에이전트 호출 때 확인.
## 보고
- 새 환경변수, 새 의존성, 기준과 다른 설정, 권한 확대가 필요해지면 그 자리에서 멈춰 주십시오.
```
- 최소 동작 확인: `docs/claude-code-cloud-harness.md`의 예시 "docs/claude-code-cloud-harness.md 를 먼저 읽고 시작해."

---

## 6. 다음에 다르게 할 점 (근거 있는 것만)
| # | 내용 | 근거 |
| --- | --- | --- |
| 1 | 새 세션은 `main`에서 시작해 `harness/setup`으로 전환하는 것을 기본으로 한다(옛 커밋 세션이 반복됨) | [gate-status.md](../gate-status.md) 8행 |
| 2 | 승인 목록 밖 추가를 구현자가 처음부터 "적용 후 보고 항목"으로 분리해 보고하게 하고, 사전 승인 필수 범주(새 변수·의존성·권한 확대·모델 변경)는 구현 전에 묻는다 | 03b 7-1·7-2, 9-2, 11-2, 13-2(매 단위 반복) |
| 3 | QA 뒤 수정은 반드시 범위(전체/범위)를 먼저 판정하고, 전체 재검증이 필요한데 생략하는 일이 없게 한다. 보고에 검증 커밋 해시를 쓴다 | 위 2-1 (해석 포함), [qa-verification](../../.claude/skills/qa-verification/SKILL.md) |
| 4 | 비밀값 보고는 대상(이미지, Cmd·Args, Env, 로그, `ps`, 번들, 브라우저 저장소)을 나눠 쓴다. "inspect 0건" 같은 뭉뚱그린 문구를 쓰지 않는다 | 사건 6 |
| 5 | 커밋 전에 `ruff check`·`ruff format --check`를 누가 고치든 돌린다(CI 밖 스크립트 포함) | [bi-wizard-dev](../../.claude/skills/bi-wizard-dev/SKILL.md) |
| 6 | 결정이 바뀌면 같은 작업에서 `CLAUDE.md` 변경 이력과 스킬·에이전트 문구를 갱신해 낡은 문구가 남지 않게 한다(EW-5 정리 단위가 별도로 필요했음) | 사건 8 |
| 7 | QA 비교 실험(예: 빅넘버 헤더)은 같은 시점·같은 데이터의 스택으로 비교한다 | PR #5 본문(40 vs 71.1k는 두 스택의 데이터가 달랐던 탓) |
| 8 | "merge commit 병합, 병합 뒤 Delete branch 금지"를 `CLAUDE.md` 또는 `gate-status.md`에 규칙으로 기록한다(지금은 저장소 문서에 원문이 없다) | 1-5 표 |
| 9 | 8번 인증은 `current_user` 한 곳으로 모아 스텁으로 진행한다(운영 어댑터는 후속에서 교체) | [gate-status.md](../gate-status.md) 미결정 8번(93행) |

기록에 근거가 없어 적지 않은 것: 모델별 비용 비교, 에이전트별 호출 횟수·시간, 단위별 일정 대비 실적.
