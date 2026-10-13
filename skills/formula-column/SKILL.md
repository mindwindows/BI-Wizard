---
name: formula-column
description: 같은 행 수식으로 계산 열을 만들고 고치는 기능의 수식 엔진과 API. 엑셀 느낌의 수식("[매출] - [비용]", IF, ROUND, SUMTAG 등)을 검사하고 쉬운 한국어 오류와 위치를 알려 주며, 빈 값 전파·오류 칸 규칙을 지켜 DB 뷰(dv_·de_)로 계산한다. 저장 전 미리보기, 수식 보기, 계산 오류 칸 점검, 뷰 재생성 점검까지 포함한다. "수식 검사", "계산 열", "함수 추가", "수식이 이상해요", "오류 칸", "뷰 다시 만들기" 같은 요청에 쓴다.
---

# formula-column — 수식 엔진 (FU-1d)

> **구현 상태(2026-10-12)**: 1단계(`backend/app/formula/` 순수 라이브러리) + **2단계 backend 완료** — `formulas`·`formula_deps` 표(revision `0005`), 정의 변경 훅이 만드는 뷰 `dv_<번호>`·`de_<번호>`, 정의 해시와 시작 시 재생성, 05 D1~D10 API, `RowViewPort` 구현, 미리보기-뷰 차분 시험 전수 매트릭스. 화면(S4 수식 편집기·수식 보기, S5 점검, S9 뷰 재생성 구역)의 사용법은 5·7절에 합쳐져 있다.

## 1. 목적
팀 사용자가 엑셀에서 쓰던 계산을 데이터셋의 계산 열로 옮길 수 있게, 같은 행 수식을 안전하게 검사하고 DB 식으로 바꾼다. 수식이 틀리면 SQL 용어 없이 "어디가 왜 틀렸는지"를 알려 주고, 빈 칸과 오류 칸을 0으로 오해하지 않게 구별한다. 저장하기 전에 일부 행으로 결과를 미리 보고, 저장한 수식은 누구나 현재 열 이름으로 풀어 읽을 수 있다. 함수 추가는 사전 항목 한 개와 시험 사례로 끝난다.

## 2. 사용 조건 / 사전 요구사항
- 권한(05 §4): 함수 도움말(D1)·수식 보기(D6)·오류 칸 점검(D7·D8)은 로그인한 활성 사용자 누구나(타 팀 포함). 검사(D2)·미리보기(D3)·계산 열 만들기(D4)·수식 고치기(D5)는 **그 데이터셋 팀의 정의 담당자**만(관리자라도 그 팀 `definer`가 아니면 403). 뷰 점검(D9)·다시 시도(D10)는 관리자.
- 데이터셋과 원본 열이 `dataset-definition`으로 만들어져 있어야 한다. 환경은 `local-environment` 통과 상태(PostgreSQL, `bi_app`·`bi_owner` 분리, `0005` 적용).
- 1단계 라이브러리는 로그인·DB가 필요 없는 순수 파이썬이다. `lark==1.3.1`(MIT, 승인 AP-15)이 `backend/requirements*.txt`에 고정돼 있다. 상수 부분식 검사(`1/0` 등)와 뷰·미리보기는 PostgreSQL이 필요하다.
- 뷰 DDL은 PostgreSQL 전용이다. SQLite 시험 엔진에서는 `formulas`·`formula_deps`만 쓰고 뷰를 만들지 않는다.

## 3. 입력
### 3-1. 수식 글자 (07 §1)
- 열 `[열 이름]`(이름 안에 `[` `]` `"` 불가), 글자 `"가나""다"`(`""`는 따옴표 하나), 숫자 `1234.5`, `TRUE`/`FALSE`, 함수 `NAME(…)`. 날짜 상수와 `NULL` 상수는 없다(날짜는 `DATE(연, 월, 일)`, 빈 값은 열 값에서만 생긴다). `%`·`^`·`!=`는 없다(같지 않음은 `<>`).
- 우선순위(낮음 -> 높음): 비교 `= <> < <= > >=` < `&` < `+ -` < `* /` < 부호. 같은 단계는 왼쪽부터.
- 함수: `+ - * /`, 비교 6종, `&`, `IF`, `AND OR NOT`, `IFERROR`, `ROUND ROUNDUP ROUNDDOWN`(자릿수는 직접 쓴 정수 -10~10), `ABS`, `MIN MAX`(2개 이상), `SUM`, `LEFT RIGHT`, `LEN`, `TRIM`, `YEAR MONTH`, `DATE`, `SUMTAG("태그")`. 이름·인수·엑셀과 차이·도움말은 `GET /api/formulas/functions`(D1)로 사전에서 자동 생성된다.
- 상한: 수식 2,000자(요청 본문은 10,000자 초과 시 422 `VALIDATION_ERROR` `TOO_LONG`), 글자 상수 200자(NFC 정규화 뒤, 역슬래시·제어·서식 문자·NUL 거부), 숫자 38자리, 펼친 노드 2,000개, AST 깊이 40, 참조 사슬 10단계, 변환 결과 SQL 노드 50,000개. 항이 41개 이상인 덧셈 `a+b+c…`은 깊이 때문에 거부되므로 `SUM(…)`을 쓴다.

### 3-2. API 요청 (05 §2-4)
| ID | 요청 |
| --- | --- |
| D2 `POST /api/datasets/{id}/formulas/check` | `{expression, column_id?}` (`column_id` = 편집 중인 계산 열, 자기 참조·순환 기준) |
| D3 `POST …/formulas/preview` | `{expression, column_id?}` (저장 없음) |
| D4 `POST …/formulas` | `{expected_version, display_name, expression, tag?, position?}` (열 이름·태그 규칙은 `dataset-definition`과 같다. 태그는 숫자 결과에만) |
| D5 `PUT …/formulas/{col_id}` | `{expected_version, expression}` |
| D6 `GET …/formulas/{col_id}` | - |
| D7 `GET /api/checks/formula-errors` | `limit`(기본 50, 최대 200)·`offset` |
| D8 `GET /api/datasets/{id}/formula-errors` | `column_id?`, `limit`, `offset` |
| D9 `GET /api/checks/views` | - |
| D10 `POST /api/checks/views/retry` | `{dataset_ids?}` (생략 = 실패 전부) |
- D10은 뷰를 다시 만든 데이터셋마다 커밋 뒤 Superset 동기화를 요청한다(`skills/dashboard-link`, 다시 만들지 못한 것은 요청하지 않는다).
- 알 수 없는 필드는 422다(`extra=forbid`). 위치(`start`/`end`)는 **0부터 시작하는 코드포인트 번호이고 `end`는 포함하지 않는다**(자바스크립트 UTF-16 번호가 아니다: 이모지 같은 보충 평면 문자 뒤에서는 화면이 변환한다).

## 4. 출력
### 4-1. 라이브러리 (`backend/app/formula/api.py`)
- `compile_formula(...)` -> `CompileResult`: `ok`, `issues[{code, message, start, end}]`, `result_type`, `ast`(열 번호 참조; `ast_json`/`ast_hash`가 저장용), `deps`(`formula_deps`), `source_columns`, `sumtag_columns`, `functions_used`, `node_count`, **`value`(값 식)·`error`(오류 식)** SQLAlchemy 표현식.
- 값 식은 오류 칸이면 NULL, 오류 식은 정상·빈 값이면 NULL이고 오류면 셀 오류 코드(smallint 1~3 = `E1` 0으로 나눔, `E2` 글자 길이 범위, `E3` 날짜 범위; 문구는 `CELL_ERROR_MESSAGES_KO`). 오류가 날 수 없는 식은 `error=None`.
- 의미 규칙(07 §3): 빈 값은 0이 아니라 결과도 빈 값(`MIN`·`MAX`·`SUM`·`SUMTAG` 포함 전파), 글자 `=`·`<>`는 대소문자 무시, 숫자-글자·날짜-글자 자동 변환 없음, `IF`는 고른 쪽만, `IFERROR`는 오류 칸일 때만 대체값(빈 값은 그대로), 평가 순서는 인수 오류 > 인수 빈 값 > 자기 조건.
- 모든 상수는 `CAST(… AS 형)`이다. 같은 표현식을 그대로 실행하면 미리보기(바인드), `render_literal_sql`로 렌더하면 뷰 정의와 같은 글자다.

