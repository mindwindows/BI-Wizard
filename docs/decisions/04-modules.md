# 04. 모듈 경계·기능↔Skill 대응·기능 단위 순서 (FU-1 범위)

**상태: 승인(2026-10-11, 03b 6절)** — architect. 05~08 초안의 부록 A 변경 제안과 문서 간 불일치를 통합했다. **EW-1·EW-3·EW-4 구현 결과 반영(2026-10-12, EW-5): 사실(상태·이름·개수)만 갱신했고 승인된 결정은 바꾸지 않았다.** **FU-2a(감사 로그) 계약 반영(2026-10-13, `03b` 29-1 범위): `audit` 모듈(§2-1·§3), 화면 S10(§4), 감사 기록 규칙·행위 목록(§5-1), Skill 대응(§6), 순서(§7), 부록 A. 행 보관·데이터셋 보관은 FU-2b로 미뤘다.**
- Gate ③ MODULARIZE. 의존 결정: 브리프 5절 2·3·6·7·8(스텁 전제)·9·10·11번(`docs/gate-status.md`), 범위 `03b` 5절(FU-1), 승인 `03b` 6절, 실험 `03c`. 원문은 `03b n-n`·`03c X-n` 참조로만 건다.
- [제안]·[미답] 표지는 `03b` 6-2에 따라 모두 승인된 것으로 읽는다(남은 [승인 필요]·AP는 `03b` 6-3 기준).
- 표지: **[미답]** 사용자가 답하지 않아 기본값으로 쓴 곳 / **[제안]** 문서 작성자가 낸 안(모음은 §9-2) / **해소(03c A-27)** 열 표시 이름 갱신 확인됨(조건부 가능, 08 §2-3).

## 1. 목적·범위·읽는 법
- 목적: FU-1의 모듈 경계, 화면, 제품 Skill, 구현 순서, 합격 기준 개요를 정하고 05~08이 같이 쓸 이름(부록 A)을 고정한다.
- 범위: FU-1 = 데이터셋 만들기(열 정의) · 팀/정의 담당자/입력자 권한(인증 스텁) · 입력 그리드 · 같은 행 수식/수식 보기/미리보기 · Superset 데이터셋 등록/임베딩 대시보드 보기(`03b` 5-1). 나머지는 §10에 항목만 둔다. 승인된 기능 축소: 브리프 4.3 역할별 열 편집 권한은 후속, 01 디자인의 "역할×데이터셋 격자"는 "팀×사용자"로 변경(`03b` 5-2 K2).
- 문서 관계: **04**(모듈·Skill·순서·이름) → **05** API 계약 / **06** 데이터 모델 / **07** 수식 엔진 / **08** Superset 임베딩. 05는 06·07·08을 받아 쓴다.
- 참조 규칙: ① 표·열·enum·역할·계정 이름은 부록 A가 기준이다. 05~08은 그대로 쓰고, 바꾸려면 부록 A를 먼저 고친 뒤 reviewer가 대조한다. ② 각 문서 맨 위에 의존 결정, 끝에 "후속 기능 단위에서 결정" 절을 둔다. ③ 구현 상세(클래스·SQL·props)는 담지 않는다. ④ AP 번호는 §9-1이 통합 번호이고 각 문서 번호와의 대응을 거기 적는다.

## 2. 모듈 경계
backend는 `app/<모듈>/`에 `router`(API) · `service`(로직) · `repo`(데이터 접근) 3층, frontend는 `src/features/<모듈>/`(화면 + API 훅)이다. 모듈 이름은 후보다. 기존 `config.py`·`db.py`·`health.py`는 `core`로 본다.

### 2-1. 공통 계층
| 이름 | 책임 | 소유 | 의존 | 금지 · 확장점 |
| --- | --- | --- | --- | --- |
| `core` | 설정, 오류 형식, DB 세션(`bi_app`, 미리보기용 읽기 전용 트랜잭션), `/health`, 시작 자가 점검(슈퍼유저·`CREATEROLE`·`CREATEDB`, `bi_data` 객체 종류[표·뷰·인덱스·제약만, 단 열이 소유한 `Identity` 시퀀스(`row_id`)는 허용], `standard_conforming_strings=on`, 07 §4-3), 포트 정의(`DatasetSyncPort`[데이터셋 단위·팀 단위 요청], 정의 변경 훅, `RowViewPort`), 정적 표 정의(`MetaData` 한 곳 = Alembic `target_metadata`) | 정적 표 정의만(쓰기 책임은 각 모듈) | 없음 | 슈퍼유저·`bi_owner` 접속 금지(시작 자가 점검). 업무 로직 금지 |
| `auth` | `current_user` 한 곳(신원 어댑터 → `CurrentUser`), 권한 판정(관리자 / 팀 정의 담당자·입력자 / 열람 = 인증된 모두), 사용자·팀·소속 **읽기 service**(다른 모듈이 팀 이름·코드를 읽는 유일한 길) | 없음(`users`·`teams`·`team_members` 읽기, 쓰기는 access) | core | 스텁은 개발·시험 전용, 기본 꺼짐·fail-closed이며 운영 설정에서 켜지면 시작 거부(`03b` 5-2 K3, §8). 확장점: 신원 어댑터 교체(8번 미결정) |
| `audit` (FU-2a) | 감사 기록 쓰기 함수(`record`)와 관리자 전용 목록 조회(05 F1). 행위 목록·`details` 허용 키(§5-1)를 한 곳에 둔다. 커밋·롤백은 하지 않고 호출한 쪽의 트랜잭션에 INSERT만 더한다 | `audit_log` (쓰기는 이 모듈의 `record`만) | core, auth(`require_admin`, 행위자 표시 이름은 auth 읽기 service로 일괄 조회) | UPDATE·DELETE 경로 없음. 호출자는 `access`·`dataset`·`superset` service(§5-1 표)뿐이고 `formula`·`entry`는 직접 부르지 않는다. 허용 키 목록 밖 `details`·행 값·수식 원문 금지. 확장점: 새 행위 = §5-1 표 한 줄 + `action` CHECK 교체(06 §2-1) + 시험 |
| `ddl` | 런타임 동적 DDL 유일 모듈, `ds_`/`dv_`/`de_`/`c_`/`e_` 이름과 인덱스·제약 이름(`ux_ds_<id>_period`, `ck_ds_<id>_period`) 규칙 함수 | `bi_data`의 표·뷰·인덱스·제약(생성·변경) | core | `text()`·`exec_driver_sql` 금지, 객체 종류 허용 목록(`bi-review` 7-4), 이 모듈 밖 DDL 금지, `bi_app`으로만 실행(`03b` 5-2 Z6) |

### 2-2. FU-1 기능 모듈
| 모듈 | 책임 | 소유 정적 표 | 소유 동적 객체 | 외부 의존(허용) | 확장점 |
| --- | --- | --- | --- | --- | --- |
| `access` | 팀·사용자·소속(역할) 관리, 비활성화, 최초 관리자 서버 명령, `/api/me`, 팀 이름 변경 뒤 팀 단위 동기화 요청 | `users` `teams` `team_members`(쓰기) | - | core(포트), auth, audit | 데이터셋별 예외 권한(후속) |
| `dataset` | 데이터셋·열 정의(타입, 필수·범위, 기준 날짜 열, 날짜 단위, 열 구분 태그), 정의 버전, 등록 + 원본 표 생성을 한 트랜잭션, **정의 변경 진입점**(§5) | `datasets` `dataset_columns` | `ds_<번호>` (ddl 경유) | core, auth, ddl, audit | 열 타입 등록, 검증 규칙 등록, 정의 변경 훅 호출 |
| `entry` | 한 기간 = 한 행 입력: 행 조회(계산 열 값·오류는 `RowViewPort`로 받음), 칸 단위 값 비교 갱신, 붙여넣기 일괄(충돌 시 전부 취소), 서버 재검증 | 없음 | `ds_<번호>` 행 읽기·쓰기(DDL 아님) | core(포트 포함), auth, dataset(정의 읽기) | 행·열 전환 보기를 나중에 추가할 수 있게 저장 형식 고정 |
| `formula` | 수식 파싱·정적 검사·순환 검사, `dv_` 뷰(와 오류 판정 뷰) 생성·시작 시 재생성(정의 해시), 미리보기, 수식 보기, 오류 칸·뷰 재생성 점검 | `formulas` `formula_deps` | `dv_<번호>`, `de_<번호>` (ddl 경유) | core, auth, dataset(정의 읽기·정의 변경 진입점 호출), ddl | 함수 사전, 리터럴 렌더러 접점 한 곳, `RowViewPort` 구현 |
| `superset` | 서비스 계정으로 가상 데이터셋 등록·열 새로고침, 동기 상태, 대시보드 연결(관리자), 입장권 발급, 임베딩 | `superset_datasets` `superset_dashboards` | 없음(Superset 쪽 역할·계정은 `superset-init`) | core, auth, dataset(읽기), ddl(이름 규칙만), audit(대시보드 연결 기록만), `httpx` → Superset | `DatasetSyncPort` 구현 |

