---
name: formula-column
description: 같은 행 수식으로 계산 열을 만들고 고치는 기능의 수식 엔진과 API. 엑셀 느낌의 수식("[매출] - [비용]", IF, ROUND, SUMTAG 등)을 검사하고 쉬운 한국어 오류와 위치를 알려 주며, 빈 값 전파·오류 칸 규칙을 지켜 DB 뷰(dv_·de_)로 계산한다. 저장 전 미리보기, 수식 보기, 계산 오류 칸 점검, 뷰 재생성 점검까지 포함한다. "수식 검사", "계산 열", "함수 추가", "수식이 이상해요", "오류 칸", "뷰 다시 만들기" 같은 요청에 쓴다.
---

# formula-column — 수식 엔진 (FU-1d)

> **구현 상태(2026-10-12)**: 1단계(`backend/app/formula/` 순수 라이브러리) + **2단계 backend 완료** — `formulas`·`formula_deps` 표(revision `0005`), 정의 변경 훅이 만드는 뷰 `dv_<번호>`·`de_<번호>`, 정의 해시와 시작 시 재생성, 05 D1~D10 API, `RowViewPort` 구현, 미리보기-뷰 차분 시험 전수 매트릭스. **화면(S4 수식 편집기·수식 보기, S5 점검, S9 뷰 재생성 구역)의 사용법은 프런트 노트(`_workspace/fu1d-frontend-skill-notes.md`)를 메인이 5·7절의 표시된 자리에 합친다.**

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
- **사람(화면)**: <!-- 합치기 자리: `_workspace/fu1d-frontend-skill-notes.md` "5절 사람" (계산 열 만들기·수식 보기·수식 고치기·입력 그리드의 계산 열·S5 점검·S9 뷰 재생성 구역). 메인이 합친다. -->
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
- **함수 추가**: `backend/app/formula/functions.py`에 `FunctionSpec` 하나(+ `cases`)를 더하고 `_ALL_SPECS`에 넣는다. 파서·C0·변환기·도움말·API·**차분 시험 행렬**은 고치지 않는다(`tests/test_formula_registry.py`가 임시 함수로 증명하고, `tests/formula_matrix.py`가 사전에서 행렬을 자동으로 키운다). 새 SQL 함수(`func.xxx`)를 쓰면 `tests/test_formula_units.py`의 검토 목록 시험이 알려 준다. 함수 변경으로 변환 SQL이 바뀌면 정의 해시가 달라져 다음 시작 때 해당 데이터셋의 뷰만 자동으로 다시 만들어진다. 항목 규칙은 `registry.py` 머리말.
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
- **완화책 3가지**(07 §4-3, X-26): ① 엔진 연결 때 `startup_params={"standard_conforming_strings": "on"}`로 세션 설정을 고정(`app/db.py`; 시작 자가 점검이 `on`인지 다시 확인) ② 역슬래시·제어문자·NUL·서식 문자 거부(C0와 리터럴 렌더러) ③ 뷰를 만든 직후 같은 트랜잭션에서 뷰 열 이름·개수를 읽어 확인하고, 뷰 정의에 들어간 모든 글자 상수를 같은 렌더러로 `SELECT`해 입력과 같은지 비교한다(어긋나면 `DdlVerificationError`로 롤백). 뷰 정의 SELECT는 `ddl` 게이트가 먼저 확인한다(자기 `ds_<번호>` 하나만 읽음, `text()`·`literal_column`·서브쿼리 없음, 바인드는 숫자·글자·참거짓·날짜뿐, 출력 열 이름은 번호 규칙). 뷰 정의 SQL에는 수식 상수가 들어 있으므로 **DB 오류는 SQL 없이(`DdlExecutionError`, SQLSTATE만) 올려 로그·응답에 상수가 남지 않는다.**
- **읽기 전용·시간 제한·동시 제한**: D2~D3·D6~D8은 트랜잭션별 `transaction_read_only=on`과 `statement_timeout=5초`(`set_config`)로 실행한다. 미리보기는 사용자당 동시 1건, 미리보기·오류 칸 조회(D7·D8)·계산 열이 있는 데이터셋의 행 조회(C1)는 전역 동시 2건(풀 5개 중 3개를 일반 요청용으로 남김)이고 넘으면 429 `PREVIEW_BUSY`다(기다리지 않고 바로 거절). 모두 코드 상수이며 새 환경변수는 없다.
- **`RowViewPort`**: `dv_`와 `de_`를 `row_id`로 결합해 C1·C2~C4 응답의 계산 열 값과 `errors["<열 번호>"] = "E1"`을 준다. 뷰를 읽지 못하면(만들기에 실패한 데이터셋) 요청을 깨뜨리지 않고 계산 열을 빈 값으로 돌려준다(D9가 알린다). C2~C4가 계산 열 키를 보내면 422 `READ_ONLY`다.
- **계약 구현 메모**: ① 새 열의 수식은 그 열이 아직 없으므로 D4에서 자기 이름을 쓰면 `UNKNOWN_COLUMN`(`FORMULA_INVALID`)이고, 순환 `FORMULA_CIRCULAR`는 D5와 태그 변경(B6)에서 난다. ② 태그가 붙은 계산 열의 결과 형이 숫자가 아니게 되면 422 `VALIDATION_ERROR`(필드 `expression`, 코드 `BAD_FORMAT`, 05 §3 기존 코드)로 막는다(먼저 태그를 지운다). ③ 편집 중인 수식이 아닌 다른 계산 열의 수식이 깨지면 `FORMULA_INVALID`의 문구에 `'열 이름' 열의 수식 문제:`가 붙고 위치는 `0`~`0`이다. ④ `GET /api/health`의 `views`는 시작 대조와 이후 정의 변경이 확인한 활성 데이터셋 수이고 `views_failed_count`는 그중 실패 수다(프로세스 메모리, worker 1개 전제).

