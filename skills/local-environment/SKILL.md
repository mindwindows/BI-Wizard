---
name: local-environment
description: BI-Wizard 로컬 실행 환경(Docker Compose)을 시작, 종료, 재시작하고 로그와 Health Check를 확인하는 방법. 하위 경로(APP_BASE_PATH), APP_PROXY_STRIP_PREFIX 전환, DB 계정 분리와 db-bootstrap, Superset 서비스·발급 계정과 역할, Superset 업그레이드 점검, 인증 스텁 스위치(AUTH_STUB_ENABLED), 마이그레이션 왕복 테스트, 문제 해결을 포함한다. "서버 띄워줘", "로그 보여줘", "상태 확인", "환경 안 올라와요" 같은 요청에 사용한다.
---

# local-environment — 로컬 실행 환경

## 1. 목적
새 PC에서 저장소를 받은 사람이 Secret 값만 채운 뒤 같은 명령으로 PostgreSQL, FastAPI, 포털(Frontend), Superset을 실행하고 상태를 확인하게 한다. 사람과 AI가 같은 명령을 쓰므로 실행법을 추측하지 않는다.

> **DB 계정 분리 (EW-1, Gate ② 한정 구성 해소):** Gate ②에서는 `POSTGRES_USER`(이미지 슈퍼유저)를 앱과 `migrate` 계정으로 썼다. 이제 `POSTGRES_USER`/`POSTGRES_PASSWORD`는 **이미지 슈퍼유저 전용**이다(이미지 초기화, postgres healthcheck, `db-bootstrap`만 사용. 운영 가이드의 `POSTGRES_USER`=앱 계정 의미와 다른 의도적 차이, `docs/deploy-coordination.md` 29번). `migrate`는 `bi_owner`, `backend`는 `bi_app`으로 접속한다. 계정 이름은 코드 상수이고 환경변수는 비밀번호만 받는다.

## 2. 사용 조건 / 사전 요구사항
- Docker Engine과 Docker Compose v2 (`docker compose`). Windows에서는 Docker Desktop 대신 Podman 등을 쓸 수 있으나 `service_completed_successfully` 지원은 사용자 PC에서 확인이 필요하다.
- `.env` 파일: `.env.example`을 복사하고 비어 있는 Secret 값 10개(`POSTGRES_PASSWORD`, `POSTGRES_APP_PASSWORD`, `POSTGRES_OWNER_PASSWORD`, `POSTGRES_READONLY_PASSWORD`, `SUPERSET_DB_PASSWORD`, `SUPERSET_SECRET_KEY`, `GUEST_TOKEN_JWT_SECRET`, `SUPERSET_ADMIN_PASSWORD`, `SUPERSET_SERVICE_PASSWORD`, `SUPERSET_GUEST_ISSUER_PASSWORD`)를 채운다. `.env`는 Git에 올리지 않는다.
- 메모리: 상시 서비스 한도 합계 약 4.75GB(여유 포함 8GB 안). 한도는 `compose.yml`에 고정되어 있다.
- BAT는 Windows에서만 실행한다. Linux/macOS와 AI 세션에서는 아래 `docker compose` 명령을 직접 쓴다.

## 3. 입력
`.env`의 변수(이름 기준 원본은 `.env.example`). 값은 이 문서에 적지 않는다.

| 변수 | 의미 | 비고 |
| --- | --- | --- |
| `APP_NAME`, `APP_ENV`, `APP_DEBUG` | 앱 이름, 환경, 디버그 | `APP_DEBUG=true`면 `/api/docs`가 열린다 |
| `AUTH_STUB_ENABLED` | 인증 스텁 스위치 | 값은 `true`/`false`로 쓴다(그 밖의 값은 CI `scripts/ci-validate-env.sh`가 `.env.example`에서 거부한다). 기본 `false`. `true`는 개발·시험 전용: `APP_ENV`가 명시적으로 `local` 또는 `test`일 때만 backend가 시작한다(그 밖에는 시작 거부). 스텁 로그인 기능 자체는 FU-1a |
| `APP_BASE_PATH` | 포털 하위 경로 | 예 `/bi-wizard`. 빈 값=루트 배포(빈 값을 허용하는 변수는 이것뿐). 앞 `/` 필수, 뒤 `/`·`//`·`.`/`..` 세그먼트 금지. 운영자 확인 필요 |
| `APP_PROXY_STRIP_PREFIX` | 프록시가 접두를 떼고 전달하는가 | `false`(기본)=유지, `true`=제거 |
| `SUPERSET_APP_ROOT` | Superset 하위 경로 | 예 `/bi-wizard/superset`. 형식은 같지만 빈 값 불가(로컬 프록시 재현에서 포털과 경로가 겹침). `APP_BASE_PATH`와 독립 값. 운영자 확인 필요 |
| `FRONTEND_HOST`, `FRONTEND_PORT` | 브라우저 접속 주소(호스트 게시) | 기본 `127.0.0.1`(이 PC에서만), `5173`. LAN에 열려면 `0.0.0.0`으로 바꾸되 Superset 관리자 로그인 화면도 LAN에 노출된다 |
| `BACKEND_HOST`, `BACKEND_PORT` | backend 바인딩(컨테이너 안) | 호스트에는 `127.0.0.1`로만 게시 |
| `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB` | PostgreSQL 주소와 DB 이름 | 호스트에는 `127.0.0.1`로만 게시 |
| `POSTGRES_USER`, `POSTGRES_PASSWORD` | **이미지 슈퍼유저** | postgres 이미지, healthcheck, `db-bootstrap`만 쓴다. backend·migrate에는 전달하지 않는다. `bi_owner`/`bi_app`/`bi_readonly`/`superset_meta`와 같은 이름 금지 |
| `POSTGRES_APP_PASSWORD` | `bi_app` 비밀번호 | backend 런타임 접속. 정적 표는 마이그레이션이 부여한 권한만, `bi_data` schema에는 표·뷰 생성 권한 |
| `POSTGRES_OWNER_PASSWORD` | `bi_owner` 비밀번호 | `migrate` 접속. 정적 표와 `bi_data` schema 소유자 |
| `POSTGRES_READONLY_PASSWORD` | `bi_readonly` 비밀번호 | Superset 업무 데이터 연결용 |
| `SUPERSET_DB_PASSWORD` | `superset_meta` 비밀번호 | Superset 메타 DB(`superset`) |
| `SUPERSET_SECRET_KEY`, `GUEST_TOKEN_JWT_SECRET` | Superset 키 | 운영 중 `SUPERSET_SECRET_KEY`를 바꾸면 저장된 암호화 값을 못 읽는다 |
| `SUPERSET_ADMIN_USER`, `SUPERSET_ADMIN_PASSWORD` | Superset 관리자 | 계정이 없을 때만 만든다(비밀번호를 바꿔도 반영되지 않는다) |
| `SUPERSET_SERVICE_USER`, `SUPERSET_SERVICE_PASSWORD` | Superset 서비스 계정(가상 데이터셋 등록 전용, 역할 `bi_service`) | 기본 이름 `bi_service`. `superset-init`이 매 기동 만들고 비밀번호를 맞춘다. **이름은 바꾸지 않는다.** backend도 받는다(사용은 FU-1e) |
| `SUPERSET_GUEST_ISSUER_USER`, `SUPERSET_GUEST_ISSUER_PASSWORD` | Superset 입장권 발급 전용 계정(역할 `bi_guest_issuer`) | 기본 이름 `bi_guest_issuer`. 규칙은 서비스 계정과 같다. 세 계정 이름(관리자 포함)은 서로 달라야 한다 |
| `LOG_LEVEL`, `TZ` | 로그 수준, 시간대 | |

