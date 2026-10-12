---
name: data-entry
description: 데이터셋에 한 기간 = 한 행으로 값을 입력하는 기능. 행 조회, 새 행 저장, 칸 단위 수정(동시 수정 충돌 감지), 엑셀에서 복사한 여러 행 붙여넣기(충돌 시 전부 취소)를 다룬다. "행 추가", "값 입력", "칸 수정", "엑셀 붙여넣기", "다른 사람이 먼저 바꿨대요", "같은 기간이 이미 있어요", "붙여넣기가 413" 같은 요청에 사용한다. 화면(S4 입력 그리드)은 프런트 단위에서 붙고 이 문서의 5절 "사람(화면)"에 합친다.
---

# data-entry — 입력 그리드(행 조회·입력·수정·붙여넣기)

## 1. 목적
팀 사용자가 데이터셋의 원본 열(`dataset-definition`에서 정의한 열)에 값을 한 기간 = 한 행으로 입력한다. 모든 사용자는 다른 팀 데이터도 읽을 수 있고, 입력은 그 데이터셋 팀의 입력자·정의 담당자만 한다. 두 사람이 같은 칸이나 같은 기간을 동시에 건드려도 한쪽 값이 말없이 사라지지 않게, 칸 단위 값 비교로 충돌을 알려 준다. 엑셀에서 복사한 여러 행은 한 번에 붙여넣고, 하나라도 충돌하면 아무것도 반영하지 않는다.

## 2. 사용 조건 / 사전 요구사항
- 로그인: 모든 API가 인증을 거친다(`permission-management`, 개발에서는 스텁).
- 권한(06 §4-1):
  - **읽기(C1): 인증된 활성 사용자 누구나**, 다른 팀 포함.
  - **입력(C2~C4): 그 데이터셋 팀의 `entry` 또는 `definer`.** 관리자(`is_admin`)여도 그 팀 소속이 아니면 403 `FORBIDDEN`이다(필요하면 관리자가 자기를 그 팀에 소속시킨다). 다른 팀 구성원·소속 없는 사용자는 403, 비활성 사용자는 403 `USER_INACTIVE`, 신원 없음은 401. 권한 검사는 본문 검증·크기 검사보다 먼저다.
- 실행 상태: `local-environment` 통과, `migrate`가 `0004`까지 적용. **1c는 새 revision이 없다**(`ds_<번호>` 행 읽기·쓰기는 DML이라 마이그레이션 대상이 아니다).
- 선행 데이터: 팀·소속(`permission-management`), 데이터셋과 원본 열(`dataset-definition`). 열이 없는 데이터셋에도 빈 행은 저장할 수 있다(필수 열이 없으면 `cells: {}`로 빈 행 생성을 허용하는 것은 의도된 동작이다).
- 임시 행(draft)은 서버에 없다. 필수 칸을 다 채우기 전의 새 행은 화면 메모리에만 있고, 다 채우면 C2 한 번(붙여넣기 새 행은 C4 한 번)으로 저장한다. 새로고침하면 미저장 행은 사라진다.

## 3. 입력
공통: JSON UTF-8, snake_case. 정의되지 않은 필드는 422. 모든 쓰기에 `expected_version`(읽은 `def_version`)이 필요하다: 다른 사람이 그 사이 열을 바꿨으면 409 `DEFINITION_VERSION_MISMATCH`(`details.current_version`)이고 아무것도 쓰지 않는다. `cells`의 키는 열 번호 글자(`"12"`)다.

### 값 해석 규칙 (서버가 항상 재검증, 화면 검사는 편의)
빈 입력(`null`, 빈 글자, 공백뿐인 글자)은 **미입력(NULL)**이다. 필수 열(`required`)과 **기준 날짜 열**(필수로 취급)을 비우면 `REQUIRED`다.
| 열 타입 | 받는 입력 | 위반 코드(`details.fields[].code`) |
| --- | --- | --- |
| `text` | 글자. NFC 정규화·앞뒤 공백 제거. 제어·서식 문자(개행·탭·NUL·`U+200B`·`U+202E` 등) 불가. 길이는 `rules.max_length`, 없으면 1만자 | `BAD_FORMAT`, `TOO_LONG` |
| `number` | **십진 문자열**(`"1234.50"`, `"-5"`) 또는 JSON 정수. JSON 부동소수점(`1.5`)·지수 표기(`1e3`)·`NaN`·`Infinity`·천 단위 쉼표·`.5`·38자리 초과 불가. `rules.decimals`(뒤 0 제외 소수 자릿수)·`min`·`max` | `BAD_FORMAT`, `OUT_OF_RANGE`(범위·자릿수) |
| `date` | `YYYY-MM-DD`(없는 날짜 불가). **기준 날짜 열**은 날짜 단위가 월이면 1일, 연이면 1월 1일만. `rules.min`·`max` | `BAD_FORMAT`, `NOT_PERIOD_START`, `OUT_OF_RANGE` |
| `boolean` | JSON `true`/`false` 또는 글자 `true`·`false`·`1`·`0`·`y`·`n`·`yes`·`no`·`예`·`아니오`·`참`·`거짓`(대소문자 무시) | `BAD_FORMAT` |
| `choice` | `rules.options` 안의 글자(NFC·공백 제거 뒤 정확히 일치, 대소문자 구분) | `NOT_IN_OPTIONS` |
계산 열(`kind=formula`)은 쓸 수 없다(`READ_ONLY`). 이 열 번호가 아닌 키는 `BAD_FORMAT`이다. 같은 기준 날짜 열 규칙: 기준 날짜 열이 없는 데이터셋은 같은 날짜 행이 여러 개여도 된다.

