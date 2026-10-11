# Gate ③ 4라운드 DB·마이그레이션 런타임 실험 결과 (X-26, X-29)

- 범위: 사용자가 승인한 X-26(수식 속 글자 상수의 뷰 렌더링 + 런타임 내장 DDL 부품), X-29(`alembic check`와 왕복 테스트 틀 + 2계정 구성 마이그레이션). 클라우드 세션 안에서만 실행. 저장소 추적 파일은 수정하지 않았다(`git status`에 내 변경 없음).
- 환경: PostgreSQL **16.10**(`postgres:16.10-bookworm`, 컨테이너 `g3x26-pg`, tmpfs 데이터, 볼륨 없음, `TZ=Asia/Seoul`, `log_statement=all`). 파이썬 시험은 모두 **프로젝트 backend 이미지 `bi-wizard-backend:local`**(SQLAlchemy 2.1.4, pg8000 1.31.5, alembic 1.20.0, 파이썬 3.12.15)을 `--network container:g3x26-pg`로 실행했다. 역할은 3라운드와 같다(`bi_owner`, `bi_app`, `bi_readonly`; schema `bi_data` 소유자 `bi_owner`; 정적 표는 `public`; `GRANT bi_app TO bi_owner WITH INHERIT TRUE, SET FALSE`; `ALTER DEFAULT PRIVILEGES FOR ROLE bi_app IN SCHEMA bi_data GRANT SELECT ON TABLES TO bi_readonly`). X-26은 `bi_app`으로 접속했고, X-29의 마이그레이션은 `bi_owner`로 접속했다.
- 시작 시 Docker 데몬이 꺼져 있어 `qa-verification` 스킬 2-2 절차대로 `service docker start`로 세션 안에서 시작했다(성공). `postgres:16.10-bookworm` 재pull은 레지스트리 429로 실패했지만 이미지가 로컬에 있어 영향 없었다.
- 스크립트·원출력: `_workspace/gate3/experiments/r4/db/`(스크립트 `x26_*.py`, `x29_*`, 실행 `run.sh`/`a.sh`/`mark.sh`, 원출력 `out/`)와 `r4/alembic_scratch/`(backend 마이그레이션 구성 복사본 + 변형 가능 `env.py`, 가짜 정적 모델 `models.py`, 실험용 revision 0002). 모두 Git 제외. 같은 폴더를 쓰는 다른 실험(`r4/lib.py` 등)과 이름이 겹쳐 내 파일은 `r4/db/`로 옮겼다.
- 표기: "확인" = 이 환경에서 실행해 관찰, "소스 근거" = 설치본 소스 읽기(`/usr/local/lib/python3.12/site-packages/…`, 아래 `INST`), "추정" = 관찰하지 않은 해석.
- **정리:** `docker rm -f g3x26-pg`(이름 지정)만 실행했다. 시험 전후 `docker ps -a`는 `r4/db/out/cleanup-before-rm.txt`, `cleanup-after-rm.txt`에 있다. 다른 컨테이너(`g3x-*`, `g3x27-lab`)와 볼륨(`bi-wizard_postgres_data`, `g3x_postgres_data`)은 건드리지 않았다(`volumes-after.txt`). 시작 시 `docker ps -a`는 비어 있었고, 종료 시 남은 것은 다른 실험의 `g3x-*`, `g3x27-lab`뿐이다. scratch의 임시 revision 파일은 명시 경로로 삭제했고(`rm`은 파일 이름 지정), 일괄 삭제 명령은 쓰지 않았다.

---

# X-26. 수식 속 글자 상수의 뷰 렌더링 (+ 런타임 내장 DDL 부품)

## 소스 근거 (INST = 설치본 `sqlalchemy/`, `pg8000/`, `alembic/`)
| 항목 | 내용 |
| --- | --- |
| `CreateView` | `sql/ddl.py:758-896`. `or_replace` 인자 있음(`:878`, 문서 `:824-826`). 컴파일러 `sql/compiler.py:7259-7295`가 `inner_kw["literal_binds"] = True`로 SELECT를 렌더 |
| 문자열 리터럴 | `sql/sqltypes.py:298-307`: `'`→`''`, `%`는 `identifier_preparer._double_percents`가 참일 때만 두 배. PG 방언 `base.py:2412-2417`: `_backslash_escapes`이면 `\`→`\\` |
| 판정 시점 | `base.py:3780`(`initialize()`), `:5938-5944`: **엔진 첫 연결 때 한 번** `show standard_conforming_strings`로 `_backslash_escapes`를 정한다 |
| pg8000 방언 | `dialects/postgresql/pg8000.py:397-401`: preparer `_double_percents = False`. **그러나 `:388-394`의 `PGCompiler_pg8000.visit_mod_binary`는 항상 `" %% "`를 낸다** |
| pg8000 프로토콜 | `pg8000/legacy.py:253-259`: `len(args) == 0`이면 `execute_simple`(simple query), 아니면 `convert_paramstyle` 후 `execute_unnamed`(extended) |
| Alembic `postgresql_using` | `alembic/ddl/postgresql.py:171-186, 534`: `"USING %s" % element.using if element.using else ""` — **문자열 끼워 넣기** |

## X-26.1 렌더링 행렬 (`CreateView(select(literal(값).label("c")))` → 실행 → `select`로 되읽기, 58건)
원출력: `r4/db/out/x26_1_matrix.out`(렌더 SQL·되읽은 값·`pg_get_viewdef` 전부). 대표 행만 인용한다.

| 입력 | 렌더된 SQL (대표) | 실행 | 되읽음 | `pg_get_viewdef` |
| --- | --- | --- | --- | --- |
| 평범한 글자, 한글, 이모지, `"`, 개행·탭·CR, 앞뒤 공백, 빈 문자열, `;`, `--`, `/* */`, `$$`, `E'`, `:name`, `?`, `$1`, `%`, `%%`, `%s`, `%(x)s`, U+FFFF, U+10FFFF, 200자·10,000자 등 | `… AS SELECT 'a %s b' AS c` | 성공 | **입력과 일치** | `SELECT 'a %s b'::text AS c;` (열 형은 `text`) |
| `'` / `''` | `'O''Brien'` / `'a''''b'` | 성공 | 일치 | `'O''Brien'::text` |
| `\` / `\'` | `'a\b'` / `'a\''b'` (standard_conforming_strings=on) | 성공 | 일치 | `'a\b'::text` |
| 결합문자 NFD 한글 | 렌더는 입력 그대로 | 성공 | 일치(정규화하지 않음) | — |
| **NUL `\x00`** | `'a\u0000b'` | **오류** `08P01 invalid message format` | — | — |
| **서로게이트 `\ud800`, `\udcff`** | 렌더 문자열에 그대로 | **오류** 파이썬 `UnicodeEncodeError`(전송 전) | — | — |
| 정수 42, -7, 0 | `SELECT 42 AS c` | 성공 | 일치 | `integer` |
| 정수 `10**30` | `SELECT 1000000000000000000000000000000` | 성공 | 값 같음, **형이 int→`Decimal`**(DB `numeric`) | `'1000…'::numeric` |
| `Decimal('1.10')`, `1E+3`, `1.5E-7`, 38자리, `-0.0` | `1.10`, `1E+3`, `1.5E-7`, … | 성공 | 일치(`-0.0`은 `0.0`) | `numeric` |
| **`Decimal('12')`(소수 아님)** | `SELECT 12 AS c` | 성공 | 값 같음, **형 `int`**(DB `integer`) | `integer` |
| float `0.1`, `1e100`, `-0.0` | `0.1`, `1e+100`, `-0.0` | 성공 | 값 같음 | **DB 형이 `numeric`**(float8 아님) |
| **`Decimal('NaN')`, `Infinity`, `-Infinity`, `sNaN`, float `nan`, `inf`, `-inf`** (7건) | `SELECT NaN AS c`, `SELECT inf AS c` (**따옴표 없음**) | **오류** `42703 column "nan" does not exist` | — | — |
| bool True/False | `true`/`false` | 성공 | 일치 | `boolean` |
| **date 2026-10-11, 0001-01-01, datetime** | `SELECT '2026-10-11' AS c` (**따옴표 문자열, CAST 없음**) | 성공 | 값 문자열 동일, **파이썬 `str`/DB `text`** (date 아님) | `'2026-10-11'::text` |
| None | `SELECT NULL AS c` | 성공 | None | `NULL::text` |
- 집계(58건): 글자 32건 중 29건 일치·3건 오류(NUL, 서로게이트 2); 숫자 20건 중 11건 일치·2건 값은 같고 형이 다름(`10**30`, `Decimal('12')`)·7건 오류(비유한 수 전부); bool 2건 일치; date·datetime 3건은 값 문자열만 같고 **형이 `text`**; None 1건 일치.
- 서버 로그(`out/x26_1_server.log`): `CREATE VIEW … AS SELECT '100%' AS c`, `'a%%b'`, `'a %s b'`, `'%(x)s'` 모두 **입력 그대로** 서버에 도착(`%`가 줄거나 늘지 않음).
- **관찰된 위험 두 가지:** ① 비유한 수는 따옴표 없이 렌더되어 **FROM 절에 `nan`·`infinity` 이름의 열이 있으면 그 열 값으로 조용히 해석**된다(확인: 열 `nan`=111인 표를 FROM으로 한 뷰에서 `Decimal('NaN')`→111, `Infinity`→222, float `nan`→111.0, `out/x26_2d_misc.out`). 열 내부 이름이 번호 기반이면 현실 위험은 낮지만 BZ7의 "`NaN`·`Infinity` 거부"는 필수다. ② `literal()`의 date·float·정수형 Decimal 렌더는 뷰에서 형이 달라진다(X-26.3).