## 3. 의존 방향 (순환 없음)
| 모듈 | 의존(→) | 의존받음(←) |
| --- | --- | --- |
| core | 없음 | 전부 |
| auth | core | audit, access, dataset, entry, formula, superset |
| ddl | core | dataset, formula, superset(이름 규칙만) |
| audit | core, auth | access, dataset, superset (formula·entry는 직접 호출하지 않음) |
| access | core, auth, audit | 앱 조립(`main.py`)만 |
| dataset | core, auth, ddl, audit | entry, formula, superset |
| entry · formula · superset | 각각 core, auth, dataset (+ formula: ddl, superset: ddl 이름·audit) | 없음 |
- 위상 순서: core → auth·ddl → audit → access·dataset → entry·formula·superset. 마지막 세 모듈은 서로 직접 의존하지 않는다. `audit`은 정방향 의존(호출자가 `audit`을 호출)이라 순환이 없다.
- 역방향 호출은 `core` 포트로 뒤집는다: dataset이 정의 변경 훅을 호출하면 formula가 등록해 뷰를 재생성하고, 정의/뷰가 바뀌면 `DatasetSyncPort`로 커밋 뒤 백그라운드 동기화를 요청하고(superset이 구현하고 자기 표에 상태를 기록, 행이 없으면 `pending`) entry는 계산 열 값·오류를 `RowViewPort`(formula 구현)로 읽는다. 팀 이름이 바뀌면(05 A4) access가 같은 포트로 팀 단위 동기화를 요청하고 superset이 그 팀의 모든 가상 데이터셋 이름을 갱신한다(08 §2-1). 팀·사용자 정보는 모든 모듈이 auth의 읽기 service로만 읽는다(access↔auth 순환 없음). 연결은 앱 팩토리 한 곳에서 한다. dataset은 superset을 읽지 않으므로 화면이 동기 상태를 따로 받아 결합한다(S2).

## 4. 화면 목록 (K9 기본값 "화면 목록 + 영역 개요"로 승인, `03b` 6-2)
01 디자인: C(3분할 작업공간) 기본 + 목록·권한·연결 관리는 B(콘솔형), 1920×1080, Inspector 접기·폭 조절. 세부 화면은 소단위마다 만들고 완료 때 사용자가 확인한다.
| 화면 | 영역 개요 | Skill |
| --- | --- | --- |
| S1 포털 셸·접근 안내(B) | 상단 Navigation, 작업 팀 선택(여러 팀 소속), 미등록 사용자에게 "접근 권한이 없습니다". 개발 빌드 한정 스텁 신원 전환기 | permission-management |
| S2 데이터셋 목록(B) | 이름·팀·날짜 단위·생성자·생성일, 동기 상태(`GET /superset/datasets`에서 받아 화면이 결합), 소속 팀 데이터셋 상단 정렬(`03b` 2-4), "새 데이터셋"(정의 담당자) | dataset-definition |
| S3 데이터셋 만들기(B 폼) | 팀·이름·날짜 단위 입력 후 작업공간으로 이동. 열은 작업공간에서 추가 | dataset-definition |
| S4 작업공간(C) | 중앙 입력 그리드, 우측 Inspector(열 기본·검증·수식), 수식 편집기(열 이름 칩·자동완성·쉬운 말 오류·미리보기 행), 계산 열 표시와 수식 보기(열람자 읽기 전용), 오류 칸 구별 표시 | data-entry, formula-column, dataset-definition |
| S5 점검(B) | 계산 오류 칸 목록(데이터셋·열·기간) | formula-column |
| S6 권한 관리(B, 관리자) | 팀×사용자 격자, 팀 만들기·소속·역할·비활성화, 저장 전 변경 요약 확인창 | permission-management |
| S7 대시보드 목록·보기 | 연결된 대시보드 목록, 선택 시 Embedded iframe, "차트 만들기" 새 창 링크와 작성자 안내문(지원 차트 6가지 목록, 차트에 시간 필터 필요, 팀 열; 08 §5) | dashboard-link |
| S8 대시보드 연결 관리(B, 관리자) | 대시보드 이름과 embedded uuid 수동 등록·해제 | dashboard-link |
| S9 관리자 현황(B, 관리자) | Superset 동기 상태·다시 시도(`superset` 모듈 API) + 뷰 재생성 실패·다시 시도(`/checks/views`, `formula` 모듈 API, `/health` 본문과 같은 정보). 화면·Skill은 `dashboard-link` | dashboard-link |
| S10 감사 기록 목록(B, 관리자, FU-2a) | 읽기 전용 표(일시·행위자·행위·대상·요약, 최신순, 50건 단위 페이지, F1). **필터 줄:** 기간(시작일·종료일 날짜 선택, 둘 다 선택 사항), 행위자(사용자 선택, A5 목록으로 채움), 대상 종류(팀·사용자·데이터셋·대시보드)와 대상 번호(대상 종류를 고른 뒤에만 입력 가능), 행위(한국어 이름, §5-1 표 15개). "조회" 누르면 첫 페이지, "필터 지우기" 제공. **요약**은 `details`를 쉬운 말로 풀어 쓴다(예: "이름 '가'→'나'", "역할 입력자→정의 담당자", "연결 해제"). 서버 `details`에 없는 정보는 보이지 않으며 행 값·수식 원문은 어디에도 없다. **빈 상태:** 필터가 없으면 "아직 기록이 없습니다", 필터가 있으면 "조건에 맞는 기록이 없습니다" + 필터 지우기. **비관리자:** 상단 메뉴에 항목이 없고, 주소로 직접 열면 403을 받아 "관리자만 볼 수 있습니다" 안내(목록·필터를 그리지 않음). 오류: 503이면 "잠시 후 다시 시도" + 재시도 버튼. 수정·삭제·내보내기 버튼 없음. 스크린샷 `fu2a-{화면}-{상태}.png`(목록, 필터, 빈 상태, 비관리자 거부, `03b` 29-2) | permission-management |

## 5. 모듈 간 규칙·확장점
- 층 규칙: router는 service만, service는 자기 repo와 다른 모듈의 service 함수만 호출한다. 다른 모듈 표의 쓰기는 소유 모듈의 service 함수로만 한다. SQL(SQLAlchemy 표현식)은 repo와 `ddl`에만 둔다.
- 정의 변경 진입점(dataset service, 06 §3-5): 순서 고정 = `datasets` 행 잠금 → `def_version` 확인 → 열 변경(원본 열·계산 열 INSERT, 계산 열 결과 형 `type` 갱신) → 정의 변경 훅 → `def_hash` 기록. formula가 직접 쓰는 것은 훅 안의 `formulas`·`formula_deps`와 `ddl` 뷰뿐이고, `dataset_columns`·`def_version`·`def_hash`는 진입점 함수가 쓴다(그래서 훅은 새 열 `id`가 있는 상태에서 불린다). 시작 시 재생성·재시도(05 D10)는 같은 진입점의 "버전을 올리지 않는" 형태다. 행 쓰기의 `datasets` 행 잠금·버전 확인도 dataset service 함수로 감싼다(06 §5).
- 경계 금지: 브라우저 → DB 직접 호출 금지. 브라우저 → Superset REST API 호출 금지(허용 접근은 Embedded iframe과 새 창 링크 둘뿐, 입장권은 FastAPI가 발급하고 서버가 직접 서명하지 않음). 프런트 API 경로는 `config.ts` 한 곳에서 `${basePath}/api`로 조립하고 하드코딩하지 않는다. 클라이언트가 보낸 `rls`·Superset 숫자 id는 받지 않는다(08). SQL 문자열 조립과 `text()` 금지.
- 확장점 합격선: 함수 추가 = 함수 사전 항목 1개 + 시험 사례(`03b` 5-2 K6) / 열 타입 추가 = 타입 등록 1곳 / 신원 방식 교체 = `auth` 1곳 / 보기 전환 = 저장 형식 변경 없이 화면만 추가.

