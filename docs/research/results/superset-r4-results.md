# 4라운드 Superset 런타임 실험 결과 (X-25 guest 역할 권한, X-28 guest token 발급 방식)

- 승인 범위: 사용자 승인 X-25, X-28 두 건과 담당 명세에 적힌 시험(클라우드 세션 안에서만). 저장소 추적 파일(`docs/`, `CLAUDE.md`, 코드, 설정)은 수정하지 않았다. 산출물은 이 파일과 `_workspace/gate3/experiments/r4/`(스크립트, 원출력 `out/`, 스크린샷 `shots/`)뿐이다(모두 Git 제외).
- 표기: **확인** = 이 환경에서 직접 관찰한 결과. **소스 근거** = Superset 6.1.0 소스(`_workspace/gate3/sources/superset-6.1.0/`, 실행 중인 컨테이너의 `/app/superset`)를 읽은 결과. **추정**은 따로 표시한다.
- 환경: Apache Superset **6.1.0**(`bi-wizard-superset:6.1.0`, 이미지 안 PyJWT 2.10.1, `gunicorn` 워커 1개), PostgreSQL 16.10, compose 프로젝트 `g3x`(더미 값 `_workspace/qa/g3x.env`), 포털 `http://127.0.0.1:25173`, Superset `…/bi-wizard/superset`, Embedded SDK 0.4.0 번들(`_workspace/qa/sdk`), 브라우저 Playwright + Chromium(`/opt/pw-browsers/chromium-1194`). 시험 전용 override: `_workspace/qa/x25-override.yml`과 `_workspace/qa/ss-x25/superset_config.py`(저장소의 `superset/superset_config.py` 복사본 + 시험용 끝부분: `GUEST_ROLE_NAME`, `GUEST_TOKEN_JWT_EXP_SECONDS`, `GUEST_TOKEN_JWT_AUDIENCE`, `GUEST_TOKEN_VALIDATOR_HOOK`을 환경변수·플래그 파일로 바꿀 수 있게 함). 운영 설정이 아니며 이 시험 인스턴스에만 있었다.
- 세션 시작 때 Docker 데몬이 꺼져 있어 `dockerd`를 직접 시작했다(`r4/dockerd-r4.log`). 이미지는 그대로 사용했다(`up -d --no-build`).
- **정리:** 컨테이너 8개(`g3x-frontend-1`, `g3x-backend-1`, `g3x-superset-1`, `g3x-superset-init-1`, `g3x-migrate-1`, `g3x-db-bootstrap-1`, `g3x-postgres-1`, 서명 시험용 `g3x-x28-sign`), 네트워크 `g3x_default`, 볼륨 `g3x_postgres_data`를 **이름을 지정해** 삭제했다. 일괄 삭제(`down -v`, `volume prune`, `system prune`)와 `rm -rf`는 쓰지 않았다(`rm -rf`로 `__pycache__`를 지우려던 명령 1건은 권한 거부되어 실행되지 않았고 우회하지 않았다). 시험 전 볼륨은 `bi-wizard_postgres_data`, `g3x_postgres_data` 두 개였고 종료 후 `bi-wizard_postgres_data` 하나만 남았다(건드리지 않음). 이미지 유지. 컨테이너 0개 남음. 전후 출력: `r4/out/cleanup-pre.txt`, `cleanup-post.txt`, `cleanup-before.txt`. 다른 에이전트의 `g3x26-*`, `g3x27-*` 컨테이너는 건드리지 않았다(시험 중간에 스스로 사라졌다).
- PyJWT는 시험용 컨테이너 `g3x-x28-sign`(backend 이미지, `--network host`로 프록시 경유 pip) 안에만 설치했다(`pip install PyJWT==2.10.1` 성공). 저장소 requirements는 수정하지 않았다.
- 환경 관찰(시험 도구 쪽): (1) 다른 에이전트의 Docker 네트워크 변경 때 Chromium이 진행 중 요청을 `net::ERR_NETWORK_CHANGED`로 끊은 적이 있어, 하네스는 이를 감지하면 그 시도를 버리고 다시 실행한다. (2) 한 화면에서 필터 변경을 연달아 자동 조작하면 Superset UI가 차트를 "Waiting on database…" 상태로 남기는 경합이 재현되어, **조작 단계마다 SDK를 새로 마운트**(isolate)해 시험했다. 이는 권한 판정과 무관하며(권한 부족은 항상 403으로 결정적으로 재현됨) 시험 방법의 한계다.

---

# X-25. guest 역할 권한 이분 탐색 + 부정 시험 + 하위 경로 재검증

## 25-0. 준비와 성공 판정 기준
| 항목 | 내용 |
| --- | --- |
| 데이터 | `bi_data.x25_sales`(216행 = 3팀 × 3상품 × 24개월, 열: 기간·팀·상품·금액·수량), 뷰 `bi_data.dv_x25`. 데이터셋 1(물리 뷰), 2(가상: `SELECT * FROM bi_data.dv_x25`) |
| 대시보드 A(id 1, 임베드 켬) | 탭 2개. 탭1: 표, 막대, 선(+주석 레이어 2종: 저장된 이벤트 레이어와 수식 `y=1000`), 큰 숫자, 파이, 피벗 표 + 마크다운. 탭2: 가상 데이터셋 표, 큰 숫자 추세. 네이티브 필터 3종(팀 값 선택 `filter_select`, 기간 `filter_time`, 금액 `filter_range`), 교차 필터 켬, CSS 문자열 있음 |
| 보조 | 대시보드 B(id 2, 임베드 켬), C(id 3, 임베드 안 켬), 차트 B 전용·C 전용, 삭제·수정 시험용 미끼 차트·대시보드·데이터셋, 차트 종류 점검용 대시보드 E(id 5, 21종) |
| 역할 | 시험 전용 `x25_guest`(역할 REST로 만들고 권한 부여), `GUEST_ROLE_NAME=x25_guest` override. `Public`은 권한 0개(확인), `PUBLIC_ROLE_LIKE` 미설정 |
| 후보 21개와 소스 | `round4-options.md` G-2의 21개는 `superset/security/manager.py`의 `PUBLIC_ROLE_PERMISSIONS`와 **정확히 일치**(소스 근거, 코드로 비교). 그러나 그중 `can_read AnnotationLayerRestApi`는 **DB에 권한 항목(PVM)이 존재하지 않는다**: `AnnotationLayerRestApi.class_permission_name = "Annotation"`(소스 근거, 컨테이너 `/app/superset/annotation_layers/api.py:63`). 그래서 실제로 부여할 수 있는 후보는 **20개**다(`can_read Annotation` 하나로 합쳐져 있음, 확인: PVM 목록 231개 중 `Annotation`은 `can_read`, `can_write`, `menu_access Annotation Layers`) |
| 성공 판정 기준(단계마다 적용) | ① Embedded SDK 페이지(포털과 같은 origin)에서 iframe이 마운트되고 탭1의 차트 6개가 **오류·로딩 상태 없이** 그려진다. ② 차트 데이터 요청(`POST /api/v1/chart/data`)이 **전부 200**이고 응답이 있다. ③ Superset 쪽 4xx/5xx가 0건(알려진 비기능 `static/service-worker.js` 404와 로고 이미지 제외). ④ 브라우저 콘솔 오류 0건(위 알려진 항목 제외). ⑤ 단계별로 **서버가 받은 요청**을 확인: 탭2 이동(차트 2개 200), 팀 필터(모든 차트 요청에 `team IN ["팀3"]`), 기간 필터 `2024-06-01 : 2025-01-01`(요청 `time_range`와 응답 `from_dttm`/`to_dttm`이 일치), 금액 필터(`amount >= , <=`), 교차 필터(파이 조각 클릭 → 다른 차트 요청에 `product IN`), 상대 기간 `Last week`(시간 범위 API 200과 응답 창), `getDataMask()` 읽기 |

