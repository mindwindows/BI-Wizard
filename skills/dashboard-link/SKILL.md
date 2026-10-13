---
name: dashboard-link
description: 포털 데이터셋을 Superset 가상 데이터셋으로 자동 등록·동기화하고, 관리자가 Superset 대시보드(임베드 번호)를 포털에 연결하면 사용자가 포털 안에서 그 대시보드를 보게 하는 기능. 동기 상태 조회·다시 시도, 대시보드 등록·해제, 입장권(guest token) 발급과 사용자별 429 한도를 다룬다. "Superset에 데이터셋이 안 보여요", "동기 상태가 실패예요", "대시보드 연결", "임베드 번호(uuid)", "입장권", "요청이 너무 많습니다", "차트 만들기" 같은 요청에 사용한다. 화면(S2 동기 상태 열, S7 대시보드, S8 연결 관리, S9 동기 현황)은 5절 "사람(화면)"에 합친다.
---

# dashboard-link — Superset 등록·대시보드 연결·입장권 발급

## 1. 목적
팀이 포털에서 만든 데이터셋(`dataset-definition`)과 계산 열(`formula-column`)을 **서버가 Superset에 읽기 쉬운 이름의 가상 데이터셋으로 등록**하고, 정의가 바뀌면 자동으로 다시 맞춘다. 작성자는 Superset에서 차트와 대시보드를 만들고, 관리자가 그 대시보드의 임베드 번호를 포털에 연결하면 모든 사용자가 포털 화면 안에서 대시보드를 본다. 브라우저는 Superset REST를 부르지 않는다. 서버가 짧게 쓰는 입장권(5분)만 발급해 주고, Superset이 멈춰도 데이터셋 만들기·입력·수식은 계속 된다.

## 2. 사용 조건 / 사전 요구사항
- 환경: `local-environment` 통과. `superset-init`이 성공해 서비스 계정(`SUPERSET_SERVICE_USER`, 기본 `bi_service`)과 발급 전용 계정(`SUPERSET_GUEST_ISSUER_USER`, 기본 `bi_guest_issuer`), 역할 `bi_guest`가 있어야 한다. backend는 `SUPERSET_APP_ROOT`와 위 계정 변수 4개(`*_USER`, `*_PASSWORD` 둘씩)가 **모두** 있을 때만 Superset 연동을 켠다. 하나라도 없으면 동기화 요청은 아무 일도 하지 않고(E1은 모두 `pending`) 입장권 발급은 503이다. 새 환경변수는 없다.
- `migrate`가 `0006`까지 적용(정적 표 `superset_datasets`, `superset_dashboards`).
- 권한(05 §4):
  - **E1 동기 상태·E3 대시보드 목록·E6 입장권: 인증된 활성 사용자 누구나.** E1의 `last_error`(실패 사유)는 관리자에게만 보이고 다른 사용자에게는 `null`이다.
  - **E2 다시 시도·E4 대시보드 등록·E5 변경: 관리자만.** `include_inactive=true`(해제된 대시보드 포함)도 관리자만이다(비관리자는 403).
  - 비활성 사용자 403 `USER_INACTIVE`, 신원 없음 401. 권한 검사는 본문·쿼리 검증보다 먼저다.
- 관리자가 Superset에서 직접 해야 하는 일(포털이 대신하지 않는다): 차트·대시보드 만들기(작성자), **대시보드 임베드 켜기와 허용 도메인(`allowed_domains`) 지정**, 임베드 번호(uuid) 복사. 임베드는 `can_set_embedded`를 가진 `Admin`만 켤 수 있고 서비스 계정·작성자 역할(`bi_author`)은 못 한다.
- 선행 데이터: 팀·데이터셋. Superset 쪽 업무 데이터 연결 `BI-Wizard (read-only)`(`superset-init`이 등록, 이름은 코드 상수)가 하나뿐이어야 한다.

## 3. 입력
공통: JSON UTF-8, snake_case, 오류 형식은 05 §1. 정의되지 않은 필드는 422.

### E1 `GET /api/superset/datasets`
쿼리(모두 선택): `limit`(기본 50, 1~200), `offset`, `sync_status`(`pending`|`registered`|`failed`), `team_id`, `dataset_id`(여러 번 반복 가능), `dataset_ids`(쉼표 목록, 합쳐서 최대 200개). 잘못된 값은 422. 정렬은 팀 이름·데이터셋 이름(한글 가나다순).