### C1 `GET /api/datasets/{id}/rows`
`order=asc|desc`(기본 `asc`, 기준 날짜 열 기준이고 없으면 `row_id`, 같으면 `row_id`로 안정화), `limit`(기본 50, 1~200), `offset`. 잘못된 값은 422.

### C2 `POST /api/datasets/{id}/rows`
`{expected_version, cells{"<열 번호>": 값}}`. 원본 열만, 필수 열(기준 날짜 열 포함)은 전부 있어야 한다.

### C3 `PATCH /api/datasets/{id}/rows/{row_id}`
`{expected_version, changes[{column_id, expected, value}]}` (`changes` 1개 이상).
- `expected`는 **키가 반드시 있어야** 한다: 화면이 읽었던 그 칸의 값(빈 칸이었으면 `null`). 키를 빠뜨리면 422 `REQUIRED`(`changes.0.expected`)다. 가드를 우회하지 못하게 하기 위해서다. `value`도 키가 필수다(`null` = 비움).
- 한 요청의 모든 칸이 가드다. 하나라도 지금 값이 `expected`도 `value`도 아니면 **전체 취소**한다. 같은 열을 두 번 보내면 422.
- 이전 값과 같은 값(`value`가 `expected`와 같음)은 규칙 위반이어도 오류가 아니다(규칙을 바꾸기 전에 들어간 값은 그대로 둔다).

### C4 `POST /api/datasets/{id}/rows/paste`
`{expected_version, column_ids[], rows[{row_id, expected[], values[]}]}`.
- `column_ids`: 붙여넣을 원본 열(중복·계산 열·없는 열 불가). 각 행의 `values`(와 `expected`)는 이 순서와 같은 길이다. 값은 문자열 또는 `null`이고 서버가 열 타입으로 해석한다(파서는 화면 몫).
- `row_id: null` = 새 행(`expected`는 무시). **필수 열(기준 날짜 열 포함)이 모두 `column_ids` 안에 있고 값이 있어야** 한다.
- `row_id: 정수` = 기존 행. `expected[]`가 **필수**(칸마다 화면이 가진 이전 값, 빈 칸 `null`)이고 같은 행을 두 번 보낼 수 없다.
- **이전 값과 같은 칸(`value` = `expected`)은 쓰지도, 가드로 쓰지도 않는다.** 바뀌는 칸만 가드이므로, 같은 행의 다른 칸을 남이 고쳐도 내가 바꾸지 않는 칸 때문에 충돌하지 않는다. 바뀐 칸이 하나도 없는 행은 `updated`에 세지 않는다.
- **기존 행의 기준 날짜 열 값은 붙여넣기로 바꿀 수 없다**(`READ_ONLY`; 같은 값이면 무시). 기간 이동은 C3 단건이다.
- 처리 순서(고정): 기존 행 `row_id` 오름차순 갱신 → 새 행 기간 오름차순 삽입(기준 날짜 열이 없으면 입력 순). 모든 붙여넣기가 같은 순서로 잠금을 잡아 교착을 막는다.
- **상한(코드 상수, 새 환경변수 아님): 5,000행, 요청 본문 1MiB.** 넘으면 413 `PAYLOAD_TOO_LARGE`(`details.limit`: 행 수 초과면 5000, 크기 초과면 1048576, 문구로 구분)이고 아무것도 쓰지 않는다. 크기는 `Content-Length`와 실제 읽은 바이트로 센다.

## 4. 출력
- 행(Row): `{row_id, cells{"<열 번호>": 값 또는 null}, errors{"<열 번호>": "E1"}}`. 값 표현(05 §1): number는 **십진 문자열**(`"1234.50"`, PostgreSQL이 저장한 자릿수 그대로), 미입력은 `null`, date는 `YYYY-MM-DD`(월·연 단위도 기간 첫날), boolean은 `true`/`false`, text·choice는 글자. 모든 열(계산 열 포함)이 `cells`에 있다. 계산 열 값과 `errors`는 `RowViewPort`(`backend/app/core/ports.py`)가 준다. **1c의 기본 구현은 계산 열 값이 없고 `errors`가 항상 `{}`**이며 FU-1d(`formula-column`)의 formula 모듈이 교체한다. 계산 열이 있을 때만 포트를 부르고 같은 트랜잭션으로 읽는다(방금 쓴 행도 보인다).
- C1 200 `{def_version, items[Row], total, limit, offset}`.
- C2 201 `{row, def_version}`. C3 200 `{row, def_version}`.
- C4 200 `{updated, created, created_rows[{index, row_id}], def_version}` (`index`는 요청 `rows`의 순서, 0부터).
- `def_version`은 현재 정의 버전이다(행 쓰기는 버전을 올리지 않는다).
- 저장 위치: `bi_data.ds_<번호>`(`row_id` bigint identity PK + 원본 열 `c_<열 번호>`). 기준 날짜 열이 있으면 같은 기간은 한 행(유일 인덱스 `ux_ds_<번호>_period`).
- 오류(`{"error": {"code", "message", "details", "request_id"}}`):
  - 422 `VALIDATION_ERROR` + `details.fields[]`: C2는 `{field: "cells.<열 번호>", code, message}`, C3는 `field`가 `changes.<순번>.value|expected|column_id`, C4는 `{row_index, column_id, code, message}` 또는 `{field: "rows.<순번>.values|expected|row_id" / "column_ids.<순번>"}`. **모든 위반을 한 번에 모아** 돌려준다(처음 200건까지). 입력 값은 응답에 되돌려 쓰지 않는다: 알 수 없는 `cells` 키도 ASCII 숫자(40자 이하)만 `cells.<숫자>`로 보이고 그 밖(글자 키, 음수, 너무 긴 숫자)은 `cells.invalid`다. 붙여넣기 엔드포인트는 원시 요청 본문을 직접 읽지만 OpenAPI에는 `openapi_extra`로 `PasteBody` 스키마를 싣는다. 깨진 JSON은 `field`가 오류 위치 번호 문자열이다.
  - 404 `NOT_FOUND`(없는 데이터셋), 404 `ROW_NOT_FOUND`(C3 없는 행).
  - 409 `DEFINITION_VERSION_MISMATCH` + `details.current_version`.
  - 409 `CELL_CONFLICT`(C3) + `details.conflicts[{row_id, column_id, current}]`: 충돌한 칸과 그 칸의 **지금 값**(응답 표현). 충돌 없는 칸도 반영되지 않았다.
  - 409 `PERIOD_CONFLICT`(C2, C3 기간 이동) + `details.conflicts[{row_id, column_id, current}]`: `row_id`는 그 기간을 이미 차지한 행, `column_id`는 기준 날짜 열, `current`는 그 기간.
  - 409 `PASTE_CONFLICT`(C4) + `details.conflicts[{row_index, row_id, column_id, kind, current}]`, `kind`: `"cell"`(칸 값이 바뀜, `current`=지금 값), `"period"`(새 행의 기간이 이미 있거나 요청 안에서 겹침, `row_id`=그 기간의 기존 행, `column_id`=기준 날짜 열, `current`=기간), `"row_missing"`(행이 없음, `column_id`·`current`는 `null`). 첫 건에서 멈추지 않고 모아서(처음 1,000건까지) 돌려주며 **전부 취소**한다.
  - 413 `PAYLOAD_TOO_LARGE`(C4). 앞단 nginx의 기본 요청 상한(1m)이 먼저 413을 내면 **JSON이 아닌 HTML**일 수 있다(프런트가 둘 다 같은 안내로 처리한다).
  - 503 `WRITE_BUSY` + `details.retry_after`(2초): 락 대기 3초 초과 또는 교착. 같은 요청을 다시 보내면 된다(재시도 가능).

