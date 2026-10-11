# Gate ③ 5라운드 확인 A-27: 서비스 계정이 Superset 데이터셋의 열 "표시 이름"을 갱신할 수 있는가

- 목적: 결정 K12 (나) "내부 번호 열 이름 + Superset 표시 이름"의 전제 확인. 사용자가 명시 요청. 클라우드 세션 안에서만 실행. 저장소 추적 파일은 수정하지 않았고 git도 쓰지 않았다.
- 환경: Apache Superset **6.1.0**(`bi-wizard-superset:6.1.0`, 저장소 기본 `superset_config.py`, 시험 전용 override 없음), PostgreSQL **16.10**, compose 프로젝트 `g3x`(더미 값 `_workspace/qa/g3x.env`, `up -d --no-build`), 포털 `http://127.0.0.1:25173`, Superset `…/bi-wizard/superset`. 브라우저: Playwright 1.56.1 + 헤드리스 Chromium(`/opt/pw-browsers/chromium-1194`). 스크립트·원출력·스크린샷: `_workspace/gate3/experiments/r5/`(Git 제외). 소스는 `_workspace/gate3/sources/superset-6.1.0/`와 실행 컨테이너 안 `/app/superset/`(사본 `r5/src/`).
- 표기: "확인" = 실행하여 관찰, "소스 근거" = 코드 읽기, "미확인" = 하지 못함.
- 세션 시작 때 Docker 데몬이 꺼져 있었다. `service docker start`는 `ulimit` 오류로 실패했고 `dockerd`를 직접 실행했다(`r5/dockerd-r5.log`). 종료하지 않았다.
- 시험 데이터(직접 생성, 합성): `bi_data.ds_1`(`row_id` identity, `c_1` numeric, `c_2` numeric, `c_3` text, `team` text, `period` date; 팀 3개 × 12개월 = 36행), 뷰 `bi_data.dv_1`(같은 5개 열을 명시 select; `bi_readonly`에 03c 방식으로 SELECT 부여). 서비스 계정 `a27_svc`/역할 `a27_service`: **X-22의 4개 권한만**(`can_read Dataset`, `can_write Dataset`, `schema_access [BI-Wizard (read-only)].[bi_wizard].[bi_data]`, `can_read SecurityRestApi`; 먼저 `POST /database/1/sync_permissions/` 실행, 역할 조회로 정확히 4개 확인 `r5/setup_users.out`). 작성자 `a27_author1`: Gamma 복사본(95개 권한) + `bi_data` schema 보조 역할(03c X-20 방식). 대시보드 `a27 대시보드`(표 차트 1개, 막대 차트 1개, 네이티브 필터 `팀`(target `team`)·`상태`(target `c_3`))는 작성자가 API로 만들었다.

---

## 1. 등록과 열 목록 (서비스 계정)

| 시험 | 결과 |
| --- | --- |
| 서비스 계정이 `POST /api/v1/dataset/` `{"database":1,"schema":"bi_data","table_name":"[팀1] 월별 실적","sql":"SELECT * FROM bi_data.dv_1"}` | **201**. 응답 `data.columns`에 열 5개가 **id 포함**으로 돌아옴(`c_1`=1, `c_2`=2, `c_3`=3, `team`=4, `period`=5) → 등록 직후에는 별도 GET 없이 id를 알 수 있다. 소유자 = `a27_svc`(GET `owners` 확인). 열 형식: `c_1`·`c_2` DECIMAL, `c_3`·`team` STRING, `period` DATE `is_dttm=true`, `main_dttm_col`은 `period`로 자동, 지표 `count` 1개, 모든 열 `verbose_name=null`(`r5/t1_register.out`) |

## 2. 표시 이름 갱신 (`PUT /api/v1/dataset/{id}`)

