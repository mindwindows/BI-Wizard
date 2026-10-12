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

### B5 `POST /api/datasets/{id}/columns` (원본 열만, 계산 열은 FU-1d)
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
| `number` | `min`, `max`, `decimals` | `min`·`max`는 십진 문자열 또는 JSON 숫자(저장·응답은 `"100.5"` 같은 **십진 문자열**, 05 §1의 number 값 표현과 같다). 유한한 값, 38자리 이하, `min ≤ max`. `decimals`는 0~10 정수 |
| `text` | `max_length` | 1~10,000 정수 |
| `date` | `min`, `max` | `YYYY-MM-DD`, `min ≤ max` |
| `choice` | `options` | **필수.** 문자열 목록 1~100개, 각 1~100자·제어문자 불가·중복 불가(앞뒤 공백 제거) |
| `boolean` | 없음 | 키가 있으면 422 |
빈 `rules`(`{}` 또는 `null`)는 저장하지 않는다(`null`).

### B6 `PATCH /api/datasets/{id}/columns/{col_id}` (보낸 필드만 바꾼다)
`expected_version`(필수), `display_name?`, `required?`, `rules?`, `tag?`(`null`이면 지움), `position?`. **`type`·`kind`는 바꿀 수 없다**: 현재와 다른 값을 보내면 422 `COLUMN_LOCKED`(같은 값이면 무시). 다른 타입이 필요하면 새 열을 추가한다. 계산 열(`formula`)에는 `required: true`와 `rules`를 줄 수 없다(422). 이름을 바꿔도 원본 표의 열 이름(`c_<번호>`)은 그대로다.

### 목록 B1 `GET /api/datasets`
`team_id?`, `limit`(기본 50, 1~200), `offset`. 정렬: **내 소속 팀의 데이터셋이 먼저**, 다음 팀 이름, 데이터셋 이름.

## 4. 출력
- 공통 형태(05 §1):
  - Column `{id, display_name, type, kind, required, rules, tag, position}`
  - Dataset `{id, team_id, name, date_unit, base_date_column_id, status, def_version, created_by{id, display_name}, created_at}` (`created_at`은 `+09:00` ISO 8601)
- B1 200 `{items[Dataset], total, limit, offset}` (동기 상태는 없다: Superset 동기 상태는 FU-1e의 `GET /api/superset/datasets`에서 화면이 결합한다).
- B2 201, B4 200, B3 200: Dataset + `team{id, code, name}` + `columns[Column]`(순서: `position`, `id`) + `permissions{define, enter}`(내 권한. 관리자라도 소속이 없으면 둘 다 false).
- B5 201, B6 200: `{column, def_version}` (새 정의 버전).
- 오류(`{"error": {"code", "message", "details", "request_id"}}`, 한국어 `message`):
  - 409 `DEFINITION_VERSION_MISMATCH` + `details.current_version` — 다른 사람이 먼저 정의를 바꿈. 새로 읽고 다시 한다.
  - 409 `ALREADY_EXISTS` + `details.field`(`name`: 팀 안 데이터셋 이름, `display_name`: 데이터셋 안 열 이름)
  - 422 `VALIDATION_ERROR` + `details.fields[{field, code, message}]` — 필드 코드 `REQUIRED`·`TOO_LONG`·`BAD_FORMAT`·`RESERVED`·`OUT_OF_RANGE`. 규칙 오류의 `field`는 `rules.min`처럼 키까지 가리킨다. 기준 날짜 열이 원본 `date` 열이 아니거나 다른 데이터셋의 열이면 `base_date_column_id` `BAD_FORMAT`.
  - 422 `DATASET_HAS_ROWS` — 행이 있어 날짜 단위·기준 날짜 열을 바꿀 수 없음
  - 422 `COLUMN_LOCKED` — 열 `type`·`kind` 변경 시도
  - 503 `DEFINITION_BUSY` + `details.retry_after`(2초) — 정의 변경 락 대기가 1초를 넘음. 같은 요청을 다시 보내면 된다.
  - 403 `FORBIDDEN`, 404 `NOT_FOUND`(없는 데이터셋·열, 다른 데이터셋의 열), 401/403 인증 오류
