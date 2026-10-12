---
name: permission-management
description: 포털의 팀·사용자·소속(정의 담당자/입력자) 관리와 내 정보 조회, 최초 관리자 만들기, 개발·시험용 인증 스텁 사용법. "팀 만들어줘", "사용자 등록", "관리자 지정", "정의 담당자로 바꿔줘", "첫 관리자 만들기", "스텁으로 로그인" 같은 요청에 사용한다. 화면(S1, S6)은 FU-1a 프런트 단위에서 붙고 이 문서는 backend API·명령 기준이다.
---

# permission-management — 팀·사용자·권한 관리

## 1. 목적
관리자가 팀을 만들고, 사용자를 사전 등록하고, 사용자를 팀에 정의 담당자(`definer`) 또는 입력자(`entry`)로 넣고 빼며, 비활성화한다. 모든 사용자는 자기 정보와 소속 팀을 본다. 인증된 모든 사용자는 모든 팀의 데이터를 열람할 수 있고(별도 역할 값 없음), 관리자는 팀 소속 역할이 없으면 데이터셋 정의·입력 권한이 없다(06 §4-1).

## 2. 사용 조건 / 사전 요구사항
- `local-environment` 통과(`migrate`가 `0003`까지 적용). backend는 시작 자가 점검을 통과해야 뜬다(`bi_app`의 위험한 속성, `bi_data` 객체 종류 등. `skills/local-environment/SKILL.md` 7절).
- 로그인 방식(미결정 8번)이 정해지기 전에는 **인증 스텁**으로만 신원을 만든다. 스텁은 `AUTH_STUB_ENABLED=true`이고 `APP_ENV`가 명시적으로 `local` 또는 `test`일 때만 켜진다(그 밖이면 backend가 시작하지 않는다).
- 역할: A1·A2는 인증된 활성 사용자 누구나, A3~A9는 관리자만. 미등록 사용자는 403 `USER_NOT_REGISTERED`, 비활성 사용자는 403 `USER_INACTIVE`, 신원이 없으면 401 `UNAUTHENTICATED`.
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
| A8 `PUT /api/teams/{team_id}/members/{user_id}` | `role`: `definer` 또는 `entry`(소속이 없으면 추가, 있으면 역할 변경) |
| A9 `DELETE /api/teams/{team_id}/members/{user_id}` | 없음 |
| 서버 명령 | `--login-id`, `--display-name` (아래 5절) |

사용자 표시 이름 100자와 로그인 ID 200자 상한은 계약(05 §1)에 없어 임시로 둔 값이다(계약 보완 대기).

## 4. 출력
- A1 `GET /api/me` 200 `{id, display_name, is_active, is_admin, memberships[{team_id, team_code, team_name, role}]}`
- A2·A5 200 `{items, total, limit, offset}`. 팀 항목 `{id, code, name, is_active}`(팀 이름순), 사용자 항목 `{id, login_id, display_name, is_admin, is_active, memberships[{team_id, role}]}`(표시 이름순)
- A3 201 팀, A4 200 팀, A6 201 사용자(`memberships` 빈 목록), A7 200 사용자, A8 200 `{team_id, user_id, role}`, A9 204
- 오류는 모두 `{"error": {"code", "message", "details", "request_id"}}`이고 `message`는 한국어다.
  - 409 `ALREADY_EXISTS` + `details.field`(`code`, `name`, `login_id`), 409 `LAST_ADMIN`(마지막 활성 관리자의 관리자 해제·비활성화 거부), 404 `NOT_FOUND`(없는 팀·사용자·소속), 422 `VALIDATION_ERROR`(`details.fields[{field, code, message}]`)
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
S1(작업 팀 선택, 개발 빌드 한정 스텁 신원 전환기)과 S6(팀×사용자 격자, 관리자)은 FU-1a 프런트 단위에서 붙는다. 이 문서는 backend 기준이다.