| 시험 | 결과 |
| --- | --- |
| **최소 본문** `{"columns":[{"id":1,"column_name":"c_1","verbose_name":"매출"}, … 5개 열 전부]}` (`c_1`→매출, `c_2`→비용, `c_3`→상태, `team`→팀, `period`→기간) | **200**. 응답은 보낸 `columns`를 그대로 되돌려 줄 뿐이라 실제 상태는 GET으로 확인해야 한다. GET 결과 5개 열의 `verbose_name`이 설정됨. **`type`, `is_dttm`, `groupby`, `filterable`, `description`, `expression`, `main_dttm_col`, 지표 `count`는 전부 그대로**(`r5/t2_put.out`) |
| `columns` 항목에서 `id` 생략(`column_name`+`verbose_name`만) | **422** `One or more columns already exist`(id 없는 항목은 "새 열 추가"로 처리되고 이름이 이미 있어 거부) |
| `column_name` 생략(`id`+`verbose_name`만) | **422** `column_name: Missing data for required field` → `column_name`은 필수 |
| 스키마에 없는 필드(`foo`) | **422** `Unknown field` |
| 다른 데이터셋의 열 id | **422** `One or more columns do not exist`, 원래 데이터셋은 변하지 않음 |
| 같은 id에 다른 `column_name` 전송(`c_2`→`zzz`) | **200**, Superset 열 이름이 실제로 `zzz`로 바뀜(검증 없음). 서비스는 Superset이 가진 현재 `column_name`을 그대로 보내야 한다 |
| **일부 열만 전송**(scratch 데이터셋에 `c_1` 한 개만) | **200이지만 나머지 4개 열이 삭제됨**(열 5→1, 지표와 `main_dttm_col` 값은 남음). 이어서 `refresh` 하면 5개 열이 **새 id**(11~14)로 다시 생기고 **표시 이름은 `null`**(`c_1`만 id·표시 이름 유지) |
| `"columns": []` | **200, 모든 열 삭제**(열 0). `refresh`로 복구되면 전부 새 id, 표시 이름 없음 |
| 소스 근거: 6.1.0 `columns` 의미 | **교체**(병합 아님). `DatasetDAO.update_columns`(`daos/dataset.py` 262~333줄): `id`가 있으면 그 열을 갱신, `id`가 없으면 새 열 추가, **목록에 없는 기존 열은 삭제**(`override_columns=false` 기본). 갱신은 `{**기존 __dict__, **보낸 값}`이라 **보내지 않은 필드는 보존**됨(실측과 일치) |
| 보낸 열의 필드 생략 | 보존됨(확인). 예: `verbose_name` 키 없이 보낸 열은 기존 표시 이름 유지 |
| `verbose_name: null` / `""` | `null`은 해제(NULL), `""`는 빈 문자열로 저장됨 |
| `description` 같이 전송 | 반영됨(`c_1`에 "내부 번호 c_1 = 매출" 확인) |
| 특수문자(`"` `'` `<b>` `%s` `{x}`) | 그대로 저장·조회됨 |
| 2,000자 `verbose_name` | **422** `Dataset could not be updated.`(DB 열이 `String(1024)`, `connectors/sqla/models.py` 855·1100줄. 스키마의 `Length(1,1024)`는 검증하지 않는 메타데이터) → 표시 이름은 1,024자 이내로 앱에서 제한 |
| **`table_name`과 `columns`를 같은 호출로** | **200**, 둘 다 적용됨(`[a27 scratch] 부분 시험`→`[a27 scratch] 이름 변경` + 표시 이름 5개) |

## 3. 보존

