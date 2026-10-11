# 03c. Gate ③ 런타임 실험 결과

- 승인: 2026-10-11 사용자(2라운드 결정, `03b-gate3-round-decisions.md` 2-7). 승인 범위 X-1, X-2, X-5, X-7, X-8, X-9, X-11, X-13. 클라우드 세션 안에서만 실행.
- 환경: PostgreSQL **16.10**(`postgres:16.10-bookworm`, tmpfs 데이터, 볼륨 없음), Apache Superset **6.1.0**(이 저장소의 `bi-wizard-superset:6.1.0` 이미지와 compose 프로젝트 `g3x`, 시험용 더미 값 env 파일 `_workspace/qa/g3x.env`). 백엔드 드라이버 pg8000 1.31.5(이 저장소의 backend 이미지), Superset 드라이버 psycopg2(Superset 이미지).
- 스크립트·원출력은 `_workspace/gate3/experiments/`(Git 제외)에 있다.
- **정리:** 시험 컨테이너 전부와 네트워크 `g3x_default`는 삭제했고, 볼륨 `g3x_postgres_data`는 이름을 지정해 삭제했다(일괄 삭제 명령 없음). 시험 시작 전 볼륨은 `bi-wizard_postgres_data`, `g3x_postgres_data` 두 개였고 종료 후 `bi-wizard_postgres_data` 하나만 남았다. 이미지는 그대로 유지했다. 독립 PostgreSQL 시험 컨테이너 `g3x-pg`는 tmpfs 데이터라 볼륨이 없고, 삭제를 확인했다.
- 한계: 이 결과는 PostgreSQL 16.10과 Superset 6.1.0, 이 저장소 구성 기준이다. 데이터 규모는 모의 데이터(난수)이며 실제 업무 수식 복잡도와 다를 수 있다.

## X-1. DDL 롤백 (PostgreSQL 16.10)
| 시험 | 결과 |
| --- | --- |
| `CREATE SCHEMA` + `CREATE TABLE` + `CREATE VIEW` + `CREATE OR REPLACE VIEW` + `ALTER TABLE ADD COLUMN` + `GRANT USAGE` + `ALTER DEFAULT PRIVILEGES IN SCHEMA` + 등록 표 `INSERT` 후 `ROLLBACK` | **모두 롤백됨.** schema 없음, 등록 행 0건, 기본 권한(`pg_default_acl`) 0건 |
| 기존 객체에 `ALTER TABLE ADD COLUMN`, `CREATE OR REPLACE VIEW`, `GRANT SELECT`, `DROP VIEW` 후 `ROLLBACK` | **모두 롤백됨.** 열 목록, 뷰 존재와 열, 권한 원상 |
| 트랜잭션 안에서 등록 `INSERT` + `CREATE TABLE`, 같은 표를 다시 `CREATE`(오류) | 오류로 트랜잭션 전체가 취소되어 **등록 행과 표 모두 없음** |
| 시퀀스(`serial`) | **롤백되지 않음.** 롤백된 `INSERT` 뒤 다음 id가 건너뛰어 4가 됨(번호 공백) |
- 결론: 확보한 PostgreSQL 문서에 없던 "DDL별 롤백"은 16.10에서 실제로 동작한다. 등록 표 쓰기와 물리 객체 생성·변경·권한 부여를 **한 트랜잭션**으로 묶을 수 있다. 번호 공백(`id` 건너뜀)은 정상 동작이다.

## X-2. 읽기 전용 트랜잭션 (PostgreSQL 16.10)
| 시험 (`BEGIN READ ONLY` 안) | 결과 |
| --- | --- |
| `SELECT`, `VALUES`, 읽기만 하는 함수 | 동작 |
| `SET LOCAL statement_timeout` | 동작(시간 초과 시 취소됨) |
| `nextval()` | **차단**: `cannot execute nextval() in a read-only transaction` |
| `CREATE TABLE`, `CREATE VIEW` | 차단 |
| **`CREATE TEMP TABLE`, `CREATE TEMP VIEW`** | **차단**(임시 객체 생성도 CREATE로 막힘) |
| `INSERT`(직접 또는 함수 안) | 차단 |
| 트랜잭션 안에서 읽기 전용 해제 | `SET transaction_read_only = off`/`SET TRANSACTION READ WRITE`는 **첫 쿼리 전에만** 가능. 쿼리 실행 후에는 `transaction read-write mode must be set before any query` 오류. 함수 안 `set_config`로도 불가 |
| 역할에 `default_transaction_read_only = on` 설정 | 같은 세션에서 `SET default_transaction_read_only = off`로 **해제 가능** |
- 결론: 읽기 전용 트랜잭션은 서버가 만든 SQL을 보낼 때의 이중 장치로 쓸 수 있으나, **사용자 SQL을 받는 경우의 방어선은 아니다**(첫 쿼리 전 해제 가능, 역할 기본값은 세션에서 해제 가능). 임시 뷰(C4-temp)는 읽기 전용 트랜잭션 안에서 만들 수 없다.

