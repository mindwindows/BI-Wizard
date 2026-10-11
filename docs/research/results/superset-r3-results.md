# Gate ③ 3라운드 Superset 런타임 실험 결과 (X-18, X-20, X-21, X-22, X-23)

- 승인: 사용자 승인 범위 X-18, X-20, X-21, X-22, X-23(`03b` 3-6). 클라우드 세션 안에서만 실행. 저장소 추적 파일(docs, CLAUDE.md, 코드, 설정)은 수정하지 않았다. git 미사용.
- 환경: PostgreSQL **16.10**(`postgres:16.10-bookworm`), Apache Superset **6.1.0**(`bi-wizard-superset:6.1.0`, flask-talisman **1.1.0**: 컨테이너 `site-packages` 확인), compose 프로젝트 `g3x`와 시험용 더미 값 env 파일 `_workspace/qa/g3x.env`(비밀 아님), 이미지 재빌드·pull 없음(`up -d --no-build`). 브라우저: Playwright 1.56.1 + 헤드리스 Chromium(`/opt/pw-browsers/chromium-1194`). Embedded SDK는 `_workspace/qa/sdk/x/package/bundle/index.js`(0.4.0).
- 시험 데이터(직접 생성): schema `bi_data`에 표 `ds_1`(period_a, team, value)·`ds_2`(base_date, team, value)·`ds_3`·`x23_src`, 뷰 `dv_1`~`dv_3`·`x23_v1`~`x23_v4`·`x22_v`, 팀 값 `팀1/팀2/팀3`(+ `영업 1팀`, `R&D!(x)'s`). `public.x20_pub`(X-20 시험용으로만 `bi_readonly`에 SELECT를 부여한 표).
- **시험 전용 설정(저장소 밖):** X-21의 Embedded 시험 직전에 `_workspace/qa/gamma-override.yml`(기존 파일, `GUEST_ROLE_NAME = "Gamma"`)을 얹어 `superset` 컨테이너만 다시 만들었다. 운영 기준선과 다른 설정이며 이 시험 인스턴스에만 있었고 종료 때 컨테이너와 함께 삭제했다. `Public` 역할은 건드리지 않았다. X-20·X-22·X-23은 이 설정 아래에서 실행되었지만 guest 역할과 무관하다.
- 표기: "확인" = 실행하여 관찰, "소스 근거" = 컨테이너 안 코드·저장소 문서 읽기, "추정" = 그 외.
- 스크립트·원출력·스크린샷: `_workspace/gate3/experiments/r3/`(Git 제외). 이 문서의 숫자는 거기의 `*.out`, `*.json`에서 가져왔다. 파일 안내는 문서 끝.

---

## X-18. Superset 일반 화면을 포털 iframe 안에 표시할 수 있는가

### (1) 응답 헤더 (`curl -i`, 그리고 브라우저에서 수집한 문서 응답 헤더)
| 시험 | 결과 |
| --- | --- |
| `/login/`, `/health`, `/superset/welcome/`(302), `/explore/`(302), `/superset/dashboard/1/`(302), `/sqllab/`(302), `/embedded/<없는 uuid>`(404), `/api/v1/dashboard/1`(401) 비로그인 응답 | **전부 `X-Frame-Options: SAMEORIGIN`**. `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`도 붙음 |
| 로그인한 관리자 세션의 문서 응답(브라우저 수집): welcome, `/explore/?slice_id=1`, `/superset/dashboard/1/`, `/sqllab/`, `/dashboard/list/`, 실제 `/embedded/<uuid>` | 전부 `X-Frame-Options: SAMEORIGIN` |
| `Content-Security-Policy` | `base-uri, default-src, img-src, worker-src, connect-src, object-src, style-src, font-src, script-src`만 있음. **`frame-ancestors` 없음**(`grep -ci frame-ancestors` 0건, 원출력 `x18/csp_login.txt`) |
| `Set-Cookie` | `session=<값>; HttpOnly; Path=/bi-wizard/superset; SameSite=Lax`. `Secure` 없음(이 시험은 HTTP) |
| 경로 주의 | 6.1.0의 실제 경로는 `/superset/welcome/`, `/explore/`, `/superset/dashboard/<id>/`, `/sqllab/`. `/dashboard/<id>/`는 404(경로 아님). 하위 경로 아래 실제 주소는 `/bi-wizard/superset/superset/welcome/`처럼 `superset`이 두 번 나온다(이 구성의 정상 동작) |

### (2) 같은 origin(`http://127.0.0.1:25173/bi-wizard/__x18.html`, Playwright가 응답을 주입한 시험 페이지) iframe
| 시험 | 결과 |
| --- | --- |
| iframe `src=/bi-wizard/superset/login/` (비로그인) | 로그인 폼이 그려짐(스크린샷 `x18/a1_same_login_anon.png`) |
| **iframe 안에서** 아이디·비밀번호를 입력해 로그인 | 성공. iframe이 `/superset/welcome/`으로 이동하고 목록이 그려짐(`a2_...png`). 세션 쿠키(`SameSite=Lax`)가 같은 사이트 iframe에서 저장·전송됨 |
| iframe `src=/explore/?slice_id=1` | Explore 화면이 그려지고 `chart/data` 요청 2건이 iframe 안에서 200 |
| iframe `src=/superset/dashboard/1/` | 대시보드·필터 바·표 차트 2개가 그려짐, `chart/data` 3건 200(`b3_same_dashboard1.png`) |
| iframe `src=/sqllab/`, `/dashboard/list/` (관리자) | 정상 표시 |
| iframe `src=/embedded/<uuid>` (SDK 없이, 부모 핸드셰이크 없음) | 빈 화면(예상된 동작: SDK가 guest token을 보내야 그려짐). 콘솔에 `static/service-worker.js` 404 오류 |
| 콘솔 오류 | 모든 화면에 Scarf 픽셀 이미지가 CSP로 차단된 오류(저장소의 Scarf 차단 설정이 의도대로 동작). 그 밖에 화면 동작을 막는 오류 없음 |

### (3) 다른 origin(`http://localhost:25173` 부모 → `http://127.0.0.1:25173` iframe, 그리고 반대 방향)
| 시험 | 결과 |
| --- | --- |
| 부모 `localhost` → iframe `127.0.0.1`의 `/login/`, `/explore/`, `/superset/dashboard/1/`, **`/embedded/<uuid>`** | **모두 차단**: iframe 안이 빈 화면, 브라우저 네트워크 `net::ERR_ABORTED`, iframe 문서 응답은 브라우저에 도달하지 않음 |
| 부모 `127.0.0.1` → iframe `localhost`의 `/login/` | 같은 결과(차단) |
| 차단 메시지 | 이 환경의 Playwright/CDP로는 "Refused to display ... X-Frame-Options" 콘솔 문구를 **수집하지 못했다**(콘솔 이벤트 없음). 차단 원인은 서버가 `X-Frame-Options: SAMEORIGIN`(위 (1) 관찰) + CSP에 허용 조상 없음이라는 것과 일치하지만, 차단 문구 자체는 확인하지 못함 |
| 헤더를 브라우저 안에서 지우는 시뮬레이션(CDP Fetch)으로 쿠키 SameSite 영향을 보려던 시험 | **못 했다**: 교차 origin iframe 요청이 페이지 세션의 가로채기 대상이 아니라서(헤더 제거 0건) 시험이 성립하지 않음. 쿠키 영향은 미확인(소스 근거만) |