## 5. 실행 방법
### 사람(화면)
#### 그리드 보기 (S4 가운데, `/datasets/<번호>`)
1. 데이터셋 목록에서 이름을 눌러 작업공간을 연다. 가운데 표가 입력 그리드다(AG Grid Community). 열은 Inspector가 읽은 열 정의 순서(위치 순)이고, 맨 앞의 고정 열 "기간 / 행 번호"에 `2026-03-01 · #12`(기준 날짜 열이 있으면 기간 + 행 번호, 없으면 `#12`)가 나온다. 기준 날짜 열의 머리글에는 "(기간)"이 붙는다. 머리글을 누르면 그 열이 Inspector에 열린다.
2. 값 표시: 숫자는 쉼표 서식에 오른쪽 정렬이고, 소수 자릿수 규칙이 있으면 끝자리 0을 채워 보여 준다(`1234.5` -> `1,234.50`). 값은 문자열 그대로라 큰 수도 정밀도를 잃지 않는다. **빈 칸(아직 입력 안 함)은 빗금 배경의 빈 칸이고, 값 0은 `0`으로 보인다.**
3. 계산 열(수식)은 이탤릭·회색 배경의 읽기 전용이다. 계산이 실패한 칸은 붉은 배경의 "오류"로 보이고 칸 위에 마우스를 올리면 이유가 나온다(E1 0으로 나눔, E2 글자 길이 범위, E3 날짜 범위). 오류 칸과 빈 칸은 다르게 보인다. (계산 열은 단위 1d부터 생긴다. 지금은 표시 규칙만 준비돼 있다.)
4. 위쪽 도구줄: "정렬"(최근 순이 기본, 과거 순), "한 쪽에"(50·100·200행), "이전 쪽/다음 쪽", 범위 표시(`1–50 / 전체 120행`), "새로 읽기", "새 행 추가". 쪽 이동은 서버에 `limit/offset`을 보내 다시 읽는 방식이다(서버 사이드 행 모델 없음).
5. 상태: 불러오는 중 / 행이 없음("아직 입력된 행이 없습니다") / 읽기 실패(쉬운 문구 + "다시 불러오기").

#### 읽기 전용
- 서버 응답의 `permissions.enter`가 false(입력 권한이 없음)이면 표 위에 "읽기 전용입니다…" 안내가 나오고, 칸 편집·붙여넣기·새 행 추가·맨 아래 입력 줄이 모두 없다. 이것은 편의이며 최종 방어선은 서버 권한 검사다(`FORBIDDEN` 403은 "이 작업을 할 권한이 없습니다"로 보인다).

#### 칸 편집 (C3)
1. 칸을 두 번 누르거나 칸을 선택하고 Enter(또는 글자 입력)로 편집을 시작한다. Enter는 저장하고 아래 칸으로, Esc는 취소, Tab은 다음 칸이다. 선택 목록·예/아니오 열은 목록에서 고른다(빈 항목을 고르면 미입력).
2. 확정하면 `PATCH /api/datasets/{id}/rows/{row_id}`에 `{expected_version, changes:[{column_id, expected, value}]}`를 보낸다. `expected`는 편집 전 화면 값(빈 칸은 `null`, 숫자는 서버가 준 문자열 그대로), `value`는 새 값이다. 값이 그대로면 보내지 않는다.
3. 보내는 동안 새 값이 흐리게 먼저 보이고(낙관적 표시), 성공하면 서버가 돌려준 행으로 바뀐다. 실패하면 원래 값으로 되돌아간다. 숫자에 글자를 넣는 것처럼 분명히 틀린 입력은 서버에 보내기 전에 "확인이 필요한 칸"에 쉬운 문구로 나온다.