Azure OpenAI 변수와 `/health/azure-openai`는 없다(브리프 5절 1번: 제외).

## 4. 출력
- 컨테이너: `postgres`, `backend`, `frontend`, `superset`은 상시 실행. `db-bootstrap`, `migrate`, `superset-init`은 일회성이라 `Exited (0)`이 정상이다. `superset-init`은 이미지 HEALTHCHECK를 끄므로(`healthcheck: disable: true`) 종료 뒤에도 `unhealthy`가 아니라 `Exited (0)`로 표시된다.
- 접속 주소(기본값): 포털 `http://localhost:5173/bi-wizard/`, Superset `http://localhost:5173/bi-wizard/superset/`
- 데이터: Docker 볼륨 `postgres_data`(종료해도 유지).
- Gate ② 때 만든 볼륨이 이미 있는 PC: `.env`에 `POSTGRES_APP_PASSWORD`, `POSTGRES_OWNER_PASSWORD`, `AUTH_STUB_ENABLED=false`를 추가하고 `up -d --build`만 하면 된다(데이터 유지). `db-bootstrap`이 새 계정을 만들고 기존 `public.alembic_version`의 소유자를 `bi_owner`로 바꾸며, `migrate`가 `0002`를 적용한다.

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
첫 기동은 이미지 빌드 때문에 수 분, 이후 `superset-init`(Superset을 여러 번 띄우는 단계라 새 설치 약 77초, 재기동 약 68초 실측, 환경에 따라 다름)이 매번 다시 실행된다. 모든 서비스가 준비되면 `docker compose ps`에서 `backend`, `frontend`, `postgres`, `superset`이 `healthy`다.

### 기동 순서
`postgres`(healthy) → `db-bootstrap`(성공 완료) → `migrate`(성공 완료) → `backend` → `frontend`. `superset-init`은 `db-bootstrap`과 `migrate` 완료 후, `superset`은 `superset-init` 완료 후에 시작한다(`superset-init`이 `migrate`를 기다리는 이유: `bi_readonly`의 `bi_data` USAGE는 마이그레이션 `0002`가 주므로 빈 볼륨 새 설치에서 순서 경쟁을 막는다. 순환 없음). `migrate`가 실패하면 `backend`와 `superset-init`은 시작하지 않는다.

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
- 정적 파일 규칙: `${APP_BASE_PATH}/` 아래와 접두 밖 루트 모두 SPA fallback(없는 경로도 `index.html` 200)을 한다. 앞단이 접두를 떼고 넘기는 딥링크(`/datasets/42`)를 살리려는 결정이다(2026-10-12, `docs/decisions/03b` 17-1). 부작용으로 접두 밖 임의 경로(`/nope`)도 200 HTML이다. `/api/…`는 backend(없는 경로는 JSON 404), `/assets/…` 누락은 404, `/nginx-health`·`/config.js`는 그대로다.
- `X-Forwarded-Proto/Host`: 이 nginx는 로컬 재현용이라 클라이언트가 보낸 값을 그대로 Superset에 전달한다. 앞단 프록시 없이 쓸 때 덮어쓰는 방법은 `frontend/nginx/templates/default.conf.template` 주석을 본다(새 변수 없음).
- 프런트 코드는 `${basePath}/api/…`(호스트 없는 상대경로)로 호출한다. `basePath`는 컨테이너 시작 때 만들어지는 `config.js`(`window.__APP_CONFIG__`)에서 온다. 정적 파일은 접두가 있어도(유지 전달) 없어도(떼고 전달) 서빙된다.
- 실제 하위 경로 값과 프록시의 접두 처리 방식은 웹서버 배포 때 관리자와 정한다(`docs/deploy-coordination.md`). 값을 바꿀 때는 `.env`만 고친다.

### Superset 등록 방식과 보안 메모
- `superset-init`은 업무 데이터 연결(`bi_readonly`)을 `superset set_database_uri` CLI가 아니라 같은 함수를 부르는 `superset/register_database.py`로 등록한다. CLI는 URI(비밀번호 포함)를 명령줄 인수로 받아 컨테이너의 프로세스 목록에 보이기 때문이다. URI는 로그에 출력하지 않는다.
- Superset 텔레메트리(Scarf): 공식 FAQ의 `SCARF_ANALYTICS=false`는 6.1.0에서 **효과가 없음을 확인해 삭제했다**(서버 소스와 빌드된 프런트엔드에 이 환경변수를 읽는 코드가 없고, 메뉴 컴포넌트가 값과 무관하게 `apachesuperset.gateway.scarf.sh` 이미지를 항상 요청한다). 대신 `superset/superset_config.py`가 기본 CSP(`TALISMAN_CONFIG`, `TALISMAN_DEV_CONFIG`)에서 `scarf.sh` 호스트를 제거해 브라우저가 해당 요청을 보내지 못하게 한다(Superset 내부 코드 수정 아님). 부수 효과로 브라우저 콘솔에 CSP 위반 경고(`img-src`)가 남을 수 있다. Google Fonts(`fonts.googleapis.com`, `fonts.gstatic.com`) 요청은 막지 않았다.
- gunicorn 워커는 1개이고 주기적 재시작(`WORKER_MAX_REQUESTS`)은 쓰지 않는다. 워커 1개를 재시작하면 그 순간 요청 1건이 502가 되고 다음 요청이 지연된다. 메모리 누수 보호는 `mem_limit`과 `restart: unless-stopped`에 맡긴다. 한계: 한도에 닿으면 컨테이너가 강제 종료(137)된 뒤 재시작되며 그동안 Superset 요청이 실패한다. `docker stats`로 추세를 보고 한도는 `docs/decisions/03a-deploy-environment.md`에 따라 조정한다.

