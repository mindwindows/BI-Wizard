---
name: local-environment
description: BI-Wizard 로컬 실행 환경(Docker Compose)을 시작, 종료, 재시작하고 로그와 Health Check를 확인하는 방법. 하위 경로(APP_BASE_PATH), APP_PROXY_STRIP_PREFIX 전환, db-bootstrap, 마이그레이션 왕복 테스트, 문제 해결을 포함한다. "서버 띄워줘", "로그 보여줘", "상태 확인", "환경 안 올라와요" 같은 요청에 사용한다.
---

# local-environment — 로컬 실행 환경

## 1. 목적
새 PC에서 저장소를 받은 사람이 Secret 값만 채운 뒤 같은 명령으로 PostgreSQL, FastAPI, 포털(Frontend), Superset을 실행하고 상태를 확인하게 한다. 사람과 AI가 같은 명령을 쓰므로 실행법을 추측하지 않는다.

> **Gate ② 한정 구성:** `POSTGRES_USER`(이미지 슈퍼유저)를 앱과 `migrate` 계정으로 쓴다. Gate ④ 진입 전에 최소 권한 앱 계정으로 분리해야 한다.

## 2. 사용 조건 / 사전 요구사항
- Docker Engine과 Docker Compose v2 (`docker compose`). Windows에서는 Docker Desktop 대신 Podman 등을 쓸 수 있으나 `service_completed_successfully` 지원은 사용자 PC에서 확인이 필요하다.
- `.env` 파일: `.env.example`을 복사하고 비어 있는 Secret 값 6개(`POSTGRES_PASSWORD`, `POSTGRES_READONLY_PASSWORD`, `SUPERSET_DB_PASSWORD`, `SUPERSET_SECRET_KEY`, `GUEST_TOKEN_JWT_SECRET`, `SUPERSET_ADMIN_PASSWORD`)를 채운다. `.env`는 Git에 올리지 않는다.
- 메모리: 상시 서비스 한도 합계 약 4.75GB(여유 포함 8GB 안). 한도는 `compose.yml`에 고정되어 있다.
- BAT는 Windows에서만 실행한다. Linux/macOS와 AI 세션에서는 아래 `docker compose` 명령을 직접 쓴다.

## 3. 입력
`.env`의 변수(이름 기준 원본은 `.env.example`). 값은 이 문서에 적지 않는다.

| 변수 | 의미 | 비고 |
| --- | --- | --- |
| `APP_NAME`, `APP_ENV`, `APP_DEBUG` | 앱 이름, 환경, 디버그 | `APP_DEBUG=true`면 `/api/docs`가 열린다 |
| `APP_BASE_PATH` | 포털 하위 경로 | 예 `/bi-wizard`. 빈 값=루트 배포(빈 값을 허용하는 변수는 이것뿐). 앞 `/` 필수, 뒤 `/`·`//`·`.`/`..` 세그먼트 금지. 운영자 확인 필요 |
| `APP_PROXY_STRIP_PREFIX` | 프록시가 접두를 떼고 전달하는가 | `false`(기본)=유지, `true`=제거 |
| `SUPERSET_APP_ROOT` | Superset 하위 경로 | 예 `/bi-wizard/superset`. 형식은 같지만 빈 값 불가(로컬 프록시 재현에서 포털과 경로가 겹침). `APP_BASE_PATH`와 독립 값. 운영자 확인 필요 |
| `FRONTEND_HOST`, `FRONTEND_PORT` | 브라우저 접속 주소(호스트 게시) | 기본 `127.0.0.1`(이 PC에서만), `5173`. LAN에 열려면 `0.0.0.0`으로 바꾸되 Superset 관리자 로그인 화면도 LAN에 노출된다 |
| `BACKEND_HOST`, `BACKEND_PORT` | backend 바인딩(컨테이너 안) | 호스트에는 `127.0.0.1`로만 게시 |
| `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | PostgreSQL | 호스트에는 `127.0.0.1`로만 게시 |
| `POSTGRES_READONLY_PASSWORD` | `bi_readonly` 비밀번호 | Superset 업무 데이터 연결용 |
| `SUPERSET_DB_PASSWORD` | `superset_meta` 비밀번호 | Superset 메타 DB(`superset`) |
| `SUPERSET_SECRET_KEY`, `GUEST_TOKEN_JWT_SECRET` | Superset 키 | 운영 중 `SUPERSET_SECRET_KEY`를 바꾸면 저장된 암호화 값을 못 읽는다 |
| `SUPERSET_ADMIN_USER`, `SUPERSET_ADMIN_PASSWORD` | Superset 관리자 | 계정이 없을 때만 만든다 |
| `LOG_LEVEL`, `TZ` | 로그 수준, 시간대 | |

Azure OpenAI 변수와 `/health/azure-openai`는 없다(브리프 5절 1번: 제외).

## 4. 출력
- 컨테이너: `postgres`, `backend`, `frontend`, `superset`은 상시 실행. `db-bootstrap`, `migrate`, `superset-init`은 일회성이라 `Exited (0)`이 정상이다.
- 접속 주소(기본값): 포털 `http://localhost:5173/bi-wizard/`, Superset `http://localhost:5173/bi-wizard/superset/`
- 데이터: Docker 볼륨 `postgres_data`(종료해도 유지).

