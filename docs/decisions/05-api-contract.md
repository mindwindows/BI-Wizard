# 05. REST API 계약 (FU-1 범위)

**상태: 승인(2026-10-11, 03b 6절)** — architect. 이름·역할·enum은 04 부록 A, 필드·권한은 06, 수식 응답은 07, 입장권·동기는 08을 그대로 쓴다.
- 의존 결정: 브리프 5절 3·6·8(스텁 전제)·9·10번, `03b` 1-3·1-6·2-4·3-3·3-4·4-2·5-2(K2·K3·K7·Z6), 실험 `03c` X-24·X-28. 결정 원문은 반복하지 않고 `03b n-n`으로만 건다. 구현 상세(클래스·SQL)는 담지 않는다.
- [제안]·[미답] 표지는 `03b` 6-2에 따라 모두 승인된 것으로 읽는다(남은 [AP]는 `03b` 6-3 기준).
- 표지: **[제안]** 이 문서가 처음 내는 안 / **[미답]** 사용자 답 없음(기본값 사용) / **해소(03c A-27)** 표시 이름 갱신은 서버 내부 흐름이라 이 계약의 필드는 변하지 않는다(08 §2-3) / **[AP]** §6 승인 필요. 공통 규칙(경로·오류 형식·상태 코드·목록·값 형식·충돌 응답)은 사용자 답이 없어 기본값으로 쓰며 **[미답]**이다.

## 1. 공통 규칙
| 항목 | 규칙 | 출처 |
| --- | --- | --- |
| 경로 | 모든 경로는 `${APP_BASE_PATH}/api/…`이고 아래 표는 `/api` 뒤만 쓴다. 버전 접두어 없음. 프록시가 접두를 떼든 말든 같은 경로(STRIP true/false 모두). 프런트는 `config.ts`의 `apiUrl()` 한 곳에서 조립하고 경로를 하드코딩하지 않는다 | [미답], 04 §5 |
| 경계 | 브라우저는 FastAPI만 호출한다. DB·Superset REST 직접 호출 없음(Superset은 Embedded iframe·새 창 링크만). 요청 본문의 `rls`·Superset 숫자 id는 받지 않는다 | 04 §5, 08 §4 |
| 형식 | JSON UTF-8, 필드 snake_case, id는 정수. 날짜 `YYYY-MM-DD`(월·연 단위도 기간 첫날, 예 `2026-03-01`), 시각 ISO 8601 `+09:00`. 첫날이 아닌 날짜는 거부(`NOT_PERIOD_START`). **`number` 값은 십진 문자열 `"1234.50"`, 미입력은 `null`** [제안: `numeric` 38자리가 JS 숫자 정밀도를 넘을 수 있어 일반 JSON 숫자 기본값과 다름, 승인 03b 6-2]. 글자는 NFC로 정규화해 저장 | 03b 2-2 W3-2, 07 §3 |
| 이름 규칙 | 표시 이름 길이 상한 [제안]: 팀 50·데이터셋 100·열 100자(Superset 열 표시 이름은 1,024자를 넘으면 원인 없는 422이므로 앱이 먼저 막는다, 03c A-27). 열 이름에 `[` `]` `"`·제어문자 금지, `team`·`팀`·`row_id`·`행 번호` 예약어(07 §1, 06 §3-3). 위반은 `VALIDATION_ERROR`(필드 코드 `TOO_LONG`·`BAD_FORMAT`·`RESERVED`) | 06 §2, 07 §1 |
| 인증 | `/health` 외 모두 `current_user` 한 곳을 거친다. 신원 없음 401 `UNAUTHENTICATED`, 신원은 있으나 `users`에 없음 403 `USER_NOT_REGISTERED`, 비활성 403 `USER_INACTIVE`. 신원 출처(헤더/토큰/로그인)는 8번 미결정이라 계약에 없다 | 03b 1-1, 5-2 K3 |
| 권한 표기 | `공개` 인증 불필요 / `읽기` 인증된 활성 사용자 전부(타 팀 포함) / `관리자` `users.is_admin` / `정의(팀)` 그 데이터셋 팀의 `definer`(관리자라도 팀 소속이 아니면 불가 [제안, 06 §4-1]) / `입력(팀)` 그 팀의 `entry` 또는 `definer` **[미답: 정의 담당자 입력 가부, 06 §4-1]** / `스텁` 스텁이 켜진 환경에서만 존재 | 03b 1-3, 5-2 K2, 06 §4 |
| 오류 | `{"error": {"code", "message", "details", "request_id"}}`. `message`는 한국어 사용자 문구(SQL·내부 용어 금지). 입력 검증 오류도 같은 형식: `code=VALIDATION_ERROR`, `details.fields[{field 또는 row_index+column_id, code, message}]`. 응답 헤더 `X-Request-ID` | [미답], 07 §9 |
| 상태 코드 | 400 형식 오류 / 401 / 403 / 404 / 409 충돌 / 413 크기 / 422 규칙 위반 / 429 제한(`Retry-After`, 코드로 구분) / 502·503 Superset 불가 / 500 `INTERNAL_ERROR`(상세는 로그에만). 행 쓰기의 락 대기 초과·교착(`55P03`·`40P01`)은 503 `WRITE_BUSY`(재시도 가능, §3) | [미답] |
| 목록 | 쿼리 `limit`(기본 50, 최대 200)·`offset`, 응답 `{items, total, limit, offset}`. 그리드의 부분 로딩은 AG Grid Community 지원 확인 뒤 적용(Enterprise 방식 금지) | [미답] |
| 동시성 | 정의를 바꾸거나 행을 쓰는 요청은 `expected_version`(읽은 `def_version`)을 싣는다. 기존 행의 칸 수정은 칸마다 `expected` 키가 **필수**다(값 `null` = 빈 칸이었음, 키 생략·`expected` 전체 `null`은 422로 가드 우회를 막는다). 이미 같은 값이면 200. 모든 쓰기 성공 응답에 새 `def_version` | 03b 3-4 Y8, 06 §5, 03c X-24 |
| 충돌 | HTTP 409 + 코드: `CELL_CONFLICT`·`PASTE_CONFLICT`·`DEFINITION_VERSION_MISMATCH`(04 후보) + `PERIOD_CONFLICT` **[제안, 04 A-3에 반영됨]**. `details`는 §3 표 | [미답] |
| 계약 변경 | 필드·엔드포인트 추가는 허용. 이름·타입·의미·코드·권한의 변경·삭제는 **계약 변경**: 변경 전후 비교표를 만들어 사용자 승인 → 이 문서, backend 스키마, 프런트 훅, 시험을 한 번에 고치고 reviewer가 대조 | `modularize` |

