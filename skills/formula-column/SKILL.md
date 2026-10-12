---
name: formula-column
description: 같은 행 수식으로 계산 열을 만드는 기능의 수식 엔진. 엑셀 느낌의 수식("[매출] - [비용]", IF, ROUND, SUMTAG 등)을 검사하고 쉬운 한국어 오류와 위치를 알려 주며, 빈 값 전파·오류 칸 규칙을 지켜 SQLAlchemy 표현식으로 바꾼다. "수식 검사", "계산 열", "함수 추가", "수식이 이상해요" 같은 요청에 쓴다. 현재는 DB를 모르는 라이브러리(1d 1단계)까지 구현되어 있고 API·뷰 생성·수식 편집기는 2단계에서 이 Skill에 더한다.
---

# formula-column — 수식 엔진 (FU-1d)

> **구현 상태(2026-10-12)**: 1단계 = `backend/app/formula/` 순수 라이브러리(파서, 함수 사전, C0 검사, 변환기, 수식 보기, 리터럴 렌더러)와 시험. **2단계 대기 중**: `formulas`·`formula_deps` 표(revision `0005`), `dv_`·`de_` 뷰 생성과 정의 해시·시작 시 재생성, 미리보기·검사·저장 API(05 D1~D10), `RowViewPort` 구현, 수식 편집기(S4)·점검(S5) 화면, 미리보기-뷰 차분 시험의 전체 매트릭스. 아래 5·6·8절에서 "2단계"라고 쓴 부분은 아직 없다.

## 1. 목적
팀 사용자가 엑셀에서 쓰던 계산을 데이터셋의 계산 열로 옮길 수 있게, 같은 행 수식을 안전하게 검사하고 DB 식으로 바꾼다. 수식이 틀리면 SQL 용어 없이 "어디가 왜 틀렸는지"를 알려 주고, 빈 칸과 오류 칸을 0으로 오해하지 않게 구별한다. 함수 추가는 사전 항목 한 개와 시험 사례로 끝난다.

## 2. 사용 조건 / 사전 요구사항
- 1단계 라이브러리는 로그인·DB가 필요 없다(순수 파이썬). `lark==1.3.1`(MIT, 승인 AP-15)이 설치되어 있어야 한다(`backend/requirements*.txt`).
- 2단계 API는 정의(팀) 권한이 필요하다(검사·미리보기·만들기·수정), 수식 보기(D6)·오류 칸 점검(D7·D8)은 인증된 모두, 뷰 점검(D9·D10)은 관리자(05 §4). 데이터셋·열이 `dataset-definition`으로 만들어져 있어야 한다.
- 상수 부분식 검사(`1/0` 등)는 DB 상수 `SELECT`가 필요하다(`const_probe`, 2단계가 제공).

## 3. 입력
수식은 글자 하나다. 문법(07 §1):
- 열 `[열 이름]`(이름 안에 `[` `]` `"` 불가), 글자 `"가나""다"`(`""`는 따옴표 하나), 숫자 `1234.5`, `TRUE`/`FALSE`, 함수 `NAME(…)`. 날짜 상수와 `NULL` 상수는 없다(날짜는 `DATE(연, 월, 일)`, 빈 값은 열 값에서만 생긴다). `%`·`^`·`!=`는 없다(같지 않음은 `<>`).
- 우선순위(낮음 -> 높음): 비교 `= <> < <= > >=` < `&` < `+ -` < `* /` < 부호. 같은 단계는 왼쪽부터.
- 함수: `+ - * /`, 비교 6종, `&`, `IF`, `AND OR NOT`, `IFERROR`, `ROUND ROUNDUP ROUNDDOWN`(자릿수는 직접 쓴 정수 -10~10), `ABS`, `MIN MAX`(2개 이상), `SUM`, `LEFT RIGHT`, `LEN`, `TRIM`, `YEAR MONTH`, `DATE`, `SUMTAG("태그")`. 이름·인수·엑셀과 차이·도움말은 `FunctionRegistry.describe()`(= 05 D1)에서 자동 생성된다.
- 상한: 수식 2,000자, 글자 상수 200자(NFC 정규화 뒤, 역슬래시·제어·서식 문자·NUL 거부), 숫자 38자리, 펼친 노드 2,000개, AST 깊이 40, 참조 사슬 10단계, 변환 결과 SQL 노드 50,000개. 항이 41개 이상인 덧셈 `a+b+c…`은 깊이 때문에 거부되므로 `SUM(…)`을 쓴다.

