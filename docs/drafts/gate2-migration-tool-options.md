> **검토용 초안, 결정 전**
>
> - 이 문서는 architect가 작성한 Gate ② DB 마이그레이션 도구 비교안 초안이다(2026-10-11, 검색요약 기반, reviewer 검증 전).
> - 사용자가 D1~D7을 검토 중이며 **어떤 항목도 확정되지 않았다.** 추천안(Alembic)도 결정이 아니다.
> - 원본은 `_workspace/gate2/migration-tool-options.md`(Git 제외)이며 이 파일은 보존용 사본이다. 결정 후 이 초안의 처리(삭제, `docs/decisions/03-migration-tool.md`로 정리, 보관)는 사용자에게 묻는다.

---

# Gate ② DB 마이그레이션 도구 후보 비교안

- 작성: architect / 작성일 및 확인일: 2026-10-11
- 상태: **승인 전 산출물**. 확정은 사용자가 한다. 이 문서는 옵션과 근거까지만 다룬다.
- 범위: 정적 앱 스키마(등록 테이블, 권한, 소유자 등)를 관리할 마이그레이션 도구. 코드와 설정 파일은 만들지 않았다.
- 참고: `.claude/agents/architect.md`는 산출물 경로를 `_workspace/gate2/migration-tool.md`, 후보를 2~3개로 적고 있다. 이번 요청은 `migration-tool-options.md`와 후보 3~5개를 지정해 요청 쪽을 따랐다.

## 0. 읽는 법

### 0.1 근거 표기
이 환경에는 WebSearch만 있어 **페이지 원문을 열어 보지 못했다.** 아래 모든 외부 사실은 검색 결과 요약에서 가져왔다.

| 표기 | 의미 |
| --- | --- |
| 검색요약 | 검색 결과 요약만 본 항목. 원문 미열람. 서로 다른 출처 2곳 이상이 일치하면 "교차 일치"로 적음 |
| 단일출처 | 출처 1곳만 확인. 교차 확인 못함 |
| 상충 | 출처끼리 내용이 다름 |
| 미확인 | 이번 조사에서 확인하지 못함 |
| 일반지식 | 검색으로 확인하지 못했고 작성자의 사전 지식에 기댄 서술. 구현 전 검증이 필요함 |

"최신"이라고 단정하지 않는다. 날짜는 출처에 적힌 값만 쓰며, 그 이후 릴리스가 있을 수 있다.

### 0.2 고정 조건 (재논의 대상 아님)
FastAPI, SQLAlchemy, PostgreSQL, `docker compose up -d --build` 단일 진입점, Jenkinsfile, Windows 개발자 PC의 BAT 조작, 허용형 라이선스(MIT, BSD, Apache 2.0, PSF, PostgreSQL License)만 추천 가능. `docker compose down -v` 등 파괴적 명령 금지(bi-review 8번은 스크립트·문서가 이를 실행하도록 쓰는 것도 차단).

### 0.3 운영 가이드 조항 점검
운영 가이드 "공통 기술 기준"은 "기존 ORM/Migration 구성이 있으면 유지하고 신규 프로젝트에서만 필요한 조합을 제안한다"고 한다. 현재 저장소에는 `backend/` 코드와 마이그레이션 구성이 없어(`.claude/`, `docs/`, `references/` 등만 존재, 마이그레이션 관련 언급은 문서에만 있음) **신규 프로젝트 조항에 해당**한다. 브리프 4.7절도 이 단계에서 제안·확정하도록 되어 있다. 브리프와 운영 가이드 사이에 충돌은 없다.

## 1. 요약

- 비교 후보 5개: **Alembic / Atlas(Community Edition) / Flyway Community / dbmate / `create_all` 기준선**.
- 부록으로 내린 후보: Liquibase(라이선스), golang-migrate, Sqitch, yoyo-migrations, pgroll, alembic_utils(보조 라이브러리).
- **추천안: Alembic.** (선택은 사용자가 한다. 근거는 7절.)
- 사용자가 따로 정해야 할 항목 7개는 8절에 모았다. 도구를 고르더라도 그 항목들은 남는다.
- 라이선스가 최근 바뀐 도구: **Liquibase**(5.0부터 Functional Source License, 검색요약 교차 일치). Atlas는 Community(Apache 2.0)와 공식 배포 바이너리(Ariga End User License)가 갈라져 있다(검색요약). Flyway Community는 소스는 Apache 2.0으로 표기되나 Redgate 직원이 "freeware(Subscription EULA)"라고 설명한 글이 있어 **불명확**이다.

## 2. 후보 선정과 비교표

### 2.1 비교표

| 항목 | Alembic | Atlas (Community Edition) | Flyway Community | dbmate | `create_all` 기준선 |
| --- | --- | --- | --- | --- | --- |
| 정체 | SQLAlchemy 계열 마이그레이션 도구(Python) | Ariga의 스키마 관리 도구(Go), HCL 설정, SQLAlchemy 연동은 별도 provider | Redgate의 SQL 마이그레이션 도구(JVM) | 언어 비종속 SQL 마이그레이션 도구(Go 단일 바이너리) | SQLAlchemy `MetaData.create_all` 호출 |
| 마이그레이션 형식 | Python 스크립트(`upgrade`/`downgrade`) | 생성된 `.sql` 파일 + 무결성 파일 `atlas.sum` | 버전별 `.sql` | `.sql` 파일 안에 up/down 구간 | 없음 |
| 모델 기준 자동 생성 | 있음(autogenerate, 한계 있음) | 있음(provider 경유, provider 성숙도 미확인) | 없음(수동 작성) | 없음(수동 작성) | 해당 없음 |
| 라이선스 판정 | **허용형**(MIT) | Community는 **허용형**(Apache 2.0). 공식 배포 바이너리는 **주의**(Ariga EULA) | **불명확(확인 필요)** | **허용형**(MIT, 교차 일치) | SQLAlchemy(MIT)이며 추가 도구 없음 |
| 확인한 릴리스 | 1.18.4, 2026-02-10(단일출처). 배포판 목록에 1.18.5 언급(날짜 미확인) | 날짜 미확인. Docker Hub에 1.1.6 태그 언급(날짜 미확인) | Wikipedia 기재 13.8.0 / 2026-09-24(단일출처, 공식 미확인). 별도 목록에 12.5.0 / 2026-04-27 | v2.34.1이 최신 표기(날짜 미확인) | 해당 없음 |
| 추가 런타임 | 없음(backend 이미지에 pip 추가) | Go 바이너리 또는 별도 이미지 + dev DB(스크래치 PG) | JVM | Go 바이너리 또는 별도 이미지 | 없음 |
| 되돌리기 | `downgrade()` 직접 작성 | Community에는 `migrate down` 없음(검색요약) | Community에는 undo 없음(교차 일치) | down 구간 직접 작성 | 없음 |
| CI 충돌·누락 검사 | `alembic check`(1.9.0 이후), 다중 head 검사 | `atlas.sum`으로 병렬 브랜치 충돌 검출, lint는 상충 | `validate`(체크섬) | `--strict`(순서 위반 거부) | 진화 검사 수단 없음 |
| PostgreSQL 뷰·확장 | 수동(`op.execute`), autogenerate 미지원 | 뷰·확장·RLS는 Pro 전용, Community에 없음(검색요약) | 순수 SQL이라 제한 없음 | 순수 SQL이라 제한 없음 | 뷰·확장 지원 없음 |
| 동적 객체 분리 수단 | `include_object`, `include_name`, `include_schemas` 훅 | `--schema`, `--exclude`, env의 `exclude` | diff가 없어 충돌 없음, `clean`만 주의 | diff가 없어 충돌 없음, dump 동작은 주의 | metadata에 넣지 않으면 건드리지 않음 |
| Compose 실행 위치 | backend 이미지 안(entrypoint 또는 일회성 서비스) | 별도 이미지 서비스 | 별도 이미지 서비스 | 별도 이미지 서비스 | backend 앱 시작 코드 |

