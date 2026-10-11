"""X-26.2 주입 시도. 인자: <mode> [scs]
mode=safe      : SQLAlchemy CreateView + literal (우리 방식)
mode=control   : 일부러 f-string 조립 + exec_driver_sql (대조군, 저장소에 넣지 않음)
mode=naive     : 작은따옴표 두 배만 하는 불완전 이스케이프 + exec_driver_sql (대조군)
mode=mismatch  : 방언 초기화는 현재 설정으로 하고, 이후 서버 설정이 바뀐 상황(스크립트가 중간에 ALTER DATABASE는 못 하므로 쉘이 두 단계로 호출)
"""
import sys, json
sys.stdout.reconfigure(errors="backslashreplace")
import sqlalchemy as sa
from sqlalchemy import literal, select, func
from sqlalchemy.sql.ddl import CreateView, DropView, DropTable
sys.path.insert(0, "/work")
from dblib import make_engine, short

mode = sys.argv[1]
extra = sys.argv[2:] 

PAYLOADS = [
    ("P1", "x'); DROP TABLE public.t; --"),
    ("P2", "x'; CREATE TABLE bi_data.evil(a int); --"),
    ("P3", "x' AS c; DELETE FROM public.t; --"),
    ("P4", "x\\'; DELETE FROM public.t; --"),
    ("P5", "\\'; CREATE TABLE bi_data.evil(a int); --"),
    ("P6", "x\\''; CREATE TABLE bi_data.evil(a int); --"),
    ("P7", "$$; DELETE FROM public.t; --"),
    ("P8", "x' || (SELECT string_agg(v, ',') FROM public.t) || '"),
    ("P9", "x' UNION SELECT 'leak' --"),
    ("P10", "x\\\\'; CREATE TABLE bi_data.evil(a int); --"),
]
T = sa.table("t", sa.column("id"), sa.column("v"), schema="public")
EVIL = sa.Table("evil", sa.MetaData(), schema="bi_data")


def state(conn):
    ev = sa.inspect(conn).has_table("evil", schema="bi_data")
    n = conn.execute(select(func.count()).select_from(T)).scalar()
    return ev, n


def reset(eng):
    with eng.connect() as c:
        with c.begin():
            c.execute(DropTable(EVIL, if_exists=True))
            c.execute(DropView(sa.Table("v_inj", sa.MetaData(), schema="bi_data"), if_exists=True))
            c.execute(sa.delete(T))
            c.execute(sa.insert(T), [{"id": 1, "v": "a"}, {"id": 2, "v": "b"}])


eng_kw = {}
if "startup_on" in extra:
    eng_kw["connect_args"] = {"startup_params": {"standard_conforming_strings": "on"}}
eng = make_engine("bi_app", **eng_kw)
with eng.connect() as c:
    scs = c.execute(sa.select(sa.func.current_setting("standard_conforming_strings"))).scalar()
    print(f"mode={mode} extra={extra} | session standard_conforming_strings={scs} | dialect._backslash_escapes={eng.dialect._backslash_escapes}")
if "init_only" in extra:
    sys.exit(0)
reset(eng)

for pid, p in PAYLOADS:
    rec = {"payload": pid, "value": p}
    try:
        with eng.connect() as conn:
            with conn.begin():
                if mode == "safe":
                    cv = CreateView(select(literal(p).label("c")), "v_inj", schema="bi_data")
                    rec["rendered"] = str(cv.compile(dialect=eng.dialect))
                    conn.execute(cv)
                    got = conn.execute(select(cv.table.c.c)).scalar()
                    rec["roundtrip_equal"] = (got == p)
                    rec["readback"] = short(got)
                elif mode in ("control", "naive"):
                    q = p.replace("'", "''") if mode == "naive" else p
                    sql = f"CREATE VIEW bi_data.v_inj AS SELECT '{q}' AS c"
                    rec["rendered"] = sql
                    conn.exec_driver_sql(sql)
                rec["exec"] = "OK"
                if mode == "safe":
                    rec["state_in_tx"] = state(conn)
    except Exception as e:
        rec["exec"] = f"ERROR {type(e).__name__}: {str(e)[:220]}".replace("\n", " ")
    if mode in ("control", "naive") and rec.get("exec") == "OK":
        try:
            with eng.connect() as conn:
                rec["readback"] = short(conn.exec_driver_sql("SELECT c FROM bi_data.v_inj").scalar())
        except Exception as e:
            rec["readback"] = f"(c 열 읽기 실패: {type(e).__name__})"
    with eng.connect() as conn:
        rec["state_after"] = {"evil_table_exists": state(conn)[0], "public.t_rows": state(conn)[1]}
    print(json.dumps(rec, ensure_ascii=False))
    reset(eng)
