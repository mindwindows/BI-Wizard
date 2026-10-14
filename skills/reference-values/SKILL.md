---
name: reference-values
description: 연도별로 바뀌는 기준값(예: 전기요금 단가)을 관리자가 등록·정정하고, 수식에서 REF("이름")으로 읽는 기능(FU-3). "단가를 수식에 넣고 싶다", "연도별 기준값을 등록하려면", "기준값을 정정하면 결과가 바뀌나", "E4 오류가 났다" 같은 요청에 해당한다.
---

# 기준값 (reference-values, FU-3)

## 1. 목적
데이터셋 행의 **기준 날짜가 속한 연도**에 맞는 숫자 값(단가·계수 등)을 수식이 자동으로 읽게 한다. 값은 포털의 기준값 화면에서 관리자가 연도별로 등록하고, 수식에서는 `REF("항목이름")` 한 줄로 쓴다. 같은 항목은 모든 데이터셋과 팀이 함께 쓴다(팀마다 다른 값이 필요하면 이름에 팀을 붙인다. 예: `전기요금_A팀`).

## 2. 사용 조건 / 사전 요구사항
- `local-environment` 통과(`migrate`가 `0009`까지 적용: 표 `reference_items`·`reference_values`).
- 읽기(R1·R3): 로그인한 누구나. **쓰기(R2·R4·R5)와 사용처 조회(R6)는 관리자만**이다. 비관리자는 본문 검증보다 먼저 403 `FORBIDDEN`을 받는다.
- `REF`를 쓰려는 데이터셋에는 **기준 날짜 열**이 있어야 한다(`dataset-definition`).
- 기준값은 **숫자만**이다. 글자 기준값(예: "1월")은 없다. 시기를 고르는 일은 기준 날짜 열과 대시보드 기간 필터가 맡는다.

## 3. 입력
- 항목(R2 `POST /api/reference-items`): `name`(필수, 1~50자, `[` `]` `"` 역슬래시와 제어·서식 문자 금지, **나중에 바꾸거나 지울 수 없다**), `description`(선택, 200자 이하. 수식 편집기 자동완성에 보인다).
- 연도 값(R4 `POST /api/reference-items/{id}/values`): `year`(정수 1900~9999), `value`(**글자로 보낸 십진수**, 38자리 이하, 쉼표·지수·글자 불가, 예 `"12.50"`).
- 정정(R5 `PATCH /api/reference-items/{id}/values/{value_id}`): `value`만. `year`·`item_id`를 보내면 422 `READ_ONLY`.
- 수식: `REF("전기요금")` 형태이며 인수는 직접 쓴 글자 상수 하나(`formula-column` 10절).

## 4. 출력
- 저장: `reference_items`(이름 유일), `reference_values`(`item_id`+`year` 유일, `numeric`). 같은 연도를 다시 추가하면 409 `ALREADY_EXISTS`이며 값은 정정(R5)으로만 바꾼다.
- 응답: 항목 `{id, name, description, value_count, year_min, year_max, created_by, created_at}`, 값 `{id, item_id, year, value, created_by, created_at}`, 정정 `{value, previous_value, changed}`(숫자로 같은 값 `1.0`→`1.00`이면 `changed=false`이고 아무것도 쓰지 않으며 감사 기록도 없다).
- 감사 기록(`permission-management`): `reference.create`, `reference_value.add`, `reference_value.update`(대상 종류 `reference`, 정정은 이전·이후 값이 남는다). 수동 `psql`은 남지 않는다.
- 수식 결과: 그 행의 기준 날짜 연도와 **정확히 같은 연도**의 값. 없으면 **오류 칸 `E4`**(값은 빈 값, 이월 없음: 전년 값이 있어도 쓰지 않는다). 기준 날짜 값이 빈 칸이면 결과도 빈 값이다.
- 정정하면 뷰를 다시 만들지 않고 조회 때마다 읽으므로, 이미 입력된 행의 결과와 Superset 차트가 **그 연도 전체에서 바뀐다**(Superset 캐시가 있으면 그 시간만큼 늦게).