#### 새 행 (C2, 임시 행)
- 새 행은 **서버에 저장하지 않고 화면 메모리에만** 둔다. 두 가지로 만든다: (1) 표 맨 아래 "＋ 새 행 입력" 줄의 아무 칸에 입력, (2) "새 행 추가" 버튼(새 행의 첫 입력 칸에서 바로 편집 시작).
- "저장 전 새 행" 목록에 아직 채워야 할 필수 칸이 나온다(기준 날짜 열은 필수로 본다). **필수 칸을 모두 채우는 순간 `POST /api/datasets/{id}/rows`를 한 번 부르고**, 성공하면 임시 행이 사라지고 표를 다시 읽는다. 값이 있는 입력 칸만 보낸다.
- **저장 전에 새로고침하거나 다른 곳으로 이동하면 임시 행은 사라진다**(안내가 화면에 있다). 다른 사람에게도 보이지 않는다. "버리기"로 지울 수 있다.
- 같은 기간의 행이 이미 있으면 `PERIOD_CONFLICT`: "이미 같은 기간의 행이 있습니다…" 안내와 함께 임시 행과 입력한 내용이 남는다. 기간을 고치면 다시 저장된다("다시 저장" 버튼도 있다).

#### 엑셀 붙여넣기 (C4)
1. 엑셀에서 범위를 복사한다. 그리드에서 **붙여넣기를 시작할 칸을 눌러 선택**하고 Ctrl+V. (칸을 편집하는 중이거나 다른 입력창에 커서가 있으면 그 입력창 안의 글자 붙여넣기로 동작한다.) 붙여넣기는 `document` 수준에서 받아, 그리드 밖 글자(안내 문단 등)가 선택된 채로 칸을 눌러도 동작한다. 조건은 그리드 안에 DOM 포커스가 있거나 이벤트 대상이 그리드 안일 때뿐이고, 입력창·편집기가 대상이면 가로채지 않는다.
2. "붙여넣기 확인" 창이 `N줄 × M열을 "열 A" ~ "열 B" 칸에… 기존 행 K개를 덮어쓰고 새 행 J개를 추가합니다`를 보여 준다. "붙여넣기 적용"(Enter)을 누를 때까지 서버에 아무것도 보내지 않는다. Esc나 "취소"로 닫는다.
3. 채우는 규칙: 선택 칸부터 아래/오른쪽으로 열 순서대로 채운다. 쪽의 마지막 행을 넘는 줄은 새 행이 된다(**마지막 쪽에서만**; 아니면 거부 안내). 맨 아래 "새 행 입력" 줄에서 시작하면 전부 새 행이다. 기존 행은 `row_id`와 화면 이전 값(`expected[]`)을 함께 보내고, 새 행은 `row_id=null`이다. 값은 문자열 또는 `null`(빈 칸) 그대로 보내고 해석은 서버가 한다. 공백은 자르지 않는다.
4. 서버에 보내기 전에 막는 경우(모두 "붙여넣을 수 없습니다" 안내, 아무것도 저장 안 됨): 5,000행 초과, 요청 1MiB 초과, 계산 열에 걸침, **기존 행의 기준 날짜 열(기간)을 바꾸려 함**(앞뒤 공백을 뺀 글자가 저장된 `YYYY-MM-DD`와 정확히 같으면 통과 — 서버도 같은 값은 무시하고 `values`에 그대로 실어 보낸다. 기간 이동은 칸 편집으로), **새 행에 기준 날짜 열 값이 없음**(열이 붙는 범위에 없거나 빈 칸이면 "새 행에는 기준 열 값이 필요합니다"; 서버 REQUIRED와 같은 취지), 입력이 4Mi 문자를 넘음(파싱 전 거부), 열이 모자람, 기존 행에 걸치는 줄의 칸 수가 모자람, 모호한 숫자·날짜(`1,234.50`, `12.5%`, `₩1,000`, `2026년 10월 11일`은 쉼표·단위 없는 `1234.5`, `2026-10-11` 형식으로), 닫히지 않은 따옴표, NUL 문자, 시작 칸을 고르지 않음.
5. 결과: 성공이면 "N행을 고치고 M행을 새로 추가했습니다"(`updated`/`created`) 후 표를 다시 읽는다.

#### 충돌과 해결
- **칸 편집 충돌(`CELL_CONFLICT`)**: 그 칸에 서버의 현재 값을 보여 주고(주황 테두리·"충돌") "다른 사람이 먼저 바꾼 칸" 목록에 `내 값 / 서버 값`을 나란히 보인다. "내 값으로 저장"(서버 값을 새 기준으로 다시 저장) 또는 "서버 값 유지"(내 값 버림)를 고른다.
- **붙여넣기 충돌(`PASTE_CONFLICT`)**: **전부 취소되며 부분 반영은 없다**는 안내와 충돌 목록(줄 번호, 행 번호, 열, 서버 값; 새 행의 기간 충돌과 사라진 행도 표시)이 나온다. 충돌한 기존 칸은 서버 값으로 바뀌어 강조된다. "서버 값 기준으로 다시 붙여넣기"를 누르면 같은 내용을 새 기준으로 다시 확인창부터 진행한다.
- **정의가 바뀜(`DEFINITION_VERSION_MISMATCH`)**: 누군가 열을 바꿨다. 화면이 정의를 다시 읽고 행도 다시 읽는다. 하던 입력은 저장되지 않았으니 확인 후 다시 한다.
- **바쁨(`WRITE_BUSY`/`DEFINITION_BUSY`)**: 값을 되돌리고 "다시 시도" 버튼을 보인다(자동 재시도는 하지 않는다).
- **검증 오류(422)**: 칸 편집은 칸 옆(확인이 필요한 칸 목록)에 `매출: 허용 범위를 벗어났습니다(0 ~ 100)`처럼, 붙여넣기는 `2번째 줄 · 매출: …`처럼 위치와 함께 보인다. 아무것도 저장되지 않는다.
- **크기 초과(413)**: nginx가 보내는 JSON 아닌 413도 같은 안내("한 번에 5,000행, 요청 크기 1MiB까지…").