## 5-1. 감사 기록 규칙 (FU-2a, `03b` 29-1, 표·열은 06 §2-1, 조회는 05 F1)
### 호출 방식: 포트가 아니라 `audit` service 직접 호출 [제안]
| 안 | 내용 | 판단 |
| --- | --- | --- |
| A. 직접 호출(제안) | 쓰기 service가 `audit.service.record(session, …)`를 같은 세션에서 부른다 | §5 층 규칙("service는 다른 모듈의 service 함수만 호출")에 맞고, `audit`은 core·auth 위에 있어 호출자(access·dataset·superset)가 아래를 부르는 **정방향**이다(§3 순환 없음). 포트 연결 누락 없이 import만으로 호출이 보장되고 시험이 호출 여부를 직접 단정한다 |
| B. `core/ports.py` 포트 | `AuditPort`를 core에 정의하고 audit이 구현, 앱 팩토리가 연결 | 포트는 **역방향** 호출(§3: 훅·동기·`RowViewPort`)을 뒤집는 장치라 이 경우 필요가 없다. 기존 포트는 미등록일 때 no-op 기본 구현(`DefinitionHooks` 빈 등록부, `NoopDatasetSync`)으로 조용히 넘어가는데, 감사에서는 연결 누락이 **기록 없는 변경**(fail-open)이 되어 부적합하다 |
- `record`는 `commit`·`rollback`을 하지 않고 호출한 쪽이 `session.commit()` **앞에서** 부른다(같은 트랜잭션, 06 §1·§5). INSERT가 실패하면 변경도 실패한다(기존 DB 오류 경로, 감사 없는 변경은 없다). 행위자 인자는 `CurrentUser`(→ `actor_source=user`) 또는 명시적 서버 명령 표식(→ `cli`, 행위자 NULL)이고 그 외는 오류다.
- **정의 변경 한 곳:** `dataset.definition.apply_definition_change`(§5)가 호출자가 넘긴 **행위 서술**(행위 이름과 `details` 구성 함수)을 받아 `changed=True`일 때만 훅 뒤·`def_version`·`def_hash` 기록 뒤·커밋 앞에서 `record`를 한 번 부른다. 그래서 B4·B5·B6·D4·D5는 이 함수 하나에서 기록되고 formula 모듈은 `audit`을 직접 부르지 않는다. 이 함수는 행위자(`CurrentUser`)를 받아야 하므로 해당 service 함수 시그니처가 늘어난다(구현 몫). B2는 이 함수를 쓰지 않으므로 `create_dataset`이 훅 뒤·커밋 앞에서 직접 기록한다.

### 기록 대상 행위 15개 (실제 service 함수와 1:1, `action`의 전체 값 = 06 §2-1 CHECK)
`details` 공통: `target_name`(대상 이름 스냅샷, 글자). `changes`는 `{필드: {from, to}}`(스칼라만). 모든 `def_version`은 변경 뒤 값. 금지 항목·크기는 06 §2-1.
| `action` | API | service 함수(파일) | `target_type` · `target_id` | 허용 `details` 키(`target_name` 외) |
| --- | --- | --- | --- | --- |
| `dataset.create` | B2 | `create_dataset` (`backend/app/dataset/service.py`) | dataset · 새 데이터셋 번호 | `team_id`, `date_unit`, `def_version` |
| `dataset.update` | B4 | `update_dataset` (같은 파일) | dataset · 데이터셋 번호 | `team_id`, `changes`(`name`·`date_unit`·`base_date_column_id`), `def_version` |
| `column.add` | B5 | `add_column` (같은 파일) | dataset · 데이터셋 번호 | `column_id`, `column_name`, `column_type`, `required`, `def_version` |
| `column.update` | B6 | `update_column` (같은 파일) | dataset · 데이터셋 번호 | `column_id`, `column_name`(변경 뒤), `changes`(`display_name`·`required`·`tag`·`position`), `rules_changed`(불리언, 규칙 값은 기록하지 않음), `def_version` |
| `formula_column.add` | D4 | `create_formula_column` (`backend/app/formula/service.py`) | dataset · 데이터셋 번호 | `column_id`, `column_name`, `result_type`, `ast_hash`, `def_version` |
| `formula_column.update` | D5 | `update_formula` (같은 파일) | dataset · 데이터셋 번호 | `column_id`, `column_name`, `result_type`, `result_type_changed`, `ast_hash_from`, `ast_hash`, `def_version` |
| `team.create` | A3 | `create_team` (`backend/app/access/service.py`) | team · 새 팀 번호 | `code` |
| `team.update` | A4 | `update_team` (같은 파일) | team · 팀 번호 | `changes`(`name`·`is_active`) |
| `member.set` | A8 | `set_member` (같은 파일) | team · 팀 번호 | `user_id`, `role`, `role_from`(새 소속이면 `null`) |
| `member.remove` | A9 | `remove_member` (같은 파일) | team · 팀 번호 | `user_id`, `role_from` |
| `user.create` | A6 | `create_user` (같은 파일) | user · 새 사용자 번호 | `is_admin` (`target_name`=표시 이름, `login_id`는 기록하지 않음) |
| `user.update` | A7 | `update_user` (같은 파일) | user · 사용자 번호 | `changes`(`is_admin`·`is_active`), `display_name_changed`(불리언, 이름 값은 `target_name`에만) |
| `user.bootstrap_admin` | 서버 명령 `create-admin` | `create_first_admin` (같은 파일, `backend/app/cli.py`가 호출) | user · 새 관리자 번호 | `is_admin`(항상 `true`). `actor_source=cli`, 행위자 NULL |
| `dashboard.create` | E4 | `create_dashboard` (`backend/app/superset/service.py`) | dashboard · 새 대시보드 번호 | `embedded_uuid`(E3가 모두에게 공개하는 값) |
| `dashboard.update` | E5 | `update_dashboard` (같은 파일) | dashboard · 대시보드 번호 | `changes`(`name`·`is_active`). `is_active`가 `true`→`false`면 "연결 해제", `false`→`true`면 "다시 연결"로 화면이 읽는다 |
- 멤버십은 별도 대상 종류 없이 `team`을 대상으로 하고 사용자는 `details.user_id`로 남긴다(복합 키라 `target_id` 하나로 못 가리키기 때문). 정의 변경은 열·수식도 `dataset`을 대상으로 하고 `column_id`를 `details`에 둔다(데이터셋 하나의 정의 이력이 `target_type=dataset`·`target_id` 필터 한 번으로 모인다).
- **기록하지 않는 것(`03b` 29-1 ②):** 행 값 입력·수정·붙여넣기(C2~C4), 입장권 발급(E6), Superset 동기 상태 변경(`superset_datasets`)·E2 접수, 시작 시 뷰 재생성·재시도(`bump=False`, 05 D10: 정의가 안 바뀜), 팀 이름 변경 뒤 동기화 같은 후속 부수 효과, 시험용 사용자 시드(`seed-stub-users`, 개발·시험 전용 명령이라 운영 기록 대상이 아님 [제안]), `/dev/*` 스텁 신원 전환. 조회(GET)는 기록하지 않는다.