## X-5. 대시보드 필터와 데이터셋별 열 이름 (Superset 6.1.0)
구성: 데이터셋 3개(뷰 `dv_1`: 시간 열 `period_a`/팀 열 `team`, `dv_2`: `base_date`/`team`, `dv_3`: `period`/`team_code`), 가상 데이터셋 1개, 표 차트 5개, 대시보드 1개(네이티브 필터: 기간 `2025-01-01 : 2026-01-01`, 팀 `T1,T2`). 관리자 계정으로 브라우저를 열어 실제 `chart/data` 요청과 응답의 SQL을 수집했다.
| 차트 | 요청 필터 | 실제 SQL의 WHERE | 결과 |
| --- | --- | --- | --- |
| `dv_1`(`period_a`, `team`), 차트에 시간 필터 있음 | `team IN`, `period_a TEMPORAL_RANGE` | `team IN ('T1','T2') AND period_a >= '2025-01-01' AND period_a < '2026-01-01'` | 양쪽 모두 적용, 12행 |
| `dv_2`(`base_date`, `team`), 시간 필터 있음 | `team IN`, `base_date TEMPORAL_RANGE` | 같은 형태, **열 이름이 달라도 각자 자기 시간 열로** 적용 | 12행 |
| `dv_3`(`period`, **`team_code`**), 시간 필터 있음 | `team IN`, `period TEMPORAL_RANGE` | 시간 조건만. **`team` 필터는 `rejected_filters: not_in_datasource`로 조용히 건너뜀** | 12행(팀 필터 미적용) |
| `dv_2`, **차트에 시간 필터 없음** | `team IN`만 | `team IN ('T1','T2')`만. **날짜 필터가 적용되지 않음** | 33행(전체 기간) |
| 가상 데이터셋(`SELECT * FROM bi_data.dv_1`) | `team IN`, `period_a TEMPORAL_RANGE` | 서브쿼리로 감싸 같은 방식으로 적용 | 12행 |
- 팀 필터 값 목록은 **지정한 한 데이터셋의 열 하나**(`dv_1.team`)에서 조회된다(`SELECT team FROM bi_data.dv_1 GROUP BY team`).
- **새 차트의 기본 시간 필터(Q33-a):** Explore에서 `table`, `echarts_timeseries_line`, `big_number_total`, `pie` 새 차트를 열면 필터 영역에 데이터셋의 기본 시간 열 칩 `base_date (No filter)`가 **기본으로 들어간다**(화면 기준. 저장된 차트의 `adhoc_filters`가 실제로 이를 포함하는지는 저장 후 확인하지 않았다).
- 결론: ① 값 선택 필터(팀)는 **열 이름이 같아야** 한다(다르면 조용히 제외). ② 날짜 필터는 **열 이름이 달라도** 각 차트의 시간 필터가 자기 시간 열로 해석한다. 단 **차트에 시간 필터가 없으면 적용되지 않는다.** → W12 "날짜 열 이름 통일"은 필수가 아니다(날짜는 형식·시간 필터 기본 포함이 핵심). 팀 열 이름 통일은 필요하다.
- 시험하지 않은 것: 필터 설정 화면에서 "다른 데이터셋 차트가 범위에서 기본 제외 + 경고"가 날짜 필터에도 나타나는지(UI 설정 화면 조작은 하지 않음).

