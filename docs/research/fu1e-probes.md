# FU-1 단위 1e-0 프로브·실측 결과

작성: env-engineer(Sonnet 5.5, `claude-sonnet-5-5`), 2026-10-13. 코드·설정·문서는 수정하지 않았다(`git status` 깨끗함). 이 파일만 만들었다.
환경: Superset 6.1.0(`superset/Dockerfile`로 만든 이미지), compose 프로젝트 `probe1e`(postgres, db-bootstrap, migrate, superset-init, superset, backend, frontend), 임시 env `_workspace/qa/probe1e/env`(더미 비밀값, 사용자 `.env` 무관), 계정은 `superset-init`이 만든 `bi_service`·`bi_guest_issuer`·관리자 `admin`. 비밀·토큰 값은 마스킹했다(`<JWT>`, `<token>`).
요청 기준 주소: `http://<superset>:8088/bi-wizard/superset` (이하 `{root}`). 모든 호출은 호스트에서 컨테이너 IP로 직접(프록시 미경유).

## 0. 결론 요약

| 항목 | 결과 |
| --- | --- |
| 프로브 P-1~P-6 | 모두 실행. **설계의 핵심 가정이 맞았다.** 차이는 응답 모양·CSRF·오류 코드 세부(아래 §7) |
| H0 실측 ① (DB 연결 하나뿐, `bi_author`는 추가 불가) | **참** |
| H0 실측 ② (관리자·서비스 계정 외에 임베드 설정 권한 보유 역할 없음) | **기능 기준 참 / 문자 그대로 읽으면 거짓 (판정 필요, §2-2)** |
| `certifi` | Superset 이미지에 이미 있음(2025.6.15, MPL-2.0). backend 이미지에는 독립 패키지로는 없고 pip 내부 묶음에만 있음(2024.08.30) |
| `httpx==0.28.1` 전이 의존성 | 신규 3개: `certifi` 2026.7.22(MPL-2.0, 승인된 예외 1건), `httpcore` 1.0.9(BSD-3), `httpx` 0.28.1(BSD-3). 나머지 4개는 운영 `requirements.txt`에 이미 있음. 라이선스 원칙 위반 없음 |
| SDK 0.4.0 | 라이선스 허용형, 전이 2개. 언마운트 때 타이머 정리됨(실행으로 확인). 저장소·쿠키·URL 사용 없음. **단 `unmount` 핸들을 받기 전에 정리하면 SDK 타이머가 영구히 남는 함정이 있다(§5-3)** |
| 메모리 기준선(유휴) | postgres 99.5, backend 68.4, superset 196.6, frontend 5.3 MiB (합계 약 370 MiB) |
| **구현 진행 판정** | **조건부 진행 가능.** 새 환경변수·새 의존성·권한 확대 필요 없음. 다만 H0 실측 ②의 문자 해석 1건은 메인이 사용자에게 확인해야 한다(§2-2). 설계 변경 필요 12건(§7), 이 중 구현을 막는 것은 없음 |

---

## 1. 프로브 P-1 ~ P-6

### 1-1. 요약표 (설계 §14 원문 순서)

| 프로브 | 질문(원문) | 결과 | 설계와 차이 |
| --- | --- | --- | --- |
| **P-1** | 서비스 계정(4권한)으로 `GET /api/v1/dataset/related/database`가 `BI-Wizard (read-only)`와 번호를 돌려주는가? 응답 모양? 새 설치에서 번호가 1인가? | **예, 번호 1.** 응답 `{"count":1,"result":[{"extra":{},"text":"BI-Wizard (read-only)","value":1}]}`. 접근 권한으로 걸러진 목록임을 DB를 하나 더 만들어 확인(§1-2) | 없음(추정이 맞음). **D(권한 확대) 불필요, 대체안 ②도 불필요** |
| **P-2** | `GET /dataset/?q=(filters:!((col:sql,opr:eq,value:'SELECT * FROM bi_data.dv_1')))`가 가상 데이터셋을 찾는가? | **예.** `sql eq`, `sql ct`, `schema eq`, `table_name eq` 모두 동작. 없으면 `count 0`. Rison 이스케이프(`!'`, `!!`)도 동작 | 없음 |
| **P-3** | `user`에 `username`만 보내는 발급이 200인가? 응답 키 `token`? | **예, 200, 키는 `token`.** 단 **세션 쿠키 + `X-CSRFToken`이 없으면 400(CSRF)** | 발급 호출도 서비스 계정과 같은 CSRF 처리가 필요(설계 §4-1 표에는 명시가 없었음). `user` 생략은 훅 때문에 **400**(03c의 500은 훅 설치 전 기록) |
| **P-4** | `POST /dataset/` 응답 본문 모양(`result.columns` 존재 여부)과 `PUT`의 `table_name`+`columns` 동시 전송 | `POST` 201 응답은 `{"data":{…,"columns":[…]},"id":N,"result":{…}}`. **열은 `data.columns`에 있고 `result`에는 없다.** `PUT` `table_name`+`columns` 동시 전송 200 | 설계의 "추정"(키가 `result`일 수 있음)은 **틀림**: `data`. 설계는 열을 `GET`으로 다시 읽으므로 영향 없음 |
| **P-5** | 이름 있는 새 볼륨이 이미지 디렉터리 소유권(10001)을 상속하는가? | **예.** `/registry`를 이미지에서 `10001:10001`로 만들면 새 이름 있는 볼륨도 `10001:10001 755`. Superset(uid 1000)이 `:ro`로 마운트하면 읽기 되고 쓰기는 `Read-only file system` | 없음. (B=H0이면 불필요한 정보) |
| **P-6** | `GET {root}/health`가 인증 없이 200이고 준비 전에는 연결 거부/5xx인가? | **200, 본문 `OK`(2바이트), 인증 없음.** 접두 없는 `/health`는 404. 기동 중에는 **연결 거부**(`000`), 5xx 없음. 컨테이너 재시작 후 7.4초에 200 | 없음. backend 컨테이너에서 `http://superset:8088{root}/health` 200 확인 |

### 1-2. P-1 상세 (정확한 요청·응답)