### 공통 형태
| 이름 | 필드 |
| --- | --- |
| Column | `{id, display_name, type, kind, required, rules, tag, position}`. `rules`: number `{min, max, decimals}` / text `{max_length}` / date `{min, max}` / choice `{options[]}` (06 §3-2). 계산 열(`kind=formula`)의 `type`은 결과 형 |
| Dataset | `{id, team_id, name, date_unit, base_date_column_id, status, def_version, created_by{id, display_name}, created_at}`. 상세는 `team{id, code, name}`, `columns[Column]`, `permissions{define, enter}` 추가 |
| Row | `{row_id, cells{"<column_id>": 값 또는 null}, errors{"<column_id>": "E1"}}`. 계산 열 칸은 값 `null` + `errors`로 오류 칸과 미입력을 구별한다(`errors`에 있으면 오류 칸). 오류 판정 구조(07 §3-1 E-A 제안, 대안 판정 SELECT)와 무관하게 응답 모양은 같다 |

## 2. 엔드포인트
ID는 04 §6 소단위 기준(A=1a 권한, B=1b 정의, C=1c 입력, D=1d 수식·점검, E=1e Superset). 모듈·Skill은 04 §2·§6. "오류"는 §1 공통(401·403·404·500)을 뺀 주요 코드다.
### 2-1. 권한 관리 — `access` · `permission-management`
| ID | 메서드 경로 | 권한 | 요청 | 성공 응답 | 오류 |
| --- | --- | --- | --- | --- | --- |
| A1 | GET `/me` | 읽기 | - | 200 `{id, display_name, is_active, is_admin, memberships[{team_id, team_code, team_name, role}]}` | 403 미등록·비활성 |
| A2 | GET `/teams` | 읽기 | 목록 | 200 `{id, code, name, is_active}` 목록 | - |
| A3 | POST `/teams` | 관리자 | `{code, name}` (`code` 불변, 형식 `^[a-z0-9_]{1,32}$` [제안: 뷰에 글자로 들어가므로 제한]) | 201 team | 409 `ALREADY_EXISTS`, 422 |
| A4 | PATCH `/teams/{team_id}` | 관리자 | `{name?, is_active?}` (이름이 바뀌면 커밋 뒤 팀 단위 동기화 요청으로 그 팀의 가상 데이터셋 이름도 갱신, 08 §2-1) | 200 team | 409, 422 |
| A5 | GET `/users` | 관리자 | `q, team_id, is_active` + 목록 | 200 `{id, login_id, display_name, is_admin, is_active, memberships[{team_id, role}]}` 목록 (S6 팀×사용자 격자는 이 응답으로 그림) | - |
| A6 | POST `/users` | 관리자 | `{login_id, display_name, is_admin?}` (사전 등록) | 201 user | 409 `ALREADY_EXISTS` |
| A7 | PATCH `/users/{user_id}` | 관리자 | `{display_name?, is_admin?, is_active?}` | 200 user | 409 `LAST_ADMIN`(마지막 활성 관리자 해제·비활성) [제안] |
| A8 | PUT `/teams/{team_id}/members/{user_id}` | 관리자 | `{role: "definer"\|"entry"}` (없으면 추가, 있으면 역할 변경) | 200 `{team_id, user_id, role}` | 404 |
| A9 | DELETE `/teams/{team_id}/members/{user_id}` | 관리자 | - | 204 | 404 |

