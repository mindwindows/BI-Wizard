# 08. Superset 등록·guest 역할·입장권·임베딩 (FU-1 범위)
**상태: 승인(2026-10-11, 03b 6절)** — architect. 용어·이름은 04 부록 A를 그대로 쓴다. EW-3·EW-4 구현 결과 반영(2026-10-12, EW-5): 상태·이름·개수·순서만 갱신했고 승인된 설계는 바뀌지 않았다.
- 의존 결정: 브리프 5절 4·7·10번, `03b` 3-1·3-3·3-6·4-1·4-2·4-5·5-2(K11 ㄷ, K12), `03a`, `deploy-coordination.md`(DC). 결정 원문은 반복하지 않는다. 사실 근거는 `03c`의 X-번호이며 **확인됨**(실험 또는 6.1.0 소스) / **추정**을 구분한다.
- [제안]·[미답] 표지는 `03b` 6-2에 따라 모두 승인된 것으로 읽는다(남은 [승인 필요]·AP는 `03b` 6-3 기준).
- 표지: **[제안]** 기본값 / **AP** §7 승인 상태 / **해소(03c A-27)** 열 표시 이름 갱신 확인됨, §2-3 / **[확인 대기]** 구현 전 확인 항목(EW-3·EW-4로 구현된 것은 **구현됨(EW-n, 날짜)**).
## 1. 구성 개요와 불변식
| 항목 | 내용 | 출처·상태 |
| --- | --- | --- |
| 경계 | 브라우저 → FastAPI → Superset(`httpx`, 서비스·발급 전용 계정). 브라우저가 Superset에 닿는 길은 Embedded iframe(입장권)과 작성 화면 새 창 링크뿐이며 Superset REST는 호출하지 않는다 | 04 §5 |
| 불변식 | **"Superset에 등록된 데이터는 모두 공개."** 전원 공개가 아닌 데이터셋을 `bi_data`에 두려면 설계 변경(별도 승인)이 필요하다. 그래서 `rls`는 쓰지 않고 guest 역할은 하나다. 데이터셋 만들기 화면에 공개 안내 문구를 둔다 [제안] | `03b` 3-1, 1-6 |
| 버전·경로 | Superset `6.1.0` 고정, 내부 코드 수정 금지. 하위 경로 `SUPERSET_APP_ROOT`, 프록시는 접두를 떼지 않고 전달(접두 없으면 404). 로고 이중 접두 등은 알려진 문제 | `03a`, DC 3·13 |
| 같은 origin | 포털과 Superset이 같은 호스트의 하위 경로여야 한다. 다른 origin이면 Embedded(`/embedded/`)까지 차단되어 `frame_options`/CSP 변경(기준선 이탈, 별도 승인)이 필요하다. 운영자 협의 중 | X-18 확인됨, DC 9 |
| 작성 화면 | 새 창 링크 + 별도 로그인(iframe 도입 없음, 8번 뒤 자동 로그인 연동이 목표, X-19는 그때). 팀 필터는 모든 대시보드가 같은 기본값으로 시작하고 소속 팀 기본값은 도입하지 않는다 | `03b` 3-1 Y3, 4-1 Z13·Z14 |
| 주체 | `Admin`(임베드 켜기·`allowed_domains` 수동, 서버에 두지 않음) / 서비스 계정 §2(`SUPERSET_SERVICE_USER`·`_PASSWORD` 승인됨) / 발급 전용 계정 §4(`SUPERSET_GUEST_ISSUER_USER`·`_PASSWORD` 확정) / `bi_guest` §3 / 작성자 §5. 서비스·발급 계정·역할 생성은 `superset-init` 확장(AP-16 승인) — **구현됨(EW-3·EW-4, 2026-10-12)**: 역할 5개 `bi_service`·`bi_guest_issuer`·`bi_author`·`bi_author_schema`·`bi_guest`, 계정 2개(기본 이름 `bi_service`·`bi_guest_issuer`) | `03b` 3-6, 4-7 |