### AI·API (스텁 로그인 예, `permission-management` 참고)
```
BASE="http://localhost:<BACKEND_PORT>${APP_BASE_PATH}/api"
curl -c jar -X PUT -H 'content-type: application/json' -d '{"login_id":"stub-entry"}' "$BASE/dev/stub-user"
# 0) 정의 읽기: columns[].id 와 def_version
curl -b jar "$BASE/datasets/<번호>"
# 1) 행 조회
curl -b jar "$BASE/datasets/<번호>/rows?order=desc&limit=20"
# 2) 새 행 (키는 열 번호 글자, 숫자는 십진 문자열)
curl -b jar -X POST -H 'content-type: application/json' \
  -d '{"expected_version": 4, "cells": {"<기준월 열>": "2026-03-01", "<매출 열>": "1234.50"}}' "$BASE/datasets/<번호>/rows"
# 3) 칸 수정: expected(읽었던 값)가 반드시 있어야 한다
curl -b jar -X PATCH -H 'content-type: application/json' \
  -d '{"expected_version": 4, "changes": [{"column_id": <매출 열>, "expected": "1234.50", "value": "1300"}]}' \
  "$BASE/datasets/<번호>/rows/<row_id>"
# 4) 붙여넣기: 새 행(row_id null)과 기존 행(expected 필수)을 한 번에
curl -b jar -X POST -H 'content-type: application/json' \
  -d '{"expected_version": 4, "column_ids": [<기준월 열>, <매출 열>], "rows": [
        {"row_id": null, "values": ["2026-04-01", "10"]},
        {"row_id": 7, "expected": ["2026-02-01", "5"], "values": ["2026-02-01", "6"]}]}' \
  "$BASE/datasets/<번호>/rows/paste"
```
- `CELL_CONFLICT`/`PASTE_CONFLICT`이면 응답의 `current`로 최신 값을 확인하고 `GET …/rows`로 다시 읽은 뒤 `expected`를 새로 맞춰 다시 보낸다.
- 잘못 입력한 행을 지우는 API는 FU-1에 없다: 칸 비우기(필수 열 제외)만 된다. 정리는 `skills/admin-cleanup`.

## 6. 관련 UI / API / command / DB
- UI: S4 작업공간의 입력 그리드(`/datasets/<번호>`, 프런트 구현은 FU-1c 프런트 단위).
- API: C1~C4(05 §2-3). 코드 `backend/app/entry/`(`router`·`service`·`repo`·`schemas`·`values`), 행 쓰기 잠금·버전 확인 `backend/app/dataset/service.py`(`lock_row_context`·`read_row_context`), 계산 열 포트 `backend/app/core/ports.py`(`RowViewPort`·`PlainRowView`·`ComputedRow`), 오류 `backend/app/core/errors.py`.
- command: 없음.
- DB: `bi_data.ds_<번호>`(`bi_app` 소유, 행 DML), `public.datasets`(행 쓰기가 `FOR SHARE`로 잡음), `public.dataset_columns`(읽기). 동적 DML도 SQLAlchemy 표현식만 쓰고 `text()`·SQL 문자열 조립이 없으며, 열 이름은 `c_<번호>` 규칙 함수(`app/ddl`)로만 만든다. `bi_app`은 자기가 만든 `ds_*`의 소유자라 DML 권한이 있고(`bi_readonly`는 `SELECT`만), 시작 자가 점검과 충돌하지 않는다(새 객체 종류 없음).