## X-26.2 주입 시도 (안전 경로 vs 대조군)
`bi_app`으로 `public.t`(행 2개, `bi_app`에 DML)와 `bi_data.evil`(생성 여부)을 증거로 썼다. 대조군 코드는 하네스에만 있고 저장소에 넣지 않았다. 입력 10종: `x'); DROP TABLE public.t; --`, `x'; CREATE TABLE bi_data.evil(a int); --`, `x' AS c; DELETE FROM public.t; --`, 역슬래시+작은따옴표 조합 4종(`x\'; DELETE …`, `\'; CREATE TABLE …`, `x\''; …`, `x\\'; …`), `$$; DELETE …`, 문맥 주입 `x' || (SELECT string_agg(v, ',') FROM public.t) || '`, `x' UNION SELECT 'leak' --`.

| 경로 | `standard_conforming_strings` | 결과 (입력 10종) |
| --- | --- | --- |
| **`CreateView` + `literal` (우리 방식)** | on(기본, 방언 `_backslash_escapes=False`) | **추가 문장 실행 0건**. `evil` 없음, `t` 행 2개 유지, **10건 모두 라운드트립 일치** |
| 같은 경로 | **off**(`ALTER DATABASE x26 SET …=off` 후 새 엔진, 방언이 `_backslash_escapes=True`로 판정) | **0건**. 렌더에서 `\`→`\\`로 두 배, 10건 모두 일치. 렌더 예: `'x\\''; DELETE …'` |
| 대조군 A: f-string 무이스케이프 + `exec_driver_sql` | on | **문장 이어붙이기 성립**: `evil` 생성(3건), `public.t` 전 행 삭제(2건), `string_agg` 값이 뷰에 섞임(`'xa,b'`). 나머지는 부작용 없음(`x'); DROP …`은 문법 오류로 문장 전체 거부, `$$…`·`x\''…`은 문자열로 해석, `UNION`은 뷰 열 이름만 달라짐) |
| 대조군 B: 작은따옴표만 두 배로 하는 불완전 이스케이프 | on | 0건 (백슬래시가 이스케이프가 아니므로) |
| 대조군 B | **off** | **이어붙이기 성립**(`\'` 포함 3건: `evil` 생성 2건, `t` 삭제 1건) |
| **방언 판정과 서버 설정이 어긋난 경우**(시나리오 A: 엔진 첫 연결 때 on, 이후 서버 DB 설정이 off로 바뀌고 같은 엔진이 새 연결) | on으로 판정, 새 연결은 off | **우리 방식에서 주입 성립**: 백슬래시 입력 2건에서 `DELETE FROM public.t` 실행(`t` 0행), `evil` 생성 |
| 시나리오 B(판정 off, 이후 서버 on) | off로 판정, 새 연결은 on | 주입 없음. 값이 바뀜: `a\b`가 `a\\b`로 저장, **라운드트립 불일치** |
| 시나리오 A + **같은 트랜잭션 라운드트립 확인 후 불일치면 롤백** | 어긋남 | 백슬래시 입력 2건: 되읽기 오류(`column v_inj.c does not exist`)로 롤백 → **`DELETE`·`CREATE TABLE`까지 모두 취소**(`t` 2행, `evil` 없음). 백슬래시 없는 입력은 어긋남과 무관하게 안전 |
| 시나리오 A의 완화책: 연결 시작 매개변수 `connect_args={"startup_params": {"standard_conforming_strings": "on"}}` | DB 설정 off여도 세션은 on | 세션 `standard_conforming_strings=on`, 방언 판정도 on → **주입 0건** |
| NUL을 낀 주입(`x\x00'; CREATE TABLE …`, 끝에 NUL, NUL만) | — | 3건 모두 `08P01 invalid message format`으로 **서버가 메시지 전체를 거부**, 아무것도 실행되지 않음 |
- **pg8000 프로토콜 확인(`x26_2c`, 서버 로그 `out/x26_2c_protocol.log`):** 파라미터 없는 쿼리는 `statement: …`(simple)로 가고 `SELECT 1 AS a; SELECT 2 AS b`처럼 **여러 문장이 실행**된다. 파라미터가 있으면 `execute <unnamed>: … $1`(extended)이고 `SELECT $1::int; SELECT 2`는 `cannot insert multiple commands into a prepared statement`로 거부된다. 무파라미터 `SELECT '100%%'`는 서버에 `100%%` 그대로 간다(두 배로 만들지도 줄이지도 않음). 파라미터가 있어도 따옴표 안의 `%%`·`%s`는 건드리지 않는다(`convert_paramstyle`이 따옴표 상태를 추적). `CreateView`(무파라미터)는 simple query, 미리보기 `select(literal())`은 `$1::VARCHAR` 바인드(extended)다.
- **방언 판정 확인:** 서버 로그에 연결 직후 `show standard_conforming_strings`가 한 번 찍힌다(소스 근거 `base.py:5938-5944`와 일치).

