-- db-bootstrap 상태 모사 (슈퍼유저 postgres, 데이터베이스 x29): 역할은 이미 있음(bi_owner, bi_app, bi_readonly)
\set ON_ERROR_STOP on
CREATE SCHEMA bi_data AUTHORIZATION bi_owner;
GRANT CREATE ON SCHEMA public TO bi_owner;
GRANT bi_app TO bi_owner WITH INHERIT TRUE, SET FALSE;