| 시험 | 결과 |
| --- | --- |
| (a) `PUT /dataset/{id}/refresh` | **200**. 열 id와 `verbose_name`·`description`·`is_dttm`·`type`·`main_dttm_col`·지표 **모두 유지**. 부수 변화는 기존 열의 `expression`이 `null`→`""`로 바뀌는 것뿐(소스 근거: `fetch_metadata`가 기존 물리 열의 `expression`을 `""`로 초기화, `connectors/sqla/models.py` 1838줄). 같은 시점 대시보드·차트 정상 |
| (b) 뷰에 `c_4` 추가(`ALTER TABLE … ADD COLUMN c_4` + `CREATE OR REPLACE VIEW`, 끝에 추가) 후 refresh | **200**. 새 열 `c_4`는 **새 id(20), `verbose_name=null`**, DECIMAL, `is_dttm=false`, `groupby/filterable=true`. **기존 5개 열 표시 이름 유지**. 새 열에 이름을 붙이려면 다시 PUT 해야 하며, **`c_4` 한 개만 보내면 나머지 열이 삭제됨**(scratch에서 확인: 열 6→1). 6개 열(기존 5 + `c_4`, 모두 id 포함)을 보내면 정상(`c_4`="이익") |
| (c) 뷰에서 `c_4` 제거(`DROP VIEW`+`CREATE VIEW`) 후 refresh | **200**. `c_4` 열 행이 삭제됨(열 6→5). 다른 열의 표시 이름 유지. 같은 이름으로 `c_4`를 다시 추가하면 **새 id(32), 표시 이름 없음**(이전 이름 복원 안 됨). 그 열을 쓰던 저장된 차트는 03c X-22대로 깨짐(이번에는 `c_4`를 쓰는 차트가 없어 재시험하지 않음) |
| (d) 표시 이름만 변경(`c_1`→총매출, `c_2`→총비용; 이어서 `c_1`→매출액) | **저장된 차트·대시보드 영향 없음**: 대시보드를 열었을 때 `chart/data` 4건 모두 200(요청 열 `c_1`…), 표 차트 머리글만 "총매출, 총비용"으로 바뀜. 표 차트 `params` 문자열은 변경 전과 **동일**(막대 차트는 Explore에서 200 확인), 대시보드 `native_filter_configuration`의 target은 `column.name`(`team`, `c_3`) 그대로 → 차트와 필터는 `column_name`을 참조한다(확인) |
| 부수 관찰: UI에서 만든 지표 | 작성자가 UI에서 `SUM`(총매출)을 만들면 차트에 **라벨 `SUM(총매출)`과 열 객체 사본(`verbose_name` 포함)이 저장**되고 SQL 별칭도 `AS "SUM(총매출)"`이 된다. 이후 표시 이름을 "매출액"으로 바꿔도 저장된 차트의 질의 별칭(데이터 `colnames`)은 `SUM(총매출)`로 **그대로**이고 Explore 지표 칩만 `SUM(매출액)`으로 바뀜. 깨짐은 없고 이름이 어긋날 뿐이다 |
| 부수 관찰: API로 만든 차트 | `query_context`가 없어 `GET /chart/{id}/data/`가 400(`Chart has no query context saved`). 차트 데이터 확인은 화면의 `chart/data` 호출로 했다. 또 API로 만든 지표는 라벨이 `SUM(c_1)`로 저장돼 별칭에 번호 이름이 남는다(우리 시험 차트의 특성이며 UI로 만든 차트는 위와 같음) |

## 4. 화면 노출 (Playwright, 작성자 `a27_author1` 기준)

표시 이름이 붙은 상태(`c_1`=매출[설명 "매출액(원)"], `c_2`=비용, `c_3`=상태, `team`=팀, `period`=기간, `c_4`=이익)에서 확인. 스크린샷은 `r5/shots/`.