### 설정을 바꾼다면 (코드 읽기 근거, 적용하지 않음 — 운영 기준선 이탈이라 별도 승인 필요)
- 응답에 `X-Frame-Options`를 쓰는 곳은 flask-talisman 1.1.0의 `_set_frame_options_headers`(`talisman.py:360-367`)뿐이다. `frame_options`가 거짓이면 헤더를 쓰지 않는다. Superset 기본 `TALISMAN_CONFIG`에는 `frame_options` 키가 없어 기본값 `SAMEORIGIN`이 적용된다(`talisman.py:80`, `config.py:2119-2157`). 인자는 `talisman.init_app(app, **TALISMAN_CONFIG)`로 전달된다(`initialization/__init__.py:892-902`).
- 다른 origin을 허용하려면 `TALISMAN_CONFIG`에 `frame_options`를 거짓 값으로 두고 `content_security_policy`에 `"frame-ancestors": [...]`를 넣는 방식이 공식 문서(`networking-settings.mdx`)의 CSP 안내와 맞다. `X-Frame-Options: ALLOW-FROM`은 현행 브라우저가 무시한다(일반 지식).
- 로그인 쿠키까지 교차 사이트 iframe에서 쓰려면 `SESSION_COOKIE_SAMESITE`를 `superset_config.py`에 두는 것만으로는 부족하다. Talisman이 `init_app`에서 `app.config['SESSION_COOKIE_SAMESITE'] = session_cookie_samesite`(기본 `"Lax"`)로 덮어쓰므로(`talisman.py:199`) `TALISMAN_CONFIG`의 `session_cookie_samesite`(`"None"`)와 `session_cookie_secure`(`True`, HTTPS 필요)로 줘야 한다(소스 근거, 미실측).

### 결론
- **같은 origin(우리 구성: 포털과 Superset이 같은 호스트의 하위 경로)이면 설정 변경 없이 일반 화면(로그인, 목록, Explore, 대시보드, SQL Lab)이 iframe 안에 표시되고 로그인도 iframe 안에서 된다.** (확인) → EX3(포털 안 iframe)에 "기준선 이탈 없음" 입력이 된다.
- 다른 origin이면 `/embedded/`를 포함한 모든 Superset 화면이 차단된다(확인). 즉 메인 플랫폼에서 포털과 Superset이 다른 호스트로 나뉘면 Embedded SDK 자체도 `frame_options`/CSP 변경이 필요하다. `deploy-coordination.md`의 "같은 origin" 가정이 깨지는 조건이다.
- 한계: ① 같은 origin iframe의 상호작용은 로그인·이동·차트 조회만 봤다. 새 창 열기(`window.open`), 파일 다운로드, 전체 화면, 모바일 폭은 시험하지 않았다. ② 포털 자체가 `X-Frame-Options`/CSP를 내리는 경우(메인 플랫폼 보안 헤더)는 이 로컬 nginx로는 재현 불가(`deploy-coordination.md` 19번). ③ 실제 HTTPS·`Secure` 쿠키 환경은 시험하지 않았다. ④ 차단 메시지 문구와 교차 사이트 쿠키 동작은 미확인.

---

## X-20. 작성자 역할(Gamma 복사본 + schema 보조 역할) 실측

구성(이름 규칙 `x20_`): 역할 `x20_author_copy`(= Gamma 권한 복사), `x20_author_schema_bi_data`(= `schema_access` on `[BI-Wizard (read-only)].[bi_wizard].[bi_data]` 한 개), 사용자 `x20_author1`, `x20_author2`(둘 다 두 역할만, 내장 Gamma 미부여). 역할·사용자 생성과 권한 부여는 **6.1.0 REST로 모두 가능**(`POST /api/v1/security/roles/`, `POST /api/v1/security/roles/{id}/permissions`(목록을 **통째로 교체**), `POST /api/v1/security/users/`, `GET /api/v1/security/permissions-resources/`(한 페이지 최대 100건)).

### (a) 복사본과 Gamma의 권한 집합
| 시험 | 결과 |
| --- | --- |
| API로 읽은 Gamma 권한 id 목록(95개)을 `x20_author_copy`에 그대로 부여 | 복사본 95개, **차이 0개**(Gamma만 있음 `[]`, 복사본만 있음 `[]`). `superset` DB(`ab_permission_view_role`)의 SQL 집합 차(Gamma − 복사본)도 0건 |
| Gamma 권한 이름 목록 | `x20_gamma_perm_names.txt`(95줄) |
| 눈에 띄는 항목 | Gamma에 **`can_get_embedded`, `can_delete_embedded`는 있고 `can_set_embedded`는 없음**. `can_write Dataset`, `can_write Database`, `can_read SQLLab`, `can_execute_sql_query SQLLab`, `menu_access SQL Lab`, `can_samples Datasource`는 **없음**. `can_read Database`, `can_export Dashboard`, `can_csv`, `can_explore`는 **있음** |

### (b) 데이터 접근
| 시험 (`x20_author1`) | 결과 |
| --- | --- |
| `GET /dataset/` | `dv_1`, `dv_2`, `dv_3`(물리), `x20_virtual`(가상, `SELECT * FROM bi_data.dv_1`)만 보임 |
| 위 4개 `GET /dataset/{id}`, `POST /chart/data` | 모두 200 (물리·가상 모두 조회됨) |
| `public.x20_pub`(관리자가 등록한 데이터셋, DB 쪽 SELECT 권한은 있음), `information_schema.tables` 데이터셋 | `GET /dataset/{id}` 404, `chart/data` 403 |
| `GET /database/`, `/database/1/schemas/`, `/database/1/tables/` | DB 1개 보임. **schema 목록 `['bi_data']`만**(`public`·`information_schema` 안 보임), `public` 표 목록 `[]`, `bi_data` 표 6개 |
| Explore 사용자 정의 SQL로 `public.x20_pub` 읽기(`(SELECT ... FROM public.x20_pub)`를 지표·열·WHERE에 넣음) | **6.1.0이 막음**: `Custom SQL fields cannot contain sub-queries`(`ADHOC_SUBQUERY_NOT_ALLOWED_ERROR`, 400/403). 하위 질의 우회는 이 경로로 되지 않음 |
| 서비스·관리자가 나중에 `bi_data`에 만든 데이터셋 | 작성자에게 **추가 권한 부여 없이 바로 보임**(X-22에서 만든 `[팀1] 월별 실적`이 `author1`의 목록에 나타남, 200) |
| 부가: 가상 데이터셋의 SQL이 다른 schema 표를 읽는 경우 | 관리자가 **선언 schema `bi_data`, SQL `SELECT * FROM public.x20_pub`**로 등록하면 `author1`(schema_access `bi_data`만)이 `chart/data` 200으로 `public` 표 값을 읽었다(확인). 읽는 쪽 권한은 선언 schema 기준이고 SQL이 참조하는 표는 등록 시점에만 검사된다(아래 X-22 부가 확인). **작성자는 데이터셋을 만들 수 없으므로(403) 이 경로를 직접 만들지는 못한다** |

### (c) 차트·대시보드 작성과 소유권
| 시험 | 결과 |
| --- | --- |
| 물리·가상 데이터셋으로 차트 생성(`POST /chart/`) | 201 |
| **접근권이 없는 데이터셋**(`public`, `information_schema`)으로 차트 생성 | **201**(03c 관찰과 같음). 단 만든 사람도 그 차트를 `GET`하면 404이고 차트 목록에도 안 나온다(소유자 `author1`에게 안 보이는 차트가 DB에 남음) |
| 자기 차트 수정 | 200. 소유자 목록 = `[author1]` |
| 대시보드 생성·저장, 자기 소유 대시보드에 자기 차트 추가(`PUT /chart/{id}` `dashboards:[id]`) | 201 / 200 / 200 |
| **`PUT /dashboard/{id}`에 `position_json`만 보냄** | 저장은 되지만 **차트↔대시보드 연결은 안 바뀜**(연결된 차트 목록 그대로) |
| `PUT /dashboard/{id}`에 `json_metadata.positions`(UI 저장 방식)로 차트 배치 | 연결 갱신됨. **다른 사람(관리자) 소유 차트 1번을 자기 대시보드에 넣어도 200**(연결됨). 반면 `PUT /chart/1 {"dashboards":[자기]}`는 403 |
| 관리자 소유 차트 수정·삭제 | 403, 403 |
| 관리자 소유 대시보드(미게시) 보기·수정·삭제 | 404, 404, 404(보이지 않음). **게시(`published`)하면 목록과 `GET`이 200**(`DashboardAccessFilter`가 게시 여부와 데이터셋 접근을 보는 것으로 관찰, 소스 본문은 미확인) |
| `author2`가 `author1`의 차트 수정 | 403 |
| `author2`가 `author1`의 미게시 대시보드 보기·수정 | 404, 404. `author1`이 게시하면 `author2`의 목록에 나타남 |
| 두 작성자의 차트 목록 | 자기 차트 + 관리자 차트(데이터셋 접근이 있어서 목록에 보임). 접근 불가 데이터셋 위 차트는 목록에서 빠짐 |

