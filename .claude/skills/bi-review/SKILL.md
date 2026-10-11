---
name: bi-review
description: BI-Wizard 변경 사항을 읽기 전용으로 리뷰하는 체크리스트와 보고 형식. 라이선스, 환경변수, Secret, SQL 조립, 마이그레이션(변수 보간, DROP 확인, downgrade), Enterprise 패키지, 코드와 Skill 동기화, 미결정 사항 준수를 점검한다. reviewer 에이전트가 사용한다. 리뷰어는 파일을 수정하지 않는다.
---

# bi-review — 읽기 전용 리뷰 기준

## 원칙
- 리뷰어는 코드, 테스트, 설정, 문서를 수정하지 않는다. 발견 사항과 수정 방향만 보고한다.
- 근거 없는 지적을 하지 않는다. 모든 발견 사항에 파일과 줄 번호를 붙인다.
- 문제가 없으면 "발견 없음"과 점검한 항목을 적는다.

## 입력
메인이 변경 파일 목록과 diff를 `_workspace/review/`에 넣어 준다. 리뷰어에게 Bash가 없으므로 git 명령을 직접 실행하지 않는다.

## 점검 항목

### 1. 라이선스 (차단)
- 새로 추가된 패키지의 라이선스와 **위치**(운영 런타임 / 개발·테스트 전용 / 업스트림 공식 이미지 내부)를 확인한다. 허용형은 MIT, BSD, Apache 2.0, PSF, PostgreSQL License다.
- **원칙(사용자 결정, 2026-10-11):** 운영 런타임에 포함되는 우리 코드의 의존성은 허용형만 사용한다. 개발·테스트 전용 도구와 업스트림 공식 이미지 내부 구성요소는 약한 카피레프트(LGPL, MPL)를 수정·재배포하지 않는 조건으로 허용한다. GPL·AGPL·EUPL 등 강한 카피레프트와 비오픈소스 라이선스는 위치와 관계없이 금지한다.
- 차단: `ag-grid-enterprise`, AGPL, GPL, EUPL 등 강한 카피레프트, Sustainable Use License 등 비오픈소스, Redis 7.4 이후 라이선스(위치와 관계없이). 우리 코드의 **운영 런타임 의존성**에 LGPL·MPL이 새로 들어오면 차단이다.
- LGPL·MPL이 개발·테스트 전용이거나 업스트림 공식 이미지 내부라면 허용한다. 단 `docs/deploy-coordination.md`의 "배포 전 회사 오픈소스 정책 확인" 표에 없는 새 항목이면 추가를 요청한다(중요). 해당 패키지를 수정·재배포(포크, 패치, 번들)하는 흔적이 있으면 차단이다.
- 라이선스가 불분명하면 "불명확 (확인 필요)"로 중요 항목에 올린다.

### 2. Secret (차단)
- 키, 비밀번호, 토큰이 코드, 이미지 설정, 프런트 번들, 로그, 문서에 들어가지 않았는지 확인한다.
- `.env` 파일이 커밋 대상에 포함되지 않았는지 확인한다.

### 3. SQL 조립 (차단)
- 문자열 연결, f-string, `%` 포맷, `.format()`으로 SQL을 만들지 않았는지 확인한다.
- SQLAlchemy 표현식을 썼는지 확인한다.
- **예외(D3, `docs/decisions/03-migration-tool.md`):** 마이그레이션 디렉터리(`backend/migrations/`) 안에서만 **보간이 전혀 없는 고정 SQL 문**(`op.execute("...")` 등)을 허용한다. 마이그레이션 안에서도 변수 보간은 차단이다.
- **예외 2(부트스트랩, 승인 2026-10-11):** `backend/bootstrap/`의 SQL에서만 **비밀번호 리터럴**(`PASSWORD :'var'`: `POSTGRES_READONLY_PASSWORD`, `SUPERSET_DB_PASSWORD`, 그리고 3라운드에서 승인된 앱 계정용 `POSTGRES_APP_PASSWORD`, `POSTGRES_OWNER_PASSWORD`. 2026-10-11 문구 변경 승인, EW-1에서 구현됨)에 한해 psql의 `:'var'` 인용 보간을 허용한다. 비밀번호는 `\getenv`로 읽고 비어 있으면 실패해야 한다. **식별자 보간(`:"var"`, `format('%I')` 포함)과 구문 보간, 비밀번호 외 값의 보간은 차단**이다. 역할·DB 이름(`bi_readonly`, `superset_meta`, `superset`)은 상수 리터럴이어야 한다.
- 위 두 경로(`backend/migrations/`, `backend/bootstrap/`) 밖의 raw SQL은 예외 없이 차단이다.