| 호출 | 계정 | 상태 | 본문(마스킹) |
| --- | --- | --- | --- |
| `POST {root}/api/v1/security/login` `{"username":"bi_service","password":"<SUPERSET_SERVICE_PASSWORD>","provider":"db","refresh":true}` | 서비스 | 200 | `{"access_token":"<token>","refresh_token":"<token>"}` |
| `GET {root}/api/v1/security/csrf_token/` (Bearer) | 서비스 | 200 | `{"result":"<csrf>"}` + `Set-Cookie: session=…` |
| `GET {root}/api/v1/dataset/related/database` (Bearer) | 서비스 | 200 | `{"count":1,"result":[{"extra":{},"text":"BI-Wizard (read-only)","value":1}]}` |
| 같은 호출 `?q=(page_size:100)` | 서비스 | 200 | 위와 같음 |
| `GET {root}/api/v1/database/` | 서비스 | **403** | `{"message":"Forbidden"}` (설계 가정대로) |
| `GET {root}/api/v1/database/1` | 서비스 | **403** | 같음 |
| `GET {root}/api/v1/database/?q=(columns:!(id,database_name,…))` | 관리자 | 200 | `ids:[1]`, `result:[{"allow_dml":false,"database_name":"BI-Wizard (read-only)","expose_in_sqllab":true,"id":1}]` |

**접근 필터 확인(임시):** 관리자가 두 번째 연결 `probe-second-db`(id 2)를 임시로 추가한 상태에서 같은 호출을 비교했다. 관리자: `count 2`(둘 다). **서비스 계정과 `bi_author` 시험 계정: `count 1`(번호 1만)**. 서비스 계정이 2번 DB에 `POST /dataset/`를 시도하면 422 `{"message":{"sql":["You need access to the following tables: …`all_database_access` or `all_datasource_access` permission"]}}`(등록 불가). 두 번째 연결은 관리자가 즉시 삭제했고 목록은 다시 1건이다.
→ 설계 §3-3의 채택안 ①은 **그대로 구현 가능**: `result[]`에서 `text == "BI-Wizard (read-only)"`인 항목의 `value`를 쓴다. 번호는 새 설치에서 1이지만 관리자가 연결을 지우고 다시 만들면 바뀌므로 코드에서 조회하는 편이 맞다.

### 1-3. P-2 상세

| 요청 `q=` (URL 인코딩 전) | 상태 | 결과 |
| --- | --- | --- |
| `(filters:!((col:sql,opr:eq,value:'SELECT * FROM bi_data.dv_1')),columns:!(id,table_name,sql,schema),page_size:5)` 등록 전 | 200 | `{"count":0,"ids":[],"result":[]}` |
| 같은 조건, 등록 후 | 200 | `{"count":1,"ids":[1],"result":[{"id":1,"schema":"bi_data","sql":"SELECT * FROM bi_data.dv_1","table_name":"[시험 A팀] 프로브1e"}]}` |
| `…sql eq` + `(col:schema,opr:eq,value:bi_data)` | 200 | 1건 |
| `sql eq 'SELECT * FROM bi_data.dv_2'` | 200 | `count 0` |
| `(col:table_name,opr:eq,value:'[시험 A팀] 프로브1e')` | 200 | 1건 |
| `(col:sql,opr:ct,value:'bi_data.dv_1')` | 200 | 1건 |
| `columns` 생략 | 200 | 기본 열 포함 1건 |
| 이름에 작은따옴표·느낌표가 있는 데이터셋(`… it's!ok`)을 `value:'… it!'s!!ok'`(`'`→`!'`, `!`→`!!`)로 조회 | 200 | **정확히 1건 일치** (이스케이프 규칙 맞음) |

→ 설계 §3-4 2단계 ②는 그대로 쓸 수 있다.

### 1-4. P-3 상세 (발급 계정 `bi_guest_issuer`, 임베드를 켠 시험 대시보드 uuid 사용)

| 요청 본문 | 상태 | 응답 |
| --- | --- | --- |
| CSRF 헤더·쿠키 없이 Bearer만 | **400** | `{"errors":[{"message":"400 Bad Request: The CSRF token is missing.","error_type":"GENERIC_BACKEND_ERROR",…}]}` |
| 쿠키 + `X-CSRFToken` + `{"user":{"username":"1"},"resources":[{"type":"dashboard","id":"<uuid>"}],"rls":[]}` | **200** | `{"token":"<JWT 363자>"}` (페이로드 키: `aud, exp, iat, resources, rls_rules, type, user`; `type=guest`, `exp-iat=300`, `user={"username":"1"}`) |
| 같은 세션으로 두 번째 호출(다른 username) | 200 | 같은 모양(세션·접근 토큰 재사용 가능) |
| `user` 생략 / `username` 빈 문자열 / `user:{}` | **400** | `{"message":["Guest token validation failed"]}` (훅 거부. 설계의 "생략 시 500"은 훅이 없을 때의 기록) |
| `rls` 생략 | 400 | `{"message":{"rls":["Missing data for required field."]}}` |
| `rls` 비어 있지 않음 / 리소스 2개 / 리소스 0개 | 400 | `{"message":["Guest token validation failed"]}` |
| 숫자 대시보드 id(임베드 켠 것·안 켠 것 모두) | 400 | 훅 거부(위와 같음) |
| 모르는 uuid | 400 | `{"message":"EmbeddedDashboard not found."}` |
| **대문자 uuid** | **200** | 훅이 통과시키고 토큰의 resource id는 대문자 그대로(→ backend는 소문자 정규형으로 보내야 한다. 설계 §4-1 3행 그대로) |
| `type:"chart"` | 400 | `{"message":{"resources":{"0":{"type":["Must be one of: dashboard."]}}}}` |
| `first_name`·`last_name` 추가 | 200 | 받아들이지만 필요 없다 |
| 서비스 계정(`bi_service`)으로 발급 | 403 | `{"message":"Forbidden"}` |
| 발급 계정으로 `GET /api/v1/dataset/`·`database/`·`dashboard/`·`chart/` | 403 ×4 | 다른 API 불가 |