### (d) SQL Lab, 데이터셋 생성, DB 연결
| 시험 | 결과 |
| --- | --- |
| 메뉴 | `Dashboards / Charts / Datasets / Settings`만. **SQL Lab 메뉴 없음**(`x20_ui.out`) |
| `/sqllab/` 페이지 | 로그인 후 `welcome`으로 되돌려짐. `POST /sqllab/execute/`, `GET /sqllab/`, `/saved_query/`, `/query/` 모두 **403** |
| 데이터셋 생성(물리·가상), 데이터셋 이름 변경 | 403 / 403 / 403 |
| `PUT /database/1`, `POST /database/` | 403 / 403 |
| `GET /database/1` | 200이지만 연결 문자열·계정은 응답에 없음(`backend`, `driver`, 이름 등만) |
| `/databaseview/list/`, `/tablemodelview/list/`, `/dataset/add/` 화면 | 렌더링되지만(화면 껍데기) 변경 API는 403 |
- SQL Lab은 **위험으로 나타나지 않았다**(Gamma 복사본에는 권한이 없음).

### (e) 임베드 켜기(`/dashboard/{id}/embedded`)
| 시험 | 결과 |
| --- | --- |
| `can_set_embedded` **없이**: `POST`/`PUT`/`DELETE`(자기 대시보드, 관리자 대시보드) | 전부 **403**. `DELETE`도 403(Gamma가 `can_delete_embedded`를 갖는데도 막힘: 삭제도 `can_set_embedded`가 필요) |
| `GET /dashboard/{id}/embedded` (관리자 대시보드 1번) | 200(Gamma의 `can_get_embedded`) |
| `can_set_embedded Dashboard`를 `x20_author_copy`에 추가 | 권한 목록 교체 방식으로 95→96개 |
| 추가 후 자기 대시보드 `POST embedded` | 200 |
| 추가 후 **관리자 소유·게시** 대시보드 `POST embedded` | **200** (소유권 확인 없음) |
| 추가 후 관리자 소유 **미게시** 대시보드 | 404(보이지 않아서) |
| 추가 후 관리자 소유·이미 임베드된 대시보드에 `PUT {"allowed_domains":[]}` | **200**: 관리자가 정한 `allowed_domains: ["https://portal.example"]`이 `[]`로 바뀌고 `changed_by`가 `author1`로 기록됨 |
| 추가 후 같은 대시보드 `DELETE embedded` | **200**: 임베드 설정이 삭제됨(관리자 확인 시 404) |
- 후속 정리: 실험 뒤 `can_set_embedded`를 복사본에서 다시 제거(96→95).

### (f) 새 권한이 생겨도 복사본이 자동으로 따라가지 않는다
| 시험 | 결과 |
| --- | --- |
| "이전 버전" 모사: Gamma와 복사본에서 `can_export Dashboard`를 같이 제거, Gamma에만 시험용 권한 `can_read X20_NewView`(새 view menu를 REST로 생성) 추가 | Gamma 95 / 복사본 94, 차이 = 시험용 권한 1개 |
| 컨테이너에서 `superset init` 실행(superset-init이 매 기동 하는 것과 같은 명령, 종료 코드 0) | **Gamma에 `can_export Dashboard`가 다시 들어감(96)**. 복사본은 **94 그대로**(차이 2개). 사용자 정의 역할은 그대로 존재 |
| `superset init`이 Gamma에서 추가 권한을 지우는가 | **안 지움**(시험용 `can_read X20_NewView`가 남음). init은 Gamma에 **더하기만** 하고 빼지 않는 것으로 관찰 |
| 복사본에 `can_export`가 없는 결과 | `author1`의 `GET /dashboard/export/`가 **403**(Gamma 사용자라면 가능했을 동작) |
- 후속 정리: 시험용 권한·view menu 삭제, 복사본 = Gamma 95개로 복구.

### 결론
- **Gamma 복사본(95개) + schema 보조 역할(1개)은 03c의 내장 Gamma + schema 조합과 같은 동작을 한다**: `bi_data`의 물리·가상 데이터셋은 보고 조회하고 `public`·`information_schema`는 못 쓰며, 차트·대시보드를 만들고 저장하고, SQL Lab·데이터셋 생성·DB 변경은 못 한다(확인). 사용자 추가 데이터셋도 권한 추가 없이 보인다.
- **복사본은 Superset이 새 권한을 Gamma에 추가해도 자동 갱신되지 않는다**(확인: `superset init`이 Gamma만 갱신). 업그레이드 때 "Gamma와 복사본 차이"를 점검하는 절차가 필요하다(`GET /security/roles/search/`로 두 역할의 `permission_ids`를 비교하면 된다).
- **`can_set_embedded`를 작성자 역할에 주면 소유하지 않은 게시 대시보드도 임베드 켜기·`allowed_domains` 변경·임베드 삭제를 할 수 있다**(확인, 소스에 소유권 확인이 없다는 앞선 판독과 일치). 미게시 대시보드는 보이지 않아서 막힌다. 즉 e3(작성자에게 `can_set_embedded` 부여)는 "게시된 모든 대시보드의 임베드 설정을 모든 작성자가 바꿀 수 있다"는 뜻이다.
- 다른 사람 차트를 자기 대시보드에 넣는 것은 UI 저장 경로로는 된다(확인). 차트 소유자가 모르는 사이에 대시보드 연결이 늘어난다.
- 한계: ① 작성자 UI에서의 실제 차트 만들기 클릭 흐름(Explore 화면 조작)은 시험하지 않았고 API로 확인했다. ② `DashboardAccessFilter` 본문은 읽지 않았다(게시·데이터셋 접근 조합별 가시성은 관찰한 경우만). ③ 작성자 2명, 팀 소속 변경 시 역할 수동 갱신 절차는 시험하지 않았다. ④ SQL Lab 권한이 없는 것은 확인했지만 Explore의 다른 "SQL 표현식" 입력(예: 계산 열 정의)이 서브쿼리 외 방식으로 `bi_data` 밖을 읽는지는 확인하지 못했다(하위 질의는 막힘).

---

## X-21. 대시보드 팀 필터를 URL로 미리 지정할 수 있는가

구성: 데이터셋 2개(`dv_1`: 시간 열 `period_a`, `dv_2`: `base_date`, 둘 다 `team` 열), 표 차트 2개(`x21_chart1`, `x21_chart2`), 대시보드 2개: `x21_dash_nodefault`(팀 선택 네이티브 필터 `NATIVE_FILTER-teamsel1`, 저장 기본값 없음), `x21_dash_default3`(필터 `NATIVE_FILTER-teamsel2`, 저장 기본값 `팀3`). 차트 요청 본문은 `chart/data` POST를 캡처했고, 화면은 필터 칩 텍스트와 스크린샷으로 확인(`x21/*.png`). 아래 "필터 id"는 `FID`.
- 팀 값 3개(`팀1/2/3`) 각 24행 → 필터 없으면 차트 72행(3팀), `팀1`이면 24행.