- 저장 위치:
  - `datasets`(`def_version`, 정의 해시 `def_hash`), `dataset_columns`(`public`, `bi_owner` 소유, 06 §2).
  - 원본 표 `bi_data.ds_<데이터셋 번호>`: `row_id`(bigint identity, PK)와 원본 열 `c_<열 번호>`(`text`→`text`, `number`→`numeric`, `date`→`date`, `boolean`→`boolean`, `choice`→`text`, 모두 NULL 허용 = 빈 칸은 미입력). 소유자는 `bi_app`, `bi_readonly`(Superset)는 `SELECT`만.
  - **기준 날짜 열**을 지정하면 그 열이 `NOT NULL`이 되고 CHECK `ck_ds_<번호>_period`(기간의 첫날: 월 단위면 1일, 연 단위면 1월 1일. `timestamp` 변환을 거쳐 세션 시간대와 무관)와 유일 인덱스 `ux_ds_<번호>_period`(같은 기간 하나)가 걸린다. 해제하거나 단위를 바꾸면 풀리고 다시 걸린다. 기준 날짜 열은 입력 때 필수로 취급한다(`required` 플래그 값은 그대로 두고 입력 단위가 `REQUIRED`로 판정, FU-1c).
- 부수 효과: 정의가 **실제로 바뀌고 커밋된 뒤에만** `DatasetSyncPort.request_dataset_sync`를 백그라운드로 요청한다(Superset 가상 데이터셋 동기화, 구현은 FU-1e이고 지금은 아무것도 하지 않는 기본 구현). 요청이 실패해도 응답은 그대로다. 아무것도 바뀌지 않은 PATCH(같은 값)는 버전을 올리지 않고 동기화도 요청하지 않는다.

### 정의 버전과 정의 변경 진입점 (동시 편집)
- 정의를 바꾸는 모든 요청(B4~B6, 이후 D4·D5)은 한 함수(`backend/app/dataset/definition.py`)를 지난다: ① `lock_timeout 1초` ② `datasets` 행을 `FOR NO KEY UPDATE`로 잠금(읽기는 막지 않는다) ③ `expected_version` 확인 ④ 열 변경(정의 행 + 원본 표 DDL) ⑤ 정의 변경 훅(1b에는 등록된 훅 없음, FU-1d의 formula가 등록해 같은 트랜잭션에서 뷰를 만든다) ⑥ `def_version + 1`과 `def_hash` 기록 후 커밋. 중간에 실패하면 모두 롤백된다(원본 표 DDL 포함).
- `def_hash`는 FU-1d 전에는 정의 구조(열 번호·종류·타입) 해시다. 표시 이름·필수·규칙·순서는 해시에 들어가지 않는다.
- 같은 `expected_version`으로 동시에 요청하면 하나만 성공하고 나머지는 `DEFINITION_VERSION_MISMATCH`다.
- 행 쓰기(FU-1c)는 같은 행을 `FOR SHARE`로 잡아 정의 변경과 서로 기다린다. `FOR SHARE` 보유자가 이어지면 정의 변경이 순서를 못 얻을 수 있다(굶음): 시험으로 확인했고(`test_continuous_for_share_holders…`) 이 경우에도 1초 뒤 `DEFINITION_BUSY`로 끝나며 무한 대기는 없다.

## 5. 실행 방법
### 사람(화면)
화면(S2 데이터셋 목록, S3 데이터셋 만들기, S4 작업공간·Inspector의 열 추가·수정·데이터셋 설정, 오류 문구)은 프런트 단위(`frontend/src/features/dataset/`)에서 정리한다. 이 자리에 frontend-dev가 쓴 화면 절차를 합친다 — **합치기 대기**(`_workspace/fu1b-frontend-skill-notes.md`).

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
- UI: S2 `/datasets`, S3 `/datasets/new`, S4 `/datasets/<번호>`(Inspector 포함). 구현 `frontend/src/features/dataset/` (화면 설명은 5절의 합치기 대기 부분).
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
| backend가 시작하지 않음 | 시작 자가 점검: `bi_data`에 허용 밖 객체(함수·독립 시퀀스·타입 등) | `docker compose logs backend`의 메시지. 누가 만들었는지 확인 후 `admin-cleanup` 방식으로 정리 |
| `ds_*`에 행/열이 정의와 어긋남 | 수동 SQL로 바꿈 | 정의 변경은 API로만 한다. 어긋나면 `datasets`·`dataset_columns`와 `bi_data` 열 목록을 대조 |