**주의(설계 §3-2 보강):** CSRF 누락·불일치도 400, 훅·스키마 거부도 400이다. 본문으로 구분해야 한다 — CSRF는 `errors[].message`에 `CSRF token is missing/invalid`, 훅 거부는 `message: ["Guest token validation failed"]`. "400이면 CSRF 토큰 다시 받아 1회 재시도"는 본문에 `CSRF`가 있을 때만 해야 불필요한 재시도가 없다. 발급 지연: 세션 재사용 시 호출당 약 15~25ms(호스트→컨테이너 직접).

### 1-5. P-4 상세와 가상 데이터셋 흐름 (서비스 계정, 포털로 만든 데이터셋 1개: 열 `기준월`·`매출`·`비용`·`비용률`)

| 단계 | 요청 | 상태 | 응답 모양 |
| --- | --- | --- | --- |
| 1 | `POST /api/v1/dataset/` `{"database":1,"schema":"bi_data","table_name":"[시험 A팀] 프로브1e","sql":"SELECT * FROM bi_data.dv_1"}` + 쿠키 + `X-CSRFToken` | **201** | 최상위 키 `data`, `id`, `result`. `data`는 데이터셋 전체(`catalog:"bi_wizard"`, `columns[]`: `team`, `row_id`, `c_1`~`c_4` 각각 `id`, `column_name`, `verbose_name:null`, `type`, `is_dttm` 등). `result`는 `{always_filter_main_dttm, database, normalize_columns, schema, sql, table_name}`로 **열 없음** |
| 2 | 같은 이름 다시 `POST` | **422** | `{"message":{"table":["Dataset bi_wizard.bi_data.%5B%EC%8B%9C%ED%97%98%20A%ED%8C%80%5D%20%ED%94%84%EB%A1%9C%EB%B8%8C1e already exists"]}}` — **이름이 URL 인코딩되어 메시지에 들어간다**(로그·`last_error`에 이 메시지를 쓰지 말 것) |
| 3 | `GET /api/v1/dataset/{id}` | 200 | `{"id","result":{…}}`. `result.columns[]`(`id`, `column_name`, `verbose_name`, `type`, `type_generic`, …), `result.database={allow_multi_catalog,backend,database_name:"BI-Wizard (read-only)",id:1,uuid}` → **등록 직후 DB 이름 대조 가능**, `result.owners=[{id:2,first_name:"BI-Wizard",…}]`(서비스 계정 소유), `result.metrics=[{id:1,metric_name:"count"}]` |
| 4 | `PUT /api/v1/dataset/{id}` `{"table_name":"…","columns":[{"id","column_name","verbose_name"}×6]}` | **200** | `{"id":1,"result":{always_filter_main_dttm, columns:[{column_name,id,verbose_name}×6], table_name}}` → 이후 `GET`에서 표시 이름 `팀`, `행 번호`, `기준월`, `매출`, `비용`, `비용률` 확인 |
| 5 | `PUT /api/v1/dataset/{id}` `columns`에 없는 id 99999 | 422 | `{"message":{"columns":["One or more columns do not exist"]}}` (불변) |
| 6 | 포털에서 계산 열 `이익` 추가(뷰 재생성) 후 `PUT /api/v1/dataset/{id}/refresh`(본문 없음, CSRF 필요) | 200 | `{"message":"OK"}`. `GET`: 기존 열 이름 유지, 새 열 `c_5`는 `verbose_name:null`로 추가 |
| 7 | 전체 열 `PUT`으로 `c_5`에 `이익` | 200 | 열 7개, id 불변, 기존 이름 유지 |
| 8 | 이름 변경(`table_name`에 `'`·`!` 포함) | 200 | P-2 이스케이프 조회로 찾아짐. 되돌림 200 |
| 9 | `GET …/related_objects` | 200 | `{"charts":{"count":0,"result":[]},"dashboards":{"count":0,"result":[]}}` |
| 10 | `DELETE /api/v1/dataset/{id}`(정리) | 200 | `{"message":"OK"}` |

### 1-6. 서비스·발급 계정 로그인 토큰 재사용

| 시험 | 결과 |
| --- | --- |
| 접근 토큰은 로그인 한 번으로 여러 호출에 Bearer로 재사용 | 가능 |
| `POST /api/v1/security/refresh`, Bearer=**갱신 토큰**, 본문·CSRF 없음 | 200 `{"access_token":"<token>"}`. 새 접근 토큰으로 `GET` 200 |
| 접근 토큰 갱신 뒤 **이전 세션 쿠키 + 이전 CSRF 토큰** 그대로 `PUT` | 200 (CSRF는 접근 토큰과 무관, 쿠키 세션에 묶임) |
| 만료된 접근 토큰 | **401** `{"msg":"Token has expired"}` (같은 키로 서명한 과거 `exp` 토큰으로 시험) |
| 형식이 깨진 토큰 | **422** `{"msg":"Not enough segments"}` (401 아님) |
| 잘못된 비밀번호 로그인 | 401 `{"message":"Not authorized"}` |
| 25회 연속 로그인(같은 계정) | 25회 모두 200 (이 설정에서 로그인 빈도 제한 없음) |
| CSRF 헤더 없이 `POST /dataset/` | 400 `The CSRF token is missing.` |
| 잘못된 CSRF 값 | 400 `The CSRF token is invalid.` |
| 접근 토큰 유효 시간 | 15분(설계 §3-2/03c, 직접 재측정 안 함) |

### 1-7. P-6 상세 (시작 점검)

| 시험 | 결과 |
| --- | --- |
| `GET {root}/health` 헤더·본문 | `HTTP/1.1 200 OK`, `Server: gunicorn`, `Content-Type: text/html`, `Content-Length: 2`, 본문 `OK`. 인증·쿠키 필요 없음 |
| `GET /health`(접두 없음) | 404 |
| `GET {root}/healthcheck` | 200 |
| `compose stop superset` 후 | 연결 거부(컨테이너 IP 사라짐) |
| `compose start superset` 후 0.5초 간격 폴링 | 0초 `000`(연결 거부) → **7.4초에 200**. 5xx를 거치지 않음 |
| 새 설치 | superset 컨테이너는 `superset-init` 성공 뒤에야 생성된다(compose `depends_on`). 그 사이 backend에서 `superset` 이름이 풀리지 않거나 연결이 거부된다 → 연결 오류로 처리하면 된다(이름 풀이 실패 자체는 이번에 따로 시험하지 않음) |

