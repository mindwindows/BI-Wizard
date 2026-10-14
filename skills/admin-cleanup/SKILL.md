---
name: admin-cleanup
description: 잘못 만든 열이나 데이터셋을 관리자가 수동으로 정리하는 절차. 열·수식·데이터셋을 지우는(영구 삭제) 화면이나 API가 없을 때 쓴다(FU-2b의 데이터셋 보관은 삭제가 아니다). "잘못 만든 데이터셋을 지우고 싶다", "열을 없애고 싶다" 같은 요청에 해당한다.
---

# 관리자 수동 정리 (admin-cleanup)

> **검증 상태(2026-10-12): FU-1b(`datasets`·`dataset_columns`·`bi_data.ds_<번호>`)와 FU-1d(`formulas`·`formula_deps`, 뷰 `dv_<번호>`·`de_<번호>`) 단계는 실제 PostgreSQL(tmpfs 시험 DB, `bi_owner` 접속)에서 실행해 확인했다**(계산 열 삭제, 원본 열 삭제, 데이터셋 삭제와 그 뒤 backend 재시작·`views_failed_count` 0, 재시작 없이 D10으로 뷰 다시 만들기). `superset_datasets`(FU-1e) 단계는 그 표가 생기는 단위가 구현된 뒤에 검증해야 한다. 지금은 그 표가 없어 해당 SQL이 `relation … does not exist`로 실패하므로 **건너뛴다**(아래 각 절에 표시).

## 1. 목적
열·수식·데이터셋을 **지우는** 수단은 없다(`docs/decisions/04-modules.md` §10). FU-2b는 데이터셋을 보관·복구하는 API만 더했다(`skills/dataset-definition`의 "보관·복구"): **보관은 정리가 아니다.** 보관해도 `ds_`·`dv_`·`de_`와 데이터, Superset 가상 데이터셋·차트가 그대로 남고 읽기 전용 계정에도 계속 보이며 이름도 계속 쓰인다. 포털 기본 목록에서만 숨고 입력·정의가 잠긴다. 데이터를 지우거나 감추려면 이 문서의 수동 절차를 쓴다(영구 삭제 단위는 후속). 이미 보관된 데이터셋의 `status`가 `archived`로 남아 있어도 아래 삭제 절차는 그대로 쓸 수 있다. 잘못 만든 열이나 데이터셋이 남았을 때 **관리자가 직접** 안전한 순서로 정리하는 방법을 정한다. 이것은 서비스 기능이 아니라 **수동 운영 절차**이며 마이그레이션(D2)도 아니다. Alembic revision을 만들지 않고, 마이그레이션의 `DROP` 확인 규칙과도 별개다.

## 2. 사용 조건 / 사전 요구사항
- 사용하는 사람: 서버 DB와 Superset 관리자 화면에 접근할 수 있는 운영 담당 관리자. 일반 사용자와 정의 담당자는 쓰지 않는다.
- 쓰기 전에 사용자(요청자)에게 **무엇을 지우는지 확인**받는다. 되돌릴 수 없다.
- 환경: `local-environment` 통과 상태, `docker compose`로 postgres 접속 가능, Superset 관리자 로그인 가능.
- 계정: DB는 `bi_owner`(정적 표 소유, `bi_data` schema 소유자). `bi_app`·슈퍼유저로 하지 않는다. `bi_owner`는 `bi_data`의 `ds_*`(소유자 `bi_app`)를 schema 소유자 권한으로 `DROP`/`ALTER`할 수 있고 정적 표의 `DELETE`도 소유자라 가능하다(실제 확인). 비밀번호는 `.env`의 `POSTGRES_OWNER_PASSWORD`이고 이 문서·명령 기록·메신저에 적지 않는다. postgres 컨테이너 안에서 `psql`을 실행하면 로컬 접속(소켓·루프백)은 공식 이미지 기본 설정으로 비밀번호를 묻지 않는다(trust). 호스트에서 네트워크로 접속할 때만 비밀번호가 필요하며 환경변수 `PGPASSWORD`로 주고 명령 기록에 남기지 않는다.
- 다른 사람이 같은 데이터셋을 편집하지 않는 시간에 한다(입력자에게 미리 알림).

## 3. 입력
- 지울 대상: 데이터셋 번호 `<DS>`(`datasets.id`), 열이면 열 번호 `<COL>`(`dataset_columns.id`, 내부 이름 `c_<COL>`).
- 대상 확인용 정보: 팀 이름, 데이터셋 이름, 열 표시 이름(화면에서 확인).

