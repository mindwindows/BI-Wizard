\set ON_ERROR_STOP on
CREATE SCHEMA IF NOT EXISTS bi_data;
GRANT USAGE ON SCHEMA bi_data TO bi_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA bi_data GRANT SELECT ON TABLES TO bi_readonly;
CREATE TABLE bi_data.x25_sales (row_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, period date NOT NULL, team text NOT NULL, product text NOT NULL, amount numeric, qty integer);
INSERT INTO bi_data.x25_sales(period, team, product, amount, qty)
SELECT (date '2024-01-01' + (g||' month')::interval)::date, t, p, 100 + g*3 + ascii(t)%7 + ascii(p)%5, 10 + g
FROM generate_series(0,23) g, unnest(array['팀1','팀2','팀3']) t, unnest(array['상품A','상품B','상품C']) p;
CREATE VIEW bi_data.dv_x25 AS SELECT period, team, product, amount, qty, amount*2 AS amount2 FROM bi_data.x25_sales;
GRANT SELECT ON bi_data.x25_sales, bi_data.dv_x25 TO bi_readonly;