## X-7. 뷰 교체 시 락 (PostgreSQL 16.10)
| 시험 | 결과 |
| --- | --- |
| 읽는 트랜잭션이 열려 있는 동안(8초) `CREATE OR REPLACE VIEW` | 기다리다 `lock_timeout`(3초)에 취소 |
| 같은 조건에서 `ALTER VIEW RENAME COLUMN`, `DROP VIEW`+`CREATE VIEW`, `ALTER TABLE ADD COLUMN`(기반 표) | 모두 기다림(3초 후 취소) |
| 같은 조건에서 `GRANT SELECT ON 뷰` | **기다리지 않음**(0.13초) |
| DDL 트랜잭션이 열려 있는 동안(5초) 읽기 | 읽기가 **DDL 커밋까지 막힘**(4.1초) |
| 읽기 A(8초) → DDL B(대기) → 새 읽기 C | **C도 B 뒤에서 막힘**(B가 `lock_timeout`으로 포기할 때까지 약 4.1초). 대기 중인 DDL 뒤로 새 읽기가 줄을 섬 |
| 락 종류 | `CREATE OR REPLACE VIEW`: 뷰에 `AccessExclusiveLock`(기반 표는 `AccessShareLock`). `ALTER TABLE ADD COLUMN`: 표에 `AccessExclusiveLock` |
- 결론: 뷰 교체 자체는 짧지만, 열려 있는 긴 읽기를 기다리며 **그 뒤의 새 읽기까지 막을 수 있다.** 서버 시작 시 재생성은 `lock_timeout`을 짧게 걸고 실패 시 재시도·헬스 체크 표시가 필요하다. 한 트랜잭션 안에서 재생성을 끝내 읽기를 막는 시간을 최소화한다.

## X-8. 세션 시간대와 `CURRENT_DATE`
| 시험 | 결과 |
| --- | --- |
| 이미지 기본(`TZ` 없음) | 서버 `Etc/UTC`. backend(pg8000)와 Superset(psycopg2) 세션 모두 `Etc/UTC` |
| 데이터베이스에 `ALTER DATABASE … SET timezone='Asia/Seoul'` | 두 드라이버 모두 `Asia/Seoul`로 따름(드라이버가 시간대를 덮어쓰지 않음) |
| **이 저장소 compose의 PostgreSQL** | `TZ=Asia/Seoul`이 전달되어 서버 `TimeZone`이 `Asia/Seoul`(설정 파일 출처) |
| 같은 순간 `2026-10-11 20:00Z` | UTC 날짜 `2026-10-11`, Seoul 날짜 `2026-10-12` |
- 결론: backend와 Superset의 `CURRENT_DATE`는 같은 서버/DB 시간대를 따른다. 현재 compose에서는 Asia/Seoul이다. 뷰의 `TODAY()` 결과는 DB 설정에 의존하므로 **DB 시간대를 고정해 두고 환경이 바뀌어도 유지**해야 한다(`TZ`를 지우면 UTC가 되어 하루 경계가 9시간 어긋남).

## X-9. 규모 시험 (5개 팀 × 팀당 10개 데이터셋 = 50개, 사용자 승인 조건)
구성: 데이터셋 50개(팀당 월 단위 8개 + 일 단위 2개), 수식 뷰 50개(같은 행 계산 + 이전 행 `lag` + 누적합 윈도 + 기준값 as-of `LATERAL` + 최종값), 공통 요약 뷰 1개(팀 5 × 지표 8 = **UNION ALL 40가지**). 기준값 표는 12개 이름 × 연 1회 개정. 단위는 PostgreSQL `EXPLAIN ANALYZE`의 Planning/Execution Time(ms, 컨테이너 안, 반복 2~3회 범위).
| 규모 | 총 행 | 요약: 팀 1·지표 1·최근 3년 | 요약: 한 지표 전체 팀 연 합계 | 요약: 필터 없이 전체 count | 일 단위 한 데이터셋 전체 계산 후 20행(C1-a) | 월 단위 한 데이터셋(C1-a) |
| --- | --- | --- | --- | --- | --- | --- |
| 기본(월 120행 × 40, 일 3,650행 × 10) | 41,300 | 0.7~1.3 | 2.3~5.3 | 19~23 | 13.6~14.9 | 0.5 |
| 2배 | 82,600 | 0.8~1.0 | 4.2~4.4 | 19~38 | 28.8~28.9 | 1.0 |
| 약 10배(월 1,200행, 일 36,500행) | 413,000 | 3.3~8.4 | 20.6~31.9 | 217~1,087 | 212~220 | 5.1 |
- 계획 시간(Planning)은 요약 뷰 40가지에서 2~16ms.
- 결론: 예상 규모(5×10)에서 공통 요약 뷰(B1)와 C1-a 전체 계산 미리보기는 **수십 ms 이내**다. 10배 규모의 최악 조건(필터 없는 전체 합산)도 약 1초 이하다. 데이터가 일 단위로 매우 길어지면(3.6만 행 이상) 미리보기에 약 0.2초가 걸린다. 모의 데이터이므로 실제 수식이 복잡해지면 달라질 수 있다.
- 한계: 메모리는 측정하지 않았다. 동시 접속(Superset 여러 위젯)은 측정하지 않았다.