## 25-1. 기준선(20개 권한 전부 부여)
| 시험 | 결과 |
| --- | --- |
| 위 판정 기준 전체 | **통과**(`out/base20_full.json`, 스크린샷 `shots/base20_full*.png`). 4xx 0건, 콘솔 오류 0건, 차트 요청 전부 200 |
| Gate ②에서 "차트가 있었는지 불명"이던 부분 | 차트 6종 + 탭 + 필터 3종 + 교차 필터가 실제로 `guest` 역할(Gamma 아님)로 동작함을 **확인** |

## 25-2. 이분 탐색 (단일 제거 20회 + 일괄 제거 + 차트 종류 확장)
방법: 20개에서 **하나씩 빼고** 핵심 시나리오(탭2, 팀, 기간, 금액, 교차 필터를 각각 새 마운트로)를 실행했다(`r4/bis.py`, 원출력 `out/bisect/`, `out/bisect_single*.log`). 권한 변경은 역할 REST `POST /api/v1/security/roles/{id}/permissions`(목록 통째 교체)로 했다.
| # | 제거한 권한 | 결과 | 판정과 증거 |
| --- | --- | --- | --- |
| 00 | `can_read CurrentUserRestApi` | 실패 | **필수.** `GET /api/v1/me/roles/` 403 → 대시보드·차트 요청이 하나도 나가지 않고 iframe이 빈 화면 |
| 01 | `can_read Dashboard` | 실패 | **필수.** `GET /api/v1/dashboard/1`, `/1/charts`, `/1/datasets` 403 → 차트 0개 |
| 02 | `can_read Chart` | 실패 | **필수.** 차트 6개 모두 "Data error Forbidden"(차트 데이터·`GET /api/v1/chart/{id}?q=` 403) |
| 03 | `can_dashboard Superset` | 통과 | 불필요(레거시 `/superset/dashboard/<id>/` 뷰용, 소스 근거 `views/core.py`) |
| 04 | `can_slice Superset` | 통과 | 불필요(레거시 `/superset/slice/<id>/` 뷰) |
| 05 | `can_explore_json Superset` | 통과 | 핵심 6종 차트에는 불필요. **레거시 차트 유형에는 필요**(아래 "차트 종류 확장") → 조건부 |
| 06 | `can_dashboard_permalink Superset` | 통과 | 불필요(레거시 `/superset/dashboard/p/<key>/` 뷰 URL용). `permalink_key`로 여는 경로는 다음 행의 권한만 필요(25-5) |
| 07 | `can_read DashboardPermalinkRestApi` | 통과(핵심 시나리오) | 핵심 시나리오에는 불필요. **permalink로 필터 상태를 복원하려면 필요**(25-5: 없으면 `GET /api/v1/dashboard/permalink/<key>` 403, 대시보드는 열리나 필터 미적용) → 조건부 |
| 08 | `can_read DashboardFilterStateRestApi` | 통과 | 불필요 |
| 09 | `can_write DashboardFilterStateRestApi` | 통과 | 불필요(필터 변경과 교차 필터가 서버 쓰기 없이 동작) |
| 10 | `can_time_range Api` | 기간 단계만 실패 | **기간(시간 범위) 필터가 있는 대시보드에서 필수.** `GET /api/v1/time_range/?q=…` 403 → 필터 팝업의 "APPLY"가 비활성이라 범위를 적용할 수 없음. 로드·팀·금액·교차 필터는 정상 |
| 11 | `can_query_form_data Api` | 통과 | 불필요 |
| 12 | `can_query Api` | 통과 | 불필요 |
| 13 | `can_read CssTemplate` | 통과 | 불필요(대시보드 CSS는 대시보드 응답에 들어 있음, CSS 문자열이 있는 대시보드로 확인) |
| 14 | `can_read Theme` | 통과 | 불필요 |
| 15 | `can_read EmbeddedDashboard` | 통과 | 불필요 |
| 16 | `can_get Datasource` | 통과 | 불필요 |
| 17 | `can_external_metadata Datasource` | 통과 | 불필요 |
| 18 | `can_read Annotation` | 통과 | 불필요. 저장된 주석 레이어가 있는 선 차트도 주석 데이터가 `chart/data` 응답의 `annotation_data`로 내려옴을 **확인**(이 권한 없이) |
| 19 | `can_read ExplorePermalinkRestApi` | 통과 | 불필요 |
- 단일 제거에서 필수는 3개(00~02) + 기간 필터용 1개(10). 통과한 16개를 **한꺼번에** 뺀 `{CurrentUserRestApi 읽기, Dashboard 읽기, Chart 읽기, Api.can_time_range}` **4개**로 시나리오 전체(탭2, 팀, 기간(절대), 금액, 교차, 기간(상대 `Last week`), `getDataMask`)를 다시 **통과**(`out/bisect/min4_full.json`). 둘 중 하나만 필요한 조합은 발견되지 않았다(16개 일괄 제거가 통과했으므로 상호 보완 관계 없음).
- **Superset 재시작 필요 여부:** 역할 권한 변경은 **재시작 없이 다음 요청부터 반영**(확인: 권한을 빼자마자 같은 인스턴스에서 403, 다시 넣자 복구). 단 `GUEST_ROLE_NAME` 같은 설정 변경은 재시작이 필요하다(설정 파일). 이는 워커 1개(compose `SERVER_WORKER_AMOUNT=1`) 구성의 관찰이며 다중 워커·캐시 구성은 확인하지 못했다.

