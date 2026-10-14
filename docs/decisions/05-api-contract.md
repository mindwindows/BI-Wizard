# 05. REST API 계약 (FU-1 범위)

**상태: 승인(2026-10-11, 03b 6절)** — architect. 이름·역할·enum은 04 부록 A, 필드·권한은 06, 수식 응답은 07, 입장권·동기는 08을 그대로 쓴다. EW-1·3·4 결과 대조(2026-10-12, EW-5): 계약(경로·필드·코드)은 바뀌지 않았고 E6 설명과 구현 상태 표기만 갱신했다. **FU-2a 계약 추가(2026-10-13, `03b` 29-1 범위): §2-7 F1 `GET /audit-logs`, §4 매트릭스 한 줄, §7 갱신. 새 오류 코드·새 환경변수 없음. 기존 엔드포인트의 요청·응답·권한은 바뀌지 않는다(감사 기록은 내부 부수 효과이고, 변경이 없는 요청은 기록도 없다: 04 §5-1).** **FU-2b 계약 추가(2026-10-14, `03b` 30-1 범위): §2-2 B7 `POST /datasets/{id}/archive`·B8 `POST /datasets/{id}/restore`, B1 `status` 쿼리, 새 오류 코드 `DATASET_ARCHIVED`(409), §2-7 F1 `action` 17개, §4 한 줄, §7 갱신. 새 환경변수·새 의존성 없음. 보관 중 정의·입력 쓰기 8개(B4 B5 B6 C2 C3 C4 D4 D5)가 새로 409를 돌려주는 것은 계약 변경이며 30-1로 승인됐다.** **FU-3 계약 추가(2026-10-14, `03b` 32절 범위): §2-8 기준값 R1~R6, B4의 새 422 `BASE_DATE_IN_USE`(C-6), 수식 검사 오류 코드 2개(`REF_UNKNOWN`·`BASE_DATE_REQUIRED`, §3), 셀 오류 `E4`, §2-7 F1 `action` 20개·`target_type`에 `reference`, §3 `WRITE_BUSY` 적용 범위, §4 매트릭스 두 줄, §7 갱신. 새 환경변수·새 의존성 없음. 기존 엔드포인트의 요청·응답 모양은 바뀌지 않는다(B4는 기준 날짜 열을 해제하는 요청이 `REF` 사용 데이터셋에서 새로 422를 받는 것만 다르며 32-3 C-6으로 승인됨).**
- 의존 결정: 브리프 5절 3·6·8(스텁 전제)·9·10번, `03b` 1-3·1-6·2-4·3-3·3-4·4-2·5-2(K2·K3·K7·Z6), 실험 `03c` X-24·X-28. 결정 원문은 반복하지 않고 `03b n-n`으로만 건다. 구현 상세(클래스·SQL)는 담지 않는다.
- [제안]·[미답] 표지는 `03b` 6-2에 따라 모두 승인된 것으로 읽는다(남은 [AP]는 `03b` 6-3 기준).
- 표지: **[제안]** 이 문서가 처음 내는 안 / **[미답]** 사용자 답 없음(기본값 사용) / **해소(03c A-27)** 표시 이름 갱신은 서버 내부 흐름이라 이 계약의 필드는 변하지 않는다(08 §2-3) / **[AP]** §6 승인 필요. 공통 규칙(경로·오류 형식·상태 코드·목록·값 형식·충돌 응답)은 사용자 답이 없어 기본값으로 쓰며 **[미답]**이다.

## 1. 공통 규칙
| 항목 | 규칙 | 출처 |
| --- | --- | --- |
| 경로 | 모든 경로는 `${APP_BASE_PATH}/api/…`이고 아래 표는 `/api` 뒤만 쓴다. 버전 접두어 없음. 프록시가 접두를 떼든 말든 같은 경로(STRIP true/false 모두). 프런트는 `config.ts`의 `apiUrl()` 한 곳에서 조립하고 경로를 하드코딩하지 않는다 | [미답], 04 §5 |
| 경계 | 브라우저는 FastAPI만 호출한다. DB·Superset REST 직접 호출 없음(Superset은 Embedded iframe·새 창 링크만). 요청 본문의 `rls`·Superset 숫자 id는 받지 않는다 | 04 §5, 08 §4 |
| 형식 | JSON UTF-8, 필드 snake_case, id는 정수. 날짜 `YYYY-MM-DD`(월·연 단위도 기간 첫날, 예 `2026-03-01`), 시각 ISO 8601 `+09:00`. 첫날이 아닌 날짜는 거부(`NOT_PERIOD_START`). **`number` 값은 십진 문자열 `"1234.50"`, 미입력은 `null`** [제안: `numeric` 38자리가 JS 숫자 정밀도를 넘을 수 있어 일반 JSON 숫자 기본값과 다름, 승인 03b 6-2]. 글자는 NFC로 정규화해 저장 | 03b 2-2 W3-2, 07 §3 |
| 이름 규칙 | 표시 이름 길이 상한 [제안]: 팀 50·사용자 표시 이름 100·로그인 ID 200(03b 17-1 결정 4)·데이터셋 100·열 100자·기준값 항목 이름 50자와 설명 200자(FU-3, 항목 이름 규칙은 06 §2-2)(Superset 열 표시 이름은 1,024자를 넘으면 원인 없는 422이므로 앱이 먼저 막는다, 03c A-27). 열 이름에 `[` `]` `"`·제어문자 금지, `team`·`팀`·`row_id`·`행 번호` 예약어(07 §1, 06 §3-3). 위반은 `VALIDATION_ERROR`(필드 코드 `TOO_LONG`·`BAD_FORMAT`·`RESERVED`) | 06 §2, 07 §1 |
| 인증 | `/health` 외 모두 `current_user` 한 곳을 거친다. 신원 없음 401 `UNAUTHENTICATED`, 신원은 있으나 `users`에 없음 403 `USER_NOT_REGISTERED`, 비활성 403 `USER_INACTIVE`, **사용자 조회 중 DB 장애는 503 `SERVICE_UNAVAILABLE`로 로그아웃(401)과 구분하며 접근은 닫혀 있다(03b 17-1 결정 2)**. 신원 출처(헤더/토큰/로그인)는 8번 미결정이라 계약에 없다 | 03b 1-1, 5-2 K3 |
| 권한 표기 | `공개` 인증 불필요 / `읽기` 인증된 활성 사용자 전부(타 팀 포함) / `관리자` `users.is_admin` / `정의(팀)` 그 데이터셋 팀의 `definer`(관리자라도 팀 소속이 아니면 불가 [제안, 06 §4-1]) / `입력(팀)` 그 팀의 `entry` 또는 `definer` **[미답: 정의 담당자 입력 가부, 06 §4-1]** / `스텁` 스텁이 켜진 환경에서만 존재 | 03b 1-3, 5-2 K2, 06 §4 |
| 오류 | `{"error": {"code", "message", "details", "request_id"}}`. `message`는 한국어 사용자 문구(SQL·내부 용어 금지). 입력 검증 오류도 같은 형식: `code=VALIDATION_ERROR`, `details.fields[{field 또는 row_index+column_id, code, message}]`(본문을 JSON으로 읽지 못한 형식 오류는 `field`가 오류 위치 번호 문자열이다). 응답 헤더 `X-Request-ID` | [미답], 07 §9 |
| 상태 코드 | 형식 오류(깨진 JSON·잘못된 쿼리·경로 형식 포함)와 규칙 위반은 모두 422 `VALIDATION_ERROR`로 통일(03b 17-1 결정 1, 400은 쓰지 않음) / 401 / 403 / 404 / 409 충돌 / 413 크기 / 422 규칙 위반 / 429 제한(`Retry-After`, 코드로 구분) / 405 `METHOD_NOT_ALLOWED` / 502·503 Superset 불가·DB 장애 `SERVICE_UNAVAILABLE` / 500 `INTERNAL_ERROR`(상세는 로그에만). 행 쓰기의 락 대기 초과·교착(`55P03`·`40P01`)은 503 `WRITE_BUSY`(재시도 가능, §3) | [미답] |
| 잘림 표시 | 응답이 항목 수 상한에서 잘리면 `details.truncated: true`와 전체 건수 `details.total`을 함께 준다(검증 오류 `details.fields[]`는 200건, 충돌 `details.conflicts[]`는 1,000건에서 자름). 화면은 "일부만 표시됨"을 안내한다(03b 19-1 결정 4) | 03b 19-1 |
| 목록 | 쿼리 `limit`(기본 50, 최대 200)·`offset`, 응답 `{items, total, limit, offset}`. 그리드의 부분 로딩은 AG Grid Community 지원 확인 뒤 적용(Enterprise 방식 금지) | [미답] |
| 동시성 | 정의를 바꾸거나 행을 쓰는 요청은 `expected_version`(읽은 `def_version`)을 싣는다. 기존 행의 칸 수정은 칸마다 `expected` 키가 **필수**다(값 `null` = 빈 칸이었음, 키 생략·`expected` 전체 `null`은 422로 가드 우회를 막는다). 이미 같은 값이면 200. 모든 쓰기 성공 응답에 새 `def_version` | 03b 3-4 Y8, 06 §5, 03c X-24 |
| 충돌 | HTTP 409 + 코드: `CELL_CONFLICT`·`PASTE_CONFLICT`·`DEFINITION_VERSION_MISMATCH`(04 후보) + `PERIOD_CONFLICT` **[제안, 04 A-3에 반영됨]**. `details`는 §3 표 | [미답] |
| 계약 변경 | 필드·엔드포인트 추가는 허용. 이름·타입·의미·코드·권한의 변경·삭제는 **계약 변경**: 변경 전후 비교표를 만들어 사용자 승인 → 이 문서, backend 스키마, 프런트 훅, 시험을 한 번에 고치고 reviewer가 대조 | `modularize` |