### Superset 계정·역할 (`superset-init`, EW-3·EW-4)
`superset-init`은 매 기동 멱등으로 `superset db upgrade → ensure_admin → superset init → register_database → sync_permissions → ensure_roles → ensure_accounts` 순서로 실행한다. 모두 Superset 이미지 안의 파이썬 스크립트이며(앱 컨텍스트와 보안 관리자 사용, 새 의존성·REST 호출 없음) 로그에는 계정·역할 이름과 권한 개수만 나온다.
- **`sync_permissions.py`**: `SyncPermissionsCommand`로 업무 데이터 연결 `BI-Wizard (read-only)`의 `schema_access` 항목(`[BI-Wizard (read-only)].[<POSTGRES_DB>].[bi_data]`)을 만든다. `SYNC_DB_PERMISSIONS_IN_ASYNC_MODE`가 켜져 있으면 실패한다(Celery가 없다).
- **역할 5개**(권한 목록은 `superset/bi_roles.py` 한 곳):
  | 역할 | 권한 | 용도 |
  | --- | --- | --- |
  | `bi_service` | `can_read Dataset`, `can_write Dataset`, `schema_access`(`bi_data`), `can_read SecurityRestApi` (4개) | 가상 데이터셋 등록 서비스 계정. `can_grant_guest_token`은 주지 않는다 |
  | `bi_guest_issuer` | `can_grant_guest_token SecurityRestApi`, `can_read SecurityRestApi` (2개) | 입장권 발급 전용 계정 |
  | `bi_author` | 처음 만들 때만 내장 `Gamma`의 권한을 복사(역할과 권한을 한 번에 넣음) | 작성자(차트·대시보드 작성). 이후 기동에서는 `Gamma`와의 차이를 로그로 알리기만 하고 권한을 바꾸지 않는다(권한이 0개여도 되살리지 않고 `점검 필요: 역할 bi_author의 권한이 0개입니다`만 남긴다. 사람이 비워 둔 역할일 수 있다) |
  | `bi_author_schema` | `schema_access`(`bi_data`) 1개 | 작성자에게 `bi_author`와 함께 수동 부여 |
  | `bi_guest` | `can_read CurrentUserRestApi`, `can_read Dashboard`, `can_read Chart`, `can_time_range Api` (4개) | 임베딩 대시보드를 보는 입장권(guest token)의 역할(`GUEST_ROLE_NAME`). 열람 전용이며 내보내기(`can_csv`)·쓰기·Explore·SQL Lab·목록 API·`can_explore_json`·`can_read DashboardPermalinkRestApi`는 넣지 않는다 |
  `bi_service`·`bi_guest_issuer`·`bi_author_schema`·`bi_guest`는 매 기동 `없으면 생성 → 권한 목록 통째 교체 → 재읽기 비교`다. 목록의 권한이 Superset에 하나라도 없으면(예: `schema_access`가 아직 없음, `bi_guest` 목록의 이름이 새 버전에서 사라짐) 아무것도 바꾸지 않고 `superset-init`이 실패한다. **새 권한은 자동으로 추가하지 않는다**(목록을 바꾸는 것은 권한 변경이므로 사전 승인).