---

## 2. H0 종결 조건 실측 2건

### 2-1. ① DB 연결이 `bi_readonly` 하나뿐이고 `bi_author`가 연결을 추가할 수 없는가 → **참**

| 근거 | 결과 |
| --- | --- |
| Superset 메타 DB `dbs` 표 | 행 1개: `id 1`, `BI-Wizard (read-only)`, `postgresql+psycopg2://bi_readonly:***@postgres:55432/bi_wizard`, `expose_in_sqllab t`, `allow_dml f`, `allow_file_upload f` |
| 관리자 `GET /api/v1/database/` | `count 1`(위 한 건) |
| 권한 표(`ab_permission_view_role`): `can_write Database` 보유 역할 | **`Admin`만.** `bi_author`는 `can_read Database`, `menu_access Databases`만(Gamma와 같음). `Alpha`는 `can_read`·`can_upload`·`all_database_access`(Alpha는 우리가 사용자에게 주지 않는 내장 역할) |
| 기능 시험: 임시 시험 계정(`bi_author` + `bi_author_schema`, 관리자가 만들고 시험 후 삭제)으로 | `POST /api/v1/database/` **403**, `POST …/test_connection/` **403**, `POST …/validate_parameters/` **403**, `PUT /database/99` **403**, `DELETE /database/99` **403**, `POST …/import/` **403**. `GET /database/` 200(1건만 보임) |

시험 계정 `probe_author_tmp`는 삭제했다(`ab_user`에 `admin`, `bi_service`, `bi_guest_issuer` 3개만 남음).

### 2-2. ② 관리자·서비스 계정 외에 임베드 설정 권한을 가진 역할이 없는가 → **기능 기준 참 / 권한 이름을 문자 그대로 읽으면 거짓 (메인·사용자 판정 필요)**

전체 역할 × 해당 권한(DB 질의 결과, `t`=보유):

| 역할 | `can_set_embedded` Dashboard | `can_delete_embedded` Dashboard | `can_get_embedded` Dashboard | `can_write` Dashboard | `can_read` EmbeddedDashboard | `can_write` Database |
| --- | --- | --- | --- | --- | --- | --- |
| Admin | **t** | t | t | t | t | t |
| Alpha | f | **t** | t | **t** | t | f |
| **bi_author** | f | **t** | t | **t** | t | f |
| **Gamma** | f | **t** | t | **t** | t | f |
| bi_service | f | f | f | **f** | f | f |
| bi_guest_issuer | f | f | f | f | f | f |
| bi_guest | f | f | f | f | f | f |
| bi_author_schema | f | f | f | f | f | f |
| sql_lab | f | f | f | f | f | f |
| Public | (권한 0개) | | | | | |

판정에 필요한 사실:
1. **`can_set_embedded Dashboard`를 가진 역할은 `Admin`뿐**이다. 서비스 계정 역할 `bi_service`는 임베드 관련 권한을 하나도 갖지 않는다.
2. 임베드 설정을 쓰는 코드는 6.1.0 소스에서 한 곳이다: `superset/dashboards/api.py`의 `set_embedded`(POST·PUT `/dashboard/{id}/embedded`)가 `EmbeddedDashboardDAO.upsert`를 호출한다. 이 메서드는 `can_set_embedded`를 요구한다. 해제 `delete_embedded`도 `@permission_name("set_embedded")`라서 `can_delete_embedded`가 아니라 **`can_set_embedded`** 를 요구한다. `can_delete_embedded`·`can_get_embedded` 항목은 존재하지만 어느 엔드포인트도 이 이름으로 검사하지 않는다(읽기 `get_embedded`는 `can_read`).
3. **기능 시험(`bi_author` 시험 계정, 임베드 안 한 대시보드 대상):** `POST …/dashboard/2/embedded` **403**, `PUT` **403**, `DELETE` **403**. 이후 관리자가 보니 해당 대시보드는 여전히 임베드 설정 없음(404). `POST /security/guest_token/`도 403.
4. 따라서 **`can_write Dashboard`(Alpha·Gamma·`bi_author` 보유)와 이름만 같은 `can_delete_embedded`는 임베드 설정·해제를 하지 못한다.** `can_write Dashboard`는 대시보드 생성·수정 권한이고 임베드와 별개다(작성자가 대시보드를 만드는 데 필요).

**문자 그대로의 거짓:** 작업 지시의 괄호 목록에 `can_write Dashboard`가 포함되어 있어, 그 항목만 기계적으로 읽으면 "`Admin`·`bi_service` 외에 Alpha·Gamma·`bi_author`가 보유"이므로 조건 ②는 **거짓**이 된다. 지시문의 "하나라도 거짓이면 멈춘다"를 따라 여기서 멈추고 보고한다. 내 판단은 "임베드 설정 권한"의 실제 의미(`can_set_embedded`)로는 참이며 기능 시험으로 뒷받침됐다는 것이다. H0을 종결해도 되는지는 메인이 사용자에게 이 표를 보여 주고 결정해야 한다. 사용자가 문자 그대로 거짓으로 보면 03b 23-1 B에 따라 H1로 바꾸지 말고 멈춰야 한다(내가 바꾸지 않았다).

부가 사실(결정에 참고): `bi_author`(Gamma 복사본)는 대시보드를 만들 수 있으므로, **임베드된 대시보드는 모두 관리자가 켠 것**이다(임베드 켜기는 관리자 수동, 08 §5 일치). 남는 위험은 08 §3-2 "공개 범위는 `bi_data` 전체"와 같다.

---

## 3. `certifi` 실측 (변경 없음)

| 대상 | 이미지 | `certifi` 독립 패키지 | 위치·버전 | 라이선스(메타데이터) |
| --- | --- | --- | --- | --- |
| Superset | `bi-wizard-superset:6.1.0`(= `apache/superset:6.1.0` + `psycopg2-binary`) | **있음** | `/app/.venv/lib/python3.10/site-packages/certifi`, **2025.6.15** | `License: MPL-2.0`, 분류자 `Mozilla Public License 2.0` (원본 `apache/superset:6.1.0`에도 같은 버전이 있음. 업스트림 공식 이미지 내부 구성요소) |
| backend 운영 | `bi-wizard-backend:local` | **없음** (`pip list`에 certifi 없음) | 독립 설치 없음. 대신 **pip 내부 묶음** `/usr/local/lib/python3.12/site-packages/pip/_vendor/certifi`(`cacert.pem` 포함), 버전 **2024.08.30**(`pip/_vendor/vendor.txt` `certifi==2024.8.30`) | pip 25.0.1 자체는 `MIT`. 묶음 certifi는 pip 배포본의 일부 |

