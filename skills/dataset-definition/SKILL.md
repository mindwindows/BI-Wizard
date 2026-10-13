---
name: dataset-definition
description: 팀의 데이터셋을 만들고 열(원본 열)을 정의하는 기능. 이름, 날짜 단위(일·월·연), 열 타입(글자·숫자·날짜·예/아니오·선택 목록), 필수·범위 규칙, 기준 날짜 열, 열 구분 태그, 정의 버전(동시 편집 충돌)을 다룬다. "데이터셋 만들어줘", "열 추가", "기준 날짜 열 지정", "열 이름 바꿔줘", "범위 규칙 걸어줘", "정의 충돌 났어요" 같은 요청에 사용한다. 화면(S2·S3·S4 Inspector)은 프런트 단위에서 붙고 이 문서의 5절 "사람(화면)"에 합친다.
---

# dataset-definition — 데이터셋·열 정의

## 1. 목적
팀의 정의 담당자가 데이터셋(이름과 날짜 단위)을 만들고 입력할 열의 타입과 규칙을 정한다. 데이터셋을 만드는 순간 값을 저장할 원본 표(`bi_data.ds_<번호>`)가 같은 트랜잭션 안에서 함께 만들어지고, 열을 추가하면 원본 표에 열(`c_<번호>`)이 생긴다. 모든 사용자는 다른 팀의 데이터셋도 열람할 수 있다. 입력(FU-1c)·수식(FU-1d)·Superset 연결(FU-1e)은 이 정의 위에서 동작한다.

## 2. 사용 조건 / 사전 요구사항
- 로그인: 모든 API가 인증을 거친다(`permission-management`의 신원 방식, 개발에서는 스텁).
- 권한(06 §4-1):
  - **읽기(B1·B3):** 인증된 활성 사용자 누구나, 다른 팀 데이터셋 포함.
  - **정의(B2·B4·B5·B6): 그 데이터셋 팀의 `definer`만.** 관리자(`is_admin`)여도 그 팀의 `definer`가 아니면 403 `FORBIDDEN`이다(필요하면 관리자가 자기를 그 팀의 정의 담당자로 소속시킨다). 입력자(`entry`), 다른 팀 구성원, 소속 없는 사용자도 403이다. 비활성 사용자는 403 `USER_INACTIVE`, 신원 없음은 401.
  - B4~B6의 권한 검사는 본문 검증보다 먼저다(권한 없는 사용자는 입력 오류 내용을 알 수 없다). B2는 팀이 본문에 있어 본문 검증 뒤에 검사한다.
- 실행 상태: `local-environment` 통과, `migrate`가 `0004`까지 적용(`datasets`·`dataset_columns`). backend 시작 자가 점검이 `bi_data`의 새 객체(표, 열이 소유한 Identity 시퀀스, 인덱스, 제약)를 허용한다.
- 선행 데이터: 팀과 정의 담당자 소속(`skills/permission-management`).
- 비활성 팀의 정의 담당자도 지금은 데이터셋을 만들 수 있다(비활성 팀·사용자의 소유 데이터셋 효과는 후속, 06 §4-1).

## 3. 입력
공통: JSON UTF-8, snake_case. 요청 본문에 정의되지 않은 필드를 보내면 422다. 글자는 NFC로 정규화하고 앞뒤 공백을 지운 뒤 길이를 센다.

### B2 `POST /api/datasets`
| 필드 | 규칙 |
| --- | --- |
| `team_id` | 필수 정수. 그 팀의 정의 담당자여야 한다 |
| `name` | 필수, 1~100자, 제어문자 불가. 팀 안에서 유일 |
| `date_unit` | 필수 `day`·`month`·`year`(기간의 단위, 시각 없음) |

### B4 `PATCH /api/datasets/{id}` (보낸 필드만 바꾼다)
`expected_version`(필수, 읽은 `def_version`), `name?`, `date_unit?`, `base_date_column_id?`(열 번호 또는 `null`로 해제). 날짜 단위와 기준 날짜 열은 **행이 0개일 때만** 바꿀 수 있다(같은 값은 항상 가능). 기준 날짜 열은 같은 데이터셋의 **원본(`raw`) `date` 열**만 된다.

### B5 `POST /api/datasets/{id}/columns` (원본 열만, 계산 열은 D4 `POST /api/datasets/{id}/formulas`, `formula-column`)
| 필드 | 규칙 |
| --- | --- |
| `expected_version` | 필수 정수 ≥ 1 |
| `display_name` | 필수, 1~100자. `[` `]` `"`와 제어문자 불가. 예약어 `team`·`팀`·`row_id`·`행 번호`는 불가(대소문자 구분 없이). 데이터셋 안에서 유일 |
| `type` | 필수 `text`·`number`·`date`·`boolean`·`choice` |
| `required` | 기본 `false` (필수 입력 여부, 입력 단위에서 서버가 검사) |
| `rules` | 타입별 검증 규칙(아래). 규칙 변경 전에 입력된 값은 지우지 않는다 |
| `tag` | 열 구분 태그. **숫자 열에만**, 50자 이하, `"`·제어문자 불가. 빈 글자는 태그 없음 |
| `position` | 화면 순서(0 이상 정수). 비우면 맨 뒤(첫 열 0, 다음은 현재 최댓값 + 1) |