### 동시성 설계 (06 §5, 시험으로 확인한 사실)
- **본문 읽기 동안 DB 연결을 쥐지 않는다**: 입력 권한 검사(`require_dataset_entry`)가 연 트랜잭션은 검사 직후 `rollback()`으로 돌려준다(검사가 크기 검사보다 먼저인 순서는 그대로). 청크를 천천히 보내는 붙여넣기 요청이 풀(`pool_size=5`, `max_overflow=0`)을 붙들어 다른 API를 굶기지 않는다. `test_slow_paste_bodies_do_not_exhaust_the_connection_pool`(pg)이 느린 본문 8건 진행 중 `/api/me`·`/api/health/db` 응답을 단정한다(되돌리면 실패함을 확인).
- **행 쓰기 = `datasets` 행 `FOR SHARE`**: C2~C4는 첫 단계에서 그 데이터셋 행을 `FOR SHARE`로 잡고 `def_version`을 비교한다. 행 쓰기끼리는 서로 막지 않고, 정의 변경(`FOR NO KEY UPDATE`)과는 서로 기다린다. 잠금 순서는 항상 `datasets` 행 → `ds_` 행이다. 락 대기 한도는 코드 상수 3초(`ROW_WRITE_LOCK_TIMEOUT`)이고 넘기거나 교착(`40P01`)이면 503 `WRITE_BUSY`다. 읽기(C1)는 잠금이 없다.
- **칸 단위 값 비교 갱신**: `UPDATE ds_<번호> SET 칸=새값 WHERE row_id=… AND (칸 IS NOT DISTINCT FROM 이전값 OR 칸 IS NOT DISTINCT FROM 새값)`, 칸마다 반복. 영향받은 행 수(`rowcount`)가 0이면 다시 읽어 행 없음(`ROW_NOT_FOUND`/`row_missing`)과 칸 충돌을 구분한다. "이미 같은 값"은 가드 안에 포함돼 성공이다.
- **pg8000 사실(1c에서 처음 실제 PostgreSQL로 확인)**: `UPDATE`의 `rowcount`는 맞은 행 수다(불일치 0, 일치 1, NULL 가드 일치 1, 없는 행 0). `INSERT … ON CONFLICT DO NOTHING RETURNING row_id`는 넣었으면 그 행 번호를, 충돌로 건너뛰었으면 **행이 없다**(`scalar()`가 `None`)이고 트랜잭션은 중단되지 않아 충돌을 모아 끝에서 한꺼번에 롤백할 수 있다(SAVEPOINT 불필요). 같은 기간을 먼저 넣은 다른 트랜잭션이 아직 끝나지 않았으면 그 끝을 기다린 뒤 충돌로 판정한다(한도를 넘으면 `WRITE_BUSY`). 시험: `backend/tests/test_entry_concurrency.py`의 `test_pg8000_rowcount_returning_and_on_conflict_facts`.
- **교착 방지**: 기존 행은 `row_id` 오름차순, 새 행은 기간 오름차순으로 잡는다. 두 붙여넣기가 같은 행을 반대 순서로 적어도 교착이 없다(15회 반복 시험). 일부러 반대 순서로 갱신하면 PostgreSQL이 교착을 끊고(`40P01`) 이것이 `WRITE_BUSY`로 바뀐다.
- **굶음(관찰, PostgreSQL 16.10)**: 행 쓰기가 `FOR SHARE`를 쥐고 있는 동안 기다리는 정의 변경(열 추가 등)을 **뒤에 들어온 새 행 쓰기가 앞지른다**(공유 잠금끼리는 호환이라 줄을 서지 않는다). 그래서 행 입력이 끊이지 않는 데이터셋에서는 정의 변경이 1초 뒤 `DEFINITION_BUSY`(503)로 끝나는 일이 반복될 수 있다. 무한 대기는 없다(`lock_timeout`). 이럴 때는 입력이 잠잠할 때 다시 시도한다. 시험은 'D가 대기 중'을 고정 `sleep`이 아니라 `pg_locks`의 `granted=false`를 폴링해 확인한 뒤 H2를 시작하고, H2가 D의 한도(1초) 안에 잠금을 얻었는지는 5초 여유로 기다리되 D가 아직 대기 중일 때 얻은 경우만 앞지름으로 센다(느린 CI의 거짓 실패 방지). 이 서술은 `test_entry_concurrency.py`의 `test_continuous_row_writes_overtake_a_waiting_definition_change`와 `test_dataset_concurrency.py`의 `test_continuous_for_share_holders_overtake_a_waiting_definition_change`가 단정으로 고정한다(관찰이 달라지면 시험이 깨져 이 서술을 다시 보게 한다).
- **정의 변경과 행 INSERT 경쟁**: 기준 날짜 열 지정·날짜 단위 변경(행이 0개일 때만 가능)은 `FOR NO KEY UPDATE`를 잡은 **뒤에** 행 존재를 확인하므로, 진행 중인 INSERT가 끝난 뒤에 확인한다 → `DATASET_HAS_ROWS`(422). 반대로 정의 변경이 먼저면 행 쓰기는 기다렸다가 버전이 달라 `DEFINITION_VERSION_MISMATCH`(409)다. 기다림이 3초를 넘으면 `WRITE_BUSY`. 500이 되는 경로는 없다.

## 7. 실패 시 확인 방법
| 증상 | 원인 | 확인과 해결 |
| --- | --- | --- |
| 403 `FORBIDDEN` | 그 데이터셋 팀의 입력자·정의 담당자가 아님(관리자 포함) | `skills/permission-management`로 팀 소속·역할 확인 |
| 409 `DEFINITION_VERSION_MISMATCH` | 다른 사람이 열을 먼저 바꿈(정의 버전이 올랐다) | `GET /datasets/<번호>`로 정의를 다시 읽고 `expected_version`을 바꿔 다시 보낸다 |
| 409 `CELL_CONFLICT` | 같은 칸을 다른 사람이 먼저 수정 | `details.conflicts[].current`가 지금 값. 다시 읽고 확인한 뒤 `expected`를 맞춰 다시 보낸다 |
| 409 `PERIOD_CONFLICT` | 같은 기간 행이 이미 있음(기준 날짜 열이 있는 데이터셋은 기간당 한 행) | `details.conflicts[].row_id`가 그 행. 그 행을 수정하거나 다른 기간을 쓴다 |
| 409 `PASTE_CONFLICT` | 붙여넣기 중 칸 값이 바뀌었거나 새 행의 기간이 이미 있음/행이 없음 | `kind`별로 확인. 아무것도 반영되지 않았다. 다시 읽고 붙여넣는다 |
| 422 `VALIDATION_ERROR` | 값 해석 규칙 위반 | `details.fields[]`의 위치와 `code`(위 표). 숫자는 십진 문자열로, 월 단위 기준 날짜는 1일로 |
| 422 `REQUIRED` `changes.N.expected` | `expected` 키가 빠짐 | 칸을 읽었던 값(빈 칸이면 `null`)을 반드시 보낸다 |
| 413 `PAYLOAD_TOO_LARGE` | 5,000행 또는 1MiB 초과 | 나누어 붙여넣는다. HTML 413이면 nginx가 막은 것(같은 안내) |
| 503 `WRITE_BUSY` | 다른 입력·정의 변경을 3초 넘게 기다림 또는 교착 | `retry_after`초 뒤 같은 요청을 다시 보낸다. 반복되면 `pg_stat_activity`의 긴 트랜잭션과 `docker compose logs backend` |
| 503 `DEFINITION_BUSY`(열 추가 등) | 입력이 이어져 정의 변경 락을 1초 안에 못 얻음 | 입력이 잠잠할 때 다시 시도(굶음 관찰 참조) |
| 503 `SERVICE_UNAVAILABLE` | DB 장애, 또는 사용자 조회 설정 오류(권한 거부·표 없음)도 같은 503으로 보임 | `/api/health/db`, `docker compose logs backend`. 설정 오류면 `migrate`가 최신인지, 접속 계정이 `bi_app`인지 확인 |
| 500 `INTERNAL_ERROR` | 예기치 않은 오류 | 응답의 `request_id`로 `docker compose logs backend` |
| 숫자 칸이 `"1234.5"`처럼 뒤 0이 사라짐 | PostgreSQL `numeric`은 저장한 자릿수를 그대로 돌려주므로 입력이 `"1234.5"`였을 것 | 입력 문자열 확인. (DB 없는 SQLite 시험은 자릿수를 보존하지 않는다) |