| 화면 | 보이는 것 | 번호 이름 노출 | 스크린샷 |
| --- | --- | --- | --- |
| Explore 왼쪽 데이터셋 패널 열 목록 | 표시 이름 | 없음. **열에 마우스를 올리면 툴팁 "Column name: c_1 / Label: 매출 / Description: 매출액(원)"** → 거기에는 `c_1`이 보임. 패널 검색은 `c_1`로도 `매출`로도 같은 열을 찾음 | `a1_explore_table.png`, `a2_hover_left_col.png` |
| Explore 열 선택 드롭다운(Columns, Dimensions, 지표의 열, Filters의 열) | 표시 이름만(매출·비용·상태·이익·기간·팀) | 없음 | `a2_columns_select_open.png`, `a3_filter_popover1.png` |
| Explore 선택된 열 칩, 지표 칩 | 표시 이름(`SUM(매출)`) | 없음 | `a1_explore_table.png`, `a6_metric_popover2.png` |
| 표 차트 머리글(Explore, 대시보드) | 표시 이름 | 없음 | `a1_explore_table.png`, `c1_dash_filtered.png` |
| **Explore Filters 칩** | — | **`c_1 > 120`, `c_1 IN`**, 기본 시간 필터는 **`period (No filter)`**(주 날짜 열의 `column_name`) | `a3_filter_chip.png` |
| **Explore Ordering 선택 목록** | — | **`c_1 [asc]`, `c_1 [desc]`, …** 전부 번호 이름 | `a3_ordering.png` |
| **Explore Customize 탭 "Customize columns"** | — | **`c_1 c_2 c_3 team period`** | `d3_customize.png` |
| **Explore "Results" 창** | — | **열 머리글 `c_1 c_2 c_3 team period`**(데이터 열 이름). "Samples"는 작성자 역할(Gamma 복사본)에서 `Access is Denied` | `a4_results_pane.png` |
| **차트 메뉴 "View query"**(Explore, 대시보드) | — | SQL 그대로: `SELECT c_1 AS c_1, c_2 AS c_2, … FROM (SELECT * FROM bi_data.dv_1 ) AS virtual_table …` | `a5_view_query.png`, `c1_dash_view_query.png` |
| **대시보드 차트 메뉴 "View as table"** | — | **머리글 `c_1 c_2 c_3 team period`** | `c5_view_as_table.png` |
| **대시보드 네이티브 필터 설정 화면의 "Column"**(선택된 열 표시와 드롭다운) | — | **`c_3`**(선택된 열), 드롭다운 목록 **`c_3, c_1, c_2, c_4, period, team`만**(표시 이름·설명 없음). 새 필터를 만들면 이름 칸이 **비어 있어** 작성자가 직접 입력(열 선택은 번호 이름) | `c3_status_filter.png`, `c4_column_dropdown.png`, `c4_new_filter3.png` |
| 같은 설정 화면의 "Pre-filter available values"의 열 선택 | 표시 이름(매출 … 팀) | 없음 | (원출력 `pw4_c7.out`) |
| 필터 바 라벨, 칩 | 작성자가 입력한 **필터 이름**(`팀`, `상태`) | 없음 | `c1_dash.png`, `c1_dash_filtered.png` |
| 차트의 "적용된 필터" 표시(깔때기 배지 호버) | `Applied filters (1) 팀: 팀1`(필터 이름) | 없음 | `c1_indicator.png` |
| 차트 컨텍스트 메뉴 "Drill by" | 표시 이름(매출·비용·상태·이익) | 없음 | `d2_drill_by_menu.png` |
| 데이터 내보내기(`POST /chart/data` `result_format=csv`, UI "Download"와 같은 경로) | CSV 첫 줄 **`매출,비용,상태,팀,기간`** | 없음(API로 확인, UI 다운로드 클릭은 하지 않음) | `csv_check.out` |
| 막대 차트(범례 `팀1…`, 월 축) | 데이터 값(팀 이름) | 없음. 지표 라벨은 위 3절 부수 관찰대로 저장 시점 이름 | `c1_dash.png`, `b1_bar_explore.png` |

- 정리: 표시 이름이 보이는 곳은 **데이터셋 패널·열 선택 드롭다운·표 머리글·내보내기·Drill by·사전 필터 열**이고, 번호 이름이 **그대로 보이는 곳은 필터 설정 화면의 열 선택, Explore의 Filters 칩·Ordering·Customize columns·Results 창, "View query", "View as table", 열 툴팁**이다. `description`은 열 툴팁에만 나타나고 번호 이름이 보이는 선택 화면에는 나타나지 않는다(확인한 범위).

## 5. 권한 경계

| 시험 | 결과 |
| --- | --- |
| 서비스 계정이 **관리자가 등록한** 데이터셋(소유자=admin)의 `columns` PUT | **403** `Forbidden`. `refresh`도 403, `owners`에 자기 자신 추가도 403. 같은 데이터셋 GET은 200 → 03c X-22("소유한 것만")와 **일치** |
| 관리자가 `owners:[1, 서비스 계정]`으로 소유자를 추가한 뒤 서비스 계정 PUT | **200**(열 6개 표시 이름 반영) |
| 작성자(`a27_author1`)가 서비스 계정 소유 데이터셋의 `columns` PUT | **403** |
| 4개 권한을 하나씩 뺐을 때(소유 데이터셋에서 GET / PUT columns / refresh / 새 등록 POST) | 4개 모두: 200 / 200 / 200 / 201. `can_read Dataset` 제외: **GET 403**, PUT·refresh·POST는 200 → **열 id를 읽으려면 필요**. `can_write Dataset` 제외: GET 200, **PUT·refresh·POST 모두 403**. `schema_access` 제외: **GET·PUT·refresh 404, POST 422**(데이터셋이 보이지 않음). `can_read SecurityRestApi` 제외: **CSRF 토큰 403**이라 쓰기 불가. 역할은 시험 뒤 4개로 복원 |
| 4개 외 권한이 더 필요한가 | **아니오**(등록, 열 조회, 표시 이름 PUT, refresh, 이름 변경 모두 4개로 동작) |
| 오래된 열 id(refresh로 사라진 id)로 PUT | **422** `One or more columns do not exist`(재조회 후 재시도 필요) |