### 4-2. API 응답
- D1 `{functions[{name, signature, returns, help_ko, excel_diff}](모두 문자열), cell_errors{"E1": 문구, …}}`.
- D2 `{ok, result_type, refs[{column_id, display_name}], errors[{code, message, start, end}]}` — C0 검사 실패도 **200**(`ok=false`).
- D3 `{result_type, rows[{row_id, period, value, error}], total_rows, error_count, empty_count, def_version}`. `rows`는 기준 날짜(없으면 `row_id`) 최근 순 **20행**, 개수는 전체 행 기준 한 번의 집계. `value`: 숫자는 십진 **문자열**(`"2.5000000000000000"`), 참거짓은 JSON 불리언, 날짜는 `YYYY-MM-DD`, 글자는 글자, 오류 칸·빈 값은 `null`(오류 칸은 `error`가 `"E1"` 등). `period`는 기준 날짜 열이 없으면 `null`.
- D4 201 `{column, def_version}`(`column`은 05 §1 Column, `kind=formula`, `type`=결과 형). D5 200 `{column, def_version, result_type_changed}` — **같은 수식(저장된 AST가 같고 결과 형도 같음)이면 아무것도 바꾸지 않고 버전도 올리지 않는다.**
- D6 `{column_id, text, refs[{column_id, display_name, kind}], tag_columns[이름], error_count}` — `text`는 **현재 열 이름으로 풀어 쓴 정규 형태**이고 이것을 그대로 다시 저장할 수 있다. **원문 `expression`은 응답에 없다.**
- D7·D8 `{items, total, limit, offset}`. D7 `{dataset_id, dataset_name, team_name, column_id, column_name, error_count}`(오류 칸이 있는 열만, 팀·데이터셋 이름순), D8 `{row_id, period, column_id, error, message}`(계산 열 번호 순, 같은 열은 행 번호 순).
- D9 `{views, views_failed_count, failed[{dataset_id, dataset_name, reason, since}]}`. `reason`은 `LOCK_TIMEOUT:`·`FORMULA_INVALID:`·`VIEW_VERIFY_FAILED:`·`LITERAL_INVALID:`·`DB_ERROR:`·`UNEXPECTED:` 같은 사유 코드와 쉬운 말 요약뿐(SQL·상수·비밀 없음), `since`는 `+09:00` 시각. D10 `{rebuilt, views_failed_count}`.
- 오류 코드(05 §3): 422 `FORMULA_INVALID`(`details.errors[]`는 D2와 같은 모양), 422 `FORMULA_CIRCULAR`(`details.path` = 열 **이름** 문자열 배열 `["가","나","가"]`), 422 `FORMULA_RUNTIME_ERROR`(DB 예외·시간 초과를 하나로 정규화), 409 `DEFINITION_VERSION_MISMATCH`(`details.current_version`)·`ALREADY_EXISTS`(`details.field=display_name`), 503 `DEFINITION_BUSY`(`details.retry_after`), 429 `PREVIEW_BUSY`(`details.retry_after`, 응답 헤더 `Retry-After`).

### 4-3. 저장되는 곳
- `formulas`(열마다 수식 하나: 보관용 원문 `expression`, 열 번호 참조 `ast`, `ast_hash`), `formula_deps`(계산 열이 읽는 열, `SUMTAG`는 펼친 구체 열). **계산 열은 원본 표 `ds_<번호>`에 저장되지 않는다.** `bi_data.dv_<번호>`(`team`, `row_id`, 열 번호 오름차순 `c_<번호>`: 원본·계산 열; 오류 칸은 NULL)와 `bi_data.de_<번호>`(`row_id`, 계산 열마다 `e_<번호>` smallint: NULL = 정상 또는 빈 값, 1~3 = 셀 오류 코드)가 데이터셋마다 생긴다(수식이 없어도 `dv_`는 `team`·`row_id`만으로 만든다). `datasets.def_hash` = 두 뷰 정의(리터럴 렌더)의 sha256.

## 5. 실행 방법
- **사람(화면)**:

#### 계산 열 만들기 (S4 왼쪽 "계산 열 추가" -> Inspector의 수식 편집기, 정의 담당자만)
1. 데이터셋 작업공간(`/datasets/<번호>`) 왼쪽 "열 목록" 아래 **계산 열 추가**를 누른다(정의 권한이 없으면 버튼이 없다). 오른쪽 Inspector에 "계산 열 추가" 편집기가 열린다.
2. **계산 열 이름**을 쓰고 **수식** 칸에 수식을 쓴다. 열은 `[열 이름]`, 글자는 `"큰따옴표"`, 함수는 `IF(…)`처럼 쓴다.
   - **열 이름 칩**: 수식 칸 위의 칩(열 이름 버튼)을 누르면 커서 위치에 `[열 이름]`이 들어간다(글자를 선택해 두면 그 글자가 바뀐다). 계산 열은 기울임 칩이다. 고치는 열 자신은 칩에 없다(자기 참조는 순환).
   - **자동완성**: 함수 이름을 한 글자 이상 치면 후보가 뜬다(함수 목록은 `GET /api/formulas/functions`). `[`를 치면 열 이름 후보, `SUMTAG("` 안에서는 열 구분 태그 후보. **↑↓ 로 고르고 Enter 또는 Tab으로 넣고 Esc로 닫는다.** 마우스로 눌러도 된다. 후보에 올려 둔 함수는 아래에 쉬운 설명과 "엑셀과 차이"가 나온다. 함수 목록을 못 읽어도 칩과 `[` 열 이름 자동완성은 동작한다("수식 도움말"에서 다시 불러오기).
3. **자동 확인**: 입력을 멈추고 약 0.4초 뒤 `POST /api/datasets/{id}/formulas/check`로 수식을 검사한다(마지막 입력만 보낸다). 문제가 있으면 수식 아래에 **오류 위치 표시**(수식 글자 중 문제 부분이 붉은 물결 밑줄)와 쉬운 말 문구가 나오고, 문구 옆 "위치 보기"를 누르면 입력창에서 그 글자가 선택된다. 문제가 있으면 저장 버튼이 막힌다. 문제가 없으면 "수식에 문제가 없습니다. 결과는 숫자입니다. 쓰는 열: …"가 나온다. 결과가 숫자일 때만 "구분 태그(선택)"가 나온다.
4. **미리보기**: 검사가 통과하고 약 0.6초 더 지나면(입력 후 약 1초) 자동으로 `POST …/formulas/preview`를 부른다. "미리보기" 버튼으로 바로 계산할 수도 있다. **저장하기 전에는 아무것도 바뀌지 않는다.**
   - 기준 날짜 최근 순 최대 20행의 값이 나오고, 위에 `결과: 숫자 · 전체 36행 중 오류 칸 1개 · 빈 값 1개`가 나온다(전체 행 기준 집계).
   - **값 / 오류 / 빈 값을 구별한다**: 값은 그대로(숫자는 쉼표 서식, 예/아니오), **오류 칸은 붉은 배경에 "오류 E1" + 이유 문구**, **빈 값은 빗금 배경의 "빈 값"**. 빈 값은 계산에 쓴 칸 중 비어 있는 칸이 있다는 뜻이고 0이 아니다.
   - 수식을 고치면 이전 요청은 취소되고(사용자당 동시 1건) 늦게 온 낡은 결과는 무시된다. 새 결과가 올 때까지 이전 표는 흐리게 남는다.
   - 계산 요청이 많아 `PREVIEW_BUSY`(429)가 오면 "잠시 뒤 자동으로 다시 시도합니다"가 나오고 **한 번 자동으로 다시 시도**한다(서버 `retry_after` 1~5초). 그래도 바쁘면 "다시 시도" 버튼이 나온다.
