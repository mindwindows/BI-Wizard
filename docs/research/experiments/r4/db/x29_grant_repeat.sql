\set ON_ERROR_STOP off
\pset pager off
\echo === 시작 상태
SELECT roleid::regrole AS role, member::regrole AS member, grantor::regrole AS grantor, admin_option, inherit_option, set_option FROM pg_auth_members WHERE roleid='bi_app'::regrole AND member='bi_owner'::regrole;
\echo === (a) 같은 문장 재실행: GRANT bi_app TO bi_owner WITH INHERIT TRUE, SET FALSE
GRANT bi_app TO bi_owner WITH INHERIT TRUE, SET FALSE;
SELECT inherit_option, set_option, admin_option, grantor::regrole FROM pg_auth_members WHERE roleid='bi_app'::regrole AND member='bi_owner'::regrole;
\echo === (b) 옵션 없이 재실행: GRANT bi_app TO bi_owner  (옵션이 기본값으로 덮이는가)
GRANT bi_app TO bi_owner;
SELECT inherit_option, set_option, admin_option FROM pg_auth_members WHERE roleid='bi_app'::regrole AND member='bi_owner'::regrole;
\echo === (c) 다시 WITH INHERIT TRUE, SET FALSE 로 갱신되는가
GRANT bi_app TO bi_owner WITH INHERIT TRUE, SET FALSE;
SELECT inherit_option, set_option, admin_option FROM pg_auth_members WHERE roleid='bi_app'::regrole AND member='bi_owner'::regrole;
\echo === (d) 다른 옵션 WITH INHERIT FALSE, SET TRUE 로 재실행(갱신) 후 원복
GRANT bi_app TO bi_owner WITH INHERIT FALSE, SET TRUE;
SELECT inherit_option, set_option, admin_option FROM pg_auth_members WHERE roleid='bi_app'::regrole AND member='bi_owner'::regrole;
GRANT bi_app TO bi_owner WITH INHERIT TRUE, SET FALSE;
SELECT inherit_option, set_option, admin_option FROM pg_auth_members WHERE roleid='bi_app'::regrole AND member='bi_owner'::regrole;
\echo === (e) 멤버십 행 수(중복 생성 안 되는가)
SELECT count(*) FROM pg_auth_members WHERE roleid='bi_app'::regrole AND member='bi_owner'::regrole;
\echo === (f) 마이그레이션 SQL 4문장을 bi_owner가 직접 다시 실행 (revision 밖 반복 실행 시 멱등성)
SET ROLE bi_owner;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.teams, public.datasets, public.dataset_columns TO bi_app;
GRANT USAGE, CREATE ON SCHEMA bi_data TO bi_app;
GRANT USAGE ON SCHEMA bi_data TO bi_readonly;
ALTER DEFAULT PRIVILEGES FOR ROLE bi_app IN SCHEMA bi_data GRANT SELECT ON TABLES TO bi_readonly;
RESET ROLE;
SELECT 'default_acl rows' AS chk, count(*) FROM pg_default_acl;
\echo === (g) CREATE TABLE 재실행은 멱등이 아님 (Alembic 버전 표가 막는 대상)
SET ROLE bi_owner;
CREATE TABLE public.teams (id int);
RESET ROLE;