### (1) 일반 대시보드 URL의 `native_filters`(rison)
| `native_filters` 값 | 필터 칩 | `chart/data` 요청의 팀 필터 | 비고 |
| --- | --- | --- | --- |
| (없음) | `3 options`(비어 있음) | 없음, 72행 | 기준 |
| **A: 필터 id 키 맵 + `extraFormData` + `filterState`** `(FID:(id:FID,extraFormData:(filters:!((col:team,op:IN,val:!(팀1)))),filterState:(value:!(팀1))))` | **팀1** | **두 차트 모두 `team IN ["팀1"]`**, 24행 | 처음 요청부터 필터가 붙음(필터 없는 조회가 먼저 나가지 않음) |
| A2: 값을 따옴표로 `!('팀1')` | 팀1 | 같음 | 단순 한글은 따옴표 유무 무관 |
| **B: `filterState`만** `(FID:(id:FID,filterState:(value:!(팀1))))` | 팀1 | 최종적으로 `team IN ["팀1"]` | **필터 없는 조회(72행)가 먼저 나가고, 필터 컴포넌트가 `extraFormData`를 만든 뒤 다시 조회**(차트 요청 순서 `[1,0],[2,0],[필터옵션],[1,1],[2,1]`) |
| G: `extraFormData`만 | **비어 있음** | 팀1 필터가 붙음 | **화면(칩)과 실제 조회가 어긋남** |
| **C: 단일 마스크** `(id:FID,extraFormData:(...),filterState:(...))` (permalink API docstring 모양) | 비어 있음 | 없음, 72행 | **조용히 무시됨**(오류 표시 없음) |
| D: 대시보드에 없는 id 키 | 비어 있음 | 없음 | 조용히 무시 |
| E: 값 2개 `!(팀1,팀2)` | 팀1 팀2 | `IN ["팀1","팀2"]` | 됨 |
| F: 잘못된 rison(`(FID:(id:` 로 끊김) | 비어 있음 | 없음 | 조용히 무시, 오류 없음 |
| H: `(FID:!(팀1))`(값 배열을 바로) / I: JSON 문자열 | 비어 있음 | 없음 | 조용히 무시 |
| 값에 공백 `영업 1팀`을 **따옴표 없이** | 비어 있음 | 없음(5팀 전체 조회) | 조용히 무시 |
| 같은 값을 따옴표로 `'영업 1팀'` | 영업 1팀 | `IN ["영업 1팀"]`, 6행 | 됨 |
| 특수 문자 `R&D!(x)'s`를 rison 규칙으로 인코딩(`'R&D!!(x)!'s'`) | `R&D!(x)'s` | `IN ["R&D!(x)'s"]` | 됨(인코더가 `!`→`!!`, `'`→`!'`를 지켜야 함) |
- **URL이 바뀌는 점:** 처음 로드한 뒤 주소창은 `?native_filters_key=<키>`로 바뀌고 `native_filters`는 사라진다. 이 키는 (사용자, 대시보드)마다 고정이었다(관찰: 새 세션에서도 같은 키).
- 저장 기본값이 `팀3`인 대시보드에 URL로 `팀1`을 주면 **URL 값이 이긴다**(칩 팀1, 요청 팀1).

### (2) Embedded(guest) 경로 (SDK 0.4.0 번들, guest token은 관리자가 `POST /api/v1/security/guest_token/`로 시험용 발급, 대시보드의 embedded uuid 사용)
| `dashboardUiConfig` | 칩 | 차트 요청 | 비고 |
| --- | --- | --- | --- |
| (없음) | 비어 있음 | 없음, 72행 | iframe 주소 `/embedded/<uuid>?uiConfig=0` |
| `urlParams:{native_filters: A(문자열)}` | 팀1 | `team IN ["팀1"]`, 24행 | SDK가 `URLSearchParams`로 붙인 iframe 주소 `...?uiConfig=0&native_filters=%28FID%3A...` — **iframe 주소에 쿼리를 붙이는 것과 같은 경로**(SDK가 주소를 만드는 방식이라 별도 시험 불필요) |
| `urlParams:{native_filters: B(filterState만)}` | 팀1 | 먼저 72행, 이어서 팀1 재조회 | 일반 대시보드와 같음 |
| `urlParams:{native_filters: C(단일 마스크)}` | 비어 있음 | 없음 | 무시 |
| **`urlParams:{native_filters: {…객체…}}`** (문자열이 아니라 JS 객체) | 비어 있음 | 없음 | iframe 주소가 `native_filters=%5Bobject+Object%5D`가 되어 무시됨: **반드시 rison 문자열로 넘겨야 함** |
| `urlParams:{permalink_key: <맵 형태 permalink>}` | 팀2(permalink에 담은 값) | 팀2 필터 | 됨 |
| `urlParams:{permalink_key: <단일 마스크 permalink>}` | 비어 있음 | 없음 | 무시 |
| 저장 기본값 `팀3` 대시보드, 파라미터 없음 | 팀3 | `team IN ["팀3"]` | 저장 기본값이 적용됨 |
| 같은 대시보드 + `native_filters`로 `팀1` | 팀1 | 팀1 | URL 우선 |
| `filters:{visible:false}` + `native_filters` | 필터 바 숨김(`show_filters=false`) | 두 차트 모두 팀1 필터 적용 | 숨겨도 값은 적용(화면 편의일 뿐 보안 아님) |
| 사용자가 iframe 안에서 `팀2`로 바꿈 | 팀2, 두 차트 팀2 | | |
| 같은 설정으로 다시 마운트(새로고침) | **팀1로 돌아감** | | 사용자 선택은 저장되지 않고 URL 값이 다시 적용 |
| 파라미터 없이 다시 마운트 | 비어 있음 | 72행 | 사용자 선택은 남지 않음 |
| `emitDataMasks:true` + `getDataMask()` | | | 반환 객체에 `FID` 키로 `{id, extraFormData:{filters:[team IN 팀1]}, filterState:{value:[팀1]}}`가 있음(차트 id 키 `1`,`2`도 함께) → 포털이 실제 적용 여부를 읽어 검증할 수 있음 |

### (3) 대시보드 permalink (`POST /api/v1/dashboard/1/permalink`, 본문은 상태 객체 그대로)
| 본문의 `dataMask` 모양 | 열기(`/superset/dashboard/p/<키>/`, `?permalink_key=<키>`) | 결과 |
| --- | --- | --- |
| P1: **필터 id 키 맵** `{FID:{id,extraFormData,filterState}}` | 두 방식 모두 | **팀2 적용**, 차트 팀2 24행, 처음 요청부터 필터 포함 |
| P2: **단일 마스크** `{id,extraFormData,filterState}` (API 문서 예시 모양) | 두 방식 모두 | **무시**(비어 있음, 72행) |
| P3: 맵 + `filterState`만 | 두 방식 모두 | 팀2 적용, 먼저 72행 후 재조회 |
| P4: 맵 + `activeTabs:[]`, `anchor:""` | 두 방식 모두 | 팀2 적용 |
| 응답 | | `201 {key, url}`. `url`은 요청 Host로 만든 절대 주소. 열면 `/superset/dashboard/<대시보드 uuid>/?native_filters_key=…`로 바뀜. `GET /dashboard/permalink/<키>`는 `{dashboardId(uuid), state:{dataMask:{...}}}` |

### (4) 사용자가 필터를 바꾼 뒤
| 시험 | 결과 |
| --- | --- |
| URL로 `팀1` 열기 → 사용자가 `팀2`로 바꾸고 적용 | 칩 팀2, 두 차트 팀2 |
| 같은 탭 새로고침 | **사용자 값(팀2) 유지**(주소의 `native_filters_key`) |
| 파라미터 없는 일반 주소로 다시 열기 | **저장 기본값**(기본값 없는 대시보드는 비어 있음, `팀3` 기본값 대시보드는 팀3). 사용자가 마지막으로 고른 값은 복원되지 않음 |
| 사용자 값이 있는 상태에서 `native_filters=팀3`로 열기 | **URL 값(팀3)이 이김** |
| `Clear all` + 적용 | 기본값이 있어도 필터가 비어 전체 조회(일반 주소를 다시 열기 전까지) |
| 새 세션에서 일반 주소 | 저장 기본값(팀3) |