### 정확히 1건 / 0건 규칙 (시험으로 단정)
1. **한 API 호출(또는 서버 명령 한 번) = 감사 행 최대 1건.** 여러 service 함수·표를 거쳐도 행위 이름은 호출이 대표하는 하나다. 예: D4는 열 INSERT + `formulas`·`formula_deps` + `dv_`·`de_` 재생성 + `def_hash` 기록이 한 트랜잭션이어도 `formula_column.add` 1건뿐이고, 훅 안의 `set_formula_result_type`·`clear_column_tag` 같은 내부 호출은 따로 기록하지 않는다. A4처럼 한 호출이 여러 필드(이름과 활성)를 바꾸면 **1건**에 `changes`로 함께 담는다. 기록은 호출당 한 번만 부르는 진입 지점(위 정의 변경 진입점, 또는 service 함수 끝)에 두고 repo·hook·내부 helper에서는 부르지 않는다.
2. **실제로 바뀐 것이 있을 때만 1건, 없으면 0건.** 0건인 경우: 값이 같은 PATCH(B4·B6·A4·A7·E5), 빈 본문 PATCH(A4·A7: 200), 같은 AST·같은 결과 형으로 다시 저장하는 PUT(D5: 현행 "같은 수식: 버전을 올리지 않는다"), 이미 같은 역할인 A8 재요청, 이미 활성 관리자인 `create-admin` 재실행(`False`, 멱등). 판정은 DB에 쓴 결과(변경된 행 여부, 쓰기 전 값과의 비교)로 하며 호출 인자로 하지 않는다. **현행 코드 중 이 규칙을 맞추려면 고칠 곳(구현 몫):** `set_member`는 역할이 같아도 UPDATE를 하고 `update_dashboard`는 값이 같아도 UPDATE를 하므로 변경 여부를 판정하는 조회·조건(`role IS DISTINCT FROM` 같은 비교)이 필요하다.
3. **실패·롤백이면 0건:** 409(`ALREADY_EXISTS`·`DEFINITION_VERSION_MISMATCH`·`LAST_ADMIN`·`TARGET_INACTIVE` 등)·404·422·503(`DEFINITION_BUSY`) 등 모든 오류 응답, 서버 명령의 `UserExistsError`, 트랜잭션 중간 실패는 감사 행도 남기지 않는다(같은 트랜잭션).
4. 경쟁 상황: A8의 동시 추가 경쟁(`IntegrityError` 뒤 역할 갱신)과 `create-admin` 동시 실행은 **실제로 일어난 전이**마다 정확히 1건이고 지는 쪽이 같은 전이를 다시 기록하지 않는다(재시도 경로에서 쓰기 전 값을 다시 읽는다).
5. 시험 단정(구현 단위가 만든다): 행위 15개 각각에 대해 ① 성공 1건과 `details` 키가 허용 목록과 같음 ② 변경 없음 0건 ③ 대표 오류 0건 ④ 롤백(훅·DDL 실패 주입) 0건 ⑤ 감사 INSERT 실패 주입 시 변경도 롤백. 목록 밖 쓰기 경로가 생기는 것을 막도록 "기록 대상 표(`users`·`teams`·`team_members`·`datasets`·`dataset_columns`·`superset_dashboards`)를 쓰는 service 함수는 §5-1 표에 있거나, 정의 변경 진입점 안에서만 불리는 helper(`add_formula_column` 등, 진입점의 기록에 포함)이거나, 제외 목록에 있다"를 확인하는 점검을 둔다 [제안].

## 6. 기능 ↔ 제품 Skill 대응표 (승인)
`skills/<기능>/SKILL.md`(제품 사용설명서, 형식 `product-skill-authoring`)다. `.claude/skills`·`.claude/agents`(개발 하네스)와는 별개이며, FU-1 Skill 5개는 소단위 완료 때 코드와 함께 만들고 연관 Skill은 양방향으로 적는다. 기존 `skills/local-environment`는 유지한다. API 경로는 05를 따른다.
| 소단위 | Skill 폴더 | 사용자 관점 기능 | 주요 UI | 주요 API 그룹(05) | 주요 DB | 연관 Skill |
| --- | --- | --- | --- | --- | --- | --- |
| FU-1a | `permission-management` | 팀·사용자·소속·역할 관리, 내 정보 | S1, S6 | `/api/me` `/api/users` `/api/teams` | users, teams, team_members | dataset-definition, dashboard-link |
| FU-1b | `dataset-definition` | 데이터셋 만들기, 열 정의(타입·필수·범위·기준 날짜 열·날짜 단위·태그) | S2, S3, S4 Inspector | `/api/datasets` `/api/datasets/{id}/columns` | datasets, dataset_columns, `ds_*` | permission-management, data-entry, formula-column, dashboard-link |
| FU-1c | `data-entry` | 한 기간=한 행 입력, 칸 편집, 엑셀 붙여넣기 | S4 그리드 | `/api/datasets/{id}/rows` (+ `/rows/paste`) | `ds_*` | dataset-definition, formula-column |
| FU-1d | `formula-column` | 같은 행 수식, 검사·미리보기, 수식 보기, 오류 칸, 뷰 재생성 점검 | S4 수식 편집기, S5 | `/api/datasets/{id}/formulas` (검사·미리보기·수식 보기), `/api/formulas/functions`, `/api/checks` (오류 칸·뷰 재생성) | formulas, formula_deps, `dv_*`, `de_*` | dataset-definition, data-entry, dashboard-link |
| FU-1e | `dashboard-link` | Superset 등록, 대시보드 연결·보기, 차트 작성 링크, 동기·뷰 현황 화면 | S7, S8, S9 | `/api/dashboards` (입장권), `/api/superset` (동기 상태·다시 시도) | superset_datasets, superset_dashboards | dataset-definition, formula-column, permission-management |
| FU-2a | `permission-management`(확장 [제안]) | 관리자의 감사 기록 조회(기간·행위자·대상·행위 필터). 아래 제안 참고 | S10 | `/api/audit-logs` | audit_log | dataset-definition, formula-column, dashboard-link (기록되는 변경을 일으키는 Skill, 양방향 한 줄) |
| (FU-1 운영) | `admin-cleanup` | 잘못 만든 열·데이터셋을 관리자가 수동 정리(FU-1에는 삭제·보관 수단이 없음). 초안: 1b·1d 구현 뒤 검증 | - | 없음(Superset 관리자 화면, `psql` `bi_owner`) | 06·08 정적 표와 `ds_*` `dv_*` `de_*` | dataset-definition, dashboard-link |
- `feature-unit`은 "한 단위 = Skill 하나"이므로 FU-1을 Skill 단위인 1a~1e로 나눠 각각 완료 기준을 적용한다(승인 `03b` 6-2). `admin-cleanup`은 수동 운영 절차 문서이며 코드 단위가 아니다(`03b` 6-2).
- **FU-2a Skill 제안(사용자 확인):** 감사 조회는 `permission-management`에 "감사 기록 조회" 절로 적는다. 근거: 기록되는 변경의 대부분이 팀·사용자·소속(이 Skill의 관리자 화면 군)이고 조회자도 같은 관리자이며, 엔드포인트가 하나·화면이 하나라 `feature-unit`의 "Skill 하나"를 새로 만들 만큼 독립 기능이 아니다. `admin-cleanup`(수동 정리 절차 문서)에는 넣지 않는다: 그 절차는 서비스를 거치지 않는 `psql` 작업이라 `audit_log`에 남지 않는다는 점만 한 줄 정정한다(현재 "서비스의 `audit_log`는 FU-2 이후" 문구 갱신). 대안: 별도 Skill `audit-log` 신설(기록 규칙이 늘면 분리). `dataset-definition`·`formula-column`·`dashboard-link`에는 "이 변경은 감사 기록에 남는다(15개 중 해당 행위)"를 연관 Skill 줄로 적는다. Skill 문서 수정은 이 문서 승인 뒤 구현 단위가 한다.
- 05의 `/health`·`/health/db`(H1·H2)는 `local-environment` Skill에, 개발·시험 전용 `/dev/*`(DV1~DV3)는 `permission-management` Skill에 둔다.