- **guest 불변식(`ensure_roles.py`가 매 기동 확인, 어기면 고치지 않고 `superset-init` 실패)**: 실제 적용된 설정 `GUEST_ROLE_NAME`이 `bi_guest`(역할 이름은 `bi_roles.py`의 `GUEST_ROLE`이 정본이고 `superset_config.py`는 같은 값을 따로 적는다. 어긋나면 실패), `PUBLIC_ROLE_LIKE` 미설정, **실제 적용된 입장권 유효 시간 `GUEST_TOKEN_JWT_EXP_SECONDS`가 300초**(가드 값 `bi_roles.GUEST_TOKEN_EXP_SECONDS` 한 곳, 설정에 아예 없으면 Superset 기본 300으로 보고 통과, 다르면 값만 메시지에 적고 실패하며 고치지 않는다. 이 확인은 guest 불변식 0단계라 역할·계정을 바꾸기 전에 끝난다), **`Public` 역할의 권한 0개**, `bi_guest` 목록에 금지 권한(내보내기·쓰기·Explore·SQL Lab·데이터 접근 계열, `can_explore_json`, 퍼머링크 읽기)이 없음. `Public`에 권한이 붙었다면 원인을 확인하고 관리자가 Superset에서 비운 뒤 다시 기동한다. 새로 띄우는 중이라 `superset`이 아직 없어 화면에 들어갈 수 없으면(`superset-init` 실패 중에는 `superset`이 시작되지 않는다), 같은 이미지로 일회성 컨테이너(`docker compose run --rm --entrypoint python superset-init`)를 띄워 앱 컨텍스트에서 `Public`의 권한을 비우는 방법을 쓰고 이 절차는 운영자가 직접 판단해 실행한다(이 저장소는 자동으로 고치지 않는다).
- **입장권 검증 훅(`GUEST_TOKEN_VALIDATOR_HOOK`, `superset_config.py`)**: `POST …/api/v1/security/guest_token/`(발급 API)에서만 불린다. `rls`가 비어 있지 않거나, 리소스가 정확히 1개가 아니거나 유형이 `dashboard`가 아니거나, 리소스 id가 정규 uuid 형식이 아니거나(숫자 id·slug 거부), `user.username`이 없으면 거부하고 Superset이 400을 낸다(`Guest token validation failed`). 거부 사유 코드만 Superset 로그(`bi_wizard.guest_token`)에 남기며 요청 본문·토큰은 남기지 않는다. 훅은 포털 DB를 읽지 않는다. "포털 등록 표의 embedded uuid만 허용" 검사는 FU-1e에서 확장 지점(`_EXTRA_GUEST_TOKEN_CHECKS`)에 채운다. 입장권 유효 시간은 Superset 기본 300초(5분)이고 바꾸지 않는다(위 불변식이 `ensure_roles.py`에서 실제 적용값을 확인하고 `sh scripts/ci-validate-env.sh`가 `superset_config.py`의 재정의를 막는다. 값을 바꿔야 하면 사전 승인을 받은 뒤 `bi_roles.GUEST_TOKEN_EXP_SECONDS`와 함께 바꾼다). **backend에는 `GUEST_TOKEN_JWT_SECRET`을 주지 않는다**(직접 서명한 토큰은 훅을 우회한다. `sh scripts/ci-validate-env.sh`가 확인).
- **계정 2개**: 서비스 계정(`SUPERSET_SERVICE_USER`, 역할 `bi_service` 하나)과 발급 계정(`SUPERSET_GUEST_ISSUER_USER`, 역할 `bi_guest_issuer` 하나). 관리자 역할은 주지 않는다. 계정이 없으면 만들고, 있으면 매 기동 비밀번호를 `.env` 값으로 다시 맞추고 활성화하며 역할을 맞춘다. **강제 복구(사용자 결정 2026-10-12):** 이 스크립트가 만든 **표식**(first_name `BI-Wizard`, email `<이름>@localhost`; email만 대소문자 무시, first_name은 대소문자 구분)이 있는 기존 계정에 정해진 역할 밖의 역할(Admin 포함)이 붙어 있으면 모두 제거하고 정해진 역할 하나로만 되돌린다(비밀번호 재설정·활성화는 기존대로). 복구하면 `[superset-init] 경고: 계정 <이름>의 허용 밖 역할(<역할 이름 목록>)을 제거하고 <역할>로 강제 복구했습니다`를 남긴다. **표식이 없는 기존 계정**은 **역할과 관계없이**(역할 0개, `Gamma`, `bi_service` 하나만 있어도) 이름이 충돌하면 비밀번호 재설정·역할 변경 없이 아무것도 바꾸지 않고 종료 코드 1로 중단한다(사용자 결정 2026-10-12. 이전에는 허용 역할 하나만 가진 표식 없는 계정의 비밀번호가 재설정되는 한계가 있었고 해소했다. 계정을 모두 변경 전에 검사하므로 하나라도 거부되면 다른 계정도 바뀌지 않고, 이 상태에서는 `superset`도 시작되지 않는다). 정리 방법은 아래 "표식 없는 기존 계정 정리"를 따른다. 새로 만들 계정의 이메일이 다른 계정과 겹쳐도 사전에 거부한다. 표식은 누가 같은 이름·표식으로 만든 계정도 복구 대상이 되므로 이름 충돌 점검은 운영 항목이다. **작성자 계정은 만들지 않는다**(관리자가 Superset에서 수동 생성하고 `bi_author`와 `bi_author_schema`를 준다. 내장 `Gamma`는 직접 주지 않는다).
- **비밀번호 변경**: `.env`의 `SUPERSET_SERVICE_PASSWORD`/`SUPERSET_GUEST_ISSUER_PASSWORD`를 바꾸고 `docker compose up -d`(`superset-init`이 다시 실행되어 반영). 비밀번호에 '%' 금지 규칙은 이 두 값에는 필요 없다(해시로 저장되고 URI에 들어가지 않는다). 다만 `$`, `#`, 따옴표, 공백 금지는 `.env` 공통 규칙이다.
- **이름 변경 금지**: 서비스 계정이 소유한 데이터셋은 계정 이름을 바꾸면(= 새 계정) 이전되지 않는다. 이름을 바꾸거나 계정을 교체하려면 소유자 이전 절차를 먼저 시험해야 한다(FU-1e). `SUPERSET_ADMIN_USER`·서비스·발급 이름이 서로 같으면(대소문자 무시) `superset-init`이 실패한다. 같은 이름의 기존 계정이 표식이 없으면(역할과 관계없이) 아무것도 바꾸지 않고 실패하고, 표식이 있으면 허용 밖 역할을 제거하는 강제 복구를 한다. 저장 뒤 비밀번호 해시가 `.env` 값과 맞는지 재읽기로 확인하며, 맞지 않으면 실패한다.
- 로그 확인: `docker compose logs superset-init`에서 `역할 …: 권한 N개 적용`, `계정 …: 만듦/갱신`, `bi_author: Gamma와 차이 없음` 또는 `점검 필요: 역할 bi_author`를 본다. **`경고:`(강제 복구)와 마지막 `점검 요약: 강제 복구 N건`을 찾는다**(0건이어도 매 기동 한 줄이 나온다. 1건 이상이면 누가 서비스·발급 계정에 허용 밖 역할을 붙였는지 확인한다). `/health`는 Superset 자체 엔드포인트이고 backend는 Superset 메타 DB를 읽지 않으므로 이 점검은 로그로만 한다.

### 표식 없는 기존 계정 정리 (`superset-init`이 계정 충돌로 실패할 때)
증상: `docker compose logs superset-init`에 `계정 <이름>은(는) 이미 있고 이 스크립트가 만든 계정 표식(이름 BI-Wizard, 이메일 <이름>@localhost)이 없어 덮어쓰지 않습니다(현재 역할: …)`가 나오고 종료 코드 1이다. 같은 이름의 기존 계정이 `.env`의 서비스·발급 계정 이름(`SUPERSET_SERVICE_USER`, `SUPERSET_GUEST_ISSUER_USER`)과 충돌한 것이다. 이 실행에서는 어떤 계정도 바뀌지 않았다(비밀번호 포함). 계정 하나만 보고 판단하지 말고 로그의 계정 이름을 확인한다.
- **(a) 충돌한 계정이 사람 계정이면**: 그 계정은 그대로 두고 `.env`의 `SUPERSET_SERVICE_USER`(또는 `SUPERSET_GUEST_ISSUER_USER`)를 다른 이름으로 바꾼 뒤 `docker compose up -d`. 새 이름으로 새 계정이 만들어진다. 서비스 계정 이름을 바꾸는 것이므로 이미 서비스 계정이 소유한 데이터셋이 있으면 이전되지 않는다(위 "이름 변경 금지", 첫 설치에서는 해당 없음).
- **(b) 충돌한 계정이 예전에 만든 서비스·발급 계정이면**(표식이 없는 이유: 수동 생성, 다른 도구로 생성, 이름·이메일 편집): **표식 보정을 권장한다.** Superset 관리 화면(Settings > List Users)에서 그 계정의 First Name을 `BI-Wizard`, Email을 `<이름>@localhost`로 맞추고 저장한 뒤 `docker compose up -d`. 관리 화면에 들어갈 수 없으면(`superset-init` 실패 중에는 `superset`이 시작되지 않는다) 같은 이미지의 일회성 컨테이너에서 앱 컨텍스트로 맞춘다(`<이름>`은 `.env` 값 그대로, 비밀번호는 다루지 않는다).
  ```
  docker compose run --rm --no-deps -T -e FIX_NAME=<이름> --entrypoint python superset-init - <<'EOF'
  import os
  from superset.app import create_app
  app = create_app()
  with app.app_context():
      sm = app.appbuilder.sm
      name = os.environ["FIX_NAME"]
      user = sm.find_user(username=name)
      if user is None:
          raise SystemExit("계정이 없습니다")
      user.first_name = "BI-Wizard"
      user.email = f"{name}@localhost"
      sm.update_user(user)
      print("표식 보정 완료:", name)
  EOF
  ```
  표식을 붙이면 다음 기동부터 그 계정은 `superset-init`이 관리하는 계정이 된다: 비밀번호가 `.env` 값으로 다시 맞춰지고 정해진 역할 하나만 남으며 그 밖의 역할(Admin 포함)은 강제 복구로 제거된다(`경고:` 로그). 사람이 쓰는 계정에는 하지 않는다.