## 2. 서비스 계정: 가상 데이터셋 등록
| 항목 | 내용 | 출처·상태 |
| --- | --- | --- |
| 최소 권한 4개 | `can_read Dataset`, `can_write Dataset`, `schema_access`(항목 이름 `[BI-Wizard (read-only)].[<POSTGRES_DB>].[bi_data]`, EW-3 확인), `can_read SecurityRestApi`(CSRF 토큰 조회). 7개 후보의 128조합 전수. `Database`/`Chart`/`Dashboard` 읽기는 불필요. 역할 `bi_service`(`superset/bi_roles.py`)로 **구현됨(EW-3)**이고 `can_grant_guest_token`이 목록에 들어가면 `superset-init`이 실패한다 | X-22 확인됨 |
| 못 하는 것 | 임베드 켜기 403. 입장권 발급은 `can_grant_guest_token`이 없어 불가이며 **이 권한을 서비스 계정에 주지 않는다**(발급 계정과 분리) | X-22 확인됨, `03b` 4-2 Z3 |
| 소유 | 이름 변경·새로고침·삭제는 **서비스 계정이 소유한 데이터셋만** 된다(관리자 소유 403). 비밀번호 변경은 가능, 계정 이름 변경·재생성 금지 [제안]. 계정을 교체하려면 소유자 이전이 필요한데 **시험하지 않았다** → FU-1e 착수 때 시험해 절차를 정한다 | X-22 확인됨 / 이전은 확인 대기 |
| 계정 생성·충돌 | **구현됨(EW-3·EW-4, `superset/ensure_accounts.py`)**: 계정마다 역할 하나(관리자 역할 없음), 매 기동 비밀번호·활성·역할을 되돌리고 저장 해시를 재읽기로 확인, 세 계정 이름(관리자·서비스·발급)은 대소문자 무시로 서로 달라야 한다. **표식**(first_name `BI-Wizard`, email `<이름>@localhost`)이 있는 계정의 허용 밖 역할(Admin 포함)은 제거해 **강제 복구**하고 `경고:`와 마지막 줄 `점검 요약: 강제 복구 N건`을 남긴다(03b 10-1). 표식 없는 기존 계정은 **역할과 관계없이 거부**(exit 1, 비밀번호 재설정 없음, 03b 12-1 3번) — **구현됨(EW-5, `ensure_accounts.py`)**: 모든 계정을 변경 전에 검사해 하나라도 거부 대상이면 아무것도 바꾸지 않는다(EW-3의 알려진 한계 해소). 운영자 정리 절차는 `skills/local-environment/SKILL.md` | `03b` 9-1, 10-1, 12-1 |
| SQL·이름 | 가상 데이터셋 SQL은 항상 `SELECT * FROM bi_data.<dv_번호>` 고정, 서비스 계정만 등록(AP-2 승인; SQL 접근 검사가 등록 시점에만 있어서: X-20, `bi_readonly`는 `public` 표를 못 읽어 이중 방어: X-15). 데이터셋마다 `dv_` 뷰가 항상 있다는 04 §7-1 [제안]에 의존한다. 이름은 `[<팀 표시 이름>] <데이터셋 표시 이름>`, 중복은 422이므로 (팀 이름, 데이터셋 이름) 유일성은 06이 보장한다 | `03b` 3-3 Y6, X-13·X-22 |
### 2-1. 등록 흐름 (멱등)
| 순서 | 단계 | 비고 |
| --- | --- | --- |
| 0 | `superset-init`(관리자 권한)이 `bi_data`가 있는 상태에서 `POST /database/{id}/sync_permissions/` → 그 뒤 서비스 역할에 `schema_access` 부여 | 새 schema의 `schema_access`는 첫 데이터셋 생성이나 이 호출 때 생겨, 부여 전에 해야 한다(X-22 확인됨). `bi_readonly`의 `bi_data` USAGE는 마이그레이션 0002가 부여한다(06 §6). **해소(EW-3 구현, 2026-10-12):** `superset-init`은 `db-bootstrap`과 `migrate` 완료를 모두 기다린다(순서 경쟁 방지, 순환 없음). `superset-init` 실행 순서는 `db upgrade → ensure_admin → superset init → register_database → sync_permissions → ensure_roles(역할 5개, `bi_guest` 포함) → ensure_accounts(계정 2개)`다. 구현 방법은 Superset 이미지 안의 앱 컨텍스트 파이썬 스크립트(`superset/sync_permissions.py` 등, `SyncPermissionsCommand`를 `test_request_context`에서 관리자를 `g.user`로 두고 직접 실행, REST·CLI·새 의존성 없음)다. **EW-3 실측:** `bi_readonly`에 USAGE가 없는 상태(`migrate` 전)에서도 `sync_permissions`가 `bi_data`의 `schema_access`를 만들었다(schema 목록은 USAGE와 무관). 그래서 `migrate` 대기는 필수 조건이 아니라 안전장치다 |
| 1 | 서비스 계정 로그인 + CSRF 토큰 (§2-2) | |
| 2 | `GET` 필터(database·schema·이름)로 조회. 있으면 4~5단계만 | `superset_dataset_id`가 있으면 그 번호를 먼저 쓴다 [제안] |
| 3 | 없으면 `POST /dataset/`(`table_name`=표시 이름, `sql`, schema `bi_data`) → 201. 422(중복)면 2단계로 | 동시 `POST` 3개는 201 하나·422 둘(X-22). 열은 자동 인식(X-13) |
| 4 | `POST` 응답의 열 id로 `PUT /dataset/{id}` **전체 열 교체**(§2-3) | 확인됨(03c A-27) |
| 5 | `PUT /dataset/{id}/refresh` → (뷰 변경 뒤면) `GET` → 포털이 보관한 `display_name`과 병합해 전체 열 재`PUT` → `superset_datasets` 갱신(`registered`, `synced_at`) | 뷰가 없으면 원인 없는 422(X-23) → 뷰 생성·재생성 **커밋 뒤** 호출(04 §3) |
- 같은 데이터셋의 동기화는 동시에 하나만 돈다(단일 작업 스레드가 순서대로 처리) [제안]. **디바운스(1e-f, 사용자 승인 2026-10-13, 03b 24절):** Superset `refresh`와 포털 뷰 DDL이 같은 뷰를 반대 순서로 잠그다 교착한 실측(4회, 모두 Superset 쪽 희생) 때문에, 요청 경로로 들어온 동기화 요청은 작업 큐에서 `not_before = 첫 요청 시각 + 3초`(코드 상수 `SYNC_DEBOUNCE_SECONDS`, 새 환경변수 없음)를 가진다. 같은 데이터셋의 반복 요청은 첫 요청의 시각을 유지한 채 합쳐지고(창 비연장) Superset 호출은 한 번이다. 데이터셋마다 독립이며 지연된 항목이 준비된 다른 항목을 막지 않는다. 처리 중 정의가 또 바뀌면(세대 번호) 결과를 `registered`로 쓰지 않고 그 요청의 지연 뒤에 다시 돈다. **시작 대조와 연결 문제 자동 재시도는 지연이 없고** 이미 지연 중인 항목은 가장 이른 시각으로 당긴다. 종료는 지연 때문에 막히지 않고(큐는 메모리, 상태는 DB의 `pending`이라 다음 시작 대조가 처리) 시계는 주입된다. 포털 쪽 교착 희생자(40P01)는 정의 변경 진입점이 503 `DEFINITION_BUSY`로 바꾸고 롤백하며 같은 요청을 다시 보내면 처리된다(`tests/test_definition_deadlock_pg.py`, 진짜 교착). **이름 변경:** 데이터셋 이름이 바뀌면 같은 흐름으로 `PUT`한다. 팀 이름이 바뀌면(05 A4) access가 커밋 뒤 `DatasetSyncPort`에 팀 단위 요청을 보내고 superset이 그 팀의 모든 데이터셋에 같은 흐름을 돌린다(팀 이름은 auth의 읽기 service로 읽음, 04 §3). 권한 항목 이름만 제자리에서 바뀌고 차트와 데이터셋 권한 사용자의 접근은 유지된다(X-22 확인됨).
- **열 제거·타입 변경:** `refresh` 뒤 그 열을 쓰던 저장 차트가 데이터 오류가 된다(X-22 확인됨). FU-1은 열 제거·타입 변경이 없고 계산 열의 결과 형 변경만 05 D5 `result_type_changed` 안내까지 한다. 영향 차트 수 안내는 후속이다(05와 같은 범위). 포털은 Superset 차트·대시보드를 대신 고치거나 지우지 않는다(`03b` 3-6).
- **동기 상태**(04 A-3): `pending`(정의 커밋 뒤 `DatasetSyncPort` 호출 때 시작, `superset_datasets` 행이 없는 데이터셋도 `pending`으로 본다) → `registered` / `failed`(사유 코드 기록, 저장 위치는 06, [제안]). 재시도는 ① 서버 시작 때 `pending`·`failed` 재동기화(시작을 막지 않는 백그라운드) ② 관리자 S9 "다시 시도". Superset 불가가 데이터셋 만들기·입력·수식 저장을 막지 않는다 [제안].
### 2-2. HTTP 클라이언트
- `httpx`(승인됨, 허용형). 접근 토큰 15분·갱신 토큰 30일(X-22 확인됨): 401이면 갱신, 실패하면 재로그인 [제안]. 로그인·갱신은 잠금으로 직렬화 [제안]. POST는 Bearer만으로 400 `CSRF token is missing`이라 `GET /api/v1/security/csrf_token/`의 토큰을 **같은 세션 쿠키 + `X-CSRFToken`**으로 보내야 한다(X-13 부가, 확인됨). 쿠키를 유지하는 클라이언트를 쓰고 400이면 토큰을 다시 받는다.
- 주소 = Superset 내부 주소 + `SUPERSET_APP_ROOT`. 내부 주소는 compose 서비스 이름 기반 **코드 상수**(새 변수 없음)이고 `SUPERSET_APP_ROOT`를 backend에 전달한다(AP-12 승인 `03b` 6-3, 적용 완료 EW-3: `backend/app/config.py`의 `SUPERSET_INTERNAL_URL`, HTTP 호출 코드는 FU-1e). 토큰·비밀번호·응답 본문을 로그에 남기지 않는다.
- **1e-f 보강:** (1) 로그인 거부(`AUTH_FAILED`) 뒤 `LOGIN_RETRY_BACKOFF_SECONDS`(30초, 코드 상수) 동안은 Superset을 부르지 않고 곧바로 같은 `SupersetRejected("AUTH_FAILED")`를 낸다 — 의미는 05 E6 표의 "Superset 거부 = 502 `SUPERSET_REJECTED`"와 같다(연결 문제 503으로 바꾸지 않았다. 비밀번호 불일치는 일시적 장애가 아니라 거부이므로). 연결 문제(5xx·시간 초과)는 대기를 시작하지 않는다. 동기화에서는 `failed`+`AUTH_FAILED`(자동 재시도 대상 아님)이다. (2) `httpx.HTTPError`가 아닌 예외(`InvalidURL`, `CookieConflict` 등)는 클라이언트 호출 경계(`_exchange` 등)에서 `SupersetRejected("INTERNAL")`로 바꾸고 로그에는 예외 클래스 이름만 남기며 원인 예외를 붙이지 않는다(`from None`). 전역 500 핸들러로 가지 않으므로 E6은 502다. (3) 서킷 브레이커는 쿨다운 뒤 **시험 호출 1건만** 통과시키고(반열림) 결과가 기록될 때까지 나머지를 막는다. 결과가 기록되지 않으면 쿨다운만큼 지난 뒤 다음 한 건을 허용한다. (4) 사용자별 속도 제한기는 윈도 길이마다 한 번 스스로 `forget_idle`을 수행한다(새 스레드 없음).
### 2-3. 열 표시 이름 (확인됨: 03c A-27, 조건부 가능)
- `03b` 5-2 K12 (나): 뷰 출력 열은 `c_<번호>`(팀 열 `team`)이고 읽기 쉬운 이름은 Superset 열 `verbose_name`이다. 서비스 계정(X-22의 4권한만)이 **자기 소유 데이터셋**의 표시 이름을 설정·변경·해제할 수 있다(관리자 소유는 403). 표시 이름만 바꿔도 저장 차트·필터는 안 깨지고(`column_name` 참조) 표 머리글만 바뀐다. 요청 순서: 로그인·CSRF → `POST /dataset/`(응답에서 열 id) → `PUT /dataset/{id}` 전체 열 → 뷰 변경 뒤 `refresh` → `GET` → 보관한 표시 이름과 병합해 전체 열 재`PUT`. 데이터셋 단위 직렬화, 422 "columns do not exist"는 재조회 후 재시도.
- **주의: `columns`는 병합이 아니라 교체다.** 일부만 보내면 나머지 열이 삭제되고(`[]`이면 전부, `refresh`로 복구해도 새 id에 이름 없음) id 없는 항목은 422이므로 **항상 전체 열(id·`column_name`·`verbose_name`)을 보낸다**. `refresh` 뒤 기존 이름은 유지되나 뷰에 새로 추가한 열은 이름 없이 생기고, 제거 뒤 다시 추가한 열은 이전 이름이 복원되지 않는다. 한계: guest·관리자 화면, 열 수백 개, `refresh`와 `PUT` 동시 호출은 미확인. 번호 이름이 보이는 곳은 §5 안내문.

