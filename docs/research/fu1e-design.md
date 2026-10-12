# FU-1 단위 1e 구현 전 설계 점검 (Superset 등록·임베딩)

작성: architect, 2026-10-12. 코드·`docs/`는 건드리지 않았다(이 파일만 `_workspace/fu1e/`에 썼다). 읽은 근거는 각 항목에 `파일:줄`로 적었다.
표지: **확인됨**(저장소 파일·실험 기록에서 직접 읽음) / **추정**(내 기억·추론, 구현 첫 시험에서 확인) / **확인하지 못함**(이 세션에서 도구 한계로 확인 불가). 이 세션에는 셸·Docker가 없어 Superset 6.1.0을 실행해 보지 못했다. 그래서 Superset REST의 세부는 03c 실험 기록을 근거로 하고, 기록에 없는 것은 §14의 "1e-0 프로브"로 먼저 확인하게 했다.

---

## 1. 사용자 사전 승인 필요 항목 (맨 앞)

**결론: 승인이 전혀 필요 없는 설계는 불가능하다.** 합격 기준에 "훅의 uuid 등록 대조"가 있는데, Superset 프로세스가 포털 정적 표를 읽을 길이 없어서 이를 만족하는 모든 안이 기준 외 설정·권한 확대·계약 밖 경로 중 하나를 요구한다(§5). 또 `httpx` 승격에 딸려 오는 전이 의존성 `certifi`가 MPL-2.0이라 하네스의 라이선스 원칙과 부딪친다. 이 두 건과 값 확인 한 건이 아래 표의 A~C이고, 나머지 1e는 승인 없이 진행할 수 있다.
새 환경변수는 **0개**, 새 의존성은 **A 한 건(전이)** 외 없음, 권한 확대는 **조건부 D 한 건**(지금 요청하지 않음)이다.

| 번호 | 항목 | 왜 필요한가 | 대안 | 권장 | 승인 없이 진행 가능한 범위 |
| --- | --- | --- | --- | --- | --- |
| **A** | **`httpx` 승격에 따른 `certifi`(MPL-2.0) 운영 런타임 진입** | 03b 21-3이 승인한 `httpx` 0.28.1은 `certifi`를 필수로 끌고 온다(`backend/requirements-dev.txt:8,13`에 둘 다 있고, 운영 `requirements.txt`에는 `httpx`·`httpcore`·`certifi` 3개가 없다. `anyio`·`h11`·`idna`는 이미 있음 `backend/requirements.txt:6,10,11`). `certifi`는 지금 `docs/deploy-coordination.md:48`(23번)에 "테스트 단계 이미지, 개발·테스트 전용"으로만 허용돼 있고, `bi-review` 1번은 "우리 코드의 운영 런타임 의존성에 LGPL·MPL이 새로 들어오면 차단"(`.claude/skills/bi-review/SKILL.md:21`)이다. 승격하면 reviewer가 차단한다. (`httpx`의 `certifi` 필수 여부는 **추정**: PyPI 메타데이터 확인은 하지 못했으나 dev lock에 같이 있다) | (1) **예외 승인**: `certifi`를 수정·재배포 없이 이미지에 설치하는 것을 "주의" 항목으로 허용하고 23번 행을 "운영 런타임 포함"으로 고친다. (2) **표준 라이브러리 구현**(`urllib.request` + `http.cookiejar`, 새 의존성 0, `httpx` 승격 철회): 승인 불필요하지만 승인된 `httpx` 계획을 버리고 직접 HTTP 코드를 써야 한다(추정 +150줄, 시험은 로컬 `http.server` 가짜). (3) 다른 라이브러리(`urllib3` 등)는 새 의존성 승인이 또 필요해 부적합 | **(1)**. 내부 HTTP(`http://superset:8088`)라 TLS 번들을 거의 쓰지 않으며, `httpx.MockTransport`로 시험하기 쉽고 HTTP 코드를 직접 쓰는 위험이 없다. 회사 정책이 MPL 운영 포함을 막으면 (2) | 코드·시험 전부 작성 가능(dev 의존성에 이미 `httpx`가 있다). **다만 `requirements.in`·`requirements.txt`에 `httpx`를 넣는 커밋은 A 결정 뒤에**(그 전에는 운영 이미지가 `httpx` 없이 깨진다). 결정이 늦으면 §3의 `SupersetHttp` 얇은 인터페이스 뒤에 `httpx`/`urllib` 구현을 갈아 끼울 수 있게 해 둔다 |
| **B** | **훅의 embedded uuid 등록 대조(FU-1 이월 3번) 구현 방식** | 훅은 Superset 프로세스 안에서 돌고 포털 정적 표를 읽을 DB 권한이 없다(`bi_readonly`는 정적 표 권한 없음: `docs/decisions/06-data-model.md:94`, X-15). 어떤 방식이든 "포털 등록·활성 uuid 목록"을 Superset 쪽에 전달할 새 경로가 필요하다. **이 대조의 실효 이익은 작다**(§5-2: 이미 backend가 발급 전에 막고, 발급 계정 비밀은 backend 컨테이너에만 있다) | **H1** 공유 읽기 전용 볼륨의 허용 목록 파일(backend가 쓰고 Superset 훅이 읽음, AND 조건이라 권한을 넓히지 않고 좁히기만 함). **H2** `bi_readonly`에 `superset_dashboards` 열 단위 SELECT + 훅이 DB 직접 조회(권한 확대 + Superset 컨테이너에 DB 비밀 추가 전달). **H3** 훅이 backend 내부 HTTP 조회(`/api` 계약 밖 경로 + 인증 비밀 필요). **H0** 라이브 대조를 하지 않고 "backend 발급 전 검사 + Superset 기본 임베드 검사 + 훅 형식 검사"로 종결(이월 항목을 사용자가 수용) | **H1**을 권장하되, 이익이 작으니 비용을 감수하지 않겠다면 **H0**. H2·H3은 비추천 | H1이면 필요한 변경: `compose.yml`(이름 있는 볼륨 1개, backend 읽기쓰기·superset 읽기 전용 마운트), `backend/Dockerfile`(디렉터리 `/registry`를 `app:app`(10001) 소유로 생성), `superset/superset_config.py`(`_EXTRA_GUEST_TOKEN_CHECKS`에 파일 검사 추가). **전부 B 결정 뒤에 착수.** B 결정 전에도 가능한 것: backend의 파일 작성기와 훅 검사 함수를 순수 함수로 작성·단위 시험(마운트 없이), 나머지 1e 전체 |
| **C** | **입장권 발급 사용자별 속도 제한 한도 값** (08 §4 **[미답]**: "한도 값은 구현 때 제안") | 사용자별 429는 승인됐으나 값이 미정(`08-superset-embedding.md:72`, `05-api-contract.md:121`). 코드 상수이고 새 환경변수·설정이 아니다 | 60초에 10회(빡빡), 60초에 30회(제안), 5분에 5회(SDK 정상 갱신 빈도 그대로: 재시도·다중 탭에서 정상 사용자가 막힘) | **사용자당 슬라이딩 윈도 60초에 30회**, 초과 시 429 `GUEST_TOKEN_RATE_LIMITED` + `Retry-After`. 근거 §4-3 | 값은 구현·시험 시 코드 상수 하나라 바꾸기 쉽다. 승인 전에는 30/60초로 구현하고 시험은 한도를 주입해서 한다 |
| **D** | **(조건부, 지금은 요청하지 않음)** 서비스 계정 `bi_service`에 5번째 권한 `can_read Database` | 가상 데이터셋 등록 `POST /api/v1/dataset/`는 Superset `database` 번호가 필요한데, 서비스 계정은 `Database` 읽기가 없어 `GET /api/v1/database/`가 403이다(`docs/research/results/superset-r4-results.md:83`은 작성자 역할 기준, 서비스 계정 4권한은 `03c-gate3-experiment-results.md:217`). 실험은 번호 `1`을 하드코딩했다(`docs/research/experiments/r5/t1_register.py:4`). | ① `GET /api/v1/dataset/related/database`(`can_read Dataset`만으로, DB 접근 권한 필터가 걸린 목록을 돌려줄 것으로 **추정**) ② 코드 상수 `1` + 등록 직후 `GET /dataset/{id}`의 `database.database_name`이 상수 `BI-Wizard (read-only)`와 같은지 대조(어긋나면 그 데이터셋 `failed`, 사유 `DB_MISMATCH`) ③ `can_read Database` 추가 | **①, 실패 시 ②.** ③은 권한 확대라 ①②가 모두 실패했을 때만 그 자리에서 멈추고 요청 | ①②는 승인 불필요(새 환경변수·권한 없음). §14의 프로브 P-1로 먼저 확인 |
| **E** | **설계 문서 보강 확인**(승인된 08·05 문구를 코드가 약간 넘어서는 곳) | ① 시작 시 점검 범위를 `registered` 포함 전체로 넓힘(08 §2-1은 `pending`·`failed`만). 커밋 직후 프로세스가 죽으면 열이 추가된 `registered` 데이터셋이 Superset에 반영 안 된 채 남는데 감지 수단이 없다(06 §3-5: 정의 변경 트랜잭션은 `superset_*`를 쓰지 않는다). ② 시작 점검이 Superset 준비(`/health`)를 기다림: 빈 볼륨 새 설치에서 backend가 superset(약 80초 뒤)보다 먼저 떠서 처음 점검이 전부 `failed`가 되는 것을 막는다. ③ E1에 추가 쿼리(`dataset_ids`, `team_id`, `sync_status`)와 페이지 응답, E6의 `expires_in`은 상수 300 (05는 "목록", "5분"뿐) | 그대로 구현(① 없이는 복구 누락 가능, ② 없이는 새 설치마다 관리자가 수동 재시도) | 그대로 구현하고 §13의 문서 변경 제안을 승인 | 계약의 필드 **추가**는 05 §1 "계약 변경" 규칙상 허용이지만 ①②는 08의 승인 문구 변경이라 확인을 받는다. 확인 전에도 ③은 진행 가능 |
| F | (선택, 적용 후 보고 항목 후보) 훅의 `user.username`을 `^[1-9][0-9]{0,9}$`로 제한 | backend는 항상 `users.id` 문자열을 보낸다. 발급 계정이 유출돼도 임의 이름의 입장권을 못 만들게 한다 | 하지 않음 | 하고 싶으면 "거부 강화"라 적용 후 보고 가능(`CLAUDE.md` 사전 승인 규칙). 8번 인증 확정 뒤 `user` 식별자가 바뀌면 같이 갱신해야 한다 | 해당 없음(강제 아님) |