### 공통 형태
| 이름 | 필드 |
| --- | --- |
| Column | `{id, display_name, type, kind, required, rules, tag, position}`. `rules`: number `{min, max, decimals}` / text `{max_length}` / date `{min, max}` / choice `{options[]}` (06 §3-2). 계산 열(`kind=formula`)의 `type`은 결과 형 |
| Dataset | `{id, team_id, name, date_unit, base_date_column_id, status(`active`\|`archived`), def_version, created_by{id, display_name}, created_at}`. 상세는 `team{id, code, name}`, `columns[Column]`, `permissions{define, enter}` 추가 |
| Row | `{row_id, cells{"<column_id>": 값 또는 null}, errors{"<column_id>": "E1"}}`. 계산 열 칸은 값 `null` + `errors`로 오류 칸과 미입력을 구별한다(`errors`에 있으면 오류 칸). 오류 판정 구조(07 §3-1 E-A 제안, 대안 판정 SELECT)와 무관하게 응답 모양은 같다 |

## 2. 엔드포인트
ID는 04 §6 소단위 기준(A=1a 권한, B=1b 정의, C=1c 입력, D=1d 수식·점검, E=1e Superset, F=FU-2a 감사 로그; B7·B8은 FU-2b 보관·복구; R=FU-3 기준값). 모듈·Skill은 04 §2·§6. "오류"는 §1 공통(401·403·404·500)을 뺀 주요 코드다.
### 2-1. 권한 관리 — `access` · `permission-management`
| ID | 메서드 경로 | 권한 | 요청 | 성공 응답 | 오류 |
| --- | --- | --- | --- | --- | --- |
| A1 | GET `/me` | 읽기 | - | 200 `{id, display_name, is_active, is_admin, memberships[{team_id, team_code, team_name, team_is_active, role}]}` (비활성 팀 소속도 나오며 화면은 `team_is_active`로 작업 팀 선택에서 거른다) | 403 미등록·비활성, 503 `SERVICE_UNAVAILABLE` |
| A2 | GET `/teams` | 읽기 | 목록 | 200 `{id, code, name, is_active}` 목록 | - |
| A3 | POST `/teams` | 관리자 | `{code, name}` (`code` 불변, 형식 `^[a-z0-9_]{1,32}$` [제안: 뷰에 글자로 들어가므로 제한]) | 201 team | 409 `ALREADY_EXISTS`, 422 |
| A4 | PATCH `/teams/{team_id}` | 관리자 | `{name?, is_active?}` (이름이 바뀌면 커밋 뒤 팀 단위 동기화 요청으로 그 팀의 가상 데이터셋 이름도 갱신, 08 §2-1) | 200 team | 409, 422 |
| A5 | GET `/users` | 관리자 | `q, team_id, is_active` + 목록 | 200 `{id, login_id, display_name, is_admin, is_active, memberships[{team_id, role}]}` 목록 (S6 팀×사용자 격자는 이 응답으로 그림) | - |
| A6 | POST `/users` | 관리자 | `{login_id, display_name, is_admin?}` (사전 등록) | 201 user | 409 `ALREADY_EXISTS` |
| A7 | PATCH `/users/{user_id}` | 관리자 | `{display_name?, is_admin?, is_active?}` | 200 user | 409 `LAST_ADMIN`(마지막 활성 관리자 해제·비활성) [제안] |
| A8 | PUT `/teams/{team_id}/members/{user_id}` | 관리자 | `{role: "definer"\|"entry"}` (없으면 추가, 있으면 역할 변경. 비활성 팀·비활성 사용자에 대한 **추가·변경은 거부**) | 200 `{team_id, user_id, role}` | 404, 409 `TARGET_INACTIVE` |
| A9 | DELETE `/teams/{team_id}/members/{user_id}` | 관리자 | - | 204 | 404 |