- **계정 삭제 후 재기동**(Superset 관리 화면에서 계정 삭제 후 `docker compose up -d`)도 가능하지만 **권장하지 않는다.** 서비스 계정을 삭제하면 그 계정이 소유한 데이터셋은 소유자가 사라지고(`docs/decisions/08-superset-embedding.md` §2의 소유 서술), 같은 이름으로 다시 만든 계정은 새 계정이라 소유가 이어지지 않는다. 삭제는 소유한 데이터셋이 없는 것을 확인한 뒤에만 한다. 발급 계정은 데이터셋을 소유하지 않는다.
- 같은 이름이지만 이메일만 다른 경우(예: first_name은 `BI-Wizard`이나 이메일이 다름)도 표식 없음으로 거부된다. 위와 같이 보정한다. 새로 만들 계정의 이메일(`<이름>@localhost`)을 다른 계정이 이미 쓰고 있어 실패하는 경우도 그 계정의 이메일을 바꾸거나 `.env` 이름을 바꾼다.

### Superset 업그레이드 점검
Superset 이미지 버전을 올릴 때(6.1.0 고정 변경은 사용자 승인) 아래를 확인한다.
1. **`bi_author` 차이 점검(필수)**: `superset init`은 내장 `Gamma`에만 새 권한을 더하고 `bi_author`(복사본)는 갱신하지 않는다. 업그레이드 뒤 첫 기동의 `docker compose logs superset-init`에서 `점검 필요: 역할 bi_author이(가) Gamma와 다릅니다`가 나오면 **반드시** 로그에 적힌 권한 이름("Gamma에만 있음"/"bi_author에만 있음")을 확인하고 복사본에 반영할지(관리자가 Superset에서 수동 추가) 그대로 둘지 결정해 기록한다. 자동으로 바꾸지 않는다. `bi_author: Gamma와 차이 없음` 한 줄이면 점검할 것이 없다.
2. 권한 목록 이름 확인: 새 버전에서 `superset/bi_roles.py`(`bi_guest` 포함)의 권한 이름이 없어지거나 바뀌면 `superset-init`이 `없는 권한: …`으로 실패한다. 이름을 새 버전에 맞게 고치는 것은 권한 목록 변경이므로 사전 승인이 필요하다.
3. **`bi_guest` 4권한 스모크(필수)**: 새 버전은 임베딩 화면이 추가 권한을 요구할 수 있고 새 권한은 자동으로 추가되지 않는다. 지원 차트 6가지가 입장권으로 정상 표시되는지, `Public` 권한 0개와 훅 거부(`rls`·리소스 2개 → 400)가 유지되는지 확인하고 권한 목록 차이를 보고한다. 필요한 권한이 늘면 사용자 승인 뒤에만 목록에 추가한다.
4. 서비스 계정 4권한과 발급 계정 2권한 스모크(데이터셋 등록·CSRF·입장권 발급 허용, 서비스 계정의 입장권 발급 403), `sync_permissions` 동작(`SyncPermissionsCommand` 시그니처·비동기 설정), guest 권한과 지원 차트 6가지(`docs/decisions/08-superset-embedding.md` §3-1), 하위 경로(`APP_PROXY_STRIP_PREFIX` true/false)와 Embedded 재검증, `docs/deploy-coordination.md` 13·21번(로고 이중 접두, 404 일러스트) 해소 여부.

### db-bootstrap (DB 계정, `bi_data` schema, Superset 메타 DB)
`docker compose up`마다 일회성 `db-bootstrap`이 `backend/bootstrap/run.sh`를 실행해 `roles.sql`을 적용한다(멱등, `initdb.d` 미사용). 이미지 슈퍼유저로 접속하는 유일한 서비스다.
- 역할(`LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE`): `bi_owner`(마이그레이션 실행, `public` 정적 표와 `bi_data` 소유), `bi_app`(backend 런타임), `bi_readonly`(읽기 전용, `default_transaction_read_only=on`, `statement_timeout=30s`), `superset_meta`(Superset 메타 DB 소유). 데이터베이스 `superset`(소유 `superset_meta`). 이름은 코드 상수다.
- 속성 재차단(03b 14-1): `CREATE ROLE`은 역할이 없을 때만 실행되므로, 이미 있는 `bi_owner`·`bi_app`에는 매 기동 고정 문장 `ALTER ROLE … NOSUPERUSER NOCREATEDB NOCREATEROLE`을 다시 실행한다. 사람이 슈퍼유저·`CREATEDB`·`CREATEROLE`을 붙여도 다음 `docker compose up`에서 되돌아간다(로그인 속성·비밀번호·권한은 그대로). `bi_readonly`·`superset_meta`에는 이 문장이 없다.
- 빈 schema `bi_data`(소유자 `bi_owner`, PUBLIC 권한 없음): 사용자 데이터 표(`ds_*`)와 수식 뷰(`dv_*`, `de_*`)가 놓일 곳. `bi_data`의 `USAGE/CREATE/SELECT` 권한 부여는 db-bootstrap이 아니라 마이그레이션 `0002`가 한다.
- `GRANT bi_app TO bi_owner WITH INHERIT TRUE, SET FALSE`: `bi_owner`가 `bi_app`의 상속 멤버여야 마이그레이션이 `ALTER DEFAULT PRIVILEGES FOR ROLE bi_app …`을 실행할 수 있다(`SET ROLE bi_app`은 불가). 반복 실행하면 NOTICE만 난다.
- `public` schema: `bi_owner`에 `CREATE`를 주고 PUBLIC의 `CREATE`는 회수한다. Gate ② 볼륨의 `alembic_version` 소유자를 `bi_owner`로 바꾼다.
- 비밀번호 4개(`POSTGRES_READONLY_PASSWORD`, `SUPERSET_DB_PASSWORD`, `POSTGRES_APP_PASSWORD`, `POSTGRES_OWNER_PASSWORD`)를 바꾸면 다음 기동에서 반영된다. 하나라도 비어 있으면 실패한다. `POSTGRES_USER`가 위 역할 이름과 같으면 실패한다. 비밀번호 설정 문장이 실패해도 서버 오류 로그에 문장이 남지 않도록 `SET LOCAL log_min_error_statement = panic`을 쓴다. `roles.sql`의 psql 보간은 `PASSWORD :'var'` 4곳뿐이며 `scripts/ci-validate-env.sh`가 검사한다.
- 수동 재실행: `docker compose run --rm db-bootstrap`