### 차트 종류 확장 (대시보드 E, 21종, 관리자 화면과 비교)
방법: 같은 대시보드를 관리자 화면과 guest(4개 권한)로 열어 차트마다 상태·`chart/data` 응답 코드를 비교했다(`r4/sweep.js`, `out/sweep_*.json`).
| 결과 | 차트 유형 |
| --- | --- |
| 관리자와 guest(4개) **동일하게 렌더** | 면적, 산점, 계단, 부드러운 선, 박스 플롯, 히스토그램, 히트맵, 트리맵, 선버스트, 게이지, 깔때기, 레이더, 버블, 혼합 시계열, 큰 숫자(추세), 표(기간 비교), 피벗 |
| guest(4개)에서만 **403** | `rose`(레거시 유형). 요청 `POST /superset/explore_json/?form_data=…` 403 "Access is Denied"(`can_explore_json Superset` 없음) → 그 권한을 더하면 관리자와 같이 렌더(확인) |
| 관리자도 실패(내 시험 설정 오류, 권한 무관) | `time_table`, `cal_heatmap`(필수 파라미터 오류 400), `handlebars`(템플릿 구문 오류) |
- 결론: **새 방식 차트는 `chart/data`만 쓰므로 4개로 충분**하고, 레거시 `explore_json` 경로를 쓰는 유형(`rose` 확인, 그 밖에 소스상 같은 경로를 쓰는 유형은 시험하지 않음)은 `can_explore_json Superset`이 추가로 필요하다. 사용할 차트 종류 목록이 정해져야 이 권한을 넣을지 판단할 수 있다.
- 시험하지 않은 유형: 지도·deck.gl 계열(외부 지도 토큰 필요), 워드클라우드, 생키, 선버스트 외 계층형 일부, 파라미터 오류로 판정하지 못한 위 3종.

### 최소 집합(결론)
| 구분 | 권한(PVM) |
| --- | --- |
| **필수 3개** | `can_read CurrentUserRestApi`, `can_read Dashboard`, `can_read Chart` |
| **기간 필터를 쓰면 필수 +1** | `can_time_range Api` |
| 조건부(시험으로 필요 확인) | `can_explore_json Superset`(레거시 차트 유형), `can_read DashboardPermalinkRestApi`(permalink로 필터 복원) |
| **불필요 확인(14개)** | `can_dashboard`, `can_slice`, `can_dashboard_permalink`(Superset), `DashboardFilterStateRestApi` 읽기·쓰기, `Api.can_query_form_data`, `Api.can_query`, `CssTemplate`·`Theme`·`EmbeddedDashboard`·`Annotation` 읽기, `Datasource.can_get`, `Datasource.can_external_metadata`, `ExplorePermalinkRestApi` 읽기 (+ DB에 없는 `AnnotationLayerRestApi` 읽기) |
- 처음 시나리오 전체를 최소 집합으로 다시 통과함을 **확인**했다(25-1과 같은 기준). 권한 4개 + 조건부 2개를 모두 준 6개 구성도 부정 시험 결과는 4개 구성과 거의 같다(25-3).

## 25-3. 부정 시험 (최소 4개 구성, 유효 guest token 대시보드 A, SDK와 같은 방식)
방법: 파이썬 클라이언트가 SDK와 같이 `/embedded/<uuid>`를 열어 세션 쿠키와 CSRF 값(HTML의 `csrf_token` 입력)을 받고 `X-GuestToken`+`X-CSRFToken`+쿠키로 호출했다(`r4/gs.py`, `x25_neg.py`, 원출력 `out/neg_min4.json`, 137건). `chart/data`는 **SDK가 실제로 보낸 본문을 그대로 재생**(`out/chart_bodies.json`)해야 의미가 있다(임의 본문은 데이터셋 접근 검사에서 막혀 시험이 무의미해진다는 것을 첫 시도에서 확인).
| 시험 | 요청 | 결과 |
| --- | --- | --- |
| 허용 기준(비교용) | 대시보드 A GET, `/charts`, `/me/roles/`, 차트 1 데이터 재생 | 200 |
| 데이터셋 목록·읽기 | `GET /api/v1/dataset/`, `/dataset/1`, `/dataset/1/related_objects`, `/dataset/distinct/team`, `/dataset/export/` | **403** |
| 데이터베이스 | `GET /api/v1/database/`, `/database/1` | **403** |
| 차트 목록·읽기 | `GET /api/v1/chart/` | 200이지만 **0건**. `GET /chart/1`은 404 |
| 대시보드 목록 | `GET /api/v1/dashboard/` | 200, **토큰의 대시보드 1건만**(id 1) |
| 차트 생성·수정·삭제 | `POST /chart/`, `PUT /chart/11`, `DELETE /chart/11` | **403** |
| 대시보드 생성·수정·삭제 | `POST /dashboard/`, `PUT /dashboard/1`(css), `PUT /dashboard/4`, `DELETE /dashboard/4`, `PUT /dashboard/1/colors` | **403** |
| 데이터셋 생성·수정·삭제 | `POST /dataset/`, `PUT /dataset/3`, `DELETE /dataset/3` | **403** |
| 임베드 설정 | `POST`/`DELETE /dashboard/1/embedded` | **403** |
| 임베드 설정 읽기 | `GET /dashboard/1/embedded` | **200**(`can_read Dashboard`로 가능). 내용: `uuid`, `allowed_domains`, 마지막 변경자(이름·**사용자명 `admin`**) 노출 |
| 사용자 정보 | `GET /api/v1/me/` | 200(이름만), `/me/roles/` 200 |
| CSRF 토큰·보안 API | `GET /security/csrf_token/`, `/security/roles/search/`, `/security/users/`, `/api/v1/menu/`, `POST /security/guest_token/` | 전부 **403** |
| SQL Lab | `POST /api/v1/sqllab/execute/`, `GET /api/v1/sqllab/`, `/saved_query/`, `/query/`, `POST /database/1/validate_sql/`, `/sqllab/format_sql/` | 전부 **403** |
| SQL Lab·목록 화면(HTML) | `GET /sqllab/`, `/tablemodelview/list/`, `/superset/sqllab/` | 로그인으로 **302**(또는 404) |
| Explore | `GET /explore/?slice_id=1`, `/superset/explore/` | 로그인으로 **302** |
| Explore API·퍼머링크 | `GET /api/v1/explore/?slice_id=1`, `POST /api/v1/explore/permalink`, `GET /superset/explore_json/` | **403** |
| **CSV·XLSX 내보내기** | `chart/data`에 `result_format=csv`/`xlsx`(`result_type=full`/`results`) | **403** `{"message":"Forbidden"}`. `can_csv Superset`을 더하면 **200**(`text/csv`, xlsx)으로 바뀜(확인). `can_export Chart`/`can_export Dashboard`만 주면 여전히 403 |
| 그 밖의 내보내기 | `GET /chart/export/`, `/dashboard/export/`, `/dataset/export/`, `GET /chart/1/data/?format=csv` | 403 또는 404 |
| 이미지·썸네일 서버 엔드포인트 | `/chart/1/screenshot/…`, `/dashboard/1/screenshot/…`, `cache_dashboard_screenshot`, `thumbnail`, `/superset/csv/…` | **404**(기능 플래그 꺼짐, 권한 이름 `can_screenshot`는 6.1.0에 없음. 있는 것은 `can_cache_dashboard_screenshot Dashboard`) |
| 화면의 내보내기 메뉴 | 차트 ⋮ 메뉴 | **"Force refresh"와 "Enter fullscreen" 두 항목뿐**(Download·View query·Share·Edit 없음). 대시보드 "…" 메뉴: "Refresh dashboard", "Set auto-refresh", "Download"(Export to PDF, Download as Image, Export YAML) |
| 대시보드 메뉴 항목 실행 | Export to PDF, Download as Image | **파일이 내려받아짐**(브라우저 안에서만 만들어져 서버 요청 없음). Export YAML은 `GET /dashboard/export/?q=!(1)` **403**(다운로드 없음). SDK `hideTitle:true`는 헤더·메뉴를 숨기지만 UI 숨김일 뿐 서버 차단이 아니다 |
| 데이터 조회 결과 형식 | 재생 본문에 `result_type`=`query` | 200이지만 `{"language":"sql"}`만(**SQL 문장 숨김**) |
| | `samples`, `results`, `columns`, `timegrains`, `drill_detail`, `force=true` | 전부 **200**(`samples`는 원시 행) |
| 다른 대시보드 | 토큰 A로 `GET /dashboard/2`, `/dashboard/{B의 임베드 uuid}`, `/dashboard/3`, `/2/charts`, `/2/datasets` | 전부 **404** |
| 다른 대시보드 데이터 | 토큰 A로 본문 `dashboardId=2`(B) 또는 3(임베드 안 한 C)의 `chart/data` | **403**. 토큰 B로 `dashboardId=2`는 200, `dashboardId=1`은 403(확인) |
| B 전용·C 전용 차트 | 토큰 A로 차트 9(B 전용), 10(C 전용) 본문 | **403** |
| 데이터셋 접근 | 슬라이스 없이 데이터셋 2·3 직접 질의, 재생 본문의 `datasource.id`를 3으로 변경 | **403** |
| 퍼머링크·필터 상태 | `POST /dashboard/1/permalink`, `GET /dashboard/permalink/<key>`, `POST /dashboard/1/filter_state` | **403**(`can_read DashboardPermalinkRestApi`만 더하면 GET은 200, 생성은 계속 403) |
| 토큰 없음 | 토큰 없이 `GET /dashboard/1`, `chart/data`, `/me/roles/` | **401** |
| | `/superset/dashboard/1/` | **302** 로그인 |
| | `/embedded/<유효 uuid>` | **200**(HTML 틀만. 데이터는 토큰이 있어야 나옴), 없는 uuid는 404 |
| 만료·변조 | 만료된 토큰, 페이로드 변조(자원을 B로) 서명 유지, 서명 변조, `alg=none`, 틀린 비밀값, 틀린 `aud`, 쓰레기 문자열, 빈 헤더 | 전부 **401** |
| `Public` 역할 | 권한 개수(역할 REST) | **0개**(확인). 익명 접근은 위 "토큰 없음" 결과와 같다 |
- 6개 구성(4개 + `can_explore_json` + `can_read DashboardPermalinkRestApi`)과의 차이는 2건뿐: `GET /dashboard/permalink/<key>` 403 → 200, `GET /superset/explore_json/…` 403 → 500(`{"error":"'table'"}`, 본문 없이 호출해서 생긴 서버 오류, 접근 자체는 통과)(`out/neg_min6.json`).