### 화면에 나오는 오류 문구
| 코드 | 화면 문구 요지 |
| --- | --- |
| CELL_CONFLICT (409) | 다른 사람이 먼저 이 칸을 바꿈, 서버 값 표시 + 내 값/서버 값 선택 |
| PASTE_CONFLICT (409) | 붙여넣는 동안 다른 사람이 바꾼 칸이 있어 아무것도 저장하지 않음 + 충돌 목록, 서버 값 기준 다시 붙여넣기 |
| PERIOD_CONFLICT (409) | 이미 같은 기간의 행이 있음 |
| DEFINITION_VERSION_MISMATCH (409) | 다른 사람이 먼저 바꿈, 최신 내용을 다시 읽음(정의·행 재읽기) |
| WRITE_BUSY / DEFINITION_BUSY (503) | 다른 작업 진행 중, 잠시 뒤 다시 시도(약 N초 뒤) + 다시 시도 버튼 |
| VALIDATION_ERROR (422) | 칸·줄 위치와 함께 REQUIRED 꼭 입력 / OUT_OF_RANGE 허용 범위(최소~최대) / BAD_FORMAT 형식 / NOT_IN_OPTIONS 선택 목록에 없음(항목 나열) / NOT_PERIOD_START 기간의 첫날 아님 / READ_ONLY 바꿀 수 없음 / TOO_LONG 너무 김(N자 이하) |
| PAYLOAD_TOO_LARGE / JSON 아닌 413 | 한 번에 5,000행·요청 1MiB까지, 나누어 붙여넣기 |
| ROW_NOT_FOUND (404) | 행을 찾을 수 없음(다른 사람이 지웠을 수 있음), 다시 읽기 |
| PREVIEW_BUSY (429) | 계산 요청이 많음, 잠시 뒤 다시 시도(행 조회 C1) |
| FORBIDDEN (403) / SERVICE_UNAVAILABLE (503) / NETWORK_ERROR / INTERNAL_ERROR | 권한 없음 / 서버 일시 장애 / 연결 실패 / 예기치 않은 오류 + 문의 번호 |

### 알려진 현상
- **접두 밖 주소를 브라우저에 직접 입력하면 빈 화면이 나온다.** 예: `APP_BASE_PATH=/bi-wizard`일 때 `http://호스트/datasets/42`처럼 접두가 없는 주소. nginx의 루트 SPA fallback이 `index.html`을 돌려주지만 라우터의 basename(`/bi-wizard`)과 맞지 않아 어느 경로와도 일치하지 않기 때문이다. 정상 사용 경로(접두가 붙은 주소와 앱 안의 링크)에서는 생기지 않으므로 고치지 않았다. 접두를 포함한 주소(`/bi-wizard/datasets/42`)로 접속하면 된다.
- AG Grid Community는 다중 범위 선택·클립보드 붙여넣기·xlsx 내보내기가 없다. 붙여넣기는 브라우저 `paste` 이벤트의 `text/plain`을 직접 해석한다. 그리드의 영어 접근성 문구(스크린리더용 aria 안내)는 번역하지 않았다(번역 패키지는 새 의존성).
- AG Grid 테마(Quartz)는 실행 때 `<style>`을 넣는다. 나중에 nginx에 CSP를 넣을 때 `style-src`에서 인라인 스타일이 막히지 않는지 확인이 필요하다(현재 프런트 nginx에는 CSP 헤더가 없다).