### 2.2 `create_all` 기준선이 이 프로젝트에서 부족한 이유
- `create_all`은 이미 있는 테이블을 다시 만들지 않는다(기본 `checkfirst`, 검색요약 교차 일치). 열 추가, 타입 변경, 제약 변경은 적용하지 못한다는 점은 SQLAlchemy 공식 문서 원문으로 확인하지 못했고 검색요약과 일반지식에 기댄다.
- 이 프로젝트는 정적 스키마가 릴리스마다 바뀐다(등록 테이블에 열 추가 등). 볼륨이 유지되는 환경(운영, 개발 PC)에서는 이미 만들어진 DB에 변경이 반영되지 않아 환경끼리 스키마가 어긋난다.
- 변경 이력, 되돌리기, 순서 보장, CI 누락 검사가 없다.
- 앱 시작 시 호출하면 backend 복수 프로세스가 동시에 DDL을 시도할 수 있다(일반지식).
- 쓸 만한 곳: 첫 릴리스 직전의 버려도 되는 프로토타입. 이 프로젝트는 운영 가이드가 Jenkins CI와 환경 간 재현성을 요구하므로 기준선으로만 둔다.

### 2.3 부록으로 내린 후보와 이유

| 후보 | 내린 이유 | 근거와 한계 |
| --- | --- | --- |
| Liquibase | **라이선스 비추천.** 5.0(2025-09-30 발표)부터 Community가 Functional Source License(FSL, 2년 후 버전별로 Apache 2.0 전환)로 바뀜. 허용형 목록(MIT, BSD, Apache 2.0, PSF, PostgreSQL License)에 없음. JVM도 필요 | Liquibase 블로그, 릴리스 노트, BusinessWire, 포럼 글이 일치(검색요약). 최신 Community 5.0.3 / 2026-05-15(다운로드 페이지, README, 포럼 공지 일치). 서드파티 글은 "OSI 오픈소스가 아니다"라고 비판(공식 입장 아님). Apache 2.0 포크는 찾지 못함 |
| golang-migrate | dbmate와 역할이 겹치고 라이선스 표기가 출처마다 다름(Homebrew는 MIT, ecosyste.ms는 other). 상충이 풀리기 전에는 "불명확" | 마지막 push 2026-03-19는 집계 사이트 값(단일출처). 보관(archive)·유지 중단 소식은 찾지 못함 |
| Sqitch | Perl 런타임이 추가되고 팀에 낯선 계획 파일 방식. 이 프로젝트 이점이 적음 | Debian README에서 MIT, v1.6.1 확인(날짜 미확인, 검색요약) |
| yoyo-migrations | Python 도구이나 모델 기준 자동 생성이 없고 릴리스 날짜를 확인하지 못함. Alembic 대비 이점이 불분명 | PyPI 요약에서 9.0.0과 Apache 표기(검색요약). 원저장소 LICENSE와 릴리스 날짜 미확인. 이름이 비슷한 다른 패키지(`yoyo-database-migrations` 등)와 혼동 주의 |
| pgroll (Xata) | 무중단 expand/contract 전용 도구로 이 프로젝트의 규모와 목적에 비해 과함 | Apache-2.0(Xata, MacPorts 일치). 확인한 최신 표기는 0.14.3(2025-11 MacPorts, 날짜 불확실) |
| alembic_utils | 후보가 아니라 **Alembic 보조 라이브러리**. PostgreSQL 뷰·함수 등을 autogenerate에 추가함. 정적 뷰가 생기면 별도로 검토 | MIT, 0.8.8 / 2025-04-10(미러 값, 단일출처). 추가 의존성 도입은 사용자 결정 사항 |
| Bytebase 등 플랫폼형 | 별도 서버가 필요한 DB 협업 플랫폼으로 범위를 벗어남 | 라이선스와 구성 미확인 |

## 3. 정적 스키마와 런타임 동적 스키마 분리 (평가 질문 1)

### 3.1 분리해야 하는 이유
- 정적 대상: 등록 테이블, 데이터셋 정의, 권한, 소유자 등 앱 자체 테이블. 마이그레이션 도구가 관리한다.
- 동적 대상: 사용자가 만든 데이터셋 테이블과 수식 열 SQL 뷰. FastAPI가 런타임에 SQLAlchemy로 DDL을 실행한다(브리프 4.2~4.5절).
- 스키마 비교형 도구는 "DB에 있고 모델에 없는 테이블"을 삭제 후보로 본다. 동적 테이블이 이 비교에 들어오면 autogenerate 결과나 declarative 적용 계획에 **사용자 데이터 테이블의 삭제가 포함**된다. Alembic은 비교 결과를 사람이 검토하는 파일로 내보내지만, Atlas의 declarative 적용(`schema apply`)은 원하는 상태와 다른 것을 바꾸는 계획을 만든다는 점이 다르다(일반지식).