`rules` 모양(알 수 없는 키는 422):
| 타입 | 키 | 비고 |
| --- | --- | --- |
| `number` | `min`, `max`, `decimals` | `min`·`max`는 **십진 문자열 또는 JSON 정수**다. JSON 부동소수점(`1.5`)은 `BAD_FORMAT`으로 거부한다(05 §1 십진 문자열, 2진 근사 배제). 지수 표기·`NaN`·무한·38자리 초과도 거부하고, 아주 큰 정수·긴 글자는 변환 전에 걸러 500이 아니라 422다. 저장·응답은 **서버가 정규화한 십진 문자열**이다(`"-5.50"` → `"-5.5"`, `"-0"` → `"0"`; 05 §1의 number 값 표현). `min ≤ max`. `decimals`는 0~10 정수 |
| `text` | `max_length` | 1~10,000 정수 |
| `date` | `min`, `max` | `YYYY-MM-DD`, `min ≤ max` |
| `choice` | `options` | **필수.** 문자열 목록 1~100개, 각 1~100자·제어문자 불가·중복 불가(앞뒤 공백 제거) |
| `boolean` | 없음 | 키가 있으면 422 |
빈 `rules`(`{}` 또는 `null`)는 저장하지 않는다(`null`).

### B6 `PATCH /api/datasets/{id}/columns/{col_id}` (보낸 필드만 바꾼다)
`expected_version`(필수), `display_name?`, `required?`, `rules?`, `tag?`(`null`이면 지움), `position?`. **`type`·`kind`는 바꿀 수 없다**: 현재와 다른 값을 보내면 422 `COLUMN_LOCKED`(같은 값이면 무시). 다른 타입이 필요하면 새 열을 추가한다. 계산 열(`formula`)에는 `required: true`와 `rules`를 줄 수 없다(422). 이름을 바꿔도 원본 표의 열 이름(`c_<번호>`)은 그대로다.

### 목록 B1 `GET /api/datasets`
`team_id?`, `limit`(기본 50, 1~200), `offset`. 정렬: **내 소속 팀의 데이터셋이 먼저**, 다음 팀 이름, 데이터셋 이름. 이름순은 한글 가나다순이다(아래 "이름순 정렬").

## 4. 출력
- 공통 형태(05 §1):
  - Column `{id, display_name, type, kind, required, rules, tag, position}`
  - Dataset `{id, team_id, name, date_unit, base_date_column_id, status, def_version, created_by{id, display_name}, created_at}` (`created_at`은 `+09:00` ISO 8601)
- B1 200 `{items[Dataset], total, limit, offset}` (동기 상태는 이 응답에 없다: Superset 동기 상태는 `GET /api/superset/datasets`(E1, `skills/dashboard-link`)에서 화면이 `dataset_id`로 결합한다).
- B2 201, B4 200, B3 200: Dataset + `team{id, code, name}` + `columns[Column]`(순서: `position`, `id`) + `permissions{define, enter}`(내 권한. 관리자라도 소속이 없으면 둘 다 false).
- B5 201, B6 200: `{column, def_version}` (새 정의 버전).
- 오류(`{"error": {"code", "message", "details", "request_id"}}`, 한국어 `message`):
  - 409 `DEFINITION_VERSION_MISMATCH` + `details.current_version` — 다른 사람이 먼저 정의를 바꿈. 새로 읽고 다시 한다.
  - 409 `ALREADY_EXISTS` + `details.field`(`name`: 팀 안 데이터셋 이름, `display_name`: 데이터셋 안 열 이름)
  - 409 `TARGET_INACTIVE` + `details.field=team` — B2에서 비활성 팀에는 데이터셋을 만들 수 없다(03b 19-1 결정 1). **권한 판정(그 팀의 정의 담당자)이 먼저**라서 정의 담당자가 아니면 팀이 비활성이어도 403이다. 팀을 다시 사용 중으로 바꾸려면 관리자가 A4(`permission-management`)를 쓴다. 이미 있는 데이터셋의 열 편집·행 입력은 이 규칙의 대상이 아니다.
  - 422 `VALIDATION_ERROR` + `details.fields[{field, code, message}]` — 필드 코드 `REQUIRED`·`TOO_LONG`·`BAD_FORMAT`·`RESERVED`·`OUT_OF_RANGE`. 규칙 오류의 `field`는 `rules.min`처럼 키까지 가리킨다. 기준 날짜 열이 원본 `date` 열이 아니거나 다른 데이터셋의 열이면 `base_date_column_id` `BAD_FORMAT`.
  - 422 `DATASET_HAS_ROWS` — 행이 있어 날짜 단위·기준 날짜 열을 바꿀 수 없음
  - 422 `COLUMN_LOCKED` — 열 `type`·`kind` 변경 시도
  - 503 `DEFINITION_BUSY` + `details.retry_after`(2초) — 정의 변경 락 대기가 1초를 넘음. 같은 요청을 다시 보내면 된다.
  - 403 `FORBIDDEN`, 404 `NOT_FOUND`(없는 데이터셋·열, 다른 데이터셋의 열), 401/403 인증 오류
- 저장 위치:
  - `datasets`(`def_version`, 정의 해시 `def_hash`), `dataset_columns`(`public`, `bi_owner` 소유, 06 §2).
  - 원본 표 `bi_data.ds_<데이터셋 번호>`: `row_id`(bigint identity, PK)와 원본 열 `c_<열 번호>`(`text`→`text`, `number`→`numeric`, `date`→`date`, `boolean`→`boolean`, `choice`→`text`, 모두 NULL 허용 = 빈 칸은 미입력). 소유자는 `bi_app`, `bi_readonly`(Superset)는 `SELECT`만.
  - **기준 날짜 열**을 지정하면 그 열이 `NOT NULL`이 되고 CHECK `ck_ds_<번호>_period`(기간의 첫날: 월 단위면 1일, 연 단위면 1월 1일. `timestamp` 변환을 거쳐 세션 시간대와 무관)와 유일 인덱스 `ux_ds_<번호>_period`(같은 기간 하나)가 걸린다. 해제하거나 단위를 바꾸면 풀리고 다시 걸린다. 기준 날짜 열은 입력 때 필수로 취급한다(`required` 플래그 값은 그대로 두고 입력 단위가 `REQUIRED`로 판정, FU-1c).
