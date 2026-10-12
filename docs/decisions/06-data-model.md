# 06. 데이터 모델·권한·마이그레이션 계획 (FU-1 범위)

**상태: 승인(2026-10-11, 03b 6절)** — architect. 이름·enum은 04 부록 A를 그대로 쓴다. 코드·전체 DDL은 담지 않는다. EW-1 구현 결과 반영(2026-10-12, EW-5): §4-2·§6·§8의 상태 표기와 구현 위치만 갱신했고 승인된 설계는 바뀌지 않았다.
- 의존 결정: 브리프 5절 2·3·8(스텁 전제)·9·11번, `03b` 2-2·2-3·2-6·3-2·3-4·3-6·4-1·4-3·5-2, 실험 `03c`. 사용자 결정은 바꾸지 않고 원문은 `03b n-n`으로만 건다.
- [제안]·[미답] 표지는 `03b` 6-2에 따라 모두 승인된 것으로 읽는다(남은 [AP-n]은 `03b` 6-3 기준).
- 표지: **[제안]** 이 문서가 처음 내는 안 / **[미답]** 사용자 답 없음 / **해소(03c A-27)** 열 표시 이름 갱신 확인됨(§7) / **[AP-n]** §8 승인 필요. 근거: `03c X-n` = 우리 환경(PostgreSQL 16.10) 실측(**확인됨**), 공식 문서는 REL_16_STABLE(16.15) 기준(마이너 차이), 그 밖은 **추정**.

## 1. 설계 원칙
| 원칙 | 내용 | 출처 |
| --- | --- | --- |
| 정적/동적 분리 | 정적 표는 `public`(`bi_owner` 소유, Alembic 생성), 동적 객체는 `bi_data`(`bi_app` 소유, 런타임 `ddl` 모듈 생성). 동적 객체는 Alembic 메타데이터에 넣지 않는다 | 03b 2-3 W1, 3-2 |
| 이름 | 표 `ds_<datasets.id>`, 뷰 `dv_<datasets.id>`, 오류 판정 보조 뷰 `de_<datasets.id>`(열 `e_<dataset_columns.id>`, §3-4 [제안]), 열 `c_<dataset_columns.id>`, 인덱스·제약도 번호 기반(`ux_ds_<id>_period`, `ck_ds_<id>_period`). 사용자 글자는 식별자에 쓰지 않는다. 번호 공백은 정상 | 03b 4-3 Z7, 03c X-1 |
| 한 트랜잭션 | 정적 표 쓰기 + 동적 DDL을 한 트랜잭션으로 한다. 실패하면 등록 행까지 롤백된다(`bi_app` 단일 로그인) | 03b 3-2 ㄷ, 03c X-1·X-15 |
| 미입력 | 빈 칸은 NULL이며 0이나 빈 글자가 아니다. 빈 글자 입력은 앱이 NULL로 바꾼다 [제안] | 03b 5-2 K7 |
| 키·형 | 정적 표 `integer GENERATED … AS IDENTITY`(시퀀스 권한 불필요), 시각 `timestamptz`. 열거 값은 PostgreSQL enum 대신 `text` + 이름 있는 CHECK [제안: 값 추가가 타입 변경 없이 가능, 추정] | 03c X-15 |