## 5. 실행 방법

### 사람 (Windows)
```
copy .env.example .env          (그리고 .env의 빈 Secret 값을 채운다)
scripts\validate-env.bat        .env 검증 (이름만 출력, 값은 출력하지 않음)
scripts\start-local.bat         시작  = docker compose up -d --build
scripts\health-check.bat        상태 확인
scripts\logs-local.bat backend  로그 (서비스 이름 생략 시 전체, 종료는 Ctrl+C)
scripts\restart-local.bat       재시작 = down 후 up -d --build
scripts\stop-local.bat          종료  = docker compose down
```

### AI / CLI (같은 동작)
```
docker compose up -d --build
docker compose ps
docker compose logs --tail=200 backend
docker compose down                       # 볼륨 삭제 옵션(-v)은 쓰지 않는다
```
첫 기동은 이미지 빌드 때문에 수 분, 이후 `superset-init`(약 30초)이 매번 다시 실행된다. 모든 서비스가 준비되면 `docker compose ps`에서 `backend`, `frontend`, `postgres`, `superset`이 `healthy`다.

### 기동 순서
`postgres`(healthy) → `db-bootstrap`(성공 완료) → `migrate`(성공 완료) → `backend` → `frontend`. `superset-init`은 `db-bootstrap` 완료 후, `superset`은 `superset-init` 완료 후에 시작한다. `migrate`가 실패하면 `backend`는 시작하지 않는다.

### 하위 경로와 프록시 (`APP_BASE_PATH`, `SUPERSET_APP_ROOT`, `APP_PROXY_STRIP_PREFIX`)
- 브라우저는 `http://localhost:${FRONTEND_PORT}${APP_BASE_PATH}/…`로 frontend nginx에 접속한다. 이 nginx가 로컬에서 **메인 플랫폼 프록시 역할**을 한다: `${APP_BASE_PATH}/`는 포털 정적 파일, `${APP_BASE_PATH}/api/`는 backend, `${SUPERSET_APP_ROOT}/`는 Superset.
- **Superset 경로는 항상 접두를 유지한 채 전달한다.** Superset 6.1.0은 접두로 시작하지 않는 요청에 404를 낸다. 프록시가 접두를 떼면 동작하지 않는다.
- 포털 API는 `APP_PROXY_STRIP_PREFIX`로 전환한다. 이미지를 다시 빌드할 필요 없이 `.env`만 바꾸고 다시 시작한다.
  - `false`(기본): nginx가 접두를 유지한 채 넘겨 backend가 `${APP_BASE_PATH}/api/…`로 받는다.
  - `true`: nginx가 접두를 떼어 backend가 `/api/…`로 받는다.
  - backend는 라우트를 항상 `/api/…`에 두고 `root_path=APP_BASE_PATH`로 접두를 떼므로, **두 형태(`${APP_BASE_PATH}/api/…`, `/api/…`)를 모두 받는다.** 이 값이 backend 동작을 막는 것은 아니고, 프록시(nginx)가 무엇을 보내는지를 바꾼다. 확인은 backend 접근 로그의 경로로 한다.
  ```
  (.env에서 APP_PROXY_STRIP_PREFIX 수정)
  docker compose up -d            # 바뀐 환경변수의 frontend, backend가 다시 만들어진다
  docker compose logs backend     # "받는 API 접두=" 로그와 접근 로그의 경로로 확인
  ```