- 부수 효과: 정의가 **실제로 바뀌고 커밋된 뒤에만** `DatasetSyncPort.request_dataset_sync`를 백그라운드로 요청한다(Superset 가상 데이터셋 동기화. 구현은 `backend/app/superset/worker.py`이고 Superset 접속 설정이 없으면 아무것도 하지 않는 기본 구현이다. 요청은 `pending` 표시와 대기열 투입뿐이라 Superset이 멈춰도 응답은 그대로다, `skills/dashboard-link`). 요청이 실패해도 응답은 그대로다. 아무것도 바뀌지 않은 PATCH(같은 값)는 버전을 올리지 않고 동기화도 요청하지 않는다.

### 정의 버전과 정의 변경 진입점 (동시 편집)
- 정의를 바꾸는 모든 요청(B4~B6, D4·D5)은 한 함수(`backend/app/dataset/definition.py`)를 지난다: ① `lock_timeout 1초` ② `datasets` 행을 `FOR NO KEY UPDATE`로 잠금(읽기는 막지 않는다) ③ `expected_version` 확인 ④ 열 변경(정의 행 + 원본 표 DDL) ⑤ 정의 변경 훅(formula 모듈이 등록한다: 저장된 수식 전부를 현재 열 이름·태그로 다시 컴파일해 `formulas`·`formula_deps`를 쓰고 `dv_<번호>`·`de_<번호>` 뷰를 같은 트랜잭션에서 만든다. 수식이 깨지면 `FORMULA_INVALID`/`FORMULA_CIRCULAR`로 열 변경까지 전부 롤백) ⑥ `def_version + 1`과 `def_hash`(훅이 돌려준 뷰 정의 해시) 기록 후 커밋. 데이터셋 등록(B2)도 같은 훅을 불러 수식이 없어도 `dv_`(팀 열 포함)·`de_`를 만든다. 중간에 실패하면 모두 롤백된다(원본 표 DDL 포함).
- `def_hash`는 **뷰 `dv_`·`de_` 정의(리터럴 렌더)의 sha256**이다(훅이 없는 환경에서만 정의 구조 해시를 쓴다). 열 표시 이름·필수·규칙·순서는 해시에 들어가지 않아 그것을 바꿔도 뷰를 다시 만들지 않는다. 시작할 때 현재 정의로 계산한 해시와 다르면 그 데이터셋의 뷰만 다시 만든다(`formula-column`).
- 같은 `expected_version`으로 동시에 요청하면 하나만 성공하고 나머지는 `DEFINITION_VERSION_MISMATCH`다.
- 행 쓰기(FU-1c, `data-entry`)는 같은 행을 `FOR SHARE`로 잡아 정의 변경과 서로 기다린다. **굶음은 일어날 수 있다(관찰, PostgreSQL 16.10)**: `FOR SHARE` 보유자가 쥔 동안 정의 변경이 기다리면, 뒤에 들어온 새 `FOR SHARE`(행 쓰기)가 정의 변경을 **앞질러** 잠금을 얻는다(공유 잠금끼리는 호환이라 줄을 서지 않는다). 그래서 행 입력이 끊이지 않으면 정의 변경(열 추가 등)이 계속 순서를 못 얻을 수 있다. 다만 무한 대기는 없다: 1초 뒤 `DEFINITION_BUSY`(503)로 끝나므로 입력이 잠잠할 때 다시 시도한다. 단정으로 고정한 시험: `test_dataset_concurrency.py`의 `test_continuous_for_share_holders_overtake_a_waiting_definition_change`(잠금 보유자만으로 재현)와 `test_entry_concurrency.py`의 `test_continuous_row_writes_overtake_a_waiting_definition_change`(실제 행 쓰기 경로).
- **이름 변경(B4)은 FK 자식 INSERT를 기다리게 한다(관찰, PostgreSQL 16.10)**: `datasets.name`이 `UNIQUE(team_id, name)`에 들어 있어 이름을 바꾸는 UPDATE는 키 변경으로 취급돼 `FOR UPDATE` 수준의 행 잠금이 걸리고, 자식 INSERT가 부모 행에 거는 `FOR KEY SHARE`가 커밋까지 기다린다. 열 추가는 `def_version`·`def_hash`만 바꾸므로 기다리게 하지 않는다. 06 §5에서 짧은 대기로 보고 **그대로 두기로 결정**했다. 이름 변경 트랜잭션이 짧으면 문제없고(`test_rename_in_progress_makes_fk_child_inserts_wait_until_commit`), 정의 변경 훅이 뷰를 만드는 시간(FU-1d)만큼 `superset_datasets` 같은 자식 INSERT가 기다릴 수 있다.
- **이름순 정렬(한글 가나다순, 03b 19-1 결정 2)**: 이 DB의 기본 정렬(`en_US.utf8`)은 한글을 가나다순으로 정렬하지 못한다. 이름순 목록(A1 소속, A2, A5, B1, DV1)의 `ORDER BY`에만 ICU collation `ko-KR-x-icu`를 붙인다(`app/core/sorting.py`의 `by_name()`, SQLAlchemy 구성요소이며 `text()`가 아니다). 저장 collation은 바꾸지 않아 마이그레이션이 없다. 선택 이유: 공식 `postgres:16.10-bookworm` 이미지에 `ko-KR-x-icu`가 있다(`pg_collation`로 확인). 'C' collation은 완성형 한글 가나다순과 같지만 라틴 대소문자가 한글 앞에 오고 한글·라틴 혼합 이름이 어색해서 쓰지 않았다. 한계: 숫자는 글자 순서(`10`이 `9`보다 앞), 라틴은 한글 뒤, 소문자가 대문자보다 앞(`abc`, `Abc`), 동명은 `id` 순. PostgreSQL이 아닌 방언(SQLite 시험)에서는 COLLATE를 붙이지 않는다. collation이 DB에 없으면 시작 자가 점검이 경고를 남기고(거부하지 않음) 이후 질의가 DB 기본 순서로 돌아간다.
- **행이 0개 확인과 INSERT 경쟁**: 기준 날짜 열 지정·날짜 단위 변경의 "행이 0개" 확인은 `FOR NO KEY UPDATE`를 잡은 **뒤에** 실행되므로 진행 중인 행 INSERT가 끝난 뒤의 결과를 본다(`DATASET_HAS_ROWS`). 그래도 규칙 DDL이 기존 값 때문에 실패하면(NOT NULL·CHECK·유일 위반, 방어선) 500이 아니라 같은 422 `DATASET_HAS_ROWS`로, 표 잠금 대기 초과·교착이면 503 `DEFINITION_BUSY`로 답한다. 이름·번호 규칙 위반 같은 `DdlError`는 프로그램 오류라 500으로 둔다.