## 2. 정적 표 (`public`, 마이그레이션 생성, FU-1 몫)
외래키는 `ON DELETE` 기본(NO ACTION)이다. FU-1에는 삭제가 없다(팀·사용자는 비활성화만, 03b 3-5 Y12(a)). `bi_app`은 표마다 명시 GRANT만 받고(03b 3-6 BY1), **`team_id`·`dataset_id`·`kind`·`code` 같은 불변 열은 열 단위 UPDATE 권한에서 빼 DB가 불변을 강제**한다 [제안: 열 단위 GRANT 문법은 `pg16-ref-grant.sgml:31`, 확인됨(문서)]. 단 `dataset_columns.type`은 계산 열의 결과 형이 바뀔 때(05 D5) 갱신해야 하므로 UPDATE 권한을 주고, 원본 열의 `type` 변경 금지는 DB가 아니라 앱 규칙과 시험으로 지킨다 [제안].
| 표 | 열 (NN = NOT NULL) | 키·제약·외래키 | `bi_app` 권한 |
| --- | --- | --- | --- |
| `users` | `id`; `login_id text NN`(신원 어댑터가 주는 변하지 않는 식별자, 종류는 8번 후); `display_name text NN`; `is_admin bool NN default false`; `is_active bool NN default true`(비활성화만); `created_at` | UNIQUE(`login_id`) | SELECT, INSERT, UPDATE(`display_name`,`is_admin`,`is_active`) |
| `teams` | `id`; `code text NN`(불변, `team` 열 값); `name text NN`(바꿀 수 있는 표시 이름); `is_active bool NN`; `created_at` | UNIQUE(`code`); CHECK(`code ~ '^[a-z0-9_]{1,32}$'` [제안]: 뷰에 글자로 들어가므로 문자 제한, 03c X-26); UNIQUE(`name`) [제안: 가상 데이터셋 이름 접두 구분]; 길이 상한 50자는 앱 검증 [제안] | SELECT, INSERT, UPDATE(`name`,`is_active`) |
| `team_members` | `team_id`, `user_id`, `role text NN` | PK(`team_id`,`user_id`)(팀마다 역할 하나); FK 둘; CHECK(`role IN ('definer','entry')`); 인덱스(`user_id`) | SELECT, INSERT, UPDATE(`role`), DELETE(소속 해제) |
| `datasets` | `id`; `team_id NN`; `name text NN`; `date_unit text NN`; `base_date_column_id` NULL(기준 날짜 열 없음); `status text NN default 'active'`; `def_version int NN default 1`; `def_hash text NN`(§5); `created_by NN`; `created_at` | FK `team_id`, `created_by`; UNIQUE(`team_id`,`name`); CHECK(`date_unit IN ('day','month','year')`), CHECK(`status IN ('active')`: 값은 후속 단위가 CHECK를 바꿔 추가); 이름 길이 100자는 앱 검증 [제안]; 복합 FK(`id`,`base_date_column_id`)→`dataset_columns`(`dataset_id`,`id`): 기준 열이 같은 데이터셋 소속임을 DB가 보장 [제안]; 순환 FK라 표 생성 뒤 추가 | SELECT, INSERT, UPDATE(`name`,`date_unit`,`base_date_column_id`,`status`,`def_version`,`def_hash`). `team_id`는 불변 [제안: 팀 열이 뷰에 상수로 들어감] |
| `dataset_columns` | `id`; `dataset_id NN`; `display_name text NN`; `type text NN`; `kind text NN`; `required bool NN default false`; `rules jsonb`(범위 등, §3-2); `tag text`(열 구분 태그); `position int NN`(화면 순서) | FK `dataset_id`; UNIQUE(`dataset_id`,`id`)(복합 FK 대상); UNIQUE(`dataset_id`,`display_name`); CHECK(`type IN ('text','number','date','boolean','choice')`), CHECK(`kind IN ('raw','formula')`), CHECK(`kind='raw' OR (NOT required AND type<>'choice')`); `kind='formula'`의 `type`은 07이 정한 결과 형. `display_name`: 길이 100자와 금지 문자(`[` `]` `"`·제어문자)는 앱 검증 [제안, 07 §1] | SELECT, INSERT, UPDATE(`display_name`,`required`,`rules`,`tag`,`position`,`type`). `kind`·`dataset_id`는 DB가 불변 강제, `type`은 계산 열만 갱신(원본 열 금지는 앱 규칙, §2 머리말·§3-3) [제안] |
| `formulas` | `column_id`; `expression text NN`(보관용 원문, 수식 보기는 AST에서 생성, 07 §9); `ast jsonb NN`(열 번호 참조, 07); `ast_hash text NN` | PK·FK `column_id`(열 하나에 수식 하나); `kind='formula'` 열인지는 앱이 확인 | SELECT, INSERT, UPDATE(`expression`,`ast`,`ast_hash`) |
| `formula_deps` | `column_id`, `depends_on_column_id` | PK 둘; FK 둘; CHECK(둘이 다름); 태그 합산은 펼친 구체 열 목록을 07이 다시 계산해 넣음; 같은 데이터셋 여부는 앱 확인 | SELECT, INSERT, DELETE |
| `superset_datasets` | `dataset_id`; `superset_dataset_id int`(등록 전 NULL); `display_name text NN`; `sync_status text NN default 'pending'`; `synced_at timestamptz`; `last_error text`(관리자 현황용 요약, 비밀·SQL 금지) [제안] | PK·FK `dataset_id`; CHECK(`sync_status IN ('pending','registered','failed')`) | SELECT, INSERT, UPDATE(`superset_dataset_id`,`display_name`,`sync_status`,`synced_at`,`last_error`) |
| `superset_dashboards` | `id`; `name text NN`; `embedded_uuid uuid NN`(관리자 수동 입력, 03b 4-2 Z3 ㄴ); `is_active bool NN default true`(해제); `created_at` | UNIQUE(`embedded_uuid`) | SELECT, INSERT, UPDATE(`name`,`is_active`) |
- 브리프 4.2의 등록 정보 대응: 소유자 = `team_id` + `created_by`, 생성일 = `created_at`, 스키마 = `dataset_columns`. 원본 파일 정보는 가져오기 단위(후속, 03b 4-4 Z11). 글자 상수는 Z6 (가)라 `formula_literals` 표를 두지 않는다(03b 5-2).
- `datasets.status`는 FU-1에서 `active`뿐이다. `archived`·`deleted`와 `_archived_at` 열은 후속이며 CHECK는 그때 교체한다.
- 시험용 사용자 시드는 마이그레이션에 넣지 않는다(03b 5-2 K3, `bi-review` 7-5). 시험 사용자는 시험 fixture·개발 전용 명령으로, 첫 관리자는 서버 명령으로 만든다(04 `access`).