### 1-1. 승인이 필요 없다고 확인한 것
- **새 환경변수 0개.** 내부 Superset 주소는 코드 상수 `SUPERSET_INTERNAL_URL`(`backend/app/config.py:24`), 하위 경로·서비스·발급 계정 5개는 이미 backend에 전달돼 있다(`compose.yml:118-122`). 데이터베이스 이름 `BI-Wizard (read-only)`는 코드 상수(`superset/bi_roles.py:13`을 backend 상수로 복제).
- **compose/nginx 변경 0건**(B의 H1 제외). 같은 origin 하위 경로에서 Embedded는 설정 변경 없이 동작함이 확인돼 있다(X-18 `03c:190`, X-25 `03c:308-309`).
- **권한 확대 0건**(D 제외). `bi_app`의 0006 GRANT는 06 §2에 적힌 그대로(§6)라 새 확대가 아니다. 서비스·발급·guest 역할 목록은 바꾸지 않는다.
- revision `0006`, `httpx`(A 제외), `@superset-ui/embedded-sdk` 0.4.0은 이미 승인(03b 21-3, `03b:513-517`).
- 승인된 AP-1(직접 서명 금지)·AP-2(고정 SQL)·AP-12(코드 상수)를 그대로 따른다. backend는 `GUEST_TOKEN_JWT_SECRET`·JWT 서명 코드를 두지 않는다(`scripts/ci-validate-env.sh:179-182`).

---

## 2. 사실 근거와 확인 수준 요약

| 사실 | 수준 | 근거 |
| --- | --- | --- |
| 서비스 계정 4권한(`can_read/can_write Dataset`, `schema_access`, `can_read SecurityRestApi`)으로 조회·등록·이름 변경·새로고침·삭제 가능, 소유 데이터셋만 | 확인됨 | `03c:214-225`, `superset/bi_roles.py:35-40` |
| POST는 Bearer만으로 400 `CSRF token is missing`, 같은 세션 쿠키 + `X-CSRFToken` 필요, 접근 토큰 15분·갱신 토큰 30일 | 확인됨 | `08:37`, `03c:223` |
| 열 `columns`는 교체(전체 열 `{id, column_name, verbose_name}` 필요), 표시 이름 갱신 가능, 1,024자 초과 422 | 확인됨 | `03c:329-342` |
| 발급 계정은 `can_grant_guest_token`+`can_read SecurityRestApi`, `user` 생략 시 500, `rls` 빈 목록, 로그인 포함 약 240ms·세션 재사용 약 26ms | 확인됨 | `03c:314-324`, `bi_roles.py:42-45` |
| 훅은 발급 API 경로에서만 호출, `hook(body)->bool`, False면 400, 예외면 500 | 확인됨(소스+실측) | `08:68`, `superset_config.py:78-113` |
| SDK는 만료 5초 전 `fetchGuestToken`을 다시 부르고 실패 시 10초마다 재시도, 400초 유지 시 401 없음 | 확인됨(실험 SDK 버전은 **확인하지 못함**) | `03c:323`, `08:71`, `gate-status.md:74` |
| `bi_guest` 4권한만으로 6가지 차트 표시(테스트 페이지 SDK, 관리자 화면과 같은 값, STRIP true/false 동일) | 확인됨 | `08:54`, `gate-status.md:65,74` |
| Superset DB 번호 조회 방법 | **확인하지 못함** | §3-2, 프로브 P-1 |
| `GET /dataset/?q=(filters:!((col:sql,opr:eq,...)))`가 되는지 | **추정** | 프로브 P-2 |
| `@superset-ui/embedded-sdk` 0.4.0의 정확한 API·의존성·언마운트 때 갱신 타이머 정리 | **확인하지 못함**(웹 검색에서 0.4.0 자료를 못 찾음, 일반 README 패턴만 확인: `id`, `supersetDomain`, `mountPoint`, `fetchGuestToken`, `dashboardUiConfig`, `iframeSandboxExtras`, `referrerPolicy`) | §8 |
| SDK 0.4.0과 Superset 6.1.0의 호환 | **확인하지 못함**(1e 실측 항목, `03b:423`) | §8 |

---

## 3. backend → Superset 호출 설계

### 3-1. 모듈 배치 (`backend/app/superset/`, 04 §2-2·§3 의존 방향 준수)
| 파일 | 책임 | 비고 |
| --- | --- | --- |
| `constants.py` | `DATABASE_NAME="BI-Wizard (read-only)"`, `SCHEMA="bi_data"`, 타임아웃·한도 상수, `GUEST_TOKEN_EXPIRES_IN=300` | `ci-validate-env.sh`에 `superset/bi_roles.py`의 `DATABASE_NAME` 문자열과 같은지 정적 대조 추가 권장(§12 1e-a) |
| `http.py` | `SupersetSession`(계정 하나당 하나: 쿠키 항아리, 접근·갱신 토큰, CSRF 토큰, 잠금), 오류 `SupersetUnavailable`/`SupersetRejected` | `httpx.Client`(A 결정 뒤) 또는 표준 라이브러리 구현을 같은 인터페이스 뒤에 둔다 |
| `naming.py` | `superset_name(team_name, dataset_name)` = `[{team}] {dataset}`, `virtual_sql(dataset_id)` | SQL은 **템플릿 하나** `SELECT * FROM bi_data.{view_name(id)}`. 숫자는 `app.ddl.names.view_name`이 검증(`ddl/names.py:85`). 시험이 `^SELECT \* FROM bi_data\.dv_[1-9][0-9]*$`로 고정(AP-2, `bi-review` 7-4) |
| `repo.py` | `superset_datasets` 업서트·조회, `superset_dashboards` CRUD | SQLAlchemy 표현식만, `on_conflict_do_update`(내장) |
| `sync.py` | 데이터셋 하나 동기화 절차(§3-4), 오류→사유 코드 | 순수 함수에 가깝게(HTTP 클라이언트·세션 팩토리를 인자로) |
| `worker.py` | `SupersetDatasetSync`(`DatasetSyncPort` 구현), 단일 작업 스레드, 시작 점검 | §3-6 |
| `guest.py` | 입장권 발급, 발급 계정 세션, 속도 제한 | §4 |
| `ratelimit.py` | 사용자별 슬라이딩 윈도 | `core/limits.py:20-49`와 같은 스타일(잠금, 프로세스 메모리) |
| `service.py`, `router.py`, `schemas.py` | E1~E6 | §7 |
| `registry_file.py` | (H1만) 허용 목록 파일 작성 | B 결정 뒤 |

연결: `create_app`의 `dataset_sync`(기본 `NoopDatasetSync`, `main.py:135`)는 **Superset 접속 설정 5개가 모두 있을 때만** 실제 구현으로 교체한다. 시험 설정(값 없음)은 계속 no-op이라 기존 약 150개 시험에 영향이 없다. 엔진은 lifespan에서 만들어지므로(`main.py:94`) 구현체는 `bind(engine)`으로 나중에 받는다(`ViewStatus.bind`와 같은 방식, `main.py:101`).

### 3-2. 로그인·토큰·CSRF
| 단계 | 호출(기준 URL = `SUPERSET_INTERNAL_URL` + `SUPERSET_APP_ROOT`) | 비고 |
| --- | --- | --- |
| 준비 확인 | `GET {root}/health` (인증 없음) | compose healthcheck가 같은 경로 사용(`compose.yml:230`) |
| 로그인 | `POST {root}/api/v1/security/login` `{"username","password","provider":"db","refresh":true}` | 접근 토큰 15분(`03c:223`). 캐시 TTL은 **12분**(토큰을 해석하지 않고 단조 시계로, JWT를 backend에서 읽지 않는다) |
| 갱신 | 401이면 `POST {root}/api/v1/security/refresh`(Bearer 갱신 토큰), 실패 시 재로그인 | `08:37` |
| CSRF | `GET {root}/api/v1/security/csrf_token/`(Bearer) → 응답 토큰 + 같은 쿠키 항아리 | POST/PUT은 `X-CSRFToken` + 쿠키. 400이면 토큰을 다시 받아 1회 재시도 |
| 직렬화 | 로그인·갱신·CSRF 재취득은 계정별 잠금 안에서(`08:37`) | 로그인은 캐시 미스 때만 한다(FAB 로그인 빈도 제한 회피: **추정**) |

`httpx`(A 결정 시) 사용 규칙:
- `trust_env=False`(내부 호출이 `HTTP(S)_PROXY`를 타지 않게. 이 세션 환경처럼 프록시 변수가 있는 곳에서 `superset:8088`이 프록시로 새는 사고 방지), `follow_redirects=False`, `http2` 끔, `Limits(max_connections=4)`.
- 타임아웃: 서비스 계정 `connect=2s, read=15s, write=5s, pool=5s`(새로고침이 느릴 수 있음), 발급 계정 `connect=2s, read=5s`. 자동 재시도는 **하지 않는다**. 예외: 401→갱신/재로그인 1회, 400 CSRF→토큰 재취득 1회, 멱등 `GET`의 연결 끊김(`RemoteProtocolError`) 1회.
- TLS: 내부 주소가 `http://`이라 해당 없음. 코드 상수가 `https://`로 바뀌면 기본 검증을 유지하고 CSRF `Referer` 검사(HTTPS에서만 작동, X-25 한계 `03c:312`)를 다시 시험한다.
- 로깅: `httpx`·`httpcore` 로거를 `LOG_LEVEL`과 무관하게 `WARNING` 이상으로 고정(요청 URL이 INFO로 찍히고, 데이터셋 조회 URL에 사용자 입력 이름이 들어갈 수 있다). 응답 본문·`Authorization`·`Set-Cookie`·토큰은 어떤 로그에도 쓰지 않는다. 예외는 클래스 이름과 사유 코드만 기록(`core/ports.py:90`의 방식).

### 3-3. 데이터베이스 번호 알아내기 (D의 근거)
- 서비스 계정에는 `Database` 읽기가 없다. `bi_readonly` 연결은 `superset-init`의 `register_database.py`가 이름 `BI-Wizard (read-only)`로 만든다(`superset/register_database.py:44`, `bi_roles.py:13`). 번호는 어디에도 기록되지 않는다.
- **채택안:** 번호를 환경변수로 받지 않고 코드로 조회한다.
  1. `GET {root}/api/v1/dataset/related/database` → `result[].text == DATABASE_NAME`인 항목의 `value`(**추정**: 데이터셋 API의 `database` 관련 목록이 `schema_access`를 가진 DB를 보여 준다. 응답 모양 `{"count","result":[{"text","value","extra"}]}`도 추정). 프로브 P-1.
  2. 실패하면 상수 `1`을 쓰되 등록 직후 `GET /dataset/{id}`의 `database.database_name`을 `DATABASE_NAME`과 대조. 다르면 그 데이터셋은 `failed`(사유 `DB_MISMATCH`), 번호는 캐시하지 않는다. 서비스 계정은 `schema_access` 없는 DB에는 데이터셋을 만들 수 없으므로(`03c:224` 새 schema 권한 관련 기록) 틀린 번호로 엉뚱한 DB에 등록될 위험은 낮다(**추정**).
  3. 둘 다 실패하면 **멈추고 D(권한 확대)를 요청**한다.