## X-26.3 미리보기(bind)와 뷰(literal) 의미 동일성
같은 식 E에 대해 (a) `select(E)` 바인드 실행, (b) `CreateView(select(E))` 후 뷰 읽기를 비교했다. 비교 항목: DB 형(`pg_typeof`), DB 문자 표기(`cast(… as text)`), 파이썬 값·형. 식은 값 종류별 5~10개(연산, 비교, 집계 아님, `coalesce`, `like`/`contains`, `mod`, `power`, `extract`, `to_char` 등) × 값 33개 = 346건. 원출력 `out/x26_3_equiv_plain.out`, `out/x26_3_equiv_typed.out`.

| 방식 | SAME | 다름·오류 |
| --- | --- | --- |
| **평범한 `literal(값)`** | 248 | **98건**: DB 형만 다름 26(str: bind `character varying` ↔ 뷰 `text`), 그 밖에 형·DB 표기·값이 다른 것 35건(float 계열, date·datetime, 정수형 `Decimal('12')`), 뷰만 오류 18(날짜 연산·`extract`·`to_char`, `%` 연산자), 바인드만 오류 17(`10**30` 정수, 날짜-문자열 비교, None), 양쪽 오류 2 |
| **타입을 CAST로 못박은 literal**(str→`CAST(… AS TEXT)`, int·Decimal→`CAST(… AS NUMERIC)`, float→`CAST(… AS FLOAT)`, date→`CAST(… AS DATE)`, datetime→`CAST(… AS TIMESTAMP)`, None→`CAST(NULL AS TEXT)`) | **324** | 22건, 모두 원인이 설명됨: 바인드만 오류 14(`10**30`이 BIGINT 범위 초과 11 + 날짜와 문자열 직접 비교 3), 뷰만 오류 5(`%` 연산자), 양쪽 오류 3(`10**30 % 7`, `0/0`, `None + 1`) |
- **다른 경우 목록(평범한 literal):**
  1. **float**: 뷰에서 `numeric`으로 계산되어 결과가 다르다. 예) `0.1*3`: bind `0.30000000000000004`(float8) ↔ 뷰 `0.3`(numeric); `(1/3)*3`: bind `1` ↔ 뷰 `0.9999999999999999`; `3.0` 표기 `3` ↔ `3.0`; `1e100` 표기 `1e+100` ↔ 100자리 숫자.
  2. **date·datetime**: 뷰의 리터럴은 `'2026-10-11'`(unknown→`text`)라서 `date - date`, `date + 1`, `extract(year …)`, `to_char(date, …)`가 **뷰 생성 오류**(`42725`, `22P02`)가 된다. 미리보기는 `%s::DATE`라 성공한다.
  3. **정수형 `Decimal`**: `Decimal('12')`는 `12`(integer)로 렌더되어 `mod`, `power`가 정수/실수 형이 달라진다(`power(12, 2)`: bind `144.00000000000000`(numeric) ↔ 뷰 `144`(double precision)). `Decimal('12') / Decimal('5')`는 SQLAlchemy가 오른쪽을 `CAST(5 AS NUMERIC)`로 감싸 둘 다 `2.4…`로 같았다.
  4. **문자열 형**: 바인드는 `::VARCHAR`, 뷰는 `text`. 값·표기는 같다(영향은 `pg_typeof`뿐).
  5. **`%` 연산자**(`literal(42) % 7`): pg8000 컴파일러가 항상 `%%`를 내보낸다(`pg8000.py:388-394`). 바인드(파라미터 있음)에서는 `%%`→`%`로 정리되어 성공하지만, `CreateView`(파라미터 없음, simple query)에서는 `%%`가 그대로 서버에 가서 **뷰 생성 오류** `42883 operator does not exist`. `func.mod(x, 7)`은 양쪽 SAME(타입 CAST 적용 시).
  6. **범위**: 정수 `10**30`은 바인드가 `::BIGINT`라 오류, 뷰는 성공(`numeric`). BZ7처럼 숫자를 `Decimal`로만 받고 `CAST(… AS NUMERIC)`를 쓰면 같아진다.
  7. **None**: 바인드는 형 없는 NULL 파라미터라 `SELECT %s IS NULL`이 `42P18 could not determine data type`(오류), 뷰는 성공. `CAST(NULL AS TEXT)`처럼 형을 주면 같아진다.
  8. **날짜와 문자열 직접 비교**(`date_literal > '2026-01-01'`): 바인드만 `operator does not exist: date > character varying`, 뷰는 unknown 상수라 성공. AST 단계에서 날짜-문자열 비교를 거부하면 일치한다.
- 읽은 점: 같은 AST라도 **리터럴 렌더 경로가 달라서 평범한 `literal()`은 동일하지 않다.** 타입을 `CAST`로 못박으면 346건 중 324건이 완전히 같고 남은 22건은 위 원인(범위·`%` 연산자·형 없는 비교)이다.

## X-26.4 검증 규칙 후보의 효과 (28개 입력, `out/x26_4_rules.out`)
| 입력 | 규칙 없음(R0)에서 라운드트립 | R1 NUL만 | R2 제어문자(Cc) | R3 +서로게이트(Cs) | R4 +역슬래시 | R5 +200자 |
| --- | --- | --- | --- | --- | --- | --- |
| 평범·한글·`O'Brien`·이모지·NFD/NFC | 일치 | 통과 | 통과 | 통과 | 통과 | 통과 |
| 역슬래시 `a\b` | 일치(on·off 모두 방언이 처리) | 통과 | 통과 | 통과 | **거부** | 거부 |
| 개행·탭·CRLF | 일치 | 통과 | **거부** | 거부 | 거부 | 거부 |
| ESC, DEL, BS, VT, FF, C1(`\x85`) | 일치 | 통과 | **거부** | 거부 | 거부 | 거부 |
| **NUL** | **오류**(서버 `08P01`) | **거부** | 거부 | 거부 | 거부 | 거부 |
| **서로게이트 `\ud800`** | **오류**(파이썬 인코딩) | 통과 | 통과 | **거부** | 거부 | 거부 |
| U+2028/2029, ZWSP, BOM, RLO(우회 방향 문자), NBSP | 일치 | 통과 | 통과(Cc가 아님) | 통과 | 통과 | 통과 |
| 200자 / 201자 / 10,000자 / **1,000,000자** | 일치(1,000,000자 0.12초) | 통과 | 통과 | 통과 | 통과 | 200자 통과, 이상 **거부** |
- **규칙 없이 라운드트립을 깨는 입력은 NUL과 서로게이트(둘 다 조용한 오염이 아니라 오류)와 비유한 수(X-26.1)뿐이다.** 제어문자(개행·탭 등)·역슬래시·긴 문자열은 이 환경에서 라운드트립이 깨지지 않았다. 따라서 규칙 R2·R4·R5의 근거는 **정확성이 아니라** (a) 역슬래시: 방언 판정과 서버 설정이 어긋나는 시나리오(X-26.2 A)에서만 위험 → 이중 방어, (b) 제어문자: 표시·감사(눈에 안 보이는 문자), (c) 길이: UX·뷰 정의 크기다. U+2028·BOM·RLO처럼 눈에 안 보이는 문자는 R2~R5가 거르지 않는다.
- **NFC 정규화:** DB에서 NFD `'한'`(3코드포인트)과 NFC `'한'`(1)은 `=`이 **거짓**이다(`eq=False`, 정규화 후 `True`). 엑셀 붙여넣기 문자열과 표의 값이 서로 다른 정규화 형이면 비교가 조용히 거짓이 되므로 입력과 데이터 쪽 정규화 정책이 별도로 필요하다(안전과 무관, 의미 정확성).