## 7. 기능 단위 순서 (승인)
### 7-1. FU-1 내부 구현 순서
| 순서 | 소단위 | 백엔드 → 프런트 | 선행 | 메모 |
| --- | --- | --- | --- | --- |
| 0 | 공통 기반 | core·auth 스텁(fail-closed)·오류 형식·`/health` 필드·시작 자가 점검·정적 `MetaData` → 셸·라우팅(STRIP=true 딥링크)·`config.ts` | EW-1, EW-3, EW-4(`03b` 5-4, 모두 구현·검증됨) | 모든 쓰기 API가 `current_user`에 의존. EW-1이 권한 전용 첫 revision `0002_bi_data_privileges`를 만들었다(구현됨, 06 §6) |
| 1 | FU-1a | users·teams·team_members(revision `0003`), 최초 관리자 명령, `/api/me`·팀·사용자 → 팀 선택, S6 | 0 | 사람 역할 권한 시험 시작 |
| 2 | FU-1b | datasets·dataset_columns(`0004`), `ddl`(등록 + `ds_` 생성 한 트랜잭션), 정의 버전 → S2, S3, Inspector | 1 | `bi-review` 7-4 첫 적용. 열 이름 노출은 `c_<번호>` + Superset 표시 이름(확인됨: 03c A-27, 08 §2-3). `dv_` 생성은 1d의 훅 등록 뒤부터라 1b 단독 단계는 `ds_`만 |
| 3 | FU-1c | 행 조회, 칸 단위 값 비교 갱신(pg8000 `rowcount` 첫 시험), 붙여넣기 일괄 → 그리드, 붙여넣기 파서 | 2 | 1d와 병렬 가능: 1c는 `RowViewPort` 기본 구현(계산 열 없음)으로 시작하고 1d가 formula 구현으로 교체 |
| 3 | FU-1d | formulas·formula_deps(`0005`), 파서·정적 검사·순환 검사, `dv_`(와 `de_`) 생성·정의 해시·시작 시 재생성, 미리보기, 수식 보기, 오류 칸, 뷰 점검 → 수식 편집기, S5 | 2 | 데이터셋마다 뷰 1개(수식 열이 없어도, 팀 열 포함)를 정의 변경 훅이 만든다(승인 `03b` 6-2) |
| 4 | FU-1e | superset_*(`0006`), 서비스 계정 등록, 연결 uuid 등록, 입장권 발급(`rls` 빈 목록, 속도 제한) → S7, S8, S9 | 1d | 하위 경로(STRIP true/false) + Embedded 재검증, 지원 차트 6가지 시험(08 P5) |
| 5 | FU-2a(FU-1 다음 단위, §7-2) | audit_log(`0007`), `audit.record`, 15개 기록 지점(access·dataset·superset), `GET /audit-logs` → S10 | 4(FU-1 전체) | 새 환경변수·의존성 없음. `DROP_APPROVED` 확인 1건(06 §6). 시험 단정은 §5-1 |
- EW 대응(`03b` 5-4): EW-1 계정 분리 = 0~1d의 DB 전제(구현·검증됨 2026-10-11), EW-3 Superset 서비스·발급 계정과 EW-4 `bi_guest` = 1e의 전제(구현·검증됨 2026-10-12, QA 독립 검증과 reviewer 차단 0건), EW-5 = 문서·하네스 정리(완료 2026-10-12), EW-6·7 = 통합 검증·reviewer 점검(완료 2026-10-12, QA 통과·reviewer 차단 0건). EW-2(업로드 상한)는 가져오기 단위로 넘긴다. 붙여넣기 요청 상한은 A안(1MiB 이하)으로 승인되어(`03b` 6-2) nginx `client_max_body_size` 변경은 FU-1에 없다.

### 7-2. FU-1 다음 단위 순서 제안 (세부 설계 없음, 의존 순서)
| 단위 | 이유 |
| --- | --- |
| **FU-2a 감사 로그**(확정, `03b` 29-1) | 이후 단위가 쓰기 흐름을 늘리기 전에 `audit_log`와 기록 지점(§5-1)을 먼저 넣어야 재작업이 적다. revision `0007`, `audit` 모듈, 15개 행위 기록, F1, S10. 선행: FU-1 전체(대상 service가 모두 있음) |
| FU-2b 보관·삭제 정책(후속, 질문 Q2~Q8은 그때) | 행 보관(복구)·데이터셋 보관과 뷰·인덱스 조건. 보관·삭제 행위는 FU-2b가 `action`·`target_type` CHECK를 교체해 감사에 추가한다. FU-2a에는 없다 |
| FU-3 기준값 표 | 수식 확장의 선행(이름 + 값 + 적용 시작일) |
| FU-4 수식 확장(이전 행 참조, 같은 데이터셋 집계, 기준값 호출) | 기준 날짜 열 필수 조건이 켜지는 첫 단위, FU-3 뒤 |
| FU-5 참조 열 | 입력 검증 + 점검 화면 확장, 보관·삭제 정책(끊어진 참조) 뒤 |
| FU-6 공통 요약 | 수식 열을 최종값으로 연결하므로 FU-4 뒤 |
| FU-7 엑셀 가져오기 | 그리드·정의·참조 열 검증을 재사용, 업로드 상한(EW-2)과 적재 시간 측정이 첫 작업. 업무 가치가 크면 FU-2 직후로 당길 수 있음(비구속) |

## 8. FU-1 합격 기준 개요 (`03b` 5-2·6-1에 있는 것만, 상세는 07·08)
- 훅의 embedded uuid 등록 대조는 H0 실측 2건으로 대체한다(`08-superset-embedding.md` §9, 실측 2 해석은 확정(사용자 판정 2026-10-13: 조건의 목적은 미등록 대시보드의 새 임베드 설정을 막는 것이고 `can_set_embedded`는 Admin만 가진다. `can_write Dashboard`는 내용 편집 권한이며, 조건 ①로 Superset이 읽는 데이터는 원래 모두에게 공개된 것뿐이다)).
- 수식 미리보기와 뷰 결과의 **불일치 0건**(X-26에서 `CAST` 적용 후에도 남은 22건의 원인 분석 포함, 차분 시험은 07 §6).
- X-26 주입 사례 10종 + 역슬래시 사례를 **회귀 시험으로 고정**. 완화책 3가지(세션 `standard_conforming_strings` 고정, 역슬래시·제어문자·NUL 거부, 생성 후 재읽기 비교·불일치 시 롤백)와 런타임 DDL `bi_app` 실행을 시험한다.
- 인증 스텁 fail-closed(`bi-review` 7-5): 스위치 `AUTH_STUB_ENABLED`는 미설정이면 꺼짐(기본 false)이고, 켜졌을 때 `APP_ENV`가 **명시적으로 설정**(코드 기본값 `local`이 채운 경우는 미설정으로 봄, 예: pydantic `model_fields_set`)되어 있고 허용 목록(local·test) 안일 때만 시작을 허용하며, 미설정·밖·알 수 없는 값이면 backend가 시작을 거부함을 시험한다. 프런트 스텁 UI는 `/dev/stub-users` 응답 여부로 판별(config.js 변경 없음)하고 시험용 사용자 시드 명령도 같은 거부 규칙을 따른다.
- K6 핵심 함수 전부에 시험 사례가 있고 함수 추가가 사전 항목 1개로 끝난다. K7: 빈 칸은 미입력으로 유지되고 결과도 빈 값(`MIN`·`MAX`·`SUM`·`SUMTAG` 빈 칸 **전파 확정**, `03b` 6-1), 글자 비교는 대소문자 무시, 오류 칸은 뷰가 NULL을 돌려주고(계산 열은 저장되지 않음) 화면에서 구별 표시되며 점검 목록에 노출. K7 ㄷ의 "빈 값으로 저장"은 계산 열이 저장되지 않는 뷰 설계에서 이 뜻으로 읽는다(승인 `03b` 6-2).
- **지원 차트 6가지(선, 막대, 표, 큰 숫자[추세 포함], 원형, 혼합[막대+선]) 모두 임베딩 화면에서 `bi_guest` 최소 권한으로 정상 표시**(`03b` 6-1, 08 P5). 추가 권한이 필요한 차트가 나오면 보고하고 멈춘다. EW-4 QA에서 6가지 모두 통과했고(추가 권한 불필요) FU-1e에서 포털 화면으로 다시 시험한다.
- K12 열 이름 방식 (나)는 서비스 계정 표시 이름 갱신이 확인됨(03c A-27, 조건부 가능: 전체 열 교체 `PUT`). 합격 기준은 08 P4.
- 공통 완료 기준은 `feature-unit`, 권한 매트릭스·왕복 시험은 EW-1 완료 기준(`03b` 3-6 BY4)을 따른다. Superset 쪽 합격 기준 P1~P5는 08 §6.

