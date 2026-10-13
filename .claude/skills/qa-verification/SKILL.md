---
name: qa-verification
description: BI-Wizard의 검증 절차. docker compose 정적 검사, 기동과 Health 검증, 프런트·백엔드 응답 구조 대조, Skill 동기화 확인을 수행한다. Docker 데몬이 꺼져 있으면 세션 안에서 먼저 시작을 시도하고, 그래도 안 될 때만 사용자 PC 검증으로 넘긴다. qa-engineer가 사용한다.
---

# qa-verification — 검증 절차

## 원칙
- 검증 결과는 통과, 실패, 미실행으로 나누고 근거를 붙인다. 실행하지 않은 항목을 통과로 쓰지 않는다.
- 수정은 하지 않는다. 실패는 담당 에이전트에게 넘긴다.
- 모듈이 끝날 때마다 바로 검증한다.

## 1단계: 정적 검증 (Docker 데몬 없이 가능)
```bash
docker compose config
```
- 백엔드, 프런트엔드 lint와 단위 테스트를 실행한다. 명령은 각 프로젝트의 `README.md`와 `Jenkinsfile`을 따른다.
- 결과를 표에 적는다.

## 2단계: Docker 데몬 확인과 시작

### 2-1. 확인
```bash
docker info
```
정상이면 3단계로 간다.

### 2-2. 세션 안에서 시작 시도
데몬이 꺼져 있으면 먼저 세션 안에서 시작을 시도한다. 사용자 PC로 넘기기 전에 반드시 해 본다.

```bash
mkdir -p _workspace/qa

# 1) 서비스 방식
sudo service docker start

# 2) 직접 실행 (1)이 실패할 때)
sudo dockerd > _workspace/qa/dockerd.log 2>&1 &
```
- 시작 후 몇 초 기다렸다가 `docker info`를 다시 실행한다.
- 실행 로그는 `_workspace/qa/dockerd.log`에 남긴다. 시작 시도 명령과 결과를 보고에 적는다.
- 데몬을 종료하거나 재설정하지 않는다. 볼륨이나 이미지를 삭제하지 않는다.

### 2-3. 시작 실패 시
다음 중 하나라도 해당하면 시작 실패로 판단한다.
- `sudo` 권한이 없다.
- `dockerd`가 오류로 끝나고 `docker info`가 계속 실패한다.
- 컨테이너 권한 제한으로 데몬을 띄울 수 없다는 로그가 있다.

이때는 3-B 경로로 간다. 시도 결과를 로그와 함께 그대로 보고한다. 추측으로 원인을 단정하지 않는다.

## 3-A단계: 데몬이 정상일 때 (전체 검증)
```bash
docker compose up -d --build
docker compose ps
```
- postgres의 healthcheck가 healthy인지 확인한다.
- `curl`로 `/health`, `/health/db`를 확인한다. 프론트엔드 접속과 `/api` 프록시도 확인한다.
- `docker compose ps -a`로 `migrate`가 종료 코드 0으로 끝났는지 확인하고, `backend`가 그 뒤에 시작됐는지(시작 시각 또는 `depends_on` 조건) 확인한다. `migrate`가 실패하면 `backend`가 시작되지 않아야 한다. 이 실패 경로는 테스트 환경에서 의도적으로 실패하는 마이그레이션이 필요하면 사용자 승인 후에 확인한다.
- 종료 확인: `docker compose down`. **`-v` 옵션은 쓰지 않는다.**
- 검증 후 컨테이너가 남아 있으면 종료 여부를 보고에 적는다.

### 3-A-1. 하위 경로 + Embedded 검증, 메모리 실측 (`docs/decisions/03a-deploy-environment.md`)
- 경로 값을 `/bi-wizard`, `/bi-wizard/superset`으로 두고 frontend nginx 프록시를 거쳐 확인한다. 세션은 `.env`를 만들거나 수정하지 않는다. 기동에 값이 필요하면 `_workspace/qa/`에 **비밀이 아닌 더미 값**으로 임시 env 파일을 만들어 `docker compose --env-file`로 지정한다(저장소에 넣지 않고, 실제 Secret 값은 요구하거나 기록하지 않는다).
  - `${APP_BASE_PATH}/` 포털과 정적 파일, `${APP_BASE_PATH}/api/health`, `${APP_BASE_PATH}/api/health/db`
  - `${SUPERSET_APP_ROOT}/` 로그인 화면과 정적 파일(중복 접두 `…/superset/superset/…`가 없는지)
  - Embedded: `${SUPERSET_APP_ROOT}/embedded/<id>` iframe 로드. guest token 발급까지 확인하려면 대시보드가 필요하므로 불가능하면 "미실행: 대시보드 없음"으로 적고 가능한 단계까지만 확인한다
  - `APP_PROXY_STRIP_PREFIX`를 `false`(기본)와 `true` 각각으로 같은 확인을 반복한다. 두 값의 결과를 표로 따로 보고한다