## 5. 실행 방법
### 사람(화면)
#### S2 데이터셋 목록 (`/datasets`)
1. 상단 메뉴 "데이터셋"을 연다. 표에 이름·팀·날짜 단위(일·월·연)·생성자·생성일이 나온다(`GET /api/datasets`). 내 소속 팀의 데이터셋이 위에 오는 정렬은 서버가 하며 화면은 받은 순서 그대로 보여 준다. 이름을 누르면 작업공간(S4)이 열린다.
2. "팀 필터"에서 팀을 고르면 그 팀만(`team_id`), "전체 팀"이면 전부 보인다. 50개씩 쪽 이동("이전"/"다음", `limit`/`offset`)이고 필터를 바꾸면 첫 쪽으로 돌아간다.
3. "새 데이터셋" 버튼은 **상단 "작업 팀"에서 내가 정의 담당자(`definer`)이고 그 팀이 활성일 때만** 보인다. 아니면 "데이터셋은 작업 팀의 정의 담당자만 만들 수 있습니다." 안내가 나온다. 이것은 편의이며 최종 방어선은 서버 권한 검사다.
4. 동기 상태(Superset) 열: 표시된 쪽의 `dataset_id`들로 `GET /api/superset/datasets`(E1)를 한 번 불러 "등록 대기 / 등록됨 / 등록 실패"를 결합한다(`skills/dashboard-link`). 실패 사유는 관리자에게만 보인다.
5. 비어 있으면 "등록된 데이터셋이 없습니다", 읽기 실패는 쉬운 문구와 "다시 불러오기".

#### S3 데이터셋 만들기 (`/datasets/new`)
1. S2의 "새 데이터셋"을 누른다. 팀 선택에는 내가 정의 담당자인 활성 팀만 나온다(기본은 작업 팀이 그 중 하나면 그 팀). 정의 담당자인 팀이 없으면 안내만 나온다.
2. 이름(100자 이하, 앞뒤 공백 제거)과 날짜 단위(일·월·연)를 고르고 "만들기"를 누르면 `POST /api/datasets {team_id, name, date_unit}` 후 작업공간으로 이동한다. 열은 작업공간에서 추가한다.
3. 같은 팀에 같은 이름이 있으면 409 `ALREADY_EXISTS`("같은 이름이 이미 있습니다"), 그 밖의 오류도 아래 표의 문구로 폼 안에 나온다.

#### S4 작업공간 골격과 Inspector (`/datasets/<번호>`)
- 왼쪽: "데이터셋 정보"(팀·날짜 단위·기준 날짜 열·생성자·생성일·정의 버전)와 "열 목록". 가운데: 열 헤더 미리보기 표(입력 그리드는 단위 1c에서 이 자리에 들어온다). 오른쪽: Inspector(접기 ▶/펼치기 ◀, "Inspector 폭" 슬라이더로 280~640px). 열 목록이나 헤더의 열 이름을 누르면 그 열이 Inspector에 열린다.
- **열 추가(B5):** "열 추가" 버튼 -> 열 이름(100자 이하)·타입(글자·숫자·날짜·예/아니오·선택 목록)·필수 입력·규칙·위치 입력 -> "열 추가". 열 이름에 `[` `]` `"`나 줄바꿈 같은 제어 문자를 넣거나 예약어(`team`, `팀`, `row_id`, `행 번호`)를 쓰면 입력하는 즉시 이유가 나오고 저장 버튼이 막힌다. 규칙: 숫자는 최솟값·최댓값(십진수 그대로, 예 `0`, `100.50`)·소수 자릿수와 "구분 태그"(숫자 열만, 50자 이하, 같은 태그끼리 수식에서 합산), 글자는 최대 글자 수, 날짜는 가장 이른/늦은 날짜(`YYYY-MM-DD`), 선택 목록은 항목(한 줄에 하나, 중복 불가), 예/아니오는 규칙 없음. 위치를 비우면 맨 뒤. 숫자 값은 `"100.50"` 같은 **십진 문자열**로 서버에 간다(05 §1).
- **열 수정(B6):** 목록에서 열을 고르면 "열 수정: <이름>"이 열린다. **타입과 종류는 바꿀 수 없다**고 표시되며 입력칸이 없다(다른 타입이 필요하면 새 열을 추가). 이름·필수·규칙·태그·위치만 바뀐 항목만 서버로 가고, 바뀐 것이 없으면 "저장"이 막혀 있다. 계산 열(수식)은 이 양식에서 읽기 전용이다(수식은 `formula-column`의 수식 편집기에서 고친다). 계산 열에도 이름·태그·위치는 B6로 바꿀 수 있고 태그를 바꾸면 `SUMTAG`를 쓰는 수식의 순환·`TAG_EMPTY`를 훅이 다시 검사해 어긋나면 변경 전체를 되돌린다(422 `FORMULA_CIRCULAR`/`FORMULA_INVALID`).
- **데이터셋 설정(B4):** "데이터셋 설정" 버튼 -> 이름, 날짜 단위, 기준 날짜 열(입력 열 중 날짜 열만, "없음"으로 해제). **행이 한 건이라도 있으면 날짜 단위와 기준 날짜 열은 바뀌지 않으며** 서버가 422 `DATASET_HAS_ROWS`를 주고 화면이 이유를 안내한다.
- **동시 편집:** 정의를 읽은 시점의 `def_version`을 `expected_version`으로 보낸다. 다른 사람이 먼저 바꿔 409 `DEFINITION_VERSION_MISMATCH`가 나면 "다른 사람이 먼저 바꿨습니다. 최신 내용을 다시 읽었습니다…" 안내와 함께 화면이 최신 상태를 자동으로 다시 읽는다. 열 추가 폼에 입력하던 내용은 남고(수정 폼은 최신 값으로 다시 채워짐), 확인한 뒤 다시 저장하면 최신 버전으로 보낸다. 503 `DEFINITION_BUSY`는 "잠시 뒤 다시 시도"(`retry_after`가 있으면 "약 N초 뒤") 안내만 하고 같은 내용을 다시 저장하면 된다.
- **읽기 전용:** 서버 응답의 `permissions.define`이 false(정의 담당자가 아닌 사용자)면 Inspector에 "읽기 전용" 안내가 나오고 열 추가 버튼·저장 버튼이 없으며 입력칸이 모두 막힌다. 열람과 열 정의 확인은 가능하다.