## 3. guest 역할 `bi_guest`
| 항목 | 내용 | 출처·상태 |
| --- | --- | --- |
| 생성 | `superset-init`이 매 기동 멱등으로: 조회 → 없으면 생성 → 권한 목록 통째 교체 → 재읽기 비교. 목록은 저장소 고정 파일(`superset/bi_roles.py`). 구현 방법은 EW-3에서 정했다(앱 컨텍스트 파이썬 스크립트, §2-1 0행). `bi_guest`는 EW-4에서 같은 방식으로 추가했다(구현됨 EW-4, 2026-10-12: qa-engineer 12항목 통과·reviewer 차단 0건, 새 설치·재기동 멱등). 목록은 `bi_roles.py`의 `ROLE_PERMISSIONS`에 있고 실제 확인한 항목은 `can_read CurrentUserRestApi`, `can_read Dashboard`, `can_read Chart`, `can_time_range Api` 4개다 | `03b` 4-2 Z2, X-20(통째 교체 확인됨) |
| 필수 3개 | `can_read CurrentUserRestApi`, `can_read Dashboard`, `can_read Chart` | X-25 확인됨 |
| 기간 필터 1개 | `can_time_range Api`(없으면 `/api/v1/time_range/` 403으로 기간 팝업 APPLY 비활성). 안내문이 시간 필터를 요구하므로 FU-1 목록에 넣는다 [제안] | X-25 확인됨 |
| 조건부 2개 | `can_explore_json Superset`(레거시 차트 유형), `can_read DashboardPermalinkRestApi`(permalink 필터 복원). **FU-1 기본은 미포함**: 지원 차트 6가지(§3-1)에 필요하지 않을 때만 제외를 유지하고(`rose` 같은 레거시 유형은 지원 차트가 아님), 필요해지면 보고하고 멈춘다(`03b` 6-1). EW-4 QA에서 6가지 모두 이 둘 없이 정상 표시됨을 확인했고 두 권한은 `FORBIDDEN_PERMISSIONS`로 목록에 들어가면 시작 실패다. `native_filters`는 추가 권한 없이 동작 | X-25 확인됨 |
| 비포함 | 쓰기 권한 전부, Explore, SQL Lab, 데이터셋·DB 등 **그 밖의 목록 API**(403), 내보내기(`can_csv Superset`을 넣으면 CSV/XLSX가 열려 넣지 않음). 시작 21개 중 14개 불필요. **대시보드·차트 목록 API는 열려 있다(실측, 03b 24절):** guest 입장권으로 `GET /api/v1/dashboard/`와 `/api/v1/chart/`는 200이지만 결과는 **토큰 대시보드 1개와 차트 0개로 한정**되고(QA 실측이며 좁혀지는 이유는 Superset 내부 동작으로 소스에서 확인하지 않았다), 데이터셋 목록 `GET /api/v1/dataset/`는 403이다. "guest는 목록 API를 쓸 수 없다"는 이전 문구는 틀렸다. 이 한정은 실제 Superset이 필요해 backend 단위 시험이 아니라 QA의 실제 Superset 스모크가 **단정**한다(1e-f QA 스크립트 `_workspace/qa/qa1f/g4.py`, git 제외: 대시보드 200·1개·토큰 대시보드, 차트 200·0개, 데이터셋 403, STRIP true·false 모두 8/8 통과). **수동 실행 스모크 스크립트가 저장소에 있다**(`scripts/manual/superset-guest-list-check.py`, 실행 방법은 `skills/dashboard-link/SKILL.md` 8절; 자동 CI는 후속) | `03b` 4-2 Z1, 24절, X-25 |
| 불변·시작 실패 | `Public` 권한 0개, `PUBLIC_ROLE_LIKE` 미설정, `Gamma` 미사용(guest 역할에만 적용). 목록의 권한 이름이 Superset에 없으면 `superset-init` 실패(`can_read AnnotationLayerRestApi`는 없는 이름이었음). 역할이 없으면 guest의 모든 API가 500. **구현(EW-4, 2026-10-12):** `ensure_roles.py`가 아무것도 바꾸기 전에 실제 적용된 `GUEST_ROLE_NAME`이 `bi_roles.GUEST_ROLE`(`bi_guest`, 이름 정본)과 같은지, `PUBLIC_ROLE_LIKE` 미설정, `Public` 권한 0개를 확인하고 어기면 **고치지 않고 실패**한다. `bi_guest` 목록에 금지 권한(조건부 2개, 내보내기·쓰기·Explore·SQL Lab·데이터 접근 계열)이 있어도 실패한다(`bi_service`의 `can_grant_guest_token` 가드와 같은 방식, 이름 조각 검사 포함). 시험: 없는 권한 이름 → 실패·불변, 금지 권한 8종 → 실패, `Public`에 권한 임시 부여 → 실패, `PUBLIC_ROLE_LIKE`·`GUEST_ROLE_NAME` 변조 → 실패 | `03b` 3-1, 4-5, X-25 |
| 반영·업그레이드 | 권한 변경은 재시작 없이 즉시, `GUEST_ROLE_NAME` 변경은 재시작 필요. `superset`은 `superset-init` 성공 뒤 시작(현 compose)하므로 역할이 먼저 생긴다. 새 권한은 자동 추가하지 않고 업그레이드 때 스모크 시험 + 권한 목록 차이 보고 | `03b` 4-5, X-25 |
### 3-1. 지원 차트 6가지와 스모크 (guest 4개 권한 구성, 관리자 화면과 비교)
- **지원 차트(`03b` 6-1): 선, 막대, 표, 큰 숫자(추세 포함), 원형, 혼합(막대+선).** 6가지 모두 임베딩 화면에서 `bi_guest` 최소 권한(필수 3개 + 기간 필터 1개)으로 정상 표시되어야 FU-1 합격이다(P5). 추가 권한이 필요한 차트가 나오면 보고하고 멈춘다. X-25가 "핵심 시나리오 차트 6개"를 시험했으나 원문에 이름이 없어 이 6가지와 같은지는 확인하지 못했으므로 FU-1e에서 6가지를 직접 시험한다. EW-4 QA에서 6가지(선·막대·표·큰 숫자·원형·혼합)는 `bi_guest` 4권한만으로 임베딩 화면에서 관리자 화면과 같은 값으로 표시됨을 확인했다(포털 화면 재시험은 FU-1e).
- 아래 목록은 X-25의 참고 결과다(지원 차트 밖 유형 포함).
- 시험함·동일(관리자 화면과 같게 렌더): 면적, 산점, 계단, 부드러운 선, 박스 플롯, 히스토그램, 히트맵, 트리맵, 선버스트, 게이지, 깔때기, 레이더, 버블, 혼합 시계열, 큰 숫자(추세), 표(기간 비교), 피벗. 막힘: `rose`(`can_explore_json` 필요). **판정 못 함**(내 시험 설정 오류): `time_table`, `cal_heatmap`, `handlebars`. **미시험**: 지도·deck.gl, 워드클라우드, 생키, 계층형 일부.
- 업그레이드 때와 새 차트 유형을 쓰기 전에 다시 시험한다. 한계: 워커 1개, Chromium 1종, HTTP만 시험(HTTPS의 CSRF Referer·`Secure` 쿠키 미확인).
### 3-2. 알려진 한계 (X-25 확인됨)
- **열 단위 접근 제어 불가**: 토큰 대시보드의 데이터셋에 대해 질의를 바꾼 요청(저장 안 된 열·지표·필터)이 200이다. 방어선은 `bi_readonly` 권한뿐이고 공개 범위는 `bi_data` 전체(불변식)와 같다. 느린 질의는 DB에서 계속 실행되며 `bi_readonly` `statement_timeout`이 대응이다(AP-9 승인 30초, psql 직접 접속에서는 EW-1 QA가 30.2초 취소를 확인했고, Superset 경유는 EW-6 QA가 관리자 `chart/data`로 확인했다: 36행×1초 `pg_sleep`이 30.1초에 400으로 끝나고 Postgres 로그에 `canceling statement due to statement timeout`. 단 guest 경로와 서브쿼리 지표(Superset이 먼저 거부)는 시험하지 않았다).
- `GET /dashboard/{id}/embedded`가 guest에 200이라 `allowed_domains`와 변경자 사용자명이 보인다 → 이 필드에 민감 정보를 넣지 않는다. PDF/이미지 내보내기는 클라이언트 생성이라 서버가 못 막는다. 권한 회수 뒤 최대 5분 열람 가능성을 수용한다(`03b` 4-2 Z5). EW-4 QA 확인: `/datasets` 응답에 가상 데이터셋 SQL이 보이고(불변식 범위) guest 요청마다 Superset 로그에 `Failed to add user to db session … LocalProxy` 경고가 남지만 기능 영향은 없다.