- **`db-bootstrap` 검증:** 두 번 연속 실행해 오류가 없는지, `docker compose down`(`-v` 없음) 후 `up`에서 계정이 유지되는지, 임시 env 파일의 비밀번호를 바꾸고 다시 `up`하면 반영되는지 확인한다. `bi_readonly`로 접속해 `SELECT 1`은 성공하고 `CREATE TABLE`, `INSERT`는 거부되는지, `SHOW default_transaction_read_only`가 `on`인지 확인한다. `superset` DB가 앱 DB와 별도인지(`\l`) 확인한다. 비밀번호는 보고에 쓰지 않는다.
- **재현되는 하위 경로 버그가 있으면 Superset 내부 코드를 수정하지 않는다.** 현상, 재현 방법, 대안과 각 영향을 정리해 보고하고 멈춘다.
- `docker stats --no-stream`으로 컨테이너별 메모리를 기록하고 `mem_limit` 대비 비율을 표로 적는다.
- **5MB 엑셀 샘플 대리 측정:** 가져오기 기능은 Gate ④에서 구현되므로, backend 이미지 안에서 5MB급 샘플(openpyxl로 생성한 합성 파일 또는 사용자가 제공한 실제 파일)을 openpyxl(read_only)과 pandas로 읽는 일회성 스크립트로 최대 메모리(RSS)를 측정한다. 스크립트와 샘플은 `_workspace/qa/`에 두고 저장소에 넣지 않는다. 보고에 "대리 측정이며 실제 가져오기 파이프라인의 값이 아니다"를 명시하고, 결과를 `docs/deploy-coordination.md` 5번에 기록하도록 메인에게 전달한다.

### 3-A-2. 마이그레이션 왕복 테스트 (D5, D6)
`docs/decisions/03-migration-tool.md` 기준이다. 빈 DB는 tmpfs 테스트 전용 PostgreSQL 서비스(compose profile `test`)로 만든다.

```bash
docker compose --profile test up -d postgres-test      # 서비스 이름은 compose.yml을 따른다
# backend 이미지로 테스트 DB에 대해 순서대로 실행 (명령은 README와 compose.yml을 따른다)
#   alembic upgrade head → alembic downgrade base → alembic upgrade head
docker compose --profile test stop postgres-test && docker compose --profile test rm -f postgres-test   # 전체 스택을 내리지 않는다(EW-6: `--profile test down`은 실행 중인 전체 스택을 내린다), -v 없음
```
- 세 단계가 모두 성공해야 통과다. 실패한 단계와 출력의 핵심 줄을 그대로 인용한다.
- 자동 생성 초안에 `DROP`이 있으면 qa-engineer가 직접 적용하지 않고 "사용자 확인 필요"로 보고한다.
- tmpfs는 메모리를 쓴다. 테스트 DB는 평소 기동 대상이 아니다.
- Jenkins에서의 적용은 Jenkins 실행 환경(Docker 사용 가능 여부) 확인 후 별도 결정이다. 그 전에는 Jenkinsfile에 넣지 않는다.

## 3-B단계: 데몬을 띄울 수 없을 때 (사용자 PC 검증으로 넘김)
1. 1단계 정적 검증까지만 수행하고 결과를 기록한다.
2. 기동 검증은 "미실행: 세션에서 Docker 데몬을 시작하지 못함"으로 표시한다.
3. 사용자에게 Windows PC에서 실행할 검증 요청서를 만든다.