### 결론
- **T2(`urlParams.native_filters`)와 T4(permalink)는 6.1.0에서 모두 실제로 적용된다**(차트 요청 본문 + 화면). 단 **필터 id를 키로 한 맵 모양만 된다.** `native_filters`/permalink에 단일 마스크(API 문서 예시 모양), 값 배열, 객체(JS 객체를 SDK에 그대로), 따옴표 없는 공백 값, 끊긴 rison은 **오류 없이 조용히 무시**되어 필터가 비어 있는 채 전체 데이터가 보인다.
- 포털이 쓸 값 형태(관찰 사실): `(FID:(id:FID,extraFormData:(filters:!((col:<팀 열>,op:IN,val:!('<팀>')))),filterState:(value:!('<팀>'))))` — 문자열 값은 따옴표로 감싸고 `!`, `'`를 rison 규칙으로 이스케이프. `filterState`만 줘도 되지만 필터 없는 조회가 먼저 나간 뒤 다시 조회된다(데이터는 전원 공개라 노출 문제는 없으나 깜빡임·요청 증가). 필터 id는 대시보드마다 다르므로 매핑 표에 id를 저장해야 한다(이번 시험에서는 id를 직접 정해 만들었고, UI로 만든 필터의 무작위 id를 읽는 것은 `GET /dashboard/{id}`의 `json_metadata.native_filter_configuration[].id`로 가능할 것으로 **추정**(미시험)).
- 적용 확인 수단: Embedded에서는 `emitDataMasks` + `getDataMask()`로 실제 적용 상태를 읽을 수 있다(확인). 일반 화면에서는 `chart/data` 요청 확인뿐이다.
- 사용자가 바꾼 값은 일반 화면에서는 `native_filters_key`로 새로고침 때 유지되지만, 일반 주소로 다시 열면 저장 기본값으로 돌아간다. Embedded는 다시 마운트하면 URL 값이 다시 적용된다. "소속 팀으로 시작하되 사용자가 바꿀 수 있다"는 동작은 URL 방식으로 구현 가능하다.
- 한계: ① 기간(시간) 필터, 다중 필터, 탭이 있는 대시보드는 시험하지 않았다. ② UI에서 만든 필터의 id 읽기는 미시험. ③ `uiConfig`/`hideChartControls` 등 다른 옵션은 보지 않았다. ④ Embedded 시험은 test-only `GUEST_ROLE_NAME=Gamma` 구성이다(최소 권한 guest 역할에서도 같은 결과인지는 미확인). ⑤ SDK 번들은 0.4.0(`facts-superset-r3.md`가 읽은 SDK와 같은 버전 계열)이다.

---

## X-22. 서버(서비스 계정)의 Superset 등록·이름 변경·새로고침 흐름

구성: 역할 `x22_service`, 사용자 `x22_svc`(관리자 아님). 권한 부분집합 128가지(7개 후보 권한의 전체 조합, `can_read SecurityRestApi`는 항상 포함)로 아래 8개 호출을 각각 시험해 요청별 성공 여부를 얻었다(`x22_min_results.json`, `x22_min.py`).

### 요청별 최소 권한 (전체 조합 시험)
후보: A `can_read Dataset`, B `can_write Dataset`, C `can_read Database`, D `schema_access [DB].[catalog].[bi_data]`, E `database_access [DB]`, F `can_read Chart`, G `can_read Dashboard`. 시험 대상 데이터셋은 `x22_svc`가 소유자.

| 호출 | 성공하는 최소 조합 | 부족할 때 |
| --- | --- | --- |
| JWT 로그인 `POST /security/login` | 권한 0개로도 200 | |
| CSRF 토큰 `GET /security/csrf_token/` | **`can_read SecurityRestApi`**(권한 0개일 때 403) | 403 |
| 조회·중복 확인 `GET /dataset/?q=(filters…table_name…)` | **A** | A 없으면 403 |
| `GET /dataset/{id}` | **A + D**(또는 A + E) | A만 있으면 **404**(보이지 않음), A 없으면 403 |
| `GET /dataset/{id}/related_objects` | **A + D**(또는 A + E) | A만 있으면 404 |
| 가상 데이터셋 등록 `POST /dataset/` | **B + D**(또는 B + E) | B만 있으면 **422**, B 없으면 403 |
| 이름 변경 `PUT /dataset/{id}` | **B + D**(또는 B + E) + **소유자** | B만 있으면 404 |
| 열 새로고침 `PUT /dataset/{id}/refresh` | **B + D**(또는 B + E) + **소유자** | B만 있으면 404 |
| 삭제 `DELETE /dataset/{id}` | **B + D**(또는 B + E) + **소유자** | B만 있으면 404 |
| **전체 흐름 최소 집합** | **`can_read Dataset` + `can_write Dataset` + `schema_access [DB].[catalog].[bi_data]` + `can_read SecurityRestApi`(CSRF)** — 4개. `database_access`로 D를 대신할 수 있으나 범위가 더 넓음 | |
- `can_read Database`(C), `can_read Chart`(F), `can_read Dashboard`(G)는 **어떤 호출에도 필요하지 않았다.**
- B+D만 있고 A가 없으면 등록·이름 변경·새로고침·삭제는 되지만 조회·`related_objects`는 403 → **멱등 처리(조회 후 갱신)에는 A도 필요**.
- **소유권:** `x22_svc`가 만든(또는 소유자로 지정된) 데이터셋만 이름 변경·새로고침·삭제 가능. 관리자가 등록한 데이터셋 1번은 `PUT`/`refresh`/`DELETE` 모두 **403**.
- 서비스 계정에 **DB/schema 접근 권한은 필요하다**(D 또는 E). 없으면 등록이 422, 이후 호출은 404.
- 서비스 계정이 못 하는 것(확인): 차트·대시보드·DB·사용자·역할 목록 403, 차트 생성 403, `chart/data` 403, DB 연결 변경·생성 403.
- **schema 권한은 먼저 만들어져 있어야 한다:** `schema_access` 권한 항목은 그 schema에 데이터셋이 처음 만들어질 때(관리자가 `bi_data3`에 첫 데이터셋 생성 → 항목 생성 확인) 또는 `POST /api/v1/database/{id}/sync_permissions/`(관리자, 200) 실행 때 생긴다(새 schema `bi_data2`로 확인: 시험 전 항목 없음, sync 후 생김). 항목이 없으면 서비스 역할에 줄 수 없으므로, 초기화 순서에서 먼저 sync 또는 첫 데이터셋 등록이 필요하다. 데이터셋을 지워도 항목은 남는다.

### (a) 로그인·CSRF·쿠키·만료
| 시험 | 결과 |
| --- | --- |
| JWT 로그인 후 `GET /security/csrf_token/`, 이후 `POST /dataset/` | 201/422(통과). **같은 쿠키 보관소에서 받은 CSRF 토큰과 쿠키를 함께** 보내야 함 |
| CSRF 헤더 없이 POST / 다른 세션의 CSRF 토큰 / 쿠키 보관소를 비운 뒤 토큰만 | **전부 400**(`The CSRF token is missing`) |
| 같은 쿠키 보관소에서 **다시 로그인한 뒤 이전 CSRF 토큰** | 계속 유효(422 응답으로 통과 확인). 토큰은 세션 쿠키에 묶여 있고 재조회해도 같은 값 |
| 접근 토큰 수명 | **900초(15분)**, 갱신 토큰 **2,592,000초(30일)**(JWT 클레임 `iat`·`exp`) |
| 만료된 접근 토큰(시험 인스턴스의 더미 비밀로 서명해 만든 **모사**) | `401 {"msg":"Token has expired"}` |
| 서명이 틀린 토큰 | `422 {"msg":"Signature verification failed"}` |
| `POST /security/refresh`에 갱신 토큰 | 200, 새 `access_token` 반환(새 토큰으로 GET 200, POST는 같은 쿠키 보관소의 CSRF로 통과). 접근 토큰을 넣으면 422 |
- 결론: 서버는 "401이면 갱신 토큰으로 `refresh`(또는 재로그인) 후 재시도", "400 CSRF 오류면 CSRF 재조회 후 재시도"를 두면 된다. 쿠키 보관소(예: `httpx.Client`)를 한 인스턴스로 유지해야 한다. 만료 응답은 모사한 것이고 실제 15분 경과는 기다려 시험하지 않았다.

### (b) 가상 데이터셋 등록과 열 동기화
| 시험 | 결과 |
| --- | --- |
| `x22_svc`가 `POST /dataset/` `table_name="[팀1] 월별 실적"`, schema `bi_data`, `sql="SELECT * FROM bi_data.dv_1 WHERE team = '팀1'"` | **201**. 이름의 대괄호·한글·공백 문제 없음. 소유자 = 서비스 계정 |
| 열 동기화 | 등록 직후 열 4개(`period_a` DATE 시간 열, `team`, `value`, `value2`)가 자동 인식, `main_dttm_col = period_a` |
| `bi_data` schema 접근 사용자(`author1`) | 목록에 바로 나타나고 `GET` 200 |
| 서비스 계정이 SQL이 읽는 표 권한을 **등록 시점에** 검사받는가 | 선언 schema `bi_data`에 SQL `SELECT * FROM public.x20_pub`로 등록 → **422** `You need access to the following tables`. SQL에 표가 없는 `select 1 as a`를 schema `public`으로 등록하는 것은 **201**(표 참조가 없어서) |