### 부정 시험 중 발견한 성질 (결정에 영향 가능, 모두 확인)
1. **토큰 대시보드에 속한 차트의 데이터셋은 호출자가 질의를 바꿔 마음대로 조회할 수 있다.** 재생 본문의 `columns`, `metrics`, `filters`, `row_limit`, `extras.where`를 바꿔도 200이다. 저장된 차트에 없는 열(`qty`, `amount2`)을 원시로 읽고(행 5000개 한도 내), 임의 SQL 식(서브쿼리·세미콜론은 막힘 400/403: `Custom SQL fields cannot contain sub-queries`, `Invalid SQL clause`)을 열·지표로 넣을 수 있으며 `current_user`는 `bi_readonly`, `version()`이 반환되었다. 같은 차트를 UI에서 저장한 것처럼 `query_context`를 저장해도 변조 검사가 막지 않았다(`query_context_modified`는 이 경로에서 효과가 없었다: 소스 근거 `security/manager.py:200-250`, 이 시험에서는 슬라이스 객체가 없을 때 검사가 건너뛰어지는 것으로 **추정**). 방어선은 **데이터셋 단위**(슬라이스·대시보드가 토큰 범위 밖이면 403, 위 표)와 **DB 계정 권한**(`bi_readonly`)이다. 3라운드 불변식 "Superset에 등록된 데이터는 모두 공개"와 일치하지만, **열 단위 숨김은 guest 역할로는 불가능**하다(뷰에서 열을 빼야 한다).
2. **DB 부하:** 열 식에 `pg_sleep(0.05)`를 넣은 한 요청이 216행을 도느라 **11초**가 걸렸고, `pg_sleep(2)`는 클라이언트가 30~60초에 포기한 뒤에도 **DB 세션이 수 분 동안 계속 실행**되었다(시험 DB에서 `pg_terminate_backend`로 종료함). `force=true`로 캐시를 우회할 수 있다. guest 쪽 권한으로는 막을 수 없고 `bi_readonly`에 대한 DB 측 `statement_timeout` 같은 제한이 방어선이다(**추정**: 적용 방법과 값은 시험하지 않음).
3. **토큰의 `resources.id`가 숫자(대시보드 id)이면 임베드를 켜지 않은 대시보드도 API로 읽힌다**(28-4 참조).
4. 다운로드 메뉴의 PDF·이미지 내보내기는 서버가 막을 수 없다(클라이언트 렌더링). "내보내기 허용 안 함"은 서버 쪽 CSV/XLSX/YAML 차단과 UI 숨김의 조합으로만 구현된다.

## 25-4. 하위 경로 재검증
| 시험 | 결과 |
| --- | --- |
| `APP_PROXY_STRIP_PREFIX=false`(기본) | 25-1~25-3 전부 위 결과(기준선) |
| `APP_PROXY_STRIP_PREFIX=true` | frontend와 backend 컨테이너만 `true`로 다시 만들고(로그 `접두 제거 전달=true`, 컨테이너 env 확인) 같은 시나리오 전체(탭2, 팀, 기간, 금액, 교차, 상대 기간, `getDataMask`)를 **통과**, 부정 시험 137건의 상태 코드가 `false`와 **전부 동일**(`out/strip_true_full.json`, `out/neg_strip_true.json`). 이유: nginx 템플릿에서 Superset 경로는 접두를 항상 유지한 채 전달하고 `STRIP`은 포털 API 경로에만 적용된다(소스 근거 `frontend/nginx/templates/default.conf.template`). 시험 후 `false`로 되돌림 |
| `allowed_domains`(대시보드 임베드 설정) | 빈 값: 열림. 포털 origin(`http://127.0.0.1:25173`, 끝 `/` 있어도): 열림. 다른 origin(`http://evil.example`) 또는 `http://localhost:25173`: `GET /embedded/<uuid>` **403**으로 막힘(iframe 빈 화면). 이 검사는 HTML 문서 요청에만 있고 API(`/api/v1/…`)에는 없다 |
| 역할이 없을 때(`GUEST_ROLE_NAME`이 존재하지 않는 역할) | iframe 빈 화면, guest 토큰으로 한 **모든 API가 500** `'NoneType' object has no attribute 'name'`(서버 로그 `AttributeError`). 이전 소스 판독(역할 부재 → `AttributeError`)과 일치 |