### 3.2 분리 옵션 (확정하지 않음)

| 옵션 | 내용 | 장점 | 단점·위험 |
| --- | --- | --- | --- |
| S. 별도 PostgreSQL schema | 정적은 `app` 계열, 동적은 `ds` 계열처럼 스키마를 나눔(이름은 예시) | 경계가 DB 수준에서 명확. DB 롤 권한을 나눌 수 있음(마이그레이션 롤은 정적 스키마, 런타임 DDL 롤은 동적 스키마, Superset용 읽기 롤은 동적 스키마 읽기). 필터 실수에도 비교 대상에 들어오지 않음 | 모든 접근에 스키마 지정 필요. 정적 테이블이 동적 테이블을 FK로 참조하기 어려움(테이블이 런타임에 생기므로 이름 참조만 가능). Superset이 스키마 지정 데이터셋을 쓰는 방식은 이 조사에서 확인하지 못함 |
| N. 이름 규칙 + 필터 | 한 스키마에서 동적 객체에 접두사(`ds_`, `v_` 등, 예시)를 앱이 강제하고 도구 필터가 접두사를 제외 | 구성이 단순함. 스키마 하나 | 필터 오류가 곧 데이터 삭제 후보 노출. 접두사 강제와 정적 테이블 이름 규칙을 계속 지켜야 함. 사용자 입력 이름과 충돌 방지 로직 필요 |
| R. 등록 테이블 기반 필터 | 필터가 등록 테이블을 조회해 등록된 이름을 제외 | 이름 규칙이 필요 없음 | 마이그레이션이 런타임 데이터에 의존. 빈 DB·CI에서 동작이 달라지고, 등록 테이블이 아직 없는 첫 적용 때 순서 문제. 비추천 쪽에 가까운 옵션 |
| D. 별도 DB | 정적과 동적을 서로 다른 PostgreSQL 데이터베이스에 둠 | 완전 분리 | 뷰가 정적 테이블과 조인할 때 한 DB 안이어야 하므로 제약이 큼. 운영 가이드의 단일 DB 관례에서 멀어짐. 복잡도 증가 |

공통 전제: 어떤 옵션이든 **마이그레이션 도구의 모델 메타데이터에는 정적 모델만 넣는다.** 동적 테이블을 SQLAlchemy `MetaData`에 등록하지 않는 설계는 Gate ③ 데이터 모델과 함께 정한다.

### 3.3 후보별 가능 여부

- **Alembic:** 공식 autogenerate 문서에 `include_schemas`를 켰을 때 스키마를 `include_name` 훅으로 거르는 방법이 있고(검색요약), `include_object(object, name, type_, reflected, compare_to)` 훅으로 객체 단위를 거르는 예시가 있다(서드파티 블로그 예시, 공식 문서 원문 미열람). 따라서 S, N, R 모두 구현 가능하다. 단 `include_schemas`를 켜지 않았을 때의 기본 검사 범위는 이번 조사에서 공식 문서로 확인하지 못했다(일반지식: 기본 스키마만 검사). 구현 시 빈 DB와 동적 객체가 있는 DB 양쪽에서 `alembic check`로 검증해야 한다. 최근 1.18.3(2026-01-29)에서 `include_name`으로 걸러진 테이블을 가리키는 FK 때문에 `NoReferencedTableError`가 나던 회귀가 수정됐다(Alembic 변경 이력, 검색요약). 필터와 FK를 함께 쓰면 이런 경계 사례가 있다는 신호다.
- **Atlas:** `schema apply`에 `--schema`(대상 스키마 지정)와 `--exclude`(리소스 제외 glob) 플래그가 있고, env의 `migration` 블록에 `exclude`를 두는 예시가 있다(Atlas 문서·가이드 요약). S와 N은 가능해 보이나 `migrate apply`·`migrate diff` 쪽의 정확한 스키마 범위 규칙은 확인하지 못했다. Community에는 뷰 지원이 없어(검색요약) 동적 뷰가 있는 DB를 검사할 때 어떻게 동작하는지 **미확인**이다.
- **Flyway / dbmate:** 스키마 비교가 없어 "삭제 후보" 문제는 생기지 않는다. 대신 (a) Flyway `clean`은 설정된 스키마의 객체를 지우는 명령이라 동적 스키마가 대상에 들어가면 위험하다(일반지식, 미검증), (b) dbmate는 마이그레이션 후 스키마 덤프 파일을 만드는 동작이 있고 DB 전체를 덤프하면 동적 객체가 파일에 섞여 변경이 생길 수 있다(일반지식, 미검증). 둘 다 S 옵션이면 대상 스키마를 좁힐 수 있다.
- **create_all:** metadata에 없는 테이블은 건드리지 않는다. 충돌은 없지만 정적 스키마 진화를 못 하는 것이 본질적 문제다.

### 3.4 정적 마이그레이션이 동적 객체를 다시 만들어야 하는 경우 (Gate ③ 인계)
릴리스에서 수식 → 뷰 변환 규칙이 바뀌면 이미 만들어진 뷰를 다시 만들어야 할 수 있다. 옵션은 (a) 마이그레이션 스크립트가 앱 코드를 호출해 재생성(마이그레이션이 과거·현재 앱 코드 버전에 묶이는 문제), (b) 앱 시작 시 뷰 정의 해시를 비교하는 조정(reconcile) 작업, (c) 관리 명령으로 수동 실행이다. 도구 선택과 독립이지만 3.2의 옵션과 함께 정해야 한다.

## 4. 평가 질문별 후보 답변

### 4.1 SQLAlchemy 연동과 SQL 조립 금지 (질문 2)