### AI·API (스텁 로그인 예, `permission-management` 참고)
```
BASE="http://localhost:<BACKEND_PORT>${APP_BASE_PATH}/api"
curl -c jar -X PUT -H 'content-type: application/json' -d '{"login_id":"stub-definer"}' "$BASE/dev/stub-user"
# 1) 데이터셋 만들기 (정의 담당자인 팀의 team_id)
curl -b jar -X POST -H 'content-type: application/json' \
  -d '{"team_id": <팀 번호>, "name": "월별 매출", "date_unit": "month"}' "$BASE/datasets"
# 2) 열 추가 (응답의 def_version을 다음 요청의 expected_version으로 쓴다)
curl -b jar -X POST -H 'content-type: application/json' \
  -d '{"expected_version": 1, "display_name": "기준월", "type": "date"}' "$BASE/datasets/<번호>/columns"
curl -b jar -X POST -H 'content-type: application/json' \
  -d '{"expected_version": 2, "display_name": "매출", "type": "number", "required": true, "rules": {"min": 0, "decimals": 2}, "tag": "수익"}' "$BASE/datasets/<번호>/columns"
# 3) 기준 날짜 열 지정 (행이 없을 때만)
curl -b jar -X PATCH -H 'content-type: application/json' \
  -d '{"expected_version": 3, "base_date_column_id": <기준월 열 번호>}' "$BASE/datasets/<번호>"
# 4) 열 이름·규칙 바꾸기
curl -b jar -X PATCH -H 'content-type: application/json' \
  -d '{"expected_version": 4, "display_name": "총매출", "rules": {"min": 0, "max": 100000}}' "$BASE/datasets/<번호>/columns/<열 번호>"
```
- 충돌(409 `DEFINITION_VERSION_MISMATCH`)이면 `GET /datasets/<번호>`로 최신 `def_version`과 열을 읽고 바꿀 내용을 확인한 뒤 새 버전으로 다시 보낸다.
- 잘못 만든 열·데이터셋을 지우는 API는 FU-1에 없다. 관리자가 수동으로 정리한다: `skills/admin-cleanup`.

## 6. 관련 UI / API / command / DB
- UI: S2 `/datasets`, S3 `/datasets/new`, S4 `/datasets/<번호>`(Inspector 포함). 구현 `frontend/src/features/dataset/`.
- API: B1~B6(05 §2-2). 코드 `backend/app/dataset/`(`router`·`service`·`repo`·`schemas`·`rules`·`definition`·`hashing`), 동적 DDL `backend/app/ddl/`(`names`·`dynamic`), 정의 변경 훅·동기화 포트 `backend/app/core/ports.py`.
- command: 없음. 정리·점검은 `skills/admin-cleanup`(수동 절차)와 `python -m migrations.roundtrip`.
- DB: `public.datasets`, `public.dataset_columns`(revision `0004_datasets_columns`), `bi_data.ds_<번호>`(런타임 DDL, `bi_app` 소유).
  - `bi_app` 권한은 명시 GRANT뿐이다: 표 단위 SELECT·INSERT(DELETE 없음), UPDATE는 열 단위(`datasets`: `name`·`date_unit`·`base_date_column_id`·`status`·`def_version`·`def_hash`, `dataset_columns`: `display_name`·`type`·`required`·`rules`·`tag`·`position`). `datasets.team_id`·`created_by`와 `dataset_columns.dataset_id`·`kind`는 DB가 변경을 거부한다(팀 열은 뷰에 상수로 들어가고 열 종류는 바뀌지 않는다). `type`은 계산 열 결과 형 때문에 갱신 권한이 있고 원본 열의 `type` 금지는 앱 규칙(`COLUMN_LOCKED`)이다.
  - 제약: 팀 안 데이터셋 이름 유일, 데이터셋 안 열 이름 유일, 열거(`date_unit`·`status`·`type`·`kind`)는 `text` + 이름 있는 CHECK, 계산 열은 필수일 수 없고 선택 목록 형이 아니다, `base_date_column_id`는 같은 데이터셋의 열만(복합 FK `fk_datasets_id_dataset_columns`).
  - 런타임 DDL 규칙: SQLAlchemy 내장 DDL 구문·Alembic `Operations`만, `text()`·`exec_driver_sql` 금지, 객체 이름은 번호 규칙 함수(`ds_<n>`, `c_<n>`, `ux_ds_<n>_period`, `ck_ds_<n>_period`)로만 만들고, 객체 종류는 표·뷰·인덱스·제약이며 `bi_data` 밖에는 만들지 않는다. 사용자 입력 글자는 식별자에 쓰이지 않는다. `bi_app`은 `public`에 만들 수 없다.