## 9. AP 승인 상태와 승인된 제안
### 9-1. AP 통합 표 (`03b` 6-3. `3-7`·`4-7`에서 승인된 것은 제외)
통합 번호는 기존 AP 번호를 유지하되 문서마다 겹친 번호(05의 AP-1·AP-2)는 새 번호를 준다. 다른 문서의 번호는 바꾸지 않는다.
| 통합 번호 | 항목 | 문서별 번호 | 상태 |
| --- | --- | --- | --- |
| AP-1 | `bi-review` 7-2 확장: guest 권한 목록 파일 규칙 + 서버 코드의 입장권 직접 서명 금지 | 08 AP-1 | 승인됨 |
| AP-2 | 가상 데이터셋 SQL을 `SELECT * FROM bi_data.<뷰>`로 고정, 서비스 계정만 등록 | 08 AP-2 | 승인됨 |
| AP-5 | db-bootstrap 고정 SQL: `bi_owner`에 `public` CREATE, `bi_data` 소유자를 `bi_owner`로 | 06 AP-5 | 승인됨(EW-1) |
| AP-9 | `bi_readonly` `statement_timeout` **30초 확정**(기준선과 다른 설정, 효과 확인됨: EW-1 QA에서 `pg_sleep(31)`이 30.2초에 취소) | 06 AP-9 = 08 AP-9 | 승인됨(EW-1 구현) |
| AP-10 | `bi-review` 7-4 문구: `Identity()` 암묵 시퀀스(`row_id`)를 "시퀀스 금지"의 예외로 명시(런타임 Alembic `Operations` 허용은 7-4에 이미 있어 06 AP-10 ②는 승인 항목이 아님) | 06 AP-10 | 승인됨 |
| AP-11 | `03-migration-tool.md` D2 안전장치를 "정적 표 대상"으로 좁힘 | 06 AP-11 | 승인·반영 완료 |
| AP-12 | backend → Superset 내부 주소는 compose 서비스 이름 기반 **코드 상수**(새 변수 없음), `SUPERSET_APP_ROOT`를 backend에 전달 | 08 AP-12 | 승인됨, 적용 완료(EW-3, 2026-10-12: `SUPERSET_INTERNAL_URL` 코드 상수와 `SUPERSET_APP_ROOT` 전달, HTTP 호출 코드는 FU-1e) |
| AP-13 | 새 환경변수 `AUTH_STUB_ENABLED`(기본 꺼짐)와 운영 판별: `APP_ENV` 명시 설정 + 허용 목록(local·test) 안일 때만 시작 허용(fail-closed, §8) | 05 AP-1 | 승인됨, 스위치·시작 거부 구현됨(EW-1, `backend/app/config.py`. 스텁 로그인 기능은 FU-1a) |
| AP-14 | 이 문서 부록 A의 이름·용어 추가·변경: `PERIOD_CONFLICT`·`WRITE_BUSY`와 05 오류 코드 사전, `de_`/`e_`, `row_id`·`team` 예약, `bi_author`/`bi_author_schema`, 셀 "오류 코드", `SUMTAG`, `RowViewPort`, 시작 자가 점검 항목 추가 | 05 AP-2, 06 §2, 07 §10, 08 §5 | 승인됨 |
| AP-15 | 새 런타임 의존성: backend `lark`, frontend 라우터·AG Grid Community·Superset Embedded SDK. `httpx`는 승인됨 | 07 §10, 08 §7 | FU-1 착수 때 버전·라이선스 확인 후 요청 |
| AP-16 | `superset-init` 확장(서비스·발급 계정, `bi_author*` 생성; `bi_guest`는 `03b` 4-2 Z2), 발급 전용 계정 변수 이름 `SUPERSET_GUEST_ISSUER_USER`·`_PASSWORD` 확정, 필요 시 compose `tmpfs`/`mem_limit`은 보고 후 적용 | 08 §7 | 승인됨, 적용 완료(EW-3·EW-4, 2026-10-12. 표식 계정 강제 복구는 `03b` 10-1) |
| AP-17 | 에이전트 정의 모델 변경: `env-engineer`·`qa-engineer`·`frontend-dev` haiku → sonnet(`CLAUDE.md` 변경 이력에 사유 기록) | - | 승인됨(`03b` 6-1) |
- 승인 항목이 아닌 것: 첫 관리자 서버 명령은 `03b` 5-2 K3 ㄷ로 결정됐고(새 환경변수 없음) 운영 서버에서 실행 가능한지만 운영자 확인 항목이다(`deploy-coordination.md` 35번). revision `downgrade`의 `op.drop_table`에 필요한 `DROP_APPROVED` 기록은 기존 D2 규칙의 적용일 뿐 새 승인이 아니다. 정규식 평가 의존성은 FU-1 밖(§10). 이 표에 없는 AP 번호는 결번이다: AP-3 정규식 의존성(후속), AP-4 위 설명, AP-6 해소(직접 서명 폴백 불채택), AP-7 브라우저 자동화 개발 의존성(필요해질 때), AP-8 작성자 계정 자동 생성(미채택).

### 9-2. 승인된 [제안] 모음 (`03b` 6-2, 문서 간 중복 제거, 항목 뒤는 출처)
| 분류 | 제안 | 출처 |
| --- | --- | --- |
| 권한 | 정의 담당자도 데이터 입력 가능 / 관리자는 팀 소속 역할 없이는 정의·입력 권한 없음 / 오류 칸 목록(D7)은 읽기 공개 | 06 §4-1, 05 §1·D7 |
| 단위·구조 | FU-1을 Skill 단위 1a~1e로 분할 / 수식이 없어도 데이터셋마다 `dv_` 뷰 1개 / 기준 날짜 열이 없는 데이터셋은 "같은 기간 하나·기간 정렬" 규칙이 없음 | 04 §6·§7, 06 §3-3·§3-4 |
| 값 표현 | `number`는 십진 문자열 `"1234.50"`·미입력 `null`(일반 JSON 숫자 기본값과 다름) / 임시 행은 화면 메모리 / 글자 NFC 정규화·상수 200자·서식 문자 거부 / 표시 이름 길이 상한(팀 50·데이터셋 100·열 100자)과 열 이름 금지 문자 / `teams.code` 형식 `^[a-z0-9_]{1,32}$` | 05 §1·§2-3, 06 §2, 07 §1·§3·§4-2 |
| 붙여넣기 상한 | **A 승인**: 요청 1MiB 이하·5,000행(B안 미채택). nginx 기본 1m이 먼저 413(JSON 아님)을 낼 수 있어 프런트가 JSON이 아닌 413도 처리 | 05 C4, 03c X-27 |
| 수식 | **오류 판정 구조 E-A 보조 뷰 `de_<번호>`** / 함수 `SUMTAG`·`[열 이름]` 문법 / `ROUND*` 자릿수 상수·`&` 숫자 자동 변환 불가·글자 대소 비교 제외 / 열 태그는 숫자 열에 하나 / 미리보기 20행·5초·사용자당 1건 + 전역 동시 상한 / 상수 부분식 오류는 C0가 상수 SELECT로 거부 / K7 ㄷ "오류 칸은 빈 값으로 저장"을 "뷰가 NULL을 돌려줌(계산 열은 저장하지 않음)"으로 읽는 재해석 | 07 §2-2·§3·§3-1·§5, 06 §3-4 |
| 데이터 모델 | 필수·범위는 앱 검증 / `row_id` 둠 / 열 단위 UPDATE GRANT로 `team_id`·`kind` 불변을 DB가 강제, `type`은 계산 열 결과 형 때문에 갱신 허용(raw 열 type 변경 금지는 앱 규칙) / 열거는 `text` + CHECK, 제약 이름 규칙 / `teams.name` 유일 / 기준 날짜 열·`date_unit`은 행 0개일 때만 변경 / 정의 변경은 `datasets` 행 `FOR NO KEY UPDATE` 한 가지 잠금 / 행 쓰기에 `expected_version` 일치 요구 / 기준 날짜 열은 `required`로 취급 / `bi_data` 소유자 `bi_owner` | 06 §1~§3·§5·§6 |
| API | `/health` 새 필드는 메모리 값(worker 1개 전제) / `E3`가 `embedded_uuid`를 모두에게 노출(입장권 요청은 포털 id만 받음) / `E1` 상태는 읽기 공개·`last_error`는 관리자 / `LAST_ADMIN` 보호 / 검사(D2) 실패도 200 / 스텁 쿠키 방식 / D6 응답에 원문 없음 / `WRITE_BUSY` 재시도 코드 / 기존 행 수정은 `expected` 필수 | 05 §1·§2·§3·§6 |
| Superset | guest 조건부 2권한은 지원 차트에 필요하지 않을 때만 제외(`can_time_range`는 포함) / 발급 계정 REST(JWT) 2권한 / 작성자 역할 `bi_author`·`bi_author_schema` / 가상 데이터셋 이름 형식·공개 안내 문구 / 서비스 계정 이름 변경 금지 / 훅은 형식·`rls`·개수·유형·`user`만 거부하고 임베드 uuid 존재는 Superset 기본 검사가 확인(포털 등록 표 일치 검사는 FU-1e 이월) / 대시보드 PDF·이미지 내보내기는 서버가 못 막으며 불변식에 따라 수용 | 08 §2~§5 |