### (c) 이름 변경
| 시험 | 결과 |
| --- | --- |
| `PUT /dataset/{id}` `{"table_name":"[팀1] 월별 실적 (개정)"}` | 200 |
| 이 데이터셋 위 차트 | 이름 변경 뒤에도 `chart/data` 200, 대시보드 화면 표시(데이터셋 단위 권한 사용자 화면, `c_rename_dashboard_dsuser_ok.png`) |
| `tables.perm` | `…[[팀1] 월별 실적 (개정)](id:188)`로 **갱신됨** |
| `slices.perm`(차트의 권한 문자열) | **갱신됨**(`…(개정)(id:188)`). `slices.datasource_name`은 이전 이름 `bi_data.[팀1] 월별 실적`**으로 그대로**(표시용 문자열이 낡음) |
| `datasource access` 권한 항목 | **같은 항목 id(425)의 이름이 새 이름으로 바뀜**(새 항목이 생기지 않음). 이름 속 `(id:188)`는 유지 |
| 이 데이터셋에만 접근하도록 만든 역할(`x22_ds_role` = Gamma 권한 + 그 데이터셋의 `datasource_access` 한 개, `schema_access` 없음)의 사용자 | 이름 변경 **전**: `GET dataset` 200, `chart/data` 200, `GET chart` 200, `GET dashboard` 200. 이름 변경 **후**: **모두 200**, 목록에도 보임, 역할이 가진 권한 항목의 이름이 새 이름으로 바뀌어 있음 → **접근 유지**(확인) |
| 이미 있는 이름(`dv_1`)으로 변경 | 422 `Dataset bi_wizard.bi_data.dv_1 already exists` |
| 관리자 소유 데이터셋 이름 변경 | 403 |
- 결론: 이 6.1.0 구성에서 이름 변경은 권한 항목을 **제자리에서 이름만 바꾸므로** 데이터셋 단위 권한과 차트가 유지된다. 이름은 달라져도 `(id:N)`이 같은 데이터셋을 가리킨다. 낡은 문자열은 `slices.datasource_name` 정도다.
- (참고) 처음 만든 시험 차트가 `period` 열을 요구해 "Columns missing" 오류가 난 것은 시험 차트 정의 실수이며 이름 변경과 무관(차트를 고쳐 다시 확인).

### (d) 뷰 열 변경 후 새로고침
시험: 뷰 `bi_data.x22_v`(period, team, value)에 물리 데이터셋과 가상 데이터셋(`SELECT * FROM bi_data.x22_v`)을 등록, 물리 위 표 차트(열 `period, team, value`).
| 시험 | 결과 |
| --- | --- |
| 뷰에 열 `value2` 추가 후 새로고침 **전** | 두 데이터셋 모두 열 3개 그대로 |
| 서비스 계정 `PUT .../refresh` (물리·가상) | 200 `{"message":"OK"}`. 두 데이터셋 모두 `value2`(NUMERIC/DECIMAL) 반영 |
| 뷰를 `DROP`+`CREATE`(한 트랜잭션)로 `value`를 `TEXT`로 바꾸고 `value2` 제거. 새로고침 **전** | 데이터셋 정의는 낡은 상태, `chart/data`는 라이브 SQL이라 `value` 열이 문자열로 조회됨(200). 지표 `SUM(value)`는 `function sum(text) does not exist`로 400 |
| 새로고침 **후** | `value`가 TEXT/STRING으로 **갱신**, `value2`는 데이터셋 열 목록에서 **삭제**. `value2`를 조회하면 400 `Columns missing in dataset: ['value2']` |
| 뷰에서 `value`를 제거하고 새로고침 | 열 목록에서 삭제됨. 이 열을 쓰는 저장된 차트는 `chart/data` 400 `Error: Columns missing in dataset: ['value']`. 대시보드 화면은 열리고 해당 차트만 "Data error"(`d_dashboard_removed_column.png`) |
| 데이터셋 `PUT {"sql": …}`만 보내기 | 열 목록은 **바뀌지 않음**. 이어서 `refresh`를 불러야 열이 바뀜 |
- 결론: 열 추가는 새로고침으로 반영되고 차트는 영향 없다. **열 제거·타입 변경은 새로고침 때 반영되며, 그 열을 쓰는 저장된 차트는 데이터 오류가 된다**(대시보드의 다른 차트는 정상). 새로고침 전에는 정의가 낡아 있다.

### (e) 중복 등록과 멱등 처리
| 시험 | 결과 |
| --- | --- |
| 같은 물리 데이터셋 `x22_v`를 다시 `POST` | **422** `Dataset bi_wizard.bi_data.x22_v already exists` |
| 같은 가상 데이터셋 이름을 다시 `POST` | **422**. 메시지의 이름은 URL 인코딩되어 나옴(`x22%20%EA%B0%80%EC%83%81%20v`) |
| 이름은 다르고 SQL이 같은 가상 데이터셋 | 201(허용) |
| 조회 `GET /dataset/?q=(filters:!((col:table_name,opr:eq,value:'<이름>'),(col:schema,opr:eq,value:bi_data)),columns:!(id,table_name,schema,kind))` | 물리·가상·한글+공백·대괄호 이름 모두 정확히 1건 조회. 없는 이름은 `[]`. 따옴표가 든 이름은 rison 이스케이프(`!'`) 필요 |
| 기존 가상 데이터셋 `PUT {"sql":…}`로 갱신 | 200 (이후 `refresh` 필요) |
| 3개 스레드가 같은 새 이름을 동시에 `POST` | **201 하나, 422 둘**. DB에 1건 |
| 중복 방지 장치 | `tables`에 유일 제약 `UNIQUE (database_id, schema, table_name)`(`_customer_location_uc`) — catalog 열은 제약에 없음 |
- 멱등 처리 방법: ① `GET`(filter)로 있는지 확인 → ② 있으면 `PUT`(필요 시 `sql`·이름) + `refresh`, 없으면 `POST` ③ `POST`가 422(이미 있음)면 ①로 되돌아가 처리(동시 요청 경합도 DB 제약이 막음).

### (f) 서비스 계정과 임베드
| 시험 | 결과 |
| --- | --- |
| `POST`/`PUT`/`GET /dashboard/{id}/embedded` | 전부 **403** (서비스 계정은 임베드를 켜거나 읽을 수 없음) |
| `POST /security/guest_token/` | **403**(별도 권한 `can_grant_guest_token SecurityRestApi` 필요). 그 권한을 서비스 역할에 추가하면 **200** |
- 결론: 서비스 계정으로 임베드 켜기는 불가(Y5 (나)의 "임베드 켜기는 관리자 수동"과 일치). 포털 backend가 guest token을 발급하는 데 같은 계정을 쓰려면 위 권한 1개를 더 주면 되지만 그 계정이 어떤 대시보드든 guest token을 만들 수 있게 된다(추정: 시험은 임베드된 대시보드 하나만 확인).

### 결론 (X-22)
- 서버 서비스 계정은 **관리자 없이** 4개 권한(`can_read Dataset`, `can_write Dataset`, `can_read SecurityRestApi`, `schema_access` on `bi_data`)으로 가상 데이터셋 등록·조회·이름 변경·새로고침·삭제·관련 객체 조회를 모두 한다(확인). 서비스 계정의 소유 범위가 곧 관리 범위다(자기가 만든 데이터셋만 수정·삭제).
- 이름 변경은 권한·차트를 깨지 않는다(확인). 열 제거·타입 변경은 새로고침 후 저장된 차트를 오류로 만든다(확인).
- 한계: ① 접근 토큰 만료는 모사만 했다(실제 15분 경과 미시험, 갱신 토큰 사용은 확인). ② 서비스 계정 비밀번호 로테이션·계정 잠금 동작은 시험하지 않았다. ③ 물리 데이터셋 이름 변경(뷰 이름과 연결)은 시험하지 않았다(가상 데이터셋만). ④ 대량 등록(수십 개) 성능, 서비스 계정 소유자가 사라진 데이터셋을 관리자가 인수하는 절차는 시험하지 않았다. ⑤ `schema_access` 대신 `database_access`를 줬을 때 범위가 더 넓다는 것은 권한 이름으로만 판단했고 다른 schema로 실제 확인하지는 않았다.