- **Alembic:** SQLAlchemy 모델 메타데이터와 DB를 비교해 마이그레이션 초안을 만든다. 공식 문서가 밝히는 감지 범위는 테이블 추가·삭제, 열 추가·삭제, null 허용 변경, 기본 인덱스, 이름이 명시된 unique 제약, FK이다. 열 타입 변경은 `compare_type` 옵션을 켜야 감지한다. 테이블 이름 변경은 삭제+추가로 보인다. 공식 문서도 autogenerate가 완벽하지 않으니 사람이 검토하라고 적는다(검색요약 교차 일치). **뷰는 감지 범위 목록에 없다**(목록에 없다는 것이지 "미지원"이라는 공식 문장은 확인하지 못함). 뷰·확장은 `op.execute` 등 수동 작성이 필요하다.
- **Atlas:** `atlas-provider-sqlalchemy`가 모델을 읽어 원하는 상태를 Atlas에 넘기고, Atlas가 `.sql` 마이그레이션 파일을 만든다(검색요약). provider 패키지는 PyPI 0.1.x~0.2.2 버전대이고 초기 단계 표시가 있다(검색요약). provider의 라이선스와 최신 릴리스는 **미확인**이다.
- **Flyway / dbmate:** 마이그레이션이 손으로 쓴 `.sql`이다. 모델과 마이그레이션이 어긋나는지 자동으로 알려 주는 기능이 없어, 어긋남 검사를 우리가 따로 만들어야 한다(예: 마이그레이션으로 만든 빈 DB의 스키마를 모델과 비교하는 테스트).
- **create_all:** 모델이 곧 스키마다. 진화는 못 한다.

**SQL 문자열 조립 금지와의 관계 (bi-review 3번, 차단 항목):**
- bi-review는 문자열 연결, f-string, `%` 포맷으로 SQL을 만드는 것을 차단하고 "SQLAlchemy 표현식을 썼는지"를 본다. 마이그레이션 스크립트의 raw SQL 허용 범위는 현재 규칙에 **명시되어 있지 않다.** 사용자가 정할 사항이다(8절 D3).
- 옵션 가. 마이그레이션도 `op.*`와 SQLAlchemy 표현식만 허용하고, 불가피한 정적 문장(변수 보간이 전혀 없는 리터럴)만 사유를 적어 리뷰 승인으로 예외 허용. 장점은 규칙이 일관됨. 단점은 확장 생성이나 뷰 같은 경우 예외가 반복됨.
- 옵션 나. 마이그레이션 파일은 "생성·검토된 산출물"로 보고 변수 보간 금지만 지키게 한다. 장점은 Atlas·Flyway·dbmate처럼 `.sql`이 정본인 도구와 맞음. 단점은 bi-review 문구 수정이 필요하고 "리터럴과 조립"의 경계 해석이 리뷰어마다 갈릴 수 있음.
- 어떤 도구든 **마이그레이션 입력으로 사용자 입력이나 환경변수를 SQL 문자열에 끼워 넣지 않는다**는 원칙은 공통으로 둘 수 있다.
- `.sql` 정본 도구(Atlas, Flyway, dbmate)는 구조상 옵션 나를 요구한다. Alembic은 가·나 모두 가능하다.

### 4.2 Docker Compose 통합 (질문 3)

실행 위치 옵션(도구 공통):
- **P1. backend 컨테이너 entrypoint에서 실행 후 앱 기동.** 서비스가 늘지 않아 운영 가이드의 `postgres/backend/frontend` 기준선에 가장 가깝다. 단점은 backend를 복수로 띄우면 동시 실행 경합이 날 수 있고, 마이그레이션 실패 시 backend가 재시작을 반복한다.
- **P2. 일회성 migrate 서비스 + `depends_on`.** postgres `service_healthy` 후 migrate 서비스가 끝나고(`service_completed_successfully`), 그다음 backend가 시작된다. Compose의 `depends_on` 조건에 이 값이 있다는 것은 Docker 공식 시작 순서 문서와 블로그에서 확인했다(검색요약). 서비스가 하나 늘지만 마이그레이션 로그와 실패 지점이 분리된다. 운영 가이드는 서비스를 "최소" postgres/backend/frontend로 두었으므로 추가는 허용 범위로 읽히나, 운영자 확인이 필요한지는 5절 4번과 별개로 확인 대상이다.
- **P3. 자동 실행 없이 명령으로만 실행(BAT 또는 Jenkins 단계).** 운영 DB 보호에는 유리하지만 `docker compose up -d --build` 한 번으로 환경이 올라온다는 운영 가이드 목표에서 멀어진다.

후보별:
- **Alembic:** backend 이미지에 이미 있는 Python 환경에서 `alembic upgrade head`를 실행하므로 P1·P2 모두 별도 이미지가 필요 없다. 이미 head이면 새로 적용할 것이 없어 재실행에 안전하다(버전 테이블 기반, 일반지식). PostgreSQL에서 동시 실행을 막는 잠금이 기본으로 있는지는 **미확인**이다.
- **Atlas / Flyway / dbmate:** 별도 이미지를 서비스로 추가(P2)하거나 backend 이미지에 바이너리를 설치해야 한다. dbmate는 DB 준비를 기다리는 `wait` 명령과 `--wait`, `--wait-timeout` 플래그가 있고(README 요약), 적용 이력은 기본 `schema_migrations` 테이블에 기록한다. 순서 위반을 거부하는 `--strict`도 있다. dbmate README는 Docker 사용 시 마이그레이션 디렉터리를 bind mount하라고 안내한다(검색요약).
- **create_all:** 앱 시작 코드에서 실행(P1과 유사). 위 2.2절의 한계가 따른다.

**`docker compose down -v` 금지와의 관계:**
- `down`은 볼륨을 지우지 않으므로 DB와 마이그레이션 이력 테이블이 유지된다. 그래서 **마이그레이션은 증분 적용**이어야 하고, 모든 후보에서 재시작은 새로 적용할 것이 있을 때만 변경이 일어난다.
- 볼륨이 없어진 환경(누군가 수동 삭제 등)에서는 마이그레이션이 정적 스키마를 처음부터 다시 만들지만 **동적 테이블과 입력 데이터는 복구하지 못한다.** 동적 객체를 마이그레이션 이력으로 재현할지, 백업·복구 절차로 둘지는 별도 결정이다(운영 환경 백업 정책은 **미확인**, 운영자 확인 필요).
- 빈 DB에서 처음부터 적용해 보는 CI 검증은 보통 DB를 폐기하는 방식으로 하는데, `down -v`는 쓸 수 없다. 대안은 4.3절에서 다룬다.

### 4.3 CI(Jenkins) 통합 (질문 4)