5. **저장**: "계산 열 추가"를 누르면 `POST /api/datasets/{id}/formulas`에 `{expected_version, display_name, expression, tag?, position?}`를 보낸다. 성공하면 새 열이 선택되고 "계산 열을 추가했습니다."가 나오며 입력 그리드가 행을 다시 읽어 새 열 값이 채워진다.
6. **수식 도움말**(편집기 아래 접힘): 빈 칸은 0이 아님, 계산할 수 없는 칸은 빈 값이 되고 점검 화면에 표시됨(`IFERROR` 안내), 글자 비교는 대소문자 무시, 자동 변환 없음, 쓰는 법. 그리고 D1의 함수 목록(모양, 설명, 엑셀과 차이).

#### 수식 보기 (계산 열 선택, 열람자도 읽기 전용)
- 열 목록이나 그리드 머리글에서 계산 열을 누르면 Inspector의 **수식 보기**에 `GET /api/datasets/{id}/formulas/{col_id}` 결과가 나온다: **현재 열 이름으로 풀어 쓴 수식**(`text`; 열 이름을 바꾸면 따라 바뀐다), 결과 종류, **쓰는 열**(입력 열/계산 열 표시), **태그로 더하는 열**(`SUMTAG`가 지금 포함하는 열, 있을 때만), **오류 칸 수**(1개 이상이면 "점검 화면에서 보기" 링크 -> `/checks?dataset=…&column=…`).
- 원문 수식(`expression`)은 API에 없다. 편집기 시작값은 `text`다.
- 정의 권한이 없으면 수식 보기만 있고 "수식은 팀의 정의 담당자만 고칠 수 있습니다."가 나온다(편집기·검사·미리보기 호출 없음). 이것은 편의이며 최종 방어선은 서버 권한 검사다.

#### 수식 고치기
- 정의 담당자는 수식 보기 아래 **수식 고치기**를 누른다. 편집기가 수식 보기의 `text`로 열린다(같은 수식이면 "수식 저장"이 막혀 있다). 검사에는 `column_id`가 같이 가서 자기 참조·순환을 서버가 판정한다. 저장은 `PUT …/formulas/{col_id}`에 `{expected_version, expression}`.
- 결과 종류가 바뀌면(`result_type_changed`) "결과 종류가 바뀌었습니다. 이 열을 쓰는 저장된 차트가 있으면 대시보드에서 차트가 그대로 보이는지 확인해 주세요."가 나온다(영향 차트 수는 후속).
- 계산 열의 이름·위치·태그는 이 화면에서 고칠 수 없다(열 정보 양식은 읽기 전용). 수식만 고친다.

#### 입력 그리드의 계산 열 (S4 가운데)
- 머리글: 계산 열은 기울임 + 앞에 `ƒ` 표시 + 아래 선(입력 열과 구별). 칸: 이탤릭 + 왼쪽 세로 선(계산 열 표지)의 읽기 전용, 값이 있는 칸만 회색 배경, 붙여넣기 범위에 걸치면 막힌다. 칸을 두 번 누르거나 Enter/F2/글자 입력을 하면 "계산 열은 수식으로 계산되어 직접 고칠 수 없습니다. 수식은 Inspector에서 고칠 수 있습니다."가 5초간 나온다.
- **오류 칸**: 붉은 배경의 "오류" + 작은 코드(E1/E2/E3). 칸 위에 올리면 이유가 나온다(문구는 `GET /api/formulas/functions`의 `cell_errors`; 못 읽으면 기본 문구). **빈 칸(계산 결과가 빈 값)은 입력 열과 같은 빗금 배경**(계산 열 표지 세로 선은 유지)이라 오류 칸과 다르게 보인다.

#### S5 점검 (`/checks`, 읽기 권한이면 누구나)
1. 상단 메뉴 **점검**. 계산 오류 칸이 있는 열만 `데이터셋 / 팀 / 계산 열 / 오류 칸 수` 표로 나온다(`GET /api/checks/formula-errors`, 50개씩 쪽 이동). 오류가 없으면 "계산 오류 칸이 없습니다".
2. 행의 **오류 칸 보기**를 누르면 그 열의 오류 칸이 `기간 / 행 / 코드 / 이유`로 펼쳐진다(`GET /api/datasets/{id}/formula-errors?column_id=…`, 50개씩). **작업공간 열기**(또는 데이터셋 이름)로 해당 데이터셋 작업공간으로 이동해 입력 값이나 수식을 고친다.
3. 계산 요청이 많으면(`PREVIEW_BUSY`, 429) 쉬운 문구와 "다시 시도" 버튼이 나온다(펼친 구역에서는 그 구역에서만).

#### S9 현황의 '뷰 재생성' 구역 (`/admin/status`, 관리자만)
- 수식 계산에 쓰는 데이터 구조(뷰)를 만들지 못한 데이터셋을 보여 준다(`GET /api/checks/views`): `확인한 데이터셋 N개 중 실패 M개`, 실패 목록(데이터셋 / 사유 / 실패한 시각). 실패가 있어도 다른 기능은 동작한다(해당 데이터셋의 계산 열 값만 안 보일 수 있다).
- **이 데이터셋 다시 시도** 또는 **실패한 항목 전부 다시 시도**(`POST /api/checks/views/retry`, 전부는 본문 `{}`)를 누르면 요청 안에서 끝까지 처리한 결과(`N개를 다시 만들었습니다. 아직 M개가 실패 상태입니다`)를 보이고 현황을 다시 읽는다. 다른 정의 변경과 겹치면 `DEFINITION_BUSY` 안내.
- 사유는 서버가 준 사유 코드·요약 그대로 보인다. 실패 상세는 서버 메모리에만 있어 서버를 다시 시작하면 사라진다(07 §8). Superset 동기 구역은 같은 화면(S9)에서 이 구역 옆에 있다(`skills/dashboard-link`).
- **AI/개발자(HTTP, 개발·시험 스텁 신원)**: 쿠키 `bi_stub_login=<login_id>`(스텁 전용 `permission-management` 참조). 아래 `$B`는 `http://127.0.0.1:<FRONTEND_PORT>${APP_BASE_PATH}`(nginx 경유), 데이터셋 번호 `$D`.
  ```
  # D2 검사
  curl -s -b "bi_stub_login=definer" -H 'Content-Type: application/json' \
    -d '{"expression": "IFERROR(([매출] - [비용]) / [매출], 0)"}' $B/api/datasets/$D/formulas/check
  # D3 미리보기(저장 없음)
  curl -s -b "bi_stub_login=definer" -H 'Content-Type: application/json' \
    -d '{"expression": "[매출] - [비용]"}' $B/api/datasets/$D/formulas/preview
  # D4 계산 열 만들기(정의 버전 필요: GET $B/api/datasets/$D 의 def_version)
  curl -s -b "bi_stub_login=definer" -H 'Content-Type: application/json' \
    -d '{"expected_version": 7, "display_name": "이익", "expression": "[매출] - [비용]"}' $B/api/datasets/$D/formulas
  # D6 수식 보기, D8 오류 칸, D9 뷰 점검(관리자)
  curl -s -b "bi_stub_login=viewer" $B/api/datasets/$D/formulas/$COL
  curl -s -b "bi_stub_login=viewer" "$B/api/datasets/$D/formula-errors?column_id=$COL"
  curl -s -b "bi_stub_login=admin" $B/api/checks/views
  ```