### 2-2. 데이터셋·열 정의 — `dataset` · `dataset-definition`
| ID | 메서드 경로 | 권한 | 요청 | 성공 응답 | 오류 |
| --- | --- | --- | --- | --- | --- |
| B1 | GET `/datasets` | 읽기 | `team_id?` + 목록 | 200 Dataset 목록. 정렬: 내 소속 팀 먼저, 다음 팀 이름·데이터셋 이름(03b 2-4). 동기 상태는 E1에서 받아 화면이 결합(04 §3: dataset은 superset을 읽지 않음) | - |
| B2 | POST `/datasets` | 정의(`team_id` 팀) | `{team_id, name, date_unit: "day"\|"month"\|"year"}` | 201 Dataset 상세. 등록 + `ds_`·`dv_` 생성이 한 트랜잭션(06 §3-5), 커밋 뒤 Superset 백그라운드 동기화 요청(등록 행이 없으면 E1이 `pending`으로 표시) | 409 `ALREADY_EXISTS`(팀 안 이름), 422, 503 `DEFINITION_BUSY` |
| B3 | GET `/datasets/{id}` | 읽기 | - | 200 Dataset 상세 | 404 |
| B4 | PATCH `/datasets/{id}` | 정의(팀) | `{expected_version, name?, date_unit?, base_date_column_id?}` | 200 Dataset 상세 | 409 `DEFINITION_VERSION_MISMATCH`(`details.current_version`), 422 `DATASET_HAS_ROWS`(날짜 단위·기준 날짜 열은 행 0개일 때만, 06 §3-3), 422(기준 열은 `raw` `date` 열만), 409 `ALREADY_EXISTS`(팀 안 이름), 503 `DEFINITION_BUSY` |
| B5 | POST `/datasets/{id}/columns` | 정의(팀) | `{expected_version, display_name, type, required?, rules?, tag?, position?}` (원본 열만. 계산 열은 D4) | 201 `{column, def_version}` | 409 `DEFINITION_VERSION_MISMATCH`·`ALREADY_EXISTS`(열 이름), 422 `VALIDATION_ERROR`(예약어·금지 문자·길이), 503 `DEFINITION_BUSY` |
| B6 | PATCH `/datasets/{id}/columns/{col_id}` | 정의(팀) | `{expected_version, display_name?, required?, rules?, tag?, position?}`. `type`·`kind` 변경 불가 | 200 `{column, def_version}`. 태그 변경은 순환 재검사(07 §7) | 409 `DEFINITION_VERSION_MISMATCH`·`ALREADY_EXISTS`(열 이름), 422 `COLUMN_LOCKED`(type·kind), 422 `FORMULA_CIRCULAR`, 503 `DEFINITION_BUSY` |