### 2-2. 데이터셋·열 정의 — `dataset` · `dataset-definition`
| ID | 메서드 경로 | 권한 | 요청 | 성공 응답 | 오류 |
| --- | --- | --- | --- | --- | --- |
| B1 | GET `/datasets` | 읽기 | `team_id?`, `status?`(`active`\|`archived`\|`all`, 기본 `active`, FU-2b) + 목록 | 200 Dataset 목록(`status` 필터는 `total`에도 같게 적용). 정렬: 내 소속 팀 먼저, 다음 팀 이름·데이터셋 이름(03b 2-4, 이름순은 한글 가나다순, 03b 19-1 결정 2. A2·A5도 이름순). 동기 상태는 E1에서 받아 화면이 결합(04 §3: dataset은 superset을 읽지 않음) | 422 `VALIDATION_ERROR`(`status`가 목록 밖이면 필드 `status`에 `NOT_IN_OPTIONS`) |
| B2 | POST `/datasets` | 정의(`team_id` 팀) | `{team_id, name, date_unit: "day"\|"month"\|"year"}` | 201 Dataset 상세. 등록 + `ds_`·`dv_` 생성이 한 트랜잭션(06 §3-5), 커밋 뒤 Superset 백그라운드 동기화 요청(등록 행이 없으면 E1이 `pending`으로 표시) | 409 `ALREADY_EXISTS`(팀 안 이름, 같은 이름이 보관된 데이터셋이면 메시지에 "보관된 데이터셋과 같은 이름" 덧붙임: B4도 같음. `details.field=name` 그대로, FU-2b), 409 `TARGET_INACTIVE`(`details.field=team`, 비활성 팀의 데이터셋 생성 불가, 03b 19-1 결정 1), 422, 503 `DEFINITION_BUSY` |
| B3 | GET `/datasets/{id}` | 읽기 | - | 200 Dataset 상세 | 404 |
| B4 | PATCH `/datasets/{id}` | 정의(팀) | `{expected_version, name?, date_unit?, base_date_column_id?}` | 200 Dataset 상세 | 409 `DATASET_ARCHIVED`(보관 중, 버전 비교보다 먼저), 409 `DEFINITION_VERSION_MISMATCH`(`details.current_version`), 422 `DATASET_HAS_ROWS`(날짜 단위·기준 날짜 열은 행 0개일 때만, 06 §3-3), **422 `BASE_DATE_IN_USE`(FU-3 C-6: `REF`를 쓰는 계산 열이 있는 데이터셋에서 `base_date_column_id: null`로 해제. 행이 0개일 때만 도달하며 `DATASET_HAS_ROWS` 다음에 판정, 훅의 재컴파일이 판정하므로 열 변경·DDL이 함께 롤백됨. `details.column{column_id, display_name}`은 훅의 전체 재컴파일이 처음 걸린 `REF` 계산 열(전부 나열하지 않음). 이 변환은 `formula`의 실패 변환 함수가 `BASE_DATE_REQUIRED`만으로 이뤄진 실패를 편집 열 없는 호출(B4)에서 만났을 때 한다. 문구 "REF를 쓰는 수식이 있어 기준 날짜 열을 해제할 수 없습니다. 먼저 그 수식을 고치거나 다른 날짜 열로 바꾸세요")**, 422(기준 열은 `raw` `date` 열만), 409 `ALREADY_EXISTS`(팀 안 이름), 503 `DEFINITION_BUSY` |
| B5 | POST `/datasets/{id}/columns` | 정의(팀) | `{expected_version, display_name, type, required?, rules?, tag?, position?}` (원본 열만. 계산 열은 D4) | 201 `{column, def_version}` | 409 `DATASET_ARCHIVED`, 409 `DEFINITION_VERSION_MISMATCH`·`ALREADY_EXISTS`(열 이름), 422 `VALIDATION_ERROR`(예약어·금지 문자·길이), 503 `DEFINITION_BUSY` 검증 순서(FU-2b 구현): 규칙·태그 422 검증은 `datasets` 행 잠금 아래에서 하므로 보관 409가 검증 422보다 먼저이고, 활성 데이터셋에서도 버전 불일치 409가 규칙 오류 422보다 먼저다 |
| B6 | PATCH `/datasets/{id}/columns/{col_id}` | 정의(팀) | `{expected_version, display_name?, required?, rules?, tag?, position?}`. `type`·`kind` 변경 불가 | 200 `{column, def_version}`. 태그 변경은 순환 재검사(07 §7) | 409 `DATASET_ARCHIVED`, 409 `DEFINITION_VERSION_MISMATCH`·`ALREADY_EXISTS`(열 이름), 422 `COLUMN_LOCKED`(type·kind), 422 `FORMULA_CIRCULAR`, 503 `DEFINITION_BUSY` |
| B7 | POST `/datasets/{id}/archive` | 정의(팀) | 본문 없음(있으면 422), `expected_version` 없음 (FU-2b, `03b` 30-1). `status`만 `archived`로 바꾼다 | 200 Dataset 상세(`status="archived"`, `def_version` 그대로). 이미 `archived`면 200이며 아무것도 바꾸지 않고 감사도 0건 | 403, 404, 503 `DEFINITION_BUSY`(락 대기 초과) |
| B8 | POST `/datasets/{id}/restore` | 정의(팀) | B7과 같음. `status`만 `active`로 바꾼다 | 200 Dataset 상세(`status="active"`). 이미 `active`면 200·감사 0건 | 403, 404, 503 `DEFINITION_BUSY` |
- B7·B8 규칙(FU-2b): ① 권한은 그 데이터셋 팀의 `definer`뿐이다. **관리자 예외 없음**(관리자라도 그 팀 `definer`가 아니면 403). ② **팀이 비활성이어도 허용**한다(팀 활성 여부를 보지 않음, 03b 30-1 결정 3). ③ 한 호출은 `datasets` 행 한 줄의 `status` UPDATE와 `audit_log` INSERT 한 줄(`dataset.archive`·`dataset.restore`)이 한 트랜잭션이다. `def_version`·`def_hash`·`ds_`·`dv_`·`de_`는 건드리지 않고 DDL·formula 훅·Superset 동기 요청이 0건이다(06 §5). ④ 응답의 `permissions`·`columns`는 B3과 같은 상세 모양이다. ⑤ 보관해도 `dv_` 뷰는 `bi_readonly`에 공개되고 Superset 가상 데이터셋·차트는 남는다(03b 30-1 결정 1, 08 §9). 데이터를 감추려면 영구 삭제 단위가 따로 필요하며 화면·Skill이 이 한계를 사용자에게 알린다(04 §4). ⑥ 판정 순서는 기존 정의(팀) 엔드포인트와 같다: 인증 → 데이터셋 없음 404 → 정의 담당자 아님 403(`require_dataset_definer`) → 행 잠금 → 같은 상태면 200 종료(롤백, 감사 0건).
- **보관 중 거부 규칙(DATASET_ARCHIVED, FU-2b):** `status='archived'`인 데이터셋에 대해 **B4·B5·B6·C2·C3·C4·D4·D5**는 409 `DATASET_ARCHIVED`(§3)다. 판정은 `datasets` 행 잠금을 잡고 그 행을 읽은 **직후, `expected_version` 비교(`DEFINITION_VERSION_MISMATCH`)·검증 422보다 앞**에서 한다(존재 404·권한 403 다음). **보관 중에도 동작하는 것:** A 전체, B1 B3(+B8), C1, D1 D2 D3 D6 D7 D8 D9, **D10 retry**(뷰 재생성은 정의 변경이 아니라 대조 복구이므로), E1~E6. B2는 새 데이터셋이라 해당 없다(보관된 데이터셋과 같은 이름이면 `ALREADY_EXISTS`).