## 7. 실패 시 확인 방법
- 사용자에게 보이는 검사 오류는 `issues[].message`(쉬운 말)와 `start`/`end`다. 코드: `UNEXPECTED_END`·`UNEXPECTED_TOKEN`·`UNCLOSED_STRING`·`UNCLOSED_COLUMN`·`BARE_NAME`(문법), `UNKNOWN_COLUMN`·`UNKNOWN_FUNCTION`, `ARG_COUNT`·`ARG_TYPE`·`TYPE_MISMATCH`·`CONST_REQUIRED`·`CONST_RANGE`, `TEXT_CONSTANT_INVALID`·`NUMBER_INVALID`, `TAG_EMPTY`, `CIRCULAR`·`CHAIN_TOO_LONG`, `TOO_MANY_NODES`·`TOO_DEEP`·`TOO_COMPLEX`, `CONSTANT_ERROR`(상수 부분식 오류: `1/0`, `DATE(0,1,1)`, `LEFT("가",-1)`).
- API 오류 코드와 대응: 422 `FORMULA_INVALID`는 `details.errors`를 본다. 422 `FORMULA_CIRCULAR`는 `details.path`의 열 이름 경로를 보고 수식을 고친다. 409 `DEFINITION_VERSION_MISMATCH`는 정의를 다시 읽는다. 503 `DEFINITION_BUSY`(락 대기 1초 초과)는 잠시 뒤 다시 시도한다. 429 `PREVIEW_BUSY`는 `retry_after`초 뒤 다시 시도한다. 422 `FORMULA_RUNTIME_ERROR`는 시간 초과이거나 계산 불가 수식이다(서버 로그에 예외 클래스와 SQLSTATE만 남는다).
- 화면 문구 표: <!-- 합치기 자리: `_workspace/fu1d-frontend-skill-notes.md` "7절 오류 문구 표" -->
- **뷰가 못 만들어졌다**(`/api/health`의 `views_failed_count` > 0 또는 D9): 사유 코드를 본다. `LOCK_TIMEOUT`은 다른 정의 변경이나 긴 읽기와 겹친 것이라 다시 시도하면 된다. `FORMULA_INVALID`는 저장된 수식이 현재 정의에서 컴파일되지 않는 것이다(열 이름·태그·참조한 수식을 확인). `VIEW_VERIFY_FAILED`는 완화책 ③이 불일치를 잡아 되돌린 것이다(서버 로그 확인). `DB_ERROR:`의 SQLSTATE는 PostgreSQL 오류 코드다. 원인을 고친 뒤 D10을 부르거나 백엔드를 재시작한다. 실패 상세는 서버 메모리에만 있어 재시작하면 새로 대조한다.
- 계산 열 값이 전부 비어 보인다: 해당 데이터셋의 `dv_`/`de_`가 없거나 읽히지 않는 상태일 수 있다(D9 확인). 뷰를 수동으로 지웠다면 재시작 대조가 다시 만든다.
- "수식 엔진이 DB 예외를 냈다"면 변환 규칙의 틈이다: 해당 수식으로 `tests/test_formula_differential.py`의 `Harness`나 `tests/formula_runner.py`의 `fuzz_check`/`differential_check`를 PostgreSQL에서 돌려 재현하고 `functions.py`의 식을 고친다. 알려진 위험: PostgreSQL은 상수 부분식을 계획 시간에 미리 계산해 `CASE`의 쓰이지 않는 갈래에서도 실패할 수 있다(07 §3). `DATE`는 연·일을 범위 안으로 가둔 값으로 만들어 이를 피한다.
- 로그: 수식 관련 로그는 예외 클래스·SQLSTATE·`dataset_id`·`request_id`만 남기고 SQL·상수 값·login_id는 남기지 않는다(시험으로 확인).