## 6. 관련 UI / API / command / DB
- UI: S1 포털 셸·접근 안내, S6 권한 관리(`docs/decisions/04-modules.md` §4)
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
| 409 `LAST_ADMIN` | 활성 관리자가 이 사람 하나뿐 | 다른 사용자를 먼저 관리자로 지정(A6/A7) |
| 409 `ALREADY_EXISTS` | `details.field`가 가리키는 값이 이미 있음 | 다른 코드·이름·로그인 ID를 쓴다(로그인 ID는 대소문자 구분) |
| `create-admin` 종료 2 | 입력 오류 또는 같은 로그인 ID의 기존 일반·비활성 사용자 | 메시지 확인. 기존 사용자는 화면·API로 바꾼다 |
| `create-admin` 종료 1 | DB 접속·표 없음 | `docker compose ps`, `logs migrate backend`(`0003` 적용 여부) |
| backend가 시작하지 않음 | 시작 자가 점검 거부 또는 스텁 설정 거부 | `docker compose logs backend`의 메시지(`시작하지 않는다: …`). 속성 이름만 나오고 비밀은 나오지 않는다 |
| 응답 문제 추적 | | 오류 본문 `request_id`로 `docker compose logs backend`를 찾는다 |

## 8. 검증 방법
- 자동(DB 없이, `docker build --target test backend`와 같다): `pytest`. API 시험은 SQLite로 돌고 `pg` 변형은 건너뛴다.
- 자동(실제 PostgreSQL, 권장): tmpfs 시험 DB로 `pg` 변형까지 실행한다. 정적 표 권한 매트릭스(`has_table_privilege`/`has_column_privilege` 대조 + 실제 UPDATE/DELETE 거부 42501), `bi_readonly` 읽기 불가, 제약(CHECK/UNIQUE/FK), LAST_ADMIN 경쟁·교착, 시작 자가 점검(속성 5가지, `bi_data` 객체 종류), 스텁·CLI·API 전체가 대상이다. 안전장치: 서버가 `fsync=off`(시험 DB 서비스만)가 아니면 건너뛴다.
```
docker compose --profile test up -d --wait postgres-test
docker compose --profile test run --rm --no-deps -e PGHOST=postgres-test db-bootstrap
docker build --target test -t bi-wizard-backend-test backend
docker run --rm --network bi-wizard_default --env-file .env -e POSTGRES_HOST=postgres-test bi-wizard-backend-test pytest
docker compose --profile test stop postgres-test && docker compose --profile test rm -f postgres-test
```
(네트워크 이름은 compose 프로젝트 이름에 따른다: `docker network ls`. 이 시험은 `POSTGRES_USER`/`POSTGRES_PASSWORD`/`*_PASSWORD`가 필요하다. 시험 DB는 새 DB여야 한다: 시험이 `users`·`teams`·`team_members`의 행을 지운다.)
- 마이그레이션: `python -m migrations.roundtrip`(`skills/local-environment/SKILL.md` 5절)이 upgrade → downgrade → upgrade와 `alembic check`, `0003`의 표·열 단위 권한 상태를 확인한다.
- 권한 매트릭스: `backend/tests/test_permission_matrix.py`가 A1~A9, DV1~DV3 × 역할(관리자, 정의 담당자, 입력자, 다른 팀 구성원, 비소속 읽기, 비활성, 인증 없음)을 확인하고, 앱의 모든 보호 경로가 표에 있는지도 확인한다. 새 엔드포인트를 더하면 이 표에 행을 더해야 시험이 통과한다.
- 수동: 위 스텁 curl로 관리자 로그인 후 팀 만들기 → 사용자 등록 → 소속 지정 → `/api/me`(해당 사용자)로 소속 확인, 마지막 관리자 해제 시 409.
- `/health` 새 필드(`views`, `views_failed_count`, `public_create`=false, `db_timezone`)가 본문에 있다(`skills/local-environment/SKILL.md`).

## 9. 연관 Skill
- `local-environment`: 환경 기동·마이그레이션 왕복·`/health` 필드·스텁 스위치(`AUTH_STUB_ENABLED`) 설정, 시작 자가 점검 실패 대응
- `dataset-definition`(예정, FU-1b): 팀의 `definer` 역할로 데이터셋을 만들고 팀 이름·코드를 이 모듈의 읽기 service로만 읽는다
- `dashboard-link`(예정, FU-1e): 팀 이름 변경(A4)이 부르는 `DatasetSyncPort`를 구현해 Superset 가상 데이터셋 이름을 갱신하고, 대시보드 연결·입장권 발급에 이 모듈의 신원·권한을 쓴다