## 7. 실패 시 확인 방법
| 증상 | 원인 | 확인과 해결 |
| --- | --- | --- |
| 409 `DEFINITION_VERSION_MISMATCH` | 다른 사람이 먼저 정의를 바꿈(또는 내 요청이 두 번 감) | `details.current_version`. `GET /datasets/<번호>`로 다시 읽고 확인한 뒤 새 `def_version`으로 재시도 |
| 503 `DEFINITION_BUSY` | 정의 변경 락을 1초 안에 못 얻음(다른 정의 변경 진행, 긴 읽기 중인 `ALTER`, 입력 중인 행 쓰기) | `retry_after`초 뒤 같은 요청을 다시 보낸다. 반복되면 `docker compose logs backend`와 DB의 긴 트랜잭션(`pg_stat_activity`)을 본다 |
| 422 `DATASET_HAS_ROWS` | 행이 있는데 날짜 단위·기준 날짜 열을 바꾸려 함 | 행이 필요 없다면 비우는 수단은 FU-1에 없다(FU-2). 새 데이터셋을 만들거나 수동 정리(`admin-cleanup`) |
| 422 `COLUMN_LOCKED` | 열 `type`·`kind` 변경 시도 | 새 열을 추가한다 |
| 422 `VALIDATION_ERROR` | 이름 규칙(금지 문자·예약어·길이)·규칙 모양·태그 위반 | `details.fields[].field/code`. 예약어는 `team`·`팀`·`row_id`·`행 번호` |
| 409 `ALREADY_EXISTS` | `details.field`가 `name`(팀 안 데이터셋) 또는 `display_name`(데이터셋 안 열) | 다른 이름을 쓴다 |
| 403 `FORBIDDEN` | 그 데이터셋 팀의 정의 담당자가 아님(관리자 포함) | `skills/permission-management`로 팀 소속·역할 확인 |
| 500 `INTERNAL_ERROR` | 원본 표 생성·열 추가 실패 등(전부 롤백됨) | 오류 본문 `request_id`로 `docker compose logs backend`. 정의 행과 원본 표가 함께 되돌려졌는지는 `datasets`와 `bi_data`의 `ds_*`를 비교 |
| 503 `SERVICE_UNAVAILABLE` (모든 API) | DB 장애뿐 아니라 **사용자 조회 설정 오류(권한 거부·표 없음)도 같은 503으로 보인다**(접근을 닫는 fail-closed). 예: `migrate` 전, 접속 계정이 `bi_app`이 아님 | `/api/health/db`, `docker compose logs migrate backend`. `migrate`가 `0004`까지 적용됐는지, 접속 계정이 `bi_app`인지 확인 |
| `ds_1 already exists`(`downgrade` 뒤 다시 `upgrade`/데이터셋 만들기) | `downgrade 0004`는 `bi_data.ds_*`를 지우지 않는다. 다시 `upgrade`한 뒤 `datasets`의 번호(Identity)는 1부터 다시 시작하므로 남은 `ds_1`과 충돌한다 | **`downgrade` 뒤에는 `bi_data.ds_*`를 `admin-cleanup`으로 정리한 뒤 다시 `upgrade`한다** |
| backend가 시작하지 않음 | 시작 자가 점검: `bi_data`에 허용 밖 객체(함수·독립 시퀀스·타입 등) | `docker compose logs backend`의 메시지. 누가 만들었는지 확인 후 `admin-cleanup` 방식으로 정리 |
| `ds_*`에 행/열이 정의와 어긋남 | 수동 SQL로 바꿈 | 정의 변경은 API로만 한다. 어긋나면 `datasets`·`dataset_columns`와 `bi_data` 열 목록을 대조 |

#### 화면 변경(03b 19-1 결정 반영)
- S3: 팀 선택은 이미 정의 담당자인 활성 팀만. 서버 409 `TARGET_INACTIVE`(`details.field=team`)는 폼 위 오류 줄에 "비활성 팀에는 데이터셋을 만들 수 없습니다."(`DATASET_TEAM_INACTIVE_TEXT`, errors.ts). A8의 소속 지정 문구와 구분(B2 전용 분기는 DatasetCreatePage).
- S3 폼 `.panel-form` 최대 폭 560px. `.panel > button`은 내용 폭(붙여넣기 확인·결과 버튼은 `.actions` 안으로 이동).
- Inspector: `.inspector-form p`와 `.field > span` 여백 0(타입·종류 줄 사이, 오류 자리 공백 제거). 오류는 있을 때만 렌더(기존 그대로).

#### 화면 변경(1d)
- 왼쪽 "열 목록" 아래에 정의 담당자에게만 **계산 열 추가** 버튼이 생겼다(원본 열은 기존 **열 추가**). 계산 열은 B5가 아니라 D4(`POST /formulas`)로 만든다.
- 계산 열을 선택했을 때 Inspector: 열 정보 양식(읽기 전용, 타입·종류 잠김) 아래에 **수식 보기**와(정의 담당자만) **수식 고치기**가 붙는다. 문구 "계산 열은 여기서 고칠 수 없습니다"는 "계산 열의 이름·위치는 여기서 고칠 수 없습니다. 수식은 아래에서 확인하고 고칩니다."로 바뀌었다.
- 오류 문구 표에 `FORMULA_CIRCULAR`에 순환 경로가 붙고(`details.path`), `FORMULA_INVALID`·`FORMULA_RUNTIME_ERROR` 문구가 추가됐다(B6 태그 변경의 순환 거부도 같은 경로 표시).

