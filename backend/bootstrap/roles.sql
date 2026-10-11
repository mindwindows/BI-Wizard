-- BI-Wizard db-bootstrap: 읽기 전용 계정과 Superset 메타 DB를 멱등으로 만든다.
-- 실행: backend/bootstrap/run.sh (docker compose up 때마다, 슈퍼유저 POSTGRES_USER로 접속).
--
-- 규칙(docs/decisions/03-migration-tool.md, bi-review 항목 3 예외 2):
--  * 역할/DB 이름은 상수 리터럴이다: bi_readonly, superset_meta, superset.
--  * psql ':'var'' 인용 보간은 비밀번호 리터럴 두 곳(ALTER ROLE ... PASSWORD)에만 쓴다.
--    식별자 보간(:"var", format('%I'))과 구문 보간은 쓰지 않는다.
--  * 비밀번호는 환경변수에서 \getenv로 읽는다. 비어 있거나 없으면 실패한다(fail closed).
--  * bi_readonly의 SELECT 권한 부여는 이 단계에서 하지 않는다(Gate ③, D2와 함께 마이그레이션).

\set ON_ERROR_STOP on

\getenv ro_pw POSTGRES_READONLY_PASSWORD
\getenv meta_pw SUPERSET_DB_PASSWORD

-- 역할 생성, 비밀번호 동기화, 검증은 한 트랜잭션이다. 비밀번호가 비어 있어 검증이 실패하면
-- 이 블록 전체가 롤백된다. (변수가 아예 없으면 아래 ALTER가 구문 오류로 실패한다.)
BEGIN;

SELECT 'CREATE ROLE bi_readonly LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'bi_readonly') \gexec

SELECT 'CREATE ROLE superset_meta LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'superset_meta') \gexec

-- 비밀번호 리터럴 두 곳(변경된 .env 값이 다음 기동에서 반영된다).
ALTER ROLE bi_readonly PASSWORD :'ro_pw';
ALTER ROLE superset_meta PASSWORD :'meta_pw';

-- 안전장치: 읽기 전용 계정은 기본적으로 읽기 전용 트랜잭션이다.
ALTER ROLE bi_readonly SET default_transaction_read_only = on;

-- fail closed: 빈 문자열 비밀번호는 PostgreSQL이 비밀번호 없음(NULL)으로 바꾸므로 여기서 걸러낸다.
DO $$
BEGIN
  IF EXISTS (
    SELECT FROM pg_authid
    WHERE rolname IN ('bi_readonly', 'superset_meta') AND rolpassword IS NULL
  ) THEN
    RAISE EXCEPTION 'POSTGRES_READONLY_PASSWORD와 SUPERSET_DB_PASSWORD는 비어 있을 수 없습니다.';
  END IF;
END
$$;

COMMIT;

-- Superset 메타데이터 DB(앱 DB와 별도). CREATE DATABASE는 트랜잭션 밖에서 실행해야 한다.
SELECT 'CREATE DATABASE superset OWNER superset_meta'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'superset') \gexec

-- 메타 DB에는 소유자(superset_meta)만 접속한다. 읽기 전용 계정이 메타 데이터를 보지 못하게 한다.
REVOKE ALL ON DATABASE superset FROM PUBLIC;

\echo '[db-bootstrap] 완료: bi_readonly, superset_meta, superset'