---

## X-23. Superset에서 데이터셋·차트를 지웠을 때 남는 것

구성: 데이터셋 → 차트 2개 → 대시보드(레이아웃에 차트 + 그 데이터셋을 대상으로 하는 팀 필터). 모두 `x23_` 접두.

### (a) 차트가 있는 데이터셋 삭제
| 시험 | 결과 |
| --- | --- |
| `DELETE /dataset/{id}` (차트 2개, 대시보드 1개가 사용 중) | **200 `OK`**(막히지 않음) |
| 삭제 전 `related_objects` | 차트 2개, 대시보드 1개 |
| DB(`slices`) | **`datasource_id`가 NULL**이 됨. `datasource_type`은 `table`, `datasource_name`(`bi_data.x23_v1`)과 `perm`/`schema_perm` 문자열은 그대로 남음. `dashboard_slices` 연결도 그대로 |
| 데이터셋·열·`datasource_access` 권한 항목 | 삭제됨(`tables`, `table_columns`, 권한 항목 모두 0건) |
| `GET /chart/{id}` | 200. `datasource_id`, `datasource_name_text`, `datasource_url`이 `null` |
| 차트 목록 | 차트는 계속 나옴(데이터셋 열이 null) |
| `GET /chart/{id}/data/` | 400 `Chart has no query context saved`(이 시험 차트가 저장된 query context 없이 API로 만들어서 데이터셋 삭제와 무관한 응답일 수 있음) |
| 대시보드 화면 | 차트 2개 모두 **로딩 표시(무한 스피너)**, 필터는 **`Network error`**. 요청: `chart/data` 400 `{'datasource': {'id': ['Field may not be null.']}}`, `GET /dataset/NaN/drill_info/` 404(`dashboard/7`). **"[Missing Dataset]" 같은 안내는 대시보드에는 없음**(`a_dashboard_after_dataset_delete.png`) |
| Explore에서 차트 열기 | **"Missing dataset — The dataset linked to this chart may have been deleted. Swap dataset"** 오류가 표시됨(`a_explore_after_dataset_delete.png`) |
| 대시보드 API | `GET /dashboard/{id}` 200, 레이아웃의 차트 id 그대로, 필터 대상 `datasetId`도 그대로(깨진 참조). `/dashboard/{id}/datasets` 결과 `[]` |
| 삭제 전에 영향을 알려 주는가 | 없음(막지도 경고하지도 않음) |

### (b) 차트 삭제 후 대시보드에 남는 것
| 시험 | 결과 |
| --- | --- |
| `DELETE /chart/{id}` (대시보드 레이아웃에 들어 있는 차트) | 200 |
| `dashboard_slices` | 그 차트의 연결은 **삭제됨** |
| 대시보드 `position_json`, `json_metadata.positions` | **차트 노드(`CHART-2`)와 `meta.chartId`가 그대로 남음**. `GET /dashboard/{id}/charts`에는 없음 |
| 대시보드 화면 | 나머지 차트는 정상. 삭제된 자리에 **"There is no chart definition associated with this component, could it have been deleted? Delete this container and save to remove this message."**(`b_dash_after_chart_delete.png`) |

### (c) 대시보드 삭제 후 차트
| 시험 | 결과 |
| --- | --- |
| `DELETE /dashboard/{id}` | 200 |
| 차트 | **남아 있음**(`GET /chart/{id}` 200, `dashboards: []`). 연결(`dashboard_slices`)만 삭제 |
| 화면 | 삭제된 대시보드 주소는 "Page not found" |

### (d) `GET /dataset/{id}/related_objects` 정확도와 필요 권한 (BY7 근거)
시험 데이터셋 하나(`x23_v3`)에 차트 3개(관리자 2개, `author1` 1개), 대시보드 3개(관리자 게시 1, 관리자 미게시 1, **`author1`의 미게시 1**)를 연결하고, 같은 데이터셋을 **네이티브 필터 대상으로만** 쓰는 대시보드 1개(차트 없음)를 따로 만들었다.
| 시험 | 결과 |
| --- | --- |
| DB 정답: 이 데이터셋의 차트 | 3개 |
| `related_objects`의 `charts` | **3개, 이름·id 모두 정확**(소유자·게시 여부와 무관하게 전부) |
| DB 정답: 차트를 통해 이 데이터셋을 쓰는 대시보드 | 3개(게시 1, 미게시 2) |
| `related_objects`의 `dashboards` | **3개**, 항목 키는 `id`, `json_metadata`, `slug`, `title`(`json_metadata` 전체 포함, 한 건당 약 750자) |
| **네이티브 필터 대상으로만 이 데이터셋을 쓰는 대시보드** | **포함되지 않음**(DB 검색으로만 찾아짐) → 삭제 전 영향 표시에 **구멍** |
| 호출자별 결과 | 관리자, `author1`, `author2`가 **모두 같은 3+3개**를 받음 → `author2`도 **`author1`의 미게시 대시보드의 id·제목·메타데이터**를 본다(정보 노출) |
| `uuid`로 호출 | 200 |
| 필요 권한 | 서비스 계정(`x22_svc`) 기준: 권한 없음 403, `can_read SecurityRestApi`만 403, **`can_read Dataset`만 404(그 데이터셋이 보이지 않아서)**, `can_write Dataset`만 403, `can_read Chart`+`Dashboard`만 403, **`can_read Dataset` + `schema_access`(해당 schema) → 200** |
- 결론: 영구 삭제 전 영향 표시(BY7)에 `related_objects`를 쓸 수 있고 **차트 목록은 정확하다**. 단 ① 필터 대상으로만 쓰는 대시보드는 빠지므로 그 정보가 필요하면 대시보드 `json_metadata`를 따로 읽어야 한다(서비스 계정이 `can_read Dashboard`를 더 가져야 하고, 본 서비스 최소 권한 4개에는 없음). ② 포털이 이 응답을 일반 사용자에게 그대로 전달하면 다른 사람의 미게시 대시보드가 노출되므로 서버가 개수·필요한 항목만 가공해야 한다. ③ 응답에는 대시보드마다 `json_metadata` 전체가 실리므로 응답 크기가 커질 수 있다.

### (e) 데이터셋 삭제 전에 `bi_data` 뷰를 `DROP`
| 시험 | 결과 |
| --- | --- |
| 뷰 `DROP` 전 `refresh` | 200 |
| 뷰 `DROP` 후 `PUT /dataset/{id}/refresh` | **422 `Dataset could not be updated.`**(원인 메시지 없음) |
| `GET /dataset/{id}` | 200, 열 정의는 마지막으로 동기화된 상태 그대로 |
| `chart/data` | **400** `Error: relation "bi_data.x23_v4" does not exist LINE 3: FROM bi_data.x23_v4`(SQL 조각 노출) |
| 대시보드 화면 | 차트에 "Data error: relation ... does not exist", 필터는 `Network error`(`e_dashboard_after_view_drop.png`). Explore도 같은 데이터 오류(데이터셋 이름·열 목록은 표시됨) |
| `GET /database/1/table_metadata/?name=...` | 500 |
| `GET /database/1/tables/?force=true` | 목록에서 사라짐 |
| 같은 이름·같은 열로 뷰를 다시 만들고 `refresh` | 200, `chart/data` 200으로 **복구**(데이터셋·차트는 그대로) |
| 뷰가 없는 상태에서 `DELETE /dataset/{id}` | 200(막히지 않음). 이후 차트는 (a)와 같이 `datasource_id` NULL |
- 결론: 뷰를 먼저 지우면 데이터셋은 남지만 차트가 오류가 되고 `refresh`는 원인 없는 422가 된다. 뷰 이름이 같은 뷰를 다시 만들면 복구된다. Superset 쪽 정리와 뷰 삭제의 **순서**(Superset 데이터셋 삭제 → 뷰 `DROP`)가 필요하고, 영향 표시는 (d)의 한계를 안고 해야 한다.