## X-26.5 런타임 내장 DDL 부품 (`bi_app`, 모든 변경은 `bi_data`, `text()`·`exec_driver_sql` 호출 0건: AST 검사 `out/ast_scan_text_usage.out`)
`MigrationContext.configure(conn)` + `Operations(ctx)`로 만든 `op`를 같은 `Connection`에서 썼다. 각 단계는 한 트랜잭션. 원출력 `out/x26_5_ddl.out`, `x26_5b_acl.out`.

| 시험 | 결과 | 출력 SQL |
| --- | --- | --- |
| `CreateTable`(identity PK) + `CreateIndex` + 행 `insert` + `CreateView`, 한 트랜잭션 | **성공**. 객체 소유자 전부 `bi_app`. 기본 권한으로 `bi_readonly`가 표·뷰 읽음. **identity가 시퀀스 `ds_100_id_seq`(kind `S`)를 암묵 생성** | `CREATE TABLE bi_data.ds_100 (id INTEGER GENERATED BY DEFAULT AS IDENTITY, …)`, `CREATE INDEX …`, `CREATE VIEW bi_data.dv_100 AS SELECT … CAST(… AS NUMERIC) AS amount FROM …` |
| `CreateView(or_replace=True)`로 끝에 열 추가 | **성공** (`CREATE OR REPLACE VIEW`) | `CREATE OR REPLACE VIEW bi_data.dv_100 AS …` |
| `or_replace`로 열 빼기 / 이름 바꾸기 / 타입 바꾸기 | **모두 거부** `42P16 cannot drop columns from view` / `cannot change name of view column` (힌트 `ALTER VIEW … RENAME COLUMN`) / `cannot change data type of view column` (03c X-11과 일치) | — |
| `op.add_column` | 성공 | `ALTER TABLE bi_data.ds_100 ADD COLUMN c_4 INTEGER` |
| 의존 뷰가 있는 열 `op.drop_column` | 거부 `2BP01 … view bi_data.dv_100 depends on column c_2` | `ALTER TABLE … DROP COLUMN c_2` |
| 한 트랜잭션: `DropView` → `op.drop_column` → `CreateView`(새 정의) | **성공** | `DROP VIEW …`, `ALTER TABLE … DROP COLUMN c_2`, `CREATE VIEW …` |
| 의존 뷰가 있는 열 `op.alter_column(type_=Numeric(12,2), postgresql_using=…)` | 거부 `0A000 cannot alter type of a column used by a view or rule` | `ALTER TABLE … ALTER COLUMN c_2 TYPE NUMERIC(12, 2) USING c_2::numeric(12,2)` |
| `USING` 없이 text→numeric | 거부 `42804 cannot be cast automatically`(힌트: `USING c_2::numeric(12,2)`) | `ALTER TABLE … ALTER COLUMN c_2 TYPE NUMERIC(12, 2)` |
| 한 트랜잭션: `DropView` → `op.alter_column(… postgresql_using="c_2::numeric(12,2)")` → `CreateView` | **성공**, 데이터 `10.50`, `20.00`로 변환 | `ALTER TABLE … TYPE NUMERIC(12, 2) USING c_2::numeric(12,2)` |
| `postgresql_using`에 SQLAlchemy 표현식(`cast(column("c_2"), Text)`) | **TypeError `Boolean value of this clause is not defined`** (`alembic/ddl/postgresql.py:534`의 `if element.using`) → **`USING`은 문자열만 받는다 = 이 한 곳이 문자열 조립 지점** | — |
| 문자열 없이 타입 바꾸기: `op.add_column`(새 열) → `sa.update(…).values(c_2t=cast(column("c_2"), Text))` → `DropView` → `op.drop_column`(옛 열) → `op.alter_column(new_column_name="c_2")` → `CreateView`, 한 트랜잭션 | **성공** (열 순서가 끝으로 감, 전체 행 재기록) | `ALTER TABLE … ADD COLUMN c_2t TEXT`, `UPDATE … SET c_2t=CAST(c_2 AS TEXT)`, `… DROP COLUMN c_2`, `… RENAME c_2t TO c_2` |
| 열 이름 변경 `op.alter_column(new_column_name)` (의존 뷰 있는 채) | **성공**, 뷰가 따라감(`SELECT id, c_1b AS name …`) | `ALTER TABLE … RENAME c_1 TO c_1b` |
| 표 이름 변경 `op.rename_table` (의존 뷰 있는 채) | **성공**, 뷰가 새 표를 가리킴(`FROM bi_data.ds_101`) | `ALTER TABLE bi_data.ds_100 RENAME TO ds_101` |
| `op.create_index` / `op.drop_index` | 성공 | `CREATE INDEX ix_ds_101_c_3 ON bi_data.ds_101 (c_3)`, `DROP INDEX bi_data.ix_ds_101_c_3` |
| 의존 뷰가 있는 표 `op.drop_table` | 거부 `2BP01 cannot drop table … view depends on it` | `DROP TABLE bi_data.ds_101` |
| 중간 실패: `DropView` → `op.add_column` → `CreateView`(없는 열 참조 → 오류) | 오류, **전부 롤백**(열·뷰 정의 변경 전과 동일) | — |
| `DropView`+`op.drop_table` 정리 | 성공, `bi_data` 객체 목록 빈 값 | `DROP VIEW …`, `DROP TABLE …` |
| 재생성·`or_replace`·이름 변경·열 추가 뒤 `bi_readonly` 읽기 | 매번 **읽힘**(기본 권한 `FOR ROLE bi_app`이 유지되고 이름 변경·열 추가는 ACL을 그대로 둠) | — |
- **빌트인 구성요소만으로 되는 목록(= `text()`·`exec_driver_sql` 불필요):** `CreateTable`, `DropTable`, `CreateIndex`, `CreateView`(`or_replace=True` 포함), `DropView`(`if_exists=True`), 데이터 변경 `insert`/`update`/`delete`(`cast` 포함), Alembic `Operations`: `add_column`, `drop_column`, `alter_column`(`type_=`, `new_column_name=`), `rename_table`, `create_index`, `drop_index`, `drop_table`. (`DropIndex`/`CreateSchema`/`CreateSequence`도 `sqlalchemy.sql.ddl`에 있으나 쓰지 않았다.)
- **예외·간극:** ① `alter_column(type_=…, postgresql_using=…)`의 `USING`은 **문자열**만 받는다 — 식별자가 번호 기반 이름이면 템플릿(`"{col}::numeric(p,s)"`)에 정수·검증 이름만 넣게 해야 하고, 피하려면 "새 열 추가 → `update(cast)` → 옛 열 삭제 → 이름 변경" 경로(문자열 없음)를 쓴다. ② **`ALTER VIEW … RENAME COLUMN`에 해당하는 내장 부품은 없다**(`alembic/operations`·`alembic/ddl`에 view 관련 연산 없음, SQLAlchemy `sql/ddl.py`에는 `CreateView`·`DropView`만 있음: grep 확인). 뷰 열 이름 변경은 `DropView` + `CreateView`로 대체해야 한다(표 열 이름 변경은 뷰가 자동으로 따라감). ③ 모든 부품은 `bi_data` 안에서 `bi_app`으로 한 트랜잭션에 묶였다. ④ `Identity()` 열은 시퀀스(`kind S`)를 암묵 생성하므로 JR1의 "시퀀스 생성 금지/허용 목록 밖 객체 종류 점검"은 **identity 시퀀스를 예외로 두거나 identity 대신 앱이 id를 부여**해야 한다(03c X-15: identity 표 INSERT는 시퀀스 권한 없이 가능).
- **판정(Z7 "text() 금지"가 현실적인가):** 표·뷰·인덱스 생성/삭제, 열 추가·삭제·이름 변경·표 이름 변경은 `text()` 없이 된다. 타입 변경은 문자열 `USING`이 필요하거나(1곳) 새 열 경로로 우회해야 하고, 뷰 열 이름 변경은 재생성으로 대체한다. 즉 "text() 금지"는 가능하며 남는 문자열 지점은 `postgresql_using` 하나다.