즉 backend 운영 이미지에는 이미 MPL-2.0 데이터(`cacert.pem`)가 pip 묶음 형태로 들어 있고, `httpx` 승격으로 독립 패키지 `certifi` 2026.7.22가 추가된다.

---

## 4. `httpx` 전이 의존성 (설치 검증: `python:3.12.15-slim-bookworm` 컨테이너의 빈 venv에서 `pip install httpx==0.28.1`)

`backend/requirements-dev.txt`에 고정된 버전: `httpx==0.28.1`, `httpcore==1.0.9`, `certifi==2026.7.22`(그 밖에 `anyio==4.15.1`, `h11==0.16.0`, `idna==3.20`, `typing_extensions==4.16.0`은 운영 `requirements.txt`에도 같은 버전). `pip freeze` 결과는 dev 고정 목록과 정확히 일치한다.

| 패키지 | 버전 | 라이선스(SPDX, 메타데이터) | 필수/선택 | 운영 `requirements.txt` | 판정 |
| --- | --- | --- | --- | --- | --- |
| httpx | 0.28.1 | BSD-3-Clause | 직접 | **없음(신규)** | 허용형 |
| httpcore | 1.0.9 | BSD-3-Clause | 필수(httpx) | **없음(신규)** | 허용형 |
| certifi | 2026.7.22 | **MPL-2.0** | 필수(httpx, httpcore) | **없음(신규)** | **승인된 예외 1건**(03b 23-1 A, 이름으로만, 수정·재배포 금지) |
| anyio | 4.15.1 | MIT | 필수(httpx) | 있음(같은 버전) | 허용형 |
| h11 | 0.16.0 | MIT | 필수(httpcore) | 있음(같은 버전) | 허용형 |
| idna | 3.20 | BSD-3-Clause | 필수(httpx, anyio) | 있음(같은 버전) | 허용형 |
| typing_extensions | 4.16.0 | PSF-2.0 | 필수(anyio, Python<3.15) | 있음(같은 버전) | 허용형 |

선택 extras(설치되지 않음, 쓰지 않음): `httpx[brotli|cli|http2|socks|zstd]`, `httpcore[asyncio|http2|socks|trio]`, `anyio[trio]`. `exceptiongroup`은 Python<3.11 조건이라 3.12에서는 설치되지 않는다.
**라이선스 원칙 판정:** 신규 3개 중 BSD-3 2개는 허용형, `certifi`(MPL-2.0)는 승인된 이름 예외와 일치한다. 다른 MPL·LGPL·GPL 패키지는 없다. `bi-review` 1번 위반 없음. (`requirements.in`·`requirements.txt` 갱신 때 `httpx==0.28.1`, `httpcore==1.0.9`, `certifi==2026.7.22` 3줄이 추가되고 나머지 줄은 변하지 않아야 한다.)
호스트 임시 venv(Python 3.13)도 `_workspace/fu1e/venv-httpx/v`에 있으나 권위 있는 결과는 위 3.12 컨테이너다(두 결과의 패키지·버전은 동일).

---

## 5. `@superset-ui/embedded-sdk@0.4.0` 확인

### 5-1. 레지스트리·설치 (`npm view` 직접 확인, 임시 폴더 `_workspace/fu1e/sdk/`에 `--save-exact` 설치, `frontend/` 무변경)

| 항목 | 값 |
| --- | --- |
| `dist-tags.latest` | `0.4.0` (공개 시각 `time["0.4.0"]` = 2026-06-18T20:58:25Z) |
| license | Apache-2.0 |
| dependencies | `@superset-ui/switchboard ^0.20.3`, `jwt-decode ^4.0.0` (peerDependencies·engines 없음) |
| 설치 스크립트 | 없음(`scripts`는 build/ci:release/test만). `jwt-decode`의 `prepare`는 husky 개발용이며 소비자 설치 때 실행되지 않음 |
| `dist.tarball` | `https://registry.npmjs.org/@superset-ui/embedded-sdk/-/embedded-sdk-0.4.0.tgz` |
| `dist.integrity` | `sha512-k/PnzvxO0xfeaAO6DRWsC7nG9oH3ooyBQNTRi/EXrK4DIH4ufx6Wy3AD3qDkCjGRw3KMdavCdwAiu2u4TVQ7oA==` (lock과 일치), shasum `c1ae77afa41e473df5d6a9a8e4d2f2f94c0674f2`, unpackedSize 125,438 |
| 진입점 | `main: bundle/index.js`(UMD, 전역 `supersetEmbeddedSdk`), `module: lib/index.js`, `types: dist/index.d.ts` |

lock에 기록된 실제 전이(전부 정확한 버전):

| 패키지 | 버전 | lock `license` | 비고 |
| --- | --- | --- | --- |
| `@superset-ui/embedded-sdk` | 0.4.0 | Apache-2.0 | 직접 |
| `@superset-ui/switchboard` | **0.20.3** | Apache-2.0 | 전이, 의존성 없음 |
| `jwt-decode` | **4.0.0** | **MIT** | 전이, `engines.node >=18` |

예상 밖 전이(MPL/LGPL)·peer 요구 **없음**. 승인 조건(정확한 버전 고정·lock 커밋·라이선스 기록)을 만족할 수 있다. 주의: 직접 의존은 `^0.20.3`, `^4.0.0` 범위이므로 우리 `package-lock.json`이 위 정확한 버전을 고정해야 한다.

### 5-2. API 모양 (`dist/index.d.ts` 요약)