- 번호는 프로세스 메모리에 캐시하고 422/404가 나면 한 번 다시 조회한다.

### 3-4. 데이터셋 하나의 동기화 절차 (멱등, 데이터셋 단위 잠금)
입력은 `dataset_id` 하나다. DB 읽기는 짧은 세션으로 끝내고 **HTTP 호출 동안 DB 트랜잭션을 열어 두지 않는다**(풀 5개 `db.py:58`).

| 순서 | 동작 | 실패 시 |
| --- | --- | --- |
| 0 | `dataset.service`의 읽기 함수로 팀 이름·데이터셋 이름·열(`id`, `display_name`, `kind`)을 읽는다(`list_active_dataset_ids`·`read_definition`이 이미 있음 `dataset/service.py:196,250`; **신규 필요**: 팀 이름까지 한 번에 주는 읽기 함수 `read_sync_source`). 이름 = `[팀] 데이터셋`, SQL = `virtual_sql(id)` | 데이터셋이 없으면 종료(행 삭제 없음) |
| 1 | 서비스 계정 세션 준비(§3-2), DB 번호 확보(§3-3) | `UNAVAILABLE`/`AUTH_FAILED` |
| 2 | **찾기**: ① 포털이 보관한 `superset_dataset_id`가 있으면 `GET /dataset/{id}`(404면 ②) ② `GET /dataset/?q=(filters:!((col:sql,opr:eq,value:'<SQL>'),(col:schema,opr:eq,value:bi_data)),columns:!(id,table_name,sql),page_size:5)`. SQL에는 숫자뿐이라 Rison 이스케이프가 필요 없다(**프로브 P-2**). ③ 둘 다 없으면 이름 조회로 대체(Rison 문자열은 `!`→`!!`, `'`→`!'`로 이스케이프하는 작은 함수 + URL 인코딩, 시험 필수) | |
| 3 | 없으면 `POST /dataset/ {"database":N,"schema":"bi_data","table_name":이름,"sql":SQL}` → 201. **즉시** `superset_dataset_id`를 표에 기록(상태는 `pending` 유지, 크래시 대비). 422(중복 이름)이면 2단계 ③으로 돌아가 같은 SQL이면 채택, 다른 SQL이면 `NAME_CONFLICT` | 아래 사유 코드 |
| 4 | `PUT /dataset/{id}/refresh`(뷰 열 변화 반영) | 422 원인 불명 → 뷰가 없을 가능성(`X-23`): 사유 `VIEW_MISSING` |
| 5 | `GET /dataset/{id}`로 열 목록(id, column_name) 읽기(POST 응답 모양에 기대지 않는다: A-27 기록은 `data.columns`로 적혀 있어 6.1.0 응답 키가 `result`일 수 있음, **추정**) | |
| 6 | **전체 열 `PUT /dataset/{id} {"table_name": 이름, "columns":[{id, column_name, verbose_name}, …]}`**. `verbose_name`: `c_<번호>` → 해당 `display_name`, `team` → `팀`, `row_id` → `행 번호`(06 §7 [제안]), 그 밖의 열 → 기존 값 유지. **일부 열만 보내는 호출은 코드에 존재하지 않는다**(함수가 항상 5단계 결과 전체를 입력으로 받는다. P4 합격 기준 `08:94`). 422 "columns do not exist"는 5단계부터 1회 재시도 | |
| 7 | 성공: `superset_datasets` 업서트(`superset_dataset_id`, `display_name`=이름, `sync_status='registered'`, `synced_at=now()`, `last_error=NULL`) | |

- **데이터셋 단위 잠금**: 프로세스 안 `dict[int, Lock]`. 단일 작업 스레드가 한 번에 하나만 처리하므로 사실상 직렬이고, 잠금은 E2(다시 시도)와 점검이 같은 데이터셋을 겹쳐 돌리지 않게 하는 안전망이다.
- **세대 번호(coalescing)**: `request_dataset_sync`가 불릴 때마다 그 데이터셋의 요청 세대를 +1(메모리). 작업 시작 때 세대를 기억하고 7단계에서 세대가 바뀌어 있으면 `registered`로 쓰지 않고 `pending`으로 두고 다시 큐에 넣는다(정의가 또 바뀐 것).
- **사유 코드**(`last_error`는 `코드: 한국어 요약` 200자 이내, SQL·본문·비밀·URL 금지): `UNAVAILABLE_CONNECT`, `UNAVAILABLE_TIMEOUT`, `UNAVAILABLE_5XX`, `AUTH_FAILED`(401/403 로그인·권한), `NOT_OWNER`(소유자 아님 403), `NAME_CONFLICT`(관리자가 같은 이름을 먼저 만든 경우), `VIEW_MISSING`, `DB_MISMATCH`, `REJECTED_<HTTP상태>`, `INTERNAL`. `str(예외)`는 쓰지 않는다.

### 3-5. 팀 이름 변경·이름 변경
- 팀 이름 변경(05 A4): `request_team_sync(team_id)` → 그 팀의 활성 데이터셋 번호들을 `dataset.service`로 읽어(팀 이름은 auth 읽기 service, 04 §3) 각각 큐에 넣는다. 처리는 §3-4와 같다(`table_name`만 달라지고 6단계 `PUT`이 이름까지 보낸다. 권한 항목 이름이 제자리에서 바뀌고 차트·권한은 유지됨 `03c:220`).
- 데이터셋 이름 변경(B4)도 같은 경로(`dataset/router.py`가 이미 `run_dataset_sync_request`를 부른다 `dataset/router.py:96` 등).

### 3-6. 상태 기계와 백그라운드 실행
```
(행 없음) ─ 요청 ─▶ pending ─ 성공 ─▶ registered ─ 정의 변경 요청 ─▶ pending
                       │ 실패                                          
                       └──────▶ failed ─ 재시도(시작 점검/E2) ─▶ pending
```
- `request_dataset_sync`/`request_team_sync`는 **BackgroundTasks 스레드에서** 불리므로(`dataset/router.py:96`, `access/router.py:103`) 거기서 하는 일은 ① 짧은 DB 업서트로 `pending`(행이 없으면 새 행: `display_name`은 이름 규칙으로 계산, `superset_dataset_id=NULL`) ② 큐에 번호 넣기, 이 둘뿐이다. **Superset 호출을 BackgroundTasks 스레드에서 하지 않는다.** 이유: 같은 anyio 스레드풀(기본 40)을 모든 `def` 엔드포인트가 쓰므로, Superset이 멈췄을 때 호출이 줄줄이 스레드를 붙잡으면 다른 API가 굶는다(P4 위반).
- **작업 스레드 1개**(`daemon=True`, lifespan에서 시작·종료 때 `stop()` 후 join 5초). 큐는 `set` + `Condition`으로 같은 번호 중복을 합친다(coalescing). Superset은 gunicorn 워커 1개라 호출을 직렬로 보내는 것이 맞다.
- **서킷 브레이커**: 연결 실패·시간 초과가 연속 3회면 30초 동안 호출을 건너뛰고 대기 중인 항목을 `failed(UNAVAILABLE_CONNECT)`로 기록(회복 후 시작 점검/재시도가 되돌린다). 데이터셋 하나가 최악 `2+15+…`초씩 기다리는 일을 막는다.
- **시작 점검**(lifespan 안에서 `asyncio.create_task`가 아니라 작업 스레드가 수행, 시작을 막지 않음): ① `/health`를 10초 간격으로 최대 10분 폴링(E ②) ② 대상 = 등록 행이 없는 활성 데이터셋 + `pending` + `failed` + (E ①) `registered`. 번호 순으로 큐에 넣는다.
- 관리자 "다시 시도"는 E2.
- **P4 시험 가능성**: `docker compose stop superset` 상태에서 데이터셋 생성 → E1 `pending`→`failed`(수 초~30초 안), 입력·수식 저장 API 200 유지, `compose start superset` 후 backend 재시작 또는 E2 → `registered`, Superset 데이터셋 수 1개(중복 없음).

---

## 4. 입장권 발급 (E6)

### 4-1. 흐름
| 순서 | 동작 |
| --- | --- |
| 1 | 인증(`current_user`) → 사용자별 속도 제한 검사·기록(§4-3) → 본문이 비어 있는지 확인(비어 있지 않으면 422) |
| 2 | 포털 `superset_dashboards`에서 `id`로 활성 행 조회(없음·비활성 → 404 `NOT_FOUND`) |
| 3 | uuid를 `str(uuid.UUID(x))` 소문자 36자 정규형으로(훅 형식 검사 `superset_config.py:103`) |
| 4 | (H1이면) 허용 목록 파일이 최신인지 확인 |
| 5 | 발급 계정 세션(§3-2의 같은 클래스, **서비스 계정과 별도 인스턴스·쿠키 항아리**)으로 `POST {root}/api/v1/security/guest_token/` 본문 `{"user":{"username":"<users.id>"},"resources":[{"type":"dashboard","id":"<uuid>"}],"rls":[]}`. `user`는 항상 보내고(생략하면 500 `03c:317`) `rls`는 서버 상수 `[]` |
| 6 | 응답 `token`을 그대로 돌려준다 `{token, expires_in:300}`. 헤더 `Cache-Control: no-store`, `Pragma: no-cache` |

- `first_name`/`last_name`은 보내지 않는다(개인정보 최소). username만으로 200이 나는지는 프로브 P-3(03c에는 "누락 400/500"만 있고 username만의 성공 사례는 EW-4 시험의 "정상 200"에 포함됨, 필드 구성 **확인하지 못함**).
- 발급 응답 동시성: 발급 계정 세션에 잠금을 걸어 직렬화(쿠키·CSRF 갱신 경쟁 방지). 약 26ms라 사용자별 30회/분 한도에서 대기가 문제되지 않는다.
- `expires_in`은 상수 300(`GUEST_TOKEN_EXP_SECONDS` 가드와 같은 값, `bi_roles.py:29`). **backend가 JWT를 해석하지 않는다**(서명 라이브러리 흔적 금지 정신 AP-1).
- 토큰은 **어떤 로그에도, 예외 메시지에도, 오류 응답에도, 캐시(메모리 포함)에도 남기지 않는다.** 함수 지역 변수로만 다루고 반환 직후 참조를 버린다.
- 오류 매핑: 연결·시간 초과·5xx → 503 `SUPERSET_UNAVAILABLE`, 로그인 실패·400(훅 거부, 없는 uuid)·403·그 밖 4xx → 502 `SUPERSET_REJECTED`. 문구에 Superset 내부 용어를 쓰지 않는다. 429는 속도 제한만.