## X-26.6 (나) 글자를 별도 표에 저장하고 뷰는 id 서브쿼리로 참조
`public.formula_literals(id identity PK, value text)`(소유자 `bi_owner`, `bi_app`에 DML만), 뷰는 `CASE WHEN status = (SELECT value FROM formula_literals WHERE id = <숫자>) THEN 1 ELSE 0 END`. 원출력 `out/x26_6_jl2.out`.

| 시험 | 결과 |
| --- | --- |
| 뷰 정의에 들어가는 것 | `WHEN status = (( SELECT formula_literals.value FROM formula_literals WHERE formula_literals.id = 1)) THEN 1` — **글자는 정의에 없고 숫자 id만** 있음 |
| `bi_readonly`가 뷰 읽기 / 정적 표 직접 읽기 | 뷰는 **읽힘**(뷰 소유자 `bi_app`의 권한으로 `formula_literals`를 읽음) / `formula_literals` 직접 `SELECT`는 **거부**(`42501`) → `bi_readonly`에 `public` 권한 불필요(JL2의 가정 확인) |
| 글자 수정 `UPDATE formula_literals SET value=… WHERE id=1` (`'완료'`→`"O'Brien"`) | **뷰 재생성 없이 즉시 반영**(뷰 DDL 0건, 집계 20→20으로 새 글자 기준) |
| 락: 읽기 트랜잭션이 4초 열려 있는 동안 | 글자 `UPDATE` **0.04초**(즉시). 같은 때 `CREATE OR REPLACE VIEW`는 `lock_timeout=1.5s` 후 `55P03` **실패**(03c X-7/X-17과 같은 동작) |
| 글자 행 삭제 후 | 서브쿼리가 NULL → 비교가 거짓 → **오류 없이 결과 0** (조용한 오류) |
| 삭제 후 같은 글자를 다시 INSERT | identity라 id가 바뀜(`1`→`2`), 뷰는 옛 id를 가리킴 → **글자 삭제·재삽입은 뷰 재생성이나 id 고정/참조 무결성 필요** |
| `EXPLAIN` 계획 | 서브쿼리는 `InitPlan`(1회 평가, PK 인덱스 스캔 `formula_literals_pkey`) |
| 성능(`EXPLAIN ANALYZE`, ms, 5회 중앙값; 글자표 50/5,000행) | 행 100: 실행 0.03 ↔ 0.09 / 0.03 ↔ 0.05(리터럴 ↔ 서브쿼리). 행 10,000: 1.9 ↔ 1.9 / 1.5 ↔ 1.8. 행 200,000: 28.8 ↔ 30.8 / 30.1 ↔ 33.2. 20개 비교 `CASE`: 행 10,000에서 4.9 ↔ 4.2 / 3.9 ↔ 5.3, 행 200,000에서 46.6 ↔ 53.6 / 48.4 ↔ 50.6. 계획 시간은 서브쿼리가 0.05~0.3ms 더 큼(20개 비교는 0.25ms 대 0.04ms) |
- 읽은 점: 서브쿼리 방식의 실행 시간 절대 차이는 행 100에서 0.06ms 이하, 행 10,000에서 ±1.4ms(상대로는 20개 비교에서 최대 약 +35%), 행 200,000에서 단일 비교 +2~3ms·20개 비교 +2~7ms였고 계획 시간은 0.05~0.3ms 늘었다. 눈에 띄는 병목은 아니었다(모의 데이터, 수식 단순). 장점은 구조적 주입 방어, 글자만 고치는 편집이 `AccessExclusiveLock`을 피함, 형/`CAST` 문제 없음(값이 바인드). 비용은 id 수명 관리(삭제 시 조용히 0, 재삽입 시 id 변경), 표·권한 추가, "뷰 정의만으로는 글자가 안 보임".

## X-26 결론 (Z6 (가), (나), Z7)
1. **Z6 (가) 이스케이프 자체는 안전했다.** 정상 구성(방언 판정 = 서버 설정)에서 `CreateView`+`literal`은 주입 입력 10종 × `standard_conforming_strings` on/off 모두에서 추가 문장 0건, 라운드트립 일치였다. 반면 같은 입력이 f-string 대조군에서는 문장 이어붙이기(표 생성, 행 삭제, 데이터 노출)가 실제로 성립했다 → 위험은 실재하고 SQLAlchemy 렌더가 이를 막는다. **한 가지 틈:** 방언의 `_backslash_escapes`는 엔진 첫 연결 때 한 번 정해지므로(`base.py:5938-5944`) 서버 설정이 그 뒤에 바뀌면 백슬래시 입력으로 주입이 성립했다(확인). 완화는 ① 역슬래시 거부, ② `startup_params`로 `standard_conforming_strings=on` 고정(확인), ③ 같은 트랜잭션 라운드트립 후 불일치 시 롤백(확인: 백슬래시 입력 2건에서 `DELETE`·`CREATE TABLE`까지 롤백됨)이다. 서버로 가는 simple query 경로이므로 라운드트립은 사전 차단이 아닌 **사후 롤백**이라는 점은 그대로다.
2. **Z6 (가) 정확성은 평범한 `literal()`로는 부족하다.** float → numeric(결과 다름), date → text(날짜 연산은 뷰 생성 오류), 정수형 Decimal → integer, 비유한 수 → 따옴표 없는 식별자(열 이름으로 조용히 해석), `%` 연산자 → 뷰 생성 오류, NUL·서로게이트 → 오류. 값을 **타입 있는 값으로 받고 `CAST`로 SQL 형을 못박으면** bind와 literal이 346건 중 324건 같아지고, 남은 22건은 숫자 범위, `%` 연산자(대신 `mod()`), 형 없는 비교 같은 AST 규칙으로 막을 수 있는 것이다.
3. **조건:** (가)를 채택하려면 BZ7 규칙을 `Decimal`(유한)·`bool`·`date`·검증된 `str` 외에 **CAST 감싸기, NaN/Inf/NUL/서로게이트 거부, `%` 연산자 대신 `mod()`, 방언 판정 고정(startup_params) 또는 역슬래시 거부**로 확장해야 한다.
4. **(나)는 필요하지 않지만 가능하다.** 주입 방어와 형 문제가 구조적으로 사라지고 글자 수정은 뷰 재생성이 필요 없다(락 회피 확인). 비용은 id 수명 관리와 구현 규모다.
5. **Z7:** `text()` 없이 되는 DDL은 위 목록이고, 문자열 지점은 `postgresql_using` 하나, 내장 부품이 없는 것은 뷰 열 이름 변경이다. identity 시퀀스는 객체 종류 점검의 예외로 다뤄야 한다.