### 인증 스텁 스위치 (`AUTH_STUB_ENABLED`)
- 기본 `false`. 스텁은 개발·시험에서만 켠다. `true`로 두려면 `.env`에 `APP_ENV=local`(또는 `test`)이 **명시**되어 있어야 한다. `.env.example`을 복사했다면 이미 `APP_ENV=local`이 들어 있다.
- `true`인데 `APP_ENV`가 없거나 비었거나 `local`/`test`가 아니면(예: `production`, `staging`, `Local`) backend는 서비스하지 않는다(compose에서는 `restart: unless-stopped` 때문에 종료와 재시작을 반복하고 포트는 열리지 않는다. `docker compose logs backend`에 "AUTH_STUB_ENABLED=true는 …" 오류). 판정은 `backend/app/config.py`, 시험은 `backend/tests/test_config.py`다.
- 운영 배포 설정에서는 `false`로 둔다. 켜졌을 때만 스텁 어댑터와 `/api/dev/*`(DV1~DV3)가 등록되고, 꺼져 있으면 경로가 없으며(404) 신원 어댑터도 없어 모든 업무 API가 401이다. 사용법과 시험용 사용자 시드는 `skills/permission-management/SKILL.md`다.

### 마이그레이션 왕복 테스트와 `alembic check` (tmpfs 테스트 DB)
빈 DB에서 `upgrade head → downgrade base → upgrade head`가 성공하고 권한 상태가 복원되는지 확인한다. 테스트 DB `postgres-test`는 compose profile `test`에만 있고 데이터가 tmpfs(256MB 제한)라 호스트에 포트를 열지 않는다. DB 접속은 `bi_owner`다.
```
docker compose --profile test up -d --wait postgres-test
docker compose --profile test run --rm --no-deps -e PGHOST=postgres-test db-bootstrap
docker compose --profile test run --rm --no-deps -e POSTGRES_HOST=postgres-test migrate python -m migrations.roundtrip
```
`migrations/roundtrip.py`가 한 번에 한다: 스냅샷 A(db-bootstrap 직후, base) → `upgrade head` → 스냅샷 B(권한 확인) → `alembic check` → `downgrade base` → 스냅샷 A′(A와 비교) → `upgrade head` → 스냅샷 B′(B와 비교). 스냅샷은 역할 속성·멤버십, schema/표 소유자와 ACL, **열 단위 ACL**(`pg_attribute.attacl`, `0003`의 `UPDATE (열)` 권한), 기본 권한(`pg_default_acl`), `public` 표·열·인덱스다. 단계 `정적 표 권한`은 `0003`의 `bi_app` 표·열 권한이 head에서 정확히 있고(`bi_readonly`·PUBLIC 없음) base에서는 없는지 확인한다. 정규화: schema ACL의 NULL과 소유자 명시의 차이, 비어 있는 `alembic_version`. 출력 `[roundtrip] … 통과`가 모두 나오고 종료 코드 0이면 통과다. DB의 현재 revision이 base가 아니면 아무것도 하지 않고 종료 코드 2로 끝난다(쓰고 있는 DB에서 `downgrade`를 돌리지 않는다).

개별 명령(필요할 때):
```
docker compose --profile test run --rm --no-deps -e POSTGRES_HOST=postgres-test migrate alembic upgrade head
docker compose --profile test run --rm --no-deps -e POSTGRES_HOST=postgres-test migrate alembic check
docker compose --profile test run --rm --no-deps -e POSTGRES_HOST=postgres-test migrate alembic downgrade base
docker compose --profile test run --rm --no-deps -e POSTGRES_HOST=postgres-test migrate alembic current
```
정리(둘 중 하나, 모두 `-v` 없음):
```
docker compose --profile test stop postgres-test
docker compose --profile test rm -f postgres-test     # 테스트 DB 컨테이너만 제거(tmpfs 데이터도 사라짐)
```
- 규칙: 모든 revision에 `downgrade()`를 구현하고 마이그레이션 안의 SQL은 보간 없는 고정 문자열만 쓴다. D5 의미: `downgrade()`는 `bi_data` schema 자체를 지우지 않는다(db-bootstrap 소유). 왕복 테스트는 "빈 DB로 돌아간다"가 아니라 정적 표와 권한 상태가 복원되는지를 본다. `0003`(`users`·`teams`·`team_members`)의 `downgrade()`는 표를 외래키 역순으로 `DROP`하므로 `tests/test_migrations.py`의 `DROP_APPROVED`에 기록이 있다.
- 자동 생성 초안(`alembic revision --autogenerate`)에 `DROP`이 있으면 적용하지 말고 사용자 확인을 받는다(D2: `public` 정적 표 대상). 동적 객체(`bi_data`의 `ds_*`, `dv_*`, `de_*`)는 `target_metadata`(`backend/app/db_metadata.py`, 정적 표만)와 `include_name`/`include_object` 필터로 비교에서 제외되어 삭제 후보에 섞이지 않는다. 권한(GRANT)은 `alembic check`가 잡지 못하므로 위 스냅샷 비교로 확인한다.
- 새 revision은 `backend/migrations/versions/`에 둔다. head는 항상 하나여야 한다(DB 없이 pytest가 검사: `alembic heads`가 둘이면 병합 revision이 필요). 마이그레이션 실행은 `migrate` 서비스뿐이며 앱 코드는 시작 때 마이그레이션을 하지 않는다.

