---
name: permission-management
description: 포털의 팀·사용자·소속(정의 담당자/입력자) 관리와 내 정보 조회, 최초 관리자 만들기, 개발·시험용 인증 스텁 사용법. "팀 만들어줘", "사용자 등록", "관리자 지정", "정의 담당자로 바꿔줘", "첫 관리자 만들기", "스텁으로 로그인" 같은 요청에 사용한다. 화면(S1, S6)은 FU-1a 프런트 단위에서 붙고 이 문서는 backend API·명령 기준이다.
---

# permission-management — 팀·사용자·권한 관리

## 1. 목적
관리자가 팀을 만들고, 사용자를 사전 등록하고, 사용자를 팀에 정의 담당자(`definer`) 또는 입력자(`entry`)로 넣고 빼며, 비활성화한다. 모든 사용자는 자기 정보와 소속 팀을 본다. 인증된 모든 사용자는 모든 팀의 데이터를 열람할 수 있고(별도 역할 값 없음), 관리자는 팀 소속 역할이 없으면 데이터셋 정의·입력 권한이 없다(06 §4-1).

## 2. 사용 조건 / 사전 요구사항
- `local-environment` 통과(`migrate`가 `0003`까지 적용. 지금 head는 `0005`로 데이터셋 표와 수식 표(`formulas`·`formula_deps`)가 더 있다). backend는 시작 자가 점검을 통과해야 뜬다(`bi_app`의 위험한 속성, `bi_app`의 `public` CREATE 권한, `bi_data` 객체 종류 등. `skills/local-environment/SKILL.md` 7절).
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
- 저장 위치: `users`, `teams`, `team_members`(DB 권한은 6절). 팀 이름이 실제로 바뀌면 **커밋 뒤** 팀 단위 동기화를 요청한다(`DatasetSyncPort.request_team_sync`). 구현체는 FU-1e(Superset 가상 데이터셋 이름 갱신)이고 지금은 아무것도 하지 않는 기본 구현이며, 요청이 실패해도 응답은 그대로다(오류 클래스 이름만 로그).

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

## 6. 관련 UI / API / command / DB
- UI: S1 포털 셸·접근 안내, S6 권한 관리(`docs/decisions/04-modules.md` §4). S1 `/`, `/access-denied`(경로는 `APP_BASE_PATH` 아래), S6 `/admin/permissions`, 구현 위치 `frontend/src/features/access/`
- API: A1~A9(05 §2-1), DV1~DV3(05 §2-6). 코드는 `backend/app/access/`(router·service·repo), 스텁은 `backend/app/auth/stub.py`, 사용자 조회는 `backend/app/auth/db_reader.py`
- command: `python -m app.cli create-admin`, `python -m app.cli seed-stub-users` (`backend/app/cli.py`)
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
| 409 `TARGET_INACTIVE` | A8 대상 팀 또는 사용자가 비활성 | `details.field`가 `team`이면 A4로 팀을 다시 사용 중으로, `user`이면 A7로 사용자를 다시 활성화한 뒤 소속을 지정한다 |
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
- 자동(실제 PostgreSQL, 권장): tmpfs 시험 DB로 `pg` 변형까지 실행한다. 정적 표 권한 매트릭스(`has_table_privilege`/`has_column_privilege` 대조 + 실제 UPDATE/DELETE 거부 42501, `users`·`teams`·`team_members`·`datasets`·`dataset_columns`·`formulas`·`formula_deps`), `bi_readonly` 읽기 불가, 제약(CHECK/UNIQUE/FK), LAST_ADMIN 경쟁·교착, 시작 자가 점검(속성 5가지, `bi_data` 객체 종류), 스텁·CLI·API 전체가 대상이다. 안전장치: 서버가 `fsync=off`(시험 DB 서비스만)가 아니면 건너뛴다.
```
docker compose --profile test up -d --wait postgres-test
docker compose --profile test run --rm --no-deps -e PGHOST=postgres-test db-bootstrap
docker build --target test -t bi-wizard-backend-test backend
docker run --rm --network bi-wizard_default --env-file .env -e POSTGRES_HOST=postgres-test bi-wizard-backend-test pytest
docker compose --profile test stop postgres-test && docker compose --profile test rm -f postgres-test
```
(네트워크 이름은 compose 프로젝트 이름에 따른다: `docker network ls`. 이 시험은 `POSTGRES_USER`/`POSTGRES_PASSWORD`/`*_PASSWORD`가 필요하다. 시험 DB는 새 DB여야 한다: 시험이 `users`·`teams`·`team_members`의 행을 지운다.)
- 마이그레이션(위 pytest를 돌린 DB와 **다른 새 postgres-test**에서 따로 실행한다. 왕복 스크립트는 DB가 이미 `0003` 이상이면 "빈 테스트 DB에서만 실행하세요"로 중단한다): `python -m migrations.roundtrip`(`skills/local-environment/SKILL.md` 5절)이 upgrade → downgrade → upgrade와 `alembic check`, `0003`·`0004`·`0005`의 표·열 단위 권한 상태(0005·0004 한 단계 내림 포함)를 확인한다.
- 권한 매트릭스: `backend/tests/test_permission_matrix.py`가 A1~A9, B1~B6(`skills/dataset-definition`), C1~C4(`skills/data-entry`), D1~D10(`skills/formula-column`: 읽기 D1·D6·D7·D8, 정의(팀) D2~D5, 관리자 D9·D10), DV1~DV3 × 역할(+ B2의 비활성 팀 행: 정의 담당자 409 `TARGET_INACTIVE`, 그 밖 역할은 403·401로 권한 판정이 먼저)(관리자, 정의 담당자, 입력자, 다른 팀 구성원, 비소속 읽기, 비활성, 인증 없음)을 확인하고, 앱의 모든 보호 경로가 표에 있는지도 확인한다. 새 엔드포인트를 더하면 이 표에 행을 더해야 시험이 통과한다.
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
- `dataset-definition`(FU-1b): 팀의 `definer` 역할로 데이터셋을 만들고(관리자도 그 팀 소속 `definer`여야 한다) 팀 이름·코드를 이 모듈의 읽기 service로만 읽는다. `/api/me`의 `memberships[].team_is_active`를 작업 팀 선택에 쓴다
- `data-entry`(FU-1c): `입력(팀)` = 그 팀의 `entry` 또는 `definer`(관리자도 소속 역할이 있어야 한다)로 행 입력(C2~C4)을 판정하고, 행 조회(C1)는 인증된 활성 사용자 누구나 한다
- `formula-column`(FU-1d): 수식 검사·미리보기·계산 열 만들기·고치기는 정의(팀) 권한, 수식 보기·오류 칸 점검은 인증된 모두, 뷰 점검·다시 시도는 관리자(05 §4). 이 Skill의 인증 스텁·시험 절차를 쓴다
- `dashboard-link`(예정, FU-1e): 팀 이름 변경(A4)이 부르는 `DatasetSyncPort`를 구현해 Superset 가상 데이터셋 이름을 갱신하고, 대시보드 연결·입장권 발급에 이 모듈의 신원·권한을 쓴다