### 2-3. 입력 그리드 — `entry` · `data-entry`
| ID | 메서드 경로 | 권한 | 요청 | 성공 응답 | 오류 |
| --- | --- | --- | --- | --- | --- |
| C1 | GET `/datasets/{id}/rows` | 읽기 | `order=asc\|desc`(기준 날짜 열, 없으면 `row_id`) + 목록 | 200 `{def_version, items[Row], total, limit, offset}`. 계산 열 값·`errors`는 formula가 `RowViewPort`로 제공(04 §3) | 404, 429 `PREVIEW_BUSY`(전역 동시 상한, 07 §5) |
| C2 | POST `/datasets/{id}/rows` | 입력(팀) | `{expected_version, cells{"<column_id>": 값}}` (원본 열만, 필수 열 전부 필요. 기준 날짜 열은 DB NOT NULL이므로 `required=true`로 취급해 `REQUIRED`로 판정) | 201 `{row, def_version}` | 409 `DATASET_ARCHIVED`, 409 `PERIOD_CONFLICT`·`DEFINITION_VERSION_MISMATCH`, 422 `VALIDATION_ERROR`(필드 코드 `REQUIRED`·`OUT_OF_RANGE`·`BAD_FORMAT`·`NOT_IN_OPTIONS`·`NOT_PERIOD_START`·`READ_ONLY`·`TOO_LONG`), 503 `WRITE_BUSY` |
| C3 | PATCH `/datasets/{id}/rows/{row_id}` | 입력(팀) | `{expected_version, changes[{column_id, expected, value}]}` (`expected` 키 필수, §1 동시성. 한 요청의 칸 전부가 가드, 하나라도 충돌하면 전체 취소) | 200 `{row, def_version}` | 404 `ROW_NOT_FOUND`, 409 `DATASET_ARCHIVED`, 409 `CELL_CONFLICT`(`details.conflicts[{row_id, column_id, current}]`), `PERIOD_CONFLICT`(이미 있는 기간으로 이동), `DEFINITION_VERSION_MISMATCH`, 422, 503 `WRITE_BUSY` |
| C4 | POST `/datasets/{id}/rows/paste` | 입력(팀) | `{expected_version, column_ids[], rows[{row_id, expected[], values[]}]}` (규칙은 아래 목록) | 200 `{updated, created, created_rows[{index, row_id}], def_version}` | 409 `DATASET_ARCHIVED`, 409 `PASTE_CONFLICT`(전부 취소, `details.conflicts[{row_index, row_id, column_id, kind: "cell"\|"period"\|"row_missing", current}]`), 409 `DEFINITION_VERSION_MISMATCH`, 413 `PAYLOAD_TOO_LARGE`, 422 `VALIDATION_ERROR`, 503 `WRITE_BUSY` |
- C4 규칙: 값은 문자열\|null(파서는 화면 몫, 07 §9)이고 서버가 열 타입으로 해석·재검증한다. `row_id=null`은 새 행(`expected` 없음), 정수는 기존 행이며 이때 `expected[]`가 **필수**(칸마다 화면이 가진 이전 값, 빈 칸 `null`)다. 처리 순서는 기존 행 `row_id` 오름차순 갱신 → 새 행 기간 오름차순(기준 날짜 열이 없으면 입력 순) 삽입으로 고정해 교착을 막고, 충돌은 첫 건에서 멈추지 않고 모아 한 번에 돌려준다(06 §5). **기존 행에서 값이 `expected`와 같은 칸은 쓰지도 가드로 쓰지도 않는다(C3는 `changes`의 모든 칸이 가드이므로 다르다. 남이 건드린 다른 칸 때문에 헛충돌이 나지 않게 하려는 해석, 06 §5)**. **기존 행의 기준 날짜 열 값은 C4로 바꿀 수 없다**(`VALIDATION_ERROR` 필드 코드 `READ_ONLY`; 기간 이동은 C3 단건만, 유일 인덱스 위반으로 트랜잭션이 중단되어 충돌 목록에 못 모이기 때문). 그래서 `conflicts.kind="period"`는 새 행 삽입의 기간 충돌만 뜻한다.
- C4 요청 상한 **A 승인(`03b` 6-2)**: 5,000행·요청 1MiB 이하(현재 nginx 기본 `client_max_body_size` 1m 안)이며 B안(상한을 늘리고 `frontend/nginx/templates/default.conf.template`의 `client_max_body_size`를 "요청 상한 + 1MiB"로 변경)은 채택하지 않았다. 1MiB는 nginx 기본 1m과 같아 요청이 백엔드 `PAYLOAD_TOO_LARGE`(JSON)에 닿기 전에 nginx 413(JSON 아님)을 받을 수 있으므로 프런트는 JSON이 아닌 413도 같은 안내로 처리한다.
- **임시 행(draft) [제안]**: 필수 열 때문에 한 칸씩 입력하는 새 행은 서버에 저장하지 않는다. 화면이 클라이언트 메모리에서 필수 칸을 모두 채우면 C2를 한 번 부른다(붙여넣기 새 행은 C4 한 번). 서버에 `draft` 상태·표 열이 없다. 비용: 새로고침하면 미저장 행이 사라지고 다른 사용자에게 보이지 않으며, 같은 기간 충돌은 저장 때 알려진다. 대안(서버 draft 열)은 `ds_`·뷰·요약에 제외 조건이 들어가 후속 비용이 커서 비추천.
- 행 삭제·보관 엔드포인트는 없다(행 보관은 후속). 데이터셋 보관은 B7·B8(§2-2)이고, 보관 중 C2~C4는 409 `DATASET_ARCHIVED`다(`DATASET_ARCHIVED`는 행 잠금 `FOR SHARE`를 잡고 그 행을 읽은 직후, 버전 비교보다 앞에서 판정하며 보관 커밋을 기다린 쓰기도 갱신된 행을 읽어 같은 코드를 받는다: 06 §5).

### 2-4. 수식·점검 — `formula` · `formula-column`
| ID | 메서드 경로 | 권한 | 요청 | 성공 응답 | 오류 |
| --- | --- | --- | --- | --- | --- |
| D1 | GET `/formulas/functions` | 읽기 | - | 200 `{functions[{name, signature, returns, help_ko, excel_diff}], cell_errors{"E1": 문구, …}}` (자동완성·도움말, 함수 사전에서 생성. 열 이름·태그는 B3의 `columns`로 클라이언트가 완성) | - |
| D2 | POST `/datasets/{id}/formulas/check` | 정의(팀) | `{expression, column_id?}` (`column_id`=편집 중 계산 열, 자기 참조·순환 기준) | 200 `{ok, result_type, refs[{column_id, display_name}], errors[{code, message, start, end}]}`. C0 검사 실패도 200(`ok=false`, 쉬운 말 문구·위치) | 404 |
| D3 | POST `/datasets/{id}/formulas/preview` | 정의(팀) | `{expression, column_id?}` (저장 없음, 읽기 전용 트랜잭션) | 200 `{result_type, rows[{row_id, period, value, error}], total_rows, error_count, empty_count, def_version}`. `rows`는 기준 날짜(없으면 `row_id`) 최근 순 20행(07 §5) | 422 `FORMULA_INVALID`(`details.errors`는 D2와 같음), 422 `FORMULA_RUNTIME_ERROR`(시간 초과 포함), 429 `PREVIEW_BUSY`(사용자당 동시 1건, 전역 동시 상한 초과도 같은 코드, 07 §5) |
| D4 | POST `/datasets/{id}/formulas` | 정의(팀) | `{expected_version, display_name, expression, tag?, position?}` (계산 열 만들기) | 201 `{column, def_version}`. dataset 정의 변경 진입점 안의 한 트랜잭션: 열 INSERT → formula 훅(수식·의존·뷰) → `def_hash` 기록(04 §5, 07 §8) | 409 `DATASET_ARCHIVED`, 409 `DEFINITION_VERSION_MISMATCH`·`ALREADY_EXISTS`, 422 `FORMULA_INVALID`·`FORMULA_CIRCULAR`(`details.path` 열 이름 경로), 503 `DEFINITION_BUSY` |
| D5 | PUT `/datasets/{id}/formulas/{col_id}` | 정의(팀) | `{expected_version, expression}` | 200 `{column, def_version, result_type_changed}`. 결과 형이 바뀌면 계산 열의 `type`(결과 형)을 같은 진입점이 갱신하고 `true`(저장된 차트 영향 안내용, 영향 차트 수는 후속) | D4와 같음(`DATASET_ARCHIVED` 포함), 404 |
| D6 | GET `/datasets/{id}/formulas/{col_id}` | 읽기 | - | 200 `{column_id, text, refs[{column_id, display_name, kind}], tag_columns[display_name], error_count}`. `text`는 현재 열 이름으로 풀어 쓴 형태(07 §9). 원문 `expression`은 응답에 없고 편집기 시작값은 `text` [제안] | 404 |
| D7 | GET `/checks/formula-errors` | 읽기 | 목록 | 200 `{dataset_id, dataset_name, team_name, column_id, column_name, error_count}` 목록(오류 칸이 있는 열만, S5; 활성 데이터셋만 대상이다. 보관 데이터셋은 FU-2b에서도 포함하지 않는다(코드 변경 없음, 알려진 한계: 보관 중 오류 칸은 이 목록에 안 보인다)) [제안: 읽기, 06 §4-1 열람과 같은 취급] | 429 `PREVIEW_BUSY`(전역 동시 상한) |
| D8 | GET `/datasets/{id}/formula-errors` | 읽기 | `column_id?` + 목록 | 200 `{row_id, period, column_id, error, message}` 목록 | 404, 429 `PREVIEW_BUSY` |
| D9 | GET `/checks/views` | 관리자 | - | 200 `{views, views_failed_count, failed[{dataset_id, dataset_name, reason, since}]}`. `reason`은 사유 코드·요약뿐(SQL·비밀 금지). `/health` 필드와 같은 집계(S9) | - |
| D10 | POST `/checks/views/retry` | 관리자 | `{dataset_ids?}` (생략 = 실패 전부) | 200 `{rebuilt, views_failed_count}`. 요청 안에서 끝까지 처리, 데이터셋별 짧은 트랜잭션과 정의 변경과 같은 `datasets` 행 잠금(07 §8) | 503 `DEFINITION_BUSY` **[1e 구현 확정]** 뷰를 다시 만든 데이터셋은 커밋 뒤 Superset 동기화를 요청한다(부수 효과) |

