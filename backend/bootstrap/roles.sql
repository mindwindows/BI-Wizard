-- BI-Wizard db-bootstrap: DB 계정(역할), Superset 메타 DB, 빈 schema bi_data와 기본 권한을 멱등으로 만든다.
-- 실행: backend/bootstrap/run.sh (docker compose up 때마다, 이미지 슈퍼유저 POSTGRES_USER로 접속).
--
-- 규칙(docs/decisions/03-migration-tool.md, bi-review 항목 3 예외 2):
--  * 역할/DB/schema 이름은 상수 리터럴이다: bi_owner, bi_app, bi_readonly, superset_meta, superset, bi_data.
--  * psql ':'var'' 인용 보간은 비밀번호 리터럴 4곳(ALTER ROLE ... PASSWORD)에만 쓴다.
--    식별자 보간(:"var", format('%I'))과 구문 보간은 쓰지 않는다.
--  * 비밀번호는 환경변수에서 \getenv로 읽는다. 비어 있거나 없으면 실패한다(fail closed).
--  * 계정 구성(03b 3-2): bi_owner = 마이그레이션 실행자이자 public 정적 표와 bi_data schema의 소유자,
--    bi_app = backend 런타임(정적 표는 마이그레이션이 명시 GRANT한 것만, bi_data에만 CREATE),
--    bi_readonly = Superset 업무 데이터 연결(읽기 전용). 이미지 슈퍼유저는 이 스크립트만 쓴다.
--  * bi_data의 USAGE/CREATE/SELECT 권한 부여는 이 스크립트가 아니라 마이그레이션(revision 0002)이 한다.

\set ON_ERROR_STOP on

\getenv ro_pw POSTGRES_READONLY_PASSWORD
\getenv meta_pw SUPERSET_DB_PASSWORD
\getenv app_pw POSTGRES_APP_PASSWORD
\getenv owner_pw POSTGRES_OWNER_PASSWORD

-- 역할 생성, 비밀번호 동기화, 검증은 한 트랜잭션이다. 비밀번호가 비어 있어 검증이 실패하면
-- 이 블록 전체가 롤백된다. (변수가 아예 없으면 아래 ALTER가 구문 오류로 실패한다.)
BEGIN;

-- 비밀번호 설정 문장이 실패해도 서버 오류 로그에 문장(평문 비밀번호 포함)이 남지 않게 한다. 고정 문장이다.
SET LOCAL log_min_error_statement = panic;

SELECT 'CREATE ROLE bi_readonly LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'bi_readonly') \gexec

SELECT 'CREATE ROLE superset_meta LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'superset_meta') \gexec

SELECT 'CREATE ROLE bi_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'bi_owner') \gexec

SELECT 'CREATE ROLE bi_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'bi_app') \gexec

-- 비밀번호 리터럴 4곳(변경된 .env 값이 다음 기동에서 반영된다).
ALTER ROLE bi_readonly PASSWORD :'ro_pw';
ALTER ROLE superset_meta PASSWORD :'meta_pw';
ALTER ROLE bi_owner PASSWORD :'owner_pw';
ALTER ROLE bi_app PASSWORD :'app_pw';

-- 속성 재차단(03b 14-1): 위 CREATE ROLE은 역할이 없을 때만 실행된다. 역할이 이미 있을 때 사람이
-- 슈퍼유저·CREATEDB·CREATEROLE 속성을 붙였다면 다음 기동에서 여기서 다시 막는다. 앱 계정 두 개만 대상이고
-- 식별자와 속성은 고정 상수다(보간 없음). 로그인 속성과 비밀번호, 권한은 건드리지 않는다.
ALTER ROLE bi_owner NOSUPERUSER NOCREATEDB NOCREATEROLE;
ALTER ROLE bi_app NOSUPERUSER NOCREATEDB NOCREATEROLE;

-- 안전장치: 읽기 전용 계정은 기본적으로 읽기 전용 트랜잭션이다(세션에서 해제할 수 있으므로 방어선은 권한이다).
ALTER ROLE bi_readonly SET default_transaction_read_only = on;
-- 느린 질의가 DB에서 계속 실행되지 않게 한다(AP-9, 03b 6-3 승인: 30초).
ALTER ROLE bi_readonly SET statement_timeout = '30s';

-- fail closed: 빈 문자열 비밀번호는 PostgreSQL이 비밀번호 없음(NULL)으로 바꾸므로 여기서 걸러낸다.
DO $$
BEGIN
  IF EXISTS (
    SELECT FROM pg_authid
    WHERE rolname IN ('bi_readonly', 'superset_meta', 'bi_owner', 'bi_app') AND rolpassword IS NULL
  ) THEN
    RAISE EXCEPTION 'POSTGRES_READONLY_PASSWORD, SUPERSET_DB_PASSWORD, POSTGRES_OWNER_PASSWORD, POSTGRES_APP_PASSWORD는 비어 있을 수 없습니다.';
  END IF;
END
$$;

-- 빈 schema bi_data: 사용자 데이터 표(ds_*)와 수식 뷰(dv_*, de_*)가 놓이는 곳. 소유자는 bi_owner다(AP-5).
-- 이미 있으면 소유자만 bi_owner로 바로잡는다. 안의 객체와 권한은 건드리지 않는다.
CREATE SCHEMA IF NOT EXISTS bi_data AUTHORIZATION bi_owner;
ALTER SCHEMA bi_data OWNER TO bi_owner;
REVOKE ALL ON SCHEMA bi_data FROM PUBLIC;

-- bi_owner가 bi_app의 상속 멤버여야 마이그레이션이 ALTER DEFAULT PRIVILEGES FOR ROLE bi_app을 실행할 수 있다
-- (03c X-14: INHERIT FALSE는 거부됨). SET FALSE라 SET ROLE bi_app은 못 한다. 반복 실행해도 NOTICE만 난다(X-29).
GRANT bi_app TO bi_owner WITH INHERIT TRUE, SET FALSE;

-- bi_owner는 public에 정적 표와 alembic_version을 만든다(AP-5). PUBLIC에는 CREATE를 주지 않는다
-- (PostgreSQL 15 이후 기본값이지만 볼륨이 이전 구성에서 올 수 있으므로 명시한다).
GRANT CREATE ON SCHEMA public TO bi_owner;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- 이전 구성(Gate ②)의 볼륨: alembic_version을 이미지 슈퍼유저가 만들었다. migrate(bi_owner)가
-- 이어서 쓸 수 있도록 소유자를 바로잡는다. 고정 문장이다(없으면 건너뛴다).
DO $$
BEGIN
  IF to_regclass('public.alembic_version') IS NOT NULL THEN
    ALTER TABLE public.alembic_version OWNER TO bi_owner;
  END IF;
END
$$;

COMMIT;

-- Superset 메타데이터 DB(앱 DB와 별도). CREATE DATABASE는 트랜잭션 밖에서 실행해야 한다.
SELECT 'CREATE DATABASE superset OWNER superset_meta'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'superset') \gexec

-- 메타 DB에는 소유자(superset_meta)만 접속한다. 읽기 전용 계정이 메타 데이터를 보지 못하게 한다.
REVOKE ALL ON DATABASE superset FROM PUBLIC;

\echo '[db-bootstrap] 완료: bi_owner, bi_app, bi_readonly, superset_meta, superset, schema bi_data'