- **빈 DB 적용 검증 방법 (down -v 금지 하에서, 옵션):**
  1) CI 전용 PostgreSQL을 볼륨 없이(임시 저장소로) 띄우고 빌드가 끝나면 컨테이너만 정리.
  2) 하나의 CI PostgreSQL 안에서 빌드마다 임의 이름의 데이터베이스를 `CREATE DATABASE`로 만들고 `DROP DATABASE`로 지움.
  3) 빌드마다 고유한 compose 프로젝트 이름을 쓰되 정리는 볼륨을 남기는 `down`으로 하고 볼륨 정리는 사람이 맡음.
  각 방식의 Jenkins 에이전트 권한과 Docker 사용 가능 여부는 **미확인**이다(Jenkins 구성은 운영자 확인 필요).
- **Alembic:** `alembic upgrade head`로 빈 DB 적용, `alembic check`(1.9.0 이후 제공, 모델과 마이그레이션이 어긋나 새 autogenerate 결과가 생기면 오류를 내는 용도)로 누락 검출. 둘이 같은 부모에서 갈라져 head가 둘이 되면 `alembic merge`로 합치는 절차가 공식 분기 문서에 있다(검색요약). CI에서 head 개수 검사를 넣을 수 있다(구체 명령은 구현 때 확정). `upgrade --sql`(오프라인)로 적용될 SQL을 검토용으로 뽑을 수도 있다(공식 문서 요약).
- **Atlas:** `atlas.sum`이 마이그레이션 디렉터리 무결성을 보장해 병렬 브랜치가 각자 마이그레이션을 추가하면 같은 파일에서 충돌이 나게 만든다(공식 설명 요약). 충돌 검출 면에서는 가장 강하다. `migrate lint`는 문서가 위험한 작업(열·테이블 삭제, 잠금)을 잡는다고 하나, Community에서의 제공 여부는 릴리스 노트(Apache 2 코드로 Community에 남음)와 Community 페이지(목록에 없음)가 어긋나 **상충**이다.
- **Flyway:** `validate`가 이름·유형·체크섬 차이를 검출한다(Redgate 문서 요약). 적용된 파일을 수정하면 체크섬 오류가 난다. 실패한 마이그레이션이 이력에 남아 같은 버전을 다시 안 돌리는 동작은 `repair` 절차가 필요하다(검색요약).
- **dbmate:** `--strict`로 순서 위반을 거부한다. 체크섬 기반 변조 검출 여부는 **미확인**.

**되돌리기(downgrade) 지원과 위험:**
- Alembic은 `downgrade()`를 스크립트마다 직접 쓴다. 쓰지 않거나 틀려도 도구가 막지 않는다. 열·테이블을 지우는 down은 데이터를 없앤다.
- Atlas Community, Flyway Community는 down/undo가 없다(전진 전용). dbmate는 down 구간을 직접 쓴다.
- 정책 옵션: (가) 전진 전용으로 정하고 사고 시 새 마이그레이션으로 고침, (나) `downgrade`를 작성하되 CI에서는 "업그레이드 → 다운그레이드 → 재업그레이드" 왕복 테스트만 수행하고 운영에서는 실행하지 않음, (다) 모든 마이그레이션에 다운그레이드 필수. 운영 DB에는 사용자 데이터가 있으므로 (다)도 데이터 보존을 보장하지 못한다. 사용자가 정한다(8절 D5).

### 4.4 Windows 개발 환경과 BAT (질문 5)

공통: 개발자 PC에는 컨테이너 런타임(Docker Desktop 또는 Podman 계열)만 있으면 되도록 **모든 후보를 컨테이너 안에서 실행**하는 구성이 가능하다. BAT는 `docker compose` 호출을 감싸는 얇은 래퍼로 쓰인다. 이 세션은 Linux라 BAT 실행 검증은 사용자 Windows PC에서 해야 한다.

- **Alembic:** 호스트에 추가 설치가 필요 없다. 마이그레이션 파일은 컨테이너 안에서 생성되므로 **호스트로 가져오는 경로**(소스 디렉터리 bind mount 또는 복사)를 정해야 한다. Windows 경로 bind mount 동작은 Podman에서 달라질 수 있어 **미확인**이며 사용자 PC 검증 대상이다.
- **Atlas:** 이미지에서 실행 가능(공식 이미지 `arigaio/atlas`, 검색요약). 마이그레이션 생성에는 임시 "dev database"(스크래치 PG)가 필요해 개발용 서비스나 임시 컨테이너가 하나 더 든다.
- **Flyway:** `redgate/flyway` 이미지로 실행 가능(검색요약). SQL 디렉터리 마운트 필요. 호스트에 JVM을 따로 깔 필요는 없다.
- **dbmate:** 이미지 `amacneil/dbmate` 사용 가능. README는 `--network=host`를 권하는데, Windows의 Docker Desktop·Podman에서는 호스트 네트워크 의미가 리눅스와 달라(일반지식) compose 네트워크 안에서 실행하는 방식이 필요하다.
- **Compose 의존 조건의 Podman 지원:** `service_completed_successfully`를 `podman-compose`와 Podman의 `docker compose` provider가 각각 어떻게 처리하는지 **미확인**이다(Go 구현 쪽이 조건을 지원한다는 서드파티 글만 있음). P2 옵션을 고르면 사용자 PC에서 확인이 필요하다.

### 4.5 의존성과 학습 비용 (질문 6)

| 후보 | 추가 런타임·의존성 | 학습 비용 (추정은 추정으로 표시) |
| --- | --- | --- |
| Alembic | 없음(Python 패키지). 필요 Python은 1.18.4 기준 3.10 이상(미러 값, 단일출처). SQLAlchemy 필수 버전 하한은 배포판 표기 1.4.23 이상(패키저 값, 상류 미확인). 템플릿 엔진 등 하위 의존성은 **미확인** | 낮음(추정). SQLAlchemy를 이미 쓰고 같은 문서 체계. 다만 `env.py`, autogenerate 한계, 분기 병합은 학습 필요 |
| Atlas | Go 바이너리 또는 이미지, HCL 설정, provider(Python), dev DB. 이미지 크기 **미확인** | 중간(추정). 선언형·버전형 두 모델, HCL, `atlas.sum` 개념이 새로움 |
| Flyway | JVM(CLI 문서가 Temurin 21 번들을 안내, 검색요약). Docker 이미지 베이스와 크기 **미확인** | 낮음~중간(추정). SQL 파일 규칙은 단순하지만 Java 도구를 Python 팀 스택에 추가 |
| dbmate | Go 정적 바이너리 또는 이미지 | 낮음(추정). 파일 규칙이 간단하나 모델과 자동 동기화가 없어 운영 규율이 필요 |
| create_all | 없음 | 가장 낮음. 한계가 큼 |