- **`REF` 수식과 D1~D6(FU-3, `03b` 32, 07 §3-2):** 요청·응답 모양은 그대로다. D1 `functions`에 `REF`가, `cell_errors`에 `E4`가 사전에서 자동으로 들어간다. D2는 `REF` 오류를 200 `ok=false`의 `errors[].code`(`REF_UNKNOWN`·`BASE_DATE_REQUIRED`, 기존 `ARG_COUNT`·`CONST_REQUIRED`·`TEXT_CONSTANT_INVALID` 포함)로, D3·D4·D5는 422 `FORMULA_INVALID`의 `details.errors`로 돌려준다. 결과 형은 늘 `number`다. D3 미리보기 `rows[].error`와 C1·D8의 오류 코드에 `E4`가 나올 수 있다.

### 2-5. Superset·대시보드 — `superset` · `dashboard-link`
| ID | 메서드 경로 | 권한 | 요청 | 성공 응답 | 오류 |
| --- | --- | --- | --- | --- | --- |
| E1 | GET `/superset/datasets` | 읽기 | 목록 | 200 `{dataset_id, superset_name, sync_status, synced_at, last_error}` 목록. 등록 행이 없는 데이터셋은 `pending`(04 A-3). `last_error`는 관리자에게만, 다른 사용자는 `null` [제안: 06 §4-1은 동기 현황을 관리자로 두었으나 04 S2 목록이 상태 열을 가짐] | - **[1e 구현 확정(03b 23-1 E ③)]** 쿼리 `limit`·`offset`·`sync_status`·`team_id`·`dataset_id`(반복)·`dataset_ids`(쉼표 목록) 추가, 응답은 `{items, total, limit, offset}` |
| E2 | POST `/superset/sync` | 관리자 | `{dataset_ids?}` (생략 = `pending`·`failed` 전부) | 202 `{accepted[dataset_id]}`. 결과는 E1로 확인. Superset 불가가 다른 API를 막지 않는다(08 §2-1) | 404 **[1e 구현 확정]** 본문 생략 또는 `dataset_ids` 생략이면 등록 행이 없거나 `pending`·`failed`인 것 전부, 번호가 하나라도 없으면 전체 404, 최대 1,000개, 접수만 하는 202. **[1e-f]** 접수된 항목은 3초 디바운스 뒤에 처리된다(같은 데이터셋의 반복 접수는 한 번의 Superset 호출로 합쳐짐, 08 §2-1) |
| E3 | GET `/dashboards` | 읽기 | `include_inactive?`(관리자만) + 목록 | 200 `{id, name, embedded_uuid, is_active}` 목록. 임베드 SDK가 uuid를 쓰므로 응답에 포함 [제안, 승인]. 08 §4 "클라이언트가 보낸 id는 받지 않는다"와 충돌하지 않는다: uuid는 읽기로만 공개되고 입장권 요청(E6)은 포털 `id`만 받는다 | - **[1e 구현 확정]** 응답은 `Page`(`{items,total,limit,offset}`) 형태, 이름순 |
| E4 | POST `/dashboards` | 관리자 | `{name, embedded_uuid}` (관리자가 Superset에서 임베드를 켜고 받은 번호를 수동 입력) | 201 dashboard | 409 `ALREADY_EXISTS`, 422(uuid 형식) **[1e 구현 확정]** `name` 1~100자, `embedded_uuid`는 공백 제거·소문자 뒤 하이픈 36자 정규형만 받는다(대문자 입력은 소문자로 정규화) |
| E5 | PATCH `/dashboards/{id}` | 관리자 | `{name?, is_active?}` (uuid 불변. 해제는 `is_active=false`, Superset 임베드는 관리자가 따로 끈다) | 200 dashboard | 404 |
| E6 | POST `/dashboards/{id}/guest-token` | 읽기 | 본문 없음(있으면 422). 포털 대시보드 `id`만 받고 서버가 등록 표의 uuid를 찾는다. `rls`는 서버 고정 빈 목록, `user`는 서버가 항상 채운다(08 §4). 활성 여부는 backend가 확인하고(해제 = 발급 중단), Superset 검증 훅은 포털 표를 읽지 않고(`rls` 빈 목록·리소스 1개 `dashboard`·uuid 형식·`user`만 거부, 포털 등록 표 일치 검사는 FU-1e 이월, EW-4 구현) 임베드 존재는 Superset 기본 검사가 확인하므로 오타·미임베드 uuid는 Superset이 400으로 거부해 502 `SUPERSET_REJECTED`가 된다. backend는 uuid를 하이픈 있는 36자 소문자 정규형으로 보낸다(훅 형식 검사, 08 §4) | 200 `{token, expires_in}` (5분, `Cache-Control: no-store`, 로그 금지). SDK가 만료 전 다시 부른다 | 404(없음·비활성), 429 `GUEST_TOKEN_RATE_LIMITED`(`Retry-After`, 사용자별), 502 `SUPERSET_REJECTED`, 503 `SUPERSET_UNAVAILABLE` **[1e 구현 확정(03b 23-1 E ③)]** `expires_in`은 상수 300, 응답 `Cache-Control: no-store`, 사용자별 슬라이딩 윈도 60초 30회 초과 시 429 `GUEST_TOKEN_RATE_LIMITED`(`Retry-After`, 워커별 적용). **[1e-f]** 발급 계정 로그인 거부(`AUTH_FAILED`)는 502 `SUPERSET_REJECTED` 그대로이고 인증(401·403)이 본문 검사(422)보다 먼저이며, 거부 뒤 30초는 Superset을 부르지 않고 즉시 같은 502, `httpx.HTTPError`가 아닌 예상 밖 예외도 502(전역 500 아님, 08 §2-2) |

### 2-6. 상태 확인 · 개발·시험 전용
| ID | 메서드 경로 | 권한 | 요청 | 성공 응답 | 오류 |
| --- | --- | --- | --- | --- | --- |
| H1 | GET `/health` | 공개 | - | 200 `{status, app, views, views_failed_count, public_create, db_timezone}`. 기존 `status`·`app` 유지, `views` = 시작 대조가 확인한 데이터셋(활성·보관, FU-2b)의 뷰 수, `views_failed_count` = 그중 실패 수 [제안], 새 필드는 시작 자가 점검·뷰 대조가 채운 **메모리 값**이라 DB를 건드리지 않는다 [제안: 지금 `/health`는 DB 비접속]. 뷰 실패가 있어도 상태 코드 200(Docker healthcheck 유지, 03b 3-6). 공개 응답이므로 개수·불리언·시간대만 | - |
| H2 | GET `/health/db` | 공개 | - | 기존 그대로: 200 `{status, database}` / 503 | - |
| DV1 | GET `/dev/stub-users` | 스텁 | - | 200 `{items[{login_id, display_name, is_admin}], current}` (화면 S1의 스텁 신원 전환기용) | - |
| DV2 | PUT `/dev/stub-user` | 스텁 | `{login_id}` | 204 + 스텁 신원 쿠키 설정(이름 `bi_stub_login`, HttpOnly) [제안] | 404 미등록 |
| DV3 | DELETE `/dev/stub-user` | 스텁 | - | 204, 쿠키 삭제 | - |
- Skill: H1·H2는 `local-environment`, DV1~DV3는 `permission-management`(04 §6). 화면 ID(S1~S9, 04 §4)와 겹치지 않게 개발용은 DV로 쓴다.
- 스텁 안전장치(8번 미결정, 방식만 제안, fail-closed): 스위치 미설정 = 꺼짐(기본 false). 스위치가 켜졌을 때 `APP_ENV`가 **명시적으로 설정**(코드 기본값 `local`이 채운 경우는 미설정으로 봄, 예: pydantic `model_fields_set`)되어 있고 허용 목록(local·test 등) 안일 때만 시작을 허용하며, 미설정·밖·알 수 없는 값이면 backend가 시작을 거부한다(`bi-review` 7-5, 시험은 04 §8). 켜진 설정에서만 스텁 어댑터와 `/dev/*`를 등록하고 꺼져 있으면 경로 자체가 없다(404). 프런트 스텁 UI는 `/dev/stub-users` 응답 여부로 판별하고(config.js 변경 없음), 시험용 사용자 시드 명령도 같은 거부 규칙을 따른다. 8번에서 어댑터를 바꾸면 `/dev/*`만 사라지고 A1 이하 계약은 그대로다. 스위치 `AUTH_STUB_ENABLED`와 판별 방식은 **이 문서 AP-1 = 통합 AP-13으로 승인됨**(`03b` 6-3). 스위치와 시작 거부 판정은 구현됨(EW-1, `backend/app/config.py`, `test_config.py`). 스텁 어댑터와 `/dev/*`는 FU-1a.