## X-26 한계
- Python 3.12 / pg8000 1.31.5 / SQLAlchemy 2.1.4 / PostgreSQL 16.10 한 조합 기준. `client_encoding`이 UTF8이 아닌 서버는 시험하지 않았다. 서버 로그는 `log_statement=all`로 켜서 봤다.
- 모의 데이터(난수 아님, 단순 값). 수식 복잡도, 동시 사용자, 다른 소스에서 오는 값(엑셀 날짜 직렬값 등)은 시험하지 않았다. 동일성 시험의 식은 이 보고서의 목록(약 40종)이며 윈도 함수·`LATERAL`·`UNION ALL`은 넣지 않았다.
- 미리보기 경로는 `execute(select(...))`(바인드)이며 실제 앱 미리보기 코드가 아니다. `startup_params`는 pg8000 1.31.5의 `connect_args`로만 확인했고 다른 버전·다른 연결 방식은 시험하지 않았다.
- `DropIndex` 구성요소, `ALTER VIEW … RENAME COLUMN`(내장 부품 없음은 grep 확인, 실행 시험 없음), 시퀀스·함수 `DDL` 금지 점검 자체는 시험하지 않았다. 성능은 서버 내부 시간이며 pg8000 전송·파싱 시간은 제외했다.

---

# X-29. `alembic check`와 왕복 테스트 틀 (+ 2계정 구성 마이그레이션)

구성: `backend/`의 `alembic.ini`, `migrations/`(`env.py`, baseline `0001`), `app/config.py`·`app/db.py`를 `r4/alembic_scratch/`에 복사했다. `env.py`는 환경변수(`X29_TARGET`, `X29_SCHEMAS`, `X29_FILTER`, `X29_COMPARE_TYPE`, `X29_TPM`)로 `target_metadata`, `include_schemas`, `include_name`/`include_object`를 바꿀 수 있게 고쳤다(원본은 `env.py.orig`). 가짜 정적 모델 `models.py`는 `teams`, `datasets`(FK `team_id`), `dataset_columns`(FK `dataset_id`) 3개. 실험용 revision `0002`(정적 표 3개를 `op.create_table`, 이어서 고정 문자열 `op.execute`로 `GRANT SELECT, INSERT, UPDATE, DELETE … TO bi_app`, `GRANT USAGE, CREATE ON SCHEMA bi_data TO bi_app`, `GRANT USAGE ON SCHEMA bi_data TO bi_readonly`, `ALTER DEFAULT PRIVILEGES FOR ROLE bi_app IN SCHEMA bi_data GRANT SELECT ON TABLES TO bi_readonly`; `downgrade`는 이의 `REVOKE`/`ALTER DEFAULT PRIVILEGES … REVOKE` + `drop_table` 3개). db-bootstrap 상태 = 슈퍼유저가 역할 3개, `bi_data`(`AUTHORIZATION bi_owner`), `GRANT CREATE ON SCHEMA public TO bi_owner`, `GRANT bi_app TO bi_owner WITH INHERIT TRUE, SET FALSE`를 만든 상태(DB `x29`).

## X-29.2 2계정 구성에서의 마이그레이션 (`bi_owner`로 접속)
| 시험 | 결과 |
| --- | --- |
| `bi_app`으로 `alembic upgrade`(계정 분리 확인) | **실패** `42501 permission denied for schema public`(버전 표 `alembic_version` 생성 단계). 마이그레이션은 `bi_app`으로 못 돌린다 |
| `bi_owner`로 `upgrade head` (0001 → 0002) | **성공**. 같은 트랜잭션에서 표 생성 + 4개 권한 문장 실행. 서버 로그에 고정 문장 그대로 기록 |
| 결과 상태 | `alembic_version`·정적 표 3개·identity 시퀀스 3개 모두 **소유자 `bi_owner`**(`public`). 정적 표 ACL `{bi_owner=arwdDxt/bi_owner,bi_app=arwd/bi_owner}`. `alembic_version`은 ACL 없음(`bi_app`은 못 읽음). `bi_data` ACL `{bi_owner=UC/bi_owner,bi_app=UC/bi_owner,bi_readonly=U/bi_owner}`. `pg_default_acl` 1행 `bi_app / bi_data / r / {bi_readonly=r/bi_app}` |
| `upgrade head` 두 번째 | **아무것도 하지 않음**(`alembic_version`=`0002`이므로 revision 미실행, 오류 없음) |
| 이후 `bi_app`이 `bi_data`에 만든 표·뷰 | `bi_readonly`가 읽음(`ds_1`, `dv_1`). **`bi_owner`가 만든 `bi_data.ds_2`는 `bi_readonly`가 못 읽음**(기본 권한이 `FOR ROLE bi_app`뿐) |
| 같은 4개 권한 문장을 `bi_owner`가 revision 밖에서 다시 실행 | **모두 성공·멱등**(오류 없음, `pg_default_acl` 여전히 1행). `CREATE TABLE teams`만 `already exists`로 실패(= Alembic 버전 표가 막는 대상) |
| `GRANT bi_app TO bi_owner WITH INHERIT TRUE, SET FALSE`를 이미 있는 상태에서 다시(db-bootstrap 매 기동) | **오류 아님**, `NOTICE: role "bi_owner" has already been granted membership in role "bi_app" by role "postgres"`, 옵션 그대로, 행 1개 유지 |
| 같은 멤버십에 **옵션 없는** `GRANT bi_app TO bi_owner` | NOTICE만, **옵션을 덮어쓰지 않음**(`inherit t / set f` 유지) |
| 같은 멤버십에 **다른 옵션** `WITH INHERIT FALSE, SET TRUE` | **옵션이 갱신됨**(NOTICE 없음) → 이어서 `WITH INHERIT TRUE, SET FALSE`로 원복됨. 즉 매 기동 명시 옵션으로 `GRANT`하면 옵션 이탈이 자동 복구된다 |
| 멤버십이 없는 상태(`REVOKE bi_app FROM bi_owner`)에서 `upgrade head` | **실패** `42501 permission denied to change default privileges`(마지막 문장), **전부 롤백**(`alembic_version` 비어 있음, `teams` 없음, `bi_app`의 `bi_data` CREATE 없음). 멤버십 복구 후 같은 `upgrade head` 성공 |

## X-29.3 왕복 테스트 (upgrade → downgrade → upgrade, 스냅샷 비교)
스냅샷 하네스: `r4/db/x29_snapshot.py`(`public`·`bi_data` 표·열·인덱스·FK·PK, 객체 소유자·ACL, 스키마 ACL, `pg_default_acl`, 멤버십, 역할 속성, `alembic_version` 행; SQLAlchemy `inspect()`와 카탈로그 표 객체만, `text()` 없음) + `snapdiff.py`(비교, `--normalize`, `--ignore-dynamic`) + `x29_roundtrip.sh`(전체 절차) + `a.sh`(alembic 실행). 원출력 `out/x29/rt/`.