팀이 이미 아는 도구인지는 확인한 정보가 없다. 위 학습 비용은 모두 작성자의 추정이다(사용자 확인 필요).

### 4.6 라이선스와 유지 상태 (질문 7)

| 후보 | 판정 | 근거 | 마지막 릴리스 (출처 기재 값) | 최근 라이선스 변경 |
| --- | --- | --- | --- | --- |
| Alembic | 허용형 | MIT. ecosyste.ms(저장소 메타), Snyk, Arch Linux 패키지가 일치(검색요약, 교차 일치) | 1.18.4 / 2026-02-10 (CERN PyPI 미러, 단일출처). 1.18.3 / 2026-01-29, 1.18.2 / 2026-01-28, 1.18.1 / 2026-01-14, 1.18.0 / 2026-01-09. Arch는 1.18.5 언급(날짜 미확인) | 찾지 못함 |
| Atlas | Community: 허용형. 공식 배포 바이너리: 주의. Pro 기능: 유료 | Atlas 문서가 Community Edition을 Apache 2.0, Open Edition은 오픈소스 코드 + 일부 독점 기능이며 Atlas EULA로 무료 사용이라고 설명. CLI 레퍼런스는 공식 릴리스 바이너리를 Ariga End User License 하에 배포한다고 표기(검색요약, 같은 벤더 도메인 위주라 교차는 약함) | 미확인. Docker Hub에 1.1.6 태그 언급(날짜 없음) | 2024-09-27부터 Pro 좌석 무료 제공 종료, 30일 체험으로 전환(공식 블로그 요약). 라이선스 자체의 변경은 찾지 못함 |
| Flyway Community | **불명확(확인 필요)** | Maven 메타데이터와 Wikipedia는 Apache 2.0 표기. 그러나 Redgate 포럼 글은 "Community Edition은 freeware이고 Subscription EULA에서 정의"라고 설명하며, GUI 포함 에디션은 오픈소스 프로젝트 일부가 아니라는 표기도 있음(검색요약). 어느 문서가 우리가 쓸 배포물에 적용되는지 확정하지 못함 | Wikipedia 13.8.0 / 2026-09-24(단일출처, 공식 미확인). 별도 목록 12.5.0 / 2026-04-27 | 변경은 확인하지 못했으나 표기가 이원적임 |
| dbmate | 허용형 | MIT. ecosyste.ms와 dev.co가 일치(검색요약, 교차 일치) | v2.34.1이 최신 표기(newreleases.io), 날짜 미확인. 다른 집계는 v2.33.0 / 2026-04-29를 표기(오래된 값일 수 있음) | 찾지 못함 |
| (참고) Liquibase | **비추천** | FSL. 5.0 릴리스 노트, 공식 블로그, BusinessWire가 일치(교차 일치) | 5.0.3 / 2026-05-15 (다운로드 페이지, README, 포럼 일치) | 5.0(2025-09-30 발표)에서 Apache 2.0 → FSL. 버전별 2년 후 Apache 2.0 전환 |

"라이선스 변경 없음"은 검색으로 변경 보도를 찾지 못했다는 뜻이며, 변경이 없다는 증명이 아니다.

### 4.7 PostgreSQL 기능 지원 (질문 8)

| 항목 | Alembic | Atlas Community | Flyway | dbmate |
| --- | --- | --- | --- | --- |
| 트랜잭션 DDL | `transactional_ddl` 기본은 방언 지원 여부를 따르고, `transaction_per_migration`으로 마이그레이션별 트랜잭션 가능(API 문서 요약). PostgreSQL이 트랜잭션 DDL을 지원하므로 기본 적용으로 예상(검색요약에 PG 명시는 없음) | 미확인 | 롤백으로 깨끗한 상태가 유지된다는 사례 글이 있음(PostgreSQL). `CREATE INDEX CONCURRENTLY` 처리 방법은 확인하지 못함 | 미확인(일반지식: 파일별 트랜잭션 기본이고 끄는 옵션이 있음) |
| 뷰 | autogenerate 미감지, 수동 `op.execute`. `alembic_utils`로 보강 가능(별도 의존성) | **Pro 전용, Community 없음**(검색요약) | 제한 없음(순수 SQL) | 제한 없음(순수 SQL) |
| 스키마(namespace) | `schema=` 인자, 필터 훅 있음. 스키마 생성은 수동 작성 | 지원(스키마 단위 플래그). 세부 미확인 | 설정한 스키마를 대상으로 함 | 순수 SQL로 가능 |
| 확장(`CREATE EXTENSION`) | 수동 | **Pro 전용**(검색요약) | 순수 SQL | 순수 SQL |
| RLS | 수동 | Pro 전용 | 순수 SQL | 순수 SQL |

이 프로젝트의 정적 스키마가 당분간 테이블 중심이면 Atlas Community의 뷰·확장·RLS 미지원은 당장 문제가 아닐 수 있다. 다만 브리프 4.6절의 Superset RLS는 Superset 쪽 설정이고 DB의 RLS와 다르다(DB RLS 사용 여부는 Gate ③에서 정해지지 않음). 정적 계층에 뷰나 확장이 생기면 Atlas는 유료 에디션으로 가야 한다.

## 5. 미결정 사항(브리프 5절)과의 의존 관계

도구 선택이 아래 항목을 정하지 않으며, 닿는 부분만 적는다.

| 5절 항목 | 닿는 부분 |
| --- | --- |
| 1. Azure OpenAI 처리 | 관계 없음 |
| 2. 수식 범위 | 수식 범위가 넓을수록(다른 표 참조, 집계) 뷰끼리·뷰와 테이블 사이 의존이 늘어 동적 객체 생성 순서와 3.4절의 재생성 문제가 커진다. 정적 마이그레이션 도구의 선택 자체와는 독립 |
| 3. 새 데이터셋 생성 권한 | 정적 권한 테이블의 구조에 영향. 런타임 DDL을 수행하는 DB 롤을 따로 두면(3.2의 옵션 S) 그 롤을 누가 쓰는지가 이 결정과 연결됨. 도구 선택과 독립 |
| 4. 팀 웹서버 Superset 운영 조건 | **확인이 필요하며 추정하지 않는다.** 아래 6절의 Superset 메타데이터 DB 위치와 `superset db upgrade` 실행 위치가 이 답에 걸린다 |
| 6. 저장 전 수식 평가 경로 | 관계 없음 |
| 7. Explore 제공 방식 | 관계 없음 |