## 25-5. X-21 후속 (최소 권한 guest 역할로 `native_filters`와 permalink)
방법: `urlParams`(SDK)로 `native_filters`(필터 id를 키로 한 rison 맵)를 주고 `emitDataMasks`로 상태를 읽었다(`r4/x25_native.js`, `out/native_*.json`). 최소 4개 구성.
| 시험 | 결과 |
| --- | --- |
| 팀 필터 맵 `{NATIVE_FILTER-team: …팀2}` | **적용됨**: 6개 차트 요청 전부 `team IN ["팀2"]`, `getDataMask()`에 반영 |
| 기간 필터 맵(`extraFormData.time_range = 2024-06-01 : 2025-01-01`) | **적용됨**: 요청 `time_range`와 응답 `from_dttm`/`to_dttm`이 `2024-06-01 ~ 2025-01-01` |
| 금액 범위 필터 맵(`amount >= 200`, `<= 400`) | **적용됨** |
| 세 필터 동시 | **전부 적용됨** |
| 단일 마스크 모양(필터 id 키 없음, 3라운드에서 조용히 무시된 모양) | **무시됨**(필터 없는 전체 조회, 오류 없음) — X-21 결과와 같음 |
| permalink(`permalink_key`), 최소 4개 구성 | `GET /api/v1/dashboard/permalink/<key>` **403** → 대시보드는 열리나 **필터가 적용되지 않음**(차트가 전체 데이터) |
| permalink + `can_read DashboardPermalinkRestApi` 1개 추가 | **적용됨**(팀2 + 기간). `can_dashboard_permalink Superset`은 필요 없음 |
- 결론: `native_filters` URL 파라미터 경로(Z14 (나))는 **추가 권한 없이** 최소 4개로 동작한다(팀·기간·금액 필터 모두). permalink 경로(Z14 (다))는 `can_read DashboardPermalinkRestApi` 1개가 추가로 필요하다. guest가 permalink를 **만드는** 것은 `can_write`가 없어 403(필요하면 서버(관리자 권한)가 만들어야 함).
- 한계: 필터 id는 시험용으로 직접 지정했다(UI로 만든 필터 id 읽기 방법은 시험하지 않음). permalink는 관리자 API로 생성했다.

## 25-6. Gamma 대조와 비교
같은 인스턴스를 `GUEST_ROLE_NAME=Gamma`로 다시 만들어 같은 시나리오와 같은 부정 시험을 돌렸다(`out/gamma_full.json`, `out/neg_gamma.json`, 파괴적 3건 제외).
| 항목 | 최소 4개 | Gamma(95개) |
| --- | --- | --- |
| 기준 시나리오(탭2, 팀, 기간, 금액, 교차, 상대 기간) | 통과 | **통과(같은 결과)** |
| 차트 종류 확장 | 새 방식 전부 동일, 레거시는 `can_explore_json` 필요 | 동일 |
| CSV·XLSX 내보내기 | **403** | **200**(`text/csv`, xlsx 내려옴) |
| 데이터셋·DB 목록, `/api/v1/menu/`, `csrf_token` | 403 | 200(목록은 빈 값, 메뉴·CSRF는 반환) |
| permalink·필터 상태 생성 | 403 | **201**(생성됨) |
| `/explore/?slice_id=1`, `/tablemodelview/list/` | 302 로그인 | 200 화면 |
| 차트 ⋮ 메뉴 | Force refresh, Enter fullscreen | + Edit chart, View query, View as table, Share, Download |
| 대시보드 메뉴 | Refresh, Set auto-refresh, Download | + Save as, Share |
| 차트 생성 `POST /chart/` | 403 | 500(생성 실패) |
- 권한 차이 목록: 최소 4개와 조건부 2개(`can_explore_json Superset`, `can_read DashboardPermalinkRestApi`)는 모두 Gamma에 **포함**된다. 20개 후보 중 Gamma에 **없는** 것은 `can_read Annotation` 하나(그러나 불필요)이다. Gamma에만 있는 권한은 91개(원본 목록 `out/gamma_vs_min4_perms.json`)이며 대표적으로 `can_csv Superset`, `can_export Chart/Dashboard/Theme`, `can_write Chart/Dashboard/DashboardFilterStateRestApi/DashboardPermalinkRestApi/ExplorePermalinkRestApi/ExploreFormDataRestApi/Tag/Theme`, `can_get MenuApi/OpenApi`이다.
- 결론: Gate ②의 "Gamma 대조 성공"과 이번 최소 4개 구성의 **기능 결과는 같다**(화면에 필요한 것은 4개뿐). 차이는 전부 "guest가 할 수 있어서는 안 되는 것"(내보내기, 생성, 메뉴)이며 최소 구성에서 막힌다.

## X-25 결론
- 최소 집합: 필수 `can_read CurrentUserRestApi`, `can_read Dashboard`, `can_read Chart`(3개), 기간 필터 사용 시 `can_time_range Api`(+1), 조건부 `can_explore_json Superset`(레거시 차트 유형), `can_read DashboardPermalinkRestApi`(permalink로 필터 복원). 후보 21개 중 14개는 불필요, 1개는 DB에 존재하지 않는 이름(실재 20개 = 필수 3 + 기간 1 + 조건부 2 + 불필요 14).
- 최소 구성에서 목록·생성·수정·삭제·SQL Lab·Explore·CSV/XLSX/YAML 내보내기·다른 대시보드·만료/변조 토큰이 모두 막힘을 확인했다. 막히지 않는 것: 토큰 대시보드의 데이터셋에 대한 임의 질의(열 제한 불가, DB 부하 가능), 클라이언트측 PDF·이미지 내보내기, 임베드 설정 읽기.
- 권한 변경은 Superset 재시작 없이 즉시 반영되고, `GUEST_ROLE_NAME` 변경과 역할 부재는 재시작·서버 오류로 이어진다.
- STRIP true/false 결과 동일, `allowed_domains`는 HTML 문서에만 적용.

## X-25 한계(못 한 시험)
- HTTP만 시험했다(HTTPS에서의 `Secure` 쿠키, `SameSite`, CSRF Referer 엄격 검사는 미확인).
- 차트 유형은 21종 중 일부(위)이며 지도·deck.gl·워드클라우드는 하지 않았다. 차트·대시보드를 API로 만들었기에 UI 저장 산출물(`query_context` 등)과 다를 수 있다.
- 워커 1개 인스턴스에서만 확인했다. 브라우저는 Chromium 1종이다.
- Gamma 대조의 부정 시험은 임베드 설정·대시보드 CSS 변경 3건을 제외했다.
- `Datasource`/`Annotation` 등 "불필요" 판정은 이번 대시보드 구성과 차트 종류 기준이다(해당 기능을 쓰는 화면 요소가 추가되면 재시험 필요).