### E2 `POST /api/superset/sync` (관리자)
`{dataset_ids?: int[]}`(최대 1,000개). 본문 생략 또는 `dataset_ids` 생략 = 등록 행이 없거나 `pending`·`failed`인 데이터셋 전부. 번호를 주면 모두 존재해야 하고 하나라도 없으면 404로 전체를 거부한다.

### E3 `GET /api/dashboards`
쿼리: `include_inactive`(관리자만 true), `limit`·`offset`.

### E4 `POST /api/dashboards` (관리자)
`{name, embedded_uuid}`. `name`은 앞뒤 공백을 지우고 1~100자, 제어문자 불가. `embedded_uuid`는 앞뒤 공백을 지우고 **소문자로 바꾼 뒤 하이픈 있는 36자 정규형**이어야 한다(하이픈 없는 32자·중괄호·`urn:` 형태는 422 `BAD_FORMAT`). 이미 등록된 번호(대소문자 무시)는 409 `ALREADY_EXISTS`(`details.field = "embedded_uuid"`).

### E5 `PATCH /api/dashboards/{dashboard_id}` (관리자)
`{name?, is_active?}` 중 하나 이상. `embedded_uuid`·그 밖의 키는 422(번호는 바꿀 수 없다: 다른 번호면 새로 등록한다). 없는 번호 404.

### E6 `POST /api/dashboards/{dashboard_id}/guest-token`
**본문 없음**(빈 본문만 허용, `{}`를 포함해 무엇이든 보내면 422). 포털의 대시보드 `id`만 받고, 서버가 등록 표의 embedded uuid를 찾는다. 클라이언트가 보낸 `rls`·uuid·Superset 번호는 받지 않는다.

## 4. 출력
- E1: `{items[{dataset_id, superset_name, sync_status, synced_at, last_error}], total, limit, offset}`. 등록 행이 없는 데이터셋은 `pending`이고 `superset_name`은 `[<팀 이름>] <데이터셋 이름>`으로 계산한 값이다. `synced_at`은 `+09:00` ISO 시각 또는 `null`.
- E2: **202** `{accepted: [dataset_id…]}`(접수일 뿐이다. 결과는 E1을 다시 읽어 확인). Superset이 멈춰 있어도 접수는 성공한다.
- E3·E4·E5: 대시보드 `{id, name, embedded_uuid, is_active}`(목록은 이름순). `embedded_uuid`는 모든 사용자에게 읽기로 보인다(임베드 화면이 필요로 한다).
- E6: 200 `{token, expires_in: 300}` + 응답 헤더 `Cache-Control: no-store`, `Pragma: no-cache`. `expires_in`은 상수(5분)이며 서버는 토큰을 해석하지 않는다.
- DB: `superset_datasets`(데이터셋마다 한 줄: `superset_dataset_id`, `display_name`, `sync_status`, `synced_at`, `last_error`), `superset_dashboards`(`id`, `name`, `embedded_uuid` 유일·소문자 정규형, `is_active`, `created_at`). Superset 쪽에는 가상 데이터셋이 생긴다.

### 동기 상태(`sync_status`)
| 값 | 뜻 | 다음 |
| --- | --- | --- |
| `pending` | 등록 대기. 등록 행이 없거나 정의가 막 바뀌었다 | 작업 스레드가 처리 → `registered` 또는 `failed` |
| `registered` | Superset 가상 데이터셋이 현재 정의와 맞다 | 정의·팀 이름이 바뀌면 다시 `pending` |
| `failed` | 마지막 시도가 실패했다. `last_error`(관리자만)에 `코드: 한국어 요약` | 연결 문제(`UNAVAILABLE_*`)는 약 1분마다 자동 재시도, 그 밖은 E2 또는 다음 backend 시작 때 |

