\set ON_ERROR_STOP on
\c x29 bi_owner
CREATE TABLE public.legacy_unmodeled (id int);
CREATE VIEW public.v_static AS SELECT id, name FROM public.teams;
CREATE FUNCTION public.f_static() RETURNS int LANGUAGE sql AS 'SELECT 1';
\c x29 bi_app
CREATE FUNCTION bi_data.f_dyn() RETURNS int LANGUAGE sql AS 'SELECT 2';
SELECT current_user;