| 시험 | 결과 |
| --- | --- |
| 출발 상태 A = db-bootstrap 직후 → `upgrade head` → B | B에서 정적 표·권한·기본 권한·`bi_data` ACL이 생김(위 표) |
| 동적 객체(`bi_data.ds_1`·`dv_1`은 `bi_app` 소유, `ds_2`는 `bi_owner` 소유) 생성 후 `downgrade base` | **동적 객체 7개(표·시퀀스·인덱스·뷰) 전부 동일하게 보존**(소유자·ACL 포함). `bi_data` 스키마도 **지워지지 않음**. 함수 `bi_data.f_dyn()`도 보존 |
| `downgrade base` 후 권한 | `bi_app`·`bi_readonly`의 `bi_data` USAGE/CREATE **회수됨**(REVOKE 복원 확인), `bi_readonly`가 `ds_1`·`dv_1` 읽기 **불가**(스키마 USAGE 없음), `pg_default_acl` **0행**(`ALTER DEFAULT PRIVILEGES … REVOKE`가 행을 지움) |
| 다시 `upgrade head` | 스냅샷이 **이전 upgrade 상태와 완전히 같음**(IDENTICAL). `bi_readonly`가 기존 동적 객체를 **다시 읽음**(객체 ACL이 유지됨) |
| 두 번째 왕복(downgrade → upgrade) | 첫 왕복과 스냅샷 동일 (head0=head1=head2, base0=base1) |
| A(부트스트랩)와 `downgrade base` 후 비교, **정규화 없이** | **다른 것 2가지**: ① `alembic_version` 표와 PK 인덱스가 **빈 채로 남는다**(Alembic은 버전 표를 지우지 않음) ② `bi_data` 스키마 ACL이 `NULL` → `{bi_owner=UC/bi_owner}`(권한 효력은 같음) |
| 같은 비교, 정규화(버전 표 제외, 스키마 ACL NULL = 소유자 전체) | **IDENTICAL** |
| `downgrade base`가 복원하지 않는 것(= db-bootstrap 관할, 마이그레이션이 만들지 않음) | 역할 3개와 속성, `GRANT bi_app TO bi_owner` 멤버십, `bi_data` 스키마·소유자, `GRANT CREATE ON SCHEMA public TO bi_owner`, 동적 객체와 그 ACL(동적 객체는 지우지도 되돌리지도 않음) |
| 의존 뷰가 있을 때(내가 `public.v_static`을 `teams` 위에 만들어 둔 경우) `downgrade base` | **`DROP TABLE teams` 실패** `2BP01 view v_static depends on table teams`, 트랜잭션 전체 롤백(`out/x29/downgrade_blocked_by_view.out`). 정적 표 위에 다른 객체를 만들면 `downgrade`가 막힌다 |

## X-29.1 `alembic check` / `revision --autogenerate` 구성별 행렬
출발: DB가 head(0002)이고 `bi_data`에 `ds_1`·`dv_1`(`bi_app` 소유), `ds_2`(`bi_owner` 소유), 함수 `bi_data.f_dyn()`, `public`에 뷰 `v_static`·함수 `f_static()`·모델에 없는 표 `legacy_unmodeled`를 둔 상태에서 `bi_owner`로 실행. 원출력 `out/x29/matrix_*.out`, `m2_*.out`.

| 구성 (`target_metadata`=정적 모델) | `bi_data` 동적 객체 | 비고 |
| --- | --- | --- |
| `include_schemas=False`(기본), 필터 없음/`include_object`/`include_name`/둘 다 | **언급 없음**(`ds_1`·`ds_2` 삭제 후보 아님). 모델에 없는 `public.legacy_unmodeled`만 `remove_table`로 제안 | 기본 `False`만으로 이미 `bi_data`를 보지 않음(확인, F-DB Q8 문서 서술과 일치) |
| **`include_schemas=True`, 필터 없음** | **`remove_table ds_2`, `remove_table ds_1` 제안**(소유자 `bi_app`이든 `bi_owner`든 둘 다). `autogenerate` 파일은 `op.drop_table('ds_2', schema='bi_data')`, `op.drop_table('ds_1', …)`와 downgrade의 `create_table`을 생성 | 위험 구성 확인. **뷰 `dv_1`·함수·`public` 뷰 `v_static`·함수 `f_static()`은 제안 대상 아님**(autogenerate는 표·열·인덱스·제약만; 확인) |
| `include_schemas=True` + `include_object`(리플렉션 객체의 schema가 `bi_data`면 False) | `bi_data` 제안 **없음** | 안전 |
| `include_schemas=True` + `include_name`(type `schema`에서 `bi_data` 제외) | 제안 **없음** | 안전, `include_object`보다 가벼움(스키마 단계에서 제외) |
| `include_schemas=True` + 둘 다 | 제안 없음 | — |
- **동적 객체가 없는 정적 모델과 DB가 일치할 때**(`legacy_unmodeled` 삭제 후): 8가지 구성 중 `include_schemas=True`+필터 없음 한 가지만 실패(위 `ds_1`·`ds_2`), 나머지 7가지는 `No new upgrade operations detected.` 종료 코드 0.
- `alembic_version` 표는 `public`에 생김(소유자 `bi_owner`, `search_path`에서 `"$user"` 스키마가 없어 `public`). `include_schemas=True`+필터 없음에서도 `alembic_version`은 제안 대상이 아니다(Alembic이 제외).
- **정적 모델 변경 감지(권장 후보 구성 `include_schemas=False`+`include_object`+`include_name`, 그리고 `include_schemas=True`+둘 다, 두 구성 동일 결과):**

| 모델 변경 | `alembic check` | 종료 코드 |
| --- | --- | --- |
| 열 추가(`datasets.owner_note`) | `[('add_column', None, 'datasets', Column('owner_note', Text(), …))]` | 255 |
| 표 추가(`audit_log`) | `[('add_table', Table('audit_log', …))]` | 255 |
| 열 삭제(`datasets.def_version`) | `[('remove_column', …)]` | 255 |
| 타입 변경(`Text` → `String(50)`, `Integer` → `BigInteger`), `compare_type=True`(현재 `env.py`) | `[('modify_type', …, TEXT(), String(length=50))]` | 255 |
| 같은 타입 변경, `compare_type=False` | `No new upgrade operations detected.` (**감지 못 함**) | 0 |
- 변경 없는 모델: `No new upgrade operations detected.`, 종료 코드 0. `revision --autogenerate`는 변경이 없어도 **빈 revision 파일**(`pass`)을 만든다(`check`가 이를 대신함).
- **`autogenerate`가 만들지 않는 것:** `GRANT`, `ALTER DEFAULT PRIVILEGES`, 뷰, 함수. 새 정적 표를 `autogenerate`로 만들면 `bi_app`에 대한 `GRANT`가 빠진 revision이 나오므로(확인: 생성 파일에 `GRANT` 없음) 권한은 수동 추가이며 `alembic check`로는 잡히지 않는다(권한 스냅샷 비교가 잡는다). 이름 변경은 add/drop 쌍으로 나온다는 문서 서술은 시험하지 않았다.
- **저장소 가드 테스트와의 상호작용(정적, 저장소 `backend/tests/test_migrations.py` 함수를 읽기 전용으로 불러 scratch 0002에 적용; pytest는 이미지에 없어 실행하지 않음, `out/x29/guard_test_on_0002.out`):** D3(execute 인자가 고정 문자열) = 7개 문장 모두 통과. **D2(`DROP` 검출)는 `downgrade()`의 `op.drop_table` 3개를 DROP으로 잡는다**(`drop_` 접두 호출 검출) → 첫 실제 revision의 `downgrade()`가 표를 지우면 `DROP_APPROVED` 기록이 필요하다. 또한 `test_single_head_and_baseline`은 `get_heads() == ["0001"]`을 단정하므로 첫 실제 revision 추가 시 갱신이 필요하다(저장소 테스트 내용을 읽고 판단한 것이며 실행하지 않았다).