## 4. 입장권(guest token) 발급
| 항목 | 내용 | 출처·상태 |
| --- | --- | --- |
| 흐름 | Embedded SDK `fetchGuestToken` → backend(경로는 05) → 인증된 활성 사용자·활성 `superset_dashboards`의 `embedded_uuid` 확인 → 발급 전용 계정으로 `POST /api/v1/security/guest_token/` → 토큰 반환(`Cache-Control: no-store`, 로그 금지) | `03b` 4-2 Z3, 4-5 |
| 본문 | `user`는 **항상** 보낸다(`username`=`users.id` 문자열 [제안]; 생략하면 500). `resources`는 `[{type: dashboard, id: <embedded uuid>}]` 하나. `rls`는 **항상 빈 목록**(클라이언트 입력 없음) | X-28 확인됨, `03b` 4-2 Z4 |
| 대시보드 식별 | 포털 등록 표의 embedded uuid만 쓴다. `Dashboard.uuid`는 사용 시 거부되고 숫자 id는 임베드 안 한 대시보드도 API로 읽힌다 → 클라이언트가 보낸 id·`rls`는 받지 않는다. uuid는 관리자가 Superset에서 임베드를 켠 뒤 수동 입력 | X-28 확인됨, `03b` 4-2 Z3 ㄴ |
| 검증 훅 | `GUEST_TOKEN_VALIDATOR_HOOK`(승인됨). **시그니처·호출 위치(6.1.0 소스 확인, EW-4):** `hook(body: dict) -> bool`, `body`는 `{user, resources, rls}`(`GuestTokenCreateSchema` 검증 뒤)이며 `security/api.py`의 `guest_token()`이 `validate_guest_token_resources`(id가 임베드 uuid 또는 대시보드 id·slug인지 확인) **다음**, 토큰 생성 전에 부른다. 반환이 거짓이면 `ValidationError`로 **400**(`Guest token validation failed`)이고 호출 불가 객체면 오류, 훅이 예외를 내면 500이다(그래서 훅은 예외를 삼키고 거부한다). **구현(`superset_config.py`):** 거부 = `rls`가 `[]`가 아님, 리소스가 정확히 1개가 아님, 유형이 `dashboard`가 아님(스키마가 먼저 400으로 거르므로 방어선), 리소스 id가 uuid 형식이 아님(**추가:** Superset 기본 검사가 숫자 id·slug를 대시보드로 인정해 임베드 안 한 대시보드도 통과함을 확인했다, 아래 시험), `user.username` 없음. 포털 DB를 읽지 않으며 로그에는 사유 코드만 남긴다. **"포털 등록 표의 embedded uuid만 허용" 검사는 FU-1e로 이월**(훅의 `_EXTRA_GUEST_TOKEN_CHECKS` 확장 지점, 포털 등록과의 일치는 backend가 발급 전에 보장). backend가 보내는 embedded uuid는 하이픈 있는 36자 소문자 정규형이어야 훅의 형식 검사(`str(uuid.UUID(v)) == v.lower()`)를 통과한다(FU-1e 구현 조건). 임베드로 등록된 uuid인지는 Superset 기본 검사가 이미 확인한다(없는 uuid → 400 `EmbeddedDashboard not found`) | X-28 확인됨, EW-4 시험(발급 계정 REST: 정상 200, `rls` 비어 있지 않음 400, 리소스 0·2개 400, 숫자 id 400, `user` 누락·빈 이름 400, 없는 uuid 400) |
| **직접 서명 금지** | 훅은 **발급 API 경로에서만** 호출된다. 직접 서명한 토큰은 훅을 우회해 비어 있지 않은 `rls`·만료 없는 토큰도 통과한다. 그래서 backend는 `GUEST_TOKEN_JWT_SECRET`을 받지 않고(현 compose도 아님) 토큰을 직접 만들지 않는다. 시험과 `bi-review` 규칙으로 고정(AP-1 승인). **EW-4:** `ci-validate-env.sh`가 backend·migrate 환경과 `backend/app` 코드에 `GUEST_TOKEN_JWT_SECRET`이 없음을 검사하고(네거티브 시험 포함) backend 코드와 의존성에 JWT 서명 라이브러리·토큰 직접 생성 흔적이 없음을 확인했다 | X-28 확인됨 |
| 발급 전용 계정 | 최소 권한: 세션 로그인 + 폼 CSRF면 `can_grant_guest_token SecurityRestApi` 1개, REST(JWT) 로그인이면 `can_read SecurityRestApi` 포함 2개. 서비스 계정과 같은 클라이언트를 재사용하도록 JWT·2개로 확정했다: 역할 `bi_guest_issuer`(`can_grant_guest_token SecurityRestApi` + `can_read SecurityRestApi`)와 계정(기본 이름 `bi_guest_issuer`) **구현됨(EW-3)**. 지연은 세션 재사용 약 26ms, 로그인 포함 약 240ms. `GUEST_TOKEN_JWT_AUDIENCE`는 불필요해 만들지 않는다 | X-28 확인됨, `03b` 4-7 |
| 유효·갱신 | 5분(설정 변경 없음, EW-4에서 6.1.0 기본 `GUEST_TOKEN_JWT_EXP_SECONDS=300`과 실제 적용값 확인). **적용값 가드(03b 12-1 2번)**: `superset-init`이 적용값을 확인해 300이 아니면 실패하게 한다 — **구현됨(EW-5)**: `ensure_roles.py`가 바꾸기 전에 실제 적용값을 확인해 300이 아니면 실패하고(`bi_roles.GUEST_TOKEN_EXP_SECONDS`), `ci-validate-env.sh`가 `superset_config.py`의 재정의를 정적으로 막는다. 값을 바꾸려면 사전 승인과 가드 값 변경이 함께여야 한다. SDK가 만료 5초 전 재호출하므로 보는 중에는 대시보드당 5분에 1회(EW-6 QA: 페이지를 400초 열어 두고 `fetchGuestToken`이 0초·295초에 호출되고 401 없이 차트 200 유지를 확인). 실패 시 10초마다 재시도, 만료 뒤 401과 차트 "Data error"(영문)가 보이다 성공하면 복구. 포털이 401이면 로그인으로(8번 후 재확인) | X-28 확인됨, `03b` 4-5 |
| 제한·실패 | 발급 API는 사용자별 429(`Retry-After`, 승인됨), **한도 값 = 사용자당 슬라이딩 윈도 60초 30회(승인 03b 23-1 C)**, 저장은 프로세스 메모리 [제안](Redis 제외, `03a`). **backend 워커(프로세스)가 여러 개면 한도가 워커별로 걸리므로 실효 한도는 워커 수 배가 된다 — 워커를 늘리면 저장소를 재설계한다(현재 워커 1개 전제, `compose.yml`).** Superset 불가·거부는 502/503 + 한국어 메시지(05) [제안] | `03b` 4-4 Z9, 4-5 |