### 4. 환경변수 (중요)
- `.env.example`의 canonical name과 맞는지 확인한다.
- 사용자가 승인한 목록 밖의 새 변수가 있으면 승인 기록(`docs/gate-status.md`, `docs/decisions/`)이 있는지 확인한다. 기록이 없으면 중요 항목이다("새 환경변수 추가는 적용 전에 사용자 승인" 규칙).
- 같은 의미의 새 이름이 생기지 않았는지 확인한다.

### 5. 경계 (중요)
- 브라우저 코드가 DB나 Superset 내부를 직접 호출하지 않는지 확인한다.
- API 주소가 `APP_BASE_PATH` 기준 상대경로(`${APP_BASE_PATH}/api`)인지 확인한다. `/api`, `/superset`, `/bi-wizard` 같은 경로가 코드에 하드코딩되어 있으면 중요 항목이다(하위 경로 배포, `docs/decisions/03a-deploy-environment.md`).
- Superset 경로는 접두를 떼지 않고 그대로 전달하는 구성인지 확인한다. 포털의 접두 처리는 설정값만으로 전환되는지 본다.

### 6. Skill 동기화 (중요)
- 기능 코드가 바뀌었는데 `skills/<기능>/SKILL.md`가 갱신되지 않았다면 완료로 보지 않는다.
- 연관 Skill의 영향도를 확인했는지 본다.

### 7. 미결정 사항 (차단)
- 브리프 5절의 미결정 항목을 임의로 정한 흔적이 없는지 확인한다. `docs/gate-status.md`의 미결정 표가 현재 상태의 정본이다.
- 수식 범위(2번), 생성 권한(3번), 수식 평가 경로(6번), Explore 제공 방식(7번), 포털 사용자 인증과 신원 출처(8번), 동시 편집 정책(9번), Superset 데이터셋·대시보드 등록 방식(10번), 삭제 정책(11번)이 승인 전에 설계 문서나 코드에 확정되어 있으면 차단 항목이다. `docs/gate-status.md`의 미결정 표가 정본이다.
- 결정된 Superset 운영 조건(4번)을 어기면 차단이다: Redis/Valkey 또는 Celery 서비스를 사용자 승인 없이 추가, Superset 이미지를 `6.1.0`이 아닌 태그로 변경, Superset 내부 코드 수정(브리프 4.6), 서비스에 `mem_limit` 누락 또는 한도 합계가 8GB 초과(`docs/decisions/03a-deploy-environment.md`).
- 결정된 항목을 어기면 차단이다. Azure OpenAI(1번)는 "제외"로 결정됐으므로 `AZURE_OPENAI_*` 변수, `/health/azure-openai`, Azure OpenAI 호출 코드가 사용자 승인 없이 들어 있으면 차단한다. 디자인(5번) 결정은 `docs/decisions/01-design-direction.md`를 따른다.