- **AI/개발자(파이썬 라이브러리)**:
  ```python
  from app.formula import ColumnInfo, compile_formula, render_text
  cols = [ColumnInfo(1, "매출", "number"), ColumnInfo(2, "비용", "number")]
  r = compile_formula("IFERROR(([매출] - [비용]) / [매출], 0)", cols, const_probe=probe)
  r.ok, r.issues, r.value, r.error   # probe: 상수 SELECT 평가기(서비스는 hook.make_probe), 없으면 r.const_probe_skipped
  render_text(r.ast, cols)           # 열 이름을 풀어 쓴 수식 보기
  ```
  계산 열을 참조하려면 그 열을 `ColumnInfo(id, name, type, kind="formula", formula=<저장된 AST>)`로 준다(`ast_from_json`). 편집 중인 기존 열은 `column_id=`, 새 열의 태그는 `tag=`로 알린다.
- **함수 추가**: `backend/app/formula/functions.py`에 `FunctionSpec` 하나(+ `cases`)를 더하고 `_ALL_SPECS`에 넣는다. 파서·C0·변환기·도움말·API·**차분 시험 행렬**은 고치지 않는다(`tests/test_formula_registry.py`가 임시 함수로 증명하고, `tests/formula_matrix.py`가 사전에서 행렬을 자동으로 키운다). 새 SQL 함수(`func.xxx`)를 쓰면 뷰 정의 게이트의 허용 목록 `ddl.VIEW_ALLOWED_FUNCTIONS`(`backend/app/ddl/dynamic.py`)에 검토해서 더해야 한다(목록 밖 함수는 `create_view`가 실행 전에 거부하고, `tests/test_formula_units.py`의 검토 목록 시험이 알려 준다). 함수 변경으로 변환 SQL이 바뀌면 정의 해시가 달라져 다음 시작 때 해당 데이터셋의 뷰만 자동으로 다시 만들어진다(예: `ROUNDUP`의 값 식을 정확한 곱셈 형태로 바꾼 1d 수정 뒤 `ROUNDUP`을 쓰는 데이터셋의 뷰가 시작 때 한 번 재생성된다. 값이 달라지는 경우는 이전에 유효숫자 약 16자리를 넘는 값에서 틀리던 경우뿐이다). 항목 규칙은 `registry.py` 머리말.
- **시작 지연(실측)**: 서비스는 시작 대조(`reconcile_all`)가 끝나야 요청을 받는다(lifespan에서 동기 실행). 활성 데이터셋 50개(원본 열 2개 + 계산 열 3개, 행 없음, tmpfs PostgreSQL, 2026-10-12)에서 해시가 모두 같은 보통의 재시작은 약 1.2초, 모든 뷰를 다시 만드는 경우(해시 전부 불일치)는 약 4.3초였다(`test_startup_reconcile_time_with_fifty_datasets`가 다시 잰다. 행 수는 뷰 생성 시간에 거의 영향이 없고 데이터셋 수와 계산 열 수에 비례하는 것으로 보이나 행이 많은 운영 데이터로는 확인하지 못했다). 코드는 바꾸지 않았다.
- **운영 점검**: 시작할 때 활성 데이터셋마다 현재 정의로 계산한 해시와 `datasets.def_hash`를 비교하고(뷰가 없어도) 다른 데이터셋의 뷰만 다시 만든다. 못 만든 데이터셋은 `/api/health`의 `views_failed_count`와 D9 `failed`에 나오고(**시작은 막지 않는다**) 원인을 고친 뒤 D10(화면 S9 "다시 시도")으로 다시 만든다.

## 6. 관련 UI / API / command / DB
- UI: 수식 편집기·수식 보기(S4), 점검(S5), 관리자 현황의 뷰 재생성 구역(S9). 화면 설명은 5절 자리에 합쳐진다.
- API: D1 `GET /api/formulas/functions`, D2 `POST /api/datasets/{id}/formulas/check`, D3 `…/formulas/preview`, D4 `POST …/formulas`, D5 `PUT …/formulas/{col_id}`, D6 `GET …/formulas/{col_id}`, D7 `GET /api/checks/formula-errors`, D8 `GET /api/datasets/{id}/formula-errors`, D9 `GET /api/checks/views`, D10 `POST /api/checks/views/retry`. 행 조회(C1)와 행 쓰기(C2~C4) 응답에는 계산 열이 `RowViewPort`로 들어간다. 태그 변경(B6)은 순환·`TAG_EMPTY`를 이 훅이 재검사한다.
- command: 없음. 정리 절차는 `skills/admin-cleanup`.
- DB: 정적 표 `formulas`, `formula_deps`(revision `0005`; `bi_app` 권한은 `formulas` SELECT·INSERT·열 단위 UPDATE(`expression`, `ast`, `ast_hash`), `formula_deps` SELECT·INSERT·DELETE; `bi_readonly`에는 없음), 동적 객체 `bi_data.dv_<번호>`·`de_<번호>`(소유자 `bi_app`, `bi_readonly`가 읽을 수 있음).
- 코드(`backend/app/formula/`): `api.py`(공개 인터페이스와 가정), `parser.py`, `analyze.py`(C0), `cycles.py`, `convert.py`, `registry.py`·`functions.py`(함수 사전), `literals.py`(리터럴 렌더러 접점), `textview.py`(수식 보기), `errors.py`(문구 사전). 2단계: `repo.py`(`formulas`·`formula_deps` 접근), `views.py`(`dv_`·`de_` 정의·정의 해시·확인 질의), `hook.py`(정의 변경 훅), `service.py`(D2~D8), `reconcile.py`(시작 시 재생성·D10), `status.py`(뷰 대조 메모리 상태), `rowview.py`(`RowViewPort` 구현), `router.py`·`schemas.py`. 공통: `app/core/limits.py`(무거운 읽기 동시 상한), `app/ddl/dynamic.py`(`create_view`·`drop_view`, 허용 목록 게이트).

