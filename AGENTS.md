# AGENTS.md — 환경·Skill·변경 규칙

사람과 모든 AI 도구가 같은 규칙을 읽는다. 요구사항 기준은 `docs/project-brief.md`, 운영 가이드는 `docs/AI_AGENT_DEVELOPMENT_GUIDE_요약.md`(브리프와 충돌하면 운영 가이드가 우선하고 충돌 사실을 사용자에게 알린다)다. 브리프 5절의 미결정 사항은 임의로 정하지 말고 사용자에게 묻는다. 현재 상태는 `docs/gate-status.md`다.

## 1. 환경 (Gate ② 결과)
- **실행 진입점은 루트 `compose.yml` 하나다.** 시작 `docker compose up -d --build`, 종료 `docker compose down`. 같은 동작의 Windows BAT는 `scripts/`에 있다. 사용법과 문제 해결은 `skills/local-environment/SKILL.md`를 읽고 추측하지 않는다.
- 서비스: `postgres`, `db-bootstrap`(일회성), `migrate`(일회성), `backend`, `frontend`, `superset-init`(일회성), `superset`, 그리고 profile `test`의 `postgres-test`(tmpfs). 순서는 `postgres → db-bootstrap → migrate → backend`, `db-bootstrap + migrate → superset-init → superset`(`superset-init`이 `migrate`를 기다리는 것은 `bi_readonly`의 `bi_data` USAGE를 주는 마이그레이션 `0002`와의 순서 경쟁을 막기 위해서다. 순환은 없다).
- 모든 서비스에 `mem_limit`이 있다(합계 8GB 안, `docs/decisions/03a-deploy-environment.md`). 한도는 `compose.yml`에 고정하고 변수화하지 않는다. Redis/Valkey/Celery는 두지 않는다(필요해지면 사용자와 재논의).
- Health: `${APP_BASE_PATH}/api/health`(본문 `status`, `app`, `views`, `views_failed_count`, `public_create`, `db_timezone`: 뒤 네 개는 backend 시작 자가 점검과 뷰 대조(FU-1d: 활성 데이터셋마다 정의 해시를 `datasets.def_hash`와 대조해 다른 뷰만 다시 만들고 실패해도 시작은 막지 않음)가 채운 메모리 값이라 DB 비접속, 공개 응답에는 개수·불리언·시간대만), `${APP_BASE_PATH}/api/health/db`, `${SUPERSET_APP_ROOT}/health`. `/health/azure-openai`는 만들지 않는다. **backend 시작 자가 점검(FU-1a):** `bi_app` 접속 역할에 SUPERUSER·CREATEROLE·CREATEDB·REPLICATION·BYPASSRLS 중 하나라도 있거나 `public` schema CREATE 권한이 있으면(`/health`의 `public_create`가 `true`, 경고가 아니라 거부), `bi_data`에 표·뷰·인덱스·제약(과 열이 소유한 Identity 시퀀스) 밖의 객체가 있으면, `standard_conforming_strings`가 off이거나 정적 표·열이 DB에 없으면 시작을 거부한다.
- **DB 계정 분리(EW-1, Gate ② 한정 구성 해소):** Gate ②에서는 `POSTGRES_USER`(이미지 슈퍼유저)를 앱·`migrate` 계정으로 썼다(한정 구성). 이제 `POSTGRES_USER`/`POSTGRES_PASSWORD`는 **이미지 슈퍼유저 전용**(postgres 이미지, healthcheck, `db-bootstrap`)이고 `backend`·`migrate`는 이 계정으로 접속하지 않는다. `migrate`=`bi_owner`(정적 표·`bi_data` 소유), `backend`=`bi_app`(정적 표는 명시 GRANT만, `bi_data`에만 `CREATE`)이며 계정 이름은 코드 상수(`backend/app/db.py`)다. 이것은 운영 가이드 기준선(`POSTGRES_USER`=앱 계정)과의 **의도적 차이**다(`docs/deploy-coordination.md` 29번). backend가 슈퍼유저로 접속하는 구성은 리뷰에서 차단된다.
- 이 환경이 통과한 상태(Environment Ready)가 기능 개발의 전제다.
- frontend의 nginx 마스터가 root로 실행되는 것은 **의도적 선택**(공식 nginx 이미지 기본)이다. 필요하면 `nginx-unprivileged` 이미지로 전환할 수 있다.
- `FRONTEND_HOST` 기본값은 `127.0.0.1`이다(Superset 관리자 로그인이 LAN에 노출되지 않게). 컨테이너 내부 바인딩 변수(`BACKEND_HOST` 등)와는 다른 의미다.
- Superset 텔레메트리(Scarf)는 `superset/superset_config.py`가 CSP에서 `scarf.sh` 호스트를 제거해 막는다(`SCARF_ANALYTICS` 환경변수는 6.1.0에서 효과가 없어 쓰지 않는다). gunicorn은 워커 1개이며 주기적 재시작(`WORKER_MAX_REQUESTS`)을 쓰지 않는다.