### 2-3. 입력 그리드 — `entry` · `data-entry`
| ID | 메서드 경로 | 권한 | 요청 | 성공 응답 | 오류 |
| --- | --- | --- | --- | --- | --- |
| C1 | GET `/datasets/{id}/rows` | 읽기 | `order=asc\|desc`(기준 날짜 열, 없으면 `row_id`) + 목록 | 200 `{def_version, items[Row], total, limit, offset}`. 계산 열 값·`errors`는 formula가 `RowViewPort`로 제공(04 §3) | 404, 429 `PREVIEW_BUSY`(전역 동시 상한, 07 §5) |
| C2 | POST `/datasets/{id}/rows` | 입력(팀) | `{expected_version, cells{"<column_id>": 값}}` (원본 열만, 필수 열 전부 필요. 기준 날짜 열은 DB NOT NULL이므로 `required=true`로 취급해 `REQUIRED`로 판정) | 201 `{row, def_version}` | 409 `PERIOD_CONFLICT`·`DEFINITION_VERSION_MISMATCH`, 422 `VALIDATION_ERROR`(필드 코드 `REQUIRED`·`OUT_OF_RANGE`·`BAD_FORMAT`·`NOT_IN_OPTIONS`·`NOT_PERIOD_START`·`READ_ONLY`·`TOO_LONG`), 503 `WRITE_BUSY` |
| C3 | PATCH `/datasets/{id}/rows/{row_id}` | 입력(팀) | `{expected_version, changes[{column_id, expected, value}]}` (`expected` 키 필수, §1 동시성. 한 요청의 칸 전부가 가드, 하나라도 충돌하면 전체 취소) | 200 `{row, def_version}` | 404 `ROW_NOT_FOUND`, 409 `CELL_CONFLICT`(`details.conflicts[{row_id, column_id, current}]`), `PERIOD_CONFLICT`(이미 있는 기간으로 이동), `DEFINITION_VERSION_MISMATCH`, 422, 503 `WRITE_BUSY` |
| C4 | POST `/datasets/{id}/rows/paste` | 입력(팀) | `{expected_version, column_ids[], rows[{row_id, expected[], values[]}]}` (규칙은 아래 목록) | 200 `{updated, created, created_rows[{index, row_id}], def_version}` | 409 `PASTE_CONFLICT`(전부 취소, `details.conflicts[{row_index, row_id, column_id, kind: "cell"\|"period"\|"row_missing", current}]`), 409 `DEFINITION_VERSION_MISMATCH`, 413 `PAYLOAD_TOO_LARGE`, 422 `VALIDATION_ERROR`, 503 `WRITE_BUSY` |
- C4 규칙: 값은 문자열\|null(파서는 화면 몫, 07 §9)이고 서버가 열 타입으로 해석·재검증한다. `row_id=null`은 새 행(`expected` 없음), 정수는 기존 행이며 이때 `expected[]`가 **필수**(칸마다 화면이 가진 이전 값, 빈 칸 `null`)다. 처리 순서는 기존 행 `row_id` 오름차순 갱신 → 새 행 기간 오름차순(기준 날짜 열이 없으면 입력 순) 삽입으로 고정해 교착을 막고, 충돌은 첫 건에서 멈추지 않고 모아 한 번에 돌려준다(06 §5). **기존 행의 기준 날짜 열 값은 C4로 바꿀 수 없다**(`VALIDATION_ERROR` 필드 코드 `READ_ONLY`; 기간 이동은 C3 단건만, 유일 인덱스 위반으로 트랜잭션이 중단되어 충돌 목록에 못 모이기 때문). 그래서 `conflicts.kind="period"`는 새 행 삽입의 기간 충돌만 뜻한다.
- C4 요청 상한 **A 승인(`03b` 6-2)**: 5,000행·요청 1MiB 이하(현재 nginx 기본 `client_max_body_size` 1m 안)이며 B안(상한을 늘리고 `frontend/nginx/templates/default.conf.template`의 `client_max_body_size`를 "요청 상한 + 1MiB"로 변경)은 채택하지 않았다. 1MiB는 nginx 기본 1m과 같아 요청이 백엔드 `PAYLOAD_TOO_LARGE`(JSON)에 닿기 전에 nginx 413(JSON 아님)을 받을 수 있으므로 프런트는 JSON이 아닌 413도 같은 안내로 처리한다.
- **임시 행(draft) [제안]**: 필수 열 때문에 한 칸씩 입력하는 새 행은 서버에 저장하지 않는다. 화면이 클라이언트 메모리에서 필수 칸을 모두 채우면 C2를 한 번 부른다(붙여넣기 새 행은 C4 한 번). 서버에 `draft` 상태·표 열이 없다. 비용: 새로고침하면 미저장 행이 사라지고 다른 사용자에게 보이지 않으며, 같은 기간 충돌은 저장 때 알려진다. 대안(서버 draft 열)은 `ds_`·뷰·요약에 제외 조건이 들어가 후속 비용이 커서 비추천.
- 삭제·보관 엔드포인트는 FU-1에 없다.