### 동작 요약 (구현 사실)
- **정의 변경 한 트랜잭션**(04 §5): `datasets` 행 `FOR NO KEY UPDATE`(`lock_timeout` 1초) -> `def_version` 확인 -> 열 변경(D4는 계산 열 행 추가, D5는 결과 형 갱신) -> **훅** -> `def_hash` 기록 -> 커밋. 훅은 ① 저장된 모든 수식을 현재 열 이름·태그로 **다시 컴파일**(열 이름 변경은 AST가 번호 참조라 통과, 태그 변경은 `SUMTAG` 펼침·순환·`TAG_EMPTY`에 반영, 참조한 수식의 결과 형이 바뀌어 깨지는 수식은 422로 거부하고 전부 롤백), ② 새 수식·바뀐 의존·바뀐 결과 형(`dataset_columns.type`)을 쓰고, ③ 뷰 정의와 해시를 만든다. **해시가 같고 뷰가 있으면 DDL을 건너뛴다**(열 이름·순서·데이터셋 이름 변경은 뷰를 다시 만들지 않는다). 열이 끝에만 늘면 `CREATE OR REPLACE VIEW`, 열 제거·형 변경이면 `DROP VIEW` + `CREATE VIEW`(`CASCADE` 없음; 실제 PostgreSQL에서 `CREATE OR REPLACE`가 형 변경에 `42P16`을 내는 것을 확인했고 그 경우 지우고 다시 만든다).
- **런타임 DDL은 `bi_app`으로 실행**한다. `bi_data` 소유자는 `bi_owner`(스키마), `ds_`/`dv_`/`de_`의 소유자는 `bi_app`, `bi_readonly`는 `dv_`·`de_`·`ds_`를 읽을 수만 있고 변경·삭제·생성은 모두 거부되며 `bi_app`은 `public`에 만들 수 없다(시험으로 확인).
- **완화책 3가지**(07 §4-3, X-26): ① 엔진 연결 때 `startup_params={"standard_conforming_strings": "on"}`로 세션 설정을 고정(`app/db.py`; 시작 자가 점검이 `on`인지 다시 확인) ② 역슬래시·제어문자·NUL·서식 문자 거부(C0와 리터럴 렌더러) ③ 뷰를 만든 직후 같은 트랜잭션에서 뷰 열 이름·개수를 읽어 확인하고, 뷰 정의에 들어간 모든 글자 상수를 같은 렌더러로 `SELECT`해 입력과 같은지 비교한다(어긋나면 `DdlVerificationError`로 롤백). 뷰 정의 SELECT는 `ddl` 게이트가 먼저 확인한다(자기 `ds_<번호>` 하나만 읽음, `text()`·`literal_column`·서브쿼리 없음, **허용 목록 `VIEW_ALLOWED_FUNCTIONS` 밖 SQL 함수 없음(`pg_sleep` 등 거부)**, 바인드는 숫자·글자·참거짓·날짜뿐이며 **글자 바인드의 NUL·역슬래시·제어·서식 문자는 게이트가 한 번 더 거부**, 출력 열 이름은 번호 규칙). **렌더 글자와 `CreateView`가 그리는 정의의 대조는 어떤 DB 문장도 실행하기 전에** 한다(렌더 함수가 정의를 바꿔 돌려주면 DB에 닿기 전에 `DdlVerificationError`). 확인 질의(`RenderedSelect`)는 렌더된 글자가 `SELECT CAST('…' AS TEXT) AS k0, …` 모양이고 값이 입력 상수와 같을 때만 **실행 전에** 통과하므로 임의 SQL을 돌려주는 render 함수를 주입해도 실행되지 않는다(`RenderedSelect`는 `ddl` 밖에서, `literal_column`은 `ddl`·`formula` 밖에서 쓰지 못하게 AST 시험이 지킨다). 뷰 정의 SQL에는 수식 상수가 들어 있으므로 **DB 오류는 SQL 없이(`DdlExecutionError`, SQLSTATE만) 올려 로그·응답에 상수가 남지 않는다.**
- **뷰 정의 게이트의 SQLAlchemy 부품 거부**(`app/ddl/dynamic.py` `_check_node_parts`·`_check_bind_value`, 1e 0단계, 뷰 정의 `_check_view_select`·확인 질의 `_check_echo_select`·`run_ddl`의 `CreateView` 직접 실행 모두): 사용자 정의 연산자(`custom_op`, `col.op("…")`), `EXTRACT` 단위가 `VIEW_ALLOWED_EXTRACT_FIELDS`(`year`·`month`·`day`) 밖인 것, callable 바인드(`callable_`; 값은 `effective_value`로 검사), 숫자 바인드의 비유한 값(`NaN`·무한대)·38자리 초과·알려진 모양 밖은 거부한다. 지수 표기(`1E+3`, `1E-8`)는 `ROUND` 계열의 10의 거듭제곱 상수가 이렇게 렌더되고 뷰 해시가 달라지므로 38자리 안에서 허용한다. 시험은 `test_formula_units.py`.
- **한도 문구**: 수식 한도에 걸릴 때 화면에 나오는 쉬운 말과 사용자가 할 일은 `skills/dataset-definition/SKILL.md`의 '수식 한도에 걸릴 때 나오는 쉬운 말' 절에 있고, `tests/test_formula_limit_messages_doc.py`가 `errors.py`와 대조한다.
- **읽기 전용·시간 제한·동시 제한**: D2~D3·D6~D8은 트랜잭션별 `transaction_read_only=on`과 `statement_timeout=5초`(`set_config`)로 실행한다. 미리보기는 사용자당 동시 1건, 미리보기·오류 칸 조회(D7·D8)·계산 열이 있는 데이터셋의 행 조회(C1)는 전역 동시 2건(풀 5개 중 3개를 일반 요청용으로 남김)이고 넘으면 429 `PREVIEW_BUSY`다(기다리지 않고 바로 거절). 모두 코드 상수이며 새 환경변수는 없다.
- **`RowViewPort`**: `dv_`와 `de_`를 `row_id`로 결합해 C1·C2~C4 응답의 계산 열 값과 `errors["<열 번호>"] = "E1"`을 준다. 뷰를 읽지 못하면(만들기에 실패한 데이터셋) 요청을 깨뜨리지 않고 계산 열을 빈 값으로 돌려준다(D9가 알린다). C2~C4가 계산 열 키를 보내면 422 `READ_ONLY`다.
- **계약 구현 메모**: ① 새 열의 수식은 그 열이 아직 없으므로 D4에서 자기 이름을 쓰면 `UNKNOWN_COLUMN`(`FORMULA_INVALID`)이고, 순환 `FORMULA_CIRCULAR`는 D5와 태그 변경(B6)에서 난다. ② 태그가 붙은 계산 열의 결과 형이 숫자가 아니게 되면 422 `VALIDATION_ERROR`(필드 `expression`, 코드 `BAD_FORMAT`, 05 §3 기존 코드)로 막는다(먼저 태그를 지운다). ③ 편집 중인 수식이 아닌 다른 계산 열의 수식이 깨지면 `FORMULA_INVALID`의 문구에 `'열 이름' 열의 수식 문제:`가 붙고 위치는 `0`~`0`이다. ④ `GET /api/health`의 `views`는 시작 대조와 이후 정의 변경이 확인한 활성 데이터셋 수이고 `views_failed_count`는 그중 실패 수다(프로세스 메모리, worker 1개 전제).

## 7. 실패 시 확인 방법
- 사용자에게 보이는 검사 오류는 `issues[].message`(쉬운 말)와 `start`/`end`다. 코드: `UNEXPECTED_END`·`UNEXPECTED_TOKEN`·`UNCLOSED_STRING`·`UNCLOSED_COLUMN`·`BARE_NAME`(문법), `UNKNOWN_COLUMN`·`UNKNOWN_FUNCTION`, `ARG_COUNT`·`ARG_TYPE`·`TYPE_MISMATCH`·`CONST_REQUIRED`·`CONST_RANGE`, `TEXT_CONSTANT_INVALID`·`NUMBER_INVALID`, `TAG_EMPTY`, `CIRCULAR`·`CHAIN_TOO_LONG`, `TOO_MANY_NODES`·`TOO_DEEP`·`TOO_COMPLEX`, `CONSTANT_ERROR`(상수 부분식 오류: `1/0`, `DATE(0,1,1)`, `LEFT("가",-1)`).
- API 오류 코드와 대응: 422 `FORMULA_INVALID`는 `details.errors`를 본다. 422 `FORMULA_CIRCULAR`는 `details.path`의 열 이름 경로를 보고 수식을 고친다. 409 `DEFINITION_VERSION_MISMATCH`는 정의를 다시 읽는다. 503 `DEFINITION_BUSY`(락 대기 1초 초과)는 잠시 뒤 다시 시도한다. 429 `PREVIEW_BUSY`는 `retry_after`초 뒤 다시 시도한다. 422 `FORMULA_RUNTIME_ERROR`는 시간 초과이거나 계산 불가 수식이다(서버 로그에 예외 클래스와 SQLSTATE만 남는다).
- 화면 문구 표(error.code 분기):