## 5. 실행 방법
### 사람(화면 S11, 상단 메뉴 "기준값", `${APP_BASE_PATH}/reference-values`)
- 누구나: 왼쪽 항목 목록(이름·설명·값 개수·연도 범위), 항목을 누르면 오른쪽에 연도별 값(연도 내림차순). 읽기 전용이다.
- 관리자만(비관리자에게는 버튼·폼이 없고 서버가 403으로 막는다):
  1. **항목 추가**: 이름과 설명. 이름은 나중에 바꿀 수 없으니 팀이나 용도를 붙여 정한다(예: `전기요금_A팀`).
  2. **연도 값 추가**: 연도와 값. 기본 연도는 가장 큰 연도 + 1. 같은 연도가 있으면 409와 "값을 바꾸려면 정정을 쓰세요".
  3. **정정**: 행의 "정정" → 새 값 → "정정 확인" → 확인창에서 "정정하기". 확인창은 "이 연도의 결과와 차트가 바뀝니다"와 영향 데이터셋 목록(R6, 읽기 5초 초과·실패 시 "확인하지 못했습니다"로 바뀌며 정정은 막지 않는다)을 보인다. 성공 안내는 이전 → 새 값이며 같은 값이면 "바꾸지 않았습니다(감사 기록 없음)".
- 수식 편집기: `REF("`를 치면 항목 이름과 설명이 자동완성으로 뜬다(처음 한 번 R1, limit=200. 넘으면 이름을 직접 입력). `REF`는 함수 도움말에도 나온다.
- 입력 그리드·점검(S5)에서 E4는 주황 점선 "기준값 없음 E4"로 보이고 "기준값 화면 열기" 링크가 있다. 고치는 방법은 그 연도 값을 추가하는 것이다(추가하면 즉시 사라진다).

### AI(REST)
```
BASE=${APP_BASE_PATH}/api   # 관리자 신원
curl -X POST "$BASE/reference-items" -H 'Content-Type: application/json' \
  -d '{"name":"전기요금_A팀","description":"kWh당 단가"}'
curl -X POST "$BASE/reference-items/1/values" -H 'Content-Type: application/json' \
  -d '{"year":2026,"value":"12.50"}'
curl -X PATCH "$BASE/reference-items/1/values/1" -H 'Content-Type: application/json' \
  -d '{"value":"13.00"}'                       # -> {"value":{...},"previous_value":"12.50","changed":true}
curl "$BASE/reference-items/1/usage"            # R6(관리자): 이 항목을 쓰는 수식·데이터셋
```
그다음 계산 열 수식에 `[사용량] * REF("전기요금_A팀")`처럼 쓴다(`formula-column`).

## 6. 관련 UI / API / command / DB
- UI: S11 기준값 화면, S4의 수식 편집기(REF 자동완성), S5 점검(E4), S10 감사 기록(대상 종류 "기준값").
- API: R1 `GET /api/reference-items`, R2 `POST /api/reference-items`, R3 `GET /api/reference-items/{id}/values`, R4 `POST …/values`, R5 `PATCH …/values/{value_id}`, R6 `GET /api/reference-items/{id}/usage`(관리자, 쓰는 수식·데이터셋). 계약은 `docs/decisions/05-api-contract.md` §2-9.
- command: 없음. DB: `public.reference_items`, `public.reference_values`(소유 `bi_owner`, `bi_app`은 SELECT·INSERT와 `description`·`number_value` 열 UPDATE만, DELETE 없음), 뷰 `dv_`·`de_`가 `reference_values`를 읽는다(안 B).
- 코드: `backend/app/reference/`(R1~R5), `backend/app/formula/usage.py`(R6), `backend/app/formula/functions.py`(`REF`), `backend/app/ddl/reference_lookup.py`·`dynamic.py`(뷰 게이트), `backend/migrations/versions/20261014_0009_reference_values.py`.