### 2-4. 수식·점검 — `formula` · `formula-column`
| ID | 메서드 경로 | 권한 | 요청 | 성공 응답 | 오류 |
| --- | --- | --- | --- | --- | --- |
| D1 | GET `/formulas/functions` | 읽기 | - | 200 `{functions[{name, signature, returns, help_ko, excel_diff}], cell_errors{"E1": 문구, …}}` (자동완성·도움말, 함수 사전에서 생성. 열 이름·태그는 B3의 `columns`로 클라이언트가 완성) | - |
| D2 | POST `/datasets/{id}/formulas/check` | 정의(팀) | `{expression, column_id?}` (`column_id`=편집 중 계산 열, 자기 참조·순환 기준) | 200 `{ok, result_type, refs[{column_id, display_name}], errors[{code, message, start, end}]}`. C0 검사 실패도 200(`ok=false`, 쉬운 말 문구·위치) | 404 |
| D3 | POST `/datasets/{id}/formulas/preview` | 정의(팀) | `{expression, column_id?}` (저장 없음, 읽기 전용 트랜잭션) | 200 `{result_type, rows[{row_id, period, value, error}], total_rows, error_count, empty_count, def_version}`. `rows`는 기준 날짜(없으면 `row_id`) 최근 순 20행(07 §5) | 422 `FORMULA_INVALID`(`details.errors`는 D2와 같음), 422 `FORMULA_RUNTIME_ERROR`(시간 초과 포함), 429 `PREVIEW_BUSY`(사용자당 동시 1건, 전역 동시 상한 초과도 같은 코드, 07 §5) |
| D4 | POST `/datasets/{id}/formulas` | 정의(팀) | `{expected_version, display_name, expression, tag?, position?}` (계산 열 만들기) | 201 `{column, def_version}`. dataset 정의 변경 진입점 안의 한 트랜잭션: 열 INSERT → formula 훅(수식·의존·뷰) → `def_hash` 기록(04 §5, 07 §8) | 409 `DEFINITION_VERSION_MISMATCH`·`ALREADY_EXISTS`, 422 `FORMULA_INVALID`·`FORMULA_CIRCULAR`(`details.path` 열 이름 경로), 503 `DEFINITION_BUSY` |
| D5 | PUT `/datasets/{id}/formulas/{col_id}` | 정의(팀) | `{expected_version, expression}` | 200 `{column, def_version, result_type_changed}`. 결과 형이 바뀌면 계산 열의 `type`(결과 형)을 같은 진입점이 갱신하고 `true`(저장된 차트 영향 안내용, 영향 차트 수는 후속) | D4와 같음, 404 |
| D6 | GET `/datasets/{id}/formulas/{col_id}` | 읽기 | - | 200 `{column_id, text, refs[{column_id, display_name, kind}], tag_columns[display_name], error_count}`. `text`는 현재 열 이름으로 풀어 쓴 형태(07 §9). 원문 `expression`은 응답에 없고 편집기 시작값은 `text` [제안] | 404 |
| D7 | GET `/checks/formula-errors` | 읽기 | 목록 | 200 `{dataset_id, dataset_name, team_name, column_id, column_name, error_count}` 목록(오류 칸이 있는 열만, S5) [제안: 읽기, 06 §4-1 열람과 같은 취급] | 429 `PREVIEW_BUSY`(전역 동시 상한) |
| D8 | GET `/datasets/{id}/formula-errors` | 읽기 | `column_id?` + 목록 | 200 `{row_id, period, column_id, error, message}` 목록 | 404, 429 `PREVIEW_BUSY` |
| D9 | GET `/checks/views` | 관리자 | - | 200 `{views, views_failed_count, failed[{dataset_id, dataset_name, reason, since}]}`. `reason`은 사유 코드·요약뿐(SQL·비밀 금지). `/health` 필드와 같은 집계(S9) | - |
| D10 | POST `/checks/views/retry` | 관리자 | `{dataset_ids?}` (생략 = 실패 전부) | 200 `{rebuilt, views_failed_count}`. 요청 안에서 끝까지 처리, 데이터셋별 짧은 트랜잭션과 정의 변경과 같은 `datasets` 행 잠금(07 §8) | 503 `DEFINITION_BUSY` |