### 동기화가 하는 일 (한 데이터셋, 멱등)
1. 서비스 계정으로 로그인하고 업무 데이터 연결 번호를 **이름**(`BI-Wizard (read-only)`)으로 찾는다.
2. 고정 SQL `SELECT * FROM bi_data.dv_<번호>`로 이미 등록된 데이터셋을 찾는다(보관한 번호 → SQL 조회 순서). 있으면 새로고침, 없으면 `[팀] 데이터셋` 이름으로 만든다. 같은 이름이 이미 있으면 같은 SQL일 때만 채택한다. 어느 경우든 Superset에는 데이터셋이 하나만 있다.
3. 열 표시 이름을 **전체 열을 한 번에** 보내 갱신한다(Superset의 `columns`는 병합이 아니라 교체라, 일부만 보내면 나머지 열이 지워진다). `c_<번호>` 열은 포털의 열 표시 이름, `team`은 "팀", `row_id`는 "행 번호"가 된다. 열 수와 열 id는 바뀌지 않는다.
4. 성공하면 `registered`와 시각을 기록한다.

동기화를 요청하는 곳(모두 커밋 뒤): 데이터셋 만들기 B2, 이름·날짜 단위·기준 열 변경 B4(바뀐 경우만), 열 추가 B5, 열 변경 B6(바뀐 경우만), 계산 열 만들기·고치기 D4·D5, 뷰 다시 만들기 D10(다시 만들어진 데이터셋만), 팀 이름 변경 A4(그 팀의 데이터셋 전부). 가상 데이터셋 SQL은 위 고정 모양 하나뿐이고 서비스 계정만 등록한다. 요청 처리 중에는 Superset을 부르지 않는다: 데이터셋 만들기·열 추가·수식 저장·이름 변경·팀 이름 변경은 커밋 뒤 `pending` 표시와 대기열 투입만 하고, 단일 작업 스레드가 순서대로 Superset을 부른다. 같은 데이터셋의 중복 요청은 합쳐지고, 처리 도중 정의가 또 바뀌면 그 결과를 `registered`로 쓰지 않고 한 번 더 돌린다. 연결 실패·시간 초과·5xx가 연속 3회면 30초 동안 Superset을 부르지 않는다(서킷 브레이커).

### 시작할 때
backend는 Superset을 기다리지 않고 바로 시작한다. 작업 스레드가 Superset `/health`가 200이 될 때까지(최대 10분, 10초 간격) 기다린 뒤 활성 데이터셋 전체를 대조한다: 등록 행이 없거나 `pending`·`failed`이면 대기열에 넣고, `registered`는 Superset의 이름·열 수·열 표시 이름을 읽어 어긋나면 다시 동기화한다(커밋 직후 서버가 죽어 열 변경이 반영되지 않은 경우). 대조 자체는 읽기뿐이다.

### 입장권 발급 (E6)
발급 전용 계정으로 `POST /security/guest_token/`을 부른다. 본문은 항상 `user.username`(포털 사용자 번호 문자열)만, `resources`는 대시보드 하나(소문자 정규형 uuid), `rls`는 항상 빈 목록이다. 서버는 JWT를 만들거나 해석하지 않고(서명 키 없음) Superset이 준 글자를 그대로 돌려준다. 오류 대응: 연결 불가·시간 초과·5xx는 503 `SUPERSET_UNAVAILABLE`, Superset이 거부(로그인 실패, 임베드 안 켠 번호, 훅 거부)는 502 `SUPERSET_REJECTED`.

### 사용자별 429 (`GUEST_TOKEN_RATE_LIMITED`)
사용자당 **60초에 30회**(슬라이딩 윈도). 넘으면 429 + 헤더 `Retry-After`(초) + `details.retry_after`. 통과한 요청만 센다(거절된 요청을 계속 보내도 영원히 막히지 않는다). 없는 번호(404)를 두드리는 요청도 센다. 정상 사용(대시보드를 열 때 1회 + 보는 동안 약 5분마다 1회, 실패 시 10초마다 재시도)은 한도에 닿지 않는다.
- **저장은 프로세스 메모리다. backend 워커(프로세스)가 여러 개면 한도가 워커별로 걸려 실효 한도가 워커 수 배가 된다.** 지금은 워커 1개(`app/__main__.py`)라 문제가 없고, 워커를 늘리면 공유 저장소로 재설계한다(08 §4). 코드 상수는 `backend/app/superset/constants.py`다.

## 5. 실행 방법
### 사람(화면)
화면 절차(S2 동기 상태 열, S7 대시보드 보기, S8 연결 관리, S9 Superset 동기 구역, 오류 문구)는 프런트 단위 문서(`_workspace/fu1e-frontend-skill-notes.md`)를 이 절에 합친다. 관리자가 알아야 할 순서는 다음과 같다.