## X-29.4 실패 시나리오
| 시험 | 결과 |
| --- | --- |
| 한 revision에서 `op.create_table` 성공 후 `GRANT … ON no_such_table` 실패 | `upgrade` 종료 코드 1, **표 없음, `alembic_version`=이전 값(0002)** — DDL과 버전 기록 모두 롤백 |
| 두 revision(0003 성공, 0004 실패), 기본(`transaction_per_migration=False`) | **둘 다 롤백**(0003의 표 `t_a` 없음, 버전 0002). 한 번의 `upgrade`가 하나의 트랜잭션 |
| 같은 두 revision, `transaction_per_migration=True` | 0003은 **커밋됨**(`t_a` 존재, 버전 `0003`), 0004만 롤백 → 부분 적용 상태가 남을 수 있다 |
| (X-29.2) 멤버십 없음 | 위 표: 전부 롤백, 복구 후 재실행 성공 |
- 현재 `backend/migrations/env.py`는 `transaction_per_migration`을 설정하지 않으므로 기본(False) = 한 번의 `upgrade head` 전체가 원자적이다(소스: 저장소 `env.py`에 해당 인자 없음, 확인: scratch 원본과 동일).

## X-29.5 도구 동작
| 항목 | 결과 |
| --- | --- |
| `alembic heads` | 한 줄에 하나(`0002 (head)`). 2개 head이면 2줄(`0003b (head)`, `0004 (head)`), `-v`는 Rev/Parent/Path 출력. **DB 없이 실행됨**(존재하지 않는 DB 이름에서도 성공). CI에서 `alembic heads | grep -c "(head)"`로 개수 검사 가능(확인: 2) |
| 다중 head에서 `upgrade head` | 거부 `Multiple head revisions are present …`, 종료 코드 255 |
| 다중 head·뒤처진 DB에서 `alembic check` | `FAILED: Target database is not up to date.` 종료 코드 255 → **`check` 전에 `upgrade head` 필요** |
| `alembic check` 종료 코드 | 변경 없음 0 / 새 연산 감지 255(`FAILED: New upgrade operations detected: [...]`, 같은 내용이 `ERROR [alembic.util.messaging]` 줄로 한 번 더 나와 stderr/stdout에 중복) / `target_metadata=None`(현재 저장소 상태)이면 255 `Can't proceed with --autogenerate option; environment script … does not provide a MetaData object` / DB 접속 불가는 1(트레이스백) |
| `alembic current`, `history`, `branches` | 정상(`history`는 분기점·head 표시) |
| 로그 형식 | 기본 INFO가 stderr에 `INFO  [alembic.runtime.migration] …`, 감지 내용은 `INFO  [alembic.autogenerate.compare.tables] Detected removed table 'bi_data.ds_1'` 형식 |

## X-29 결론 (BZ14·BZ16·Z0)
1. **`alembic check` 구성:** `target_metadata`에 정적 모델 `MetaData` 하나를 연결하고 **`include_schemas=False`(기본) 하나만으로** `bi_data` 동적 객체(소유자 무관)는 제안 대상이 되지 않았다. `include_schemas=True`로 바꾸면 필터 없이 `ds_*`가 `drop_table`로 제안(생성 파일에 `op.drop_table('ds_1', schema='bi_data')`)되므로 `include_name`(schema `bi_data` 제외) 또는 `include_object`를 안전망으로 둔다 — 둘 중 하나로 충분했다. 뷰·함수는 어느 구성에서도 제안 대상이 아니었다. 열 추가·삭제·표 추가·타입 변경은 감지된다(`compare_type=True` 필요). 종료 코드는 0 / 255 / (DB 오류 1)이며 DB가 head 상태여야 한다.
2. **2계정 구성:** `bi_owner`로 정적 표 생성 + 4개 권한 문장이 한 트랜잭션에서 성공했고, 같은 권한 문장은 반복 실행해도 멱등이다. 멤버십 `INHERIT TRUE, SET FALSE`가 없으면 `ALTER DEFAULT PRIVILEGES FOR ROLE bi_app`에서 실패하고 전부 롤백된다 → db-bootstrap이 migrate보다 먼저여야 한다. 이미 있는 멤버십에 대한 `GRANT … WITH INHERIT TRUE, SET FALSE` 재실행은 오류가 아니라 NOTICE이고 명시 옵션은 갱신된다(매 기동 실행 안전).
3. **왕복 테스트:** upgrade → downgrade → upgrade가 스냅샷 완전 일치로 돌아오고, 동적 객체와 `bi_data` 스키마는 보존되며, `REVOKE`와 `ALTER DEFAULT PRIVILEGES … REVOKE`로 권한·기본 권한이 복원된다. 복원되지 않는 것은 `alembic_version` 빈 표, 스키마 ACL의 NULL/명시 차이(정규화로 흡수), 그리고 db-bootstrap 관할 객체(역할·멤버십·`bi_data`)다. 정적 표 위에 외부 뷰가 있으면 `downgrade`가 막힌다.
4. **주의:** 새 정적 표의 `GRANT`는 `autogenerate`가 만들지 않고 `check`도 잡지 못한다(권한 스냅샷이 잡음). 저장소의 D2 가드 테스트는 `downgrade`의 `drop_table`도 `DROP`으로 본다.

## X-29 한계
- PostgreSQL 16.10, Alembic 1.20.0, 가짜 모델(표 3개)과 소량 객체 기준. 정적 표 수가 많거나 동적 객체가 수천 개일 때의 `check` 시간은 재지 않았다(`include_object`는 완전 리플렉션 후 필터라는 문서 서술도 확인하지 못함; 이번 구성은 `include_schemas=True`+`include_name`이 스키마 단계에서 막는 것을 확인했을 뿐 시간 비교는 없음).
- `version_table_schema`를 바꾼 구성은 시험하지 않았다(기본 `public` 위치만 확인). `compare_server_default`, 이름 변경 감지, 제약 이름 비교, 데이터 이전이 있는 revision은 시험하지 않았다.
- 저장소 `backend/`의 현재 baseline revision만 복사해 쓰고 실험용 revision `0002`는 scratch에만 있다. 저장소 `test_migrations.py`는 pytest가 이미지에 없어 **실행하지 않고** 함수만 읽기 전용으로 적용했다. Jenkins·`profile test` compose 서비스(`migrate`, `db-bootstrap`)로는 시험하지 않았고 이 컨테이너 한 대에서 `psql`/`alembic` CLI를 직접 썼다.
- 정적 표 `ALTER DEFAULT PRIVILEGES FOR ROLE bi_owner IN SCHEMA public GRANT … TO bi_app`(새 정적 표 권한 자동화 아이디어)는 시험하지 않았다.
- 시험 설정을 위해 DB 수준 설정(`ALTER DATABASE x26 SET standard_conforming_strings`)을 바꿨다가 모두 복구했고 컨테이너와 함께 사라졌다(tmpfs).

---

# 하네스 전용 코드에 대한 메모
- 저장소 규칙(`text()`·`exec_driver_sql` 금지)은 런타임 후보 코드 대상이다. 실험 하네스에서만 `exec_driver_sql`을 쓴 곳: `x26_2_inject.py`(대조군 f-string 실행), `x26_2b_mismatch.py`(서버 설정 변경), `x26_2c_protocol.py`(프로토콜 관찰), `x26_6_jl2.py`(`EXPLAIN`, `GRANT`, `SET LOCAL lock_timeout`). `x26_1`, `x26_3`, `x26_4`, `x26_5`, `x26_5b`, `x29_snapshot.py`, `x29_dyn.py`는 `text()`·`exec_driver_sql` 호출이 0건이다(AST 검사).