## 7. 실패 시 확인 방법
| 증상 | 원인·해결 |
| --- | --- |
| 403 `FORBIDDEN` | 관리자가 아님(쓰기·R6). 관리자 신원으로 다시 한다 |
| 409 `ALREADY_EXISTS` | 같은 이름의 항목, 또는 같은 연도의 값이 있음. 값은 정정으로 바꾼다 |
| 422 `VALIDATION_ERROR` | 이름·연도·값 형식 오류(`details.fields`). 값은 숫자만, 38자리 이하 |
| 422 `READ_ONLY` | 정정 본문에 `year`·`item_id`를 보냄 |
| 503 `WRITE_BUSY` | 같은 항목을 다른 요청이 쓰는 중(3초 안에 잠금을 못 얻음). 잠시 뒤 다시 한다 |
| 수식 저장 422 `FORMULA_INVALID` + `REF_UNKNOWN` | 없는 항목 이름. 이름은 대소문자·공백까지 정확히 같아야 한다 |
| `BASE_DATE_REQUIRED` | 데이터셋에 기준 날짜 열이 없음 |
| 422 `BASE_DATE_IN_USE` | REF를 쓰는 수식이 있어 기준 날짜 열을 해제할 수 없음(`dataset-definition`) |
| 칸이 E4 | 그 행의 기준 날짜 연도에 값이 없음. 기준값 화면에서 그 연도 값을 추가한다 |
| `REF(1)`, `REF([열])`이 거부됨 | 인수는 직접 쓴 글자 상수(`ARG_TYPE`·`CONST_REQUIRED`) |

## 8. 검증 방법
- 자동: `cd backend && pytest tests/test_reference_*.py tests/test_ddl_reference_gate.py`(실제 PostgreSQL은 `permission-management` 8절의 tmpfs 시험 DB로 `REQUIRE_PG=1`). 구성:
  - `test_reference_api.py`(R1~R5, 권한, 오류 우선순위, 감사 행, 같은 값 정정, 동시성), `test_reference_values.py`(이름·값·연도 규칙을 수식 엔진 규칙과 대조), `test_reference_usage.py`(R6).
  - `test_reference_pg.py`(`REF`의 뷰 경유 값·E4·기준 날짜 해제 막기·시작 대조·정정 뒤 값 변화), `test_ddl_reference_gate.py`(뷰 게이트 음성 시험), `test_reference_env_calls.py`(컴파일 호출 6곳이 `env`를 넘김).
  - `test_reference_differential.py`+`reference_bundle.py`: 미리보기(바인드)·뷰(리터럴)·파이썬 독립 기준값 3갈래 차분. 요약은 시험 출력 끝 "REF 차분 시험 요약".
  - `test_reference_acl.py`, `test_reference_migration_pg.py`, `test_migrations.py`, `test_roundtrip_tools.py`, `test_permission_matrix.py`, `test_audit_*`(감사 20개): 권한·`0009` 왕복·`downgrade` 거부.
  - `python -m migrations.roundtrip`과 `alembic check`.
- 수동: 관리자로 항목·2026년 값을 만들고, 기준 날짜가 2026년인 행에 `REF` 계산 열을 만들어 값 확인 → 2025년 행은 E4 → 정정 후 결과 변화 → Superset 차트에서 같은 값(캐시 시간 감안).
- 알려진 한계: 항목 삭제·이름 변경·설명 수정 없음(후속). `0009` `downgrade`는 기준값 뷰나 새 감사 행이 있으면 거부하며, 서버 밖에서 직접 넣은 기준값 행은 점검하지 못한다. 100만 행 규모의 정정 잠금 시간은 재지 않았다. E4 오류 칸 코드는 어느 항목·연도가 없는지 담지 않는다.

## 9. 연관 Skill
- `formula-column`: `REF` 함수·E4·C0 코드(`REF_UNKNOWN`·`BASE_DATE_REQUIRED`)·뷰 게이트(10절).
- `dataset-definition`: 기준 날짜 열, `BASE_DATE_IN_USE`.
- `permission-management`: 관리자 판정, 감사 행위 20개·대상 `reference`, 실제 PostgreSQL 시험 절차.
- `data-entry`: 입력 그리드가 계산 열의 E4를 오류 칸으로 보인다.
- `dashboard-link`: 차트는 `dv_` 뷰를 읽으므로 정정이 차트 값에 반영된다.
- `admin-cleanup`: 기준값 수동 정리(감사 기록에 남지 않음).
- `local-environment`: `0009` 마이그레이션 왕복.