| 코드 | 화면 |
| --- | --- |
| FORMULA_INVALID (422) | 저장 응답: "수식에 고칠 곳이 있어 저장하지 않았습니다…" + 수식 아래 위치 표시·문구(`details.errors`, D2와 같은 모양). 응답이 상한에서 잘리면 "일부만 표시됨(전체 N건 중 일부)" |
| FORMULA_CIRCULAR (422) | "이 변경으로 계산 열이 서로를 참조하는 순환이 생깁니다…(순환 경로: A → B → A)" (`details.path` 열 이름 경로) |
| FORMULA_RUNTIME_ERROR (422) | 저장: "수식을 계산할 수 없습니다…" / 미리보기: "수식을 계산할 수 없습니다. 시간이 너무 오래 걸렸거나 계산이 불가능한 수식일 수 있습니다…" + 다시 시도 |
| DEFINITION_VERSION_MISMATCH (409) | "다른 사람이 먼저 바꿨습니다. 최신 내용을 다시 읽었습니다…" + "입력한 수식은 그대로 남아 있습니다". 정의를 다시 읽고 다음 저장은 새 `expected_version`으로 간다 |
| DEFINITION_BUSY (503) | "다른 작업이 진행 중입니다…(약 N초 뒤)" + "잠시 뒤 다시 저장해 주세요", 수식은 남는다 |
| PREVIEW_BUSY (429) | "지금 계산 요청이 많습니다…(약 N초 뒤)". 미리보기는 한 번 자동 재시도 후 버튼, S5는 다시 시도 버튼 |
| ALREADY_EXISTS (409, field=display_name) | "같은 이름의 열이 이미 있습니다." |
| VALIDATION_ERROR (422) | 열 이름·길이·예약어 등 필드 문구(1b와 같음) |
| 셀 오류 E1 / E2 / E3 | D1 `cell_errors` 문구. 기본: E1 0으로 나누어 계산할 수 없습니다 / E2 글자 길이 범위를 벗어났습니다 / E3 날짜 범위를 벗어났습니다 |

#### 계산 열 값 표시(03b 21-1 결정 2, 화면 표시만)
- 계산 열(숫자) 칸 표시: 소수 최대 6자리, 끝자리 0 제거, 천 단위 쉼표. 반올림은 0에서 먼 쪽(7번째 자리 5 이상이면 올림, 음수도 크기 기준).
  반올림 결과가 0이면 "0"(-0 없음). 과학 표기(1E-7)는 나오지 않는다. 부동소수점 없이 문자열로 처리하므로 38자리도 정확하다.
- 같은 규칙을 수식 편집기 미리보기 값(결과 종류가 숫자일 때)에 적용한다. S5 점검 화면에는 값 표시가 없어(오류 코드·이유만) 변경 없음.
- 입력 열(원본 숫자 열) 표시는 기존 규칙 그대로(decimals 규칙이 있으면 끝자리 0 채움, 깎지 않음). 열 규칙 decimals를 계산 열에 쓰는 것은 후속.
- 계산 열 칸 폭은 190px 유지.
- 구현 위치: frontend/src/features/entry/values.ts (formatComputedNumber, isComputedNumber), gridColumns.tsx (툴팁), EntryGrid.tsx (선택·복사),
  formula/messages.ts (previewCell), formula/FormulaPanel.tsx (Inspector 전체 값).

##### 사용자 관점 절차
1. 전체 값 보기(툴팁): 6자리를 넘어 줄여 보이는 칸에 마우스를 올리면 "전체 값: 2.718281828459"가 뜬다. 줄지 않은 칸은 기존 안내.
   미리보기 표의 값 칸도 같다.
2. 전체 값 보기(Inspector): 입력 그리드에서 계산 열 칸을 누르면 오른쪽 Inspector가 그 열의 수식 보기로 바뀌고,
   "선택한 칸의 전체 값"에 기간·행 번호·열 이름·전체 값이 쉼표·반올림 없이 나온다(오류 칸은 오류 코드와 이유, 빈 칸은 "빈 값").
   주의: 다른 계산 열 칸을 누르면 Inspector가 그 열로 바뀌므로, 수식 고치기 입력 중이던 내용은 사라진다(머리글을 누를 때와 같음).
   키보드로 칸을 옮기면 Inspector가 이미 그 열을 보여 주는 경우에만 값이 갱신된다(열을 바꾸지 않음).
3. 복사: 계산 열 숫자 칸을 고르고 Ctrl+C. 클립보드에는 전체 값(쉼표 없는 십진 문자열, 예 2.718281828459)이 들어간다.
   오류 칸·빈 칸·입력 열 칸은 가로채지 않는다(브라우저 기본 동작). AG Grid Community에는 칸 복사 기능이 없어 copy 이벤트를 직접 처리한다.
   복사는 단일 칸만이며 다중 범위는 지원하지 않는다.

##### 시험 한계
- jsdom에 ClipboardEvent/DataTransfer가 없어 copy 이벤트는 일반 Event에 clipboardData.setData를 붙여 시험했다. 실제 브라우저 클립보드 기록은 Playwright/수동 확인 필요.

- 알려진 현상: 계산 열 숫자 전체에 천 단위 쉼표를 적용하므로 `YEAR([기준월])` 결과가 `2,026`처럼 보인다(사용자 결정 대기, 03b 22-1).