## 2. 환경변수
- `.env.example`이 이름 기준 원본이다. 운영 가이드의 canonical name(`APP_*`, `FRONTEND_*`, `BACKEND_*`, `POSTGRES_*`, `LOG_LEVEL`, `TZ`)을 그대로 쓰고, 같은 의미의 새 이름을 만들지 않는다. 환경별 이름 분리(`LOCAL_DB_HOST` 등) 금지: 이름은 고정하고 값만 바꾼다.
- Azure OpenAI 변수(`AZURE_OPENAI_*`)는 없다(브리프 5절 1번: 제외). LLM 사용이 생기면 사용자 승인 후에만 추가한다.
- 이 프로젝트의 추가 변수(현재 `.env.example` 30개): `APP_BASE_PATH`, `APP_PROXY_STRIP_PREFIX`, `AUTH_STUB_ENABLED`, `SUPERSET_APP_ROOT`, `POSTGRES_APP_PASSWORD`, `POSTGRES_OWNER_PASSWORD`, `POSTGRES_READONLY_PASSWORD`, `SUPERSET_DB_PASSWORD`, `SUPERSET_SECRET_KEY`, `GUEST_TOKEN_JWT_SECRET`, `SUPERSET_ADMIN_USER`, `SUPERSET_ADMIN_PASSWORD`, `SUPERSET_SERVICE_USER`, `SUPERSET_SERVICE_PASSWORD`, `SUPERSET_GUEST_ISSUER_USER`, `SUPERSET_GUEST_ISSUER_PASSWORD`(EW-3). 역할 `bi_owner`·`bi_app`·`bi_readonly`·`superset_meta`, 메타 DB `superset`, schema `bi_data`의 **이름은 코드 상수**이며 변수로 만들지 않는다(환경변수는 비밀번호만 받는다).
- **인증 스텁 스위치 `AUTH_STUB_ENABLED`**(기본 `false`, 승인 AP-13): `true`는 개발·시험 전용이다. 켜져 있으면 `APP_ENV`가 환경변수로 **명시적으로 설정**(코드 기본값 `local`이 채운 것은 미설정으로 본다)되어 있고 값이 `local`·`test`일 때만 backend가 시작하며, 아니면 시작을 거부한다(fail-closed, `backend/app/config.py`, `test_config.py`). 시험용 사용자 시드를 운영 마이그레이션에 넣지 않는다. 스텁 로그인 기능은 FU-1a에서 만든다(지금은 스위치만 있다).
- **Superset 계정·역할(EW-3·EW-4):** `superset-init`이 매 기동 멱등으로 만든다(`superset/ensure_roles.py`, `ensure_accounts.py`, 앞 단계 `sync_permissions.py`). 권한 목록은 `superset/bi_roles.py` 한 곳에만 둔다(흩뿌리지 않는다). 역할: `bi_service`(4개, `can_grant_guest_token` 금지), `bi_guest_issuer`(2개), `bi_author`(처음 만들 때만 Gamma 복사, 이후 차이는 로그로 알리기만), `bi_author_schema`(1개), `bi_guest`(4개: `can_read CurrentUserRestApi`·`Dashboard`·`Chart`, `can_time_range Api`. 내보내기·쓰기·Explore·SQL Lab·`can_explore_json`·퍼머링크 읽기는 금지이고 새 권한은 자동 추가하지 않는다). 서비스·발급 계정은 역할 하나만 갖고 관리자 역할을 갖지 않으며, 작성자 계정은 만들지 않는다(관리자가 수동). **서비스 계정 이름은 바꾸지 않는다**(소유 데이터셋 이전 절차 미확정). 세 계정 이름(관리자·서비스·발급)은 서로 달라야 한다(`ci-validate-env.sh`와 스크립트가 검사). 비밀번호는 환경변수로만 받고 인수·로그·예외 메시지에 넣지 않는다. 서비스·발급 변수는 backend와 `superset-init`에만 전달한다(`ci-validate-env.sh`가 검사). backend의 Superset 내부 주소 `http://superset:8088`은 코드 상수(`backend/app/config.py`)이며 변수로 만들지 않는다. 새 권한 목록 변경은 사전 승인이 필요하다.
- **guest 역할·검증 훅(EW-4):** `superset_config.py`의 `GUEST_ROLE_NAME = "bi_guest"`는 `bi_roles.GUEST_ROLE`과 같은 값을 따로 적은 것이고 `ensure_roles.py`가 실제 적용된 설정과 비교해 어긋나면 `superset-init`을 실패시킨다(`ci-validate-env.sh`도 정적으로 확인). `ensure_roles.py`는 `Public` 역할 권한 0개와 `PUBLIC_ROLE_LIKE` 미설정도 확인하고 어기면 고치지 않고 실패한다. `GUEST_TOKEN_VALIDATOR_HOOK`(`superset_config.py`)은 발급 API(`POST /api/v1/security/guest_token/`)에서만 불리며 `rls` 비어 있지 않음·리소스 1개 아님·유형 `dashboard` 아님·리소스 id가 uuid 형식 아님(숫자 id·slug)·`user` 누락을 400으로 거부한다(포털 DB를 읽지 않음, 로그에는 사유 코드만). "포털 등록 표의 embedded uuid만 허용" 검사는 FU-1e에서 훅의 확장 지점에 넣는다. **backend에는 `GUEST_TOKEN_JWT_SECRET`을 전달하지 않고 입장권을 직접 서명하지 않는다**(훅 우회, `ci-validate-env.sh`가 compose와 `backend/app`을 검사). 입장권 유효 시간은 Superset 기본 5분이며 바꾸지 않는다: `ensure_roles.py`가 실제 적용된 `GUEST_TOKEN_JWT_EXP_SECONDS`가 `bi_roles.GUEST_TOKEN_EXP_SECONDS`(300)인지 0단계에서 확인해 다르면 실패하고(설정에 없으면 통과), `ci-validate-env.sh`는 `superset_config.py`의 재정의를 막는다. 바꾸려면 사전 승인 후 가드 값과 함께 바꾼다.
- **서비스·발급 계정 강제 복구(EW-4, 사용자 결정 2026-10-12):** 표식(first_name `BI-Wizard`, email `<이름>@localhost`)이 있는 기존 계정에 허용 밖 역할이 붙어 있으면 제거하고 정해진 역할 하나로 되돌리며 `경고:` 로그와 `점검 요약: 강제 복구 N건`을 남긴다. 표식 없는 기존 계정과 이름이 충돌하면 역할과 관계없이(허용 역할 하나만 가져도) 비밀번호 재설정 없이 아무것도 바꾸지 않고 실패한다(EW-5, 사용자 결정 2026-10-12). 정리 절차는 `skills/local-environment/SKILL.md`의 "표식 없는 기존 계정 정리".
- **새 변수를 추가할 때** 이 순서로 영향을 확인하고 변경 요약(커밋 메시지)에 기록한다.
  1. `.env.example` (이름, 주석, Secret이면 빈 값)
  2. backend Settings (`backend/app/config.py`) 와 테스트
  3. `compose.yml` — 필요한 서비스의 `environment:`에만 넣는다
  4. `scripts/ci-validate-env.sh`의 `REQUIRED`(Secret이면 `SECRETS`도)와 `Jenkinsfile`(Credential 매핑이 필요한지)
  5. `scripts/validate-env.bat`, `README.md`, `skills/local-environment/SKILL.md`
  6. 테스트