---

# X-28. guest token 발급 방식 비교

## 28-1. 발급 전용 계정(Z3 ㄱ): `x28_issuer` + `x28_issuer_role`
방법: 역할 REST로 역할·사용자를 만들고(`r4/x28_setup.py`), 이 계정으로 `POST /security/login`(JWT) → `GET /security/csrf_token/` → `POST /security/guest_token/`(`r4/x28_a.py`, `out/x28_a.json`).
| 시험 | 결과 |
| --- | --- |
| ① 정상(권한 `can_grant_guest_token SecurityRestApi` + `can_read SecurityRestApi`) | **200**, 응답 `{"token": "<jwt>"}` 하나(키는 `token`뿐). 토큰 클레임: `user`, `resources`, `rls_rules`(요청의 `rls`가 이 이름으로 들어감), `iat`, `exp`(= `iat` + 300), `aud`(= `http://0.0.0.0:8080/`), `type: "guest"` |
| ② CSRF 생략 | 세션·헤더 모두 없음: **400** `The CSRF token is missing`. 쿠키만 있고 헤더 없음: 400 같은 문구. 다른 세션의 토큰을 헤더로: **400** `The CSRF tokens do not match`. 헤더는 맞는데 쿠키 없음: **400** `The CSRF session token is missing`. 같은 세션의 CSRF 토큰은 여러 번(3회) 재사용 가능 |
| `Referer` 헤더(HTTP) | 없어도, 다른 origin이어도 **200**(HTTP에서는 검사 안 함. HTTPS에서의 엄격 검사는 미확인) |
| ③ `user` 생략 | **500** `{"message":"Fatal error"}`(소스 근거: `api.py`가 `body["user"]`를 직접 읽음). `user: {}`는 200(토큰 `user`가 빈 객체, 사용 시 이름은 기본값 `guest_user`), `user: null`은 400 `Field may not be null`, `{"username":"only"}` 200 |
| ④ `resources.id` | 임베드 uuid: 200. 숫자 `"1"`(대시보드 id, 문자열): 200. 숫자를 정수 `1`로: **400** `Not a valid string`. **임베드를 켜지 않은 대시보드의 숫자 id `"3"`: 200(발급됨)**. 임베드 안 한 대시보드의 `Dashboard.uuid`, 임베드한 대시보드의 `Dashboard.uuid`(임베드 uuid가 아님): 200(발급됨, **사용 시 거부**: 28-4). 존재하지 않는 uuid·숫자: **400** `EmbeddedDashboard not found.`. 대문자 uuid: 200. `type: "chart"`: **400** `Must be one of: dashboard`. 리소스 2개: 200. 빈 목록: 200(토큰 발급은 됨, 사용 시 의미 없음). `resources` 생략: 400 |
| ⑤ `rls` | `[]`: 200. 비어 있지 않은 규칙(`{"dataset":1,"clause":"team = '팀1'"}` 또는 `clause`만): **200**(기본 상태에서는 그대로 발급, 훅이 없을 때 막지 않음). `rls: null`, 생략: 400 |
| ⑥ 응답 형태·소요 시간(ms) | 세션 재사용 POST 20회: 중앙값 **26**(최소 20, 최대 32). 로그인 10회: 중앙값 **180**(150~262). CSRF 조회: 중앙값 31. 로그인+CSRF+POST 전체: 중앙값 **241**(195~356). 발급 계정 JWT 접근 토큰 수명 900초 |
| ⑦ 이 계정의 다른 일 | `GET /me/`, `/dataset/`, `/dataset/1`, `/dashboard/`, `/dashboard/1`, `/dashboard/1/embedded`, `/chart/`, `/database/`, `/security/roles/search/`, `/menu/`, `/saved_query/`, `/annotation_layer/` 전부 **403**. `POST /dashboard/1/embedded`, `POST /dataset/`, `POST /chart/data`, `POST /sqllab/execute/` **403**. 되는 것은 `GET /security/csrf_token/` **200**뿐 |
| 최소 권한 조합 | `can_grant_guest_token`만(JWT 로그인): CSRF 조회 **403** → 발급 POST **400 CSRF**. `can_read SecurityRestApi`만: CSRF 200, 발급 **403**. 둘 다: **200**. 둘 + `can_read CurrentUserRestApi`: 200(추가 불필요). 권한 없음: 400. **`can_grant_guest_token` 1개만 있어도 세션 로그인 방식(`/login/` 폼의 CSRF 토큰 + 세션 쿠키)이면 발급 200**(확인). 즉 필요 최소는 `can_grant_guest_token SecurityRestApi` **1개**이며, REST(JWT) 로그인 흐름을 쓰려면 CSRF 조회용 `can_read SecurityRestApi`가 하나 더 필요하다 |

## 28-2. 검증 훅 (`GUEST_TOKEN_VALIDATOR_HOOK`)
시험용 훅: 비어 있지 않은 `rls`, 리소스가 1개가 아님, 타입이 `dashboard`가 아님, 허용 목록 밖 uuid를 거부(`ss-x25/superset_config.py`의 `_x25_hook`, 플래그 파일로 켜고 끔, 호출 인자를 `hook.log`에 기록).
| 시험 | 결과 |
| --- | --- |
| 호출 시그니처 | `hook(body)`, `body`는 **`{"user":…, "resources":…, "rls":…}`**(스키마 로드 결과 딕셔너리, 확인: `hook.log`의 인자 키 `["resources","rls","user"]`). 설정 파일 주석("GuestTokenUser dict를 인자로")과 **다르다**(소스 근거 `security/api.py:175-190`) |
| 호출 순서 | 스키마 검증 → 자원 존재 검증 → **훅** → 토큰 생성. 스키마 오류(`type: chart`, `resources` 생략)와 `EmbeddedDashboardNotFoundError`(존재하지 않는 id)는 **훅이 호출되기 전에** 400이 된다(훅 호출 0회) |
| 거부 | 비어 있지 않은 `rls`, 허용 목록 밖 uuid, 리소스 2개·0개, 숫자 id `"1"`·`"3"`: 전부 **400** `{"message": ["Guest token validation failed"]}`(훅이 falsy 반환). 정상 요청: 200 |
| `user` 생략 | 훅은 호출되고(허용), 그 뒤 토큰 생성에서 **500** `Fatal error`(훅이 막지 못함: 필수 필드 검사는 따로 필요) |
| 훅은 발급 때만 호출되는가 | **그렇다.** 소스 근거: `GUEST_TOKEN_VALIDATOR_HOOK`을 쓰는 곳은 `security/api.py` 한 곳. 실측: 토큰을 사용한 요청(`dashboard`, `me/roles`, `chart/data` 3건)에서 훅 호출 **0회**, 발급 1회당 호출 1회 |
| 훅의 한계 | 훅은 API 발급 경로만 막는다. 직접 서명한 토큰은 훅을 **호출하지 않는다**(28-3) |