- 정적 파일 규칙: 하위 경로가 있으면 `${APP_BASE_PATH}/` **아래에서만** SPA fallback(없는 경로도 `index.html`)을 한다. 접두 밖 루트 경로는 정적 자산(`/`, `/index.html`, `/config.js`, `/assets/…`)만 서빙하고 나머지는 404다(앞단이 접두를 떼고 넘겨도 정적 자산은 서빙된다). 접두 없이 잘못 나간 요청이 200 HTML에 가려지지 않게 하려는 것이다. `APP_BASE_PATH`가 빈 값(루트 배포)이면 루트에서 SPA fallback을 한다.
- `X-Forwarded-Proto/Host`: 이 nginx는 로컬 재현용이라 클라이언트가 보낸 값을 그대로 Superset에 전달한다. 앞단 프록시 없이 쓸 때 덮어쓰는 방법은 `frontend/nginx/templates/default.conf.template` 주석을 본다(새 변수 없음).
- 프런트 코드는 `${basePath}/api/…`(호스트 없는 상대경로)로 호출한다. `basePath`는 컨테이너 시작 때 만들어지는 `config.js`(`window.__APP_CONFIG__`)에서 온다. 정적 파일은 접두가 있어도(유지 전달) 없어도(떼고 전달) 서빙된다.
- 실제 하위 경로 값과 프록시의 접두 처리 방식은 웹서버 배포 때 관리자와 정한다(`docs/deploy-coordination.md`). 값을 바꿀 때는 `.env`만 고친다.

### Superset 등록 방식과 보안 메모
- `superset-init`은 업무 데이터 연결(`bi_readonly`)을 `superset set_database_uri` CLI가 아니라 같은 함수를 부르는 `superset/register_database.py`로 등록한다. CLI는 URI(비밀번호 포함)를 명령줄 인수로 받아 컨테이너의 프로세스 목록에 보이기 때문이다. URI는 로그에 출력하지 않는다.
- Superset 텔레메트리(Scarf): 공식 FAQ의 `SCARF_ANALYTICS=false`는 6.1.0에서 **효과가 없음을 확인해 삭제했다**(서버 소스와 빌드된 프런트엔드에 이 환경변수를 읽는 코드가 없고, 메뉴 컴포넌트가 값과 무관하게 `apachesuperset.gateway.scarf.sh` 이미지를 항상 요청한다). 대신 `superset/superset_config.py`가 기본 CSP(`TALISMAN_CONFIG`, `TALISMAN_DEV_CONFIG`)에서 `scarf.sh` 호스트를 제거해 브라우저가 해당 요청을 보내지 못하게 한다(Superset 내부 코드 수정 아님). 부수 효과로 브라우저 콘솔에 CSP 위반 경고(`img-src`)가 남을 수 있다. Google Fonts(`fonts.googleapis.com`, `fonts.gstatic.com`) 요청은 막지 않았다.
- gunicorn 워커는 1개이고 주기적 재시작(`WORKER_MAX_REQUESTS`)은 쓰지 않는다. 워커 1개를 재시작하면 그 순간 요청 1건이 502가 되고 다음 요청이 지연된다. 메모리 누수 보호는 `mem_limit`과 `restart: unless-stopped`에 맡긴다. 한계: 한도에 닿으면 컨테이너가 강제 종료(137)된 뒤 재시작되며 그동안 Superset 요청이 실패한다. `docker stats`로 추세를 보고 한도는 `docs/decisions/03a-deploy-environment.md`에 따라 조정한다.

### db-bootstrap (읽기 전용 계정과 Superset 메타 DB)
`docker compose up`마다 일회성 `db-bootstrap`이 `backend/bootstrap/run.sh`를 실행해 `roles.sql`을 적용한다(멱등, `initdb.d` 미사용).
- 역할 `bi_readonly`(읽기 전용, `default_transaction_read_only=on`), `superset_meta`, 데이터베이스 `superset`(소유 `superset_meta`)을 만든다. 이름은 코드 상수다.
- `.env`의 `POSTGRES_READONLY_PASSWORD`, `SUPERSET_DB_PASSWORD`를 바꾸면 다음 기동에서 반영된다. 비어 있으면 실패한다. `POSTGRES_USER`가 `bi_readonly`/`superset_meta`와 같으면 실패한다. 비밀번호 설정 문장이 실패해도 서버 오류 로그에 문장이 남지 않도록 `SET LOCAL log_min_error_statement = panic`을 쓴다.
- `bi_readonly`의 `SELECT` 권한 부여는 Gate ③에서 마이그레이션으로 한다. 지금은 업무 테이블이 없다.
- 수동 재실행: `docker compose run --rm db-bootstrap`