- **Secret**(DB 비밀번호, Superset 키, 관리자·서비스·발급 계정 비밀번호)은 Repository, Dockerfile, 이미지, Frontend 번들, 로그에 넣지 않는다. `.env`는 Git 제외다. **Frontend 컨테이너에는 전체 `.env`를 넘기지 않는다**(공개 설정만 `environment:`에 명시). 컨테이너마다 필요한 변수만 전달한다.

## 3. 하위 경로 배포와 프록시
- 포털은 메인 플랫폼의 URL 하위 경로로 서비스된다. 프런트 API 호출은 `${basePath}/api/…`(호스트 없는 상대경로)이고 `/api`, `/superset`, `/bi-wizard`를 코드에 하드코딩하지 않는다(`/api` 구간은 `frontend/src/config.ts` 한 곳).
- 경로 값 규칙: 앞 `/` 필수, 뒤 `/`·`//`·`.`/`..` 세그먼트·개행 금지. **빈 값(루트 배포)은 `APP_BASE_PATH`에만 허용**하고 `SUPERSET_APP_ROOT`는 비울 수 없다. 검증은 `backend/app/config.py`, `frontend/src/config.ts`, nginx 시작 스크립트, `scripts/ci-validate-env.sh`가 같은 규칙으로 한다.
- `APP_PROXY_STRIP_PREFIX`(기본 `false`)로 포털의 접두 처리(유지/제거)를 **설정값만으로** 전환한다. 코드를 바꾸거나 이미지를 다시 빌드하지 않는다.
- **Superset 경로는 접두를 떼지 않고 그대로 전달한다**(Superset 6.1.0 요구). 이미지 태그 `6.1.0`을 바꾸지 않는다. 하위 경로 지원은 공식 문서상 BETA이므로 문제가 보이면 **Superset 내부 코드를 수정하지 말고** 대안과 영향을 정리해 보고한다.
- 로컬 검증 값은 `/bi-wizard`, `/bi-wizard/superset`이다. 실제 값은 웹서버 배포 때 관리자와 정하며, 배포 때 맞출 항목은 `docs/deploy-coordination.md`에 모은다.

