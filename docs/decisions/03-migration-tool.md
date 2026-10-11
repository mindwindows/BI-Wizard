# 03. DB 마이그레이션 도구와 실행 방식

- Gate: ② ENVIRONMENT BOOTSTRAP
- 결정일: 2026-10-11 (사용자 결정)
- 근거 조사: architect의 후보 비교안(2026-10-11, 검색요약 기반, reviewer 검증 전). 비교 근거는 아래 "비교 근거 요약"에 옮겼고, 초안 원문 파일은 삭제했다(내용은 `git show 3b239e7:docs/drafts/gate2-migration-tool-options.md`로 볼 수 있다).
- 운영 가이드 근거: "기존 ORM/Migration 구성이 있으면 유지하고 신규 프로젝트에서만 필요한 조합을 제안한다". 이 저장소에는 마이그레이션 구성이 없어 신규 제안 대상이었다. 브리프와의 충돌은 없다.

## 결정

| 번호 | 항목 | 결정 | 상태 |
| --- | --- | --- | --- |
| D1 | 마이그레이션 도구 | **Alembic** | 결정 |
| D7 | Superset 메타데이터 DB | **같은 PostgreSQL 컨테이너 안의 별도 데이터베이스**로 둔다. Superset이 업무 데이터(수식 뷰 등)를 읽는 데이터 연결은 **읽기 전용 DB 계정**을 쓴다 | 결정 |
| D4 | 마이그레이션 실행 위치 | backend 이미지를 재사용하는 **일회성 `migrate` 서비스**를 둔다. `backend`는 `migrate`가 **성공 완료된 뒤에만** 시작하도록 `depends_on`(`condition: service_completed_successfully`)을 건다 | 결정 |
| D3 | 마이그레이션의 raw SQL 허용 범위 | **마이그레이션 디렉터리 안에서만** 고정 SQL 문(`op.execute` 등)을 허용한다. **변수 보간(f-string, `%`, `.format()`, `+` 연결)은 금지**한다. 그 밖의 코드는 기존 SQL 문자열 조립 금지 규칙을 그대로 따른다 | 결정 |
| D2 | 동적 객체(사용자 데이터셋 테이블, 수식 뷰) 분리 방식 | **Gate ③ 데이터 모델 설계 때 결정**한다. 그때까지 Alembic 자동 생성 초안에 `DROP` 문이 포함되면 **적용 전에 반드시 사용자 확인**을 받는다 | 연기 (Gate ③) |
| D5 | 되돌리기 정책 | **모든 마이그레이션에 `downgrade`를 작성**하고, 빈 DB에서 **upgrade → downgrade → upgrade 왕복 테스트**로 검증한다. 운영 중 문제는 되돌리기가 아니라 **수정 마이그레이션 추가**로 대응한다 | 결정 |
| D6 | 빈 DB 검증 방식 | 왕복 테스트용 빈 DB는 **데이터를 tmpfs에 두는 테스트 전용 PostgreSQL 서비스**로 만들고, **compose profile**로 평소에는 띄우지 않는다. 정리는 **`-v` 없는 `docker compose down`** 으로 한다. **Jenkins에서의 적용 방식은 Jenkins 실행 환경(Docker 사용 가능 여부)을 확인한 뒤 정한다** | 결정 (Jenkins 적용은 추후) |

## 구현 지침 (결정에서 따라 나오는 것)

### 실행 구성 (D4, D6, D7)
- `migrate`: backend 이미지를 재사용하고 `alembic upgrade head`를 실행한 뒤 종료한다. `restart`는 하지 않는다. `postgres`의 `service_healthy` 이후에 시작한다.
- `backend`: `depends_on`에 `migrate`의 `service_completed_successfully`와 `postgres`의 `service_healthy`를 건다. `migrate`가 실패하면 `backend`는 시작하지 않는다.
- 테스트 DB: `postgres-test`(이름은 예시)를 `profiles: ["test"]`로 정의한다. 데이터 디렉터리는 `tmpfs`다. `docker compose --profile test up -d postgres-test`로 띄우고 `docker compose --profile test down`으로 정리한다. 볼륨 삭제 옵션은 쓰지 않는다. tmpfs는 메모리를 쓰므로 크기를 제한한다.
- Superset 메타데이터: 같은 PostgreSQL 컨테이너 안의 **별도 데이터베이스**다. 우리 앱의 DB와 `alembic_version` 테이블이 섞이지 않는다. Superset의 업그레이드(`superset db upgrade`, `superset init`)는 Superset 쪽 절차이며 우리 Alembic의 범위 밖이다.
- Superset의 업무 데이터 연결은 **읽기 전용 계정**을 쓴다. 이 계정에는 Superset이 읽어야 하는 객체에 대한 `SELECT`만 준다.