## 6. Superset과의 관계: 우리 마이그레이션 도구의 범위 밖인가

- Superset은 자체 메타데이터 DB를 가지고 업그레이드는 **`superset db upgrade` 다음에 `superset init`** 으로 한다고 공식 업그레이드 문서가 설명한다(검색요약). 업그레이드 전 메타데이터 DB 백업을 권고한다. 메타데이터 DB 연결은 `superset_config.py`의 `SQLALCHEMY_DATABASE_URI`로 지정하고, 분석 대상 DB 연결은 웹 UI에서 추가하는 별개 설정이다(검색요약).
- 따라서 **Superset의 메타데이터 스키마는 우리 마이그레이션 도구의 범위 밖**이다. 우리 도구가 건드리지 않고, Superset 서비스의 초기화·업그레이드 단계가 담당한다.
- **충돌 위험:** Superset은 내부적으로 Alembic을 쓴다(오래된 소스 미러 기준, 현재 소스는 미확인). 같은 PostgreSQL 데이터베이스·같은 스키마를 Superset 메타데이터와 우리 앱이 함께 쓰면 두 쪽의 Alembic 버전 테이블(기본 이름 `alembic_version`)이 부딪칠 수 있다. 우리 쪽이 Alembic이면 버전 테이블 이름을 바꾸는 `version_table` 설정이 있고(여러 프로젝트 사례 요약, 공식 문서 원문 미열람), 스키마를 나누는 `version_table_schema`도 사례가 있다. 어느 도구를 쓰든 **Superset 메타데이터는 별도 데이터베이스(권장 후보)나 별도 스키마로 분리**하는 결정이 필요하다(8절 D7). 팀 웹서버에서 이를 어떻게 구성할 수 있는지는 5절 4번 확인 전까지 **미확인**이다.
- 우리 동적 뷰가 Superset의 분석 대상 DB 연결에서 읽히므로, 읽기 전용 롤과 스키마 범위(3.2의 옵션 S)는 이 구성과 함께 정한다.

## 7. 추천안 (한 개) — 선택은 사용자가 한다

**추천: Alembic.** 근거는 다섯 가지다. 첫째, 이미 확정된 SQLAlchemy와 같은 계열이라 백엔드 이미지에 패키지 하나를 더하는 것으로 끝나고 JVM이나 Go 바이너리 같은 새 런타임이 없다(운영 가이드의 기술 스택을 늘리지 않는다). 둘째, MIT로 허용형이며 여러 출처에서 일치하고 2026년 1월에 연속 릴리스가 확인된다(검색요약). 셋째, 이 프로젝트의 핵심 위험인 "동적 테이블·뷰가 스키마 비교에 섞이는 문제"를 `include_object`, `include_name`, `include_schemas` 훅과 3절 옵션으로 다룰 수 있다. 넷째, `alembic check`와 다중 head 병합 절차로 CI에서 누락과 충돌을 잡을 수 있고, 모델에서 초안을 만들어 SQL 조립 금지 원칙과 결이 맞는다(단 raw SQL 범위는 D3에서 정해야 한다). 다섯째, Atlas는 Community가 뷰·확장·RLS를 지원하지 않고 공식 바이너리가 별도 EULA이며, Flyway는 라이선스 표기가 이원적이고 JVM이 필요하며, Liquibase는 FSL이라 비추천이다. **약점도 있다:** 뷰는 autogenerate가 다루지 않아 수동 작성이 필요하고, `downgrade()`는 도구가 보장하지 않으며, 두 브랜치가 동시에 마이그레이션을 추가하면 head가 갈라져 병합 파일이 필요하고, `include_schemas` 기본 동작은 공식 문서 원문으로 확인하지 못했다.

**추천을 바꿀 수 있는 조건:** 팀이 SQL 파일을 정본으로 삼고 언어 비종속을 중시하면 dbmate가 가장 가볍다(MIT, 단일 바이너리). 병렬 브랜치 충돌 검출을 도구가 강제하길 원하고 정적 계층에 뷰·확장이 없을 것이라 확신하면 Atlas Community가 후보가 된다. 이 경우 provider와 Community 범위를 먼저 검증해야 한다.

## 8. 사용자가 정할 항목

| 번호 | 항목 | 옵션 |
| --- | --- | --- |
| D1 | 마이그레이션 도구 | 7절 추천안(Alembic) 또는 다른 후보. 추천이 맞지 않으면 사유를 알려 주면 비교를 갱신함 |
| D2 | 동적 객체 분리 방식 | 3.2의 S(별도 schema), N(이름 규칙), R(등록 테이블 기반), D(별도 DB). Gate ③ 데이터 모델과 함께 확정 가능 |
| D3 | 마이그레이션 raw SQL 허용 범위 | 4.1의 옵션 가(예외 목록 방식), 옵션 나(보간 금지 방식). bi-review 문구 수정 여부 포함 |
| D4 | 마이그레이션 실행 위치 | 4.2의 P1(entrypoint), P2(일회성 서비스), P3(수동 실행) |
| D5 | 되돌리기 정책 | 4.3의 가(전진 전용), 나(CI 왕복 테스트만), 다(전부 필수) |
| D6 | CI 빈 DB 검증 방식 | 4.3의 1), 2), 3). Jenkins 에이전트 조건은 운영자 확인 필요 |
| D7 | Superset 메타데이터 DB 분리 | 별도 데이터베이스, 별도 스키마, 버전 테이블 이름만 분리. 5절 4번 운영자 확인과 연결 |

도구를 고른 뒤 `env-engineer`가 반영한다. 이 문서는 `docs/`에 옮기기 전 승인 대기 상태다. 승인 시 `docs/decisions/03-migration-tool.md`로 옮기는 것은 메인의 몫이다.

## 9. 출처와 확인 한계

### 9.1 출처 (모두 2026-10-11 검색, 원문 미열람, 검색요약)