### 4-2. 로그인 토큰 캐시
- 발급 계정·서비스 계정 각각 접근 토큰 12분 TTL, 401이면 갱신→재로그인(§3-2). **메모리만**, 프로세스 재시작 시 새로 로그인. 비밀번호는 `SecretStr`을 로그인 호출 직전에만 `get_secret_value()`(`config.py:110,112`).
- 비밀번호가 바뀌면(`superset-init`이 매 기동 되돌림 `08:22`) 캐시된 토큰은 유효 시간 동안 계속 쓰이고 만료 뒤 재로그인에서 실패하면 `AUTH_FAILED`로 드러난다.

### 4-3. 사용자별 429 (C)
- **저장소:** 프로세스 메모리 `dict[user_id, deque[monotonic_ts]]` + 잠금, worker 1개 전제(`06:106`, `08:72`). 워커를 늘리면 재설계(08 §8에 이미 기재).
- **방식:** 슬라이딩 윈도 60초에 **30회**(제안). 검사와 기록은 같은 잠금 안에서(검사 통과 시 즉시 기록, 거절된 요청은 기록하지 않아 계속 두드려도 영원히 막히지 않음). `Retry-After` = 가장 오래된 기록이 윈도를 벗어나기까지 초(올림, 최소 1). 응답 `429 GUEST_TOKEN_RATE_LIMITED`, `details.retry_after`, 헤더 `Retry-After`(`preview_busy`와 같은 모양 `core/errors.py:314-321`).
- **근거:** SDK 정상 사용은 대시보드를 연 순간 1회 + 보는 동안 295초마다 1회(`03c:323`, `gate-status.md:74`의 400초 실측: 0초·295초). 탭 5개를 열어도 분당 1회 미만. 발급이 실패하면 SDK가 10초마다 재시도하므로(`08:71`) 대시보드 하나당 분당 6회, 3개가 동시에 실패해도 18회라 30회 아래다. 5분당 1회 같은 값은 다중 탭·재시도에서 정상 사용자를 막는다. 30회/분은 Superset(워커 1개, 발급 약 26ms)에 부담이 되지 않는다.
- **시험(주입):** 윈도·한도·시계를 생성자 인자로 받아 단위 시험이 시간을 건너뛴다. 한 사용자의 429가 다른 사용자에게 영향이 없음, 거절된 요청은 기록되지 않음, 정확히 한도에서 통과 / 한도+1에서 429, 윈도 경과 뒤 복구, 동시 요청(스레드) 한도 초과 불가. 정리: 빈 deque 키 삭제.
- 순서: 제한 검사는 **404 판정보다 앞**(존재하지 않는 id를 두드리는 정찰도 제한). 비활성 사용자는 `current_user`가 이미 403.

---

## 5. 훅의 uuid 등록 대조 (FU-1 이월 3번)

### 5-1. 문제
- 현재 훅(`superset_config.py:78-113`)은 `rls==[]`, 리소스 정확히 1개, 유형 `dashboard`, id가 정규 uuid 형식, `user.username` 존재만 본다. 확장 지점 `_EXTRA_GUEST_TOKEN_CHECKS`는 비어 있다(`:59-62`).
- 훅은 Superset 웹 프로세스 안에서 돈다. 그 프로세스가 가진 비밀은 `SUPERSET_DB_PASSWORD`(메타 DB `superset_meta`) 등이고(`compose.yml:215-225`) `POSTGRES_READONLY_PASSWORD`는 `superset` 서비스에 전달되지 않는다(`superset-init`에만, `:195`). `bi_readonly`는 정적 표 권한이 없다.

### 5-2. 이 대조가 실제로 막는 것 (솔직한 평가)
backend는 이미 활성 `superset_dashboards`의 uuid만 보낸다. 발급 계정 비밀번호는 backend 컨테이너와 `superset-init`에만 있다. 따라서 훅의 라이브 대조가 추가로 막는 것은 **발급 계정 비밀이 유출된 공격자**가 "포털 미등록·비활성 상태이지만 Superset에서는 임베드가 켜져 있는" 대시보드의 입장권을 만드는 경우뿐이다. 그 공격자는 등록·활성 대시보드의 입장권은 어차피 만들 수 있다(불변식: 등록된 데이터는 모두 공개). 이익이 작으므로 비용(아래)이 큰 안은 고르지 않는다.

### 5-3. 선택지 비교
| 안 | 동작 | 새 환경변수 | GRANT/권한 | 기준 외 설정·계약 밖 | 보안 영향 | 위험·비용 | 판정 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **H0** 라이브 대조 없음 | backend 발급 전 검사 + Superset 기본 임베드 존재 검사 + 훅 형식 검사로 종결 | 0 | 0 | 0 | 5-2의 잔여 위험 수용 | 이월 항목을 사용자가 "수용"으로 종결해야 함(승인된 08 §4 문구 변경) | 승인 불필요 설계의 유일한 길. 사용자 결정 필요 |
| **H1** 공유 허용 목록 파일 | backend가 활성 uuid 목록을 `/registry/guest_dashboards.json`에 원자적 쓰기(임시 파일 + rename), 훅이 mtime 캐시로 읽고 **목록에 없으면 거부** | 0 | 0 | **compose 이름 있는 볼륨 1개**(backend rw, superset ro), backend 이미지에 `/registry`(app:app 10001) 생성, 훅 확장 | Superset 쪽은 읽기 전용 마운트. 파일이 변조돼도 훅은 **AND 조건**이라 Superset 기본 검사를 넘어 허용을 넓힐 수 없고 좁히기만 한다. 파일이 없거나 깨졌으면 거부(fail-closed) | 장애 시 발급 전부 거부(파일 쓰기 실패·볼륨 권한). 완화: 쓰기 실패 시 dirty 표시 후 재시도, E6가 발급 전 dirty면 재쓰기, 시작 때 항상 다시 씀. 볼륨 권한은 Docker가 이미지 디렉터리 소유권을 새 볼륨에 복사하는 동작에 의존(**추정**, QA가 확인) | **권장**(대조를 구현한다면) |
| **H2** `bi_readonly`에 열 단위 SELECT | `GRANT SELECT (embedded_uuid, is_active) ON superset_dashboards TO bi_readonly`, 훅이 Superset의 읽기 전용 연결로 조회 | `superset` 서비스에 `POSTGRES_READONLY_PASSWORD` 전달(새 변수는 아님, 새 Secret 전달) 또는 Superset 내부 `Database` 모델로 복호화(내부 API 의존) | **권한 확대**(`bi_readonly`) | 마이그레이션 `0006` GRANT 추가는 06 §2의 "bi_readonly에 정적 표 없음" 원칙 위반 | `bi_readonly`는 모든 Superset 질의가 쓰는 계정이라 X-15의 "public 정적 표를 못 읽는" 이중 방어(`03c:202`, `06:94`)가 약해진다 | 높음 | 비추천 |
| **H3** 훅이 backend 내부 HTTP 조회 | 훅이 `http://backend:8000/…` 호출 | 인증용 비밀(새 환경변수) 또는 무인증 | 0 | `/api` 계약(05 §1) 밖 경로 또는 무인증 내부 경로. nginx가 `/api/` 전체를 backend로 프록시하므로(`default.conf.template:63`) 무인증 경로는 브라우저에도 열림 | 무인증이면 uuid 목록 노출(E3가 이미 인증된 사용자에게 공개하는 값이지만 비로그인에 공개되는 점이 다름) | Superset 요청 처리 중 backend 동기 호출(순환 대기 위험), 장애 결합 | 비추천 |
| H4 backend가 Superset REST로 목록 푸시 | 서비스 계정에 추가 권한 필요 | 0 | **권한 확대**(대시보드/임베드 쓰기) | 03b Y5 위반(`can_set_embedded` 금지 취지) | - | - | 기각 |

- **새 승인이 필요 없는 안:** H0뿐이다(그리고 H0은 이월 항목 종결에 대한 사용자 결정이 필요하다).
- **H1 상세(B 승인 시)**
  - 파일 형식: `{"version":1,"updated_at":"<ISO>","uuids":["<정규형>",…]}`. 활성(`is_active`) 행만.
  - backend: 시작 직후(시작 점검 앞)와 E4·E5 커밋 뒤 동기로 쓴다. 쓰기 실패는 요청을 실패시키지 않고(커밋은 이미 끝남) 로그 + dirty 플래그 + 작업 스레드가 30초마다 재시도, E6는 발급 전에 dirty이면 재쓰기를 시도.
  - 훅: `os.stat` mtime이 바뀐 때만 JSON을 다시 읽고, 파일 없음·깨짐·`version` 불일치·uuid 목록이 아님이면 **거부**하며 사유 코드만 로그(`_reject`, `superset_config.py:72-75`). `_EXTRA_GUEST_TOKEN_CHECKS`에 `lambda body: body["resources"][0]["id"].lower() in allowed`를 추가(앞선 형식 검사가 정규형을 보장).
  - 시험: 훅 함수는 파일 경로를 인자로 받는 순수 함수로 두고(전역 상수로 `/registry/…`) 임시 파일로 단위 시험(등록 있음/없음/비활성/파일 없음/깨짐/대소문자), 기능 시험은 QA(§12 1e-d): 등록된 uuid 발급 200, 포털 미등록·비활성 uuid를 발급 계정 REST로 직접 요청하면 400, E5로 비활성화한 직후 발급 거부.
  - `ci-validate-env.sh` 보강: superset 볼륨 마운트가 `:ro`인지, backend 외 서비스가 `/registry`를 rw로 쓰지 않는지 정적 확인(적용 후 보고 항목 후보).
  - `docs/deploy-coordination.md`에 새 행: "이름 있는 볼륨 `registry`는 backend·superset이 같은 compose 프로젝트에 있어야 함, 운영 Superset을 분리 배치하면 재설계".

### 5-4. 권장
1순위 **H1**(B 승인), 2순위 **H0**. 이월 3번의 "정규 형식"(하이픈 36자) 요건은 어느 안에서도 backend 코드가 `str(uuid.UUID(x))`로 맞춘다(§4-1 3행).