#### 대시보드 연결 (관리자)
1. Superset(`${SUPERSET_APP_ROOT}/`)에서 작성자가 차트와 대시보드를 만든다. 지원 차트는 선, 막대, 표, 큰 숫자(추세 포함), 원형, 혼합(막대+선) 6가지이고 날짜 필터가 적용되려면 차트에 시간 필터가 있어야 한다.
2. 관리자가 그 대시보드에서 **임베드를 켜고** 허용 도메인(`allowed_domains`)에 포털 주소(`http://호스트:포트` 형식, 경로 없음)를 넣는다. 화면에 나오는 36자 임베드 번호를 복사한다.
3. 포털 S8에서 이름과 번호를 등록한다(E4). 대문자로 붙여넣어도 소문자로 바뀐다.
4. 연결을 멈추려면 S8에서 해제한다(`is_active=false`, 새 입장권 발급이 멈춘다). **Superset의 임베드는 관리자가 따로 끈다**(이미 발급된 입장권은 최대 5분 동안 유효하다).

#### 운영 주의
- **Superset에 다른 데이터베이스 연결을 추가하지 않는다**(`docs/deploy-coordination.md` 44번). 이 안전 전제 때문에 훅의 포털 등록 번호 대조를 하지 않는다(`docs/decisions/08-superset-embedding.md` §9). 임베드를 켠 대시보드는 포털 등록과 일치시킨다.
- Superset에서 관리자가 가상 데이터셋(서비스 계정 소유)을 지우면 다음 동기화 때 새 번호로 다시 만들어지고 기존 차트는 데이터 오류가 된다. 가상 데이터셋 이름·열 표시 이름을 Superset 화면에서 손으로 바꾸지 않는다(다음 동기화가 포털 값으로 되돌린다).

### AI / curl (스텁 로그인 쿠키 `bi_stub_login`은 `permission-management` 참고)
```
# 관리자: 동기 상태와 사유
curl -b "bi_stub_login=admin" "http://127.0.0.1:8000/api/superset/datasets?sync_status=failed"
# 관리자: 다시 시도(접수)
curl -b "bi_stub_login=admin" -X POST http://127.0.0.1:8000/api/superset/sync
# 관리자: 대시보드 등록
curl -b "bi_stub_login=admin" -H 'Content-Type: application/json' \
  -d '{"name":"월간 현황","embedded_uuid":"<Superset에서 복사한 36자>"}' http://127.0.0.1:8000/api/dashboards
# 누구나: 입장권(본문 없음, 응답을 저장하거나 로그에 남기지 않는다)
curl -b "bi_stub_login=viewer" -X POST http://127.0.0.1:8000/api/dashboards/1/guest-token -o /dev/null -w '%{http_code}\n'
```
(`${APP_BASE_PATH}/api`가 실제 경로다. 위는 backend 직접 호출 예시이며 토큰 값을 출력하지 않도록 `-o /dev/null`을 쓴다.)

## 6. 관련 UI / API / command / DB
- UI: S2 데이터셋 목록의 "동기 상태" 열, S7 대시보드, S8 대시보드 연결 관리(관리자), S9 관리자 현황의 Superset 동기 구역(관리자)
- API: `GET /api/superset/datasets`(E1), `POST /api/superset/sync`(E2), `GET`·`POST /api/dashboards`(E3·E4), `PATCH /api/dashboards/{id}`(E5), `POST /api/dashboards/{id}/guest-token`(E6)
- 코드: `backend/app/superset/`(`client.py` Superset REST, `sync.py` 한 건 절차, `worker.py` 대기열·작업 스레드·서킷 브레이커·시작 대조, `tokens.py` 입장권 발급, `ratelimit.py` 사용자별 한도, `naming.py` 이름·SQL 규칙, `service.py`·`router.py`·`repo.py`)
- command: 없음(첫 관리자 명령 등은 `permission-management`)
- DB: `superset_datasets`, `superset_dashboards`(revision `0006`, `bi_app`은 명시 GRANT만: 두 표 모두 DELETE 없음, `bi_readonly`·Superset에는 공개하지 않음)
- 환경변수(기존, 새 변수 없음): `SUPERSET_APP_ROOT`, `SUPERSET_SERVICE_USER`/`_PASSWORD`, `SUPERSET_GUEST_ISSUER_USER`/`_PASSWORD`. Secret이라 코드·로그·응답·`last_error`에 넣지 않는다. 내부 주소 `http://superset:8088`은 코드 상수다.