Alembic
- PyPI 미러(1.18.4, 2026-02-10, Python 3.10 이상): https://simple-repository.app.cern.ch/project/alembic
- 저장소 메타(MIT): https://summary.ecosyste.ms/projects/369267 , Snyk: https://snyk.io/advisor/python/alembic , Arch Linux: https://archlinux.org/packages/extra/any/python-alembic/
- 공식 autogenerate 문서: https://alembic.sqlalchemy.org/en/latest/autogenerate.html
- 공식 변경 이력(1.18.3 등): https://alembic.sqlalchemy.org/en/latest/changelog.html
- 공식 명령 API(`check`, 1.9.0): https://alembic.sqlalchemy.org/en/latest/api/commands.html
- 공식 분기 문서(merge): https://alembic.sqlalchemy.org/en/latest/branches.html
- 공식 오프라인 모드: https://alembic.sqlalchemy.org/en/latest/offline.html
- 훅 예시(서드파티): https://datawookie.dev/blog/2023-07-22-controlling-what-alembic-autogenerates/
- `transactional_ddl` 시그니처(소스 `context.pyi` 미러): https://git.genenetwork.org/gn-ai/plain/.venv/lib/python3.12/site-packages/alembic/context.pyi
- alembic_utils(MIT, 미러): https://openapps.pro/packages/alembic-utils

Atlas
- Community Edition: https://atlasgo.io/community-edition , https://atlasgo.io/tags/open-source
- 기능 호환표(뷰·확장·RLS Pro): https://atlasgo.io/features
- 가격: https://www.atlasgo.io/cloud/pricing , https://www.atlasgo.io/blog/2024/09/26/atlas-pro-pricing-update
- CLI 레퍼런스(EULA 표기): https://atlasgo.io/cli-reference
- 무결성 파일: https://atlasgo.io/concepts/migration-directory-integrity
- lint: https://atlasgo.io/versioned/lint
- SQLAlchemy provider: https://github.com/ariga/atlas-provider-sqlalchemy/blob/master/README.md , https://pypi.org/project/atlas-provider-sqlalchemy/0.2.2
- Docker Hub: https://hub.docker.com/r/arigaio/atlas/tags
- 선언형 적용 문서: https://www.atlasgo.io/declarative/apply

Flyway
- Wikipedia(13.8.0 표기): https://en.wikipedia.org/wiki/Flyway_(software)
- Redgate 포럼(freeware 설명): https://forum.red-gate.com/roletracker/jump/90503
- Maven 메타데이터(Apache 2.0): https://mvnrepository.com/artifact/org.flywaydb/flyway-parent/9.22.1
- 12.5.0 릴리스 표기: https://www.componentsource.com/product/flyway/releases
- Community에 undo 없음: https://forum.red-gate.com/discussion/89862/does-flyway-community-edition-supports-undo
- validate/체크섬: https://documentation.red-gate.com/fd/validate-277578898.html
- CLI 요구사항(Temurin 21): https://documentation.red-gate.com/flyway/getting-started-with-flyway/system-requirements/command-line-and-api-requirements

Liquibase
- 라이선스 변경 블로그: https://www.liquibase.com/blog/liquibase-community-for-the-future-fsl
- 5.0 릴리스 노트: https://docs.liquibase.com/community/release-notes/5-0
- BusinessWire: https://www.businesswire.com/news/home/20250930639100/en/Liquibase-Unveils-Liquibase-Secure-and-Liquibase-5.0-A-New-Era-for-Mission-Critical-Database-Change
- 포럼: https://forum.liquibase.org/t/liquibase-secure-liquibase-5-0-a-new-chapter-for-community-enterprise-users/10675
- 다운로드 페이지(5.0.3, 2026-05-15): https://www.liquibase.com/download-oss

dbmate / golang-migrate / Sqitch / yoyo / pgroll
- dbmate: https://summary.ecosyste.ms/projects/370063 , https://dev.co/databases/open-source/dbmate , https://newreleases.io/project/github/amacneil/dbmate/release/v2.31.0 , README: https://unpkg.com/dbmate@2.34.1/README.md
- golang-migrate: https://formulae.brew.sh/formula/golang-migrate , https://summary.ecosyste.ms/projects/362584 , https://gittrend.io/repo/golang-migrate/migrate
- Sqitch: https://sources.debian.org/src/sqitch/1.6.1-1/README
- yoyo-migrations: https://pypi.python.org/pypi/yoyo-migrations
- pgroll: https://xata.io/open-source , https://ports.macports.org/port/pgroll/builds

Superset, Compose, SQLAlchemy
- Superset 업그레이드: https://superset.apache.org/docs/installation/upgrading-superset
- Superset 설정: https://superset.apache.org/docs/installation/configuring-superset
- Superset 마이그레이션 env(오래된 미러): https://codeclimate.com/github/airbnb/caravel/superset/migrations/env.py/source
- Compose 시작 순서: https://docs.docker.com/compose/how-tos/startup-order
- Podman과 `depends_on`: https://documentation.suse.com/fr-fr/sle-micro/6.1/html/Micro-compose/index.html
- `create_all` 동작(미러): https://docs-sqlalchemy.readthedocs.io/ko/latest/core/metadata.html
- 도구 비교 블로그(참고용, 근거로 쓰지 않음): https://www.bytebase.com/blog/top-open-source-postgres-migration-tools/

### 9.2 확인하지 못한 것
- 페이지 **원문을 열람하지 못했다.** 모든 외부 사실은 검색 요약 기준이며 날짜·버전은 요약이 인용한 값이다.
- 확인하지 못한 항목: Alembic 1.18.5의 릴리스 날짜와 Alembic 현행 의존 하한, `include_schemas` 기본 동작의 공식 문구, Atlas 최신 릴리스 날짜와 provider 라이선스·성숙도, Atlas Community에서 `migrate lint` 제공 여부(상충)와 동적 뷰가 있는 DB에서의 동작, Flyway Community 배포물에 적용되는 정확한 라이선스 문서와 Docker 이미지 베이스·크기, dbmate 최신 릴리스 날짜와 체크섬 검증 여부, golang-migrate의 LICENSE 원문, yoyo의 원저장소 LICENSE와 릴리스 날짜, Podman 계열의 `service_completed_successfully` 지원, PostgreSQL 동시 마이그레이션 잠금 동작, 이미지 크기 전반.
- 일반지식으로 표기한 서술(동시 실행 경합, `clean`·덤프 동작, 파일별 트랜잭션 기본 등)은 검증하지 않았다.
- 코드나 설정을 실행해 확인한 항목은 없다. 팀의 기존 도구 숙련도, 팀 웹서버·Jenkins 에이전트의 조건은 알지 못한다(운영자 확인 필요).