---

## 6. revision `0006` (`superset_datasets`, `superset_dashboards`)

**06 §2·§8과 그대로 일치 확인**(`06-data-model.md:28-29`). 파일: `backend/migrations/versions/20261012_0006_superset.py`, `revision="0006"`, `down_revision="0005"`(현재 head, `20261012_0005_formulas.py:33-34`).

| 표 | 열 | 제약 | `bi_app` GRANT |
| --- | --- | --- | --- |
| `superset_datasets` | `dataset_id int NN`; `superset_dataset_id int NULL`; `display_name text NN`; `sync_status text NN server_default 'pending'`; `synced_at timestamptz NULL`; `last_error text NULL` | PK(`dataset_id`) + FK→`datasets.id`; CHECK(`sync_status IN ('pending','registered','failed')`) | `SELECT, INSERT, UPDATE (superset_dataset_id, display_name, sync_status, synced_at, last_error)` (`dataset_id` 불변) |
| `superset_dashboards` | `id int identity PK`; `name text NN`; `embedded_uuid uuid NN`; `is_active bool NN server_default true`; `created_at timestamptz NN server_default now()` | UNIQUE(`embedded_uuid`) | `SELECT, INSERT, UPDATE (name, is_active)` (`id`·`embedded_uuid`·`created_at` 불변) |

- 제약 이름은 `NAMING_CONVENTION`(`db_metadata.py:43-49`)과 같게: `pk_superset_datasets`, `fk_superset_datasets_dataset_id_datasets`, `ck_superset_datasets_sync_status`, `pk_superset_dashboards`, `uq_superset_dashboards_embedded_uuid`. 모든 SQL은 보간 없는 고정 문자열(`op.execute("GRANT … ")`, 0005 방식 `0005:74-75`).
- `DELETE`/`TRUNCATE` 권한 없음(FU-1에 삭제 없음). `bi_readonly`에는 **아무것도 주지 않는다**(정적 표는 Superset에 공개하지 않음, `0005` 머리말 `:13`과 같음).
- `downgrade()`: `superset_dashboards`, `superset_datasets` 순으로 `op.drop_table`(권한 함께 사라짐). `backend/tests/test_migrations.py`의 `DROP_APPROVED`(`:27`)에 `"20261012_0006_superset.py"` 항목과 사유(06 §6 표 역순 삭제, D2 규칙 적용, 03b 21-3 승인)를 기록한다(새 승인 아님).
- `db_metadata.py`: 두 표 모델 추가(SQLite 시험용 `create_all` 호환: `uuid`는 `sa.Uuid()`, CHECK는 PG 전용 아님). `alembic check` 통과 확인.
- **같이 고칠 시험:** `test_migrations.py`의 head 단정 `["0005"]`→`["0006"]`(`:156`)과 revision 순서(`:162,172`), 0006 GRANT 검사 블록(0005 `:376,513` 패턴), `test_static_acl.py`의 표 사전·권한 집합·불변 열 목록(`:40,52,66,124-125` 패턴에 두 표 추가), `test_roundtrip_tools.py`의 0006 한 단계 시험(`:205` 패턴), 왕복(`python -m migrations.roundtrip`) 스냅샷에 두 표 포함.
- **정적 표 권한 매트릭스 재확인 항목(EW-1, X-15 기준, 실제 표):** (1) `bi_app`: 위 표의 허용 동작만 성공, `DELETE`·`TRUNCATE`·DDL·`alembic_version` 거부, 불변 열(`dataset_id`, `id`, `embedded_uuid`, `created_at`) `UPDATE` 거부 (2) `bi_readonly`: 두 표 `SELECT` 거부(`permission denied`), (3) `bi_owner` 소유, (4) `PUBLIC` 접근 없음, (5) upgrade→downgrade→upgrade 스냅샷 일치와 `bi_data` 보존, (6) `alembic check` 0, (7) `ON CONFLICT … DO UPDATE`(업서트)가 pg8000 + 열 단위 UPDATE 권한에서 동작하는지(06 §5 "pg8000 `ON CONFLICT` 확인" 미확인 항목과 같은 계열: `INSERT … ON CONFLICT DO UPDATE`는 SET 대상 열에 UPDATE 권한과 충돌 판정 열 SELECT가 필요 → `dataset_id`는 PK라 SELECT 가능).

---

## 7. API E1~E6 구현 범위

공통: 보호 라우터(`main.py:51-56`의 `PROTECTED_ROUTERS`에 `superset_router` 추가), 오류 형식·코드는 `core/errors.py`(`SUPERSET_*`·`GUEST_TOKEN_RATE_LIMITED`는 `ErrorCode`에 이미 있음 `:52-54`; 만들 팩토리: `superset_unavailable()`, `superset_rejected()`, `guest_token_rate_limited(retry_after)`). 권한은 `app.auth.permissions.require_admin`.

| ID | 메서드 경로 | 권한 | 요청 검증 | 응답 | 오류 |
| --- | --- | --- | --- | --- | --- |
| E1 | GET `/superset/datasets` | 읽기 | `limit`(≤200)·`offset`, **추가 선택** `dataset_ids`(쉼표 목록, ≤200개), `team_id`, `sync_status`(enum) | `Page{items[{dataset_id, superset_name, sync_status, synced_at, last_error}]}`. `datasets` LEFT JOIN `superset_datasets`(조인은 dataset 모듈 읽기 함수 경유), 행 없는 데이터셋은 `sync_status="pending"`, `superset_name`은 이름 규칙으로 계산, `synced_at=null`. `last_error`는 **관리자에게만**, 그 밖에는 `null` | 422(`sync_status` 값, `dataset_ids` 형식) |
| E2 | POST `/superset/sync` | 관리자 | `{dataset_ids?: int[]}`(생략 = `pending`·`failed`·행 없음 전부, ≤1000) | **202** `{accepted:[dataset_id]}`. 즉시 `pending` 표시 + 큐 투입. **동기 처리가 아니라 접수**(결과는 E1 폴링). Superset 불가여도 접수는 성공 | 404(없는 번호가 하나라도 있으면 전체 거부, 05 표), 422 |
| E3 | GET `/dashboards` | 읽기 | `include_inactive`(관리자만 true 허용, 비관리자가 true면 403), `limit`·`offset` | `Page{items[{id, name, embedded_uuid, is_active}]}`, 이름순(가나다, `core/sorting`) | 403 |
| E4 | POST `/dashboards` | 관리자 | `{name: 1~100자 공백뿐 금지, 제어문자 금지; embedded_uuid: 정규형 36자만(공백 제거·소문자화 뒤 `str(UUID(x))==x`)}` | 201 대시보드. (H1이면 허용 목록 파일 갱신) | 409 `ALREADY_EXISTS`(`field=embedded_uuid`), 422 `VALIDATION_ERROR`(`BAD_FORMAT`·`TOO_LONG`·`REQUIRED`) |
| E5 | PATCH `/dashboards/{id}` | 관리자 | `{name?, is_active?}` 둘 다 없으면 422, `embedded_uuid` 등 다른 키는 422 | 200 대시보드. 비활성화는 발급을 멈춘다(Superset 임베드는 관리자가 따로 끈다 `08:80`). (H1이면 파일 갱신) | 404 |
| E6 | POST `/dashboards/{id}/guest-token` | 읽기 | 본문 없음(있으면 422, 빈 본문만 허용) | 200 `{token, expires_in:300}` + `Cache-Control: no-store`, `Pragma: no-cache` | 404(없음·비활성), 429 `GUEST_TOKEN_RATE_LIMITED`, 502 `SUPERSET_REJECTED`, 503 `SUPERSET_UNAVAILABLE` |

- 한국어 문구(내부 용어 금지): `SUPERSET_UNAVAILABLE` "대시보드 서비스에 연결할 수 없습니다. 잠시 후 다시 시도하세요." / `SUPERSET_REJECTED` "대시보드 서비스가 요청을 받아들이지 않았습니다. 관리자에게 문의하세요." / `GUEST_TOKEN_RATE_LIMITED` "요청이 너무 많습니다. 잠시 후 다시 시도하세요."
- E3가 `embedded_uuid`를 모든 사용자에게 보여 주는 것은 승인됨(`05:88`). E6 요청은 포털 `id`만 받는다(클라이언트가 보낸 uuid·`rls`·Superset 번호는 받지 않음 `05:12`).
- 권한 매트릭스 시험(`test_permission_matrix.py`)에 E1~E6 × 역할(관리자, 정의 담당자, 입력자, 다른 팀 구성원, 비소속 읽기, 비활성)을 추가(05 §4).
- 관리자 화면 S8·S9: §8.

---

## 8. 프런트 설계

### 8-1. 의존성·설치 (사용자 승인 03b 21-3, `03b:420`)
- `npm install --save-exact @superset-ui/embedded-sdk@0.4.0` → `package.json` 고정 표기(`^`·`~` 없음, `frontend/package.json:16-22` 방식), `package-lock.json` 커밋.
- 설치 직후 기록(deploy-coordination 또는 1e 보고): `npm view @superset-ui/embedded-sdk@0.4.0 license dependencies peerDependencies engines`, `npm ls`로 전이 확인, 라이선스 Apache-2.0·`@superset-ui/switchboard` Apache-2.0·`jwt-decode` MIT 대조. 예상 밖 전이 의존성(특히 MPL/LGPL) 또는 peer 요구가 있으면 **그 자리에서 멈추고 보고**. (현재는 **확인하지 못함**.)
- 설치 뒤 SDK 소스 정적 확인(1e-c 첫 작업): `node_modules/@superset-ui/embedded-sdk`에서 `localStorage|sessionStorage|console\.|document\.cookie|window\.name` 검색(SDK 자체가 토큰을 저장·출력하는지), 언마운트 때 갱신 타이머(`setTimeout`)를 정리하는지, `fetchGuestToken` 실패 시 오류 처리 방식. 결과를 보고에 적는다. 타이머가 정리되지 않으면 8-3의 `disposed` 가드가 필수다.