`embedDashboard({ id, supersetDomain, mountPoint, fetchGuestToken, dashboardUiConfig?, debug?, iframeTitle?, iframeSandboxExtras?, iframeAllowExtras?, referrerPolicy?, resolvePermalinkUrl?, guestTokenFetchTimeoutMs? }): Promise<EmbeddedDashboard>`
- 반환 객체: `getScrollSize`, `unmount`, `getDashboardPermalink`, `getActiveTabs`, `observeDataMask`, `getDataMask`, `getChartStates`, `getChartDataPayloads`, `setThemeConfig`, `setThemeMode` (설계가 가정한 이름은 모두 있음).
- `dashboardUiConfig`: `hideTitle`(1), `hideTab`(2), `hideChartControls`(8), `emitDataMasks`(16), `showRowLimitWarning`(32), `filters.{visible,expanded}`(URL `show_filters`/`expand_filters`), `urlParams`. 값이 있으면 iframe 주소에 `?uiConfig=<합계>`가 붙는다(`{hideTitle:false}`면 `uiConfig=0`).
- `supersetDomain`: 끝의 `/`는 SDK가 제거한다. iframe 주소는 `${supersetDomain}/embedded/${id}${쿼리}`. **경로를 포함한 `http://host:port/bi-wizard/superset/`로 실제 동작 확인**(§5-4).
- iframe `sandbox`: `allow-same-origin allow-scripts allow-presentation allow-downloads allow-forms allow-popups` + `iframeSandboxExtras`; `allow="fullscreen; clipboard-write"` + `iframeAllowExtras`. `referrerPolicy` 미지정이면 브라우저 기본값(→ `allowed_domains` 검사는 Referer로 이뤄짐, §5-4 S0).
- `guestTokenFetchTimeoutMs` 기본 **30,000ms**: `fetchGuestToken` 한 번이 이보다 오래 걸리면 거부된다.
- 통신: `iframe`의 `load` 이벤트에서 `MessageChannel`을 만들고 `contentWindow.postMessage({type:"__embedded_comms__", handshake:"port transfer"}, supersetDomain, [port2])`로 포트를 넘긴다. 이후 `@superset-ui/switchboard`가 그 포트로 `emit('guestToken', {guestToken})`를 보낸다. `postMessage`의 targetOrigin에 경로가 포함된 URL을 넘겨도 브라우저가 origin만 쓰므로 동작한다(실행 확인).

### 5-3. 토큰 갱신·언마운트 (소스 `lib/index.js`·`lib/guestTokenRefresh.js` + 실행 확인)

소스 규칙:
- 첫 토큰: `embedDashboard` 시작 때 `fetchGuestToken()`을 호출하고 iframe 로드와 함께 기다린다(`Promise.all`). **첫 호출이 실패하면 `embedDashboard`가 거부되고 `mountPoint.replaceChildren()`로 iframe을 지운다. 재시도하지 않는다**(재시도는 갱신 주기에만 있음).
- 갱신: 토큰 JWT의 `exp`를 `jwt-decode`로 읽어 `ttl = max(10초, exp − 지금) − 5초` 뒤 `setTimeout(refreshGuestToken)`을 건다(`REFRESH_TIMING_BUFFER_MS=5000`, `MIN_REFRESH_WAIT_MS=10000`, 파싱 실패 시 `DEFAULT_TOKEN_EXP_MS=300000`). `setInterval`은 쓰지 않는다. 갱신 호출이 성공하면 새 토큰의 `exp`로 다음 타이머를 건다.
- 갱신 실패(거부·타임아웃): **10초(`DEFAULT_TOKEN_REFRESH_RETRY_MS`) 뒤 다시 시도, 무한 반복.**
- `unmount()`: `unmounted=true`, `clearTimeout(refreshTimer)`, `mountPoint.replaceChildren()`. 진행 중인 갱신 요청이 끝난 뒤에도 `if (unmounted) return`이라 `emit`도 새 타이머도 없다.
- 반환 객체는 **Promise가 풀린 뒤에야** 얻는다.

실행 확인(Playwright + Chromium, 실제 Superset 6.1.0 + 실제 발급, SDK `bundle/index.js`. 295초 갱신을 보려고 시험 페이지에서만 280초 이상 타이머를 1/100로 줄임):

| 시험 | 결과 |
| --- | --- |
| S1 정상 갱신 → `unmount()` | 갱신이 약 2.9초 간격(= 295초/100)으로 호출됨. `unmount()` 직후 타이머 활성 0(설정 3, 해제 1), iframe 0개, 이후 14초 동안 `fetchGuestToken` 호출 **0회 추가**. 정리 확인 |
| S2 갱신 요청이 진행 중일 때 `unmount()` | 진행 요청이 끝난 뒤에도 새 호출·새 타이머 없음(8초 관찰, 호출 수 불변, 활성 타이머 0) |
| S3a **`embedDashboard`가 풀리기 전에 정리(핸들 없이 `disposed`만 true)하고 이후 `unmount()`를 부르지 않은 경우** | **SDK가 정리되지 않고 계속 동작한다.** 호출 시각 약 0.05, 3.6, 13.6, 23.6초(= 갱신 1회 + 10초마다 재시도 무한). `fetchGuestToken`이 `disposed`로 던져도 SDK는 10초마다 다시 부른다. 활성 타이머 1개가 계속 남음 |
| S3b 같은 상황에서 Promise가 풀린 뒤 `unmount()` 호출 | 호출 1회뿐, 타이머 정리(활성 0) |
| S4 첫 `fetchGuestToken` 실패 | `embedDashboard`가 같은 오류로 거부, iframe 0개, 12초 동안 재호출 없음 |

→ **설계 §8-3의 `disposed` 가드만으로는 부족하다.** React `useEffect` 정리가 `embedDashboard` 완료 전에 일어나면(StrictMode 이중 마운트, 빠른 화면 전환) 핸들이 없어 `unmount`를 못 부른다. 효과 안에서 `embedDashboard(...).then(h => { if (disposed) h.unmount(); else handle = h; })` 형태로 **늦게라도 `unmount()`를 부르는 처리**가 필요하다. 또 첫 실패는 SDK가 재시도하지 않으므로 화면 쪽에 다시 시도 동작이 필요하다(설계 §8-3 "SDK가 10초마다 재시도"는 갱신에만 해당).