#### 알려진 현상 / 한계(화면)
- 시험은 jsdom + fetch 모의다. 실제 백엔드 연동, 1920x1080 배치, 수식 칸의 IME(한글 조합) 입력, 자동완성 목록의 실제 위치는 확인하지 못했다(Playwright 스크린샷 단계에서 확인).
- 수식 칸은 일반 `textarea`라 입력창 안에서 색을 칠할 수 없다. 오류 위치는 **입력창 아래의 수식 사본에 표시**하고 "위치 보기"로 입력창 글자를 선택하는 방식이다.
- 오류 위치(`start`/`end`)는 0부터 시작하는 글자 위치, `end`는 포함하지 않는 것으로 읽는다(계약에 단위가 적혀 있지 않다). 길이 0 오류는 그 자리의 글자 하나(수식 끝이면 끝 표시)로 표시한다.
- 같은 사용자의 이전 미리보기 요청을 브라우저가 취소해도 서버에서 아직 끝나지 않았으면 `PREVIEW_BUSY`가 올 수 있다. 그래서 한 번 자동 재시도한다.
- 계산 열의 이름·위치·태그 변경은 FU-1d 화면에 없다(B6은 열 정보 양식이 계산 열에서는 읽기 전용). 필요하면 후속.
- 데이터셋 정의가 바뀌면 열려 있는 수식 보기는 새 정의 버전으로 다시 읽는다. 입력 중인 수식은 그대로 둔다.
- **뷰가 못 만들어졌다**(`/api/health`의 `views_failed_count` > 0 또는 D9): 사유 코드를 본다. `LOCK_TIMEOUT`은 다른 정의 변경이나 긴 읽기와 겹친 것이라 다시 시도하면 된다. `FORMULA_INVALID`는 저장된 수식이 현재 정의에서 컴파일되지 않는 것이다(열 이름·태그·참조한 수식을 확인). `VIEW_VERIFY_FAILED`는 완화책 ③이 불일치를 잡아 되돌린 것이다(서버 로그 확인). `DB_ERROR:`의 SQLSTATE는 PostgreSQL 오류 코드다. 원인을 고친 뒤 D10을 부르거나 백엔드를 재시작한다. 실패 상세는 서버 메모리에만 있어 재시작하면 새로 대조한다.
- **긴 잠금 아래 읽기가 느려 503이 난다**: pg8000 소켓 시간 초과(`connect_args timeout` 5초)가 SQLAlchemy 예외로 감싸이지 않고 `TimeoutError`로 올라오는데, 전역 핸들러가 `TimeoutError`·`ConnectionError`·pg8000 `InterfaceError`도 SQLAlchemy 연결 오류와 같이 503 `SERVICE_UNAVAILABLE`로 답한다(C1 행 조회, D6~D8 등 수식과 무관한 읽기 경로; 로그에는 예외 클래스 이름과 `request_id`만). 문장 시간 초과(`statement_timeout` 5초, SQLSTATE 57014)는 경로에 따라 다르다: D3 미리보기만 07 §5대로 수식 계산 불가로 보아 422 `FORMULA_RUNTIME_ERROR`이고, D6·D7·D8(오류 칸 수·목록)은 DB 지연이라 503 `SERVICE_UNAVAILABLE`이다(`service.raise_read_timeout`; 로그에는 클래스 이름·SQLSTATE·`dataset_id`만). 시험은 `statement_timeout`을 300ms로 낮추고 `ds_N`에 `ACCESS EXCLUSIVE` 잠금을 쥔 세션으로 재현한다(`test_formula_checks_api.py`). 상수 부분식 검사(C0)의 DB 호출이 연결 끊김·소켓 시간 초과로 실패하면 수식 거부(`CONSTANT_PROBE_FAILED`)가 아니라 그 예외가 그대로 올라가 503이 되고, 문장 시간 초과(`57014`)는 이 검사에서 422 `FORMULA_RUNTIME_ERROR`다(수식이 원인인 DB 거부만 `CONSTANT_PROBE_FAILED`). 시작 대조에서는 사유 코드 `DB_UNAVAILABLE`로 기록된다.
- 계산 열 값이 전부 비어 보인다: 해당 데이터셋의 `dv_`/`de_`가 없거나 읽히지 않는 상태일 수 있다(D9 확인). 뷰를 수동으로 지웠다면 재시작 대조가 다시 만든다.
- "수식 엔진이 DB 예외를 냈다"면 변환 규칙의 틈이다: 해당 수식으로 `tests/test_formula_differential.py`의 `Harness`나 `tests/formula_runner.py`의 `fuzz_check`/`differential_check`를 PostgreSQL에서 돌려 재현하고 `functions.py`의 식을 고친다. 알려진 위험: PostgreSQL은 상수 부분식을 계획 시간에 미리 계산해 `CASE`의 쓰이지 않는 갈래에서도 실패할 수 있다(07 §3). `DATE`는 연·일을 범위 안으로 가둔 값으로 만들어 이를 피한다.
- 로그: 수식 관련 로그는 예외 클래스·SQLSTATE·`dataset_id`·`request_id`만 남기고 SQL·상수 값·login_id는 남기지 않는다(시험으로 확인).

## 8. 검증 방법
- 자동(DB 없이, `docker build --target test backend`와 같다): `cd backend && pytest tests/test_formula_*.py tests/test_ddl.py`. 파서·C0·사전 완결성·함수별 `cases`(SQLite 평가 + PostgreSQL 컴파일)·리터럴 렌더러·수식 보기 왕복·무작위 수식 컴파일, 2단계의 단위 시험 `test_formula_units.py`(동시 제한, 뷰 대조 상태, 실패 사유, 뷰 정의 게이트, SQL 함수 검토 목록·DDL 이름 정적 검사), 매트릭스 생성기 시험(사전 항목마다 수식이 있는지, 2인수 전수·3인수 쌍별 덮임)이 돈다.
- 자동(실제 PostgreSQL, `REQUIRE_PG=1`로 건너뛰면 실패): `skills/permission-management/SKILL.md` 8절 절차로 tmpfs 시험 DB를 띄우고 `REQUIRE_PG=1 pytest`. 이 기능의 PostgreSQL 시험:
  - `test_formula_api.py` — D1~D6와 B6 태그 연동(위치는 코드포인트, 형식, 읽기 전용·시간 제한 정규화, 한 트랜잭션 저장, 같은 수식 무변경, 결과 형 변경과 뷰 열 형, 순환 경로 이름, 의존 수식 깨짐 롤백, `DEFINITION_BUSY`, 로그·응답에 SQL·상수 0건, 429).
  - `test_formula_checks_api.py` — D7·D8·C1~C4 계산 열(저장 안 됨, 오류 칸/빈 값 구별, 미리보기와 같은 값, `READ_ONLY`), 정의 변경 직렬화(동시 정의 변경은 한쪽 409, 행 쓰기와 정의 변경 경쟁), 시작 시 해시 대조(다른 뷰만 재생성, 버전 불변, 삭제된 뷰 재생성, 실패해도 시작·`views_failed_count`, D9·D10, 락 시간 초과, 성공한 정의 변경이 실패 기록을 지움, 데이터셋 없으면 뷰 0개).
  - `test_formula_views_pg.py` — 뷰 모양(수식 없어도 `dv_` 1개·팀 열, 열 순서, 오류 칸 NULL + `de_` 코드), 정의 해시(재계산 일치, 표시 이름·순서 무관, 같으면 DDL 건너뜀), `bi_app` 실행·소유자·`bi_readonly` 권한 매트릭스, 완화책 ①(역할 기본값이 `off`여도 엔진은 `on`) ③(롤백), 뷰 정의 허용 목록 게이트, DDL 오류 비노출, **X-26 주입 10종 + 역슬래시 사례 L0~L3 층별 고정**(L0 전체 구성, L1 ②를 끄고 ①만, L2 ①을 끄고 서버 설정 `off` 시나리오 A에서 ③, L3 렌더러 단독 on/off; 판정 효과 0건: `bi_data.evil` 없음, `public.t` 행 수 불변, 뷰 글자 값이 입력과 같거나 롤백 후 변경 전 상태).
  - `test_formula_cases_views.py` — K6 `cases` 전부를 실제 뷰 경유로 실행하고(비교한 수는 거부 사례를 뺀 전체 `cases` 수와 정확히 같아야 하고, 반올림 함수는 허용 오차 없이 정확한 값으로 비교한다) 거부 사례는 D2·D4가 같은 코드로 거부하는지 확인, K7(빈 칸 전파 `MIN`·`MAX`·`SUM`·`SUMTAG`, 글자 비교 대소문자 무시, `IFERROR`, 날짜, 오류 칸이 뷰 NULL + `de_` 코드 + D7·D8 노출).
  - `test_formula_differential.py` (`slow`, 기본 전체 실행에 포함) — **차분 전수 매트릭스**: 사전 전체(연산자 포함) × 인수 구성 × 값 변형 × 출처(수식 상수 / 원본 열 / 계산 열 참조 펼침)에서 미리보기(바인드)와 뷰(리터럴) 결과의 값 글자 표기·`pg_typeof`·오류 코드·DB 예외 여부를 비교한다. 결과 요약은 시험 출력 끝의 "수식 차분 시험 요약"에 나온다(2026-10-12 1d 수정 뒤 실행: 수식 7,353개[통과 7,057 + C0 거부 296], 데이터셋 79개, 비교한 칸 1,353,335개, **불일치 0건, DB 예외 0건**, 오류 칸 E1 896·E2 6,720·E3 18,202, 빈 값 29,912). 값 변형에 긴 소수(정수부 12자리 + 소수 10자리와 그 음수, 소수 38자리)가 들어 있다. **거부 건수는 정확히 단정한다**: 거부 코드는 `CONSTANT_ERROR` 하나뿐이고, 거부된 수식의 집합이 생성기가 표시한 기대값(`tests/formula_matrix.py`의 `CONSTANT_ERROR_ORACLE`: `/` 0으로 나눔 E1 14건, `LEFT`·`RIGHT` 길이 범위 E2 각 60건, `DATE` 범위 E3 162건 = 296건; DB·변환기를 쓰지 않고 파이썬으로 따로 계산)과 수식 단위로 같아야 하며 통과 수도 `전체 - 296`으로 정확히 같아야 한다(`error_when`이 있는 새 사전 항목은 기대값 계산을 더하지 않으면 시험이 실패한다). 실패 메시지는 코드별·항목별 집계와 기대 밖/누락 사례를 보인다. 또 X-26.3 "남은 22건"의 원인 4가지(10**30 BIGINT 바인드, 날짜-글자 비교, `%`, `0/0`·`None + 1`)가 닫혔음을 하나씩 확인한다(대조군 포함).
  - 전체 결과(2026-10-12, 1d reviewer·QA 지적 수정 뒤): 실제 PostgreSQL `REQUIRE_PG=1` `slow` 포함 전체 **2,820 passed, 98 skipped**(skip 98은 모두 1단계의 SQLite 전용 시험이 "PostgreSQL 전용 함수/상수 조건이라 PostgreSQL 시험으로 넘긴다"고 의도해 건너뛴 것이고 `pg` 변형 skip은 0), DB 없이(`slow` 제외) 1,976 passed(PostgreSQL 변형은 건너뜀). 전체 실행 약 21분(차분 행렬만의 시간은 이번에 따로 재지 않았다. 이전 수식 5,552개에서 약 5분 30초). `python -m migrations.roundtrip`과 `alembic check` 통과(스키마 변경 없음).
  - 1d 수정에서 더한 시험: `test_formula_units.py`·`test_ddl.py`(뷰 게이트의 SQL 함수 허용 목록·글자 바인드 금지 문자, 확인 질의 모양·값의 **실행 전** 확인, 렌더 글자와 `CreateView` 대조의 실행 전 확인(첫 ` AS ` 뒤 전체가 렌더 글자와 정확히 같아야 한다, 일부만 같으면 거부), `RenderedSelect`·`@compiles`·`literal_column` 위치 AST 검사[별칭 import·속성 사슬 포함]), `test_formula_pg.py`(`ROUND`·`ROUNDUP`·`ROUNDDOWN`을 파이썬 `Decimal` 기준값과 긴 소수 21개 값 × 자릿수 -10~10으로 정확히 대조), `test_formula_c0.py`(오류 문구의 단위·조사 겹침 점검, 상수 검사 중 연결 끊김·시간 초과의 구분), `test_formula_checks_api.py`(소켓 시간 초과 503, 시작 대조 시간 실측), `test_errors.py`(감싸지 않은 연결 계층 예외 503).
  - 정적 표 권한·왕복: `test_static_acl.py`(`formulas`·`formula_deps` 권한 매트릭스, 제약), `test_migrations.py`·`test_roundtrip_tools.py`, 권한 매트릭스 `test_permission_matrix.py`에 D1~D10 × 역할.