## 3. 동적 객체 (`bi_data`, `bi_app` 소유)
### 3-1. 원본 표 `ds_<id>`
| 열 | PostgreSQL 형 | NULL·제약 |
| --- | --- | --- |
| `row_id` 행 고유 번호 | `bigint GENERATED BY DEFAULT AS IDENTITY` | PK. 갱신 대상 지정·충돌 응답·순서 안정(03b 2-5 B7 "06에서 정함") [제안: 둠]. 암묵 시퀀스가 `bi-review` 7-4의 "시퀀스 금지"와 충돌하므로 열이 소유한 `Identity` 시퀀스는 예외로 두고 시작 자가 점검의 객체 종류 규칙에도 같은 예외를 둔다(04 §2-1). 없으면 첫 데이터셋 뒤 매 시작이 거부된다 **[AP-10]** |
| `c_<id>` 원본 열 | text→`text`, number→`numeric`, date→`date`, boolean→`boolean`, choice→`text`(선택 목록 값 자체) | NULL 허용(미입력). 필수·범위는 §3-2. `numeric`의 NaN은 앱이 거부(03c X-26 비유한 수) |
| 기준 날짜 열 `c_<base>` | `date` | **NN**(지정되면 `required=true`로 취급해 입력 판정에서도 `REQUIRED`) + CHECK(기간 첫날: 열이 `date`라 `date_trunc('month', c::timestamp)::date = c`처럼 `timestamp` 변환을 거쳐 세션 시간대에 의존하지 않는 식, `date_unit`별) + UNIQUE 인덱스 `ux_ds_<id>_period`(Y9 (a) 기본 하나). 열이 `date`·`raw`가 아니면 DDL이 실패해 롤백됨 |
- 계산 열(`kind='formula'`)은 `ds_`에 열이 없고 `dv_`에서만 계산된다(저장 안 함). 오류 칸도 저장되지 않고 뷰가 NULL을 돌려준다(04 §8, §3-4).

### 3-2. 필수·범위 검증을 어디에서 하나 **[제안: A, 단 기준 날짜 열만 DB 제약]**
| 방식 | 내용 | 영향 |
| --- | --- | --- |
| A 앱 검증(제안) | `rules` jsonb(number: `min`·`max`·`decimals`, text: `max_length`, date: `min`·`max`, choice: `options`)와 `required`를 서버가 입력·붙여넣기마다 검사. 새 행은 필수 열이 모두 있어야 저장(그래서 한 칸씩 채우는 새 행은 화면 메모리의 임시 행이고 서버·`ds_`에 draft 상태가 없다, 05 §2-3), 기존 행은 필수 칸을 비울 수 없음 | 규칙 변경이 DDL 없이 끝남. 규칙 변경 전의 기존 값은 그대로 두고 점검은 후속. DB는 위반 값을 막지 못함 |
| B DB CHECK/NOT NULL | 규칙마다 제약을 `ds_`에 만듦 | 규칙을 바꿀 때마다 DDL + 기존 값 검증 필요, `ALTER TABLE`이 표를 잠금(03c X-7), 선택 목록 변경이 DDL이 됨 |
- 정규식·유일성 검증은 후속. 선택 목록 값이 목록 밖이어도 지우지 않고 점검에서 표시하는 원칙은 후속과 같다.

### 3-3. 기준 날짜 열과 변경 제한 **[제안]**
| 항목 | 규칙 | 근거 |
| --- | --- | --- |
| 기준 날짜 열이 없는 데이터셋 | "한 기간 = 한 행"은 입력 단위(행 하나 = 기록 하나)로만 쓰고, 같은 기간 하나만 규칙·정렬 기준은 없다(순서 = `row_id`). `date_unit`은 지정만 하고 쓰이지 않는다. FU-1에는 기준 날짜 열을 필수로 만드는 기능이 없다(이전 행·기준값·요약은 후속) | 03b 2-3 W3-1, 3-4 Y9 (a) |
| 열 `type`·`kind` 변경 | **FU-1 전체 금지**(새 열 추가로 옮김). 기준 날짜 열은 결정(Y9 (c))이고 나머지는 변환 미리보기 흐름이 후속이라 맞춘 것(04 §10 기능 축소 표). 계산 열의 결과 형 `type` 갱신은 이 금지에 속하지 않는다(§2) | 03b 3-4 Y9 (c), 브리프 4.3 |
| 기준 날짜 열 지정·변경, `date_unit` 변경 | 행이 0개일 때만(기존 값의 기간·유일성 검증을 피함). 이름 변경은 항상 가능 | 03b 3-4 Y9 (c) |
| 열 삭제·보관, 데이터셋 삭제·보관 | FU-1 없음(삭제 정책 제외) | 03b 5-1 |
- 열 표시 이름은 `team`·`팀`·`row_id`·`행 번호`(Superset 표시 이름과 같아짐)를 쓸 수 없고 `[` `]` `"`·제어문자를 포함할 수 없다. 열 구분 태그도 길이 50자·`"`·제어문자 금지(07 §2-2) [제안: Superset 팀 열과 혼동 방지, 수식 `[열 이름]` 문법이 이름을 그대로 다시 읽기 위함(07 §1)]. 정의 담당자의 입력은 §4.