## 8. 검증 방법
- DB 없이(SQLite, `docker build --target test backend`와 같다): `cd backend && pytest`. 입력 API 시험은 SQLite로 돌며 `pg` 변형과 **차이가 있다**: SQLite는 `numeric`을 실수로 저장해 자릿수 단정을 못 하고, 기준 날짜 열의 `NOT NULL`·기간 첫날 CHECK는 지원하지 않으며(앱 검증이 같은 규칙을 먼저 막는다. 기간 **유일 인덱스**는 SQLite에서도 실제로 만들어 `PERIOD_CONFLICT` 경로를 시험한다), 잠금·`lock_timeout`·교착이 없다.
- 실제 PostgreSQL(권장, `skills/permission-management/SKILL.md`의 "검증 방법" 절차로 tmpfs `postgres-test`): 같은 `pytest`가 `pg` 변형과 동시성 시험을 포함해 돈다. 시험 실행 환경에 `REQUIRE_PG=1`을 주면 PostgreSQL 환경이 없을 때 건너뛰지 않고 실패한다(skip 0 확인).
- 시험 위치(`backend/tests/`):
  - `test_entry_values.py` — 열 타입별 해석 표(숫자 자릿수·범위·NaN·지수·부동소수점·큰 정수, 날짜 단위별 첫날, boolean 표기, choice, text 길이·NFC·제어문자), 응답 값 표현
  - `test_entry_api.py` — C1 정렬·쪽·값 표현, C2~C4 모든 오류 코드, `expected` 누락 422, 전부 취소, 413(5,001행·1MiB 초과), `RowViewPort` 교체와 호출 조건 (SQLite·`pg` 두 변형)
  - `test_entry_concurrency.py` — (pg 전용) pg8000 `rowcount`·`ON CONFLICT` 사실, 같은 칸 동시 수정, 같은 기간 동시 INSERT, 붙여넣기 교차 갱신 교착 없음, `WRITE_BUSY`, 정의 변경과 행 쓰기 경쟁, 굶음 관찰
  - `test_permission_matrix.py` — C1~C4 × 역할(관리자·정의 담당자·입력자·다른 팀 구성원·비소속 읽기·비활성·인증 없음), 거부된 요청이 데이터를 바꾸지 않음
  - `test_dataset_api.py`·`test_ddl.py`·`test_dataset_concurrency.py` — 기준 날짜 열 규칙 DDL 실패의 오류 변환, 동적 DDL 게이트(FK·유일·계산 열 거부), 이름 변경 중 FK 자식 INSERT 대기, `FOR SHARE` 굶음
- 마이그레이션: 1c는 새 revision이 없다. `python -m migrations.roundtrip`·`alembic check`가 그대로 통과해야 한다(`skills/local-environment/SKILL.md`).
- 수동 확인: 위 curl 순서 실행 뒤 `psql`(`bi_owner`)로 `SELECT * FROM bi_data.ds_<번호>`. 두 터미널에서 같은 칸을 `expected`가 같은 두 요청으로 동시에 수정해 한쪽이 `CELL_CONFLICT`가 되는지 본다. 5,000행 붙여넣기 소요 시간은 측정 조건에 따라 다르다: tmpfs PostgreSQL에서 pytest로 약 3~4초, 볼륨 PostgreSQL + nginx 경유 실측 4.7~6.5초(QA 2026-10-12). 운영 DB에서는 더 달라질 수 있다.

- 프런트 자동 시험:
  - `frontend/src/features/entry/paste/parser.test.ts`: 붙여넣기 파서. `docs/samples/clipboard-cases.json` 42건(거부 3건 포함)과 속성 시험 `parse(serialize(x)) == x`(무작위 표 2,000개 x CRLF/LF, 외부 라이브러리 없음). 이미지 빌드(`docker build --target test frontend`)는 frontend/ 폴더만 쓰므로 사본을 `paste/fixtures/clipboard-cases.json`에 두었고, 저장소 전체가 있을 때는 원본과 같은지 확인한다. 원본을 고치면 사본도 같이 고친다.
  - `paste/plan.test.ts`: 요청 만들기(row_id·expected·values, 새 행, 5,000행/1MiB, 계산 열·기간 열·열/행 부족, 모호 값).
  - `values.test.ts`: 십진 문자열 서식·빈 칸과 0 구별·편집 입력 해석. `model.test.ts`: 임시 행 준비 판정과 AG Grid 열 정의.
  - `entry.test.tsx`: 렌더링(값 표현·오류 칸·계산 열 읽기 전용·읽기 전용 모드·로딩/빈/오류), 쪽 이동 쿼리, 칸 편집 호출 본문과 낙관적 표시·되돌림, 충돌 해결, 버전 불일치, 임시 행 C2 1회, 붙여넣기 호출 본문·충돌·413·422. 가짜 서버는 `test-server.ts`(05 C1~C4 계약대로 동작).
  - jsdom 한계: 마우스 더블클릭·Enter로 편집이 시작되지 않아 시험은 그리드 API로 편집을 시작하고 입력·Enter 확정은 DOM 이벤트로 보낸다. 가로 스크롤·Tab 이동·1920x1080 배치는 확인하지 못했다(Playwright 스크린샷 단계에서 확인).
  - 실행: `cd frontend && npm run typecheck && npm run lint && npm test && npm run build`.

## 9. 연관 Skill
- `dataset-definition`: 열 타입·필수·범위 규칙·기준 날짜 열·날짜 단위의 정의. 행 쓰기가 같은 `datasets` 행을 `FOR SHARE`로 잡아 정의 변경과 서로 기다린다(`DEFINITION_BUSY`, `DATASET_HAS_ROWS`)
- `permission-management`: 팀·소속·역할(`입력(팀)` 판정), 인증 스텁, 실제 DB 시험 방법
- `formula-column`(예정, FU-1d): 계산 열 값과 오류 칸을 `RowViewPort`로 제공하고 이 Skill의 행 조회가 그것을 읽는다
- `dashboard-link`(예정, FU-1e): 입력된 행이 `dv_` 뷰를 거쳐 Superset 차트에 보인다
- `admin-cleanup`: 잘못 입력한 행·데이터셋의 수동 정리(FU-1에는 삭제 API가 없다)
- `local-environment`: 마이그레이션 왕복, 시작 자가 점검, 실제 DB 시험 환경