## 4. 출력
- `compile_formula(...)` -> `CompileResult`: `ok`, `issues[{code, message, start, end}]`(위치는 원문 코드포인트 번호), `result_type`, `ast`(열 번호 참조; `ast_json`/`ast_hash`가 저장용), `deps`(`formula_deps`), `source_columns`, `sumtag_columns`, `functions_used`, `node_count`, **`value`(값 식)·`error`(오류 식)** SQLAlchemy 표현식.
- 값 식은 오류 칸이면 NULL, 오류 식은 정상·빈 값이면 NULL이고 오류면 셀 오류 코드(smallint 1~3 = `E1` 0으로 나눔, `E2` 글자 길이 범위, `E3` 날짜 범위; 문구는 `CELL_ERROR_MESSAGES_KO`). 오류가 날 수 없는 식은 `error=None`.
- 의미 규칙(07 §3): 빈 값은 0이 아니라 결과도 빈 값(`MIN`·`MAX`·`SUM`·`SUMTAG` 포함 전파), 글자 `=`·`<>`는 대소문자 무시, 숫자-글자·날짜-글자 자동 변환 없음, `IF`는 고른 쪽만, `IFERROR`는 오류 칸일 때만 대체값(빈 값은 그대로), 평가 순서는 인수 오류 > 인수 빈 값 > 자기 조건.
- 모든 상수는 `CAST(… AS 형)`이다. 같은 표현식을 그대로 실행하면 미리보기(바인드), `render_literal_sql`로 렌더하면 뷰 정의와 같은 글자다.
- 저장하지 않는다(1단계). 2단계가 `formulas`·`formula_deps`·`dv_`·`de_`를 쓴다.

## 5. 실행 방법
- 사람: 2단계에서 수식 편집기(S4)에서 쓴다. 1단계에는 화면이 없다.
- AI/개발자(파이썬):
  ```python
  from app.formula import ColumnInfo, compile_formula, render_text
  cols = [ColumnInfo(1, "매출", "number"), ColumnInfo(2, "비용", "number")]
  r = compile_formula("IFERROR(([매출] - [비용]) / [매출], 0)", cols, const_probe=probe)
  r.ok, r.issues, r.value, r.error   # probe: 상수 SELECT 평가기(2단계), 없으면 상수 오류 검사만 건너뜀(r.const_probe_skipped)
  render_text(r.ast, cols)           # 열 이름을 풀어 쓴 수식 보기
  ```
  계산 열을 참조하려면 그 열을 `ColumnInfo(id, name, type, kind="formula", formula=<저장된 AST>)`로 준다(`ast_from_json`). 편집 중인 기존 열은 `column_id=`, 새 열의 태그는 `tag=`로 알린다.
- **함수 추가**: `backend/app/formula/functions.py`에 `FunctionSpec` 하나(+ `cases`)를 더하고 `_ALL_SPECS`에 넣는다. 파서·C0·변환기·도움말은 고치지 않는다(`tests/test_formula_registry.py`가 임시 함수로 증명). 항목 규칙은 `registry.py` 머리말.

## 6. 관련 UI / API / command / DB
- UI: 수식 편집기(S4)·점검(S5) — 2단계.
- API(2단계, 05 §2-4): D1 `GET /formulas/functions`, D2 `POST /datasets/{id}/formulas/check`, D3 `…/formulas/preview`, D4 계산 열 만들기, D5 수정, D6 수식 보기, D7·D8 오류 칸 점검, D9·D10 뷰 재생성 점검(관리자).
- command: 없음.
- DB: 1단계는 DB를 읽고 쓰지 않는다. 2단계 표 `formulas`, `formula_deps`, 뷰 `bi_data.dv_<번호>`, `bi_data.de_<번호>`.
- 코드: `backend/app/formula/` — `api.py`(공개 인터페이스와 가정), `parser.py`, `analyze.py`(C0), `cycles.py`, `convert.py`, `registry.py`·`functions.py`(함수 사전), `literals.py`(리터럴 렌더러 접점), `textview.py`(수식 보기), `errors.py`(문구 사전).