### 8-2. 구성
| 파일(`frontend/src/features/dashboard/`) | 책임 |
| --- | --- |
| `api.ts` | E3·E4·E5·E6 호출. E6은 `apiRequest` 대신 전용 함수(`cache: "no-store"`, 성공 본문에서 `token`만 꺼내 문자열로 반환, 형식 검사 후 `badShape`). 응답 객체를 보관하지 않는다 |
| `DashboardsPage.tsx`(S7) | 왼쪽 목록(E3), 오른쪽 `DashboardEmbed`. 선택은 URL 쿼리 `?d=<포털 id>`(uuid·토큰 아님). 상단 "차트 만들기" 새 창 링크 + 안내문 |
| `DashboardEmbed.tsx` | `embedDashboard` 마운트·정리 |
| `AuthorGuide.tsx` | 08 §5 안내문(지원 차트 6가지, "시간 필터가 있어야 날짜 필터가 적용됩니다", 팀 필터는 `team` 열, "일부 화면에서는 내부 번호 이름이 보입니다", "지표 라벨은 만든 시점의 표시 이름으로 굳어…", 공개 안내) |
| `DashboardAdminPage.tsx`(S8) | 목록(`include_inactive=true`), 등록 폼(제목·uuid), 활성 토글. uuid는 앞뒤 공백 제거·소문자화해 보여 주고 형식 오류는 입력 칸 옆에 쉬운 말로. Superset에서 임베드를 켜고 uuid를 복사하는 절차 도움말 |
| `features/status/SupersetSyncSection.tsx`(S9) | `GET /superset/datasets?sync_status=pending|failed`를 표시(데이터셋·상태·`last_error`·시각), 개별 "다시 시도"와 "대기·실패 전부 다시 시도"(E2). 요약 건수. 대기 항목이 있으면 5초 폴링, 언마운트·없어지면 중단. `AdminStatusPage.tsx:21`의 연결 지점 위에 추가, 뷰 재생성 구역(`ViewsSection`) 옆 |
| `features/dataset/DatasetListPage.tsx`(S2) | `:118` 연결 지점: 표시된 페이지의 `dataset_id`들로 E1(`dataset_ids`) 1회 호출 → "동기 상태" 열(등록 대기 / 등록됨 / 등록 실패). 비관리자는 `last_error`를 못 본다. **기존 시험 `dataset.test.tsx:89`("1e 전이라 /superset/datasets를 부르지 않는다")를 새 동작으로 교체** |
| `routes.tsx` | `:37-38`의 `Placeholder`를 S7·S8로 교체 |
| `config.ts` | `supersetDomain()`(= `window.location.origin + supersetRoot`), `supersetLink(path)`를 추가(경로 조립을 이 파일 한 곳에서, `config.js` 형식은 변경 없음 `05:140`). `supersetRoot`가 빈 값이면 임베드·링크를 숨기고 안내 |

### 8-3. 임베딩 컴포넌트 규칙 (토큰 비저장)
- `embedDashboard({ id: dashboard.embedded_uuid, supersetDomain: supersetDomain(), mountPoint: ref.current, fetchGuestToken, dashboardUiConfig: { hideTitle: false }, … })`. 컨테이너는 높이를 명시한다(예: `min-height: 720px; height: calc(100vh - …)`)—SDK iframe이 100%로 채우므로 높이가 없으면 0이 된다(**추정**).
- `fetchGuestToken = async () => { if (disposed) throw new Error("종료됨"); const token = await requestGuestToken(dashboard.id); return token; }` — `disposed`는 `useEffect` 정리 함수가 true로 바꾸는 지역 변수. 언마운트 뒤 SDK 타이머가 계속 불러도 발급 요청을 보내지 않는다(8-1 확인 결과와 무관하게 방어).
- **토큰은 메모리 변수에만**: React state·ref·context·전역·URL·`history`·`localStorage`·`sessionStorage`·cookie·`console`·오류 메시지·`postMessage` 외 어디에도 두지 않는다. `fetchGuestToken`이 던지는 오류는 우리 `ApiError`(서버 오류 본문에는 토큰이 없다)나 고정 문구뿐이고 토큰 문자열이 포함된 객체를 던지지 않는다. 오류 코드만 화면 상태(`tokenProblem: "RATE"|"UNAVAILABLE"|"OTHER"|null`)에 둔다.
- 실패 안내: 연속 실패하면 iframe 위 배너로 "대시보드 접속 허가를 받지 못했습니다(<쉬운 문구>). 잠시 뒤 자동으로 다시 시도합니다"(SDK가 10초마다 재시도 `03c:323`). 429면 `retry_after` 표시. 만료 뒤 Superset 쪽 영문 "Data error"가 보일 수 있으므로 5분 이상 열어 둔 화면에서 갱신 실패 배너가 먼저 보이게 한다.
- 정리: `useEffect` 반환에서 `disposed=true`, 반환된 `unmount()` 호출. React 19 StrictMode 개발 이중 마운트에서도 이전 인스턴스가 정리되는지 시험.
- **정적 방어:** (1) `eslint.config.js`에 `src/features/dashboard/**`에 한해 `no-restricted-globals`(`localStorage`, `sessionStorage`)·`no-console` 추가(적용 후 보고 항목: 거부 강화), (2) vitest 정적 시험이 해당 폴더 소스에 `localStorage|sessionStorage|console\.|document\.cookie|history\.(push|replace)State`가 없음을 단언, (3) 동작 시험이 `Storage.prototype.setItem`·`console.*`·`history.*`를 spy하고 정상·실패(429, 503) 경로에서 토큰 문자열이 한 번도 나오지 않음을 단언.

### 8-4. 하위 경로·STRIP·iframe 영향
- iframe 주소 = `${origin}${supersetRoot}/embedded/<uuid>`. Superset 경로는 STRIP 값과 무관하게 접두 유지(`default.conf.template:50-60`, `.env.example:28`). 그래서 `APP_PROXY_STRIP_PREFIX`가 바꾸는 것은 브라우저→backend의 E6 경로뿐이고, backend→Superset 내부 호출은 nginx를 거치지 않아 STRIP과 무관하다.
- 같은 origin이면 `frame_options`/CSP 변경이 필요 없다(`03c:190,308-309`). 포털 nginx는 CSP를 두지 않는다. `allowed_domains`는 임베드를 켤 때 관리자가 포털 origin(`http://127.0.0.1:5173` 형식)으로 지정(`08:81`). 값이 있으면 `/embedded/<uuid>` HTML 요청의 `Referer`로 검사되므로 `referrerPolicy`를 `no-referrer`로 바꾸지 않는다(기본 유지). 다른 origin 배치(DC 9)가 되면 `frame_options`/CSP 변경이 필요하며 그때 별도 승인(`08:111`).
- 변경 필요한 compose·nginx 설정: **없음**(B의 H1 볼륨 제외).
- 5분 넘는 갱신: SDK가 만료 5초 전 `fetchGuestToken`을 다시 호출(`03c:323`). QA가 포털 S7에서 400초 이상 유지해 `guest-token` 요청이 0초·약 295초에 나가고 `chart/data` 401이 없음을 확인(EW-6은 테스트 페이지로 확인함 `gate-status.md:74`, 포털 화면 재시험이 1e 몫).
- "차트 만들기": `<a href={supersetLink("/")} target="_blank" rel="noopener noreferrer">`. 8번 인증 뒤 자동 로그인 연동 목표(`08:13`)는 이번 범위 밖.

### 8-5. 스크린샷(1920×1080, `fu1e-{화면}-{상태}.png`)
`fu1e-s7-list`, `fu1e-s7-embed-line|bar|table|bignumber|pie|mixed`(차트별 6장), `fu1e-s7-token-rate-limited`, `fu1e-s7-superset-down`, `fu1e-s8-register`, `fu1e-s8-uuid-format-error`, `fu1e-s9-sync-failed`, `fu1e-s9-sync-retry-done`, `fu1e-s2-sync-column`. 모의 화면으로 대신한 것은 `docs/screens/fu1/README`에 표시(1d 선례 `03b:512`).

---

## 9. 지원 차트 6종 시험과 숫자 형식 선택지

### 9-1. 시드 방법 (QA 도구, REST, 관리자 계정은 QA 임시 env의 더미 값)
도구는 `_workspace/qa/fu1e/seed_superset.py`(표준 라이브러리 `urllib`만, 새 의존성 없음, 저장소 커밋 여부는 보고 때 사용자에게 묻는다). 실험 스크립트(`docs/research/experiments/r3,r5`)의 로그인·CSRF 헬퍼를 참고한다.
1. **합성 데이터**: 포털 API로 팀 2개, 데이터셋 1개(기준 날짜 열 `기간`(월 단위), `매출` number, `비용` number, `구분` text/choice(4종 값), 계산 열 `이익=[매출]-[비용]`, `비용률=[비용]/[매출]`(소수 많음)), 36개월 × 팀 2개 행. 포털 등록 흐름으로 가상 데이터셋 `[팀] 이름`이 `registered`가 되는 것까지가 1e-a/QA의 확인.
2. **대시보드·차트 생성**(관리자 세션, CSRF 포함): `POST /api/v1/dashboard/` → 차트 6개 `POST /api/v1/chart/`(`slice_name`, `viz_type`, `datasource_id`=Superset 데이터셋 번호, `datasource_type:"table"`, `params`=JSON 문자열, `dashboards:[대시보드 번호]`) → `PUT /api/v1/dashboard/{id}`로 `position_json`과 `json_metadata`(`positions`·네이티브 필터 구성: 03c 부가 `:239`가 "position_json만 보내면 연결이 갱신되지 않고 `json_metadata.positions`가 연결을 갱신한다"고 기록).
3. **임베드 켜기**: `POST /api/v1/dashboard/{id}/embedded {"allowed_domains":["<포털 origin>"]}` → 응답의 uuid를 E4로 포털에 등록.
4. 차트별 `viz_type`(초안, **추정** — 구현 때 Explore에서 같은 유형을 하나씩 만들어 `GET /api/v1/chart/<id>`의 `params`와 대조해 확정):

| 지원 차트 | `viz_type` | 필요한 `params` 골격 |
| --- | --- | --- |
| 선 | `echarts_timeseries_line` | `x_axis:"기간 열 c_N"`, `time_grain_sqla:"P1M"`, `metrics:[SUM(매출 c_N) 단순 지표]`, `groupby:[]`, 시간 필터(`adhoc_filters` TEMPORAL_RANGE, "No filter"), `y_axis_format` |
| 막대 | `echarts_timeseries_bar` | 위와 같고 `groupby:[구분 열]` 또는 단일 지표, 누적 여부 |
| 표 | `table` | `query_mode:"aggregate"`, `groupby:[기간, 구분]`, `metrics`, 정렬·행 제한, `column_config` |
| 큰 숫자(추세 포함) | `big_number` | `x_axis`(기간), `time_grain_sqla`, `metric`, `show_trend_line:true`, `y_axis_format` |
| 원형 | `pie` | `groupby:[구분 열]`, `metric`, `number_format`, `label_type` |
| 혼합(막대+선) | `mixed_timeseries` | `x_axis`, 질의 A `metrics` + `seriesType:"bar"`, 질의 B `metrics_b` + `seriesTypeB:"line"`, `y_axis_format`/`y_axis_format_secondary` |

   네이티브 필터: 시간(`filter_time`, 대상 차트 전체)과 팀(`filter_select`, 대상 열 `team`). 시간 필터가 없으면 날짜 필터가 적용되지 않는다는 안내문(`08:83`)을 검증하는 대조 차트 1개를 따로 둔다.
