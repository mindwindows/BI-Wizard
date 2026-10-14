---
name: permission-management
description: 포털의 팀·사용자·소속(정의 담당자/입력자) 관리와 내 정보 조회, 최초 관리자 만들기, 개발·시험용 인증 스텁 사용법, 관리자의 감사 기록 조회(누가 언제 무엇을 바꿨는지). "팀 만들어줘", "사용자 등록", "관리자 지정", "정의 담당자로 바꿔줘", "첫 관리자 만들기", "스텁으로 로그인", "누가 이걸 바꿨어?", "감사 기록 보기", "변경 이력 조회" 같은 요청에 사용한다. 화면(S1, S6, S10)은 프런트 단위에서 붙고 이 문서는 backend API·명령 기준이다.
---

# permission-management — 팀·사용자·권한 관리

## 1. 목적
관리자가 팀을 만들고, 사용자를 사전 등록하고, 사용자를 팀에 정의 담당자(`definer`) 또는 입력자(`entry`)로 넣고 빼며, 비활성화한다. 모든 사용자는 자기 정보와 소속 팀을 본다. 인증된 모든 사용자는 모든 팀의 데이터를 열람할 수 있고(별도 역할 값 없음), 관리자는 팀 소속 역할이 없으면 데이터셋 정의·입력 권한이 없다(06 §4-1).

## 2. 사용 조건 / 사전 요구사항
- `local-environment` 통과(`migrate`가 최신 revision까지 적용. 이 Skill의 권한 표는 `0003`이고, 지금 head는 `0009`(FU-3: 기준값 표 `reference_items`·`reference_values`와 감사 CHECK 두 개 교체)이고 `0008`은 CHECK 두 개 교체만이고 `0007`까지로 데이터셋 표, 수식 표(`formulas`·`formula_deps`), Superset 등록 표, 감사 기록 표(`audit_log`)가 더 있다). backend는 시작 자가 점검을 통과해야 뜬다(`bi_app`의 위험한 속성, `bi_app`의 `public` CREATE 권한, `bi_data` 객체 종류 등. `skills/local-environment/SKILL.md` 7절).
- 로그인 방식(미결정 8번)이 정해지기 전에는 **인증 스텁**으로만 신원을 만든다. 스텁은 `AUTH_STUB_ENABLED=true`이고 `APP_ENV`가 명시적으로 `local` 또는 `test`일 때만 켜진다(그 밖이면 backend가 시작하지 않는다).
- 역할: A1·A2는 인증된 활성 사용자 누구나, A3~A9는 관리자만. 미등록 사용자는 403 `USER_NOT_REGISTERED`, 비활성 사용자는 403 `USER_INACTIVE`, 신원이 없으면 401 `UNAUTHENTICATED`. **사용자를 조회하는 중에 DB 연결·운영 오류가 나면 401이 아니라 503 `SERVICE_UNAVAILABLE`이다**(로그아웃과 구분하며 접근은 계속 닫혀 있다. 모든 보호 경로가 같다). 신원 어댑터 자체의 예외는 기존대로 401이다.
- 최초 관리자는 아래 서버 명령으로 만든다(화면·API로는 만들 수 없다: 관리자가 한 명도 없기 때문).

## 3. 입력
공통: JSON UTF-8, 필드 snake_case. 요청 본문에 정의되지 않은 필드를 보내면 422다(예: 팀 `code`는 만든 뒤 바꿀 수 없어 PATCH에 보내면 거부).

| API | 입력 |
| --- | --- |
| A2 `GET /api/teams`, A5 `GET /api/users` | `limit`(기본 50, 1~200, 밖이면 422), `offset`(0 이상). A5는 `q`(로그인 ID·표시 이름 부분 일치, 대소문자 무시, `%`·`_`는 글자 그대로), `team_id`, `is_active` |
| A3 `POST /api/teams` | `code`(필수, 형식 `^[a-z0-9_]{1,32}$`, 만든 뒤 불변), `name`(필수, 앞뒤 공백 제거·NFC 정규화, 1~50자, 제어문자 불가, 유일) |
| A4 `PATCH /api/teams/{team_id}` | `name?`, `is_active?`(보낸 것만 바꾼다. 빈 본문은 변경 없이 200) |
| A6 `POST /api/users` | `login_id`(필수, 1~200자, 정규화·대소문자 변환 없음, 유일), `display_name`(필수, 1~100자), `is_admin?`(기본 false) |
| A7 `PATCH /api/users/{user_id}` | `display_name?`, `is_admin?`, `is_active?`. `login_id`는 바꿀 수 없다 |
| A8 `PUT /api/teams/{team_id}/members/{user_id}` | `role`: `definer` 또는 `entry`(소속이 없으면 추가, 있으면 역할 변경). **비활성 팀이나 비활성 사용자에게는 추가도 역할 변경도 거부**한다(409 `TARGET_INACTIVE`) |
| A9 `DELETE /api/teams/{team_id}/members/{user_id}` | 없음. 비활성 팀·사용자의 소속 해제는 허용한다 |
| 서버 명령 | `--login-id`, `--display-name` (아래 5절) |

길이 상한은 계약(05 §1)이다: 팀 이름 50자, 사용자 표시 이름 100자, 로그인 ID 200자. 로그인 ID는 대소문자를 구분한다(8번 인증 결정 때 재검토).

## 4. 출력
- A1 `GET /api/me` 200 `{id, display_name, is_active, is_admin, memberships[{team_id, team_code, team_name, team_is_active, role}]}` (비활성 팀 소속도 나오며 `team_is_active`로 알려 준다. 화면은 작업 팀 선택에서 비활성 팀을 거른다)
- A2·A5 200 `{items, total, limit, offset}`. 팀 항목 `{id, code, name, is_active}`(팀 이름순), 사용자 항목 `{id, login_id, display_name, is_admin, is_active, memberships[{team_id, role}]}`(표시 이름순)
- A3 201 팀, A4 200 팀, A6 201 사용자(`memberships` 빈 목록), A7 200 사용자, A8 200 `{team_id, user_id, role}`, A9 204
- 오류는 모두 `{"error": {"code", "message", "details", "request_id"}}`이고 `message`는 한국어다.
  - 409 `ALREADY_EXISTS` + `details.field`(`code`, `name`, `login_id`), 409 `LAST_ADMIN`(마지막 활성 관리자의 관리자 해제·비활성화 거부), 409 `TARGET_INACTIVE` + `details.field`(`team` 또는 `user`, 둘 다 비활성이면 `team`을 먼저 알린다), 404 `NOT_FOUND`(없는 팀·사용자·소속. 비활성 확인보다 먼저), 422 `VALIDATION_ERROR`(`details.fields[{field, code, message}]`. 깨진 JSON·잘못된 쿼리·경로 형식도 400이 아니라 이 코드다), 405 `METHOD_NOT_ALLOWED`, 503 `SERVICE_UNAVAILABLE`(DB 장애)