## 7. 실패 시 확인 방법
| 증상 | 원인 | 확인과 해결 |
| --- | --- | --- |
| 동기 상태가 계속 `pending` | 작업 스레드가 Superset 준비를 기다리는 중이거나 큐가 밀림 | `${SUPERSET_APP_ROOT}/health`가 200인지(`docker compose ps`), backend 로그 `Superset 시작 대조 완료`. 한참 지나도 그대로면 관리자가 E2로 다시 시도 |
| `failed` + `UNAVAILABLE_CONNECT`/`UNAVAILABLE_TIMEOUT`/`UNAVAILABLE_5XX` | Superset이 멈췄거나 느리다 | `docker compose ps superset`, 로그. Superset이 돌아오면 약 1분 안에 자동 재시도된다. 서킷 브레이커가 열려 있으면 30초 뒤에 다시 시도 |
| `failed` + `AUTH_FAILED` | 서비스 계정 로그인/권한 실패(비밀번호가 `superset-init`과 다름, 역할 변조) | `docker compose logs superset-init`의 `bi_service` 줄, `.env`의 `SUPERSET_SERVICE_*` 확인. `superset-init`을 다시 실행하면 비밀번호와 역할을 되돌린다 |
| `failed` + `NOT_OWNER` | 서비스 계정이 소유하지 않은 데이터셋(관리자가 같은 SQL로 만든 것 등) | Superset에서 그 데이터셋을 지우거나 이름을 바꾼 뒤 E2 |
| `failed` + `NAME_CONFLICT` | 같은 이름의 다른 데이터셋이 Superset에 있다 | Superset에서 그 데이터셋 이름을 바꾸거나 포털 데이터셋 이름을 바꾼다 |
| `failed` + `VIEW_MISSING` | 포털 `dv_` 뷰가 없다(수식 뷰 재생성 실패) | S9의 뷰 재생성 구역(`formula-column`)에서 다시 시도한 뒤 E2 |
| `failed` + `DB_NOT_FOUND`/`DB_MISMATCH` | Superset 업무 데이터 연결 이름이 `BI-Wizard (read-only)`가 아니거나 서비스 계정이 못 본다 | `superset-init` 로그, Superset 데이터베이스 목록에 연결이 **하나뿐**인지 확인 |
| `failed` + `REJECTED_<상태>` | Superset이 그 요청을 거부했다 | 상태 번호로 원인을 좁힌다(422: 입력/뷰, 403: 권한). 응답 본문은 일부러 남기지 않으므로 `docker compose logs superset`를 본다 |
| E6 503 `SUPERSET_UNAVAILABLE` | Superset 연결 불가/시간 초과 또는 연동 설정 없음(변수 5개 중 누락) | 위와 같고, backend 환경변수 5개가 모두 있는지 확인 |
| E6 502 `SUPERSET_REJECTED` | 발급 계정 로그인 실패, Superset에서 임베드를 켜지 않은 번호, 훅 거부 | 포털 등록 번호가 Superset 임베드 번호와 같은지(오타), 임베드가 켜져 있는지, `superset-init` 로그의 `bi_guest_issuer` |
| E6 429 `GUEST_TOKEN_RATE_LIMITED` | 한 사용자가 60초에 30회를 넘김(브라우저 재시도 폭주, 시계가 5분 이상 어긋난 PC) | `Retry-After` 초 뒤에 다시. 반복되면 그 사용자의 브라우저 시계와 네트워크를 확인 |
| 대시보드가 흰 화면/403 JSON | 임베드 `allowed_domains`에 포털 주소가 없음(이 경우 입장권 발급은 성공한다) | Superset에서 임베드 설정의 허용 도메인에 포털 origin 추가 |
| E4 409 `ALREADY_EXISTS` | 같은 번호가 이미 등록(해제된 항목일 수 있음) | `GET /api/dashboards?include_inactive=true`에서 찾아 E5로 다시 활성화 |
- 오류 응답과 `last_error`에는 SQL·Superset 응답 본문·URL·토큰·비밀번호가 없다(사유 코드와 고정 한국어 요약뿐). 상세는 backend 로그에도 예외 클래스 이름과 사유 코드만 남는다.