### 마이그레이션 작성 규칙 (D3, D5, D2)
- 마이그레이션 파일은 마이그레이션 디렉터리(제안: `backend/migrations/`) 안에만 둔다. env-engineer가 구성할 때 이 경로를 확정하고, 바뀌면 `bi-review` 규칙의 경로를 함께 고친다.
- 허용: `op.*`, SQLAlchemy 표현식, **보간이 전혀 없는 고정 SQL 문자열**(`op.execute("CREATE ...")` 등. 뷰·확장은 autogenerate가 다루지 않으므로 이 방식으로 수동 작성한다).
- 금지: SQL에 변수를 끼워 넣는 모든 방식(f-string, `%`, `.format()`, `+` 연결). 사용자 입력이나 환경변수를 SQL 문자열에 넣지 않는다.
- 마이그레이션 디렉터리 밖의 코드는 기존 규칙(SQL 문자열 조립 금지, SQLAlchemy 표현식 사용)을 그대로 따른다.
- 모든 revision에 `downgrade()`를 작성한다. `downgrade`는 개발·테스트 환경의 왕복 검증용이며 운영 DB에서 문제 대응으로 쓰지 않는다. 운영 중 문제는 수정 마이그레이션을 추가한다.
- **D2 안전장치:** 자동 생성 초안에 `DROP`(`op.drop_table`, `op.drop_column`, `op.drop_index`, `op.drop_constraint`, SQL의 `DROP` 등)이 있으면 적용하기 전에 사용자에게 확인받고, 확인했다는 기록을 변경 요약(커밋 메시지 등)에 남긴다. 스키마 비교형 도구는 "DB에 있고 모델에 없는 테이블"을 삭제 후보로 보므로, 사용자가 런타임에 만든 데이터셋 테이블이 삭제 후보로 섞일 수 있다.

### 읽기 전용 계정과 Superset 메타 DB 생성 방식 (2026-10-11 승인)

근거(공식 소스에서 확인): 공식 postgres 이미지는 `/docker-entrypoint-initdb.d`를 데이터 디렉터리가 비어 있을 때만 실행한다(`docker-entrypoint.sh`). `CREATE ROLE`에는 `IF NOT EXISTS`가 없고 비밀번호는 `PASSWORD '리터럴'`만 받는다(바인드 불가). psql은 변수를 SQL 리터럴·식별자로 인용하는 `:'var'`·`:"var"`와 환경변수를 읽는 `\getenv`, 조건부 실행 `\gexec`을 제공한다(PostgreSQL 16 문서). `ALTER DEFAULT PRIVILEGES`는 `FOR ROLE`을 생략하면 현재 역할이 만드는 객체에 적용된다.

- **매 기동 멱등 `db-bootstrap` 서비스:** postgres 클라이언트 이미지로 `docker compose up`마다 실행한다. `initdb.d`는 쓰지 않는다(볼륨이 이미 있으면 다시 실행되지 않기 때문). 슈퍼유저(`POSTGRES_USER`)로 접속해 `backend/bootstrap/`의 스크립트와 `roles.sql`을 실행한다.
- **실행 순서:** `postgres`(healthy) → `db-bootstrap`(성공 완료) → `migrate` → `backend`. `superset-init`도 `db-bootstrap` 완료 후 실행한다. 테스트 DB(profile `test`)에도 같은 스크립트를 적용한다.
- **이름은 코드 상수로 고정:** 읽기 전용 역할 `bi_readonly`, Superset 메타 역할 `superset_meta`, Superset 메타 DB `superset`. 환경변수는 비밀번호만 `POSTGRES_READONLY_PASSWORD`, `SUPERSET_DB_PASSWORD`로 받는다. 이름 변수는 두지 않는다.
- **D3 예외(승인):** `backend/bootstrap/`의 SQL에서 **비밀번호 리터럴 두 곳에 한해** psql `:'var'` 인용 보간을 허용한다. **식별자 보간(`:"var"`, `format('%I')` 포함)과 구문 보간은 금지**한다. 나머지 SQL은 모두 고정 문장이다. 비밀번호 변수는 `\getenv`로 읽고, 비어 있으면 실패한다(fail closed).
- **안전장치:** `bi_readonly`에 `ALTER ROLE … SET default_transaction_read_only = on`을 설정한다.
- **권한 부여 시점:** `bi_readonly`의 `SELECT` 권한(`USAGE ON SCHEMA`, `ALTER DEFAULT PRIVILEGES … GRANT SELECT … TO bi_readonly`)은 D2와 함께 Gate ③ 마이그레이션에서 고정 SQL로 쓴다. 이름이 상수라서 D3와 충돌하지 않는다.
- **Superset 데이터 연결:** `superset-init`이 `set_database_uri`(6.1.0 CLI)로 `bi_readonly` 연결을 등록한다. URI의 비밀번호는 URL 인코딩한다.
- **앱 계정 (조건부 승인):** Gate ②에서는 `POSTGRES_USER`를 앱·migrate 계정으로 쓴다(운영 가이드 기준선). 최소 권한 앱 계정 분리는 Gate ③에서 D2와 함께 설계하고, **Gate ④ 진입 전 분리 완료가 필수**이며, Gate ④에서 backend가 슈퍼유저로 접속하면 `bi-review`가 차단한다. 계정을 나눌 때 `ALTER DEFAULT PRIVILEGES`의 `FOR ROLE` 생략 방식도 다시 정한다(`FOR ROLE`을 생략하면 마이그레이션을 실행하는 역할과 런타임 DDL을 실행하는 역할이 같아야 한다).
- **마이그레이션 디렉터리:** `backend/migrations/`(승인).