### 7-1. 마이그레이션 (D2·D3·D5·D4·D6·D7, `docs/decisions/03-migration-tool.md`)
- **D3 (차단):** 마이그레이션 파일에서 `op.execute`, `text()`, `connection.execute` 등에 넘기는 SQL 문자열에 f-string, `%`, `.format()`, `+` 연결이 있는지 확인한다. 하나라도 있으면 차단이다. 마이그레이션 디렉터리 밖에서 raw SQL을 쓰면 차단이다(점검 항목 3).
- **D2 안전장치 (차단):** 마이그레이션에 `DROP`(`op.drop_table`, `op.drop_column`, `op.drop_index`, `op.drop_constraint`, SQL의 `DROP` 등)이 있는지 확인한다. 있으면 **사용자 확인 기록**(커밋 메시지나 변경 요약의 "DROP 확인: 사용자 승인" 문구)이 있는지 본다. 기록이 없으면 차단이다. D2는 2026-10-11 AP-11 승인으로 **`public` 정적 표 마이그레이션의 `DROP`에 적용**한다(`bi_data` 동적 객체는 마이그레이션 대상이 아니므로 `include_name`/`include_object`로 제외되어 있어야 하고, 삭제 대상에 섞이면 차단). revision의 `downgrade()`에 있는 `op.drop_table`도 DROP이므로 `DROP_APPROVED` 기록(기존 D2 규칙의 적용일 뿐 새 승인이 아님)이 필요하다.
- **D5 (중요):** 모든 revision에 `downgrade()`가 실제로 구현되어 있는지(`pass`, `NotImplementedError`만 있으면 미구현) 확인한다. upgrade → downgrade → upgrade 왕복 테스트 결과(qa-engineer 보고)가 첨부되어 있는지 본다. 운영 문제를 되돌리기로 해결하라는 문구나 스크립트가 있으면 지적한다(수정 마이그레이션 추가가 원칙). **예외:** 업무 객체가 아직 없는 baseline revision은 사유를 적은 의도적 no-op(`return None`)을 허용한다. 첫 실제 객체를 만드는 revision부터는 실질적인 `downgrade()` 구현을 요구한다.
- **D4 (중요):** `compose.yml`에 backend 이미지를 재사용하는 일회성 `migrate` 서비스가 있고, `backend`가 `migrate`의 `service_completed_successfully`에 의존하는지 확인한다.
- **D6 (중요):** 테스트용 PostgreSQL 서비스가 `tmpfs` 데이터이고 compose profile로 평소에는 뜨지 않는지 확인한다. 정리 방법이 `-v` 없는 `docker compose down`인지 본다(점검 항목 8과 같이).
- **D7 (중요):** Superset 메타데이터가 우리 앱 DB와 **별도 데이터베이스**(`superset`, 소유 `superset_meta`)인지, Superset이 업무 데이터를 읽는 연결이 **읽기 전용 계정**(`bi_readonly`, 쓰기 권한 없음, `default_transaction_read_only=on`)인지 확인한다. Superset 연결 문자열이나 설정에 앱 DB 소유자 계정이 쓰이면 차단이다.
- **db-bootstrap (중요):** 매 기동 멱등으로 실행되는 일회성 서비스이고(`initdb.d` 미사용), `postgres`(healthy) → `db-bootstrap` → `migrate` → `backend` 순서가 `depends_on`으로 걸려 있는지 확인한다. 스크립트가 두 번 실행해도 오류가 없도록 `\gexec` 조건부 생성 + `ALTER ROLE … PASSWORD`로 작성됐는지 본다.
- **앱 계정 (차단, EW-1 구현 완료 2026-10-11):** backend는 `bi_app`, migrate는 `bi_owner`(코드 상수)로만 접속한다. backend·migrate에 이미지 슈퍼유저 변수(`POSTGRES_USER`, `POSTGRES_PASSWORD`)나 상대 계정의 비밀번호가 전달되거나 슈퍼유저로 접속하면 **차단**이다. 마이그레이션의 `ALTER DEFAULT PRIVILEGES FOR ROLE bi_app`은 db-bootstrap의 승인된 `GRANT bi_app TO bi_owner WITH INHERIT TRUE, SET FALSE`가 있을 때만 쓴다.
- **접두 처리 변수 (중요):** `APP_PROXY_STRIP_PREFIX`의 기본값이 `false`(접두 유지 전달)인지, `true`/`false` 두 값 모두 로컬에서 검증됐는지 확인한다.
- 마이그레이션 도구는 Alembic이다. 다른 도구(Flyway, Atlas 등)나 앱 시작 시 `create_all`로 스키마를 만드는 코드가 새로 들어오면 사용자 승인 여부를 확인한다.