## 8. 검증 방법
- DB 없이(SQLite, `docker build --target test backend`와 같다): `cd backend && pytest`. 데이터셋 API 시험은 SQLite에서 원본 표 생성·열 추가까지 실제로 실행하고 기준 날짜 열 규칙 DDL은 호출 기록으로 대신한다.
- 실제 PostgreSQL(권장, `skills/permission-management/SKILL.md`의 "검증 방법" 절차로 tmpfs `postgres-test` 준비): 같은 `pytest`가 `pg` 변형을 포함해 돈다. 시험 실행 환경에 `REQUIRE_PG=1`을 주면 PostgreSQL 환경이 없을 때 건너뛰지 않고 실패한다.
- 시험 위치(`backend/tests/`):
  - `test_dataset_api.py` — B1~B6 동작, 이름·규칙·태그 검증, 버전 충돌, 등록 + 원본 표 생성 원자성(실패 시 정의 행과 표가 함께 롤백), 정의 변경 훅, 동기화 요청 시점
  - `test_permission_matrix.py` — A1~A9, B1~B6 × 역할(관리자·정의 담당자·입력자·다른 팀 구성원·비소속 읽기·비활성·인증 없음), 거부된 요청이 데이터를 바꾸지 않음
  - `test_static_acl.py` — 정적 표 `datasets`·`dataset_columns`의 `bi_app` 권한(표·열 단위 카탈로그 대조 + 실제 거부 42501), `bi_readonly` 접근 불가, 제약·복합 FK
  - `test_ddl.py`, `test_ddl_names.py` — 이름 규칙, 허용 목록 밖 거부(실행 전), `text()`·`exec_driver_sql`·ddl 모듈 밖 DDL이 없음을 코드에서 검사, 실제 DB에서 표·열·기준 날짜 열 규칙, 롤백 시 표가 남지 않음, `bi_app`이 `public`에 만들 수 없음, 시작 자가 점검이 새 객체를 허용, `alembic check`, `downgrade 0004` 뒤 `ds_*` 보존
  - `test_dataset_concurrency.py` — 동시 정의 변경(`DEFINITION_VERSION_MISMATCH`), 락 대기 초과(`DEFINITION_BUSY`), `FOR NO KEY UPDATE`가 읽기·FK 자식 INSERT를 막지 않음, `FOR SHARE` 상호 대기와 굶음 시나리오, 같은 이름 동시 등록
  - `test_dataset_rules.py` — 열 이름·태그·`rules` 정리, 구조 해시
  - `test_migrations.py`, `test_roundtrip_tools.py` — 0004 revision 규칙(고정 SQL, `downgrade` 구현, `DROP_APPROVED`)
- 마이그레이션 왕복(**새** 빈 `postgres-test`에서): `python -m migrations.roundtrip`, `alembic check` (`skills/local-environment/SKILL.md`).
- 수동 확인: 위 curl 순서 실행 뒤 `psql`(`bi_owner`)로 `\d bi_data.ds_<번호>`에서 `row_id`와 `c_<번호>` 열, 기준 날짜 열의 `NOT NULL`·`ck_ds_<번호>_period`·`ux_ds_<번호>_period`를 본다.

## 9. 연관 Skill
- `permission-management`: 팀·소속·역할(정의 담당자 판정), `/api/me`의 `memberships`, 인증 스텁, 실제 DB 시험 방법
- `data-entry`(예정, FU-1c): 이 정의의 열 타입·필수·범위 규칙으로 행을 입력·검증하고, 행 쓰기가 `datasets` 행을 `FOR SHARE`로 잡아 `expected_version`을 확인한다
- `formula-column`(예정, FU-1d): 계산 열(`kind=formula`)을 만들고 정의 변경 훅에서 `dv_`·`de_` 뷰와 `def_hash`(뷰 DDL 해시)를 맡는다. 태그 변경의 순환 재검사(`FORMULA_CIRCULAR`)도 이 훅이다
- `dashboard-link`(예정, FU-1e): 정의가 바뀐 뒤 `DatasetSyncPort`로 Superset 가상 데이터셋 이름·열 표시 이름을 동기화한다
- `admin-cleanup`: 잘못 만든 열·데이터셋을 지우는 수동 절차(FU-1에는 삭제 API가 없다)
- `local-environment`: 마이그레이션 왕복, 시작 자가 점검 대응