## 6. 관련 UI / API / command / DB
- UI: 포털 `${APP_BASE_PATH}/`(Gate ②에서는 API/DB 상태 표시뿐), Superset `${SUPERSET_APP_ROOT}/`
- API (브라우저 쪽 경로 기준, 권한 관리 API는 `skills/permission-management/SKILL.md`):
  - `GET ${APP_BASE_PATH}/api/health` — FastAPI 상태. 본문 `{status, app, views, views_failed_count, public_create, db_timezone}`: 앞 두 개는 프로세스 상태, 나머지 네 개는 **시작 자가 점검이 채운 메모리 값**이라 DB에 접속하지 않는다(`views`·`views_failed_count` 지금은 0, `public_create`는 `bi_app`이 `public`에 CREATE 권한이 있는지로 정상은 `false`, `db_timezone`은 DB 시간대). 공개 응답이라 개수·불리언·시간대만 담고, 뷰 실패가 있어도 200이다
  - `GET ${APP_BASE_PATH}/api/health/db` — PostgreSQL `SELECT 1` (정상 200, 실패 503)
  - `GET ${SUPERSET_APP_ROOT}/health` — Superset (`OK`)
  - 공통: 모든 `/api` 응답에 `X-Request-ID` 헤더가 붙는다. 이 두 health 경로만 인증 없이 열려 있고, 그 밖의 `/api` 경로는 `current_user`를 거쳐 신원 어댑터가 없으면 401 `UNAUTHENTICATED`다(신원 방식은 미결정 8번이라 어댑터는 `AUTH_STUB_ENABLED=true`일 때만 스텁이 연결된다). 오류는 `{"error": {"code", "message", "details", "request_id"}}` 형식이고 `request_id`는 헤더와 같다. 장애 때 이 id로 `docker compose logs backend`를 찾는다.
- command: `scripts\*.bat`, `docker compose …`, `alembic …`(migrate 서비스 안)
- DB: 앱 DB(`POSTGRES_DB`: `public`에 `alembic_version`과 정적 표 `users`·`teams`·`team_members`, 빈 schema `bi_data`), 메타 DB `superset`, 역할 `bi_owner`/`bi_app`/`bi_readonly`/`superset_meta`

## 7. 실패 시 확인 방법
| 증상 | 원인 | 확인과 해결 |
| --- | --- | --- |
| `required variable … is missing a value` | `.env`에 변수가 없거나 비어 있음 | `scripts\validate-env.bat`이 이름을 알려 준다 |
| 포트 사용 중 | `FRONTEND_PORT`, `POSTGRES_PORT`, `BACKEND_PORT` 충돌 | `.env`의 포트를 바꾸고 `restart-local.bat` |
| `db-bootstrap` 실패 | 비밀번호 변수 4개 중 하나가 비어 있음, `POSTGRES_USER`가 역할 이름과 같음, 또는 `POSTGRES_PASSWORD`가 볼륨 생성 때 값과 다름 | `docker compose logs db-bootstrap`. `POSTGRES_PASSWORD`는 DB 볼륨이 처음 만들어질 때만 적용된다. 값을 되돌리거나 psql에서 `\password`로 바꾼다 |
| `migrate` 실패 | `POSTGRES_OWNER_PASSWORD` 불일치·누락, `db-bootstrap`이 먼저 성공하지 않음(`bi_owner`·`bi_data` 없음) | `docker compose logs migrate`. `.env`의 비밀번호를 고치고 `docker compose up -d`(db-bootstrap이 비밀번호를 다시 맞춘다) |
| `backend`가 시작하지 않음 | `migrate` 실패, `POSTGRES_APP_PASSWORD` 누락, `AUTH_STUB_ENABLED=true`인데 `APP_ENV`가 `local`/`test`가 아님, 또는 **시작 자가 점검 거부**(`bi_app`에 SUPERUSER·CREATEROLE·CREATEDB·REPLICATION·BYPASSRLS 속성이 있음, `bi_data`에 표·뷰·인덱스·제약·Identity 시퀀스 밖의 객체가 있음, `standard_conforming_strings`가 off, 정적 표·열이 DB에 없음). DB가 아직 안 올라왔으면 2초 간격 10회 재시도한 뒤 실패 | `docker compose logs migrate backend`. 원인을 고치고 `docker compose up -d` |
| `superset-init` 실패 | 메타 DB 접속 실패, 키 누락, 계정 변수 누락·이름 중복, 표식 없는 기존 계정과의 이름 충돌("표식 없는 기존 계정 정리"), `GUEST_TOKEN_JWT_EXP_SECONDS`가 300이 아님, `없는 권한: …`(역할 목록의 권한이 Superset에 없음), 권한 동기화 실패, `migrate` 실패로 시작하지 않음 | `docker compose logs superset-init`(실패 단계 이름 바로 앞 `[superset-init]` 줄을 본다). `없는 권한`이 `schema_access`이면 `POSTGRES_DB` 값과 업무 데이터 연결 이름이 `sync_permissions` 단계의 결과와 같은지 확인 |
| `up`이 `SUPERSET_SERVICE_PASSWORD`(또는 발급 계정 변수) `is missing a value`로 멈춤 | 예전 `.env`에 EW-3 변수 4개가 없음 | `.env.example`에서 4줄을 추가하고 비밀번호 2개를 채운다(`scripts\validate-env.bat`이 이름을 알려 준다) |
| 로그에 `점검 필요: 역할 bi_author` | Superset 업그레이드 등으로 `Gamma`의 권한이 바뀜 | 위 "Superset 업그레이드 점검" 1번 |
| Superset 404 | 프록시가 접두를 뗐거나 `SUPERSET_APP_ROOT`가 다름 | Superset 경로는 접두를 유지해야 한다. `.env`의 값과 접속 주소 확인 |
| Superset 로고 이미지 404(경로에 접두가 두 번 붙음), `static/service-worker.js` 404 | Superset 6.1.0 하위 경로 동작과 이미지 구성. 화면 기능에는 영향이 없다 | Superset 내부 코드는 수정하지 않는다. 알려진 사항이며 대안은 개발 에이전트가 보고한다 |
| Superset 로그인 화면에서 접두 없는 일러스트 이미지 요청이 404(404 페이지 그림). 올바른 경로 `${SUPERSET_APP_ROOT}/static/assets/<해시>.png`는 200 | 알려진 Superset 6.1.0 현상(이미지 요청 경로에 접두가 빠짐). 접두 밖 요청이 이제 404로 드러난다 | 화면 기능에는 영향이 없다. Superset 내부 코드는 수정하지 않는다 |
| Embedded iframe이 "Something went wrong with embedded authentication"으로 실패 | **하위 경로 때문이 아니다.** guest 역할(`GUEST_ROLE_NAME`)에 권한이 없거나 역할이 없으면 `GET ${SUPERSET_APP_ROOT}/api/v1/me/roles/`가 403·500을 낸다(기본값 `Public`은 권한이 0개라 실패한다). 공식 Embedded SDK README도 guest가 `GUEST_ROLE_NAME` 역할로 동작한다고 설명한다 | EW-4부터 `GUEST_ROLE_NAME=bi_guest`(4권한)이고 `superset-init`이 매 기동 만든다. `docker compose logs superset-init`에서 `역할 bi_guest: 권한 4개 적용`을 확인한다. 권한을 임의로 늘리지 않는다(사용자 승인 필요) |
| Superset이 갑자기 502/지연 후 복구 | 메모리 한도 초과로 컨테이너가 재시작됨(137) | `docker compose ps`, `docker stats --no-stream`, `docker compose logs superset` |
| `docker compose stop`/`restart` 때 `superset`이 10초쯤 걸리고 exit 137로 끝남 | **알려진 현상**(03b 14-1 ②): `superset`(gunicorn)이 SIGTERM에 반응하지 않아 stop 유예 10초 뒤 강제 종료된다. 원인 미확인, 기능 영향 없음, compose는 바꾸지 않았다 | 조치 없음. 메모리 초과(137 + 재시작)와 구별하려면 `docker inspect -f '{{.State.OOMKilled}}' <컨테이너>`가 `false`인지 본다 |
| 포털에서 API 오류 | 경로 값 불일치, backend 비정상 | `health-check.bat`, `docker compose logs backend frontend` |
| BAT 출력이 영어다 | 일부 Windows cmd에서 UTF-8 BAT가 `goto` 레이블 탐색을 깨뜨릴 수 있어 BAT는 ASCII(영문)로만 쓴다 | 정상이다. 설명은 이 문서와 README에 있다. 성공은 `[OK]`, 실패는 `[FAIL]`, `.env` 검사는 `[MISSING]`/`[EMPTY]`로 표시한다 |
| BAT가 이상하게 동작 | 줄바꿈이 LF로 바뀜 | `.gitattributes`가 BAT를 CRLF로 고정한다. 저장소를 다시 체크아웃 |
| 컨테이너가 메모리 부족으로 종료(137) | `mem_limit` 초과 | `docker stats --no-stream`. 한도 조정은 `docs/decisions/03a-deploy-environment.md`를 따른다 |