### 2-5. Superset·대시보드 — `superset` · `dashboard-link`
| ID | 메서드 경로 | 권한 | 요청 | 성공 응답 | 오류 |
| --- | --- | --- | --- | --- | --- |
| E1 | GET `/superset/datasets` | 읽기 | 목록 | 200 `{dataset_id, superset_name, sync_status, synced_at, last_error}` 목록. 등록 행이 없는 데이터셋은 `pending`(04 A-3). `last_error`는 관리자에게만, 다른 사용자는 `null` [제안: 06 §4-1은 동기 현황을 관리자로 두었으나 04 S2 목록이 상태 열을 가짐] | - |
| E2 | POST `/superset/sync` | 관리자 | `{dataset_ids?}` (생략 = `pending`·`failed` 전부) | 202 `{accepted[dataset_id]}`. 결과는 E1로 확인. Superset 불가가 다른 API를 막지 않는다(08 §2-1) | 404 |
| E3 | GET `/dashboards` | 읽기 | `include_inactive?`(관리자만) + 목록 | 200 `{id, name, embedded_uuid, is_active}` 목록. 임베드 SDK가 uuid를 쓰므로 응답에 포함 [제안, 승인]. 08 §4 "클라이언트가 보낸 id는 받지 않는다"와 충돌하지 않는다: uuid는 읽기로만 공개되고 입장권 요청(E6)은 포털 `id`만 받는다 | - |
| E4 | POST `/dashboards` | 관리자 | `{name, embedded_uuid}` (관리자가 Superset에서 임베드를 켜고 받은 번호를 수동 입력) | 201 dashboard | 409 `ALREADY_EXISTS`, 422(uuid 형식) |
| E5 | PATCH `/dashboards/{id}` | 관리자 | `{name?, is_active?}` (uuid 불변. 해제는 `is_active=false`, Superset 임베드는 관리자가 따로 끈다) | 200 dashboard | 404 |
| E6 | POST `/dashboards/{id}/guest-token` | 읽기 | 본문 없음(있으면 422). 포털 대시보드 `id`만 받고 서버가 등록 표의 uuid를 찾는다. `rls`는 서버 고정 빈 목록, `user`는 서버가 항상 채운다(08 §4). 활성 여부는 backend가 확인하고(해제 = 발급 중단), Superset 검증 훅은 포털 표가 아니라 Superset 쪽 임베드 설정으로 확인하므로 오타 uuid는 Superset이 거부해 502가 된다 | 200 `{token, expires_in}` (5분, `Cache-Control: no-store`, 로그 금지). SDK가 만료 전 다시 부른다 | 404(없음·비활성), 429 `GUEST_TOKEN_RATE_LIMITED`(`Retry-After`, 사용자별), 502 `SUPERSET_REJECTED`, 503 `SUPERSET_UNAVAILABLE` |

### 2-6. 상태 확인 · 개발·시험 전용
| ID | 메서드 경로 | 권한 | 요청 | 성공 응답 | 오류 |
| --- | --- | --- | --- | --- | --- |
| H1 | GET `/health` | 공개 | - | 200 `{status, app, views, views_failed_count, public_create, db_timezone}`. 기존 `status`·`app` 유지, `views` = 시작 대조가 확인한 활성 데이터셋의 뷰 수, `views_failed_count` = 그중 실패 수 [제안], 새 필드는 시작 자가 점검·뷰 대조가 채운 **메모리 값**이라 DB를 건드리지 않는다 [제안: 지금 `/health`는 DB 비접속]. 뷰 실패가 있어도 상태 코드 200(Docker healthcheck 유지, 03b 3-6). 공개 응답이므로 개수·불리언·시간대만 | - |
| H2 | GET `/health/db` | 공개 | - | 기존 그대로: 200 `{status, database}` / 503 | - |
| DV1 | GET `/dev/stub-users` | 스텁 | - | 200 `{items[{login_id, display_name, is_admin}], current}` (화면 S1의 스텁 신원 전환기용) | - |
| DV2 | PUT `/dev/stub-user` | 스텁 | `{login_id}` | 204 + 스텁 신원 쿠키 설정(이름 `bi_stub_login`, HttpOnly) [제안] | 404 미등록 |
| DV3 | DELETE `/dev/stub-user` | 스텁 | - | 204, 쿠키 삭제 | - |
- Skill: H1·H2는 `local-environment`, DV1~DV3는 `permission-management`(04 §6). 화면 ID(S1~S9, 04 §4)와 겹치지 않게 개발용은 DV로 쓴다.
- 스텁 안전장치(8번 미결정, 방식만 제안, fail-closed): 스위치 미설정 = 꺼짐(기본 false). 스위치가 켜졌을 때 `APP_ENV`가 **명시적으로 설정**(코드 기본값 `local`이 채운 경우는 미설정으로 봄, 예: pydantic `model_fields_set`)되어 있고 허용 목록(local·test 등) 안일 때만 시작을 허용하며, 미설정·밖·알 수 없는 값이면 backend가 시작을 거부한다(`bi-review` 7-5, 시험은 04 §8). 켜진 설정에서만 스텁 어댑터와 `/dev/*`를 등록하고 꺼져 있으면 경로 자체가 없다(404). 프런트 스텁 UI는 `/dev/stub-users` 응답 여부로 판별하고(config.js 변경 없음), 시험용 사용자 시드 명령도 같은 거부 규칙을 따른다. 8번에서 어댑터를 바꾸면 `/dev/*`만 사라지고 A1 이하 계약은 그대로다. 스위치 `AUTH_STUB_ENABLED`와 판별 방식은 **이 문서 AP-1 = 통합 AP-13으로 승인됨**(`03b` 6-3).

