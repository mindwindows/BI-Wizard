"""X-26.2d 보충: (1) NUL을 낀 주입 시도 (2) 따옴표 없이 렌더되는 NaN/Infinity가 FROM 절의 열 이름으로 해석되는지."""
import sys, json
sys.stdout.reconfigure(errors="backslashreplace")
from decimal import Decimal
import sqlalchemy as sa
from sqlalchemy import Column, Integer, MetaData, Table, literal, select, func
from sqlalchemy.sql.ddl import CreateTable, DropTable, CreateView, DropView
sys.path.insert(0, "/work")
from dblib import make_engine
eng = make_engine("bi_app")
T = sa.table("t", sa.column("id"), sa.column("v"), schema="public")
EVIL = Table("evil", MetaData(), schema="bi_data")
def st(conn): return {"evil": sa.inspect(conn).has_table("evil", schema="bi_data"), "t_rows": conn.execute(select(func.count()).select_from(T)).scalar()}
for p in ["x\x00'; CREATE TABLE bi_data.evil(a int); --", "x'; CREATE TABLE bi_data.evil(a int); --\x00", "\x00"]:
    try:
        with eng.begin() as c:
            c.execute(CreateView(select(literal(p).label("c")), "v_nul", schema="bi_data"))
        r = "OK"
    except Exception as e:
        r = f"ERROR {type(e).__name__}: {str(e)[:120]}".replace("\n", " ")
    with eng.connect() as c: print("NUL 주입", repr(p)[:60], "->", r, st(c))
# NaN이 열 참조로 해석되는가
nt = Table("ds_nan", MetaData(), Column("id", Integer, primary_key=True), Column("nan", Integer), Column("infinity", Integer), schema="bi_data")
with eng.begin() as c:
    c.execute(DropTable(nt, if_exists=True)); c.execute(CreateTable(nt)); c.execute(sa.insert(nt), [{"id": 1, "nan": 111, "infinity": 222}])
for v in (Decimal("NaN"), Decimal("Infinity"), float("nan")):
    try:
        with eng.begin() as c:
            cv = CreateView(select(literal(v).label("c")).select_from(nt), "v_nan", schema="bi_data")
            sql = str(cv.compile(dialect=eng.dialect))
            c.execute(cv)
            got = c.execute(select(cv.table.c.c)).scalar()
            c.execute(DropView(cv.table))
        print("값", repr(v), "| 렌더:", sql[-60:], "| 읽은 값:", got, "(열 nan/infinity의 값이 나오면 열 참조로 해석된 것)")
    except Exception as e:
        print("값", repr(v), "-> ERROR", str(e)[:100].replace("\n", " "))
with eng.begin() as c:
    c.execute(DropTable(nt, if_exists=True))