## 7. 실패 시 확인 방법
- 사용자에게 보이는 오류는 `issues[].message`(쉬운 말)와 `start`/`end`다. 코드: `UNEXPECTED_END`·`UNEXPECTED_TOKEN`·`UNCLOSED_STRING`·`UNCLOSED_COLUMN`·`BARE_NAME`(문법), `UNKNOWN_COLUMN`·`UNKNOWN_FUNCTION`, `ARG_COUNT`·`ARG_TYPE`·`TYPE_MISMATCH`·`CONST_REQUIRED`·`CONST_RANGE`, `TEXT_CONSTANT_INVALID`·`NUMBER_INVALID`, `TAG_EMPTY`, `CIRCULAR`·`CHAIN_TOO_LONG`, `TOO_MANY_NODES`·`TOO_DEEP`·`TOO_COMPLEX`, `CONSTANT_ERROR`(상수 부분식 오류).
- "수식 엔진이 DB 예외를 냈다"면 변환 규칙의 틈이다: 해당 수식으로 `tests/formula_runner.py`의 `fuzz_check`/`differential_check`를 PostgreSQL에서 돌려 재현하고 `functions.py`의 식을 고친다. 알려진 위험: PostgreSQL은 상수 부분식을 계획 시간에 미리 계산해 `CASE`의 쓰이지 않는 갈래에서도 실패할 수 있다(07 §3). `DATE`는 연·일을 범위 안으로 가둔 값으로 만들어 이를 피한다.
- 로그/Health: 1단계에는 없다.

## 8. 검증 방법
- 자동(DB 없이, `docker build --target test backend`와 같다): `cd backend && pytest tests/test_formula_*.py tests/test_ddl.py`. 파서(우선순위·따옴표·위치 오류·상한), C0 거부 사례(위치 포함), 사전 완결성과 함수 추가 증명, 함수별 `cases`(SQLite 평가 + PostgreSQL 컴파일·모든 상수 `CAST` 확인), 빈 값 전파와 오류 의미 규칙, 순환·`SUMTAG`, 리터럴 렌더러와 X-26 주입 10종·역슬래시 사례, 수식 보기 왕복, 무작위 수식 컴파일.
- 자동(실제 PostgreSQL): `skills/permission-management/SKILL.md` 8절 절차로 tmpfs 시험 DB를 띄우고 `REQUIRE_PG=1 pytest tests/test_formula_pg.py`. 모든 `cases`를 실제 PostgreSQL에서 평가하고, 미리보기(바인드)와 뷰(리터럴 렌더)의 값·`pg_typeof`·오류 코드 일치, 주입 사례 라운드트립, 무작위 수식 × 경계 값 행에서 DB 예외 0건을 확인한다.
- 수동: 2단계 화면이 생기면 오류 문구가 쉬운 말인지, 빈 칸과 오류 칸이 다르게 보이는지 확인한다.
- 미실시(2단계): 엑셀 실제 값과의 대조는 하지 않는다(클라우드에 Excel 없음). `lower()`의 DB 로케일 영향은 확인하지 못했다(시험 사례는 ASCII·한글만).

## 9. 연관 Skill
- `dataset-definition`: 계산 열(`kind=formula`)의 정의·태그(`SUMTAG`)·표시 이름을 소유한다. 열 이름 변경은 AST가 열 번호 참조라 수식에 영향이 없다. 태그 변경은 순환을 다시 검사한다(2단계 훅).
- `data-entry`: 행 조회가 계산 열 값과 오류 칸을 `RowViewPort`(2단계)로 받는다. 원본 열 값의 NFC 정규화와 글자 규칙이 이 엔진의 상수 규칙과 같은 방향이다.
- `permission-management`: 수식 편집·미리보기는 정의(팀) 권한, 열람은 인증된 모두. PostgreSQL 시험 절차(8절)를 쓴다.
- `dashboard-link`(예정, FU-1e): `dv_<번호>` 뷰가 Superset 가상 데이터셋의 원천이다.