## 8. 검증 방법
- 자동 테스트: backend `docker build --target test backend`(ruff, pytest), frontend `docker build --target test frontend`(eslint, tsc, vitest). Jenkins도 같은 명령을 쓴다. 이 빌드에는 PostgreSQL이 없어 **`pg` 변형(실제 DB 시험: 정적 표 권한 매트릭스, 시작 자가 점검, LAST_ADMIN 경쟁)은 건너뛴다.** 실제 DB 시험은 tmpfs 테스트 DB(`postgres-test`)에 연결해 따로 실행한다: `skills/permission-management/SKILL.md`의 "검증 방법".
- 구성 검증: `docker compose config --quiet`
- 수동: `scripts\health-check.bat`이 모두 `[OK]`이고 마지막에 `All checks passed.`를 출력하며 `docker compose ps`에서 상시 서비스가 `healthy`.
- Superset 계정·역할: `docker compose logs superset-init`에 `bi_service` 4개, `bi_guest_issuer` 2개, `bi_author_schema` 1개, `bi_guest` 4개, `bi_author` 새로 만듦 또는 `Gamma와 차이 없음`, 계정 2개, 마지막 `점검 요약: 강제 복구 N건`이 나오고 종료 코드 0. `GUEST_TOKEN_JWT_EXP_SECONDS`가 300이 아니면 `superset-init`은 실패한다(`설정 GUEST_TOKEN_JWT_EXP_SECONDS가 … 입니다`). 표식 없는 기존 계정과 이름이 충돌해도 실패한다. `Public` 역할 권한은 0개이고 발급 계정으로 `rls`가 비어 있지 않은 입장권 요청은 400이다. 서비스 계정으로 `…/api/v1/security/csrf_token/`·`/api/v1/dataset/`는 200, `/api/v1/database/`와 입장권 발급(`guest_token`)은 403, 발급 계정은 입장권 발급 권한이 있다. 로그에 비밀번호가 없다.
- 읽기 전용 계정: `bi_readonly`로 `SELECT 1`은 되고 `CREATE TABLE`·`INSERT`는 거부된다. `statement_timeout`은 30초다.
- 계정 분리: backend 컨테이너의 환경에 `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_OWNER_PASSWORD`가 없고(`docker compose config`), `/api/health/db`가 정상이며 `pg_stat_activity`의 backend 접속 계정이 `bi_app`이다. `bi_app`은 `public`에 `CREATE TABLE`, `SET ROLE bi_owner`, `alembic_version` 조회가 거부되고 `bi_data`에는 표·뷰를 만들 수 있다. 마이그레이션 왕복 테스트(`python -m migrations.roundtrip`) 통과.
- 정적 검사(Docker 없이): `sh scripts/ci-validate-env.sh`(변수 목록·계정 분리·backend에 `GUEST_TOKEN_JWT_SECRET` 없음·`superset_config.py`의 `GUEST_ROLE_NAME`/`PUBLIC_ROLE_LIKE`·`roles.sql` 규칙·frontend에 `ag-grid-enterprise`/`ag-charts-enterprise` 없음과 의존성 정확한 버전 고정), `sh scripts/test-ci-validate-env.sh`(그 검사의 네거티브 케이스).
- 두 가지 `APP_PROXY_STRIP_PREFIX` 값 모두에서 `${APP_BASE_PATH}/api/health`가 응답하고 backend 접근 로그의 경로가 각각 `${APP_BASE_PATH}/api/health`, `/api/health`다.
- BAT 실행 검증은 사용자 Windows PC에서 한다(AI 세션은 Linux라 실행하지 않는다).
- 메모리 실측: `docker stats --no-stream`(결과는 `docs/deploy-coordination.md` 5번에 기록).

## 9. 연관 Skill
- `.claude/skills/env-bootstrap`: 이 환경을 만들고 점검하는 개발용 절차(Environment Ready 체크리스트)
- `.claude/skills/qa-verification`: 기동과 Health 검증 절차
- `.claude/skills/product-skill-authoring`: 이 Skill의 작성 형식
- `skills/permission-management`: `/health` 새 필드·시작 자가 점검·스텁 스위치의 사용 쪽(최초 관리자 명령, `/api/dev/*`, 실제 DB 시험 방법)
- 업무 기능 Skill(`skills/<기능>/SKILL.md`)은 모두 이 환경이 통과한 상태를 사용 조건으로 삼는다.