- 저장 위치: `users`, `teams`, `team_members`(DB 권한은 6절). 팀 이름이 실제로 바뀌면 **커밋 뒤** 팀 단위 동기화를 요청한다(`DatasetSyncPort.request_team_sync`). 구현체는 `backend/app/superset/worker.py`(Superset 가상 데이터셋 이름 갱신, `skills/dashboard-link`)이고 Superset 접속 설정이 없으면 아무것도 하지 않는 기본 구현이다. 요청 처리 중에는 Superset을 부르지 않으며(`pending` 표시와 대기열 투입뿐) 요청이 실패해도 응답은 그대로다(오류 클래스 이름만 로그).

## 5. 실행 방법
### 최초 관리자 만들기 (서버 명령, 비밀번호 없음)
```
docker compose exec backend python -m app.cli create-admin --login-id <신원 어댑터가 주는 로그인 ID> --display-name "<화면에 보일 이름>"
```
- `bi_app` 접속으로 `users`에 활성 관리자(`is_admin=true`)를 넣는다. 새 환경변수는 없다.
- 이미 같은 로그인 ID의 **활성 관리자**가 있으면 아무것도 바꾸지 않고 성공(종료 0, 멱등). 같은 로그인 ID가 일반 사용자이거나 비활성이면 **거부**(종료 2)한다. 명령 한 줄이 기존 계정 권한을 조용히 올리지 않게 하려는 것이며, 이 경우 다른 관리자가 화면·API(A7)로 바꾼다.
- 종료 코드: 0 성공, 1 DB 오류(`migrate`/`postgres` 확인), 2 입력 오류 또는 기존 사용자와 충돌, 3 설정으로 거부(예: `POSTGRES_APP_PASSWORD` 누락).
- 운영 서버에서 이 명령을 실행할 수 있는지는 운영자 확인 항목이다(`docs/deploy-coordination.md` 35번).

### 개발·시험: 인증 스텁
`.env`에 `AUTH_STUB_ENABLED=true`, `APP_ENV=local`(또는 `test`) 후 `docker compose up -d`. 시험용 데이터는 서버 명령으로 넣는다(스텁이 꺼져 있거나 `APP_ENV`가 허용 밖이면 거부, 종료 3):
```
docker compose exec backend python -m app.cli seed-stub-users
```
팀 `stub_a`(시험 A팀)·`stub_b`와 사용자 `stub-admin`(관리자), `stub-definer`(A팀 정의 담당자), `stub-entry`(A팀 입력자), `stub-multi`(A팀 입력자 + B팀 정의 담당자), `stub-viewer`(소속 없음), `stub-inactive`(비활성)가 생긴다. 이미 있는 것은 바꾸지 않는다(멱등).

스텁 API(스위치가 꺼져 있으면 **경로 자체가 없어 404**, 인증 없이 열려 있다. 신원을 고르기 전에 쓰기 때문이다):
| ID | 요청 | 결과 |
| --- | --- | --- |
| DV1 | `GET /api/dev/stub-users` | 200 `{items[{login_id, display_name, is_admin}], current}` (등록된 사용자 전부, `current`는 지금 쿠키의 로그인 ID 또는 null) |
| DV2 | `PUT /api/dev/stub-user` `{login_id}` | 204 + 쿠키 `bi_stub_login`(HttpOnly, SameSite=Lax, Path=`${APP_BASE_PATH}` 또는 `/`). 없는 로그인 ID는 404. 비활성 사용자도 고를 수 있다(비활성 차단을 시험하려고) |
| DV3 | `DELETE /api/dev/stub-user` | 204 + 쿠키 삭제 |

```
curl -c jar -X PUT -H 'content-type: application/json' -d '{"login_id":"stub-admin"}' "http://localhost:<BACKEND_PORT>${APP_BASE_PATH}/api/dev/stub-user"
curl -b jar "http://localhost:<BACKEND_PORT>${APP_BASE_PATH}/api/me"
```
쿠키 값은 로그인 ID(URL 인코딩)이고 서명하지 않는다. 쿠키가 있어도 `users`에 없으면 403 `USER_NOT_REGISTERED`다. 스텁이 꺼진 환경에서는 쿠키가 있어도 무시되고 모든 업무 API가 401이다(fail-closed).

### 사람(화면)
#### S1 포털 셸·접근 안내
1. 브라우저로 포털 주소(`APP_BASE_PATH` 아래)를 연다. 화면이 먼저 `GET /api/me`로 내 정보를 읽는다.
2. 정상: 상단에 주 메뉴(홈·데이터셋·점검·대시보드), 이름, "작업 팀" 선택, 관리자라면 오른쪽에 관리 메뉴(권한 관리·대시보드 연결·현황)가 보인다. 홈에는 내 소속 팀과 역할, API·DB 연결 상태가 나온다.
3. 여러 팀에 속하면 상단 "작업 팀"에서 고른다. 선택은 이 브라우저 탭의 화면 상태(`sessionStorage` 키 `bi-wizard.workTeamId`)에만 남고 서버에는 저장되지 않는다. 저장된 팀이 지금 소속에 없으면 첫 소속 팀을 쓴다. 소속이 없으면 "소속 팀 없음"이고 홈에 안내가 나온다(열람은 가능).
4. 관리 메뉴는 `is_admin`일 때만 보이지만 이것은 편의다. 최종 방어선은 서버 권한 검사(관리자 전용 API는 403 `FORBIDDEN`)이며, 일반 사용자가 `/admin/permissions`로 직접 들어가도 "관리자만 사용할 수 있는 화면입니다"만 보이고 사용자·팀 API를 부르지 않는다.
5. "접근 권한이 없습니다" 화면(본문 전체를 대신하고 메뉴가 숨겨짐):
   - 401 `UNAUTHENTICATED`: 로그인 정보를 확인하지 못했다는 안내.
   - 403 `USER_NOT_REGISTERED`: 아직 등록되지 않은 사용자이니 관리자에게 등록을 요청하라는 안내.
   - 403 `USER_INACTIVE`: 사용이 중지된 계정이니 관리자에게 문의하라는 안내.
   - "다시 확인" 버튼이 `/me`를 다시 읽는다. 그 밖의 실패(500, 연결 실패)는 접근 거부가 아니라 일반 오류와 "다시 시도" 버튼이다.