## X-11. 열 타입·이름·삭제 변경과 의존 뷰 (PostgreSQL 16.10)
| 시험 | 결과 |
| --- | --- |
| 뷰가 쓰는 열의 `ALTER COLUMN TYPE` | **거부**: `cannot alter type of a column used by a view or rule` (`SELECT *` 뷰도 모든 열에 의존해 거부, 뷰-on-뷰도 연쇄) |
| 열 `DROP COLUMN` (의존 뷰 있음) | `CASCADE` 없이는 거부. `CASCADE`는 의존 뷰를 같이 삭제 |
| 열 `RENAME COLUMN` | 뷰가 **자동으로 따라감**(뷰 정의가 새 이름으로 바뀜) |
| 열 `ADD COLUMN` | `SELECT *` 뷰는 만들 때 열 목록이 고정되어 새 열을 포함하지 않음 |
| `CREATE OR REPLACE VIEW`로 열 타입·이름·순서 변경 | **거부**(끝에 열 추가만 가능). 이름 변경은 `ALTER VIEW … RENAME COLUMN` 안내 |
| 의존 뷰를 모두 삭제 → 타입 변경 → 뷰 재생성(한 트랜잭션) | **성공** |
| 의존 뷰 찾기 | `pg_depend`/`pg_rewrite`로 한 표에 의존하는 모든 뷰를 열거하는 질의가 동작(뷰-on-뷰 포함, 연쇄는 반복 필요) |
- 결론: 열 타입 변경은 "의존 뷰 전부 내리기 → 변경 → 재생성"의 한 트랜잭션 절차로 한다(X-1이 원자성을 뒷받침). 이름 변경은 뷰가 따라가지만 Superset 차트는 이름을 문자열로 참조하므로 표시 이름과 내부 이름을 분리하는 설계가 필요하다(Q21).

## X-13. 뷰를 가상 데이터셋으로 등록 (Superset 6.1.0)
| 항목 | 결과 |
| --- | --- |
| 등록 | `table_name`에 한글 표시 이름 `팀1 월별 (가상 데이터셋)`, `sql = SELECT * FROM bi_data.dv_1`, schema `bi_data`로 **등록 성공**(201) |
| 열 동기화 | 열이 자동 인식됨(시간 열 `period_a`는 `is_dttm`, `main_dttm_col` 자동). 뷰에 열을 추가하고 `PUT /dataset/{id}/refresh` 하면 물리 데이터셋과 가상 데이터셋 모두 **새 열이 반영됨** |
| 쿼리 | `SELECT … FROM (SELECT * FROM bi_data.dv_1 ) AS virtual_table WHERE …`로 실행. 필터 열 매칭은 물리 데이터셋과 같음(X-5) |
| 권한 이름 | 가상 데이터셋의 `datasource access` 권한 이름에 **표시 이름**이 쓰임(`[BI-Wizard (read-only)].[팀1 월별 (가상 데이터셋)](id:4)`) |
| 열 형식 이름 | 가상은 `STRING`/`DECIMAL`, 물리 뷰는 `TEXT`/`NUMERIC`으로 보고됨(동작 차이는 확인하지 못함) |
- 결론: 뷰를 가상 데이터셋으로 등록하면 Superset 화면의 데이터셋 이름을 읽기 쉽게 줄 수 있다(W11 (다)). 단 데이터셋 이름이 바뀌면 권한 이름이 바뀌는 등 영향이 있어 이름 관리 정책이 필요하다.