### 2-7. 감사 로그 — `audit` · `permission-management` (FU-2a, `03b` 29-1. FU-3: `action` 20개·`target_type` 5개)
| ID | 메서드 경로 | 권한 | 요청 | 성공 응답 | 오류 |
| --- | --- | --- | --- | --- | --- |
| F1 | GET `/audit-logs` | 관리자 | 쿼리(전부 선택, 모두 AND): `from`·`to`(날짜 `YYYY-MM-DD`, 한국 시간 기준 **그날 포함**: `from`은 그날 00:00부터, `to`는 그날 24:00 전까지), `actor_user_id`(정수), `target_type`(`team`·`user`·`dataset`·`dashboard`·`reference`), `target_id`(정수, `target_type`과 함께만), `action`(04 부록 A-3의 20개 값 중 하나), `limit`(기본 50, 최대 200)·`offset` | 200 `{items[{id, occurred_at, actor{id, display_name} 또는 null, actor_source, action, target_type, target_id, details}], total, limit, offset}`. 정렬은 **`occurred_at` 내림차순, 같으면 `id` 내림차순**으로 고정(정렬 인자 없음). `total`은 필터를 적용한 전체 건수(정확한 값). `actor`는 `cli` 행(`actor_source="cli"`)에서 `null`이고 `display_name`은 조회 시점의 `users` 값이다. `occurred_at`은 ISO 8601 `+09:00`. `details`는 04 §5-1 표의 허용 키만 있고 행 값·수식 원문·토큰·비밀은 없다(06 §2-1) | 401·403 `FORBIDDEN`(비관리자·미등록·비활성은 §1 인증 규칙 그대로, 권한 검사가 쿼리 검증보다 먼저), 422 `VALIDATION_ERROR`, 503 `SERVICE_UNAVAILABLE` |
- F1 규칙: ① **읽기 전용**이다. 수정·삭제·내보내기 엔드포인트는 만들지 않는다(후속). ② 쿼리 오류는 422 한 가지다(§1 상태 코드 통일): 날짜 형식 오류 `BAD_FORMAT`(필드 `from`·`to`), `from`이 `to`보다 늦으면 필드 `to`에 `OUT_OF_RANGE`, `target_type`·`action`이 목록 밖이면 `NOT_IN_OPTIONS`, `target_id`만 있고 `target_type`이 없으면 필드 `target_type`에 `REQUIRED`, 정수 아님 `BAD_FORMAT`, `limit`·`offset` 범위 밖은 기존 목록과 같다. 새 오류 코드는 없다. ③ **잘림 표시:** 목록은 `total`이 정확하고 `limit`·`offset`으로 모두 넘겨 볼 수 있으므로 `details.truncated`를 쓰지 않는다. 행의 `details`는 자르지 않고 쓰는 쪽이 4,000바이트 이하로만 만든다(06 §2-1, 넘으면 쓰기 쪽 구현 오류로 변경이 롤백됨). ④ `from`·`to`가 모두 없으면 전체 기간이다(화면은 기본값을 최근 기간으로 채울 수 있으나 서버 기본값은 없다). 새 기록이 계속 쌓이므로 offset 페이지 사이에 행이 밀릴 수 있다(알려진 한계, 후속에서 커서 방식 검토). `offset`에 상한은 두지 않으며 깊은 페이지의 느림은 측정하지 않았다(확인 못 함). ⑤ 쿼리 이름 `from`은 언어 예약어일 수 있어 구현은 별칭(alias)으로 받는다. ⑥ 한 건의 감사 행이 무엇을 뜻하는지(한 호출 = 한 건, 변경 없음 = 0건)는 04 §5-1이 정한다.