### 마이그레이션 왕복 테스트 (tmpfs 테스트 DB)
빈 DB에서 `upgrade head → downgrade base → upgrade head`가 성공하는지 확인한다. 테스트 DB `postgres-test`는 compose profile `test`에만 있고 데이터가 tmpfs(256MB 제한)라 호스트에 포트를 열지 않는다.
```
docker compose --profile test up -d --wait postgres-test
docker compose --profile test run --rm --no-deps -e PGHOST=postgres-test db-bootstrap
docker compose --profile test run --rm --no-deps -e POSTGRES_HOST=postgres-test migrate alembic upgrade head
docker compose --profile test run --rm --no-deps -e POSTGRES_HOST=postgres-test migrate alembic downgrade base
docker compose --profile test run --rm --no-deps -e POSTGRES_HOST=postgres-test migrate alembic upgrade head
docker compose --profile test run --rm --no-deps -e POSTGRES_HOST=postgres-test migrate alembic current
```
정리(둘 중 하나, 모두 `-v` 없음):
```
docker compose --profile test stop postgres-test
docker compose --profile test rm -f postgres-test     # 테스트 DB 컨테이너만 제거(tmpfs 데이터도 사라짐)
docker compose --profile test down                    # 프로젝트 전체 종료(운영 데이터 볼륨은 유지)
```
- 규칙: 모든 revision에 `downgrade()`를 구현하고 마이그레이션 안의 SQL은 보간 없는 고정 문자열만 쓴다. 자동 생성 초안에 `DROP`이 있으면 적용하지 말고 사용자 확인을 받는다. 지금은 모델 메타데이터를 연결하지 않아(D2는 Gate ③) `alembic revision --autogenerate`와 `alembic check`는 쓸 수 없다.
- 새 revision은 `backend/migrations/versions/`에 둔다. 마이그레이션 실행은 `migrate` 서비스뿐이며 앱 코드는 시작 때 마이그레이션을 하지 않는다.

## 6. 관련 UI / API / command / DB
- UI: 포털 `${APP_BASE_PATH}/`(Gate ②에서는 API/DB 상태 표시뿐), Superset `${SUPERSET_APP_ROOT}/`
- API (브라우저 쪽 경로 기준, 업무 API는 아직 없음):
  - `GET ${APP_BASE_PATH}/api/health` — FastAPI 상태 (`{"status":"ok"}`)
  - `GET ${APP_BASE_PATH}/api/health/db` — PostgreSQL `SELECT 1` (정상 200, 실패 503)
  - `GET ${SUPERSET_APP_ROOT}/health` — Superset (`OK`)
- command: `scripts\*.bat`, `docker compose …`, `alembic …`(migrate 서비스 안)
- DB: 앱 DB(`POSTGRES_DB`, 현재 `alembic_version`만), 메타 DB `superset`, 역할 `bi_readonly`/`superset_meta`