## 5. 작성자 역할과 대시보드 연결
| 항목 | 내용 | 출처·상태 |
| --- | --- | --- |
| 작성자 역할 | Gamma 복사본(권한 차이 0) + `bi_data` schema 보조 역할. 이름 `bi_author`(Gamma 복사본), `bi_author_schema`(schema 보조) [04 A-3에 반영됨]. 역할 생성은 **구현됨(EW-3)**: `bi_author`는 6.1.0 `Gamma`에서 95개를 처음에만 복사, `bi_author_schema`는 `schema_access` 1개. 내장 `Gamma`는 직접 주지 않는다. `bi_data`의 물리·가상 데이터셋은 보이고 `public`은 못 보며, 차트·대시보드를 만들 수 있고 타인 소유는 수정 못 한다 | `03b` 3-1 Y4, X-20 확인됨 |
| 계정·임베드 | 계정은 관리자가 Superset에서 수동 생성(서버에 사용자·역할 관리 권한 없음). `can_set_embedded`는 주지 않는다: 주면 소유하지 않은 게시 대시보드의 임베드·`allowed_domains`도 바뀐다 → 임베드 켜기는 관리자 수동 | `03b` 5-2 K11 ㄷ, 3-3 Y5, X-20 |
| 복사본 갱신 | `superset init`은 Gamma에만 새 권한을 더하고 복사본은 갱신하지 않는다 → **구현됨(EW-3)**: 매 기동 `Gamma`와의 차이를 로그(`점검 필요: 역할 bi_author이(가) Gamma와 다릅니다`)로만 알리고 권한은 바꾸지 않으며, 업그레이드 때 사람이 점검한다(`deploy-coordination.md` 38번). 관찰: 접근 권한 없는 Gamma가 차트 생성 201(데이터 조회는 403)이며 불변식상 FU-1에서는 수용(후속 확인) | X-20 확인됨, `03c` X-13 부가 |
| 대시보드 연결(S8) | 관리자만 등록·해제. 입력: 제목(`superset_dashboards.name`), embedded uuid(유일), 활성 여부. 팀 필터 기본값 입력은 없다. 해제는 `is_active=false`로 발급을 멈추는 것이며 Superset 임베드는 관리자가 따로 끈다 | `03b` 4-2 Z3 ㄴ, 4-1 Z14 |
| `allowed_domains` | 포털 origin 지정 [제안]. 접근 제어가 아니라 iframe 삽입 제한이다(`/embedded` HTML 요청에만 검사, API엔 없음). 실제 origin 값은 DC 9 협의 뒤 | X-25 확인됨 |
| 안내문(S7) | 새 창 링크 `${supersetRoot}/`, 별도 로그인, 지원 차트 목록과 아래 안내 문구 | `03b` 3-6, X-5 확인됨 |
- 안내 문구: "지원하는 차트는 선, 막대, 표, 큰 숫자(추세 포함), 원형, 혼합(막대+선) 6가지입니다. 다른 유형은 대시보드에서 정상 표시되지 않을 수 있습니다", "차트에 시간 필터가 있어야 날짜 필터가 적용됩니다", 팀 필터는 `team` 열, "일부 화면(필터 설정의 열 선택 등)에서는 내부 번호 이름이 보입니다", "지표 라벨은 만든 시점의 표시 이름으로 굳어 열 표시 이름을 바꿔도 기존 차트의 라벨은 그대로입니다(차트는 깨지지 않음)"(03c A-27 확인됨).
- 번호 이름이 보이는 곳: 네이티브 필터 Column 선택·Explore Filters 칩·Ordering·Customize·Results·View query·View as table·열 툴팁. 표시 이름이 보이는 곳: 데이터셋 패널·열 드롭다운·표 머리글·Drill by·CSV 헤더.