### 사용자 PC 검증 요청서 형식
| 순서 | 실행할 명령 (또는 BAT) | 기대 결과 | 실패 시 보낼 정보 |
| --- | --- | --- | --- |
| 1 | `scripts\validate-env.bat` | 오류 없이 종료 | 콘솔 출력 |
| 2 | `scripts\start-local.bat` | `postgres`, `backend`, `frontend` 기동. `migrate`는 정상 종료(종료 코드 0) 후 `backend` 시작 | `scripts\logs-local.bat` 출력 |
| 3 | `scripts\health-check.bat` | `/health`, `/health/db` 정상 | 응답 내용 |
| 4 | `scripts\stop-local.bat` | 정상 종료 | 콘솔 출력 |

- BAT는 세션에서 실행하지 않았다는 사실을 요청서에 명시한다.
- `.env`는 사용자가 직접 채운다. 세션은 값을 요구하거나 기록하지 않는다.

## 4단계: 경계면 대조
- 백엔드 응답 예시와 프런트엔드 훅·타입 정의의 필드 이름, 타입, 중첩 구조를 대조한다.
- 파일이 존재하는지만 확인하고 "연결됨"으로 쓰지 않는다.
- 불일치는 필드 단위로 적는다.

## 5단계: Skill 동기화 확인
- 변경된 기능의 `skills/<기능>/SKILL.md`에 적힌 실행 명령, API 경로, 실패 확인 방법이 실제 코드와 맞는지 확인한다.
- 맞지 않으면 "Skill 미갱신"으로 보고한다.

## 최종 검증(main 반영 직전) 규칙 (사용자 결정 2026-10-13)
- 최종 검증은 **마지막 커밋(해시를 보고에 적는다)** 기준으로 QA가 독립으로 돌린다: 실제 PG 전체 pytest(`REQUIRE_PG=1`, slow 포함, pg 변형 skip 0), 차분 전수, 프런트 전체(vitest·build·빌드 뒤 static-checks), 실제 Superset 스모크(STRIP true·false, guest 목록 한정 스크립트 `scripts/manual/superset-guest-list-check.py` 포함), 비밀값 검사(번들·로그·`ps`·`docker inspect`·브라우저 저장소).
- **재검증 범위(사용자 결정 2026-10-13):**
  - **제품 영향 경로**(`backend/`, `frontend/`, `superset/`, nginx 설정, `compose.yml`, `Dockerfile`, 마이그레이션, `backend/bootstrap/`, 설정 파일)가 QA 뒤에 바뀌면 **전체 재검증**을 다시 돌린다.
  - 그 밖(`scripts/manual/`, `docs/`, 시험 보조 스크립트)만 바뀌면 **범위 재검증**: (1) 검증한 커밋..HEAD의 `git diff --stat`로 제품 영향 경로 변경이 0건임을 증명하고, (2) 바뀐 스크립트를 실제 환경으로 실행하며, (3) ruff와 CI 검증 스크립트를 돌린다. 변경 성격상 필요한 항목(예: 비밀값 조건이 바뀌면 그 검사)은 추가한다.
- 비밀값 조건(사용자 결정 2026-10-13): 이미지(`docker image inspect`·`docker history`), 컨테이너 Cmd·Args, 로그, `ps`, 프런트 번들, 브라우저 저장소에는 0건이다. **컨테이너 Env는 `.env`와 같은 보호 등급(호스트 Docker 권한자만 접근)으로 허용**한다.
- 실패가 1건이라도 있으면 PR을 만들지 않고 멈춰 보고한다.

- **커밋 전 자체 점검(사용자 결정 2026-10-13):** 누가 고치든(리드 포함) 커밋 전에 바뀐 `.py` 파일은 `ruff check`와 `ruff format --check`(backend `pyproject.toml` 설정)를, 바뀐 프런트 파일은 lint와 typecheck를 직접 돌린다. 문서 규칙이며 훅·설정 변경은 없다(`scripts/manual/` 같은 CI 밖 스크립트도 포함).

## 보고 형식
| 항목 | 결과 | 근거 | 담당 |
| --- | --- | --- | --- |

- 데몬 시작 시도 명령과 결과를 별도 줄로 적는다.
- 미실행 항목에는 이유를 쓴다.

## 금지 사항
- `docker compose down -v`, `docker volume rm`, `docker system prune`을 실행하지 않는다.
- BAT 파일을 Linux에서 실행하지 않는다.
- `.env`를 만들거나 수정하지 않는다.

## 관련 Skill
- `env-bootstrap`: 체크리스트 항목
- `local-environment` (`skills/local-environment/SKILL.md`): 사용자용 실행 절차