## 8. 검증 방법
- 자동(DB 없이, `docker build --target test backend`와 같다): `cd backend && pytest tests/test_formula_*.py tests/test_ddl.py`. 파서·C0·사전 완결성·함수별 `cases`(SQLite 평가 + PostgreSQL 컴파일)·리터럴 렌더러·수식 보기 왕복·무작위 수식 컴파일, 2단계의 단위 시험 `test_formula_units.py`(동시 제한, 뷰 대조 상태, 실패 사유, 뷰 정의 게이트, SQL 함수 검토 목록·DDL 이름 정적 검사), 매트릭스 생성기 시험(사전 항목마다 수식이 있는지, 2인수 전수·3인수 쌍별 덮임)이 돈다.
- 자동(실제 PostgreSQL, `REQUIRE_PG=1`로 건너뛰면 실패): `skills/permission-management/SKILL.md` 8절 절차로 tmpfs 시험 DB를 띄우고 `REQUIRE_PG=1 pytest`. 이 기능의 PostgreSQL 시험:
  - `test_formula_api.py` — D1~D6와 B6 태그 연동(위치는 코드포인트, 형식, 읽기 전용·시간 제한 정규화, 한 트랜잭션 저장, 같은 수식 무변경, 결과 형 변경과 뷰 열 형, 순환 경로 이름, 의존 수식 깨짐 롤백, `DEFINITION_BUSY`, 로그·응답에 SQL·상수 0건, 429).
  - `test_formula_checks_api.py` — D7·D8·C1~C4 계산 열(저장 안 됨, 오류 칸/빈 값 구별, 미리보기와 같은 값, `READ_ONLY`), 정의 변경 직렬화(동시 정의 변경은 한쪽 409, 행 쓰기와 정의 변경 경쟁), 시작 시 해시 대조(다른 뷰만 재생성, 버전 불변, 삭제된 뷰 재생성, 실패해도 시작·`views_failed_count`, D9·D10, 락 시간 초과, 성공한 정의 변경이 실패 기록을 지움, 데이터셋 없으면 뷰 0개).
  - `test_formula_views_pg.py` — 뷰 모양(수식 없어도 `dv_` 1개·팀 열, 열 순서, 오류 칸 NULL + `de_` 코드), 정의 해시(재계산 일치, 표시 이름·순서 무관, 같으면 DDL 건너뜀), `bi_app` 실행·소유자·`bi_readonly` 권한 매트릭스, 완화책 ①(역할 기본값이 `off`여도 엔진은 `on`) ③(롤백), 뷰 정의 허용 목록 게이트, DDL 오류 비노출, **X-26 주입 10종 + 역슬래시 사례 L0~L3 층별 고정**(L0 전체 구성, L1 ②를 끄고 ①만, L2 ①을 끄고 서버 설정 `off` 시나리오 A에서 ③, L3 렌더러 단독 on/off; 판정 효과 0건: `bi_data.evil` 없음, `public.t` 행 수 불변, 뷰 글자 값이 입력과 같거나 롤백 후 변경 전 상태).
  - `test_formula_cases_views.py` — K6 `cases` 전부를 실제 뷰 경유로 실행하고 거부 사례는 D2·D4가 같은 코드로 거부하는지 확인, K7(빈 칸 전파 `MIN`·`MAX`·`SUM`·`SUMTAG`, 글자 비교 대소문자 무시, `IFERROR`, 날짜, 오류 칸이 뷰 NULL + `de_` 코드 + D7·D8 노출).
  - `test_formula_differential.py` (`slow`, 기본 전체 실행에 포함) — **차분 전수 매트릭스**: 사전 전체(연산자 포함) × 인수 구성 × 값 변형 × 출처(수식 상수 / 원본 열 / 계산 열 참조 펼침)에서 미리보기(바인드)와 뷰(리터럴) 결과의 값 글자 표기·`pg_typeof`·오류 코드·DB 예외 여부를 비교한다. 결과 요약은 시험 출력 끝의 "수식 차분 시험 요약"에 나온다(이번 실행: 수식 5,552개[통과 5,352 + C0 거부 200], 비교한 칸 679,664개, **불일치 0건, DB 예외 0건**, 오류 칸 E1 572·E2 4,000·E3 9,384, 빈 값 21,227). 또 X-26.3 "남은 22건"의 원인 4가지(10**30 BIGINT 바인드, 날짜-글자 비교, `%`, `0/0`·`None + 1`)가 닫혔음을 하나씩 확인한다(대조군 포함).
  - 전체 결과(2026-10-12, 이 기능 구현 직후): 실제 PostgreSQL `REQUIRE_PG=1` 전체 **2,754 passed, 89 skipped**(skip 89는 모두 1단계의 SQLite 전용 시험이 "PostgreSQL 전용 함수/상수 조건이라 PostgreSQL 시험으로 넘긴다"고 의도해 건너뛴 것이고 `pg` 변형 skip은 0), DB 없이 1,921 passed(PostgreSQL 변형 922개는 건너뜀). 전체 실행 약 19분(차분 행렬이 약 5분 30초).
  - 정적 표 권한·왕복: `test_static_acl.py`(`formulas`·`formula_deps` 권한 매트릭스, 제약), `test_migrations.py`·`test_roundtrip_tools.py`, 권한 매트릭스 `test_permission_matrix.py`에 D1~D10 × 역할.