## 6. 하위 경로 + Embedded 재검증과 FU-1 합격 기준 (08 몫)
- 절차: `APP_PROXY_STRIP_PREFIX`를 `false`·`true` 각각으로 포털 → 대시보드 선택 → iframe 렌더 → `chart/data` 200, 4xx 0건(알려진 404인 로고·`service-worker.js`·404 일러스트 제외), guest 부정 시험 상태 코드가 두 값에서 같음(X-25는 같았음). 시점: `bi_guest` 생성 직후(EW-4: QA 완료, 두 값에서 부정 시험 상태 코드 동일, 브라우저 포털 화면은 상태 코드까지만), FU-1e 완료, Superset 업그레이드.
| 번호 | 합격 기준 | 근거 |
| --- | --- | --- |
| P1 | 서비스 계정 4권한만으로 등록·이름 변경·`refresh`·삭제·`related_objects` 성공, 관리자 소유 데이터셋 403·임베드 켜기 403·발급 거부 재현 | X-22 |
| P2 | guest 부정 시험 일부(목록·생성·수정·삭제·SQL Lab·Explore·CSV/XLSX·다른 대시보드·만료·변조·`alg=none`·틀린 `aud`)가 모두 차단, `Public` 0개, `PUBLIC_ROLE_LIKE` 미설정 | X-25 |
| P3 | 훅이 비어 있지 않은 `rls`·resource 2개·type 불일치·임베드 안 한 id를 400으로 거부, backend에 `GUEST_TOKEN_JWT_SECRET`·직접 서명 코드 없음, 발급 계정은 다른 API 403, 서버는 `user`를 항상 전송, 5분 넘게 열어 둬도 SDK 갱신으로 유지, 사용자별 429 동작 | X-28, AP-1 |
| P5 | 지원 차트 6가지(선, 막대, 표, 큰 숫자[추세 포함], 원형, 혼합[막대+선])가 모두 임베딩 화면에서 `bi_guest` 최소 권한으로 정상 표시됨. 추가 권한이 필요한 차트가 나오면 보고하고 멈춘다 | `03b` 6-1, X-25 |
| P4 | Superset을 멈춘 채 데이터셋을 만들면 `pending`/`failed`가 표시되고 입력은 막히지 않으며, 재기동·재시작 뒤 `registered`가 되고 중복 등록이 없음. §3-1 스모크 통과(미시험은 "미시험"으로 남김). 열 표시 이름 전체 열 `PUT` 후 열 수·id 불변, 일부 열만 보내는 호출이 코드에 없음 | §2-1, X-25 |