### 2-8. 기준값 — `reference` · `reference-values` (FU-3, `03b` 32)
전역 기준값(06 §2-2): 항목마다 연도별 숫자 값 하나, 행의 기준 날짜와 같은 연도 값을 쓰고 이월이 없다(07 §2-2 `REF`). 항목 삭제·이름 변경·설명 수정 엔드포인트는 없다(후속).
| 형태 | 필드 |
| --- | --- |
| ReferenceItem | `{id, name, description(null 가능), value_count, year_min, year_max(값이 없으면 둘 다 null), created_by{id, display_name}, created_at}` |
| ReferenceValue | `{id, item_id, year, value, created_by{id, display_name}, created_at}`. `value`는 `number` 십진 문자열(§1). `created_*`는 처음 입력의 기록이며 정정해도 바뀌지 않는다(정정 이력은 감사 기록 F1) |
| ID | 메서드 경로 | 권한 | 요청 | 성공 응답 | 오류 |
| --- | --- | --- | --- | --- | --- |
| R1 | GET `/reference-items` | 읽기 | `limit`·`offset`(기본 50, 최대 200) | 200 `{items[ReferenceItem], total, limit, offset}` 이름 가나다순. 수식 편집기의 `REF("` 자동완성 겸용(S4가 `limit=200`으로 읽고 `total`이 더 크면 이름 입력으로 보충, 항목은 수십 개를 예상) | 422 `VALIDATION_ERROR`(`limit`·`offset`) |
| R2 | POST `/reference-items` | 관리자 | `{name, description?}` | 201 ReferenceItem(`value_count`=0) | 409 `ALREADY_EXISTS`(`details.field=name`), 422(`name`: `REQUIRED`·`TOO_LONG`·`BAD_FORMAT`, `description`: `TOO_LONG`), 503 `WRITE_BUSY` |
| R3 | GET `/reference-items/{id}/values` | 읽기 | `limit`·`offset`(기본 50, 최대 200) | 200 `{items[ReferenceValue], total, limit, offset}` **연도 내림차순** | 404 `NOT_FOUND`(항목 없음) |
| R4 | POST `/reference-items/{id}/values` | 관리자 | `{year, value}` (`year`는 JSON 정수, `value`는 십진 문자열: JSON 숫자는 `BAD_FORMAT`) | 201 ReferenceValue | 404 `NOT_FOUND`, 409 `ALREADY_EXISTS`(`details.field=year`: 같은 (항목, 연도)가 이미 있음, 문구에 "값을 바꾸려면 정정을 쓰세요"), 422(`year`: `REQUIRED`·`BAD_FORMAT`·`OUT_OF_RANGE`(1900~9999 밖), `value`: `REQUIRED`·`BAD_FORMAT`(숫자 아님·비유한)·`OUT_OF_RANGE`(38자리 초과) **[제안]**), 503 `WRITE_BUSY` |
| R5 | PATCH `/reference-items/{id}/values/{value_id}` | 관리자 | `{value}` (`year`·`item_id`는 받지 않는다: 본문에 있으면 422 필드 코드 `READ_ONLY`) | 200 `{value: ReferenceValue(정정 뒤), previous_value(요청 전 값, 십진 문자열), changed(bool)}`. **숫자로 같은 값이면(`1.0`과 `1.00`도 같음) 아무것도 바꾸지 않고 200, `changed=false`, 감사 0건**(`previous_value`는 현재 값과 같음) | 404 `NOT_FOUND`(항목 없음, 또는 `value_id`가 그 항목 소속이 아님), 422(`value`), 503 `WRITE_BUSY` |
| R6 (선택) | GET `/reference-items/{id}/usage` | 관리자 | - | 200 `{items[{dataset_id, dataset_name, team_id, team_name, status, column_count}], total, truncated}`: 그 항목을 `REF("이름")`으로 쓰는 데이터셋(활성·보관 모두, 이름순, 최대 200개에서 자르고 `truncated`). 정정 확인창의 영향 목록용(정정 전 조회). 쓰는 곳이 없으면 `items=[]` | 404 `NOT_FOUND` |
- 판정 순서(R2·R4·R5, 기존 정의(팀) 엔드포인트와 같은 방식): 인증 → **403**(관리자 아님, 본문 검증보다 먼저) → 요청 본문 형태 오류 422(Pydantic, 서비스 단계보다 앞) → **404**(항목·값 없음) → 규칙 422(값 규칙) → **409**(중복) → 쓰기. R5의 "같은 값" 200은 404·422 뒤, 쓰기 앞이다. 락 대기 초과·교착은 503 `WRITE_BUSY`(06 §5).
- **R6 구현 방안과 근거:** (a) `formulas.ast`(jsonb)를 읽어 `{"t":"call","n":"REF","a":[{"t":"text","v":이름}]}` 노드를 **파이썬으로 걸러내는 방식**을 제안한다(가장 단순). `formulas`·`dataset_columns`·`datasets`·`teams`를 읽는 SQL 한 번(사전 거름: `formulas.expression`에 `REF`가 든 행만, 정확한 일치는 AST로)과 `ast_from_json`의 `walk`로 끝나며 새 표·열·마이그레이션이 없다(수식 수십~수백 개 규모의 읽기, 미측정 **추정**). (b) `formula_deps`에 기준값 항목 간선을 더하는 방식은 새 표가 필요하고(`formula_deps`는 열 번호 쌍) 0009의 승인 범위(표 2개)를 넘으며 JSONB 포함 연산(`@>`)은 임의 깊이의 노드를 찾지 못해 채택하지 않는다. (c) 일반 경고만 두는 방식은 (a)가 실패해도 항상 가능한 **대체 경로**이다: 화면은 R6를 부르되 실패·지연 시 "이 항목을 쓰는 모든 데이터셋의 해당 연도 결과가 바뀝니다"만 보이고 정정은 막지 않는다. **구현 위치는 `formula` 모듈이다**(04 §2-2: formula가 reference를 읽는 방향이라 reference가 formula를 부르면 순환이 생긴다). 경로 접두 `/reference-items`는 같지만 라우터는 formula가 가진다. 목록은 이미 모두에게 열람 가능한 데이터셋 이름뿐이지만 용도가 정정 확인이라 관리자 전용으로 둔다.
- 감사: R2 = `reference.create`, R4 = `reference_value.add`, R5 = `reference_value.update`(변경이 있을 때만 1건). `target_type=reference`, `target_id`는 항목 번호. 키는 04 §5-1. R1·R3·R6은 기록하지 않는다.
- 새 오류 코드는 없다(`ALREADY_EXISTS`·`VALIDATION_ERROR`·`NOT_FOUND`·`FORBIDDEN`·`WRITE_BUSY` 재사용). `WRITE_BUSY`의 뜻을 "기준값 쓰기의 락 대기 초과·교착"까지 넓힌다(§3).

## 3. 오류 코드 사전 (FU-1, FU-2b에서 `DATASET_ARCHIVED`, FU-3에서 `BASE_DATE_IN_USE` 추가)
| 코드 | HTTP | `details` | 뜻 |
| --- | --- | --- | --- |
| `UNAUTHENTICATED` · `USER_NOT_REGISTERED` · `USER_INACTIVE` · `FORBIDDEN` | 401·403 | - | 신원 없음 / 미등록 / 비활성 / 권한 부족 |
| `METHOD_NOT_ALLOWED` | 405 | - | 허용되지 않는 메서드(03b 17-1 결정 1) |
| `SERVICE_UNAVAILABLE` | 503 | - | DB 등 내부 의존 장애(재시도 가능, 로그아웃과 구분, 접근은 닫힘, 03b 17-1 결정 2). Superset 불가는 `SUPERSET_UNAVAILABLE` |
| `TARGET_INACTIVE` | 409 | `field` = `team` 또는 `user`(둘 다 비활성이면 `team`) | 비활성 팀·사용자에 소속 추가·변경 시도(A8, 03b 17-1 결정 3. 코드 이름은 구현 제안, 값은 구현 기준으로 확정) |
| `NOT_FOUND` · `ROW_NOT_FOUND` | 404 | - | 대상 없음 / 행 없음(C3) |
| `VALIDATION_ERROR` | 422 | `fields[]` | 필수·범위·형 등 입력 규칙 위반 |
| `ALREADY_EXISTS` | 409 | `field` | 유일 값 중복(팀 코드·이름, 로그인 ID, 데이터셋·열 이름, uuid) |
| `DEFINITION_VERSION_MISMATCH` | 409 | `current_version` | 다른 사람이 먼저 정의를 바꿈. 화면은 다시 읽기를 안내 |
| `CELL_CONFLICT` · `PASTE_CONFLICT` · `PERIOD_CONFLICT` | 409 | `conflicts[]` | 칸 값이 바뀜 / 붙여넣기 충돌(전부 취소) / 이미 있는 기간 |
| `DATASET_HAS_ROWS` · `COLUMN_LOCKED` · `LAST_ADMIN` | 422·422·409 | - | 행이 있어 변경 불가 / 열 type·kind 변경 불가 / 마지막 관리자 |
| `BASE_DATE_IN_USE` | 422 | `column{column_id, display_name}` | **(FU-3, C-6)** `REF`를 쓰는 계산 열이 있어 기준 날짜 열을 해제할 수 없음(B4). 문구 "REF를 쓰는 수식이 있어 기준 날짜 열을 해제할 수 없습니다. 먼저 그 수식을 고치거나 다른 날짜 열로 바꾸세요" |
| `WRITE_BUSY` | 503 | `retry_after` | 행 쓰기·기준값 쓰기(R2·R4·R5, FU-3)의 락 대기 초과·교착(`55P03`·`40P01`). 재시도 가능, 정의 변경용 `DEFINITION_BUSY`와 구분 |
| `FORMULA_INVALID` · `FORMULA_CIRCULAR` · `FORMULA_RUNTIME_ERROR` | 422 | `errors[]` / `path[]` / - | C0 검사 실패 / 순환 참조 / 계산 불가(DB 오류는 정규화, 07 §5) |
| `DEFINITION_BUSY` | 503 | `retry_after` | 정의 변경 락 대기 초과, 화면이 "다시 시도" 안내(07 §8). 보관·복구(B7·B8)의 락 대기 초과도 같은 코드 |
| `DATASET_ARCHIVED` | 409 | `status`(`"archived"`) | 보관된 데이터셋에 정의·입력 쓰기(B4 B5 B6 C2 C3 C4 D4 D5)를 시도. 문구 "보관된 데이터셋은 고칠 수 없습니다. 복구한 뒤 다시 시도하세요"(`message`는 한국어 사용자 문구). 새 환경변수·필드 없음. 판정은 잠근 행을 읽은 뒤 버전 비교보다 앞(FU-2b, §2-2) |
| `PAYLOAD_TOO_LARGE` | 413 | `limit`(단위는 값으로 구분: 5000=행 수, 1048576=바이트) | 붙여넣기 5,000행 또는 요청 상한(기본값 A 1MiB) 초과 |
| `PREVIEW_BUSY` · `GUEST_TOKEN_RATE_LIMITED` | 429 | `retry_after` | 미리보기 사용자당 동시 1건·전역 상한 / 입장권 사용자별 제한(한도 값 **[미답]**, 08 §4) |
| `SUPERSET_REJECTED` · `SUPERSET_UNAVAILABLE` | 502·503 | - | Superset이 거부 / 연결 불가 |
| `INTERNAL_ERROR` | 500 | - | 예기치 않은 오류 |
- 계산 열 칸의 오류 코드 `E1`(0으로 나눔) `E2`(글자 길이 범위) `E3`(날짜 범위) `E4`(기준값 없음, FU-3: `REF`가 그 행의 기준 날짜 연도 값을 못 찾음)는 API 오류가 아니라 Row `errors` 값이며 문구는 D1 `cell_errors`가 준다(07 §2-2).
- 수식 검사(C0) 오류 코드(`errors[].code`, D2 응답과 `FORMULA_INVALID`의 `details.errors`)는 API 오류 코드가 아니며 사전은 `backend/app/formula/errors.py`(07 §9 `message_ko`)다. **FU-3이 더한 것:** `REF_UNKNOWN`(없는 기준값 이름), `BASE_DATE_REQUIRED`(기준 날짜 열이 없는 데이터셋에서 `REF` 사용). 글자 상수가 아닌 인수·인수 개수 오류는 기존 `CONST_REQUIRED`·`ARG_COUNT`를 쓴다(07 §3-2). 이 셀 코드는 §2-5의 엔드포인트 ID `E1`~`E6`(Superset·대시보드)과 이름만 같고 별개다.
- `VALIDATION_ERROR`의 필드 코드(`details.fields[].code`): `REQUIRED` `OUT_OF_RANGE` `BAD_FORMAT` `NOT_IN_OPTIONS` `NOT_PERIOD_START` `READ_ONLY` `TOO_LONG` `RESERVED`. API 오류 코드가 아니며 HTTP 422 한 가지로 돌려준다.