## 6. 대안 근거(실패 시에만)

해당 없음(결과가 "조건부 가능"). 뷰 열 별칭 `AS "표시 이름"` 방식과 계산 열(`expression`)을 통한 우회는 **시험하지 않았다**(03c X-22와 소스 근거에 기대는 것은 이름을 문자열로 참조한다는 점뿐).

---

## 결론

**조건부 가능.** 서비스 계정(X-22의 4개 권한)이 **자신이 소유한** 가상 데이터셋의 열 `verbose_name`을 `PUT /api/v1/dataset/{id}`의 `columns`로 설정·변경·해제할 수 있다. 표시 이름만 바꾸면 저장된 차트·네이티브 필터는 `column_name`을 참조하므로 깨지지 않는다. 조건은 다음과 같다.

1. **`columns`는 교체 방식**이라 **항상 현재 모든 열을 `id`+`column_name`(+`verbose_name`)로 보낸다.** 일부만 보내거나 `[]`를 보내면 나머지 열이 삭제되고(refresh로 복구해도 새 id·표시 이름 없음), `id`가 없는 항목은 새 열로 취급된다. 서비스는 반드시 GET으로 받은 열 목록을 병합해서 보낸다.
2. **refresh는 기존 열 표시 이름을 건드리지 않지만 새 열은 이름 없이 생긴다.** 뷰에 열을 추가한 뒤에는 refresh → GET → 전체 열 PUT으로 새 열에 이름을 붙이는 단계가 필요하다. 뷰에서 지웠다가 다시 만든 열은 이전 표시 이름이 복원되지 않으므로 포털이 표시 이름을 자체 보관하고 다시 적용해야 한다.
3. **번호 이름이 여전히 보이는 화면이 있다**(4절): 특히 작성자가 대시보드 필터를 설정할 때의 열 선택 목록(`c_1` … 만 표시), Explore의 Filters 칩·Ordering·Customize columns·Results, View query·View as table. 표시 이름은 이 화면들을 가리지 못하며 `description`도 열 툴팁 외에는 나타나지 않았다. K12 (나)를 선택하면 작성자가 필터를 설정할 때 열 매핑을 알아야 하는 비용이 남는다.
4. 소유권 제한: 관리자가 등록한 데이터셋은 서비스 계정이 못 바꾼다(403). 서비스 계정이 **직접 등록**해서 소유하도록 유지한다.

### 서비스 계정이 보낼 요청 순서

1. (관리자, 새 schema일 때만 1회) `POST /api/v1/database/{id}/sync_permissions/` → 서비스 역할에 `schema_access` 부여.
2. 로그인과 토큰: `POST /api/v1/security/login`(provider `db`, `refresh:true`) → 같은 쿠키 세션으로 `GET /api/v1/security/csrf_token/` → 이후 쓰기 요청에 `Authorization: Bearer`, `X-CSRFToken`, `Referer`. (접근 토큰 15분: 03c X-22)
3. **등록:** `POST /api/v1/dataset/` `{"database":<id>,"schema":"bi_data","table_name":"<읽기 쉬운 이름>","sql":"SELECT * FROM bi_data.dv_<n>"}` → 201, 응답 `data.columns[]`에서 `id`와 `column_name`을 얻는다(별도 GET 불필요).
4. **표시 이름 적용:** `PUT /api/v1/dataset/{id}` `{"columns":[{"id":1,"column_name":"c_1","verbose_name":"매출"}, … 모든 열 …]}` (필요하면 같은 본문에 `"table_name"`, 열별 `"description"` 추가) → 200. `column_name`은 현재 값을 그대로 보낸다(바꾸면 Superset 열 이름이 바뀜). `verbose_name`은 1,024자 이내.
5. **뷰 변경 후(열 추가·제거·타입 변경):** `PUT /api/v1/dataset/{id}/refresh` → `GET /api/v1/dataset/{id}`(현재 열 `id`·`column_name`·`verbose_name`) → 포털이 가진 표시 이름과 병합해 **전체 열을 다시 PUT**(4단계). 새 열만 보내지 않는다. refresh와 PUT은 데이터셋 단위로 직렬화하고, 422 `columns do not exist`면 재조회 후 재시도한다.
6. **이름만 바꿀 때(`table_name` 또는 표시 이름):** 4단계 PUT만 보낸다(refresh 불필요, 차트·필터 영향 없음).

