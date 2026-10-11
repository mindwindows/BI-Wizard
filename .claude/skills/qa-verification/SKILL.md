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

### 3-A-2. 마이그레이션 왕복 테스트 (D5, D6)
`docs/decisions/03-migration-tool.md` 기준이다. 빈 DB는 tmpfs 테스트 전용 PostgreSQL 서비스(compose profile `test`)로 만든다.

```bash
docker compose --profile test up -d postgres-test      # 서비스 이름은 compose.yml을 따른다
# backend 이미지로 테스트 DB에 대해 순서대로 실행 (명령은 README와 compose.yml을 따른다)
#   alembic upgrade head → alembic downgrade base → alembic upgrade head
docker compose --profile test down                     # -v 없음
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