## 부가 확인 (실험 중 관찰)
- **CSRF:** Bearer 토큰만으로 POST하면 `400 The CSRF token is missing`. `GET /api/v1/security/csrf_token/`으로 토큰을 받고 **같은 세션 쿠키와 `X-CSRFToken` 헤더를 함께** 보내면 통과한다(다른 세션의 토큰은 400). 포털 backend가 Superset REST API를 호출하려면 쿠키를 유지하는 세션과 토큰 갱신이 필요하다(10번 입력).
- **스키마 목록(Q34-g):** `GET /api/v1/database/{id}/schemas/` 결과가 `['information_schema', 'public', 'bi_data']`였다(`pg_catalog`는 제외, `information_schema`는 포함).
- **스키마 단위 기본 권한(W2 (a)):** `GRANT USAGE ON SCHEMA bi_data` + `ALTER DEFAULT PRIVILEGES IN SCHEMA bi_data GRANT SELECT ON TABLES TO bi_readonly`(`FOR ROLE` 생략)를 DDL 실행 역할로 실행한 뒤 같은 역할이 만든 표·뷰를 `bi_readonly`가 읽었고, `public` 표(`alembic_version`)는 읽지 못했다.
- **Gamma 기반 작성자 역할(D의 입력):** 권한 없는 Gamma 사용자는 데이터셋·차트·대시보드·DB 목록이 모두 비어 있었다. Gamma 권한 + `schema access on [DB].[catalog].[schema]`만 가진 역할(`g3x_author`)은 그 schema의 **물리 데이터셋과 가상 데이터셋을 모두** 보고 `chart/data`로 조회할 수 있었다(200). 같은 사용자의 데이터셋 생성은 물리·가상 모두 403이고 관리자 소유 대시보드는 목록에 없었다(404).
- **관찰(후속 확인 필요):** 데이터셋 접근 권한이 전혀 없는 Gamma 사용자가 `POST /api/v1/chart/`로 그 데이터셋에 대한 차트를 만드는 것이 201로 성공했다(데이터 조회는 403). 6.1.0 차트 생성 명령이 데이터셋 접근 권한을 검사하지 않는 것으로 보이며, 데이터 노출은 아니지만 차트 메타데이터가 생긴다.

---

# 3라운드 실험 결과 (승인: 2026-10-11 사용자, `03b-gate3-round-decisions.md` 3-6)

- 승인 범위: X-14, X-15, X-17, X-18, X-20, X-21, X-22, X-23, X-24 (X-16 불필요, X-19는 8번 인증 결정 후). 클라우드 세션 안에서만 실행.
- DB 실험(X-14, X-15, X-17, X-24) 환경: PostgreSQL **16.10**(`postgres:16.10-bookworm`, 컨테이너 `g3x14-pg`, tmpfs 데이터, 볼륨 없음). 역할은 설계대로 `bi_owner`(schema `bi_data` 소유, 정적 표 소유), `bi_app`(런타임), `bi_readonly`를 만들어 각 역할로 접속(`psql -U`). 스크립트·원출력: `_workspace/gate3/experiments/x14.sql/.out`, `x15.sql/.out`, `x17.sh/.out`, `x24.sh/.out`, `x24b.sh/.out`(Git 제외).
- **정리:** `g3x14-pg`는 이름을 지정해 삭제했다(tmpfs라 볼륨 없음).
- **한계:** 이 결과는 PostgreSQL 16.10과 psql 세션 기준이다(앱의 pg8000 드라이버 경유 동작은 확인하지 않았다). 데이터는 모의 데이터이며 동시성 시험은 사람이 만든 타이밍(`pg_sleep`)이다.