#### 개발용 신원 전환기 (개발·시험 전용)
- 서버가 스텁을 켠 환경(`AUTH_STUB_ENABLED`, `APP_ENV` local·test)에서 `GET /api/dev/stub-users`가 200이면 상단에 점선 테두리의 "개발용 신원" 선택이 나타난다. 404(운영 설정, 경로 자체가 없음)이거나 다른 오류면 아무것도 보이지 않는다. 프런트에는 별도 설정·환경변수가 없다.
- 사용자를 고르면 `PUT /api/dev/stub-user {login_id}` 뒤 `/me`를 다시 읽는다. "(선택 안 함)"은 `DELETE /api/dev/stub-user` 뒤 다시 읽는다(401이 되어 접근 안내가 나온다). 접근 안내 화면에서도 전환기는 남는다.

#### S6 권한 관리 (관리자)
1. 관리 메뉴의 "권한 관리"를 연다. 가로가 팀, 세로가 사용자인 격자다(`GET /api/teams`, `GET /api/users`). 비활성 팀(헤더에 "비활성")과 비활성 사용자(배지)도 회색으로 보인다. 사용자는 50명씩 쪽 이동("이전"/"다음"), 팀은 200개씩 이어 읽는다. "사용자 검색"은 `q`로 로그인 ID·이름을 찾는다.
2. 모든 수정은 즉시 서버에 가지 않고 아래 "변경 목록"에 모인다. 변경한 칸은 노랗게 표시된다.
   - 소속·역할: 격자 칸의 선택(소속 없음 / 정의 담당자 / 입력자). 원래 값으로 되돌리면 목록에서 빠진다.
   - 팀 만들기: 코드(영문 소문자·숫자·밑줄 1~32자, 만든 뒤 변경 불가)와 이름(1~50자) 입력 후 "변경 목록에 담기".
   - 사용자 사전 등록: 로그인 ID, 표시 이름, 관리자 여부.
   - 팀 수정: 헤더의 "<팀> 수정"에서 이름 변경, 사용 중 해제(비활성).
   - 사용자 수정: 행의 "<이름> 수정"에서 표시 이름, 관리자, 사용 중 해제(비활성).
3. "저장하기"를 누르면 변경 요약 확인창이 모은 변경 전부를 실행 순서대로 보여 준다. "확인하고 저장"을 눌러야 API가 호출되고, "돌아가기"/Esc는 아무것도 호출하지 않는다.
4. 실행 순서: 팀 만들기(A3) → 사용자 등록(A6) → 팀 수정(A4) → 권한을 주는 사용자 수정(A7) → 소속 추가·역할 변경(A8) → 소속 해제(A9) → 관리자 해제·비활성 사용자 수정(A7). 마지막 관리자 보호(`LAST_ADMIN`)에 걸리지 않게 새 관리자 지정이 먼저다.
5. 하나라도 실패하면 거기서 멈춘다. 결과 창에 완료/실패/실행 안 함이 표시되고, 성공한 변경만 목록에서 빠지며 실패·미실행분은 목록에 남아 고친 뒤 다시 저장할 수 있다. 이미 성공한 변경은 되돌려지지 않는다(트랜잭션 하나가 아님).
6. 저장하지 않은 변경이 있으면 탭을 닫을 때 브라우저가 한 번 묻는다.
- 새로 만든 팀·사용자는 저장 뒤 격자에 나타나며, 그때 소속을 지정한다(같은 저장 묶음에서 새 객체의 소속은 지정할 수 없다).

## 5-1. 감사 기록 조회 (관리자, FU-2a)
누가 언제 무엇을 바꿨는지를 관리자가 읽는다. 기록은 변경과 **같은 트랜잭션**에서 서버가 남기고, 읽기만 가능하다(수정·삭제·내보내기 경로가 없다). 규칙은 `docs/decisions/04-modules.md` §5-1, API는 05 §2-7 F1, 표는 06 §2-1이다.

### API로 조회하기 (관리자만)
```
curl -b jar "http://localhost:<BACKEND_PORT>${APP_BASE_PATH}/api/audit-logs?from=2026-10-01&to=2026-10-13&action=member.set&limit=50"
```
(`jar`는 위 스텁 로그인으로 관리자 신원을 고른 쿠키 파일이다.) 쿼리는 모두 선택이고 **모두 AND**로 걸린다.

| 쿼리 | 뜻 |
| --- | --- |
| `from`, `to` | 날짜 `YYYY-MM-DD`, **한국 시간 기준 그날 포함**(`from`은 그날 00:00부터, `to`는 그날 24:00 전까지). 둘 다 없으면 전체 기간 |
| `actor_user_id` | 행위자 사용자 번호(정수). 서버 명령(`create-admin`) 행은 행위자가 없어 이 필터로는 나오지 않는다 |
| `target_type` | `team` · `user` · `dataset` · `dashboard` · `reference` 중 하나 |
| `target_id` | 대상 번호(정수). **`target_type`과 함께만** 보낸다(번호는 종류마다 따로 매겨진다) |
| `action` | 아래 20개 값 중 하나 |
| `limit`, `offset` | 기본 50, 최대 200 / 0 이상(상한 없음) |

응답 `200 {items, total, limit, offset}`. **정렬은 항상 최신순**(`occurred_at` 내림차순, 같으면 `id` 내림차순)이고 정렬 인자는 없다. `total`은 필터를 적용한 정확한 전체 건수다. 항목은 `{id, occurred_at(+09:00), actor{id, display_name} 또는 null, actor_source("user"|"cli"), action, target_type, target_id, details}`이다. `actor.display_name`은 조회 시점의 사용자 이름이다(이름을 바꾸면 이전 행에도 새 이름이 보인다). `details`는 행위마다 정해진 키만 있고 항상 `target_name`(대상 이름 스냅샷)이 있다.