- 마이그레이션: 빈 새 DB에서 `python -m migrations.roundtrip`(`0005` 단계 포함)과 `alembic check`. `ds_1`·`dv_1`·`de_1`이 있는 상태에서 `0005`·`0004`를 내려도 동적 객체가 남고 다시 올린 뒤 `alembic check`가 통과함을 확인했다.
- 수동: 화면 점검은 5절 자리에 합쳐질 프런트 노트를 따른다. 엑셀 실제 값과의 대조는 하지 않는다(클라우드에 Excel 없음). `lower()`의 DB 로케일 영향은 확인하지 못했다(시험 사례는 ASCII·한글만).

## 9. 연관 Skill
- `dataset-definition`: 계산 열(`kind=formula`)의 정의·태그(`SUMTAG`)·표시 이름을 소유한다. 열 이름 변경은 AST가 열 번호 참조라 수식에 영향이 없다. 정의 변경 진입점(`definition.py`)이 이 모듈의 훅을 부르고 태그 변경의 순환을 재검사한다.
- `data-entry`: 행 조회가 계산 열 값과 오류 칸을 `RowViewPort`로 받는다. 원본 열 값의 NFC 정규화와 글자 규칙이 이 엔진의 상수 규칙과 같은 방향이다. 계산 열 키로 쓰면 `READ_ONLY`다.
- `permission-management`: 수식 편집·미리보기는 정의(팀) 권한, 열람은 인증된 모두. PostgreSQL 시험 절차(8절)를 쓴다.
- `local-environment`: `/api/health`의 `views`·`views_failed_count`, 시작 자가 점검(`standard_conforming_strings`), 마이그레이션 왕복.
- `admin-cleanup`: 잘못 만든 계산 열·뷰를 관리자가 수동으로 정리하는 절차(`formulas`·`formula_deps`·`dv_`·`de_`).
- `dashboard-link`(예정, FU-1e): `dv_<번호>` 뷰가 Superset 가상 데이터셋의 원천이다.