5. **표시 확인**(포털 S7, Playwright 등 QA 기존 도구): 대시보드를 선택해 6개 차트가 모두 그려지고 각 `chart/data` 200, 4xx 0건(알려진 404인 로고·`service-worker.js`·404 일러스트 제외 `08:87`), 값이 관리자 화면 또는 DB 직접 합계와 일치, 시간 필터 적용·팀 필터 적용 시 값이 바뀜, 스크린샷. `bi_guest` 4권한(`bi_roles.py:54-59`)이 그대로인지 시작 로그(`역할 bi_guest: 권한 4개 적용`)로 확인.
6. **정지 규칙(08 P5)**: 차트가 `403`(`can_explore_json`, `DashboardPermalinkRestApi` 등)이나 권한 문구로 실패하면 **권한을 추가하지 말고 그 자리에서 보고하고 멈춘다.** `FORBIDDEN_PERMISSIONS`(`bi_roles.py:63-67`)에 있는 두 권한이 필요해지는 경우가 이에 해당.

### 9-2. 계산 열 숫자의 표시(03b 21-1 결정 2: 설정을 바꾸지 말고 선택지만 보고)
시험 전에 **현재 기본 동작을 관찰·기록**한다: `비용률` 같은 `numeric` 계산 열이 6가지 차트에서 몇 자리로 보이는가(Superset 기본은 지표/축에 SMART_NUMBER, 표는 원시 값에 가깝게 보일 것으로 **추정** — 실측으로 확정). 선택지(채택하지 않고 보고만):

| 위치 | 방법 | 범위 | 비고 |
| --- | --- | --- | --- |
| 차트 설정 | 선·막대·혼합 `y_axis_format`(혼합은 `y_axis_format_secondary`), 큰 숫자 `y_axis_format`, 원형 `number_format`, 표 열별 `column_config`의 숫자 형식(D3 형식 문자열, 예 `,.2f`, `,.6~f`로 끝자리 0 제거) | 작성자가 차트마다 지정 | 안내문(§8 작성자 안내)에 한 줄 추가할 수 있음 |
| 데이터셋 저장 지표 | Superset 지표의 `d3format`(열에는 해당 속성이 없을 것으로 **추정**) | 포털이 서비스 계정으로 `PUT /dataset/{id}`에 `metrics`를 보내야 함 | **미시험**: `metrics`를 보내면 기존 지표가 교체될 수 있어 `columns`와 같은 주의 필요(A-27은 `columns`만 시험) |
| 뷰 | 계산식을 `ROUND`로 감싸 값 자체를 줄임 | 데이터 자체가 변함 | 07 수식 의미를 바꾸므로 **비추천**(결정 2는 "저장값·뷰·API 값 그대로") |
| Superset 전역 | `superset_config.py`의 D3 로케일/기본 형식 설정 | 모든 차트 | 기준선과 다른 설정이라 승인 필요, 선택지로만 기록 |
| 후속 | 열 규칙 `decimals`(03b 21-1 결정 4로 후속 단위)를 Superset 열/지표 형식에 연결 | 포털 정의 기준 | 후속 단위 |

---

## 10. 메모리 실측 설계 (8GB 예산, `03a` 2-3: 한도 합계 상시 4.75GiB, 여유 약 2.75GiB `03a:50`)

- **대상:** 상시 서비스 `postgres, backend, frontend, superset`(`superset-init`은 종료 뒤 0, 시작 중 최대는 별도 기록: EW-6 최대 약 213MiB `gate-status.md:74`).
- **측정 방법:** (a) `docker stats --no-stream --format` 을 5초 간격 루프로 파일에 기록, (b) 컨테이너 cgroup v2의 `memory.current`·`memory.peak`·`memory.stat`(anon/file)을 `docker exec <c> cat /sys/fs/cgroup/memory.peak` 등으로 구간 끝에 읽는다(`docker stats`의 사용량은 캐시 제외 계산 방식이 달라 둘 다 기록; cgroup v2 가용 여부는 **확인하지 못함**, v1이면 `memory.max_usage_in_bytes`), (c) `docker inspect`의 `State.OOMKilled`·`RestartCount`·`HostConfig.Memory`, (d) 호스트 `free -m`. 시험 프로젝트·임시 env는 QA 규칙(`_workspace/qa/`, 전용 프로젝트명)을 따른다.
- **시나리오(각 구간 사이 60초 안정):**
  1. S0 유휴: 전체 기동 + `superset-init` 종료 후 120초.
  2. S1 로딩: 포털 S7에서 6차트 대시보드 1명 로딩(차트 6개 `chart/data`).
  3. S2 유지: 같은 화면 5분 이상 유지(입장권 갱신 포함), 시작·중간·끝 측정.
  4. S3 동시 사용자 N명: N = 3, 5, 10(브라우저 컨텍스트 또는 입장권 + `chart/data`를 같은 요청으로 재현하는 스크립트; Superset 워커 1개·스레드 다수라 질의가 겹치는 모습을 본다). 사용자별 429(30회/분)에 걸리지 않게 N명에 입장권을 각자 발급.
  5. S4 등록 폭주: 데이터셋 50개 생성 직후 백그라운드 동기화(§3) 동안 backend·superset.
- **판정 기준(제안):** ① OOMKilled 0, 재시작 0. ② 서비스별 `memory.peak` ≤ 한도의 80%(superset ≤ 1.6GiB, backend ≤ 0.8GiB, postgres ≤ 1.2GiB, frontend ≤ 205MiB). ③ 상시 4개 서비스 `memory.peak` 합 ≤ 8GiB의 60%(4.8GiB)이고, 한도 합(4.75GiB)과 별개로 호스트에서 OS·Docker·페이지 캐시용 여유 ≥ 2GiB. ④ S3 N=10에서 `chart/data` 5xx 0건. 기존 EW-6 결과(유휴 합계 약 333MiB, 렌더 중 약 424MiB `gate-status.md:74`)와 비교해 증가분을 보고하고, 80% 초과 서비스는 `mem_limit` 조정안을 **제안만** 한다(`compose.yml` 변경은 보고 후 적용 `03b:208`).
- **`mem_limit` 점검 항목:** 4개 상시 서비스 현재값 `1536m, 1g, 256m, 2g`(`compose.yml:28,102,149,214`) 대비 peak, `superset-init` 1g 대비 peak, `docker inspect` 값이 compose와 같은지, 새 작업 스레드·서킷 브레이커로 backend 메모리가 눈에 띄게 늘지 않는지(비교: S0 대 S4).
- 결과는 `docs/deploy-coordination.md` 5번에 추가 기록할 값으로 보고한다(문서 갱신은 메인).

---

## 11. STRIP true/false 반복과 비밀 노출 검사

### 11-1. STRIP 반복 계획 (`08 §6`)
`APP_PROXY_STRIP_PREFIX`를 `false`·`true`로 각각(재빌드 없이 컨테이너 재시작 `.env.example:28`) 아래를 반복하고 두 값의 결과를 표로 비교한다(E6 경로만 다르고 나머지는 같아야 한다).
1. 포털 `${APP_BASE_PATH}/dashboards` 딥링크·새로고침(STRIP true는 루트 SPA fallback `default.conf.template:81-87`).
2. 대시보드 선택 → iframe 렌더 → `chart/data` 200, 4xx 0건(§9-1 5).
3. E6: 브라우저→`${APP_BASE_PATH}/api/dashboards/{id}/guest-token`(true면 접두가 떨어져 `/api/...`로 backend 도착), 429·503 경로도 동일 응답.
4. guest 부정 시험 상태 코드 동일(X-25의 시험 세트 재사용 `03c:308`), `Public` 0개.
5. "차트 만들기" 링크가 `${SUPERSET_APP_ROOT}/`로 열림.
6. 시점: 1e-c 통합 후 1회 + 최종 1회.

### 11-2. 비밀 노출 검사 (03b 21-3 조건)
| 대상 | 방법 | 찾는 문자열 |
| --- | --- | --- |
| 빌드한 프런트 번들 | `docker create` + `docker cp`로 `/usr/share/nginx/html` 추출(또는 `npm run build`의 `dist/`) 후 `grep -rIF` | QA 임시 env의 **값**: `SUPERSET_SERVICE_PASSWORD`, `SUPERSET_GUEST_ISSUER_PASSWORD`, `SUPERSET_ADMIN_PASSWORD`, `SUPERSET_SECRET_KEY`, `GUEST_TOKEN_JWT_SECRET`, `SUPERSET_DB_PASSWORD`, `POSTGRES_*_PASSWORD` 5종. **이름**: 위 변수명 전부, 계정 이름 `bi_service`·`bi_guest_issuer`·`SUPERSET_GUEST_ISSUER_USER`. **형태**: `eyJ`(JWT 머리 base64; SDK 코드 안의 우연한 일치는 맥락을 보고 구분하되 모든 일치를 보고), `Bearer `, `X-GuestToken` 값, `guest_token` 문자열은 SDK/우리 코드의 정상 일치(경로 `/guest-token`)와 구분해 보고 |
| 소스(커밋 전) | `grep -rIn` `frontend/src` | 같은 목록. Vite는 `VITE_*`만 번들에 내보내므로 `VITE_` 접두 환경변수 사용 여부도 확인 |
| 브라우저(포털+iframe, 같은 origin이라 저장소를 공유) | 세션 끝에 `localStorage`·`sessionStorage`·`document.cookie`·컨텍스트 쿠키·IndexedDB 이름 덤프, 방문한 모든 URL(`page.url()`·`performance.getEntriesByType('resource')`), 콘솔 메시지 전부 | `eyJ`, 입장권 문자열(응답에서 캡처한 실제 토큰 값으로 `grep -F`), 비밀번호 값. **Superset의 iframe 앱 자체가 토큰을 저장하거나 URL에 싣는다면** 우리가 고칠 수 없으므로 있는 그대로 보고 |
| 서버 로그 | `docker compose logs` 전 서비스 grep | 토큰 값, `eyJ`, 비밀번호 값, `Set-Cookie`, `Authorization` |
| 프로세스·메타데이터 | `docker exec <c> ps -eo args`(backend, superset), `docker inspect`의 `Config.Cmd/Entrypoint/Args`(EW-3·4 범위와 같음; `Config.Env`는 compose가 환경변수로 값을 전달하는 설계상 원래 보이므로 기존 QA와 같은 기준으로 비교하고 `frontend`의 Env에 Superset 비밀이 **없음**을 별도 확인: `compose.yml:150-154`) | 비밀번호·토큰 값 |
| nginx 접근 로그 | `docker logs frontend` | URL 쿼리에 토큰/uuid 비밀 없음 |
| backend 응답 헤더 | E6 응답 | `Cache-Control: no-store` |