## 4. 출력
- 정리된 상태: 정적 표 행, `bi_data`의 `ds_<DS>`·`dv_<DS>`·`de_<DS>`, Superset 가상 데이터셋이 모두 사라지거나(데이터셋 삭제), 열 정의·열·수식이 사라지고 뷰가 다시 만들어진 상태(열 삭제).
- 작업 기록: 누가 언제 무엇을 지웠는지 변경 요약이나 운영 노트에 적는다(비밀 값 제외). **이 수동 `psql` 정리는 서비스를 거치지 않으므로 감사 기록(`audit_log`, `skills/permission-management`의 "감사 기록 조회")에 남지 않는다.** 정리한 사실은 반드시 여기에 적는다. `audit_log`는 정리 대상이 아니며 지우지 않는다.

## 5. 실행 방법

### 5-1. 사전 확인 (읽기만, 영향 파악)
1. 대상이 맞는지 확인한다.
   - `SELECT d.id, d.name, t.name AS team FROM datasets d JOIN teams t ON t.id = d.team_id WHERE d.id = <DS>;`
   - 열이면 `SELECT id, display_name, kind, type FROM dataset_columns WHERE dataset_id = <DS> ORDER BY id;`
2. 영향 범위를 센다.
   - 입력 데이터: `SELECT count(*) FROM bi_data.ds_<DS>;` (데이터셋 삭제면 이 행이 모두 사라진다. 필요하면 먼저 내보내 둔다.)
   - 연결된 수식 열: `SELECT column_id FROM formula_deps WHERE depends_on_column_id = <COL>;` 열을 지우려는데 결과가 있으면 **멈추고** 그 수식 열을 먼저 정리한다(순환·깨짐 방지). 이 확인을 건너뛰어도 `formula_deps`의 외래키가 `DELETE FROM dataset_columns`를 막는다(확인됨).
   - Superset 등록(`0006` 이후: `superset_datasets` 표가 있다. `skills/dashboard-link`): `SELECT superset_dataset_id, display_name, sync_status FROM superset_datasets WHERE dataset_id = <DS>;`
   - Superset 차트·대시보드: Superset 관리자 화면에서 그 데이터셋을 쓰는 차트·대시보드를 본다(API 사용 시 `GET /api/v1/dataset/<SS>/related_objects`, 필터 전용 대시보드는 누락될 수 있어 "N개 이상"으로 본다, 03c X-23).
3. 영향을 요청자에게 알리고 **확정 답을 받는다.** 차트·대시보드는 포털이 대신 고치거나 지우지 않는다(`03b` 3-6). 필요하면 담당자가 먼저 정리한다.

### 5-2. 데이터셋 삭제 (순서 고정)
**파괴적 명령입니다. 5-1의 확인을 받은 뒤에만 실행합니다.**
1. **Superset 등록 정리(`0006` 이후):** Superset 관리자 화면(또는 서비스 계정 API)에서 가상 데이터셋 `<SS>`를 삭제한다. 차트가 있어도 막히지 않고 차트는 "데이터 없음" 상태가 된다(03c X-23). 뷰를 먼저 지우면 refresh가 원인 없는 422가 되므로 Superset을 먼저 한다.
2. **포털 등록 표 + 동적 객체를 한 트랜잭션으로** (`bi_owner`로 접속한 하나의 `BEGIN … COMMIT`, 실패하면 `ROLLBACK`; DDL도 롤백된다, 03c X-1):
   - `UPDATE datasets SET base_date_column_id = NULL WHERE id = <DS>;` (기준 열 순환 FK 해제)
   - `DELETE FROM formula_deps WHERE column_id IN (SELECT id FROM dataset_columns WHERE dataset_id = <DS>);`
   - `DELETE FROM formulas WHERE column_id IN (SELECT id FROM dataset_columns WHERE dataset_id = <DS>);`
   - `DELETE FROM dataset_columns WHERE dataset_id = <DS>;`
   - `DELETE FROM superset_datasets WHERE dataset_id = <DS>;` (`0006` 이후. 이 행을 먼저 지우지 않으면 `datasets` 삭제가 외래키로 막힌다. 포털 쪽 `bi_app`은 DELETE 권한이 없으므로 `bi_owner`로 한다)
   - `DROP VIEW IF EXISTS bi_data.de_<DS>; DROP VIEW IF EXISTS bi_data.dv_<DS>; DROP TABLE bi_data.ds_<DS>;` (`CASCADE`는 쓰지 않는다. 걸리는 객체가 있으면 원인을 확인한다. `ds_`를 지우면 그 표의 기간 인덱스·제약도 함께 사라진다. 뷰는 `ds_`에 의존하므로 반드시 먼저 지운다.)
   - `DELETE FROM datasets WHERE id = <DS>;`
   - 정적 표 `DELETE`는 `bi_owner`가 소유자라 가능하다. `bi_data`의 객체는 `bi_app`이 소유하지만 `bi_owner`는 schema 소유자라 `DROP`할 수 있다(03c X-14).