### 기록되는 행위 20개
| `action` | 언제 | `details`(`target_name` 외) |
| --- | --- | --- |
| `dataset.create` | 데이터셋 만들기(B2) | `team_id`, `date_unit`, `def_version` |
| `dataset.update` | 이름·날짜 단위·기준 날짜 열 변경(B4) | `team_id`, `changes{name, date_unit, base_date_column_id}`, `def_version` |
| `dataset.archive` | 데이터셋 보관(B7, FU-2b). 정의 버전을 올리지 않아 `def_version`이 없다 | `team_id` |
| `dataset.restore` | 보관된 데이터셋 복구(B8, FU-2b) | `team_id` |
| `column.add` | 원본 열 추가(B5) | `column_id`, `column_name`, `column_type`, `required`, `def_version` |
| `column.update` | 열 이름·필수·태그·순서·규칙 변경(B6) | `column_id`, `column_name`, `changes{display_name, required, tag, position}`, `rules_changed`(규칙 값 자체는 없다), `def_version` |
| `formula_column.add` | 계산 열 만들기(D4) | `column_id`, `column_name`, `result_type`, `ast_hash`, `def_version` |
| `formula_column.update` | 수식 고치기(D5, 같은 수식이면 기록 없음) | `column_id`, `column_name`, `result_type`, `result_type_changed`, `ast_hash_from`, `ast_hash`, `def_version` |
| `team.create` | 팀 만들기(A3) | `code` |
| `team.update` | 팀 이름·활성 변경(A4) | `changes{name, is_active}` |
| `member.set` | 소속 추가·역할 변경(A8) | `user_id`, `role`, `role_from`(새 소속이면 null) |
| `member.remove` | 소속 해제(A9) | `user_id`, `role_from` |
| `user.create` | 사용자 등록(A6) | `is_admin` |
| `user.update` | 이름·관리자·활성 변경(A7) | `changes{is_admin, is_active}`, `display_name_changed`(이름 값은 `target_name`에만) |
| `user.bootstrap_admin` | 서버 명령 `create-admin`으로 최초 관리자를 만듦 | `is_admin`(항상 true). 행위자 없음, `actor_source="cli"` |
| `dashboard.create` | 대시보드 연결 등록(E4) | `embedded_uuid` |
| `dashboard.update` | 대시보드 이름·활성 변경(E5). `is_active` true→false는 "연결 해제", false→true는 "다시 연결" | `changes{name, is_active}` |
| `reference.create` | 기준값 항목 만들기(R2, FU-3). 대상은 `reference`이고 `target_id`는 항목 번호, `target_name`은 항목 이름 | `description_length` |
| `reference_value.add` | 기준값 연도 값 추가(R3) | `year`, `value`(십진 글자) |
| `reference_value.update` | 기준값 정정(R5). 같은 숫자면 기록 없음 | `year`, `value_from`, `value_to` |

대상은 `target_type`·`target_id`로 가리킨다. 소속(`member.*`)은 `team`을 대상으로 하고 사용자는 `details.user_id`에 있다. 열·수식 변경은 `dataset`을 대상으로 하고 `details.column_id`가 열이다(데이터셋 하나의 정의 이력이 `target_type=dataset&target_id=<번호>` 한 번으로 모인다). 한 번의 요청은 **최대 한 건**이고(여러 필드를 바꿔도 `changes`에 함께), **실제로 바뀐 것이 없으면 한 건도 남지 않는다**(같은 값으로 저장, 빈 본문, 같은 역할 재요청, 이미 활성 관리자인 `create-admin` 재실행, 이미 같은 상태인 보관·복구 재요청). 실패한 요청(409·404·422·503)과 롤백된 요청도 남지 않는다.

### 기록되지 않는 것
행 값 입력·수정·붙여넣기(C2~C4), 입장권 발급(E6), Superset 동기 상태 변경·동기화 접수(E2), 시작 시 뷰 재생성·다시 시도(D10, 정의가 안 바뀜), 팀 이름 변경 뒤의 동기화 같은 후속 부수 효과, 시험용 사용자 시드(`seed-stub-users`), `/dev/*` 신원 전환, 모든 조회(GET). **`details`에는 행 값, 수식 원문, 검증 규칙 값, 로그인 ID, 토큰·비밀번호가 들어가지 않는다**(사용자는 표시 이름만, 수식은 열 번호와 `ast_hash`만).

### 조회할 수 없는 사용자
관리자(`is_admin`)만 읽는다. 정의 담당자·입력자·소속 없는 사용자·다른 팀 구성원은 모두 `403 FORBIDDEN`, 미등록 사용자는 403 `USER_NOT_REGISTERED`, 비활성 사용자는 403 `USER_INACTIVE`, 로그인 정보가 없으면 401 `UNAUTHENTICATED`. 권한 검사가 쿼리 검증보다 먼저라 권한 없는 사용자는 입력 오류의 내용도 알 수 없다. 화면 메뉴를 숨기는 것은 편의이고, 막는 것은 서버다(주소로 직접 열어도 403).

### 오류
`422 VALIDATION_ERROR`의 `details.fields[].code`: 날짜 형식 오류 `BAD_FORMAT`(필드 `from`·`to`, `YYYY-MM-DD` 아님·없는 날짜·공백·전각 숫자), `from`이 `to`보다 늦으면 필드 `to`에 `OUT_OF_RANGE`, `target_type`·`action`이 목록 밖이면 `NOT_IN_OPTIONS`, `target_id`만 있고 `target_type`이 없으면 필드 `target_type`에 `REQUIRED`, 정수가 아니거나 범위 밖이면 `BAD_FORMAT`, `limit`·`offset` 범위 밖은 다른 목록과 같다. DB 장애는 503 `SERVICE_UNAVAILABLE`.