### 3-4. 수식 뷰 `dv_<id>`
| 항목 | 내용 | 출처·상태 |
| --- | --- | --- |
| 구성 | 출력 열: `team`, `row_id`, 원본·계산 열 `c_<id>`를 **번호 오름차순**으로(07 §8과 같은 순서). `CREATE OR REPLACE VIEW`는 끝에 열 추가만 되므로 순서를 번호순으로 고정 [제안, 07과 맞춤] | 03c X-11 |
| 수식 없는 데이터셋 | 뷰를 만든다(`team`, `row_id`, 원본 열). Superset 등록 SQL·팀 열·그리드의 계산 열 조회가 한 경로가 됨 [제안]. 생성은 dataset 트랜잭션 안에서 정의 변경 훅이 formula 모듈을 불러 `ddl`로 한다(04 §3, 07과 맞춤) | 04 §7-1 |
| `team` | 팀 코드 상수(형식을 제한한 `teams.code`, 불변). 이름은 예약(04 부록 A) | 03b 2-5 B8, 3-6 BY9 |
| 재생성 | 열 추가·표현식 변경(같은 결과 형)은 `CREATE OR REPLACE`. 출력 열 삭제·형 변경·이름 변경은 `DropView`+`CreateView`(의존 뷰 포함 한 트랜잭션). 정의 해시가 같으면 DDL을 건너뜀 | 03c X-11·X-17 |
| 읽는 표 | 자기 `ds_<id>`만 읽는다. `public` 정적 표 위에 뷰가 없어 `downgrade`가 막히지 않고(X-29), 소유자 권한 문제도 없다 | 03c X-29 |
| 오류 칸 (07과 맞춤) | **뷰가 보이는 값**: 오류·미입력 입력이면 NULL(빈 값). **오류 판정 구조는 07 §3-1 E-A(승인 03b 6-2)**: 보조 뷰 `de_<id>`(`row_id` + 계산 열마다 `e_<열 id>`)를 `ddl`로 만든다. 종류가 뷰라 허용 목록(표·뷰·인덱스·제약)에 맞고, 비용은 뷰 수 2배·재생성 락 증가·이름 규칙 확장(04 부록 A). 대안은 DB 객체 없이 포털이 같은 변환기로 만든 판정 SELECT(읽기 전용 트랜잭션) | 03b 5-2 K7 ㄷ, 03c X-2 |

### 3-5. 정의 변경 한 트랜잭션 (열 추가 예)
dataset의 **정의 변경 진입점**(04 §5)이 순서대로 한다: `datasets` 행 잠금 → `def_version` 확인·+1(§5) → 열 변경(`dataset_columns` INSERT로 새 `id` 확보, 원본 열이면 `ALTER TABLE ds_<id> ADD COLUMN c_<id>`[Alembic `Operations`, `bi-review` 7-4가 허용]와 기준 열이면 CHECK·UNIQUE 인덱스, 계산 열 결과 형이 바뀌면 `type` 갱신) → 정의 변경 훅(formula가 새 `id`로 `formulas`·`formula_deps`를 쓰고 `dv_`·`de_`를 `CREATE OR REPLACE`) → `def_hash` 기록. formula가 직접 쓰는 정적 표는 `formulas`·`formula_deps`뿐이다. 이 트랜잭션은 `superset_*` 표를 쓰지 않는다. 표 쓰기는 소유 모듈의 repo가 하고 모듈 사이는 서비스 함수·훅으로 부른다(04 §5). 커밋 뒤에만 `DatasetSyncPort`로 백그라운드 동기화를 요청하고, 그때 superset 모듈이 자기 표에 상태를 쓴다(등록 행이 없으면 `pending`, 08 §2-1). 중간 실패는 전부 롤백(03c X-1). `ds_` 표의 `ALTER TABLE`은 읽기와 서로 기다리므로 `lock_timeout`을 걸고 실패는 "다시 시도"(03c X-7·X-17).

## 4. 권한
### 4-1. 사람 역할 × 동작 (팀 단위, 여러 팀 소속 가능, 03b 5-2 K2)
데이터셋의 권한은 **그 데이터셋의 팀**(`datasets.team_id`)에 대한 `team_members.role`로 판정한다. 비활성 사용자는 모두 거부 [제안]. 비활성 팀·사용자의 소유 데이터셋 효과는 후속(K10 ㄱ).
| 동작 | 관리자 | 정의 담당자(그 팀) | 입력자(그 팀) | 인증된 읽기(타 팀 포함) |
| --- | --- | --- | --- | --- |
| 팀 만들기·소속·역할·비활성화 | O | X | X | X |
| 내 정보·팀 목록(이름·코드) 보기 | O | O | O | O |
| 데이터셋 만들기·열 정의·수식 편집·미리보기 | X [제안] | O | X | X |
| 행 입력·칸 수정·붙여넣기 | X [제안] | O [제안] | O | X |
| 데이터셋·행·열 정의·**수식 보기**·오류 칸 목록 열람 | O | O | O | O (03b 1-3, 1-6) |
| Superset 동기 상태 보기(사유 `last_error`는 관리자만) | O | O | O | O |
| 대시보드 목록·보기(입장권) | O | O | O | O |
| 대시보드 연결 등록·해제, 동기 사유·뷰 재생성 현황·다시 시도 | O | X | X | X |
- **정의 담당자의 입력은 가능**(승인 03b 6-2; 역할을 하나만 두는 `team_members` 구조에서 입력하려고 다른 역할 행이 필요한 일을 피함).
- **관리자는 팀 소속 역할 없이 데이터셋 정의·입력 권한이 없다**(승인 03b 6-2). 필요하면 그 팀의 `team_members`에 올라 그 역할로 한다.
- Superset 차트 작성 계정은 관리자가 수동으로 만든다(03b 5-2 K11 ㄷ). 작성 권한 자체는 DB가 아니라 Superset 역할이다(08).