---

## 12. 구현 순서·담당·합격 기준

의존: **1e-0 → (1e-a ∥ 1e-c(목 서버) ∥ 1e-b) → 1e-c 통합 → 1e-d**. 승인 A·B·C·E가 오면 해당 부분이 열린다.

| 단위 | 담당 | 범위 | 합격 기준 | 병렬 |
| --- | --- | --- | --- | --- |
| **1e-0 프로브** | env-engineer(+QA 임시 env, 전용 compose 프로젝트) | §14의 P-1~P-6을 임시 Superset으로 확인하고 결과를 `_workspace/fu1e/probes.md`에 기록(코드 변경 없음) | P-1(DB 번호 조회) 또는 대체 ②가 정해짐. P-1·②가 모두 실패하면 **D 승인 요청 후 멈춤** | 선행(몇 시간). 1e-a의 3-3·3-4 최종화에 필요 |
| **1e-a backend** | backend-dev | `0006` + 모델 + 시험 갱신(§6), `httpx`(A 결정 뒤 requirements 커밋), `app/superset/*`(§3~§4, §7), `DatasetSyncPort` 구현·연결(`create_app`), 시작 점검 스레드, 속도 제한, E1~E6, 오류 팩토리, 권한 매트릭스 시험, `ci-validate-env.sh`(DB 이름 상수 대조), `skills/dashboard-link/SKILL.md` 초안 | 단위 시험: Superset 가짜(`httpx.MockTransport` 또는 로컬 가짜 서버)로 등록·이름 변경·전체 열 `PUT`(일부 열만 보내는 호출 없음 단언)·중복 방지(422→찾기)·소유 403·서킷 브레이커·세대 번호·시작 점검(Superset 늦게 뜸)·`user` 항상 전송·`rls` 항상 `[]`·`resources` 정규형 uuid·429(주입)·응답 헤더·로그에 토큰/비밀번호 0건(caplog)·`failed` 사유에 SQL/비밀 없음. 실제 PG(`REQUIRE_PG`) 마이그레이션 왕복·권한 매트릭스. 기존 시험 전부 통과, `ruff` 통과 | 1e-c와 병렬(계약은 05 §2-5) |
| **1e-b env-engineer** | env-engineer | B 승인 시: `compose.yml` 볼륨, `backend/Dockerfile` `/registry`, `superset_config.py` 훅 확장, `ci-validate-env.sh`·`test-ci-validate-env.sh` 보강, `deploy-coordination.md` 행 제안. B=H0이면 단위 없음(훅 변경 0). 승인과 무관하게: `docker compose` 기동 확인, 그리고 선택 F | 훅 거부 시험(미등록·비활성·파일 없음·깨짐 → 400, 등록 → 200), 기존 훅 거부 5가지 회귀, `ci-validate-env.sh` 통과, `superset-init` 멱등·`bi_guest` 4권한·`Public` 0개 회귀, 읽기 전용 마운트 확인(`touch` 실패) | 1e-a와 병렬. 훅 기능 시험은 1e-a의 파일 작성기 뒤 |
| **1e-c frontend** | frontend-dev | SDK 설치·lock(§8-1), `features/dashboard/*`, S2 열, S8, S9 구역, `config.ts` 추가, 라우트, ESLint/정적 시험, 제품 Skill 화면 부분, 스크린샷 모의 서버 | vitest: 목 서버로 E1·E3~E6 전부, 토큰 비저장 3종(§8-3), 429·503·404 화면, 비관리자 S8·S9 접근 차단, `disposed` 가드, StrictMode, `typecheck`·`lint`·`build` 통과, 번들 비밀 grep 0건. SDK 소스 정적 확인 보고 | 1e-a와 병렬(목 서버). 통합은 1e-a 뒤 |
| **1e-d QA·reviewer** | qa-engineer → reviewer | P1~P5, 차트 6종(§9), 훅 uuid 대조(B 승인 시), 사용자별 429(실서버), STRIP 반복(§11-1), 메모리(§10), 비밀 검사(§11-2), 스크린샷, 5분+ 갱신 400초, SDK-Superset 6.1.0 호환 기록, P4(Superset 정지·복구·중복 없음), 정적 표 권한 매트릭스 재확인(§6) | 08 §6 P1~P5 전부, §9-1 5·6, 메모리 판정 ①~④, 비밀 0건, reviewer 차단 0건(`bi-review` 7-2·7-4·7-5, 라이선스 1번에 A 결과 반영) | 마지막(직렬) |

완료 보고 항목(`feature-unit` 절차): 변경 파일, 테스트 결과, 갱신한 Skill(`dashboard-link` 신규, 연관: `dataset-definition`(동기 상태 열), `formula-column`(표시 이름·번호 이름), `permission-management`(팀 이름 변경→동기), `local-environment`, `admin-cleanup`(Superset 객체 정리 절차)), 미실행 항목. **1e를 마치면 main 반영 PR은 만들지 않고 보고만 한다**(`03b:517`).

---

## 13. 문서 변경 제안 (docs/decisions는 수정하지 않았다. 승인 후 메인이 반영)
| 대상 | 제안 | 사유 |
| --- | --- | --- |
| 08 §2-1 ① | 시작 점검 대상에 `registered` 포함 + Superset `/health` 준비 대기 | E ①② |
| 08 §4 | 훅 대조 방식(B 결정), 한도 값 30회/60초(C) | `08:68,72` |
| 05 §2-5 | E1 추가 쿼리·페이지 응답, E2는 202 접수(동기 아님) 명시, E3 페이지 응답, E6 `expires_in` 상수 300, E4 `name` 1~100자 | E ③ |
| 06 §2 | (선택) `superset_datasets.superset_dataset_id`에 UNIQUE(null 허용)로 같은 Superset 객체의 이중 등록을 DB가 막음 | 6.1.0에서 같은 번호가 두 행에 들어가는 오류 방지. 06 문구 변경이라 승인 대기, 기본은 추가하지 않음 |
| `deploy-coordination.md` | A 결과에 따라 23번 `certifi` 행을 "운영 런타임 포함(수정·재배포 없음)"으로; B=H1이면 볼륨 행 추가; 메모리 실측값 | 라이선스 원칙, 5번 |
| `.claude/skills/bi-review` | 7-2에 "훅 대조 파일은 superset에 읽기 전용 마운트" (H1일 때), 7-4/AP-2에 "가상 데이터셋 SQL 템플릿 단일·정규식 시험" 확인 항목 | 거부 강화, 적용 후 보고 가능 |
| `CLAUDE.md` 변경 이력 | 위 승인 반영 시 한 줄 | 하네스 규칙 |

---

## 14. 확인하지 못한 것과 1e-0 프로브 목록 (임시 Superset 6.1.0, 전용 compose 프로젝트, `.env` 변경 없음)
| 프로브 | 질문 | 판단에 쓰는 곳 |
| --- | --- | --- |
| P-1 | 서비스 계정(4권한)으로 `GET /api/v1/dataset/related/database`가 `BI-Wizard (read-only)`와 번호를 돌려주는가? 응답 모양? 새 설치에서 DB 번호가 1인가? | §3-3, D |
| P-2 | `GET /api/v1/dataset/?q=(filters:!((col:sql,opr:eq,value:'SELECT * FROM bi_data.dv_1')))` 가 가상 데이터셋을 찾는가(`sql` 검색 열 허용 여부)? | §3-4 2단계 |
| P-3 | `user`에 `username`만 보내는 `guest_token` 발급이 200인가(`first_name`/`last_name` 필요 여부)? 응답 키 `token` 확인 | §4-1 |
| P-4 | `POST /dataset/` 응답 본문 모양(`result.columns` 존재 여부)과 `PUT`의 `table_name`+`columns` 동시 전송 | §3-4 5·6단계 |
| P-5 | 이름 있는 새 볼륨이 이미지 디렉터리 소유권(10001)을 상속하는가(B=H1일 때) | §5 H1 |
| P-6 | `GET {root}/health`가 인증 없이 200이고 준비 전에는 연결 거부/5xx인가 | §3-6 시작 점검 |
| 설치 후 | SDK 0.4.0: 의존성·peer·언마운트 타이머·저장소/콘솔 사용·Superset 6.1.0 호환·`supersetDomain`에 경로 포함 시 `postMessage`/iframe 주소 동작 | §8-1 (1e 실측 항목 `03b:423`) |
| 구현 중 | `ON CONFLICT DO UPDATE`의 pg8000 동작(열 단위 UPDATE 권한), `chart` 6종 `params`의 정확한 필드, 숫자 표시 기본 동작, 5분+ 갱신 포털 화면, 같은 origin 저장소 공유 시 Superset iframe 앱의 저장 여부, cgroup v2 `memory.peak` 가용 | 해당 단위 보고 |

---

## 15. 이 점검에서 발견한 주의점 (요약)
1. `certifi`(MPL-2.0)가 `httpx` 승격과 함께 운영 이미지에 들어온다 — A.
2. 서비스 계정은 Superset DB 번호를 조회할 권한이 없다. 실험은 `1`을 하드코딩했다 — §3-3, D(조건부).
3. `BackgroundTasks`에서 Superset을 직접 호출하면 Superset 정지 시 스레드풀이 고갈되어 다른 API가 굶는다 — 단일 작업 스레드 + 큐로 해결(§3-6).
4. 빈 볼륨 새 설치에서 backend가 superset보다 먼저 떠서 첫 동기화가 전부 실패한다 — `/health` 대기(E ②).
5. 커밋 뒤 크래시로 `registered` 데이터셋의 열 변경이 Superset에 반영되지 않는 틈 — 시작 점검 범위 확대(E ①).
6. 훅의 uuid 대조는 Superset이 포털 DB를 읽을 수 없어 어떤 안이든 승인이 필요하고, 실효 이익은 작다 — B.
7. 테스트가 이미 기대하는 연결 지점: `AdminStatusPage.tsx:21`, `DatasetListPage.tsx:118`, `routes.tsx:37-38`, `dataset.test.tsx:89`, `main.py:135`.