## 4. 마이그레이션과 DB 계정 (`docs/decisions/03-migration-tool.md`)
- 도구는 **Alembic**, 위치는 `backend/migrations/`. 실행은 일회성 `migrate` 서비스(`alembic upgrade head`)뿐이며 앱 코드는 시작 때 마이그레이션이나 `create_all`을 하지 않는다.
- 마이그레이션 안의 SQL은 **보간 없는 고정 문자열만** 쓴다(f-string, `%`, `.format()`, `+` 금지). 모든 revision에 `downgrade()`를 구현하고 빈 DB 왕복 테스트(`upgrade → downgrade → upgrade`)로 검증한다. 운영 중 문제는 되돌리기가 아니라 수정 마이그레이션 추가로 대응한다.
- **`DROP`이 있는 마이그레이션(자동 생성 초안 포함)은 적용하지 않고 사용자 확인을 받는다**(D2 안전장치, `public` 정적 표 대상. `revision`의 `downgrade()`에 있는 `op.drop_table`도 해당). 확인했다면 변경 요약에 "DROP 확인: 사용자 승인"을 남기고 `backend/tests/test_migrations.py`의 `DROP_APPROVED`에 기록한다.
- DB 계정(`bi_owner`, `bi_app`, `bi_readonly`, `superset_meta`), 빈 schema `bi_data`(소유자 `bi_owner`), Superset 메타 DB는 `db-bootstrap`(`backend/bootstrap/`)이 만든다. `initdb.d`를 쓰지 않는다. **D3 예외 2:** `roles.sql`의 psql `:'var'` 인용은 **비밀번호 리터럴(`PASSWORD :'var'`) 4곳**(`POSTGRES_READONLY_PASSWORD`, `SUPERSET_DB_PASSWORD`, `POSTGRES_APP_PASSWORD`, `POSTGRES_OWNER_PASSWORD`)에만 허용하고 식별자 보간(`:"var"`, `format('%I')`)과 구문 보간은 금지다. 비밀번호는 `\getenv`로 읽고 비면 실패한다(fail closed). 역할·DB·schema 이름은 상수 리터럴이다. db-bootstrap 고정 SQL에는 승인된 `GRANT bi_app TO bi_owner WITH INHERIT TRUE, SET FALSE`(마이그레이션이 `ALTER DEFAULT PRIVILEGES FOR ROLE bi_app`을 쓰려면 필요), `bi_owner`의 `public` `CREATE`, `bi_readonly`의 `statement_timeout = '30s'`가 들어 있다. 또한 매 기동 기존 `bi_owner`·`bi_app`의 속성을 재차단하는 고정 문장 `ALTER ROLE … NOSUPERUSER NOCREATEDB NOCREATEROLE`(03b 14-1, 권한 축소, 보간 없음)이 있다. `superset-init`은 일회성이라 `healthcheck: disable: true`로 종료 뒤 `unhealthy` 표시를 막는다. `backend/migrations/`와 `backend/bootstrap/`(승인된 예외) 밖의 raw SQL은 금지이고, SQL 문자열 조립은 어디서도 금지다(SQLAlchemy 표현식 사용). `roles.sql`의 정적 규칙은 `scripts/ci-validate-env.sh`가 검사하고 그 네거티브 케이스는 `scripts/test-ci-validate-env.sh`가 시험한다.
- `bi_data`의 `USAGE/CREATE`(`bi_app`)와 `bi_readonly`의 읽기 권한(`USAGE`, 기본 권한 `SELECT`)은 마이그레이션 `0002_bi_data_privileges`가 `bi_owner`로 부여한다(고정 SQL). 동적 객체(`ds_*`, `dv_*`, `de_*`)는 마이그레이션 대상이 아니다: `target_metadata`는 정적 표 `MetaData`(`backend/app/db_metadata.py`) 하나이고 `include_name`/`include_object`가 `bi_data`와 동적 객체 이름을 제외한다(D2 안전장치는 `public` 정적 표의 `DROP` 대상). 왕복 테스트는 `python -m migrations.roundtrip`(테스트 DB), D5 의미는 "권한 상태 복원"이다.
- `0003_users_teams_members`(FU-1a): 정적 표 `users`·`teams`·`team_members`와 `bi_app` 명시 GRANT(표 단위 SELECT/INSERT, `team_members`는 DELETE도, UPDATE는 열 단위: `users`의 `display_name`·`is_admin`·`is_active`, `teams`의 `name`·`is_active`, `team_members`의 `role`). `login_id`·`code`·`team_id`·`user_id`는 DB가 변경을 막는다. `bi_readonly`에는 아무 권한도 없다. `downgrade()`는 표를 외래키 역순으로 `DROP`하며 `tests/test_migrations.py`의 `DROP_APPROVED`에 기록이 있다. 최초 관리자는 서버 명령 `python -m app.cli create-admin`(`skills/permission-management/SKILL.md`)으로 만든다.
- `0004_datasets_columns`(FU-1b): 정적 표 `datasets`·`dataset_columns`(순환 FK `fk_datasets_id_dataset_columns`는 표 생성 뒤 `create_foreign_key`로 추가)와 `bi_app` 명시 GRANT(표 단위 SELECT/INSERT, DELETE 없음, UPDATE는 열 단위: `datasets`의 `name`·`date_unit`·`base_date_column_id`·`status`·`def_version`·`def_hash`, `dataset_columns`의 `display_name`·`type`·`required`·`rules`·`tag`·`position`). `team_id`·`created_by`·`created_at`와 `dataset_id`·`kind`는 DB가 변경을 거부한다. `downgrade()`는 순환 FK를 끊고 표를 역순으로 `DROP`하며 `DROP_APPROVED`에 기록이 있고, `bi_data`의 `ds_*`는 건드리지 않는다. `ds_<번호>` 원본 표는 런타임 동적 DDL 모듈 `backend/app/ddl/`(SQLAlchemy 내장 DDL 구문·Alembic `Operations`만, `text()`·`exec_driver_sql` 금지, 이름은 번호 규칙 함수로만, 객체 종류는 표·뷰·인덱스·제약)이 `bi_app`으로 만든다.
- `0005_formulas`(FU-1d): 정적 표 `formulas`(열마다 수식 하나: 보관용 `expression`, 열 번호 참조 `ast`, `ast_hash`)·`formula_deps`(자기 참조 CHECK)와 `bi_app` 명시 GRANT(`formulas`는 SELECT·INSERT와 열 단위 UPDATE(`expression`·`ast`·`ast_hash`), DELETE 없음; `formula_deps`는 SELECT·INSERT·DELETE). `downgrade()`는 두 표를 역순으로 `DROP`하고 `DROP_APPROVED`에 기록이 있다. 뷰 `dv_<번호>`·`de_<번호>`는 자기 `ds_<번호>`만 읽어 정적 표 `downgrade`를 막지 않는다. 뷰는 정의 변경 훅(`backend/app/formula/hook.py`)이 `bi_app`으로 `ddl.create_view`(허용 목록 게이트: 자기 `ds_<번호>`만 읽음·허용 SQL 함수 목록 `VIEW_ALLOWED_FUNCTIONS`·글자 바인드의 금지 문자 방어 중복, 렌더 글자와 `CreateView` 대조와 확인 질의 모양·값 확인은 **DB 실행 전**, 그리고 생성 후 재읽기 확인, `skills/formula-column`)를 통해서만 만들고, backend 엔진은 연결 때 `standard_conforming_strings=on`을 고정한다(`startup_params`).
- FU-1c(`backend/app/entry/`, 입력 그리드 C1~C4)는 **새 revision이 없다**: `ds_<번호>` 행 읽기·쓰기는 DML이라 SQLAlchemy 표현식만 쓰고(`text()` 금지, 열 이름은 `c_<번호>` 규칙 함수), 행 쓰기는 `datasets` 행을 `FOR SHARE`로 잡는다(`skills/data-entry/SKILL.md`). 붙여넣기 상한 5,000행·1MiB는 코드 상수다. **`downgrade` 뒤에는 `bi_data.ds_*`를 `skills/admin-cleanup`으로 정리한 뒤 다시 `upgrade`한다**(`datasets`의 번호가 1부터 다시 시작해 `ds_1 already exists`가 난다).
- `0006_superset`(FU-1e): 정적 표 `superset_datasets`(데이터셋마다 Superset 동기 상태 한 줄: `superset_dataset_id`, `display_name`, `sync_status` CHECK(`pending`·`registered`·`failed`), `synced_at`, `last_error`)·`superset_dashboards`(포털 `id` ↔ 임베드 `embedded_uuid`, 유일·소문자 정규형 CHECK, `is_active`)와 `bi_app` 명시 GRANT(두 표 모두 SELECT·INSERT와 열 단위 UPDATE: `superset_datasets`는 `superset_dataset_id`·`display_name`·`sync_status`·`synced_at`·`last_error`, `superset_dashboards`는 `name`·`is_active`; `dataset_id`·`id`·`embedded_uuid`·`created_at`은 DB가 변경을 막고 DELETE 없음). `bi_readonly`·Superset에는 공개하지 않는다. `downgrade()`는 두 표를 `DROP`하며 `DROP_APPROVED`에 기록이 있다. backend는 `backend/app/superset/`에서 서비스 계정으로 가상 데이터셋을 등록하고(고정 SQL `SELECT * FROM bi_data.dv_<번호>` 한 가지, `naming.virtual_sql` 한 곳) 발급 전용 계정으로 입장권을 요청한다(`skills/dashboard-link/SKILL.md`). 요청 처리 중에는 Superset을 부르지 않고 단일 작업 스레드가 처리하며, `httpx==0.28.1`(전이 `httpcore`, `certifi` MPL-2.0 이름 예외)은 `skills/local-environment/SKILL.md`에 표로 기록했다.