## 7. 승인 상태 (`03b` 6-3)
| 번호 | 항목 | 내용 | 시점 |
| --- | --- | --- | --- |
| AP-1 | `bi-review` 7-2 확장 | guest 권한 목록 파일 규칙(금지 권한 없음, `Public` 0개 시험)과 서버 코드의 입장권 직접 서명 금지 | 승인됨 |
| AP-2 | 가상 데이터셋 SQL 고정 | `SELECT * FROM bi_data.<뷰>` 고정, 서비스 계정만 등록 | 승인됨 |
| AP-9 | `bi_readonly` `statement_timeout` | 30초 확정(06), EW-1에서 효과 확인 | 승인됨 |
| AP-12 | backend → Superset 주소 | 내부 주소는 compose 서비스 이름 기반 코드 상수(새 변수 없음), `SUPERSET_APP_ROOT`를 backend에 전달 | 승인됨, 적용 완료(EW-3, 2026-10-12) |
| - | 이름 확정·구현 시점 | 발급 전용 계정 변수 이름 `SUPERSET_GUEST_ISSUER_USER`·`_PASSWORD`(AP-16 승인으로 확정). `GUEST_ROLE_NAME=bi_guest`·`GUEST_TOKEN_VALIDATOR_HOOK`은 승인됨이며 EW-4에서 적용·보고됨(`03b` 11-1), `superset-init` 확장도 AP-16으로 승인되어 EW-3·EW-4에서 적용·보고됨(`03b` 9-2, 11-2) | EW-3 적용 완료(2026-10-12, 계정·역할 생성 포함), **EW-4 적용 완료(2026-10-12, `bi_guest` 4권한·훅·`Public` 0개 검사·계정 강제 복구, QA 12항목 통과·reviewer 차단 0건)**, `GUEST_TOKEN_JWT_EXP_SECONDS` 300 가드와 표식 없는 계정 거부는 03b 12-1로 EW-5에서 적용 완료 |
| - | 의존성·값 | frontend Embedded SDK는 FU-1 착수 때 버전·라이선스 확인 후 요청(AP-15, 04 §9-1), `httpx`는 승인됨. 속도 제한 한도 값 | FU-1e |

## 8. 후속 기능 단위에서 결정
- 8번 인증 뒤 Explore 자동 로그인 연동과 X-19, 발급 `user` 식별자 교체.
- 보관·삭제와 Superset: 보관 데이터셋의 노출, 영구 삭제 전 영향 표시, 뷰 `DROP` 전 Superset 정리 순서(K10 ㄷ, X-23).
- 기준값·공통 요약·참조 열 데이터셋의 Superset 등록, 공통 열(기간·팀) 통일 방식.
- 서비스 계정 소유자 이전 시험, 작성자 계정 자동 생성(미채택, 04 §9-1 결번 설명), 대시보드 템플릿 자동 배포.
- `allowed_domains` 실제 origin(DC 9)과 다른 origin일 때의 `frame_options`/CSP 변경, HTTPS·다중 워커 시험, 속도 제한 저장소 재설계, `statement_timeout` 효과 시험, 팀 단위 열람 제한이 필요해질 때의 설계 변경.