### 화면에 나오는 오류 문구
| 코드 | 화면 문구 요지 |
| --- | --- |
| ALREADY_EXISTS (409, details.field) | name: 같은 이름이 이미 있음(데이터셋) / display_name: 같은 이름의 열이 이미 있음 |
| VALIDATION_ERROR (422) | 입력 확인 + `(표시 이름: 사용할 수 없는 이름입니다, 검증 규칙: 형식이 맞지 않습니다)` 식 필드별 풀이(필드 이름 한글화: 팀·날짜 단위·기준 날짜 열·타입·필수 여부·검증 규칙·구분 태그·위치). 필드 코드 REQUIRED·TOO_LONG·BAD_FORMAT·RESERVED·OUT_OF_RANGE 등 |
| DEFINITION_VERSION_MISMATCH (409) | 다른 사람이 먼저 바꿈, 최신 내용을 다시 읽었으니 확인 후 다시 시도(자동 재로딩) |
| DEFINITION_BUSY (503) | 다른 작업 진행 중, 잠시 뒤 다시 시도(약 N초 뒤) |
| DATASET_HAS_ROWS (422) | 이미 입력된 행이 있어 날짜 단위·기준 날짜 열을 바꿀 수 없음 |
| COLUMN_LOCKED (422) | 열의 타입과 종류는 바꿀 수 없음, 새 열을 추가 |
| FORMULA_CIRCULAR (422) | 이 변경으로 계산 열이 서로를 참조하는 순환이 생김(태그·수식 확인) |
| FORBIDDEN (403) | 이 작업을 할 권한이 없음 |
| NOT_FOUND (404) | 대상을 찾을 수 없음(없는 데이터셋 주소 포함) |
| SERVICE_UNAVAILABLE (503) | 서버가 일시적으로 응답하지 못함, 잠시 뒤 다시 시도 |
| NETWORK_ERROR / INTERNAL_ERROR | 서버 연결 실패 / 예기치 않은 오류 + 문의 번호(`request_id`) |

### 수식 한도에 걸릴 때 나오는 쉬운 말
수식·계산 열에 한도가 있다(03b 21-1). 한도에 걸리면 화면에는 아래 문구가 나온다. 문구는 `backend/app/formula/errors.py`의 `MESSAGES_KO`·`CELL_ERROR_MESSAGES_KO`와 같아야 하며, 값 자리 `{max}`·`{count}`·`{length}`는 예시 값으로 채워 보인다(`backend/tests/test_formula_limit_messages_doc.py`가 표와 코드를 대조한다).

| 한도 | 코드 | 화면 문구 | 사용자가 할 일 |
| --- | --- | --- | --- |
| 수식 2,000자 | `TOO_LONG` | `수식이 너무 깁니다. 2000자 이하로 줄여 주세요(지금 2500자).` | 수식을 줄이거나 여러 계산 열로 나눈다 |
| 글자 상수 200자 | `TEXT_CONSTANT_INVALID` | `글자 상수에 쓸 수 없는 내용이 있습니다: 200자를 넘습니다.` | 큰따옴표 안의 글자를 200자 이하로 줄인다 |
| AST 깊이 40 | `TOO_DEEP` | `괄호나 함수가 너무 깊게 겹쳐 있습니다(최대 40단계). 항이 많은 덧셈은 SUM(…)으로 쓰고, 긴 계산은 여러 열로 나눠 주세요.` | 괄호·함수 겹침을 줄이고 계산을 여러 열로 나눈다 |
| 항 41개 이상 덧셈 | `TOO_DEEP` | `괄호나 함수가 너무 깊게 겹쳐 있습니다(최대 40단계). 항이 많은 덧셈은 SUM(…)으로 쓰고, 긴 계산은 여러 열로 나눠 주세요.` | 항이 많은 덧셈은 `SUM(…)`으로 쓴다 |
| 참조 사슬 10단계 | `CHAIN_TOO_LONG` | `다른 계산 열을 따라가는 단계가 너무 깁니다(최대 10단계).` | 계산 열이 계산 열을 참조하는 단계를 줄인다 |
| 펼친 노드 2,000개 | `TOO_MANY_NODES` | `계산이 너무 복잡합니다. 참조한 계산 열을 펼치면 2000개를 넘습니다(지금 2500개).` | 참조하는 계산 열의 수식을 단순하게 만든다 |
| 변환 SQL 노드 5만 | `TOO_COMPLEX` | `계산이 너무 복잡해 처리할 수 없습니다. 수식을 나눠 여러 열로 계산해 주세요.` | 수식을 나눠 여러 열로 계산한다 |
| 숫자 38자리 | `NUMBER_INVALID` | `숫자는 38자리 이하로 쓰고 소수점 아래는 38자리까지 쓸 수 있습니다.` | 숫자를 38자리 이하로 줄인다 |
| `DATE` 범위 0001-01-01~9999-12-31 | `E3`(셀 오류) | `날짜가 범위(0001-01-01~9999-12-31)를 벗어났습니다.` | 해당 칸의 날짜 계산 입력값을 확인한다 |

- `neg`(단항 부호 `-`)는 전용 문구가 없다. 부호를 연달아 많이 겹쳐 쓰면 깊이로 세어져 위 `TOO_DEEP` 문구가 나온다.