## 28-3. 직접 서명 방식 (Z3 ㄱ 대안)
방법: 시험용 컨테이너에서 표준 라이브러리 HS256(`hmac`, `hashlib`, `base64`, `json`)과 PyJWT 2.10.1로 `GUEST_TOKEN_JWT_SECRET`(env 파일의 더미 값)로 서명(`r4/sign.py`, `gtok_direct.py`)하고 SDK 시험 페이지에서 사용했다.
| 시험 | 결과 |
| --- | --- |
| SDK에서 사용 | 표준 라이브러리 서명 토큰과 PyJWT 서명 토큰 **둘 다** 대시보드가 끝까지 그려지고 팀 필터·탭2·교차 필터가 동작(`out/direct_stdlib.json`, `out/direct_pyjwt.json`) |
| 필요한 클레임 | `user`(객체, `{}`도 가능), `resources`, `rls_rules`, `type: "guest"`, `aud`(설정값과 같아야 함)는 **필수**(없으면 401). **`exp`와 `iat`는 없어도 통과**(없는 토큰이 **만료 없이 계속 유효**함). `exp`를 30일 뒤로 해도 통과(최대 수명 제한 없음). `nbf`나 `iat`가 미래이면 401. 모르는 클레임은 무시. `exp`를 문자열 `"9999999999"`로 줘도 통과. 알고리즘은 HS256만(`HS384`/`HS512`로 올바른 비밀값으로 서명해도 401) |
| **`aud`** | 기본값은 `GUEST_TOKEN_JWT_AUDIENCE`가 없을 때 **`WEBDRIVER_BASEURL`**(`http://0.0.0.0:8080/`, 소스 근거 `config.py:2025`, `security/manager.py:2984-2988`)이다. 직접 서명이면 토큰의 `aud`가 이 값과 정확히 같아야 한다(다르면·없으면·빈 문자열이면 401, 확인). **발급 API 경로에서는 backend가 `aud`를 알 필요가 없다**: Superset이 설정값(또는 기본값)을 채우며, `GUEST_TOKEN_JWT_AUDIENCE='bi-wizard-embed'`로 바꾼 인스턴스에서 API 발급 토큰의 `aud`가 `bi-wizard-embed`로 나오고 그대로 동작(확인). 직접 서명이면 `aud`를 명시 설정(`GUEST_TOKEN_JWT_AUDIENCE`)하고 같은 값을 backend와 공유해야 환경(`WEBDRIVER_BASEURL`)이 바뀌어도 깨지지 않는다. 설정 후 기본 `aud` 토큰은 401, 설정값 토큰은 200, `aud` 배열에 설정값이 포함되면 200, 포함하지 않으면 401 |
| 훅 | 직접 서명한 토큰은 훅을 **호출하지 않는다**(훅 호출 0회, 확인). 훅이 거부하는 종류(비어 있지 않은 `rls`)를 담은 직접 서명 토큰이 **그대로 통과해 쿼리에 적용**된다: `rls_rules=[{"dataset":1,"clause":"team = '팀1'"}]` → 응답이 팀1만, `{"clause":"1=0"}`(데이터셋 지정 없음)은 0행(모든 데이터셋에 적용), 다른 데이터셋만 지정한 규칙은 이 차트에 영향 없음. `clause`는 **원시 SQL 조각**이다 |
| 변조·만료 | 서명 변조, 페이로드 변조, `alg=none`, 틀린 비밀값, 만료(`exp` 과거), 틀린 `aud`: **401** |
| 서명 속도(컨테이너 안, 2만 회) | 표준 라이브러리 **15.0 µs**/토큰, PyJWT **17.7 µs**/토큰(로컬 계산, Superset 불필요) |

## 28-4. 비교표
| 기준 | 발급 API(IS1b, 전용 계정) | 직접 서명(IS2) |
| --- | --- | --- |
| backend에 필요한 Secret·변수 | 발급 계정 아이디·비밀번호(새 Secret 2개 후보). `GUEST_TOKEN_JWT_SECRET`은 backend에 필요 없음 | **`GUEST_TOKEN_JWT_SECRET`이 backend에도 필요**(기존 변수의 새 소비자). `aud` 값 공유 필요 |
| 필요 라이브러리 | HTTP 클라이언트(`httpx` 승인됨) | 표준 라이브러리 ~20줄(시험 코드 `sign.py`) 또는 PyJWT |
| Superset 쪽 준비 | 역할 1개 + 사용자 1개(권한: `can_grant_guest_token` 1~2개) | 없음(권장: `GUEST_TOKEN_JWT_AUDIENCE` 명시) |
| 검증 훅 | **적용됨**(발급 경로에서만 호출) | **우회됨**(훅 호출 0회, `rls` 비어 있지 않아도, 임의 자원 id도 통과) |
| 자원 id 검증 | 훅의 허용 목록으로 서버 쪽 코드와 이중으로 가능 | backend 코드만이 방어선 |
| 유출 시 영향 | 발급 계정 비밀번호 유출 = 토큰 발급만 가능(다른 API 403, 확인). 비밀번호 교체로 즉시 차단 가능 | 서명 키 유출 = 임의 자원·임의 `rls`·`exp` 없는 영구 토큰 위조 가능. 키를 바꾸면 모든 기존 토큰이 무효(Superset 재시작 필요) |
| 장애 시 영향 | Superset이 안 되면 대시보드도 못 보므로 추가 의존은 작음. 발급 호출이 느리면 SDK 기본 30초 타임아웃(`guestTokenFetchTimeoutMs`) | 로컬 계산이라 발급 자체는 실패하지 않음(Superset이 죽어도 토큰은 만들어짐) |
| 지연 | 세션 재사용 약 **26 ms**, 로그인 포함 전체 약 **240 ms**(로그인 약 180 ms가 대부분). 접근 토큰 수명 900초이므로 세션을 재사용하면 로그인은 15분에 1회 | **약 15~18 µs** |
| 숨은 함정 | `user` 생략 시 500, 숫자 id·`Dashboard.uuid`가 발급은 되나 사용 시 거부/허용이 다름(아래), CSRF 400, 세션 쿠키 유지 필요 | `exp` 생략 시 영구 토큰, `aud` 불일치 401, `iat`·`nbf` 미래 401 |
- `resources.id` 발급 vs 사용(확인, `out/x28_resource_usage.json`):
  | 발급한 id | 발급 | 사용(`GET /dashboard/{id}`, `chart/data`) |
  | --- | --- | --- |
  | 임베드 uuid | 200 | 200, 200 |
  | 임베드한 대시보드의 숫자 id | 200 | 200, 200 |
  | **임베드 안 한 대시보드의 숫자 id** | 200 | **200, 200**(임베드를 켜지 않아도 그 대시보드를 API로 읽을 수 있음. `/embedded/<uuid>` 화면만 임베드 uuid가 있어야 열림) |
  | `Dashboard.uuid`(임베드 uuid 아님) | 200 | **404, 403**(사용 불가) |
  - 소스 근거: `has_guest_access`가 `str(dashboard.id)` 또는 임베드 uuid와 비교(`security/manager.py:3103-3125`, `TODO: remove once uuids are rolled out`). 따라서 **backend는 임베드 uuid만 쓰고 숫자 id를 보내지 않으며, 훅(발급 API 경로)으로 허용 uuid 목록을 강제**해야 임베드를 켜지 않은 대시보드가 노출되지 않는다.