3. 서비스 재기동은 필요 없다. 시작 시 대조는 존재하는 데이터셋만 보고, 지워진 데이터셋은 `/api/health`의 `views` 개수에서 빠진다(재시작 뒤).

### 5-3. 열 삭제 (잘못 만든 열 하나)
**파괴적 명령입니다.** 그 열을 쓰는 수식(`formula_deps`)이 없고, Superset에서 그 열을 쓰는 차트가 없거나 요청자가 감수한다고 확인된 경우에만 한다. 열의 값이 사라진다.
1. 입력자 작업을 멈추게 한다. 아래를 `bi_owner`의 한 트랜잭션으로 한다.
2. 대상 데이터셋 행을 잠근다: `SELECT id FROM datasets WHERE id = <DS> FOR NO KEY UPDATE;` (서비스의 정의 변경과 같은 잠금, 06 §5)
3. 원본 열이면 뷰를 먼저 내리고 열을 지운다: `DROP VIEW IF EXISTS bi_data.de_<DS>; DROP VIEW IF EXISTS bi_data.dv_<DS>; ALTER TABLE bi_data.ds_<DS> DROP COLUMN c_<COL>;` (`IF EXISTS`를 쓴다: 뷰 만들기에 실패했던 데이터셋은 뷰가 없을 수 있다.) **계산 열이면 원본 표에 열이 없으므로(저장하지 않는다) `ALTER TABLE … DROP COLUMN`을 하지 않는다.** 기준 날짜 열이면 `datasets.base_date_column_id`를 먼저 `NULL`로 한다. **확인됨:** 그 열을 지우면 기간 유일 인덱스(`ux_ds_<DS>_period`)와 CHECK(`ck_ds_<DS>_period`)가 열과 함께 자동으로 사라진다(기준 날짜 열 삭제는 그래도 권하지 않음).
4. 정적 표에서 정리한다: 계산 열이면 `DELETE FROM formula_deps WHERE column_id = <COL>; DELETE FROM formulas WHERE column_id = <COL>;` 그다음 `DELETE FROM dataset_columns WHERE id = <COL>;` 마지막으로 `UPDATE datasets SET def_version = def_version + 1, def_hash = '' WHERE id = <DS>;` (해시를 비워 서비스가 뷰를 다시 만들게 한다. 값이 `NOT NULL`이라 빈 글자를 쓴다. 이 절차 뒤 서비스가 정상임을 확인했다: 재시작하면 해시가 달라진 뷰가 다시 만들어지고 `views_failed_count`가 0이며, 시작 자가 점검이 통과한다.)
5. 커밋 후 뷰를 다시 만든다. 방법 둘 중 하나: ① **backend를 재시작**(시작 시 해시 대조가 `def_hash`가 다른 데이터셋의 뷰만 다시 만든다) ② 재시작 없이 관리자가 `POST /api/checks/views/retry`에 `{"dataset_ids": [<DS>]}`를 보낸다(`formula-column` D10, 해시가 같아도 다시 만든다). 어느 쪽이든 `/api/health`의 `views_failed_count`가 0인지 확인한다. 이어서 Superset 동기 요청으로 가상 데이터셋을 새로고침한다. 그 사이(뷰가 없는 동안) 그 데이터셋의 행 조회는 계산 열을 빈 값으로 돌려준다. `refresh` 뒤 그 열을 쓰던 저장 차트는 데이터 오류가 된다(03c X-22).

## 6. 관련 UI / API / command / DB
- UI: Superset 관리자 화면(데이터셋·차트·대시보드), 포털 S9 관리자 현황(뷰 재생성 상태, 다시 시도).
- API: Superset `GET/DELETE /api/v1/dataset/<SS>`, `GET …/related_objects`(서비스 계정 또는 관리자). 정리 뒤 뷰 재생성에만 포털 `POST /api/checks/views/retry`(관리자)를 쓴다. 그 밖의 포털 쓰기 API는 쓰지 않는다.
- command: `docker compose exec postgres psql -U bi_owner -d <DB 이름>` (DB 이름은 `.env`의 `POSTGRES_DB`. 컨테이너 안 로컬 접속이라 비밀번호를 묻지 않는다).
- DB: 정적 표 `datasets`, `dataset_columns`(1b), `formulas`, `formula_deps`(1d), `superset_datasets`(1e), 동적 객체 `bi_data.ds_<DS>`(1b)·`dv_<DS>`·`de_<DS>`(1d).