### 최소 요청 본문
```json
{"columns": [
  {"id": 1, "column_name": "c_1", "verbose_name": "매출"},
  {"id": 2, "column_name": "c_2", "verbose_name": "비용"},
  {"id": 3, "column_name": "c_3", "verbose_name": "상태"},
  {"id": 4, "column_name": "team", "verbose_name": "팀"},
  {"id": 5, "column_name": "period", "verbose_name": "기간"}
]}
```

## 한계

- 합성 데이터, Superset 6.1.0 한 버전, gunicorn 워커 1개, HTTP, 헤드리스 Chromium 1종, 열 5~6개 규모. 열 수백 개·본문 크기·동시 호출(refresh와 PUT이 겹칠 때)은 시험하지 않았고, 오래된 id가 422로 막히는 것만 확인했다.
- 화면 확인은 **Gamma 복사본 + schema 보조 역할 작성자**만 대상으로 했다. 관리자 화면, Embedded(guest 역할 `bi_guest`)로 보는 화면, 알림·리포트, 다른 차트 유형(피벗·필터 상자 등)은 시험하지 않았다. Explore X축 드롭다운 내용(열지 못함)과 UI의 CSV/이미지 다운로드 버튼은 미확인(CSV는 API로만 확인).
- 시험 차트는 API로 만들었고 지표 라벨 관찰(3절)은 UI로 만든 차트 1개로 확인한 것이다. 사용자가 만드는 다양한 지표·계산 열·저장 지표(`SqlMetric`)의 표시 이름은 시험하지 않았다.
- 뷰 DDL은 이 시험 DB의 슈퍼유저로 실행했다(`bi_owner` 아님). 번호 이름 열이 아닌 `period`, `team`은 규약 이름이라 Filters 기본 시간 필터 칩에 `period`가 보였다. 주 날짜 열을 번호 이름으로 만들면 그 번호가 보일 것이다(추정).
- 대안(뷰 별칭, 계산 열)은 필요가 없어 시험하지 않았다.

## 정리

- 삭제(이름 지정): 컨테이너 `g3x-frontend-1`, `g3x-superset-1`, `g3x-backend-1`, `g3x-superset-init-1`, `g3x-migrate-1`, `g3x-db-bootstrap-1`, `g3x-postgres-1`, 네트워크 `g3x_default`, 볼륨 `g3x_postgres_data`. 일괄 삭제 명령(`down -v`, `volume prune`, `system prune`, `rm -rf`)과 git은 쓰지 않았다. Superset 안의 시험 객체(데이터셋, 차트, 대시보드, 시험 사용자·역할)는 볼륨과 함께 사라졌다.
- 정리 전후 기록: `r5/cleanup-before.txt`(시작 시 컨테이너 0개, 볼륨 `bi-wizard_postgres_data`만), `r5/cleanup-pre.txt`, `r5/cleanup-post.txt`.
- 정리 후: 컨테이너 0개, 볼륨 `bi-wizard_postgres_data` 하나(건드리지 않음), 네트워크는 기본 3개, 이미지 유지. 이 세션에서 시작한 `dockerd`는 실행 중으로 두었다.
- 파일 안내: `setup*.py`/`setup_data.sql`(환경), `t1_*`~`t5_*`(API 시험과 `.out`), `pw4_*.js`(화면 시험과 `.out`), `shots/`(스크린샷 56개), `src/`(참조한 컨테이너 소스 사본), `ids.json`(시험 객체 번호).