## X-14. `ALTER DEFAULT PRIVILEGES`와 `FOR ROLE`, 역할 멤버십 (Y1 ㄴ의 입력)
| 시험 | 결과 |
| --- | --- |
| A1: `bi_app`이 `ALTER DEFAULT PRIVILEGES IN SCHEMA bi_data GRANT SELECT ON TABLES TO bi_readonly`(`FOR ROLE` 생략) 실행 후 `bi_app`이 표·뷰 생성 | `bi_readonly`가 **표와 뷰 모두 읽음**(`has_table_privilege` t). 같은 schema에서 `bi_owner`가 만든 표는 읽지 못함(f). `pg_default_acl`: `defaclrole=bi_app`, `{bi_readonly=r/bi_app}` |
| A2: `bi_owner`(멤버십 없음)가 `ALTER DEFAULT PRIVILEGES FOR ROLE bi_app …` | **거부**: `permission denied to change default privileges` |
| A2: 슈퍼유저가 `GRANT bi_app TO bi_owner`(기본 옵션: `INHERIT` t, `SET` t, `ADMIN` f) 후 `FOR ROLE bi_app` | **성공** |
| A2 멤버십 옵션별 | `INHERIT TRUE, SET TRUE`: 성공. **`INHERIT FALSE, SET TRUE`: 거부.** **`INHERIT TRUE, SET FALSE`: 성공.** `INHERIT FALSE, SET FALSE, ADMIN TRUE`: 거부 |
| A3: 슈퍼유저(db-bootstrap 후보)가 `ALTER DEFAULT PRIVILEGES FOR ROLE bi_app IN SCHEMA bi_data …` 후 `bi_app`이 표·뷰 생성 | `bi_readonly`가 표·뷰 모두 읽음 |
| `bi_owner`(스키마 소유자)가 `bi_app` 소유 객체에 대해 (`INHERIT TRUE` 멤버) | `CREATE OR REPLACE VIEW`, `ALTER TABLE ADD COLUMN`, `DROP VIEW`, `DROP TABLE … CASCADE`(의존 뷰 포함) **모두 성공** |
| 같은 작업, 멤버십 `INHERIT FALSE, SET TRUE` | `CREATE OR REPLACE VIEW`는 **`must be owner of view` 거부**. `SET ROLE bi_app` 후에는 성공 |
| 같은 작업, **멤버십 없음** | `ALTER TABLE`은 거부(`must be owner`), 그러나 **`DROP TABLE`/`DROP VIEW`(`CASCADE` 포함)는 `bi_owner`가 schema 소유자라서 성공** |
- 결론:
  - `FOR ROLE`로 다른 역할이 만들 객체의 기본 권한을 정하려면 그 역할의 **상속(`INHERIT`) 멤버**여야 한다(PostgreSQL 문서 본문 "member"와 16.0 릴리스 노트 "inherited roles"가 달랐던 점은 **상속이 필요한 쪽(릴리스 노트)** 으로 확인됨, `SET` 옵션은 필요 없음). 최소 권한 형태는 `GRANT bi_app TO bi_owner WITH INHERIT TRUE, SET FALSE`.
  - `bi_app`이 직접 `ALTER DEFAULT PRIVILEGES`(A1)를 실행하는 방식과 슈퍼유저가 실행하는 방식(A3)도 동작한다. 세 방식 모두 가능하므로 **어느 계정이 실행할지는 보안·운영 선택**(Y1 ㄴ 재질문).
  - schema 소유자 `bi_owner`는 멤버십이 없어도 schema 안 객체를 `DROP`(CASCADE 포함)할 수 있다(소유자가 아닌 `ALTER`/`REPLACE`는 상속 멤버십이 필요).
  - `bi_owner`가 `bi_app`의 상속 멤버이면 `bi_owner`는 `bi_app`의 권한(정적 표 DML 등)을 상속한다(`bi_owner`는 어차피 정적 표 소유자라 실질 증가는 `bi_app`이 가진 `bi_data` 권한 정도).