## 8. 검증 방법
- 자동(DB 없이, `docker build --target test backend`와 같다): `pytest -m "not slow"`. Superset은 가짜 서버(`backend/tests/fake_superset.py`, 프로브 문서의 실제 응답 모양)를 `httpx.MockTransport`로 연결한다. 파일별 내용:
  - `test_superset_client.py`: 로그인 재사용, 401일 때만 갱신·재시도, CSRF 400 재시도와 훅 거부 400 비재시도, 연결 오류 → 사유 코드, 로그에 비밀번호·토큰·URL 없음, 전체 열 `PUT`(일부 열 호출 없음)
  - `test_superset_sync.py`: 등록·재동기화 멱등(Superset에 데이터셋 하나, 열 수·id 불변), 이름 변경, 중복 이름 채택/충돌, DB 불일치, 소유자 아님, 시작 대조 판정
  - `test_superset_worker.py`: 요청은 Superset을 부르지 않음(P4), 큐 중복 병합, 상태 기계, 서킷 브레이커, 세대 번호, 팀 단위 갱신, 시작 대조, Superset 정지 → 복구
  - `test_superset_api.py`: E1~E6(권한·입력 검증·오류 코드), 입장권 요청 본문(`user`·`rls: []`·소문자 uuid), 사용자별 429(한도·시계 주입), 토큰이 로그에 없음, Superset을 멈춘 채 앱 즉시 시작과 다른 API 정상, 복구, 역할 × 엔드포인트
  - `test_superset_units.py`: 고정 SQL 정규식, 속도 제한기, 서킷 브레이커, 사유 코드 요약, 서명 흔적 없음(`GUEST_TOKEN_JWT_SECRET`·JWT 라이브러리 0)
  - `test_permission_matrix.py`: 모든 보호 경로(E1~E6 포함) × 7가지 역할
- 자동(실제 PostgreSQL): `skills/permission-management/SKILL.md` 8절 절차로 tmpfs 시험 DB를 띄우고 `REQUIRE_PG=1 pytest -m "not slow"`(`pg` 변형 skip 0). `test_static_acl.py`가 `0006` 두 표의 `bi_app` 표·열 권한(DELETE·TRUNCATE·불변 열 거부, 업서트 동작), `bi_readonly` 접근 거부, 제약을 확인한다. 마이그레이션: `python -m migrations.roundtrip`(0006 한 단계 포함)와 `alembic check`.
- 수동(Superset이 떠 있는 환경): 데이터셋을 만들고 S9/E1에서 `pending` → `registered`, Superset 화면에서 `[팀] 이름` 데이터셋과 열 표시 이름 확인, `docker compose stop superset` 뒤 데이터셋을 만들면 `failed`(`UNAVAILABLE_CONNECT`)인데 입력 API는 정상이고 `docker compose start superset` 뒤 자동으로 `registered`가 되며 Superset에 중복이 없는지, 임베드를 켠 대시보드를 S8에 등록해 S7에서 보이는지.

## 9. 연관 Skill
- `dataset-definition`: 데이터셋·열 정의 변경(B2·B4~B6)이 커밋 뒤 `DatasetSyncPort`로 동기화를 요청한다. S2 목록에 동기 상태 열을 붙인다
- `formula-column`: 계산 열 추가·수정(D4·D5)과 뷰 재생성이 Superset 열 목록을 바꾸므로 동기화 대상이다. 가상 데이터셋 SQL은 `dv_<번호>` 뷰를 읽는다. 열 표시 이름은 계산 열의 이름도 포함한다
- `permission-management`: 팀 이름 변경(A4)이 팀 단위 동기화를 요청한다. 인증 스텁·권한 매트릭스·실제 DB 시험 절차(8절)를 이 Skill이 쓴다. 입장권 `user`는 포털 사용자 번호다
- `local-environment`: `0006` 마이그레이션 왕복, `httpx` 운영 의존성과 `certifi` 예외 기록, `superset-init`(서비스·발급 계정, `bi_guest` 역할), 하위 경로 설정
- `data-entry`: 입력 값이 바뀌어도 Superset 데이터셋은 뷰를 읽으므로 동기화가 필요 없다(정의가 바뀔 때만)
- `admin-cleanup`: Superset 쪽 객체 정리 절차(데이터셋·대시보드 수동 삭제, 임베드 해제)