## 5. 라이선스
- 허용형만 쓴다: MIT, BSD, Apache 2.0, PSF, PostgreSQL License. `ag-grid-enterprise`, AGPL, GPL, EUPL, Sustainable Use License, Redis 7.4 이후 라이선스는 금지다. 불분명하면 쓰지 말고 질문한다.
- 의존성을 추가하면 PyPI/npm 메타데이터로 라이선스를 확인해 변경 요약에 쓴다. 의존성은 버전을 고정한다(`backend/requirements*.txt`, `frontend/package-lock.json`). 이미지 태그에 `latest`를 쓰지 않는다.
- LGPL인 `psycopg2`/`psycopg`는 backend에 쓰지 않는다(backend는 pg8000, BSD-3). Superset 이미지(`superset/Dockerfile`)에만 `psycopg2-binary`를 둔다.

## 6. Skill 규칙
- 사용자 관점의 주요 기능마다 `skills/<기능>/SKILL.md`를 둔다(형식: `.claude/skills/product-skill-authoring`). 현재는 `skills/local-environment/`, `skills/permission-management/`(FU-1a), `skills/dataset-definition/`(FU-1b), `skills/data-entry/`(FU-1c), `skills/formula-column/`(FU-1d), `skills/dashboard-link/`(FU-1e)와 수동 운영 절차 `skills/admin-cleanup/`다.
- **Feature Code ↔ Skill ↔ 연관 Skill ↔ 회귀 테스트는 함께 바뀐다.** 코드나 환경만 바꾸고 Skill을 갱신하지 않으면 완료로 보지 않는다. 환경을 바꾸면 `skills/local-environment/SKILL.md`, `README.md`를 같은 작업에서 고친다.
- `.claude/`(개발 에이전트 정의)와 `skills/`(제품 사용설명서)는 다른 것이다.