### 4-2. DB 계정 권한 (구현됨: EW-1, 2026-10-11, QA 11항목 통과·reviewer 차단 0건, 03b 3-2·5-4)
| 계정 | 있는 권한 | 없는 권한·잔여 위험 | 근거 |
| --- | --- | --- | --- |
| `bi_owner` | 정적 표 소유(DDL·DML), `alembic_version`, `bi_data` 소유자(멤버십 없이도 `DROP` 가능), `bi_app`의 `INHERIT TRUE, SET FALSE` 멤버 | backend 런타임 접속 금지. `bi_data`에 객체를 만들지 않는다(만들면 `bi_readonly`가 못 읽음) | X-14, X-15 |
| `bi_app` | §2 표 GRANT만(`TRUNCATE`·DDL·`alembic_version` 거부), `bi_data` `USAGE, CREATE`(`ds_`·`dv_` 소유) | `public` CREATE·schema/역할 생성·`SET ROLE bi_owner` 거부. **잔여:** `bi_data`에 함수·시퀀스·타입 생성과 `GRANT … TO PUBLIC` 가능 → `ddl` 허용 목록(표·뷰·인덱스·제약), 시작 자가 점검(객체 종류[열이 소유한 `Identity` 시퀀스 `row_id`는 허용], 슈퍼유저·`CREATEROLE`·`CREATEDB` 거부), 권한 매트릭스 시험 | X-15, 03b 3-6 BY3, 4-3 Z7 |
| `bi_readonly` | `CONNECT`, `bi_data` `USAGE`, `bi_app`이 만든 `ds_`·`dv_`의 `SELECT`(기본 권한) | `public` 읽기 불가, `CREATE`·DML 거부, 다른 역할 멤버십 없음 [제안: 명세 문장은 4라운드 5-(e)]. **잔여:** `CREATE TEMP TABLE` 가능(DB 이름이 변수라 고정 SQL `REVOKE` 불가. EW-1 QA에서 `bi_app`도 가능함을 확인했고 DB 수준 `PUBLIC TEMP`가 원인으로 추정된다). `default_transaction_read_only`는 세션에서 해제 가능하므로 **방어선은 권한**이다. 느린 질의가 DB에서 계속 실행됨 → `statement_timeout` 설정 **[AP-9]**: 값 30초 [제안, 추정], 위치는 db-bootstrap `roles.sql`의 기존 `ALTER ROLE bi_readonly SET …` 옆 고정 SQL, 효과는 EW-1 QA에서 실측(`pg_sleep(31)`이 30.2초에 취소, `bi_app`·`bi_owner`는 영향 없음) | X-2, X-15, X-25 |
- 열 단위 숨김은 Superset에서 불가능하고 방어선은 `bi_readonly` 권한뿐이므로 `bi_data`에 둔 것은 모두 공개다(불변식, 03b 3-1, 03c X-25). 권한 매트릭스 시험은 정상과 부정(위 "없는 권한")을 모두 자동화한다(03b 3-6 BY4).