## 3. 오류 코드 사전 (FU-1)
| 코드 | HTTP | `details` | 뜻 |
| --- | --- | --- | --- |
| `UNAUTHENTICATED` · `USER_NOT_REGISTERED` · `USER_INACTIVE` · `FORBIDDEN` | 401·403 | - | 신원 없음 / 미등록 / 비활성 / 권한 부족 |
| `NOT_FOUND` · `ROW_NOT_FOUND` | 404 | - | 대상 없음 / 행 없음(C3) |
| `VALIDATION_ERROR` | 422 | `fields[]` | 필수·범위·형 등 입력 규칙 위반 |
| `ALREADY_EXISTS` | 409 | `field` | 유일 값 중복(팀 코드·이름, 로그인 ID, 데이터셋·열 이름, uuid) |
| `DEFINITION_VERSION_MISMATCH` | 409 | `current_version` | 다른 사람이 먼저 정의를 바꿈. 화면은 다시 읽기를 안내 |
| `CELL_CONFLICT` · `PASTE_CONFLICT` · `PERIOD_CONFLICT` | 409 | `conflicts[]` | 칸 값이 바뀜 / 붙여넣기 충돌(전부 취소) / 이미 있는 기간 |
| `DATASET_HAS_ROWS` · `COLUMN_LOCKED` · `LAST_ADMIN` | 422·422·409 | - | 행이 있어 변경 불가 / 열 type·kind 변경 불가 / 마지막 관리자 |
| `WRITE_BUSY` | 503 | `retry_after` | 행 쓰기의 락 대기 초과·교착(`55P03`·`40P01`). 재시도 가능, 정의 변경용 `DEFINITION_BUSY`와 구분 |
| `FORMULA_INVALID` · `FORMULA_CIRCULAR` · `FORMULA_RUNTIME_ERROR` | 422 | `errors[]` / `path[]` / - | C0 검사 실패 / 순환 참조 / 계산 불가(DB 오류는 정규화, 07 §5) |
| `DEFINITION_BUSY` | 503 | `retry_after` | 정의 변경 락 대기 초과, 화면이 "다시 시도" 안내(07 §8) |
| `PAYLOAD_TOO_LARGE` | 413 | `limit` | 붙여넣기 5,000행 또는 요청 상한(기본값 A 1MiB) 초과 |
| `PREVIEW_BUSY` · `GUEST_TOKEN_RATE_LIMITED` | 429 | `retry_after` | 미리보기 사용자당 동시 1건·전역 상한 / 입장권 사용자별 제한(한도 값 **[미답]**, 08 §4) |
| `SUPERSET_REJECTED` · `SUPERSET_UNAVAILABLE` | 502·503 | - | Superset이 거부 / 연결 불가 |
| `INTERNAL_ERROR` | 500 | - | 예기치 않은 오류 |
- 계산 열 칸의 오류 코드 `E1`(0으로 나눔) `E2`(글자 길이 범위) `E3`(날짜 범위)는 API 오류가 아니라 Row `errors` 값이며 문구는 D1 `cell_errors`가 준다(07 §2-2).