## 7. 검증 명령
```
sh scripts/ci-validate-env.sh && sh scripts/test-ci-validate-env.sh   # 변수 목록·계정 분리·roles.sql 규칙·AG Grid Enterprise 혼입 방지와 frontend 의존성 정확한 버전 고정, 그 네거티브 케이스(Docker 불필요)
docker compose config --quiet                       # 구성 (CI는 sh scripts/ci-validate-env.sh 로 만든 더미 env 사용)
docker build --target test backend                  # ruff check/format, pytest (PostgreSQL 필요한 pg 변형은 건너뜀)
# 실제 PostgreSQL 시험: skills/permission-management/SKILL.md "검증 방법". 시험 실행 환경에 REQUIRE_PG=1을 주면
# PG 환경이 없을 때 pg 변형이 건너뛰지 않고 실패한다(CI 전용 시험 옵션, .env·.env.example·compose에는 넣지 않는다)
docker build --target test frontend                 # eslint, tsc, vitest
docker compose up -d --build && docker compose ps   # 기동 (Windows: scripts\start-local.bat, scripts\health-check.bat)
```
CI는 `Jenkinsfile`이다: Checkout → Env Validation → Backend Lint/Test → Frontend Lint/Test/Build → `docker compose config` → Docker Build. 앞 단계가 실패하면 뒤 단계는 실행하지 않는다.

## 8. 하지 않는 일
- `.env` 삭제, `rm -rf`, `git clean -fdx`, `git reset --hard`, `docker compose down -v`(볼륨 삭제)를 실행하거나 스크립트·문서에 쓰지 않는다. 필요하면 먼저 사용자에게 묻는다.
- `main`에 직접 커밋하거나 푸시하지 않는다.
- Dockerfile에서 `apt-get`을 쓰지 않는다. 특정 PC·세션에서만 필요한 빌드 우회(CA 인증서 등)는 저장소에 넣지 않는다.
- `scripts/*.bat`는 ASCII(영문)만 쓰고 CRLF, BOM 없음으로 유지한다. AI 세션(Linux)에서는 BAT를 실행하지 않는다. BAT 실행 검증은 사용자 Windows PC에서 한다.
- Superset 내부 코드를 수정하지 않는다(설정과 공식 CLI만 쓴다).