## 5. 동시 편집 필드 (03b 3-4, 03c X-24)
| 대상 | 방식 | 필드·규칙 |
| --- | --- | --- |
| 칸 수정 | 칸 단위 값 비교 갱신 | `UPDATE ds_<id> SET c_a=:새값 WHERE row_id=:id AND c_a IS NOT DISTINCT FROM :이전값`. 바꾸는 칸의 이전 값만 가드(빈 칸은 `IS NOT DISTINCT FROM`). 0행이면 앱이 다시 읽어 원인 구분(칸 충돌 / 행 없음), 이미 같은 값이면 성공. 한 요청에서 여러 칸이면 칸 전체가 가드라 하나라도 충돌하면 전체 취소 |
| 붙여넣기 | 한 트랜잭션, 충돌 시 전부 취소 | 기존 행은 **`row_id` 오름차순**으로 갱신한 뒤, 새 행은 **기간(기준 날짜) 오름차순**으로 삽입한다. 기존 행의 기준 날짜 열 값은 붙여넣기로 바꾸지 못한다(UPDATE의 유일 인덱스 위반은 트랜잭션을 중단시켜 충돌을 모을 수 없으므로 기간 이동은 05 C3 단건만)(둘 다 같은 순서로 대기해 교착 방지; 기준 날짜 열이 없으면 입력 순). 새 행은 `INSERT … ON CONFLICT DO NOTHING RETURNING`(SQLAlchemy 내장)으로 넣어 `ux_ds_<id>_period` 충돌이 트랜잭션을 중단시키지 않고 충돌 목록에 모이게 하고(대안 SAVEPOINT; pg8000 경유 `ON CONFLICT`·UPDATE 경로 동작은 1c 첫 시험), 충돌이 하나라도 있으면 끝에서 전부 롤백한다. 락 대기 초과(`55P03`)·교착(`40P01`)은 `WRITE_BUSY`(05)로 돌려준다. 시간 제한은 `set_config`로 |
| 기간(기준 날짜) 수정 | 허용 + 확인창(화면) | 이미 있는 기간으로 옮기면 같은 유일 인덱스 위반으로 거부(03b 3-4 Y9 (b)) |
| `pg8000` 확인 | **미확인 (CC-05)** | `rowcount`를 못 얻으면 `UPDATE … RETURNING row_id`가 0행인지 보는 방식으로 바꾼다 [제안]. Gate ④ 1c의 첫 시험 |
| 정의 변경 직렬화 | **`datasets` 행 잠금 하나**(advisory 잠금은 쓰지 않음, 07 §8과 같음) [제안] | 정의 변경(열·수식·검증 편집)·시작 시 뷰 재생성·재시도(05 D10)는 모두 정의 변경 진입점의 맨 앞에서 `SELECT … FOR NO KEY UPDATE`(SQLAlchemy `with_for_update(key_share=True)`; `id`가 불변이라 충분하고 `FOR UPDATE`는 `superset_datasets` 같은 FK 자식 INSERT의 KEY SHARE까지 막는다)로 그 데이터셋 행을 잡는다. **실제 동작(1b 시험, 03b 19-1)**: 열 추가 같은 정의 변경은 FK 자식 INSERT를 기다리게 하지 않지만, 데이터셋 **이름 변경(B4)** 은 `UNIQUE(team_id, name)`에 들어 있는 열의 UPDATE라 PostgreSQL이 `FOR UPDATE` 수준으로 잠금을 올려 FK 자식 INSERT가 커밋까지 잠시 기다린다. 영향은 짧은 대기라 그대로 두기로 결정했다. 편집은 읽은 `def_version`과 `expected_version`을 비교해 다르면 `DEFINITION_VERSION_MISMATCH`, 같으면 +1. 시작 시 재생성·재시도는 정의가 안 바뀌므로 잠금만 잡고 버전은 올리지 않으며 짧은 `lock_timeout`으로 못 잡으면 실패로 남긴다. 03c X-24는 같은 효과의 `UPDATE … WHERE def_version` 가드와 advisory 잠금을 확인했고 `FOR NO KEY UPDATE` 자체는 미시험이라 1b 첫 시험 |
| 행 쓰기 ↔ 정의 | 행 요청(C2~C4)은 dataset service 함수(잠금 + 버전 확인, 04 §5)로 `datasets` 행을 `FOR SHARE`로 잡고 `def_version`을 비교한다 [제안: 03b Y8의 정의 편집 범위 밖의 요구, 승인 03b 6-2] | 다르면 409(열 추가 때 열려 있던 그리드 입력도 409가 됨). 잠금 순서는 항상 **`datasets` 행 → `ds_` 행 → 동적 DDL**이라 정의 변경(`FOR NO KEY UPDATE`, SHARE 보유자를 기다림)과 행 쓰기 사이에 순서 역전 교착이 없다. **시험함(1b·1c, PostgreSQL 16)**: 연속 `FOR SHARE` 보유자가 이어지면 뒤 보유자가 대기 중인 정의 변경을 앞지르는 굶음이 실제로 관찰되며, 정의 변경은 `lock_timeout`(1초) 뒤 `DEFINITION_BUSY`로 끝나 무한 대기는 없다 |
| `datasets.def_hash` | 마지막으로 뷰를 **성공적으로** 만든 정의의 해시(표시 이름 제외, 알고리즘은 07) | 시작 시 현재 정의의 해시와 비교해 다르면 재생성, 같으면 건너뜀(03c X-17). 실패하면 저장값이 안 바뀌어 다음 시작·재시도 때 다시 대상이 되고, 그 수가 `/health`의 `views_failed_count`(05). **`/health`의 새 필드와 실패 상세(사유·시각)는 프로세스 메모리 값이고 영속되는 것은 `def_hash` 표 값뿐**이며 상세는 로그에도 남긴다. uvicorn **worker 1개 전제**(`03a`)이고 worker를 늘리면 실패 상세를 표 필드로 옮기도록 재설계한다(07 §8) |