## 10. 기능 축소 기록 · 후속 기능 단위에서 결정
"사용자 승인" 열은 `03b` 6-2로 모두 승인됐다(기능 축소 항목 전부 승인).
| 항목 | 구분 | 사용자 승인 | 담당 단위·근거 |
| --- | --- | --- | --- |
| 정규식·유일성 검증(브리프 4.3은 4종, FU-1은 필수·범위만), 정규식 평가 의존성 | 기능 축소 | 승인됨 | 후속 단위, `03b` 5-2 |
| 글자 대소 비교(`<` `>`) 제외, `ROUND*` 자릿수는 상수만 | 기능 축소(수식 함수 범위) | 승인됨 | 07 §2-2 |
| 같은 기간 행을 정의 담당자가 끌 수 있는 설정(`03b` 3-4 Y9 (a))은 FU-1에 없음(기준 날짜 열이 있으면 기간당 한 행 고정) | 이월 | 승인됨 | 후속, 06 §3-1 |
| 열 `type`·`kind` 변경 금지(FU-1), 데이터 있는 열의 이름·타입 변환 흐름. 기준 날짜 열의 타입 변경 금지는 결정됨 | 기능 축소(브리프 4.3 "변환 미리보기 후 확인") | 승인됨 | 06 §3-3, 07 §8 |
| `audit_log` 기록 시작: FU-1의 정의 변경은 기록하지 않았다. **FU-2a가 정의 변경·팀·소속·사용자·대시보드 연결 15개 행위를 기록한다**(`03b` 29-1, K4 변경 기록 범위 답). 아직 기록하지 않는 것: 행 값 수정·입장권 발급(제외 결정), 삭제·기준값 변경 행위(해당 기능이 생길 때), 보존·삭제 정책(자동 삭제 없음) | 구현 단위(FU-2a), 나머지 후속 | 승인됨(`03b` 29-1) | FU-2a, 후속 |
| 행·열·수식·데이터셋 보관·삭제 없음: FU-1에서는 잘못 입력한 행은 칸 비우기만 가능. FU-2a에서도 같음 | 범위(`03b` 5-1, 29-1 ①) | 승인됨 | FU-2b, 05 §2-3 |
| 잘못 만든 열·데이터셋의 수동 정리: FU-1에는 화면·API가 없어 관리자 수동 절차를 문서로 둠 | 후속 | 승인됨 | `skills/admin-cleanup/SKILL.md`(초안), FU-2 |
| 역할별 열 편집 권한, 데이터셋별 예외 권한 | 기능 축소 | 승인됨(`03b` 5-2 K2) | 후속 |
| 이전 행 참조, 같은 데이터셋 집계, 기준값 표·호출, 참조 열, 공통 요약, 엑셀 가져오기 | 후속 단위 | 해당 없음(범위 결정) | FU-3~FU-7 |
| 미답 질문 K5(소급·마감), K8(추가·교체), K10(보관·비활성), K11 ㄱ·ㄴ·ㄹ(재업로드·시트·개수 상한) | 후속 질문(K4 변경 기록 범위는 `03b` 29-1로 답함) | 해당 단위에서 질문 | FU-2b~FU-7 |
| 8번 인증 방식, 스텁 안전장치 최종 설계, X-19, Explore 자동 로그인, 입장권 `user` 식별자 교체 | 미결정 | 방식 확정 때 | 운영자 답 뒤 |
| 행·열 전환 보기, 같은 날짜에 여러 행이 필요한 데이터셋, 그 밖의 수식 함수·"건너뛰는 합계"(`03b` 6-1) | 후속 | 해당 단위에서 | 후속 |
| 가져오기 의존성(`python-multipart`·`openpyxl`·`defusedxml`·`rapidfuzz`)과 상한(EW-2) | 후속 | 착수 때 요청 | FU-7 |
| 기존 엑셀 이관 도구 | 범위 제외(`03b` 4-6) | 해당 없음 | 필요해지면 추가 |

---

## 부록 A. 용어·엔티티 사전 (05~08이 그대로 쓴다. **임의 변경 금지**: 바꾸려면 이 부록을 먼저 고친다)
(결정) = `03b` 근거가 있는 이름, (제안) = 작성자 제안이며 `03b` 6-2·6-3(AP-14)으로 승인됐다. 영문 이름은 확정이다. 타입·제약은 06이 정한다.