### 운영 주의
- **자동 삭제가 없다.** 기록은 계속 쌓이고 보존·삭제 정책은 후속이다. 하루 건수는 측정하지 않았다(확인 못 함). 새 기록이 계속 쌓이므로 `offset` 페이지 사이에 행이 밀릴 수 있고(알려진 한계), 아주 깊은 페이지의 속도는 측정하지 않았다.
- **`bi_app`(서버)은 읽기와 추가만 한다**(UPDATE·DELETE·TRUNCATE 권한 없음). 잘못 남은 기록을 서비스로 고치거나 지울 수 없다. 정정 방법은 후속이다.
- **경고: `alembic downgrade`로 `0007` 아래로 내리면 `audit_log` 표와 기록이 모두 삭제된다. 실행 전 백업이 필수다.** 되돌리기용이 아니라 빈 시험 DB의 왕복 시험용이다. 운영에서는 하지 않고 문제는 수정 revision으로 대응한다. 이 `DROP`은 사용자가 승인했다(2026-10-14, `docs/decisions/03b-gate3-round-decisions.md` 29-3, `backend/tests/test_migrations.py`의 `DROP_APPROVED`에 "DROP 확인: 사용자 승인"으로 기록).
- **경고(FU-2b, revision `0008`): 보관·복구 감사 행(`dataset.archive`·`dataset.restore`)이나 보관된 데이터셋이 있으면 `alembic downgrade 0007`은 한국어 메시지로 거부하고 아무것도 바꾸지 않는다**(CHECK를 옛 정의로 되돌리면 그 행들이 제약에 걸리고 감사 기록은 지우지 않기 때문). `0007` 아래로 내리는 경고는 위와 같다. `0008`의 제약 교체(`drop_constraint` 4개)는 사용자가 승인했다(2026-10-14, 03b 30-1 결정 4, `DROP_APPROVED`).
- **`skills/admin-cleanup`의 수동 `psql` 정리는 감사 기록에 남지 않는다.** 서비스를 거치지 않기 때문이다. 정리한 사실은 변경 요약·운영 노트에 따로 적는다. 정리해도 `audit_log`의 `target_id`(외래키 없음)는 그대로 남는다.
- 감사 기록은 변경과 같은 트랜잭션이라 **기록 INSERT가 실패하면 변경도 실패한다**(500 `INTERNAL_ERROR`, 감사 없는 변경은 없다). `occurred_at`은 DB의 트랜잭션 시작 시각이라 오래 걸린 요청은 조금 이른 시각으로 남는다.
- 시작 자가 점검은 정적 표 정의에 `audit_log`가 있어 `0007`이 적용되지 않은 DB에서는 backend가 시작하지 않는다(`migrate`가 끝났는지 확인).

### 화면 (S10 감사 기록 목록)
화면은 위 API만 부른다. 비관리자에게는 메뉴 항목이 없고, 주소로 직접 열어도 화면이 "관리자만 볼 수 있습니다"만 보여 주고 API를 부르지 않는다(관리자로 알려졌는데 서버가 403을 주는 경우에도 같은 안내). 수정·삭제·내보내기 버튼은 없다.

#### 화면 절차
##### 여는 법
- 상단 오른쪽 "관리 메뉴"의 **감사 기록**(관리자에게만 보인다). 주소는 `<포털 주소>/admin/audit`.
- 일반 사용자가 주소로 직접 열면 "관리자만 볼 수 있습니다"만 보이고 목록·필터는 나오지 않는다. 메뉴 숨김은 편의이고 실제 방어선은 서버의 관리자 확인(403)이다.

##### 무엇이 보이나
- 변경 기록 목록(읽기 전용, 최신순, 한 쪽 50건). 열: 일시(한국 시간, 초 단위) / 행위자 / 행위 / 대상 / 요약.
- 행위자가 "서버 명령"이면 포털 화면이 아니라 서버에서 실행한 명령(최초 관리자 등록)이 한 일이다.
- 대상은 "종류 #번호 이름"(예: 데이터셋 #12 월별 매출). 열·수식 변경과 소속 변경은 데이터셋·팀을 대상으로 한다.
- **요약 읽는 법:** 기록의 상세를 쉬운 말로 풀어 쓴 것이다. 예) `이름 '가'→'나'`, `역할 입력자→정의 담당자`, `연결 해제`, `다시 연결`, `열 '매출' 추가 (숫자, 필수), 정의 버전 5`. 화살표(→) 왼쪽이 바꾸기 전, 오른쪽이 바꾼 뒤 값이다.
- 요약 끝의 "(일부 상세 생략)"과 "(상세 생략)"은 서버가 준 상세 중 이 화면이 아는 항목만 보여 주고 나머지는 일부러 숨겼다는 뜻이다.
- **보이지 않는 것:** 입력한 행의 값, 수식 원문, 비밀번호·토큰. 기록에 남지 않으며 화면에도 없다. 수식은 "수식 수정" 사실과 결과 타입 변경 여부만 남는다.
- 수정·삭제·내보내기 버튼은 없다. 기록은 추가만 되고 자동으로 지워지지 않는다.

##### 필터 사용법
- 시작일·종료일: 그날을 포함한다(한국 시간). 둘 다 비우면 전체 기간. 시작일이 종료일보다 늦으면 조회하지 않고 알려 준다.
- 행위자: 사용자 목록에서 고른다(사용 중지 사용자 포함). 목록을 못 읽으면 이 칸만 막히고 나머지 조건은 쓸 수 있다.
- 대상 종류(팀·사용자·데이터셋·대시보드)를 먼저 고르면 대상 번호를 입력할 수 있다(1 이상의 정수). 종류를 바꾸면 번호가 비워진다.
- 행위: 한국어 이름 20개 중 하나.
- 조건을 바꾼 뒤 **조회**를 눌러야 목록에 반영된다(첫 쪽부터). **필터 지우기**는 모든 조건을 비우고 다시 읽는다.
- 쪽 이동은 "이전/다음"이며 "전체 N건 중 a–b"로 위치를 보여 준다. 새 기록이 쌓이는 동안 쪽을 넘기면 행이 한두 건 밀려 보일 수 있다(알려진 한계).

##### 빈 상태와 오류
- 필터가 없고 기록이 없음: "아직 기록이 없습니다."
- 필터가 있고 결과가 없음: "조건에 맞는 기록이 없습니다." + **필터 지우기** 버튼.
- 서버가 바쁘거나 응답하지 못함(503): "서버가 일시적으로 응답하지 못합니다. 잠시 뒤 다시 시도하세요." + **다시 시도** 버튼(필터는 그대로 유지).
- 입력 오류(422): 틀린 칸 이름을 한국어로 알려 준다(시작일, 종료일, 대상 종류, 대상 번호, 행위).