기타 관찰:
- 클라이언트 시계가 토큰 `exp`보다 5분 이상 앞서 있으면 `ttl`이 하한 10초가 되어 **5초마다 `fetchGuestToken`을 부른다**(`max(10s, …) − 5s`). 소스에서 읽은 결과이며 실행으로는 확인하지 않았다. 30회/60초 한도에서 탭 3개 이상이면 걸릴 수 있다.
- `embedDashboard`는 iframe의 `load` 이벤트가 오면 풀린다. **임베드 페이지가 403이어도 `load`는 오므로 SDK는 성공으로 끝난다**(S0: `allowed_domains`에 없는 origin에서 `start: ok`, iframe 안은 JSON 403). 허용 origin 불일치는 SDK 거부로 감지되지 않는다.
- `debug` 기본 `false`. `debug:true`이면 SDK와 switchboard가 `console.debug`로 메시지·오류를 출력한다 → 운영에서 켜지 않는다. 항상 쓰는 `console.error`는 switchboard의 "메서드 실행 중 오류"와 "초기화 안 됨" 두 곳뿐이며 토큰을 넘기지 않는다.

### 5-4. 저장소·URL·로그 (소스 grep + 실행 확인)

| 검사 | 결과 |
| --- | --- |
| 소스(`lib/*.js`, switchboard `lib`/`esm`, `bundle/index.js`)에서 `localStorage`, `sessionStorage`, `document.cookie`, `indexedDB`, `history.`, `location.`, `window.name`, `XMLHttpRequest`, `fetch(`, `sendBeacon` | **0건** |
| `console.*` | `console.debug`(debug일 때만), `console.error`(switchboard 오류 2곳). `console.log`·`warn` 0건 |
| 실행(S5, 임베드 화면 6초 유지 후): 최상위·iframe 프레임의 `localStorage`, `sessionStorage`, `document.cookie`, IndexedDB 이름, 컨텍스트 쿠키, 프레임 URL | **입장권(JWT) 0건.** `localStorage`에는 Superset 앱의 `redux`, `dashboard__explore_context`(같은 origin이라 최상위와 공유됨), `sessionStorage`·IndexedDB 비어 있음. 쿠키는 Superset이 발급한 HttpOnly `session`(경로 `/bi-wizard/superset`) 1개 |
| 입장권 전달 방식 | HTTP 요청 **헤더** `X-GuestToken`(iframe 안 Superset 앱이 보냄, 4건 확인). 요청 URL에 토큰 0건 |
| 콘솔 | 입장권 문자열 0건. 알려진 항목: Superset의 service-worker 404 오류, SDK 샌드박스 경고("allow-scripts와 allow-same-origin 동시 → 탈출 가능"; SDK가 필수로 붙이는 속성이며 `iframeSandboxExtras`로 줄일 수 없음) |
| 서버 로그 4종(superset, backend, postgres, frontend) | `eyJ` 0건, 더미 비밀값(서비스·발급·관리자 비밀번호, `SECRET_KEY`, `GUEST_TOKEN_JWT_SECRET`) 0건 |

### 5-5. Superset 6.1.0 호환 (실행 확인, 포털 화면이 아닌 시험 페이지)

- 포털 origin(시험 페이지 `http://127.0.0.1:55191`)과 Superset이 같은 nginx 아래 `/bi-wizard/superset/`로 있는 상태에서 SDK 0.4.0 `embedDashboard` + 실제 입장권으로 `GET /embedded/<uuid>?uiConfig=0` **200**, 이어서 `…/api/v1/me/roles/`, `/dashboard/1/charts`, `/dashboard/1/datasets`, `/dashboard/1?q=…` **모두 200**(`X-GuestToken` 헤더). 즉 postMessage 포트 핸드셰이크(`__embedded_comms__`, switchboard)와 입장권 전달이 6.1.0에서 동작한다. 시험 대시보드에는 차트가 없다(차트 6종은 1e-d 범위).
- `allowed_domains`: 임베드 설정에 시험 origin이 없을 때 `/embedded/<uuid>` HTML이 **403**(JSON 본문 `403 Forbidden: You don't have the permission…`), origin을 추가하면 200. 08 §5 `allowed_domains` 설명(Referer 검사)과 일치.

---

## 6. 메모리 기준선 (유휴, 8GB 예산 대비 판정은 1e-d)

환경: 호스트 16GB, **cgroup v1**(Docker `Cgroup Version: 1`). 설계 §10의 `memory.peak`(cgroup v2)는 **이 환경에서 없다**. 대신 `memory.max_usage_in_bytes`(컨테이너 시작 이후 최대)를 쓴다. 측정은 전체 스택을 한 번 멈춘 뒤 `superset-init`부터 다시 올리고(콜드 스타트) 정상화 후 90초 유휴 상태에서 했다. 브라우저·API 부하 없음. 서비스 5개(postgres, backend, frontend, superset + 종료된 init/migrate/db-bootstrap).

| 서비스 | `mem_limit` | 유휴 `docker stats`(MiB) | cgroup 사용량(MiB, 페이지 캐시 포함) | 시작 이후 최대(`max_usage_in_bytes`, MiB) | RSS(MiB) | OOMKilled / 재시작 |
| --- | --- | --- | --- | --- | --- | --- |
| postgres | 1536m | **99.5** | 179 (캐시 161) | 194 | 9 | false / 0 |
| backend | 1g | **68.4** | 69 | 82 | 66 | false / 0 |
| superset | 2g | **196.6** | 197 | 198 | 189 | false / 0 |
| frontend | 256m | **5.3** | 7 | 8 | 4 | false / 0 |
| superset-init(일회성, 1g) | 1g | (종료) | - | 시작 중 샘플링 최대 **185.2** | - | - |
| **상시 4개 합계(docker stats)** | 합 4.75GiB | **약 370** | | | | |

- 콜드 스타트 구간(초기화 포함 약 70초, 초당 샘플)의 서비스별 최대: backend 78.7, frontend 5.5, postgres 100.1, superset 196.9, superset-init 185.2 MiB.
- `docker inspect`의 `HostConfig.Memory`가 compose 값과 같음(1.5GiB, 1GiB, 2GiB, 256MiB 확인).
- 호스트 `free -m`: 사용 1,073MB(전체 스택 + 시험 후).
- 참고: 위 측정 이전의 시험(브라우저 5개 시나리오, 발급·등록 호출) 동안에도 OOM·재시작은 없었다. 같은 컨테이너의 부하 구간 최대는 따로 재지 않았다(1e-d가 S1~S4로 잰다).

