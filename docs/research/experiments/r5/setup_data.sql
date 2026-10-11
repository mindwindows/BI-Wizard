
\set ON_ERROR_STOP on
CREATE SCHEMA IF NOT EXISTS bi_data;
GRANT USAGE ON SCHEMA bi_data TO bi_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA bi_data GRANT SELECT ON TABLES TO bi_readonly;
CREATE TABLE bi_data.ds_1 (row_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, c_1 numeric NOT NULL, c_2 numeric NOT NULL, c_3 text NOT NULL, team text NOT NULL, period date NOT NULL);
INSERT INTO bi_data.ds_1(c_1,c_2,c_3,team,period)
 SELECT 100+g*10+ascii(t)%10, 50+g*3+ascii(t)%7, CASE WHEN g%3=0 THEN '완료' WHEN g%3=1 THEN '진행' ELSE '대기' END, t, (date '2025-01-01' + (g||' month')::interval)::date
 FROM generate_series(0,11) g, unnest(array['팀1','팀2','팀3']) t;
CREATE VIEW bi_data.dv_1 AS SELECT c_1, c_2, c_3, team, period FROM bi_data.ds_1;