## 비교 근거 요약

비교한 후보와 판정(근거 수준: 모두 검색요약이며 페이지 원문은 열람하지 못했다).

| 후보 | 라이선스 판정 | 핵심 사유 |
| --- | --- | --- |
| **Alembic** (선택) | 허용형 (MIT) | SQLAlchemy와 같은 계열이라 backend 이미지에 pip 패키지만 추가하면 되고 새 런타임이 없다. `include_object`·`include_name`·`include_schemas` 훅으로 동적 객체를 걸러 낼 수 있다. `alembic check`, 다중 head 병합 절차로 CI 검사가 가능하다 |
| Atlas Community | Community는 허용형(Apache 2.0), 공식 배포 바이너리는 Ariga EULA(주의) | 뷰·확장·RLS는 Pro 전용, `migrate down` 없음, 별도 이미지·HCL·임시 DB 필요 |
| Flyway Community | **불명확** (소스는 Apache 2.0 표기, Redgate 글은 "freeware / Subscription EULA") | JVM 필요, Community에는 undo 없음 |
| dbmate | 허용형 (MIT) | 가볍지만 모델 기준 자동 생성이 없어 어긋남 검사를 따로 만들어야 한다 |
| `create_all` 기준선 | SQLAlchemy(MIT) | 이미 있는 테이블의 변경을 적용하지 못하고 이력·CI 검사가 없어 이 프로젝트에 부족하다 |
| Liquibase (부록) | **비추천** | 5.0(2025-09-30 발표)부터 Functional Source License로 변경(교차 일치) |
| golang-migrate, Sqitch, yoyo-migrations, pgroll (부록) | golang-migrate는 출처마다 표기 상이(불명확), 나머지는 이점이 적어 제외 | |

**Alembic의 알려진 약점** (결정에 반영된 대응):
- 뷰는 autogenerate가 다루지 않아 수동 작성이 필요하다 → D3(고정 SQL 허용).
- `downgrade()`는 도구가 보장하지 않는다 → D5(모든 revision에 작성 + 왕복 테스트).
- 두 브랜치가 동시에 마이그레이션을 추가하면 head가 갈라져 병합 파일이 필요하다 → CI에서 head 개수 검사를 넣는 것을 구현 단계에서 확정한다.
- `include_schemas` 기본 동작은 공식 문서 원문으로 확인하지 못했다 → D2 결정 후 빈 DB와 동적 객체가 있는 DB 양쪽에서 `alembic check`로 검증한다.

**D2 후보 옵션** (Gate ③에서 비교·결정): S 별도 PostgreSQL schema, N 이름 규칙 + 필터, R 등록 테이블 기반 필터(비추천 쪽), D 별도 DB. 어떤 옵션이든 마이그레이션 도구의 모델 메타데이터에는 정적 모델만 넣는 설계를 데이터 모델과 함께 정한다. 수식 → 뷰 변환 규칙이 바뀔 때 기존 뷰를 다시 만드는 문제(마이그레이션이 앱 코드를 호출 / 앱 시작 시 정의 해시 비교 조정 / 관리 명령)도 Gate ③에서 함께 정한다.

## 확인하지 못한 항목

- 페이지 원문을 열람하지 못했다. Alembic 1.18.4(2026-02-10)와 Flyway 13.8.0(2026-09-24)은 단일 출처이고, 여러 릴리스 날짜가 미확인이다.
- Alembic `include_schemas` 기본 동작의 공식 문구, PostgreSQL 동시 마이그레이션 잠금 동작.
- `service_completed_successfully`의 Podman 계열 지원(`podman-compose`, Podman의 `docker compose` provider). 개발자 PC가 Podman이면 **사용자 PC 검증 대상**이다.
- Windows 경로 bind mount 동작(마이그레이션 파일을 컨테이너에서 호스트로 가져오는 경로).
- Jenkins 에이전트의 Docker 사용 가능 여부 (D6의 Jenkins 적용을 정하기 위한 선행 확인).
- Superset 내부 Alembic과 `alembic_version` 테이블 충돌 가능성은 D7(별도 데이터베이스)로 피한다. Superset의 팀 웹서버 운영 조건은 브리프 5절 4번에서 결정됐다(`docs/decisions/03a-deploy-environment.md`: 정식 서비스, Redis/Valkey 제외, 하위 경로 배포, 메모리 8GB).
- 코드나 설정을 실행해 검증한 항목은 없다. 학습 비용은 모두 추정이다.

## 하네스 반영

이 결정에 맞춰 다음 파일을 수정했다(CLAUDE.md 변경 이력 참고): `.claude/agents/env-engineer.md`, `qa-engineer.md`, `architect.md`, `.claude/skills/env-bootstrap`, `qa-verification`, `backend-fastapi`, `bi-review`, `feature-unit`, `modularize`, `bi-wizard-dev`.