### 7-2. Superset Embedded guest 역할 (차단, 2026-10-11 결정)
- 운영 설정(`superset/superset_config.py`, `compose.yml`, `.env.example`, 초기화 스크립트)에서 `GUEST_ROLE_NAME`을 `Gamma`나 `Public`으로 지정하거나, `PUBLIC_ROLE_LIKE`를 설정하면 차단이다. 이 금지는 **임베딩 대시보드를 보는 guest 역할에만 적용**된다(2026-10-11 사용자 확정). 운영 guest 역할은 최소 권한 커스텀 역할이어야 한다(권한 목록은 Gate ③ 4라운드 G에서 정의). 포털 작성자 역할은 내장 `Gamma`를 사용자에게 직접 부여하지 않고 **`Gamma`를 복사한 커스텀 역할 + schema 단위 데이터 접근 보조 역할**로 만든다(내장 `Gamma` 직접 부여는 차단). 시험 전용 override 파일(`_workspace/`)의 Gamma 대조 실험은 운영 설정이 아니므로 대상이 아니다.
- **guest 권한 목록 파일(AP-1, 2026-10-11 승인):** `bi_guest` 권한 목록은 저장소의 파일 한 곳에 있고(필수 3 + 기간 필터 1, 조건부 2는 기본 제외), `Public` 권한은 0개여야 하며 `GUEST_ROLE_NAME`은 `bi_guest`다. 목록에 없는 권한이 역할에 있거나, 목록의 권한이 Superset에 없는데 시작이 막히지 않으면 차단이다. **서버 코드(backend)가 guest token을 직접 서명하거나 `GUEST_TOKEN_JWT_SECRET`을 backend에 전달하면 차단**이다(검증 훅 우회, 03c X-28). `rls`는 서버 코드가 항상 빈 목록으로 고정한다.
- Scarf 호스트가 CSP에 다시 들어갔는지, 효과 없는 `SCARF_ANALYTICS` 변수가 다시 생겼는지 확인한다(중요).

### 7-3. 사실 확인 교차 검증 (Gate ③, 요청 시)
- `_workspace/gate3/facts.md`의 `확인됨` 항목은 출처, 문서 버전, 확인일, 원문 인용이 있고 인용이 `_workspace/gate3/sources/` 발췌와 일치해야 한다. 근거가 없거나 인용이 발췌와 다르면 중요 항목이다.
- 우리 버전(PostgreSQL 16, Superset 6.1.0 등)과 다른 버전의 문서를 근거로 삼았다면 그 사실이 적혀 있는지 본다.
- 사실 확인에 설계안·추천이 섞여 있으면 지적한다.

### 7-4. 런타임 동적 DDL (차단, 2026-10-11 4라운드 결정 Z7)
- 서비스가 실행 중에 사용자 데이터 표·뷰를 만들고 바꾸고 지우는 코드는 **SQLAlchemy 내장 구성요소**(`CreateTable`, `DropTable`, `CreateIndex`, `CreateView`, `DropView`, Alembic `Operations` 등)만 쓰고 **한 모듈 안에만** 둔다. 그 모듈 안에서도 `text()`와 `exec_driver_sql`로 SQL 문자열을 실행하거나 f-string·`%`·`.format()`·`+`로 SQL을 조립하면 차단이다. 모듈 밖에서 `literal_binds`를 쓰는 것도 차단이다.
- 이름은 번호로 만든 이름(`ds_<번호>`, `dv_<번호>`)만 쓴다. 만들 수 있는 **객체 종류는 허용 목록(표·뷰·인덱스·제약)** 이다. `bi_data`에 함수·시퀀스·타입·권한 부여(`GRANT … TO PUBLIC` 등)를 만드는 코드는 차단이다(03c X-15: `bi_app`이 만들 수 있고 `bi_readonly`가 함수를 실행할 수 있어 권한 상승 경로가 됨). 열 타입 변경·열 이름 변경·`DROP … CASCADE`는 허용 목록 안의 동작이다.
- 수식 속 글자 상수(Z6 (가), 2026-10-11 결정)는 SQLAlchemy 내장 부품 + 완화책 3가지(세션 `standard_conforming_strings` 고정, 역슬래시·제어문자·NUL 거부, 생성 후 다시 읽어 비교·불일치 시 롤백)로만 구현하고 런타임 DDL은 `bi_app` 계정으로 실행해야 한다. X-26 주입 사례 10종과 역슬래시 사례의 회귀 시험이 없으면 중요 항목이다.
- **가상 데이터셋 SQL 고정(AP-2, 승인):** Superset 가상 데이터셋의 SQL은 `SELECT * FROM bi_data.<뷰>`로 고정하고 서비스 계정만 등록한다. 다른 형태의 SQL, 서비스 계정 외의 등록은 차단이다.
- **`Identity()` 시퀀스 예외(AP-10, 승인):** 소유 표의 열에 연결된 `Identity()` 암묵 시퀀스(`row_id`)는 "시퀀스 금지"의 예외다. 독립 시퀀스·함수·타입은 여전히 차단이며, backend 시작 자가 점검도 같은 예외를 쓴다.