## 6. 관련 UI / API / command / DB
- UI: S1 포털 셸·접근 안내, S6 권한 관리, S10 감사 기록 목록(`docs/decisions/04-modules.md` §4). S1 `/`, `/access-denied`(경로는 `APP_BASE_PATH` 아래), S6 `/admin/permissions`, 구현 위치 `frontend/src/features/access/`
- API: A1~A9(05 §2-1), F1 `GET /api/audit-logs`(05 §2-7, 코드는 `backend/app/audit/`: `actions.py`가 행위 20개와 `details` 허용 키의 유일한 출처, `service.py`의 `record`가 쓰기, `router.py`가 조회), DV1~DV3(05 §2-6). 코드는 `backend/app/access/`(router·service·repo), 스텁은 `backend/app/auth/stub.py`, 사용자 조회는 `backend/app/auth/db_reader.py`
- command: `python -m app.cli create-admin`, `python -m app.cli seed-stub-users` (`backend/app/cli.py`)
- DB(`audit_log`, revision `0007_audit_log`, `bi_owner` 소유, `public`): `id bigint`(identity, 시퀀스 권한 불필요), `occurred_at`, `actor_user_id`(users 외래키, 서버 명령이면 NULL), `actor_source`, `action`, `target_type`, `target_id`(외래키 없음), `details jsonb`(객체, 4,000바이트 이하). CHECK 6개와 인덱스 3개. `bi_app`은 **SELECT·INSERT만**(UPDATE·DELETE·TRUNCATE 없음)이고 `bi_readonly`(Superset)와 PUBLIC에는 권한이 없다.
- DB(`public`, revision `0003_users_teams_members`, `bi_owner` 소유): `users`(`login_id` 유일), `teams`(`code` 유일·불변·형식 CHECK, `name` 유일), `team_members`(PK `team_id`+`user_id`, `role` CHECK). `bi_app` 권한은 명시 GRANT뿐이다: 표 단위 SELECT·INSERT(`team_members`는 DELETE도), UPDATE는 열 단위(`users`: `display_name`·`is_admin`·`is_active`, `teams`: `name`·`is_active`, `team_members`: `role`). 불변 열(`login_id`, `code`, `team_id`, `user_id`)은 DB가 변경을 거부한다. `bi_readonly`(Superset)와 PUBLIC에는 아무 권한도 없다.
- 마지막 활성 관리자 보호: A7이 활성 관리자 행을 id 순서로 한 문장에서 `FOR NO KEY UPDATE`로 잠그고 판정하므로 두 관리자를 동시에 해제해도 활성 관리자가 0명이 되지 않는다(교착 없음).

## 7. 실패 시 확인 방법
| 증상 | 원인 | 확인과 해결 |
| --- | --- | --- |
| 모든 API가 401 | 스텁이 꺼져 있거나 쿠키가 없음(운영 어댑터는 8번 결정 뒤) | `AUTH_STUB_ENABLED`, `GET /api/dev/stub-users`가 404면 꺼진 것. 켠 뒤 DV2로 신원을 고른다 |
| 403 `USER_NOT_REGISTERED` | 로그인 ID가 `users`에 없음 | 관리자가 A6으로 등록하거나 `seed-stub-users`/`create-admin` |
| 403 `USER_INACTIVE` | 비활성 사용자 | 다른 관리자가 A7로 `is_active=true` |
| 403 `FORBIDDEN` | 관리자가 아님 | A3~A9는 관리자만 |
| 503 `SERVICE_UNAVAILABLE` | 사용자 조회 중 DB 연결·운영 오류(로그아웃이 아니다) | `docker compose ps postgres`, `docker compose logs backend`의 `사용자 조회 중 DB 장애(503으로 닫음): <예외 클래스>`(login_id·SQL은 로그에 없다). DB가 돌아오면 같은 요청이 다시 된다 |
| 409 `TARGET_INACTIVE` | A8 대상 팀 또는 사용자가 비활성 | `details.field`가 `team`이면 A4로 팀을 다시 사용 중으로, `user`이면 A7로 사용자를 다시 활성화한 뒤 소속을 지정한다. **보관된 데이터셋을 복구해야 하는데 비활성 팀에 정의 담당자가 없을 때의 순서**(FU-2b 실측, 관리자 예외 코드는 없음): 비활성 팀에는 A8로 `definer`를 지정할 수 없으므로 ① A4로 팀을 다시 활성화 ② A8로 `definer` 지정 ③ 그 `definer`가 복구(B8). 복구는 팀 활성 여부를 보지 않으므로 ③ 전에 팀을 다시 비활성으로 돌려도 된다(`skills/dataset-definition`의 "복구 경로") |
| 409 `LAST_ADMIN` | 활성 관리자가 이 사람 하나뿐 | 다른 사용자를 먼저 관리자로 지정(A6/A7) |
| 409 `ALREADY_EXISTS` | `details.field`가 가리키는 값이 이미 있음 | 다른 코드·이름·로그인 ID를 쓴다(로그인 ID는 대소문자 구분) |
| `create-admin` 종료 2 | 입력 오류 또는 같은 로그인 ID의 기존 일반·비활성 사용자 | 메시지 확인. 기존 사용자는 화면·API로 바꾼다 |
| `create-admin` 종료 1 | DB 접속·표 없음 | `docker compose ps`, `logs migrate backend`(`0003` 적용 여부) |
| backend가 시작하지 않음 | 시작 자가 점검 거부(`bi_app`의 위험 속성, **`bi_app`에 `public` schema CREATE 권한이 있음** 등) 또는 스텁 설정 거부 | `docker compose logs backend`의 메시지(`시작하지 않는다: …`). 속성 이름만 나오고 비밀은 나오지 않는다 |
| 응답 문제 추적 | | 오류 본문 `request_id`로 `docker compose logs backend`를 찾는다 |

#### 화면 변경(03b 17-1 결정 반영)
##### S1 (작업 팀 선택, 홈, 접근 안내)
- `/me`(A1) 응답의 `memberships[].team_is_active`를 쓴다. **비활성 팀은 상단 "작업 팀" 선택에 "(비활성)"으로 보이지만 고를 수 없다(선택 불가 항목).** 저장된 선택(`sessionStorage` `bi-wizard.workTeamId`)이 비활성 팀이거나 소속에 없으면 **첫 활성 팀**을 쓴다. 소속은 있는데 활성 팀이 하나도 없으면 "활성 팀 없음"이 표시되고 작업 팀 선택은 없다.
- 홈의 "소속 팀" 표에서 비활성 팀 이름 옆에 "비활성" 배지가 붙고 "선택됨"은 활성 팀에만 붙는다.
- **503 `SERVICE_UNAVAILABLE`(DB 등 일시 장애)는 접근 안내("접근 권한이 없습니다")로 가지 않는다.** 로그아웃(401)과 구분되어 일반 오류 영역에 "서버가 일시적으로 응답하지 못합니다. 잠시 뒤 다시 시도하세요."와 "다시 시도" 버튼이 나온다(접근은 서버에서 닫혀 있다). 접근 안내 화면은 401·403(`USER_NOT_REGISTERED`·`USER_INACTIVE`)에만 쓴다.