## 8. 검증 방법
- DB 없이(SQLite, `docker build --target test backend`와 같다): `cd backend && pytest`. 데이터셋 API 시험은 SQLite에서 원본 표 생성·열 추가까지 실제로 실행하고 기준 날짜 열 규칙 DDL은 호출 기록으로 대신한다.
- 실제 PostgreSQL(권장, `skills/permission-management/SKILL.md`의 "검증 방법" 절차로 tmpfs `postgres-test` 준비): 같은 `pytest`가 `pg` 변형을 포함해 돈다. 시험 실행 환경에 `REQUIRE_PG=1`을 주면 PostgreSQL 환경이 없을 때 건너뛰지 않고 실패한다.
- 시험 위치(`backend/tests/`):
  - `test_dataset_api.py` — B1~B6 동작, 이름·규칙·태그 검증, 버전 충돌, 등록 + 원본 표 생성 원자성(실패 시 정의 행과 표가 함께 롤백), 정의 변경 훅, 동기화 요청 시점
  - `test_permission_matrix.py` — A1~A9, B1~B6 × 역할(관리자·정의 담당자·입력자·다른 팀 구성원·비소속 읽기·비활성·인증 없음), 거부된 요청이 데이터를 바꾸지 않음
  - `test_static_acl.py` — 정적 표 `datasets`·`dataset_columns`의 `bi_app` 권한(표·열 단위 카탈로그 대조 + 실제 거부 42501), `bi_readonly` 접근 불가, 제약·복합 FK
  - `test_ddl.py`, `test_ddl_names.py` — 이름 규칙, 허용 목록 밖 거부(실행 전; 표 생성의 외래키·유일 제약·계산 열 거부 포함, 모든 DDL 보조 함수가 이름 규칙을 거침), `text()`·`exec_driver_sql`·ddl 모듈 밖 DDL이 없음을 코드에서 검사, 실제 DB에서 표·열·기준 날짜 열 규칙, 롤백 시 표가 남지 않음, `bi_app`이 `public`에 만들 수 없음, 시작 자가 점검이 새 객체를 허용, `alembic check`, `downgrade 0004` 뒤 `ds_*` 보존
  - `test_dataset_concurrency.py` — 동시 정의 변경(`DEFINITION_VERSION_MISMATCH`), 락 대기 초과(`DEFINITION_BUSY`), `FOR NO KEY UPDATE`가 읽기·FK 자식 INSERT를 막지 않음, `FOR SHARE` 상호 대기와 굶음 관찰(앞지름을 단정으로 고정), 이름 변경 중 FK 자식 INSERT 대기 관찰, 같은 이름 동시 등록
  - `test_dataset_rules.py` — 열 이름·태그·`rules` 정리(JSON 부동소수점·큰 정수 거부 회귀 포함), 구조 해시
  - `test_migrations.py`, `test_roundtrip_tools.py` — 0004·0005 revision 규칙(고정 SQL, `downgrade` 구현, `DROP_APPROVED`)
  - `test_formula_api.py`, `test_formula_views_pg.py` — 정의 변경 훅이 뷰를 만들고 `def_hash`를 기록하는 동작(`formula-column` 8절)
- 마이그레이션 왕복(**새** 빈 `postgres-test`에서): `python -m migrations.roundtrip`, `alembic check` (`skills/local-environment/SKILL.md`).
- 수동 확인: 위 curl 순서 실행 뒤 `psql`(`bi_owner`)로 `\d bi_data.ds_<번호>`에서 `row_id`와 `c_<번호>` 열, 기준 날짜 열의 `NOT NULL`·`ck_ds_<번호>_period`·`ux_ds_<번호>_period`를 본다.

- 프런트 자동 시험:
  - `cd frontend && npm run typecheck && npm run lint && npm test && npm run build` (fetch 모의, 실제 백엔드 없음)
  - 시험 위치: `src/features/dataset/dataset.test.tsx`(S2 목록·필터·쪽 이동·정의 담당자 버튼 조건, S3 폼 검증·POST 본문·이동·오류), `src/features/dataset/workspace.test.tsx`(S4 골격, 열 추가/수정 본문과 `expected_version`, 이름 즉시 검사, 데이터셋 설정, 버전 충돌·BUSY, 읽기 전용), `src/features/dataset/rules.test.ts`(열 이름·태그 검사, 십진 문자열 비교, rules <-> 입력칸 변환), `src/errors.test.ts`(코드별 문구). 시험용 가짜 서버는 `src/features/dataset/test-server.ts`(계약대로 `expected_version`을 확인).
  - 수동: 정의 담당자와 입력자 신원으로 번갈아 열어 버튼·읽기 전용 차이를 확인하고, 두 브라우저에서 같은 데이터셋에 열을 동시에 추가해 버전 충돌 안내와 자동 재로딩을 확인한다.

## 9. 연관 Skill
- `permission-management`: 팀·소속·역할(정의 담당자 판정), `/api/me`의 `memberships`, 인증 스텁, 실제 DB 시험 방법
- `permission-management`(FU-2a 감사 기록 조회): 데이터셋 만들기·수정(B2·B4)과 열 추가·수정(B5·B6)은 성공하고 실제로 바뀐 경우에만 감사 기록(`dataset.create`·`dataset.update`·`column.add`·`column.update`)이 한 건 남는다. 검증 규칙 값은 기록되지 않고 `rules_changed`만 남는다. 관리자가 5-1절 API로 조회한다.
- `data-entry`(FU-1c): 이 정의의 열 타입·필수·범위 규칙으로 행을 입력·검증하고, 행 쓰기가 `datasets` 행을 `FOR SHARE`로 잡아 `expected_version`을 확인한다
- `formula-column`(FU-1d): 계산 열(`kind=formula`)을 만들고 정의 변경 훅에서 `formulas`·`formula_deps`, `dv_`·`de_` 뷰, `def_hash`(뷰 정의 해시)를 맡는다. 태그 변경의 순환 재검사(`FORMULA_CIRCULAR`)도 이 훅이다
- `dashboard-link`(FU-1e): 정의가 바뀐 뒤 `DatasetSyncPort`로 Superset 가상 데이터셋 이름·열 표시 이름을 동기화한다. 열 표시 이름은 Superset에서 `c_<번호>` 열의 이름이 되고(전체 열 한 번에 갱신), 이름 변경(B4)·열 추가(B5)·열 이름 변경(B6)도 같은 경로로 반영된다
- `admin-cleanup`: 잘못 만든 열·데이터셋을 지우는 수동 절차(FU-1에는 삭제 API가 없다)
- `local-environment`: 마이그레이션 왕복, 시작 자가 점검 대응