## 4. 권한 매트릭스와의 일치 (06 §4-1)
| 06 동작 | 엔드포인트 | 권한 열 |
| --- | --- | --- |
| 팀 만들기·소속·역할·비활성화 | A3 A4 A5 A6 A7 A8 A9 | 관리자 |
| 내 정보·팀 목록 | A1 A2 | 읽기 |
| 데이터셋 만들기·열 정의·수식 편집·미리보기 | B2 B4 B5 B6 D2 D3 D4 D5 | 정의(팀) |
| 행 입력·칸 수정·붙여넣기 | C2 C3 C4 | 입력(팀) |
| 데이터셋·행·열 정의·수식 보기 열람 | B1 B3 C1 D1 D6 D7 D8 | 읽기 |
| 대시보드 목록·보기(입장권) | E3 E6 | 읽기 |
| 대시보드 연결 등록·해제, 동기 현황·다시 시도 | E4 E5 E2 D9 D10 (E1 상태 값은 읽기, 사유는 관리자) | 관리자 |
- 권한 매트릭스 시험은 이 표의 엔드포인트 × 역할(관리자, 정의 담당자, 입력자, 다른 팀 구성원, 비소속 읽기, 비활성)로 자동화한다(03b 3-6 BY4). 계약 밖 쓰기 경로는 없다.

## 5. 프런트 설정과 훅
- `config.js`/`config.ts`는 **FU-1에서 변경하지 않는다**(새 변수 없음). Superset 새 창 링크는 기존 `supersetRoot`를 쓴다. `APP_UPLOAD_MAX_MB`는 가져오기 단위로 이월(03b 5-4). 훅은 위 ID 단위로 만들고 오류는 `error.code`로 분기한다.

## 6. 승인 상태 (`03b` 6-3. 통합 번호는 04 §9-1: 이 문서의 AP-1 = 통합 AP-13, AP-2 = 통합 AP-14)
| 번호 | 항목 | 시점 |
| --- | --- | --- |
| AP-1 | **승인**: 새 환경변수 `AUTH_STUB_ENABLED`(스텁 켜기, 기본 꺼짐)와 fail-closed 판별(`APP_ENV` 명시 설정 + 허용 목록 local·test, 04 §8). 8번 확정 시 어댑터 변수는 따로 승인 | 승인됨 |
| AP-2 | **승인**(통합 AP-14): 04 부록 A 갱신 — `PERIOD_CONFLICT` 추가, 이 문서의 오류 코드 사전 채택 | 승인됨 |
| - | 새 런타임 의존성·기준선과 다른 설정·모델 변경: 이 문서 없음. `/health` 필드 추가는 03b 3-6에서 승인됨 | - |
- 승인된 **[제안]**(`03b` 6-2): 숫자 십진 문자열(일반 JSON 숫자와 다름), 이름 길이 상한·금지 문자, 붙여넣기 요청 상한 A/B, `WRITE_BUSY`, 클라이언트 임시 행, `/health` 새 필드의 메모리 값, `E3`가 `embedded_uuid`를 모두에게 노출, `E1` 상태 값을 읽기로 공개, 스텁 쿠키 방식, `LAST_ADMIN` 보호, 검사(D2)를 200으로 응답.

## 7. 후속 기능 단위에서 결정
- 행 보관·복구·영구 삭제, 열·수식·데이터셋 보관·삭제 API와 영향 차트 수 안내(08 §2-1), 30일 규칙 응답(409).
- 기준값 표, 이전 행 참조·같은 데이터셋 집계의 수식 응답, 참조 열 검증·끊어진 참조 점검, 공통 요약 API.
- 엑셀 가져오기(업로드 413·`APP_UPLOAD_MAX_MB`·미리보기·확정·동시 1건 429·입력 차단 응답), 원본 파일 정보.
- 변경 기록 조회, 소급 변경·마감, 역할별 열 편집 권한·데이터셋별 예외 권한, 같은 기간 여러 행 허용 설정, 데이터셋의 팀 변경.
- 8번 인증 방식 확정 뒤 `/dev/*` 제거, 401 처리(로그인 이동), Explore 자동 로그인, 입장권 `user` 식별자 교체.
- 행 부분 로딩 방식(AG Grid Community 확인 뒤), 입장권 속도 제한 한도 값, 버전 접두어 도입.