## 6. 마이그레이션 계획 (db-bootstrap·`0002`·틀은 구현됨 EW-1, 정적 표 revision은 FU-1 단계, 03b 3-2·4-1)
| 항목 | 내용 | 출처·상태 |
| --- | --- | --- |
| db-bootstrap 사전 조건 | ① 역할 `bi_owner`·`bi_app`과 비밀번호(변수 승인됨) ② 빈 `bi_data`, **소유자 `bi_owner`** [제안: 03b에 소유자 명시 없음, X-15 구성] ③ 이미 있는 `bi_owner`·`bi_app`은 매 기동 고정 문장 `ALTER ROLE … NOSUPERUSER NOCREATEDB NOCREATEROLE`로 속성을 다시 차단한다(구현됨 EW-8, 03b 14-1 ①) ④ `GRANT bi_app TO bi_owner WITH INHERIT TRUE, SET FALSE`(승인됨, 반복 실행 안전) ④ `bi_owner`에 `public` CREATE **[AP-5]**(PostgreSQL 15 이후 기본 구성은 `PUBLIC`에 주지 않음, `pg16-ddl.sgml:3255`; `bi_app`의 `public` CREATE 거부는 03c X-15) | 03b 3-2, 4-1 Z0, 7-1, 03c X-14·X-29. **구현됨(EW-1)**: `backend/bootstrap/roles.sql`에 ①~④와 함께 소급 승인된 `REVOKE ALL ON SCHEMA bi_data FROM PUBLIC`·`REVOKE CREATE ON SCHEMA public FROM PUBLIC`·`SET LOCAL log_min_error_statement = panic`이 있다 |
| 첫 실제 revision `0002_bi_data_privileges`(권한 전용, **구현됨(EW-1)**: `backend/migrations/versions/20261011_0002_bi_data_privileges.py`) | `GRANT USAGE, CREATE ON SCHEMA bi_data TO bi_app` → `GRANT USAGE ON SCHEMA bi_data TO bi_readonly` → `ALTER DEFAULT PRIVILEGES FOR ROLE bi_app IN SCHEMA bi_data GRANT SELECT ON TABLES TO bi_readonly`. 실질 `downgrade()`(REVOKE). 전부 `bi_owner`가 실행하는 보간 없는 고정 SQL | 03b 4-1 Z0, 6-4, 03c X-29 |
| 이후 revision | `0003`(1a) `users`·`teams`·`team_members`와 §2 명시 GRANT, `0004`(1b) `datasets`·`dataset_columns`(순환 FK는 `create_foreign_key`로 뒤에 추가), `0005`(1d) `formulas`·`formula_deps`, `0006`(1e) `superset_*`. 소단위마다 하나 | 04 §6·§7-1 |
| `downgrade()` | 실질 구현: 권한 `REVOKE`, 기본 권한 `REVOKE`, 표 역순 삭제. `bi_data` schema·동적 객체·멤버십은 건드리지 않는다(D5 의미 변경 승인). 표 삭제의 `op.drop_table`은 `DROP_APPROVED`에 사용자 승인 기록이 필요하다(`test_migrations.py`) | 03b 3-2 ㄱ, D2 안전장치 |
| `env.py` | **구현됨(EW-1)**: `target_metadata`는 정적 `MetaData` 하나(현재 `backend/app/db_metadata.py`, 04의 `core` 소속, 제약 이름 규칙 지정 [제안, 일반 지식]). `bi_data`용 `MetaData`는 별개 인스턴스이고 `env.py`가 가져오지 않는다. `include_schemas=False`(기본) + 안전망 `include_name`/`include_object`로 `bi_data` 제외. `compare_type=True` 유지 | 03c X-29 (`include_schemas=True`이고 필터가 없을 때만 `ds_*`가 `drop_table`로 제안됨) |
| 점검 | `alembic check`(DB가 head, 종료 코드 0/255/1): ① 빈 DB 성공 ② `ds_1`·`dv_1`이 있는 DB도 성공 ③ 정적 모델 열을 지우면 255 ④ `DROP_APPROVED` 규칙. 권한은 `check`가 못 잡으므로 스냅샷 비교. `heads` 개수 1개 점검. `test_migrations.py`의 head 단정은 `["0002"]`로 갱신됨(EW-1), `INTENTIONAL_NOOP`은 `{"0001"}` 유지 | 03c X-29 |
| 왕복 시험 | 출발 = db-bootstrap 직후 DB, `bi_owner` 실행. 스냅샷(`public` 표·열·인덱스·제약, ACL, `pg_default_acl`, `bi_data` 권한) A → upgrade → B → downgrade → A → upgrade → B. 사전에 `bi_app`이 만든 `ds_1`·`dv_1`이 남는지 확인. schema ACL의 NULL/소유자 명시 차이는 정규화. 복원 대상 제외: db-bootstrap 산물(역할·멤버십·`bi_data`·`public` CREATE), 빈 `alembic_version` | 03c X-29, 03b 4-1. **구현됨(EW-1)**: `python -m migrations.roundtrip`(`backend/migrations/roundtrip.py`, QA 통과) |
- D2 안전장치 문구 재서술은 **[AP-11]**(선택, 현행 유지도 가능). D6 Jenkins 적용은 보류(Docker 가능 여부 확인 후).