## 4. 권한 매트릭스와의 일치 (06 §4-1)
| 06 동작 | 엔드포인트 | 권한 열 |
| --- | --- | --- |
| 팀 만들기·소속·역할·비활성화 | A3 A4 A5 A6 A7 A8 A9 | 관리자 |
| 내 정보·팀 목록 | A1 A2 | 읽기 |
| 데이터셋 만들기·열 정의·수식 편집·미리보기 | B2 B4 B5 B6 D2 D3 D4 D5 | 정의(팀) |
| 데이터셋 보관·복구(FU-2b) | B7 B8 | 정의(팀)(관리자 예외 없음, 비활성 팀도 허용) |
| 행 입력·칸 수정·붙여넣기 | C2 C3 C4 | 입력(팀) |
| 데이터셋·행·열 정의·수식 보기 열람 | B1 B3 C1 D1 D6 D7 D8 | 읽기 |
| 대시보드 목록·보기(입장권) | E3 E6 | 읽기 |
| 대시보드 연결 등록·해제, 동기 현황·다시 시도 | E4 E5 E2 D9 D10 (E1 상태 값은 읽기, 사유는 관리자) | 관리자 |
| 감사 기록 조회(FU-2a) | F1 | 관리자 |
| 기준값 항목·연도 값 보기(FU-3) | R1 R3 | 읽기 |
| 기준값 항목 추가·연도 값 추가·정정, 정정 영향 조회(FU-3) | R2 R4 R5 R6 | 관리자 |
- 권한 매트릭스 시험은 이 표의 엔드포인트 × 역할(관리자, 정의 담당자, 입력자, 다른 팀 구성원, 비소속 읽기, 비활성)로 자동화한다(03b 3-6 BY4). 계약 밖 쓰기 경로는 없다.

## 5. 프런트 설정과 훅
- `config.js`/`config.ts`는 **FU-1에서 변경하지 않는다**(새 변수 없음). Superset 새 창 링크는 기존 `supersetRoot`를 쓴다. `APP_UPLOAD_MAX_MB`는 가져오기 단위로 이월(03b 5-4). 훅은 위 ID 단위로 만들고 오류는 `error.code`로 분기한다.

## 6. 승인 상태 (`03b` 6-3. 통합 번호는 04 §9-1: 이 문서의 AP-1 = 통합 AP-13, AP-2 = 통합 AP-14)
| 번호 | 항목 | 시점 |
| --- | --- | --- |
| AP-1 | **승인**: 새 환경변수 `AUTH_STUB_ENABLED`(스텁 켜기, 기본 꺼짐)와 fail-closed 판별(`APP_ENV` 명시 설정 + 허용 목록 local·test, 04 §8). 8번 확정 시 어댑터 변수는 따로 승인 | 승인됨, 스위치·시작 거부 구현됨(EW-1) |
| AP-2 | **승인**(통합 AP-14): 04 부록 A 갱신 — `PERIOD_CONFLICT` 추가, 이 문서의 오류 코드 사전 채택 | 승인됨 |
| FU-3 | R1~R6(R6 선택)·`BASE_DATE_IN_USE`·C0 코드 2개·`E4`·감사 20개는 `03b` 32절에서 승인된 범위다(C-5, C-2, C-6). 32절 안의 세부 [제안](R5 응답의 `previous_value`·`changed`, R6의 구현 위치와 방안, 연도·값 필드 코드, 설명 200자)은 확인 요청 없이 구현하되 사용자가 바꾸면 이 문서를 먼저 고친다 | 구현 착수 가능 |
| - | 새 런타임 의존성·기준선과 다른 설정·모델 변경: 이 문서 없음. `/health` 필드 추가는 03b 3-6에서 승인됨 | - |
- 승인된 **[제안]**(`03b` 6-2): 숫자 십진 문자열(일반 JSON 숫자와 다름), 이름 길이 상한·금지 문자, 붙여넣기 요청 상한 A/B, `WRITE_BUSY`, 클라이언트 임시 행, `/health` 새 필드의 메모리 값, `E3`가 `embedded_uuid`를 모두에게 노출, `E1` 상태 값을 읽기로 공개, 스텁 쿠키 방식, `LAST_ADMIN` 보호, 검사(D2)를 200으로 응답.

## 7. 후속 기능 단위에서 결정
- 데이터셋 보관·복구는 FU-2b의 B7·B8로 구현한다(`03b` 30-1). 후속: 행 보관·복구·영구 삭제, 열·수식 보관·삭제 API, 데이터셋 영구 삭제(`deleted`)와 영향 차트 수 안내(08 §2-1), 30일 규칙 응답(409).
- 기준값 표는 FU-3의 R1~R6으로 구현한다(`03b` 32). 후속: 기준값 항목 삭제·이름 변경·설명 수정(PATCH) 엔드포인트, 정정 이력 조회 화면(F1로 `target_type=reference` 필터는 이미 가능), 값 정정의 낙관적 동시성(`expected` 가드: 지금은 마지막 쓰기가 이기며 감사 기록의 이전·이후 값이 남는다), 연도 값 일괄 입력.
- 이전 행 참조·같은 데이터셋 집계의 수식 응답, 참조 열 검증·끊어진 참조 점검, 공통 요약 API.
- 엑셀 가져오기(업로드 413·`APP_UPLOAD_MAX_MB`·미리보기·확정·동시 1건 429·입력 차단 응답), 원본 파일 정보.
- 변경 기록 조회는 FU-2a의 F1로 구현한다. 후속: 감사 내보내기·커서 방식·보존 정책, 행 값 수정·입장권 발급 기록(제외 결정), `actor_source` 필터. 소급 변경·마감, 역할별 열 편집 권한·데이터셋별 예외 권한, 같은 기간 여러 행 허용 설정, 데이터셋의 팀 변경.
- 8번 인증 방식 확정 뒤 `/dev/*` 제거, 401 처리(로그인 이동), Explore 자동 로그인, 입장권 `user` 식별자 교체.
- 행 부분 로딩 방식(AG Grid Community 확인 뒤), 입장권 속도 제한 한도 값, 버전 접두어 도입.