### A-1. 용어
| 용어 | 뜻 | 식별자·표기 |
| --- | --- | --- |
| 팀 | 데이터셋 소유 단위. 관리자가 만들고 소속을 지정, 한 사용자가 여러 팀에 속할 수 있음 | `teams`, 불변 `code`(필터 값), 바꿀 수 있는 `name` |
| 관리자 / 정의 담당자 / 입력자 | 팀·소속·연결 관리, 모든 열람(정의·입력 권한은 아님) / 팀의 데이터셋 생성·열·수식 편집 / 데이터 입력 | `users.is_admin` / `team_members.role` = `definer` / `entry`. 관리자의 정의·입력 권한은 팀 소속 역할로만, 정의 담당자도 입력 가능(승인 `03b` 6-2) |
| 열람자 | 인증된 모든 사용자(전 팀 데이터·수식 열람) | 별도 역할 값 없음(`03b` 1-3) |
| `current_user` | 접속자를 알려 주는 단 한 곳, 스텁은 개발·시험용 신원 흉내 | `CurrentUser`(id, display_name, is_active, is_admin, memberships) |
| 데이터셋 | 화면 용어("표"·"뷰"는 화면에서 안 씀). 내부 번호 = `datasets.id` | 원본 표 `bi_data.ds_<번호>`, 수식 뷰 `bi_data.dv_<번호>` (결정 2-6) |
| 열 | 원본 열(`raw`) 또는 계산 열(`formula`). 내부 번호 이름과 표시 이름이 따로 있음. 표시 이름은 `[` `]` `"`·제어문자를 쓸 수 없고 `team`·`팀`·`row_id`·`행 번호`는 예약, 길이 상한이 있음 | `c_<번호>`(번호 = `dataset_columns.id`), `display_name`. Superset에는 `c_<번호>` + 표시 이름(`verbose_name`, 확인됨: 03c A-27) |
| `RowViewPort` | entry가 행 조회에서 계산 열 값·오류를 받는 `core` 포트. formula가 `dv_`와 `de_`를 `row_id`로 결합해 구현하고, 1d 전에는 계산 열 없는 기본 구현 | 07 §3-1·§9 |
| 행 고유 번호 / 임시 행 | 행을 지정하는 번호(갱신·충돌 응답·순서 안정) / 필수 칸을 다 채우기 전 화면 메모리에만 있는 새 행(서버·`ds_`에 상태 없음) | `row_id` (bigint identity, PK) / draft(05 §2-3) |
| 기준 날짜 열 / 날짜 단위 | 기간을 정하는 `date` 열(이전 행·기준값·요약 연결에 쓸 때만 필수) / 일·월·연, 시각 없음, 기간의 첫날로 저장 | `datasets.base_date_column_id`, `datasets.date_unit` (결정 2-2, 2-3 W3) |
| 한 기간 = 한 행 | 저장·입력 모두 기간 하나가 행 하나, 항목은 열 | 기준 날짜 열이 있으면 같은 기간 행은 기본 하나(`03b` 3-4 Y9) |
| 팀 열 | 모든 `dv_` 뷰에 자동으로 붙는 열, 값은 팀 코드 | 출력 열 예약 이름 `team`·`row_id`. `dv_` 열 순서는 `team`, `row_id`, `c_<번호>` 오름차순 (06 §3-4, 07 §8) |
| 열 구분 태그 | 정의 담당자가 열에 붙이는 이름표(숫자 열에 하나), 같은 태그 열의 합산에 쓴다 | `dataset_columns.tag`, 함수 `SUMTAG("태그")` (07 §2-2) |
| 함수 사전 | 수식 함수를 이름 → 규칙·변환으로 등록하는 구조 | formula 모듈 확장점(결정 5-2 K6) |
| 미입력 / 오류 칸 | 값이 비어 있음(0이 아님), 결과도 빈 값 / 계산 오류로 빈 값이 된 칸. 뷰가 NULL을 돌려주며 계산 열은 저장되지 않음. 화면에서 구별·점검 목록 | NULL (결정 5-2 K7). 오류 판정은 보조 뷰 `de_<번호>`(열마다 `e_<열 번호>`, 승인 `03b` 6-2) |
| 오류 코드(셀) | 계산 오류 칸의 종류: `E1` 0으로 나눔, `E2` 글자 길이 범위, `E3` 날짜 범위. **05의 API 오류 코드(`error.code`)와 별개** | 07 §2-2, 05 §3 |
| 값 표현(API) | `number`는 십진 문자열 `"1234.50"`, 미입력 `null`, 날짜 `YYYY-MM-DD`(월·연도 첫날) | 05 §1 (06 `numeric`·07 `NUMERIC`과 맞음) |
| 수식 보기 / 미리보기 | 계산 열의 수식을 열 이름으로 풀어 읽기 전용 표시(AST에서 생성, `formulas.expression`은 보관용 원문) / 저장 전 일부 행 계산(뷰와 같은 변환기) | 07 §9 (결정 1-6, 2-3 W7) |
| 정의 버전 / 정의 해시 | 데이터셋 정의 변경 번호(충돌 확인) / 뷰 SQL 구조 해시(시작 시 재생성 판단) | `datasets.def_version`, `datasets.def_hash` (결정 3-4, 2-3 W2) |
| 정적 표 / 동적 객체 | Alembic이 관리하는 포털 표(`public`, 등록 표 포함) / 런타임 DDL이 만드는 `ds_`·`dv_`·`de_`(`bi_data`) | 소유 계정 `bi_owner` / `bi_app` (결정 2-3 W1, 3-2) |
| 서비스 계정 / 발급 전용 계정 | Superset 데이터셋 등록·새로고침용 / 입장권 발급용(서로 분리) | `SUPERSET_SERVICE_USER`·`_PASSWORD` / `SUPERSET_GUEST_ISSUER_USER`·`_PASSWORD`(AP-16 확정). 기본 계정 이름 `bi_service`·`bi_guest_issuer`, 역할은 같은 이름 하나씩(구현됨 EW-3) |
| 입장권(guest token) / embedded uuid | 대시보드 임베드용 5분짜리 접속 허가, `rls`는 항상 빈 목록 / 관리자가 수동 등록하는 임베드 번호 | `superset_dashboards.embedded_uuid` (결정 4-2) |
| 가상 데이터셋 | `dv_` 뷰를 읽는 Superset 데이터셋(읽기 쉬운 이름) | 이름 `[<팀 표시 이름>] <데이터셋 표시 이름>` (결정 3-3 Y6) |
| 감사 기록 / 행위자 / 행위 / 대상 | 정의·권한·대시보드 연결 변경의 누가·언제·무엇을 남긴 추가 전용 기록(화면 용어는 "감사 기록", 수정·삭제 없음, 자동 삭제 없음) / 변경을 일으킨 사용자(서버 명령이면 비어 있음) / 바뀐 일의 종류 15가지 / 바뀐 팀·사용자·데이터셋·대시보드 | `audit_log`, `actor_user_id`·`actor_source`, `action`, `target_type`·`target_id` (결정 `03b` 29-1, §5-1, 06 §2-1) |

### A-2. 엔티티
| 표 | 핵심 필드 후보 | 소유 모듈 |
| --- | --- | --- |
| `users` | id, login_id(유일, 8번 후 종류 확정), display_name, is_admin, is_active, created_at | access |
| `teams` | id, code(유일·불변), name(유일), is_active, created_at | access |
| `team_members` | team_id, user_id, role(`team_role`), PK(team_id, user_id) | access |
| `datasets` | id, team_id(불변), name, date_unit, base_date_column_id, status, def_version, def_hash, created_by, created_at | dataset |
| `dataset_columns` | id, dataset_id, display_name, type, kind, required, rules(범위 등), tag, position | dataset |
| `formulas` / `formula_deps` | column_id(유일), expression(보관용 원문), ast(열 번호 참조), ast_hash / column_id, depends_on_column_id | formula |
| `superset_datasets` | dataset_id, superset_dataset_id, display_name, sync_status, synced_at, last_error(text, 사유 요약) | superset |
| `superset_dashboards` | id, name, embedded_uuid(유일), is_active, created_at | superset |
| `bi_data` 동적 객체 | `ds_<id>`: `row_id` PK + `c_<열 id>`. `dv_<id>`: `team`, `row_id`, `c_<열 id>`. `de_<id>`: `row_id` + `e_<열 id>`. 인덱스·제약 `ux_ds_<id>_period`, `ck_ds_<id>_period` | ddl 경유(dataset·formula) |
| `audit_log` (FU-2a) | id(bigint), occurred_at, actor_user_id(NULL 허용), actor_source(`audit_actor_source`), action(`audit_action`), target_type(`audit_target_type`), target_id, details(jsonb) | audit |
- 이름 예약(후속 단위가 정함): 기준값·공통 지표·연결·가져오기 원본 정보 표. 동적 객체 이름은 번호 기반만 쓴다. (`audit_log`는 FU-2a에서 정의됐다: 06 §2-1)

### A-3. enum 값과 계정·객체 이름
| 이름 | 값 · 설명 |
| --- | --- |
| `team_role` | `definer`, `entry` (관리자는 `users.is_admin`). 모든 열거는 `text` + 이름 있는 CHECK (06 §1) |
| `date_unit` | `day`, `month`, `year` |
| `column_type` | `text`, `number`, `date`, `boolean`, `choice` (참조 타입 `reference`는 후속) |
| `column_kind` | `raw`, `formula` |
| `dataset_status` | `active`만 (`archived`·`deleted`는 보관·삭제 단위가 CHECK를 바꿔 추가) |
| `audit_action` | 15개: `dataset.create` `dataset.update` `column.add` `column.update` `formula_column.add` `formula_column.update` `team.create` `team.update` `member.set` `member.remove` `user.create` `user.update` `user.bootstrap_admin` `dashboard.create` `dashboard.update` (§5-1 표, `text` + 이름 있는 CHECK `ck_audit_log_action`, 후속 단위가 CHECK를 교체해 추가) |
| `audit_target_type` | `team`, `user`, `dataset`, `dashboard` (멤버십은 `team`, 열·수식은 `dataset`을 대상으로 한다) |
| `audit_actor_source` | `user`(포털 요청, 행위자 필수), `cli`(서버 명령, 행위자 NULL) |
| `sync_status` | Superset 등록 동기화 상태(화면 문구 "동기 상태"): `pending`(등록 행이 없거나 갱신 필요), `registered`, `failed` |
| API 오류 코드(05 §3) | 충돌 `CELL_CONFLICT`, `PASTE_CONFLICT`, `PERIOD_CONFLICT`, `DEFINITION_VERSION_MISMATCH`, 재시도 가능 `WRITE_BUSY`(행 쓰기 락 대기·교착). 나머지 코드는 05 §3 사전을 따른다 |
| DB 계정·schema | `bi_owner`, `bi_app`, `bi_readonly`, `bi_data`, `public` (결정 3-2). 그 밖에 Superset 메타 DB `superset`과 소유 역할 `superset_meta`(03a). 모두 코드 상수이고 `db-bootstrap`이 만든다(구현됨 EW-1) |
| Superset | `bi_guest`(guest 역할, 결정 4-2 Z2), 서비스 계정 / 발급 전용 계정(위)과 역할 `bi_service` / `bi_guest_issuer`, 작성자 역할 `bi_author`(Gamma 복사본)와 `bi_data` schema 보조 역할 `bi_author_schema` (08 §5). 구현된 권한 개수: `bi_service` 4, `bi_guest_issuer` 2, `bi_author_schema` 1, `bi_guest` 4, `bi_author` 6.1.0 Gamma 복사본 95, `Public` 0(EW-3·EW-4 QA 실측) |