---

## 7. 설계가 바뀌어야 하는 점 (`docs/research/fu1e-design.md` 대비)

| 번호 | 설계 위치 | 실측 | 영향 | 구현을 막는가 |
| --- | --- | --- | --- | --- |
| 1 | §3-3 D, §1 표 D | `related/database`가 된다. 대체안 ②·권한 확대 모두 **불필요** | D 항목 삭제, `DB_MISMATCH` 사유 코드는 선택(등록 직후 `GET`의 `database.database_name` 대조는 계속 가능) | 아니오 |
| 2 | §3-4 5행, 08 §2-1 4행 | `POST /dataset/` 응답에서 열은 `data.columns`, `result`에는 없음 | 5단계를 `GET`으로 읽는 설계는 그대로 맞음. "POST 응답의 열 id" 표현이 필요하면 `data.columns[].id` | 아니오 |
| 3 | §3-4 3행(422 중복) | 메시지에 URL 인코딩된 이름이 포함됨 | 응답 본문을 로그·`last_error`에 쓰지 말 것(이미 금지). 본문 키 `message.table[]`로 중복 판정 가능 | 아니오 |
| 4 | §4-1 5행, §3-2 | 발급 `POST`도 세션 쿠키 + `X-CSRFToken` 필요(없으면 400) | 발급 계정 세션도 서비스 계정과 같은 로그인·CSRF 처리 사용(설계가 같은 클래스라고 했으므로 일치). 쿠키 항아리 분리는 그대로 | 아니오 |
| 5 | §3-2 CSRF 재시도 규칙 | CSRF 400과 훅 거부 400이 같은 상태 코드 | 재시도 조건을 상태 코드가 아니라 본문의 `CSRF token`으로 한정. 훅·스키마 400은 `SUPERSET_REJECTED`(502) | 아니오 |
| 6 | §4-1, 03c 표(`user` 생략 시 500) | 훅 설치 후에는 `user` 생략·빈 이름이 400 | 오류 매핑 영향 없음(항상 `user`를 보냄) | 아니오 |
| 7 | §4-1 3행 | 대문자 uuid가 훅을 통과해 200 | backend가 소문자 정규형으로 보내는 설계가 맞음(방어선은 backend 한 곳) | 아니오 |
| 8 | §3-2 재로그인 | 접근 토큰 만료는 401 `{"msg":"Token has expired"}`, 깨진 토큰은 **422** | 401만 갱신 대상, 422(형식 오류)는 코드 오류로 취급해 재로그인 루프에 빠지지 않게 한다 | 아니오 |
| 9 | §8-3 정리 규칙 | `embedDashboard` 완료 전 정리 시 핸들이 없어 SDK 타이머가 영구 유지(10초마다 호출) | **`disposed` 가드만으로는 부족.** Promise 완료 뒤 `disposed`면 `unmount()` 호출 필요, 첫 실패는 화면 쪽 재시도 필요(SDK는 재시도 안 함) | 아니오(설계 보강) |
| 10 | §8-3 "임베드 실패 안내" | 허용 origin 불일치(403)여도 SDK는 성공으로 끝난다 | 허용 origin 오류는 SDK 거부로 감지 불가. 관리자 안내 문구(S8 등록 도움말)와 QA 점검 항목으로 대응 | 아니오 |
| 11 | §10 메모리 측정 | 이 환경은 cgroup v1 | `memory.peak` 대신 `memory.max_usage_in_bytes` 사용(1e-d 계획 수정) | 아니오 |
| 12 | §5 H0 근거 | ②의 문자 해석(§2-2)이 사용자 판정 필요 | H0 종결 결정은 메인이 사용자에게 §2-2 표를 보여 주고 확인 | **이 1건만 사용자 확인 대기**(나머지 구현은 막지 않음) |

그 밖에 설계와 일치한 것: 서비스 계정 4권한으로 등록·전체 열 `PUT`·refresh·이름 변경·삭제·related_objects 성공(P1), 발급 계정은 다른 API 403, 훅 거부 5가지, 입장권 유효 300초, 표시 이름 보존, `schema_access` 없는 DB에는 등록 불가, backend 컨테이너가 `http://superset:8088{root}/health`에 닿고 Superset 접속 변수 5개가 전달됨(값 확인 생략).

## 8. 승인 필요 항목

없음. 프로브 중 새 환경변수·새 의존성·기준 외 설정·권한 확대가 필요한 경우는 발견되지 않았다. (사용자 확인이 필요한 것은 §2-2 해석 1건뿐이며 권한 확대가 아니다.) `certifi`·`httpx`·SDK는 이미 승인된 범위다.

## 9. 시험 환경 정리·잔여물

- 컨테이너: `docker compose -p probe1e stop` 후 `rm -f`로 모두 제거. 시험 전용 nginx(`probe1e-testnginx`)는 `docker rm -f`로 제거.
- **남은 것(이름 지정 삭제 명령 목록 밖이라 지우지 않았다):** 볼륨 `probe1e_postgres_data`, `probe1e_p5vol`, 이미지 `probe1e-p5:tmp`, `bi-wizard-superset:6.1.0`(로컬 빌드), 로컬 태그 `apache/superset:6.1.0`(= CA 파일·환경변수만 얹은 오버레이, 원본은 `apache/superset:6.1.0-orig`), 임시 폴더 `_workspace/qa/ov-superset/`, `_workspace/qa/probe1e/`(더미 env), `_workspace/fu1e/sdk/`, `_workspace/fu1e/venv-httpx/`, `_workspace/fu1e/probe/dockerd-1e0.log`. 모두 `.gitignore`의 `_workspace/` 안이다. 저장소 추적 파일은 바뀌지 않았다.
- 이 세션에서 `dockerd`를 직접 시작했다(실행 중으로 둠). `service docker start`는 쓰지 않았다.
- 프로브 스크립트는 세션 임시 폴더에 두었고 저장소에 넣지 않았다.