## 9. 훅의 embedded uuid 등록 대조: H0 종결과 남는 위험 (2026-10-12, 사용자 결정 03b 23-1 B)
- **결정:** 훅은 Superset 프로세스 안에서 돌고 포털 정적 표를 읽을 권한이 없어서(EW-1 설계, X-15) 라이브 대조(허용 목록 볼륨 H1 등)는 하지 않는다(H0). 대신 **합격 기준 "훅의 uuid 등록 대조"를 아래 두 실측으로 바꾼다.** 기준 문구는 `04-modules.md` §8과 `gate-status.md` 이월 3번에서 이 절을 가리킨다.
- **실측 1(참, 2026-10-12 `docs/research/fu1e-probes.md`):** Superset에 등록된 DB 연결은 `bi_readonly` 하나뿐(메타 DB `dbs` 1건, 관리자 `GET /database/` 1건)이고, `bi_author` 시험 계정은 DB 추가·`test_connection`·`validate_parameters`·`PUT`·`DELETE`·`import`가 모두 403이다(`can_write Database`는 `Admin`만).
- **실측 2(참, 확정 — 사용자 판정 2026-10-13):** `can_set_embedded Dashboard`는 `Admin`만 가지고 `bi_service`는 임베드 관련 권한이 없다. 임베드 설정(`set_embedded`)과 해제(`delete_embedded`)는 둘 다 `can_set_embedded`만 요구하고, `bi_author` 시험 계정의 임베드 설정(POST·PUT)·해제(DELETE)는 403이었다. 참고: `can_write Dashboard`·`can_delete_embedded`는 `Alpha`·`Gamma`·`bi_author`도 가지지만 임베드 설정 경로에서 검사하는 권한이 아니다(전체 역할×권한 표는 프로브 문서 2-2). 이 실측 2는 "임베드 설정 권한"(= 실제로 임베드를 켜고 끄는 권한)을 기준으로 읽는다. **사용자 판정(2026-10-13, 03b 25-1):** 조건의 목적은 미등록 대시보드의 새 임베드 설정을 막는 것이고 `can_set_embedded`는 Admin만 가진다. `can_write Dashboard`는 내용 편집 권한이며, 조건 ①로 Superset이 읽는 데이터는 원래 모두에게 공개된 것뿐이다. 따라서 H0 종결은 확정이다. **`can_delete_embedded` 실측(1e-f QA, 결과만):** (a) `bi_author`는 이 권한이 있어도 자기 소유·남의 대시보드 모두 `DELETE /embedded`가 403이었고 임베드가 그대로 남았다(설정 POST도 403, 원인은 추측: Superset이 이 경로를 다른 권한 이름으로 검사). (b) 관리자가 임베드를 해제한 연결을 S7에서 열면 E6이 502 `SUPERSET_REJECTED`이고 화면은 "대시보드를 열지 못했습니다. 대시보드 서비스가 요청을 받아들이지 않았습니다. 관리자에게 문의해 주세요. 문의 번호: …"+"다시 시도"를 보인다. (c) 임베드를 다시 켜면 uuid가 새로 발급되어 기존 포털 연결(uuid 변경 불가)은 계속 502이고, 새 연결을 등록해야 E6이 200이 된다(이전 연결은 해제).
- **남는 위험:** (1) 발급 계정 비밀이 유출되고 (2) 관리자가 임베드를 켠 포털 미등록 대시보드가 있으면 그 uuid로 입장권을 만들 수 있다(백엔드는 포털에 등록된 활성 uuid만 요청하지만 발급 계정을 직접 쓰는 공격자는 우회한다). 이 입장권은 `bi_guest` 4권한과 훅 거부 규칙(5가지)과 `bi_readonly`의 `bi_data` 읽기 한계 안에 머문다. 완화: 관리자가 Superset에서 임베드를 켠 대시보드를 포털과 일치시키는 운영 절차, 발급 계정 비밀 보호(`.env`·로그·`ps`·`docker inspect` 0건 검사), `deploy-coordination.md` 44번(Superset에 다른 DB 연결을 추가하지 말 것).
- **재검토:** 실측 중 하나가 거짓이 되면(예: `bi_author`에 DB 연결 권한이 생김, 임베드 설정 권한을 가진 역할이 늘어남) H0을 버리지 않고 멈추고 사용자에게 보고한다(H1로 임의 변경 금지).

## 10. 알려진 한계 (1e-f 기록, 2026-10-13, 사용자 결정으로 기록만)
- **E1 읽기 비용(S9):** E1은 요청마다 전체 데이터셋 이름과 동기 행을 읽어 메모리에서 거르고 쪽을 나눈다. S9가 200개씩 이어 읽으면 전체 읽기가 쪽마다 반복되어 데이터셋이 수천 개를 넘으면 느려진다.
- **E2 "전부"·팀 이름 변경의 순차 커밋 비용:** 대상 데이터셋마다 `pending` 표시를 따로 커밋한다(Superset 호출 아님). 대상이 수천 개이면 접수 응답이 길어진다.
- **가짜 Superset의 CSRF 동시성 차이:** 자동 시험의 가짜 서버는 호출마다 새 세션 쿠키·토큰을 따로 기억한다. 실제 Superset에서 여러 요청이 동시에 CSRF를 받는 모양은 확인되지 않았고 실제 Superset 스모크에서만 확인한다.
- **시작 대기 10분 포기 뒤의 `pending`:** 시작 대조를 포기한 뒤 주기 재시도는 연결 문제로 `failed`가 된 데이터셋만 다시 넣는다. 그 시점까지 요청이 없었던 데이터셋은 관리자가 E2를 누르거나 backend를 다시 시작할 때까지 `pending`이다.
- **`registered` 순간 표시:** `_write_result`가 세대를 확인한 뒤 커밋하기 전의 틈에 새 요청이 `pending`을 커밋하면 DB가 잠시 `registered`일 수 있다. 큐에 새 항목이 남아 약 3초 안에 수렴하고 중간 종료는 시작 대조가 잡는다.
- **연결 풀 고갈 시 503:** 5개 흐름이 동시에 열을 추가하면 연결 풀(당시 `pool_size=5`, `max_overflow=0`) 고갈로 일부 요청이 503(`SERVICE_UNAVAILABLE`)이 될 수 있었다(1e 이미지에서도 재현, 회귀 아님). 사용자 결정(2026-10-13)으로 풀을 10+5로 상향했다(코드 상수). 같은 부하의 재측정은 후속 QA.