### 7-5. 인증 스텁 (차단, 2026-10-11 FU-1 결정 K3)
- 인증 스텁(시험용 사용자로 접속자를 흉내 내는 임시 기능)은 개발·시험 환경에서만 켜진다. **운영 환경 설정(`APP_ENV`가 운영 값이거나 운영 배포용 env/Jenkins 설정)에서 스텁이 켜져 있으면 backend가 시작을 거부해야 한다.** **스위치 `AUTH_STUB_ENABLED`(AP-13, 승인)는 기본 꺼짐이고, 켜졌을 때 `APP_ENV`가 명시적으로 설정(코드 기본값이 채운 `local`은 미설정으로 봄)되어 있고 허용 목록(`local`·`test`) 안일 때만 시작을 허용한다(fail-closed).** 이 시작 거부 코드와 시험이 없거나, 스텁이 기본으로 켜지는 기본값(설정이 비면 켜짐, fail-open)이면 차단이다. 스텁을 켜는 설정이 새 환경변수이면 이름과 함께 사전 승인 여부를 확인한다. 시험용 사용자 시드가 운영 마이그레이션에 들어가면 차단이다. 첫 관리자는 서버 명령(새 환경변수 없음)으로 만든다.

### 8. 파괴적 명령 (차단)
- 스크립트나 문서가 다음을 실행하도록 쓰지 않았는지 확인한다: `.env` 삭제, `rm -rf`, `git clean -fdx`, `git reset --hard`, `docker compose down -v`

### 9. BAT 파일 (권장)
- BAT 파일은 작성만 되어 있어야 한다. Linux에서 실행한 흔적이 없어야 한다.
- 경로 구분자와 인코딩(UTF-8 BOM 여부)을 확인한다.

### 10. 운영 가이드 준수 (중요)
- FastAPI, PostgreSQL, React, Docker Compose, Jenkins 기준을 따르는지 확인한다.
- 운영 가이드 기준선과 다른 설정(예: 포트 게시 범위, 기본값과 다른 보안·네트워크 값)이 사용자 승인 기록 없이 들어갔는지 확인한다. 기록이 없으면 중요 항목이다.
- Frontend 컨테이너에 전체 `.env`가 전달되지 않는지 확인한다.

## 심각도
| 심각도 | 의미 | 예 |
| --- | --- | --- |
| 차단 | 머지 전에 반드시 고친다 | Secret 노출, 금지 라이선스, SQL 조립(마이그레이션 변수 보간 포함), 확인 없는 `DROP`, 미결정 사항 확정 |
| 중요 | 기능이나 계약에 영향이 있다 | Skill 미갱신, 계약과 다른 응답, 환경변수 중복 |
| 권장 | 개선하면 좋다 | 이름 개선, 테스트 보강 |

## 보고 형식
| 심각도 | 위치 | 근거 | 담당 | 수정 방향 |
| --- | --- | --- | --- | --- |

- 담당은 `backend-dev`, `frontend-dev`, `env-engineer`, `architect` 중 하나로 적는다.
- 같은 원인의 항목은 묶는다.
- 마지막 줄에 점검한 항목 번호 목록을 적는다.

## 관련 Skill
- `feature-unit`: 완료 기준
- `product-skill-authoring`: 제품 Skill 형식