##### S6 권한 관리
- **비활성 팀 또는 비활성 사용자 칸은 소속 추가·역할 변경이 막힌다.** 소속이 없는 칸은 선택 상자 전체가 비활성이고, 이미 소속이 있는 비활성 팀 칸은 "소속 없음"(해제)과 현재 역할만 고를 수 있다(해제 A9는 서버가 허용). 격자 위에 안내 문구가 있다. 서버는 그래도 최종 방어선이라 낡은 화면에서 보내면 409 `TARGET_INACTIVE`를 돌려주고 결과 창에 "비활성 팀에는 소속을 지정할 수 없습니다…" 또는 "비활성 사용자에게는…"(`details.field`가 `team_id`/`user_id`일 때)이 나온다.
- 사용자 사전 등록·수정: 표시 이름 입력은 **100자**, 로그인 ID는 **200자**로 제한된다(`maxLength`, 붙여넣어 넘기면 "담기" 때 한 번 더 막는다).

### 화면에 나오는 오류 문구 (error.code 분기, 서버 message는 알 수 없는 4xx만 사용)
| 코드 | 화면 문구 요지 |
| --- | --- |
| LAST_ADMIN (409) | 마지막 관리자는 해제·사용 중지할 수 없다. 먼저 다른 관리자를 지정 |
| ALREADY_EXISTS (409, details.field) | code: 같은 코드의 팀이 이미 있음 / login_id: 같은 로그인 ID 사용자가 있음 / 그 밖: 이미 같은 값이 있음 |
| VALIDATION_ERROR (422) | 입력 확인 + `(팀 코드: 형식이 맞지 않습니다, 이름: 너무 깁니다)` 식 필드별 풀이 |
| FORBIDDEN (403) | 이 작업을 할 권한이 없음 |
| NOT_FOUND (404) | 대상을 찾을 수 없음, 새로 고친 뒤 재시도 |
| NETWORK_ERROR / INTERNAL_ERROR | 서버 연결 실패 / 예기치 않은 오류 + 문의 번호(`request_id`) |
| SERVICE_UNAVAILABLE (503) | 서버가 일시적으로 응답하지 못함, 잠시 뒤 다시 시도(로그아웃 아님). `/me`에서는 접근 안내가 아니라 일반 오류 + 다시 시도 |
| TARGET_INACTIVE (409, details.field) | team_id: 비활성 팀에는 소속을 지정할 수 없음 / user_id: 비활성 사용자에게는 지정할 수 없음 / 그 밖: 둘을 함께 안내 |
| METHOD_NOT_ALLOWED (405) | 허용되지 않는 요청, 새로 고친 뒤 다시 시도 |
- `BAD_REQUEST`는 더 이상 오지 않는다. 형식 오류는 422 `VALIDATION_ERROR` 하나다.

## 8. 검증 방법
- 자동(DB 없이, `docker build --target test backend`와 같다): `pytest`. API 시험은 SQLite로 돌고 `pg` 변형은 건너뛴다. **CI에서 건너뛰어 통과처럼 보이는 일을 막으려면 시험을 실행하는 환경에 `REQUIRE_PG=1`을 준다**: PostgreSQL 시험 환경(접속 정보·tmpfs 시험 DB)이 없을 때 `pg` 변형이 건너뛰지 않고 **실패**한다. 미설정이면 건너뛴다. `.env`·`.env.example`·compose에는 넣지 않는 시험 실행용 옵션이다.
- 자동(실제 PostgreSQL, 권장): tmpfs 시험 DB로 `pg` 변형까지 실행한다. 정적 표 권한 매트릭스(`has_table_privilege`/`has_column_privilege` 대조 + 실제 UPDATE/DELETE 거부 42501, `users`·`teams`·`team_members`·`datasets`·`dataset_columns`·`formulas`·`formula_deps`·`superset_datasets`·`superset_dashboards`·`audit_log`), `bi_readonly` 읽기 불가, 제약(CHECK/UNIQUE/FK), LAST_ADMIN 경쟁·교착, 시작 자가 점검(속성 5가지, `bi_data` 객체 종류), 스텁·CLI·API 전체가 대상이다. 안전장치: 서버가 `fsync=off`(시험 DB 서비스만)가 아니면 건너뛴다.
```
docker compose --profile test up -d --wait postgres-test
docker compose --profile test run --rm --no-deps -e PGHOST=postgres-test db-bootstrap
docker build --target test -t bi-wizard-backend-test backend
docker run --rm --network bi-wizard_default --env-file .env -e POSTGRES_HOST=postgres-test bi-wizard-backend-test pytest
docker compose --profile test stop postgres-test && docker compose --profile test rm -f postgres-test
```
(네트워크 이름은 compose 프로젝트 이름에 따른다: `docker network ls`. 이 시험은 `POSTGRES_USER`/`POSTGRES_PASSWORD`/`*_PASSWORD`가 필요하다. 시험 DB는 새 DB여야 한다: 시험이 `users`·`teams`·`team_members`의 행을 지운다.)
- 마이그레이션(위 pytest를 돌린 DB와 **다른 새 postgres-test**에서 따로 실행한다. 왕복 스크립트는 DB가 이미 `0003` 이상이면 "빈 테스트 DB에서만 실행하세요"로 중단한다): `python -m migrations.roundtrip`(`skills/local-environment/SKILL.md` 5절)이 upgrade → downgrade → upgrade와 `alembic check`, `0003`~`0007`의 표·열 단위 권한 상태(0007·0006·0005·0004 한 단계 내림 포함)를 확인한다. 왕복은 `0007`의 `DROP`(감사 기록 전체 삭제)을 포함하므로 **빈 시험 DB에서만** 한다.
- 권한 매트릭스: `backend/tests/test_permission_matrix.py`가 A1~A9, B1~B6(`skills/dataset-definition`), C1~C4(`skills/data-entry`), D1~D10(`skills/formula-column`: 읽기 D1·D6·D7·D8, 정의(팀) D2~D5, 관리자 D9·D10), DV1~DV3 × 역할(+ B2의 비활성 팀 행: 정의 담당자 409 `TARGET_INACTIVE`, 그 밖 역할은 403·401로 권한 판정이 먼저)(관리자, 정의 담당자, 입력자, 다른 팀 구성원, 비소속 읽기, 비활성, 인증 없음)을 확인하고, 앱의 모든 보호 경로가 표에 있는지도 확인한다. 새 엔드포인트를 더하면 이 표에 행을 더해야 시험이 통과한다.
- 감사 기록(FU-2a): `tests/test_audit_record.py`(허용 키 표·`record` 단위), `test_audit_hooks.py`(행위 20개 각각: 성공 1건·변경 없음 0건·대표 오류 0건·커밋/훅 실패 주입 0건·감사 INSERT 실패 주입 시 변경도 롤백), `test_audit_api.py`(F1: 권한·필터·정렬·페이지·422 필드 코드·경계), `test_audit_coverage.py`(기록 대상 표를 쓰는 service 함수가 행위 표에 있는지 소스 점검), `test_audit_secrets.py`(심은 로그인 ID·셀 값·수식 상수·규칙 값이 `details`에 없음), `test_audit_pg.py`(행위자 `users` 행 잠금 영향·경쟁에서 전이 한 건씩·직렬화 크기), `test_static_acl.py`(`bi_app` UPDATE·DELETE·TRUNCATE 거부, `bi_readonly` 접근 거부, 시퀀스 권한 없이 INSERT 성공, CHECK·FK), 권한 매트릭스에 F1.
- 수동: 위 스텁 curl로 관리자 로그인 후 팀 만들기 → 사용자 등록 → 소속 지정 → `/api/me`(해당 사용자)로 소속 확인, 마지막 관리자 해제 시 409.
- 프런트:
  - `cd frontend && npm run typecheck && npm run lint && npm test && npm run build`
  - 시험 위치: `frontend/src/features/access/access.test.tsx`(`/me` 상태별 화면, 관리 메뉴, 작업 팀, 스텁 전환기 200/404), `frontend/src/features/access/permissions/permissions.test.tsx`(S6 격자, 변경 요약 확인창 호출 순서·본문, LAST_ADMIN, 입력 검증, 쪽 이동), `frontend/src/errors.test.ts`(오류 코드 문구). 시험은 fetch를 모의하며 실제 백엔드를 부르지 않는다.
  - 수동: 스텁이 켜진 로컬 환경에서 전환기로 관리자/일반/미등록 신원을 번갈아 선택해 위 화면을 확인한다.