### 결론 (X-23)
- Superset은 **데이터셋을 지울 때 차트·대시보드를 막거나 경고하지 않는다.** 차트는 `datasource_id=NULL`로 남고, 대시보드는 로딩이 끝나지 않는 차트와 "Network error" 필터로 보인다("Missing dataset" 안내는 Explore에만 있다). 차트 삭제는 대시보드 레이아웃에 **"차트 정의 없음" 자리표시**를 남기고, 대시보드 삭제는 차트를 남긴다.
- Y11의 "포털이 Superset 차트·대시보드를 대신 지우지 않음"과 "영구 삭제 전 영향 표시"는 이 동작 때문에 **포털이 영향을 미리 보여 주지 않으면 사용자는 깨진 대시보드를 나중에 발견**한다는 뜻이다.
- 한계: ① 데이터셋 삭제 후 같은 뷰로 새 데이터셋을 만들어도 기존 차트는 자동으로 연결되지 않는다(차트의 `datasource_id`는 NULL로 남음; UI의 "Swap dataset"로 연결하는 흐름은 시험하지 않았다). ② 보고서·알림(Report/Alert), 저장된 쿼리, 태그 등 다른 참조는 시험하지 않았다. ③ 사용자가 접근할 수 없는 데이터셋 위 차트(테스트 중 만들어진 보이지 않는 차트)가 영향 표시에 어떻게 나오는지는 따로 보지 않았다(`related_objects`는 접근 여부와 무관하게 모두 나열).

---

## 부가 확인 (실험 중 우연히 관찰)
- **하위 경로 로고:** Superset 상단 로고 이미지 주소가 `/bi-wizard/superset/bi-wizard/superset/static/assets/images/superset-logo-horiz.png`(접두 이중)로 만들어져 404(`x18c_404.js`). 모든 Superset 화면에서 로고가 깨진 이미지로 보임(기능 영향 없음, Gate ② QA의 "중복 접두" 점검과 관련).
- **Embedded 경로에서 `static/service-worker.js` 404** 콘솔 오류(기능 영향 없음).
- **REST 보안 API(6.1.0):** `/api/v1/security/roles/`, `.../roles/{id}/permissions`(**교체**), `/security/users/`, `/security/permissions-resources/`(최대 100건/쪽), `/security/resources/`(view menu 생성), `/database/{id}/sync_permissions/`가 있다. 사용자 삭제는 그 사용자가 UI에서 대시보드를 연 적이 있으면 `key_value` 외래키 때문에 **422로 실패**(`x22_dsuser` 사례; "삭제 말고 비활성화"가 Superset 안내와 같음, 비활성화한 사용자는 로그인 401) → 계정 삭제 정책(Y12 비활성화만)과 일치.
- **`POST`와 `PUT` 모두 `/dashboard/{id}/embedded`가 임베드 켜기**(둘 다 `can_set_embedded` 필요). `GET`은 `can_get_embedded`.
- **차트 데이터셋 접근 검사 없는 차트 생성:** 03c 관찰과 같이 201이지만, 만든 사람에게도 보이지 않는 차트가 된다.
- **Explore 사용자 정의 SQL:** 6.1.0은 하위 질의를 막는다(`Custom SQL fields cannot contain sub-queries`). 이는 작성자의 `bi_data` 밖 조회 방어에 도움이 된다(우회는 시도하지 않음).
- **가상 데이터셋의 SQL 표 접근 검사는 등록 시점에만**, 읽는 사용자는 선언 schema의 권한으로 읽는다(X-20 (b), X-22 (b)).
- **`superset init`은 Gamma에 더하기만** 한다(권한을 빼지 않음). 사용자 정의 역할은 건드리지 않는다.
- **dashboard `position_json` vs `json_metadata.positions`:** API로 `position_json`만 갱신하면 차트 연결이 안 바뀌고, UI가 보내는 `json_metadata.positions`가 연결을 갱신한다.
- **필터 상태 키:** `native_filters_key`는 (사용자, 대시보드)마다 고정이고, 사용자 값은 그 키에 저장된다(`key_value` 표, 사용자 삭제 시 외래키 충돌의 원인).
- **다른 에이전트의 컨테이너:** 시험 중 같은 Docker 데몬에 `g3x14-pg`(다른 에이전트의 시험 컨테이너)가 잠시 보였고 건드리지 않았다(정리 시점에는 없었음).
- Playwright 헤드리스에서 차단된 iframe이 있는 페이지의 `page.screenshot`이 폰트 대기에서 멈추는 문제가 있어 CDP `Page.captureScreenshot`으로 대체했다.

## 정리 기록
- 시험 중 Superset API로 삭제: 대시보드 17개, 차트 18개, 데이터셋 12개, 사용자 `x20_*`·`x22_svc`(`x22_dsuser`는 삭제 불가라 **비활성화**), 역할 `x20_author_copy`, `x20_author_schema_bi_data`, `x22_service`, `x22_ds_role`. Gamma 권한은 95개로 복구(`cleanup_api.out`).
- 컨테이너·네트워크·볼륨은 **이름을 지정해서만** 삭제: `docker rm -f g3x-frontend-1 g3x-superset-1 g3x-backend-1 g3x-superset-init-1 g3x-migrate-1 g3x-db-bootstrap-1 g3x-postgres-1`, `docker network rm g3x_default`, `docker volume rm g3x_postgres_data`. 이미지는 지우지 않음.
- 시작 전(`r3/cleanup-before.txt`): 컨테이너 없음, 볼륨 `bi-wizard_postgres_data`. 정리 직전(`r3/cleanup-pre.txt`): 컨테이너 7개(`g3x-*`), 볼륨 `bi-wizard_postgres_data`, `g3x_postgres_data`. 정리 후(`r3/cleanup-post.txt`): **컨테이너 없음, 볼륨 `bi-wizard_postgres_data` 하나**, `g3x` 네트워크 없음.
- `bi-wizard_postgres_data`는 건드리지 않았다. 일괄 삭제 명령(`down -v`, `volume prune`, `system prune`, `rm -rf`)은 실행하지 않았다. 권한 거부된 명령은 없었다.

## 스크립트·원출력 안내 (`_workspace/gate3/experiments/r3/`)
- 공통: `r3lib.py`(REST 세션·역할 보조), `x23_lib.py`, `pwlib.js`, `x21lib.js`, `setup_base.py`, `r3_data.sql`, `base_ids.json`, `openapi.json`(6.1.0 OpenAPI)
- X-18: `x18_pw.js`, `x18b_pw.js`(시뮬레이션 시도, 교차 origin에서는 성립하지 않음), `x18c_404.js`, `x18/`(헤더 `headers_anon.txt`, `csp_login.txt`, `x18_results.json`, 스크린샷)
- X-20: `x20_setup.py`, `x20_a.py`(`x20_a.out`, `x20_gamma_perm_names.txt`), `x20_b.py`/`x20_b2.py`(`x20_b.out`, `x20_b2.out`), `x20_c.py`(`x20_c.out`), `x20_ui.js`(`x20_ui.out`, `x20_ui_*.png`), `x20_d.py`(`x20_d.out`), `x20_f.py`(`x20_f.out`)
- X-21: `x21_a.js`, `x21_b.js`, `x21_c_mk.py`/`x21_c.js`, `x21_d.js`(SDK), `x21_e.js`/`x21_e2.js`(공백·특수 문자), `x21/`(결과 JSON, 스크린샷 `01_*`, `b_*`, `c_*`, `d_*`)
- X-22: `x22_setup.py`, `x22_min.py`(`x22_min_results.json`, 128 조합), `x22_flow.py`~`x22_flow4.py`(`.out`), `x22_virt_scope.out`
- X-23: `x23_a.py`, `x23_b.py`/`x23_b2.py`, `x23_c.py`, `x23_ui.js`(`x23_*.out`, `x23/*.png`)
- 정리: `cleanup_api.py`(`cleanup_api.out`), `cleanup-before.txt`, `cleanup-pre.txt`, `cleanup-post.txt`