## 7. Superset에 노출되는 열 이름과 변경 영향 (K12 (나), 확인됨: 03c A-27)
Superset 열 이름 = 내부 이름 `c_<id>`(팀 열은 `team` 고정), 읽기 쉬운 이름은 Superset 열 "표시 이름"으로 붙인다(03b 5-2 K12). 서비스 계정(4권한)이 자기 소유 데이터셋의 표시 이름을 설정·변경·해제할 수 있다(조건부 가능: `columns`는 교체라 **항상 전체 열을 보내야** 함, 08 §2-3). 포털은 표시 이름의 원천(`dataset_columns.display_name`)을 보관해 `refresh` 뒤 병합한다. 표시 이름은 1,024자를 넘으면 Superset PUT이 원인 없는 422이므로 앞서 정한 길이 상한(§2)으로 먼저 막는다.
| 변경 | DB·뷰 | Superset 영향 |
| --- | --- | --- |
| 열 표시 이름 변경 | `display_name`만 바뀜, `c_<id>` 불변, 뷰 재생성 없음 | 차트·필터는 안 깨지고 표 머리글만 바뀐다(03c A-27 확인됨). 데이터셋 표시 이름(가상 데이터셋)은 제자리 변경, 차트·데이터셋 권한 유지(03c X-22 확인됨) |
| 열 추가 | 뷰 끝에 열 추가 | 새로고침 후 새 열 반영(03c X-13·X-22 확인됨) |
| 계산 열 표현식 변경(같은 결과 형) | `CREATE OR REPLACE` | 열 이름 불변이라 차트 영향 없음(추정) |
| 열 삭제·형 변경 | FU-1 없음(§3-3). 후속에서 영향 안내 필요 | 그 열을 쓰는 저장된 차트가 데이터 오류(03c X-22 확인됨) |
- 번호 이름은 네이티브 필터 설정의 열 선택·Explore 칩·View query 등 일부 화면에서 보인다(03c A-27 확인됨, 08 §5 안내문). 작성자가 UI에서 만든 지표의 라벨은 저장 시점의 표시 이름으로 굳어(`SUM(총매출)`) 이름을 바꿔도 질의 별칭은 그대로다(깨지지는 않음, 03c A-27). `row_id`는 Superset 전체 열 `PUT`에 포함되므로 숨기지 않고 표시 이름 "행 번호"를 붙이고 `team`은 "팀"으로 둔다 [제안]. 팀 열 이름이 같아야 값 선택 필터가 동작하고 날짜 열 이름은 통일하지 않는다(03c X-5, 03b 3-6 BY9).

## 8. 승인 상태 (`03b` 6-3)
| 번호 | 항목 | 시점 |
| --- | --- | --- |
| AP-5 | **승인**: db-bootstrap 고정 SQL 추가 — `bi_owner`에 `public` CREATE, `bi_data` 소유자 `bi_owner`(위 §6 ②) | 승인됨, 구현됨(EW-1) |
| AP-9 | **승인**: `bi_readonly` `statement_timeout` 30초(기준선과 다른 설정, 효과 확인됨: EW-1 QA에서 30.2초에 취소) | 승인됨, 구현됨(EW-1) |
| AP-10 | **승인**: `bi-review` 7-4 문구 — 열에 연결된 `Identity()` 암묵 시퀀스를 "시퀀스 금지"의 예외로 명시(`row_id`가 의존). 런타임 Alembic `Operations` 허용은 7-4에 이미 있어 승인 대상이 아니다 | 승인됨 |
| AP-11 | **승인·반영 완료**: `03-migration-tool.md` D2 안전장치를 "정적 표 대상"으로 좁힘 | 완료 |
| - | revision `downgrade`의 `op.drop_table`에 필요한 `DROP_APPROVED` 기록: 기존 D2 규칙의 적용이며 새 승인이 아니다 | 각 revision 때 |
- 이 문서는 새 환경변수·새 런타임 의존성·모델 변경을 요구하지 않는다. 열 단위 UPDATE GRANT, 제약 이름 규칙은 [제안]이며 `03b` 6-2로 승인됐다.

## 9. 후속 기능 단위에서 결정
- 기준값 표(숫자·글자, 적용 시작일, 추가만), 공통 요약(지표·연결·요약 뷰), 이전 행 참조·같은 데이터셋 집계(기준 날짜 열 필수 조건이 켜짐), 참조 열(`reference` 타입), 정적 표를 읽는 뷰의 `downgrade` 막힘 규칙.
- 엑셀 가져오기 원본 정보(이름·크기·해시, 03b 4-4 Z11), 가져오기 중 입력 차단, 업로드 상한(EW-2), 데이터셋 개수·크기 상한(K11 ㄹ).
- 보관·삭제 정책(`deleted` 상태, 숨은 열 `_archived_at`, 30일 `DROP`, `DROP COLUMN`, 열·데이터셋 삭제 수단), 변경 기록 `audit_log`(이름 예약, 기록 시작도 후속), 소급 변경·마감(K5), 팀 비활성의 효과(K10 ㄱ).
- 데이터 있는 열의 타입 변환 흐름, 정규식·유일성 검증, 같은 기간 여러 행 허용 설정(`03b` 3-4 Y9 (a)의 "정의 담당자가 끌 수 있음"), 역할별 열 편집 권한·데이터셋별 예외 권한, 행·열 전환 보기, 8번 인증 방식에 따른 `users.login_id` 규칙, 데이터셋의 팀 변경.
