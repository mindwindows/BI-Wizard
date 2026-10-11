\set ON_ERROR_STOP on
CREATE SCHEMA bi_data;
GRANT USAGE ON SCHEMA bi_data TO bi_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA bi_data GRANT SELECT ON TABLES TO bi_readonly;
CREATE TABLE bi_data.ds_1 (row_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, period_a date NOT NULL, team text NOT NULL, value numeric);
CREATE TABLE bi_data.ds_2 (row_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, base_date date NOT NULL, team text NOT NULL, value numeric);
CREATE TABLE bi_data.ds_3 (row_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, period_a date NOT NULL, team text NOT NULL, value numeric, note text);
INSERT INTO bi_data.ds_1(period_a, team, value) SELECT (date '2024-01-01' + (g||' month')::interval)::date, t, 100+g+ascii(t)%10 FROM generate_series(0,23) g, unnest(array['팀1','팀2','팀3']) t;
INSERT INTO bi_data.ds_2(base_date, team, value) SELECT (date '2024-01-01' + (g||' month')::interval)::date, t, 200+g+ascii(t)%10 FROM generate_series(0,23) g, unnest(array['팀1','팀2','팀3']) t;
INSERT INTO bi_data.ds_3(period_a, team, value, note) SELECT (date '2024-01-01' + (g||' month')::interval)::date, t, 300+g, 'n' FROM generate_series(0,11) g, unnest(array['팀1','팀2']) t;
CREATE VIEW bi_data.dv_1 AS SELECT period_a, team, value, value*2 AS value2 FROM bi_data.ds_1;
CREATE VIEW bi_data.dv_2 AS SELECT base_date, team, value, value*2 AS value2 FROM bi_data.ds_2;
CREATE VIEW bi_data.dv_3 AS SELECT period_a, team, value, note FROM bi_data.ds_3;
-- public table readable by bi_readonly ONLY for the X-20 Superset-permission test (not a real portal table)
CREATE TABLE public.x20_pub (id int, team text, value numeric);
INSERT INTO public.x20_pub VALUES (1,'팀1',1),(2,'팀2',2);
GRANT SELECT ON public.x20_pub TO bi_readonly;