- 프런트 시험 추가(03b 17-1):
  - `access.test.tsx`: 503 `/me`가 접근 안내가 아닌 일반 오류, 비활성 팀 선택 불가/첫 활성 팀 대체/활성 팀 없음, 홈 "비활성" 표시.
  - `permissions.test.tsx`: 비활성 칸 컨트롤 막힘(소속 해제만 가능), 409 `TARGET_INACTIVE` 문구, maxLength 100/200과 제출 때 재검사.
  - `errors.test.ts`: `SERVICE_UNAVAILABLE`·`TARGET_INACTIVE`·`METHOD_NOT_ALLOWED`.
  - 기존 S6 시험은 비활성 사용자 칸에 소속을 추가하던 부분을 활성 사용자(입력자 박) 칸으로 바꿨다.
- `/health` 새 필드(`views`, `views_failed_count`, `public_create`=false, `db_timezone`)가 본문에 있다(`skills/local-environment/SKILL.md`).

## 8-1. 정렬과 DV1 `current` (03b 19-1)
- A2 `/teams`, A5 `/users`(표시 이름), A1 `memberships`, DV1 `items`(표시 이름)는 한글 가나다순이다(`ko-KR-x-icu`, 자세한 방식·한계·collation이 없을 때의 동작은 `skills/dataset-definition/SKILL.md`의 "이름순 정렬"). 같은 이름은 `id` 순. DV1 `items`는 이전에는 로그인 ID 순이었다.
- DV1 `current`는 쿠키의 로그인 ID 그대로이며 등록 여부와 무관하다(스텁 전용 경로라 쿠키에 담긴 값을 되돌려 줄 뿐 DB를 더 읽지 않는다). 등록되지 않은 값이면 `items`에 없으므로 화면이 "(미등록)"으로 보여 준다. 쿠키가 없을 때만 `null`이다. 시험: `test_stub.py`, 정렬은 `test_name_sorting.py`(pg 변형에서 순서 단정).
- 시작 자가 점검에 collation 존재 확인이 추가됐다(경고만, 시작 거부 없음).

## 9. 연관 Skill
- `local-environment`: 환경 기동·마이그레이션 왕복·`/health` 필드·스텁 스위치(`AUTH_STUB_ENABLED`) 설정, 시작 자가 점검 실패 대응
- `dataset-definition`(FU-1b): (데이터셋·열 정의 변경 `dataset.*`·`column.*`은 감사 기록에 남는다, 5-1) 팀의 `definer` 역할로 데이터셋을 만들고(관리자도 그 팀 소속 `definer`여야 한다) 팀 이름·코드를 이 모듈의 읽기 service로만 읽는다. `/api/me`의 `memberships[].team_is_active`를 작업 팀 선택에 쓴다
- `data-entry`(FU-1c): `입력(팀)` = 그 팀의 `entry` 또는 `definer`(관리자도 소속 역할이 있어야 한다)로 행 입력(C2~C4)을 판정하고, 행 조회(C1)는 인증된 활성 사용자 누구나 한다
- `formula-column`(FU-1d): (계산 열 만들기·고치기 `formula_column.*`은 감사 기록에 남고 수식 원문은 남지 않는다) 수식 검사·미리보기·계산 열 만들기·고치기는 정의(팀) 권한, 수식 보기·오류 칸 점검은 인증된 모두, 뷰 점검·다시 시도는 관리자(05 §4). 이 Skill의 인증 스텁·시험 절차를 쓴다
- `dashboard-link`(FU-1e): (대시보드 연결 등록·변경 `dashboard.*`은 감사 기록에 남고 입장권 발급은 남지 않는다) 팀 이름 변경(A4)이 부르는 `DatasetSyncPort`를 구현해 Superset 가상 데이터셋 이름을 갱신하고(팀 단위, 그 팀의 데이터셋만), 대시보드 연결·입장권 발급(E1~E6, 권한 매트릭스에 포함)에 이 모듈의 신원·권한을 쓴다
- `admin-cleanup`: 수동 `psql` 정리는 서비스를 거치지 않아 감사 기록에 남지 않는다(5-1 운영 주의)
- `reference-values`(FU-3): 기준값 쓰기(R2·R3·R5)는 관리자 전용(403이 본문 검사보다 먼저)이며 감사 행위 3개를 남긴다. 감사 CHECK는 `0009`에서 20개·대상 5종으로 늘었고 `downgrade 0008`은 기준값 뷰나 새 감사 행이 있으면 거부한다.