## X-15. 계정별 권한 매트릭스 (Y1·Y2의 입력)
설계: 슈퍼유저가 `bi_data`를 `AUTHORIZATION bi_owner`로 만들고 `public`에 `CREATE`를 `bi_owner`에게 부여, `bi_owner`가 `bi_data`에 `USAGE, CREATE`를 `bi_app`에, `USAGE`를 `bi_readonly`에 부여, 정적 표는 `bi_owner` 소유 + `bi_app`에 DML 명시 부여.
| 주체 | 시험 | 결과 |
| --- | --- | --- |
| `bi_app` | 정적 표 `INSERT`/`UPDATE`/`DELETE`(부여됨) | 성공(`DELETE`도 가능 → 행 삭제는 앱 수준 소프트 삭제·감사 기록으로 관리해야 함) |
| `bi_app` | 부여되지 않은 표 `SELECT`, `alembic_version` `SELECT` | 거부 |
| `bi_app` | `TRUNCATE`, `DROP TABLE`, `ALTER TABLE`, `CREATE INDEX`(정적 표) | **모두 거부**(`must be owner` / `permission denied`) |
| `bi_app` | `public`에 `CREATE TABLE` | 거부(`permission denied for schema public`) |
| `bi_app` | `CREATE SCHEMA`, `CREATE ROLE`, `SET ROLE bi_owner`, `DROP SCHEMA bi_data`, `ALTER SCHEMA bi_data OWNER` | **모두 거부** |
| `bi_app` | 자기 점검: `rolsuper`/`rolcreaterole`/`rolcreatedb`, `has_schema_privilege('public','public','CREATE')`, DB `CREATE` | 모두 f (BY3 시작 자가 점검 쿼리가 동작함) |
| `bi_app` | `identity` 열 표에 `INSERT`(시퀀스 권한 없이) | **성공**. `serial` 열 표는 **`permission denied for sequence`** → `GRANT USAGE ON SEQUENCE` 필요 (정적 표의 id는 `identity`가 권한 관리에 유리) |
| `bi_app` | 한 트랜잭션: 정적 표 `INSERT` + `bi_data`에 `CREATE TABLE`/`CREATE VIEW`/`ALTER TABLE`/`CREATE OR REPLACE VIEW` | 커밋 시 모두 반영. 중간 오류(중복 `CREATE TABLE`) 시 **등록 `INSERT`까지 모두 롤백**(B10 변경의 근거) |
| `bi_app` | `bi_data`에 함수·시퀀스·타입 생성, `GRANT SELECT … TO PUBLIC` | **성공**(schema `CREATE` 권한은 객체 종류를 가리지 않음, 자기 객체 권한을 임의로 부여 가능) → 런타임 코드가 만드는 DDL 종류를 제한하고 점검 필요 |
| `bi_readonly` | `bi_data` 표·뷰 `SELECT`(기본 권한으로) | 성공. `public` 정적 표 `SELECT`는 거부 |
| `bi_readonly` | `bi_data`·`public`에 `CREATE TABLE` | 거부 |
| `bi_readonly` | **`CREATE TEMP TABLE`** | **성공**(`PUBLIC`의 TEMP 권한, DB 이름이 변수라 `REVOKE`를 고정 SQL로 못 씀) → 알려진 성질로 기록 |
| `bi_readonly` | `SET default_transaction_read_only = off` 후 `INSERT`/`UPDATE` | **권한 거부**(실제 방어선은 권한, X-2와 일치) |
| `bi_readonly` | `bi_app`이 만든 함수 실행 | 성공(함수 `EXECUTE`는 기본 `PUBLIC`) → `bi_app`이 `SECURITY DEFINER` 함수를 만들면 권한 상승 경로가 될 수 있으므로 런타임 DDL 종류 제한이 필요 |
| `bi_owner` | 정적 표 `ALTER`, `alembic_version` 읽기 | 성공 |
- 결론: 설계한 2계정 구성에서 `bi_app`은 정적 표 구조·`TRUNCATE`·schema 생성·역할 생성이 모두 막히고, 동적 객체 DDL은 `bi_data` 안에서만 가능하다. 등록 + 물리 객체를 한 트랜잭션으로 처리하는 B10 변경은 `bi_app` 단일 로그인에서 동작한다. 남는 위험은 (1) 정적 표 `DELETE` 가능, (2) `bi_app`이 `bi_data`에 만들 수 있는 객체 종류(함수 등)와 임의 `GRANT`, (3) `bi_readonly`의 TEMP 권한이다. `pg_dump` 소유자 복원은 시험하지 않았다.

## X-17. `lock_timeout`과 뷰 재생성 (BY2, F-7의 입력)
| 시험 | 결과 |
| --- | --- |
| 유휴 상태에서 뷰 50개 `CREATE OR REPLACE` | 한 세션·한 트랜잭션이면 **0.16초**(별도 `psql` 호출 50번이면 6.19초는 접속 오버헤드) |
| 긴 읽기(6초 트랜잭션) 중 `lock_timeout=500ms`로 교체 | 약 0.5초 뒤 **`55P03 canceling statement due to lock timeout`**로 실패, 이후 새 읽기는 지연 없음(0.15초) |
| 같은 시험, `lock_timeout=2s`, 교체 대기 중(1.5초 시점)에 새 읽기 도착 | 교체는 약 2.1초 뒤 같은 오류로 실패. **새 읽기는 교체가 포기될 때까지 막혀 1.62초 지연**(X-7 재확인: 대기 중인 DDL 뒤에 새 읽기가 줄을 섬) |
| 짧은 읽기(수십~백 ms) 반복 중 교체(`lock_timeout=2s`) | 0.14초에 성공 |
| 정의가 **같은** `CREATE OR REPLACE VIEW`를 긴 읽기 중 실행 | **똑같이 대기하다 실패**(락을 먼저 잡음) → 정의 해시가 같으면 DDL 자체를 건너뛰어야 한다 |
| 긴 읽기 중 `GRANT SELECT` | 0.13초, **막히지 않음** |
| 오류 코드 | `55P03`(`lock_not_available`) |
- 결론: 뷰 단위 짧은 트랜잭션 + `SET LOCAL lock_timeout` + 재시도는 동작한다. 지연 영향은 **대기 중 새 읽기에 `lock_timeout` 만큼**이다(500ms ~ 2s 범위에서 선택). 해시가 같으면 건너뛰는 최적화가 필수다. 값 자체는 운영 부하에서 정해야 한다(5팀 × 10개 규모에서 읽기는 수십 ms였다, X-9).