## 7. 실패 시 확인 방법 / 복구
- 트랜잭션 중간 오류: `ROLLBACK`하면 DDL과 행 삭제가 모두 되돌아간다. 오류 메시지의 객체를 확인하고 5-1부터 다시 한다.
- 외래키 오류: 삭제 순서(수식 의존 → 수식 → 열 → 등록 → 데이터셋)가 맞는지 본다. `datasets.base_date_column_id`를 먼저 `NULL`로 했는지 본다(복합 FK `fk_datasets_id_dataset_columns`).
- `relation "superset_datasets" does not exist` 같은 오류: 아직 그 표가 없는 단위(1e 전)다. 해당 줄을 건너뛰고 `ROLLBACK` 후 다시 한다.
- 락 대기가 길면 서비스 쓰기가 끝난 뒤 다시 한다(`lock_timeout`을 짧게 걸고 재시도).
- 이미 커밋한 뒤에는 복구할 수 없다. 실수 방지가 최선이므로 5-1을 건너뛰지 않는다. 데이터가 필요하면 지우기 전에 `COPY`나 화면 붙여넣기용으로 따로 내보내 둔다.
- Superset을 먼저 정리했는데 포털 단계가 실패했으면 `superset_datasets`가 `failed`로 보일 수 있다. 포털 단계를 끝낸 뒤 행이 남아 있지 않은지 확인한다.

## 8. 검증 방법
정리 뒤 모두 확인한다.
- `SELECT count(*) FROM datasets WHERE id = <DS>;` 가 0(데이터셋 삭제) 또는 열 정의에서 `<COL>`이 없음(열 삭제).
- `SELECT table_name FROM information_schema.tables WHERE table_schema = 'bi_data' AND table_name IN ('ds_<DS>','dv_<DS>','de_<DS>');` 가 비어 있음(데이터셋 삭제).
- `/health` 응답의 `views_failed_count`가 0, 포털 S2 목록에 데이터셋이 없거나 열이 없음. backend 시작 자가 점검(`run_startup_checks`)은 정리 뒤에도 통과한다(확인됨).
- Superset 데이터셋 목록에서 가상 데이터셋이 사라졌거나 열이 갱신됨.
- 이 절차를 실제로 쓴 뒤 순서·SQL이 현재 스키마와 다르면 이 파일을 같은 작업에서 고친다(06·08 변경 시 함께 갱신).

## 9. 연관 Skill
- `dataset-definition`: 데이터셋·열 정의 기능과 이름 규칙(06)의 출처.
- `formula-column`: 계산 열(`formulas`·`formula_deps`)과 뷰 `dv_`·`de_`의 정의, 시작 시 해시 대조와 D10 다시 시도.
- `permission-management`: 감사 기록 조회(5-1). 서비스로 한 변경은 `audit_log`에 남지만 이 문서의 수동 `psql` 정리는 남지 않는다.
- `dashboard-link`: Superset 등록·동기 상태·다시 시도, 대시보드 연결(`superset_dashboards`)과 임베드 해제 절차. 정리 중에는 작업 스레드가 지워진 데이터셋의 요청을 조용히 건너뛴다.
- 정적 표 구조나 `bi_data` 이름 규칙이 바뀌면(영구 삭제 단위 포함) 이 Skill도 함께 고친다. 보관·복구(FU-2b)는 `status` 값만 바꾸는 서비스 기능이라 이 수동 절차를 바꾸지 않는다.

## 기준값 수동 정리 (FU-3)
기준값 항목·연도 값을 지우는 API는 없다. 잘못 만든 것은 `bi_owner`로 `psql`에서 `DELETE FROM reference_values WHERE item_id = <번호>;` 다음 `DELETE FROM reference_items WHERE id = <번호>;`로 지운다(값이 먼저, 외래키 때문). 먼저 R6(`GET /api/reference-items/<번호>/usage`)로 그 항목을 쓰는 수식이 없는지 확인한다. 쓰는 수식이 있으면 값이 사라져 그 칸이 `E4`가 되고, 그 수식을 다시 저장하면 `REF_UNKNOWN`이 된다. **이 수동 정리는 감사 기록에 남지 않는다**(운영 노트에 적는다).