## 28-5. 갱신 흐름 (SDK 0.4.0)
소스 근거(`_workspace/qa/sdk/x/package/lib/index.js`, `guestTokenRefresh.js`): 토큰의 `exp`에서 현재 시각을 뺀 값에서 5초(`REFRESH_TIMING_BUFFER_MS`)를 뺀 시간 뒤에 `fetchGuestToken`을 다시 호출(최소 대기 10초). 실패하면 10초(`DEFAULT_TOKEN_REFRESH_RETRY_MS`)마다 재시도. 호출 한 번의 타임아웃 30초.
| 시험 | 결과 |
| --- | --- |
| 기본 만료 300초, 335초 관찰 | `fetchGuestToken` 호출 시각: **0초, 295초**(만료 5초 전 갱신 **확인**). 원래 토큰이 만료된 뒤인 331초에 대시보드 새로고침 → 차트 6개 요청 전부 200 |
| 만료 30초(`GUEST_TOKEN_JWT_EXP_SECONDS`를 시험 override로 단축), 95초 | 호출 0, 25, 51, 76초(약 25초 간격). 20·40·60·85초 시점 새로고침 모두 200 |
| 갱신이 계속 실패(호출 2번째부터 예외) | 호출 시각 0, 25, 36, 46, 56, 67, 77초(**10초마다 재시도**). 원래 토큰이 만료된 30초 이후 새로고침은 전부 **401**, 자동 복구 없음. 화면: 모든 차트 "Data error", 필터 "Network error", 토스트 `This session has encountered an interruption, and some controls may not work as intended. If you are the developer of this app, please check that the guest token is being generated correctly.`(영문, 개발자용 문구, `shots/refresh_failAll_end.png`). 이미 그려진 차트는 다시 조회할 때까지 그대로 남음 |
| 갱신 2회(25초, 36초) 실패 후 성공(호출 4번째 46초) | 30~46초 구간(약 16초) 새로고침 **401**, 46초 이후 **200**으로 자동 복구 |
| 갱신이 쓰레기 문자열을 반환(호출 2번째) | 그 토큰이 iframe에 **먼저 전달되어** 요청이 401(만료 시각 파싱 실패로 예외 → 10초 뒤 재시도). 36초 호출에서 정상 토큰을 받으면 복구(45초 시점 200) |
- 갱신 때마다 발급 API 호출이 1회 생긴다(만료 300초 기준 대시보드 1개당 시간당 약 12회, 계산과 실측 295초 간격 일치).

## X-28 결론
- **발급 계정 최소 권한:** `can_grant_guest_token on SecurityRestApi` **1개**(세션 로그인+폼 CSRF 방식)이며, REST(JWT) 로그인 흐름이면 CSRF 조회용 `can_read on SecurityRestApi`가 더해져 **2개**. 이 계정은 다른 API를 전부 403으로 받는다(데이터셋·대시보드·임베드·차트 데이터·SQL Lab).
- **훅:** 발급 API 경로에서만 호출되며 `body = {user, resources, rls}`를 받는다. 거부 응답은 `400 {"message": ["Guest token validation failed"]}`. 직접 서명한 토큰은 훅을 우회한다.
- **`aud`:** 발급 API 경로에서는 backend가 알 필요가 없다. 직접 서명이면 필요(기본 `http://0.0.0.0:8080/` = `WEBDRIVER_BASEURL`; `GUEST_TOKEN_JWT_AUDIENCE` 명시 권장).
- 직접 서명은 `exp` 없는 영구 토큰과 임의 `rls`가 통과하므로 backend 코드가 유일한 방어선이다. 발급 API는 지연이 약 26 ms(세션 재사용)~240 ms(로그인 포함)다.
- 갱신: 만료 5초 전에 호출되고, 실패하면 10초마다 재시도하며 그 동안 만료 후에는 401과 개발자용 영문 안내가 보인다.

## X-28 한계(못 한 시험)
- HTTPS 프록시 뒤에서의 CSRF(`Referer` 엄격 검사)와 쿠키 속성은 미확인. 발급 계정의 JWT 갱신 토큰 흐름(X-22에서 확인)은 다시 시험하지 않았다.
- 슬러그(slug) 기반 `resources.id`는 슬러그가 없어 시험하지 못했다. `GUEST_TOKEN_JWT_AUDIENCE`를 함수로 주는 방식은 시험하지 않았다.
- 5분 만료의 실제 대기는 1회(335초)만 했고, 나머지 갱신 시험은 30초 단축 설정으로 했다. 갱신 실패 시 화면은 한 구성(401)만 보았다.
- 훅·`aud` 시험은 시험 전용 override(운영 설정 아님)에서만 했다. 훅 시험에서 `user` 필수 검사는 훅 안에서 하지 않았다.

---

# 부가 확인 (실험 중 관찰)
- Superset 6.1.0 임베드 화면은 `POST /superset/log/?explode=events`를 `sendBeacon`으로 보내며 guest 토큰이 없어 **302 로그인 리다이렉트**가 반복된다(영향 없음, 로그인 페이지 GET이 뒤따름). 서버 로그에 `Failed to add user to db session: Class 'werkzeug.local.LocalProxy' is not mapped` 경고가 guest 요청마다 남는다(영향 없음으로 보이며 원인은 확인하지 못함).
- 대시보드 "…" 메뉴의 "Download" 항목은 최소 권한에서도 보이며 PDF·이미지는 브라우저 안에서 만들어진다.
- 권한 이름 `can_screenshot`은 6.1.0에 없다. 화면 캡처 엔드포인트는 기능 플래그가 꺼져 있어 404였다.

# 산출물 위치
- 스크립트·원출력: `_workspace/gate3/experiments/r4/` — `emb.js`(SDK 시험 하네스), `bis.py`/`bis2.py`(이분 탐색), `sweep.js`(차트 종류), `x25_neg.py`·`gs.py`(부정 시험), `x25_native.js`(X-21 후속), `x28_a.py`·`x28_hook.py`·`x28_aud.py`·`x28_refresh.js`·`sign.py`·`gtok_direct.py`(X-28), `setup_base.py`·`setup2.py`·`setup3.py`(시험 객체), `out/`(JSON·로그), `shots/`(스크린샷).
- 시험 전용 설정(Git 제외): `_workspace/qa/x25-override.yml`, `_workspace/qa/ss-x25/superset_config.py`, `flags.json`, `hook.log`(원본은 `r4/out/hook.log`에도 복사).