## X-24. 동시 편집의 DB 동작 (Y8·Y9의 입력, READ COMMITTED)
| 시험 | 결과 |
| --- | --- |
| 같은 칸: A가 `a`를 10→11(미커밋), B가 `UPDATE … SET a=12 WHERE id=1 AND a IS NOT DISTINCT FROM 10` | B는 A가 커밋할 때까지 **기다린 뒤 `UPDATE 0`(0행)**. 최종 `a=11` (B의 값이 조용히 덮이지 않음) |
| 다른 칸: A가 `a`, B가 `b`(각자 자기 칸의 이전 값으로 가드) | B도 **`UPDATE 1`**, 최종 `a=11, b=21` (둘 다 반영) |
| B가 한 번에 두 칸(`a`, `b`)을 바꾸고 둘 다 가드 | A가 `a`를 바꿨으므로 B는 **0행**(바꾸는 칸 전체를 가드로 쓰므로 한 칸 충돌이 전체 취소) |
| 가드 없음 | **마지막 저장이 이김**(B의 12가 A의 11을 덮음) |
| 같은 칸을 A와 B가 **같은 값**으로 바꿈 | B는 0행(값이 같아도 가드는 "이전 값 10"이라 충돌로 보임) → 앱에서 "이미 같은 값이면 성공 처리" 규칙 필요 |
| A가 행을 숨김(보관) 처리하는 동안 B가 편집 | B는 0행(`hidden=false` 조건) → 0행의 원인(칸 충돌 vs 행 보관/삭제)을 앱이 다시 읽어 구분해야 함 |
| 여러 행 붙여넣기(한 트랜잭션): 2행이 A에 의해 바뀜 | B는 2행에서 기다린 뒤 0행 → 앱이 트랜잭션 전체를 롤백하면 모든 행 미반영(1·3행도) |
| 두 붙여넣기가 서로 반대 순서로 행을 갱신 | **`deadlock detected`**로 한쪽 실패. **행을 id 순으로 정렬해 갱신하면 교착 없음**(같은 순서로 대기) |
| `REPEATABLE READ` | 0행이 아니라 **`could not serialize access due to concurrent update`** 오류 |
| `SELECT … FOR UPDATE NOWAIT` | 즉시 `could not obtain lock on row` 오류; `SKIP LOCKED`는 잠긴 행을 건너뜀(편집 중 잠금 표시용 대안, 비추천 사유 유지) |
| 정의 버전 확인: 두 편집자가 version=1을 읽고 `UPDATE … SET def_version=def_version+1 WHERE def_version=1` | 먼저 커밋한 쪽만 성공, 나중은 0행 |
| `pg_advisory_xact_lock(1)` | 두 번째 세션은 첫 번째 트랜잭션이 끝날 때까지 대기(2.14초에 획득) |
- 결론: "칸 단위 값 비교 갱신"(Y8 (a)), "충돌 시 전부 취소"(Y8 (b)), "데이터셋 단위 직렬화 + 정의 버전 확인"(Y8 정의 편집)이 모두 PostgreSQL 16.10 `READ COMMITTED`에서 의도대로 동작함을 확인했다. 구현 시 지켜야 할 점: (1) 가드는 **바꾸는 칸의 이전 값**만 비교(`IS NOT DISTINCT FROM`으로 빈 칸 처리), (2) 0행의 원인 구분, (3) 붙여넣기 행은 **id 순서로 갱신**, (4) 같은 값으로 바꾸는 경우 성공 처리, (5) 대기 시간 상한(`lock_timeout`/`statement_timeout`)을 둔다. 앱 드라이버(pg8000) 경유 동작과 `rowcount` 노출은 확인하지 않았다.