- 마이그레이션: 빈 새 DB에서 `python -m migrations.roundtrip`(`0005` 단계 포함)과 `alembic check`. `ds_1`·`dv_1`·`de_1`이 있는 상태에서 `0005`·`0004`를 내려도 동적 객체가 남고 다시 올린 뒤 `alembic check`가 통과함을 확인했다.
- 수동: 화면 점검은 5절 자리에 합쳐질 프런트 노트를 따른다. 엑셀 실제 값과의 대조는 하지 않는다(클라우드에 Excel 없음). `lower()`의 DB 로케일 영향은 확인하지 못했다(시험 사례는 ASCII·한글만).

- 프런트 자동 시험:
  - `frontend/src/features/formula/autocomplete.test.ts`: 자동완성 자리 판정(함수·`[열]`·`SUMTAG("태그")`, 글자 상수 안), 후보 순서, 넣기, 칩 삽입, 오류 위치 구간(겹침·수식 밖·길이 0·코드포인트 -> UTF-16).
  - `formula/editor.test.tsx`: 편집기(칩, 키보드 자동완성, 디바운스 검사 1회, 오류 위치 표시·위치 보기, 미리보기 값/오류/빈 값 구별, 이전 요청 취소·낡은 결과 무시, `PREVIEW_BUSY` 자동 재시도·버튼, 저장 입력, 오류 코드별 분기).
  - `formula/workspace.test.tsx`: 작업공간 연결(계산 열 추가 본문 `expected_version`, 수식 보기, 수식 고치기 PUT 본문, `result_type_changed`, 버전 충돌 재읽기·수식 유지, 순환 경로, 권한 없음 읽기 전용, 그리드 오류 칸·빈 칸 구별·계산 열 머리글, 계산 열 없으면 D1 미호출).
  - `formula/api.test.ts`: 응답 읽기 관용(D1 `signature` 형태, 목록 배열/페이지). `checks/checks.test.tsx`: S5(D7·D8, 쪽 이동, 딥링크, 429)와 S9 뷰 재생성(D9·D10, 관리자 한정). `errors.test.ts`: 수식 코드 문구.
  - 가짜 서버는 `formula/test-server.ts`(계약대로 응답을 흉내 낸 것이며 실제 백엔드와 같다는 보증은 아니다).

## 9. 연관 Skill
- `dataset-definition`: 계산 열(`kind=formula`)의 정의·태그(`SUMTAG`)·표시 이름을 소유한다. 열 이름 변경은 AST가 열 번호 참조라 수식에 영향이 없다. 정의 변경 진입점(`definition.py`)이 이 모듈의 훅을 부르고 태그 변경의 순환을 재검사한다.
- `data-entry`: 행 조회가 계산 열 값과 오류 칸을 `RowViewPort`로 받는다. 원본 열 값의 NFC 정규화와 글자 규칙이 이 엔진의 상수 규칙과 같은 방향이다. 계산 열 키로 쓰면 `READ_ONLY`다.
- `permission-management`: 수식 편집·미리보기는 정의(팀) 권한, 열람은 인증된 모두. PostgreSQL 시험 절차(8절)를 쓴다.
- `local-environment`: `/api/health`의 `views`·`views_failed_count`, 시작 자가 점검(`standard_conforming_strings`), 마이그레이션 왕복.
- `admin-cleanup`: 잘못 만든 계산 열·뷰를 관리자가 수동으로 정리하는 절차(`formulas`·`formula_deps`·`dv_`·`de_`).
- `dashboard-link`(FU-1e): `dv_<번호>` 뷰가 Superset 가상 데이터셋의 원천이다(고정 SQL `SELECT * FROM bi_data.dv_<번호>`). 계산 열이 추가·수정되어 커밋되면 같은 요청이 동기화를 요청하고, Superset 열 표시 이름에 계산 열 이름이 `c_<번호>`로 붙는다.