## 7. 실패 시 확인 방법
| 증상 | 원인 | 확인과 해결 |
| --- | --- | --- |
| `required variable … is missing a value` | `.env`에 변수가 없거나 비어 있음 | `scripts\validate-env.bat`이 이름을 알려 준다 |
| 포트 사용 중 | `FRONTEND_PORT`, `POSTGRES_PORT`, `BACKEND_PORT` 충돌 | `.env`의 포트를 바꾸고 `restart-local.bat` |
| `db-bootstrap` 실패 | 비밀번호 변수 비어 있음, 또는 `POSTGRES_PASSWORD`가 볼륨 생성 때 값과 다름 | `docker compose logs db-bootstrap`. `POSTGRES_PASSWORD`는 DB 볼륨이 처음 만들어질 때만 적용된다. 값을 되돌리거나 psql에서 `\password`로 바꾼다 |
| `backend`가 시작하지 않음 | `migrate` 실패 | `docker compose logs migrate`. 원인을 고치고 `docker compose up -d` |
| `superset-init` 실패 | 메타 DB 접속 실패, 키 누락 | `docker compose logs superset-init` |
| Superset 404 | 프록시가 접두를 뗐거나 `SUPERSET_APP_ROOT`가 다름 | Superset 경로는 접두를 유지해야 한다. `.env`의 값과 접속 주소 확인 |
| Superset 로고 이미지 404(경로에 접두가 두 번 붙음), `static/service-worker.js` 404 | Superset 6.1.0 하위 경로 동작과 이미지 구성. 화면 기능에는 영향이 없다 | Superset 내부 코드는 수정하지 않는다. 알려진 사항이며 대안은 개발 에이전트가 보고한다 |
| Superset 로그인 화면에서 접두 없는 일러스트 이미지 요청이 404(404 페이지 그림). 올바른 경로 `${SUPERSET_APP_ROOT}/static/assets/<해시>.png`는 200 | 알려진 Superset 6.1.0 현상(이미지 요청 경로에 접두가 빠짐). 접두 밖 요청이 이제 404로 드러난다 | 화면 기능에는 영향이 없다. Superset 내부 코드는 수정하지 않는다 |
| Embedded iframe이 "Something went wrong with embedded authentication"으로 실패 | **하위 경로 때문이 아니다.** guest 역할 `GUEST_ROLE_NAME`(기본 `Public`)에 권한이 없어 `GET ${SUPERSET_APP_ROOT}/api/v1/me/roles/`가 403을 낸다. QA 대조 실험: 루트 경로+`Public`도 실패, 하위 경로+`Gamma`는 성공. 공식 Embedded SDK README도 guest가 `GUEST_ROLE_NAME` 역할로 동작한다고 설명한다 | 어떤 역할/권한을 줄지는 **사용자 결정 대기**이므로 이 단계에서 `GUEST_ROLE_NAME`을 바꾸지 않는다 |
| Superset이 갑자기 502/지연 후 복구 | 메모리 한도 초과로 컨테이너가 재시작됨(137) | `docker compose ps`, `docker stats --no-stream`, `docker compose logs superset` |
| 포털에서 API 오류 | 경로 값 불일치, backend 비정상 | `health-check.bat`, `docker compose logs backend frontend` |
| BAT 출력이 영어다 | 일부 Windows cmd에서 UTF-8 BAT가 `goto` 레이블 탐색을 깨뜨릴 수 있어 BAT는 ASCII(영문)로만 쓴다 | 정상이다. 설명은 이 문서와 README에 있다. 성공은 `[OK]`, 실패는 `[FAIL]`, `.env` 검사는 `[MISSING]`/`[EMPTY]`로 표시한다 |
| BAT가 이상하게 동작 | 줄바꿈이 LF로 바뀜 | `.gitattributes`가 BAT를 CRLF로 고정한다. 저장소를 다시 체크아웃 |
| 컨테이너가 메모리 부족으로 종료(137) | `mem_limit` 초과 | `docker stats --no-stream`. 한도 조정은 `docs/decisions/03a-deploy-environment.md`를 따른다 |

## 8. 검증 방법
- 자동 테스트: backend `docker build --target test backend`(ruff, pytest), frontend `docker build --target test frontend`(eslint, tsc, vitest). Jenkins도 같은 명령을 쓴다.
- 구성 검증: `docker compose config --quiet`
- 수동: `scripts\health-check.bat`이 모두 `[OK]`이고 마지막에 `All checks passed.`를 출력하며 `docker compose ps`에서 상시 서비스가 `healthy`.
- 읽기 전용 계정: `bi_readonly`로 `SELECT 1`은 되고 `CREATE TABLE`·`INSERT`는 거부된다.
- 두 가지 `APP_PROXY_STRIP_PREFIX` 값 모두에서 `${APP_BASE_PATH}/api/health`가 응답하고 backend 접근 로그의 경로가 각각 `${APP_BASE_PATH}/api/health`, `/api/health`다.
- BAT 실행 검증은 사용자 Windows PC에서 한다(AI 세션은 Linux라 실행하지 않는다).
- 메모리 실측: `docker stats --no-stream`(결과는 `docs/deploy-coordination.md` 5번에 기록).

## 9. 연관 Skill
- `.claude/skills/env-bootstrap`: 이 환경을 만들고 점검하는 개발용 절차(Environment Ready 체크리스트)
- `.claude/skills/qa-verification`: 기동과 Health 검증 절차
- `.claude/skills/product-skill-authoring`: 이 Skill의 작성 형식
- 업무 기능 Skill(`skills/<기능>/SKILL.md`)은 Gate ③ 이후 추가되며, 모두 이 환경이 통과한 상태를 사용 조건으로 삼는다.
