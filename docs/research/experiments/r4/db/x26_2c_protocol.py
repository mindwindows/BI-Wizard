"""X-26.2c pg8000 프로토콜 확인: 파라미터 없으면 simple(여러 문장 가능, % 그대로), 있으면 extended(% 해석, 여러 문장 불가).
하네스 전용으로 exec_driver_sql을 사용한다(저장소 코드 아님). 서버 로그와 함께 본다."""
import sys, json
sys.stdout.reconfigure(errors="backslashreplace")
import sqlalchemy as sa
from sqlalchemy import literal, select
from sqlalchemy.sql.ddl import CreateView, DropView
sys.path.insert(0, "/work")
from dblib import make_engine

eng = make_engine("bi_app")
def run(label, fn):
    try:
        with eng.connect() as c, c.begin():
            r = fn(c)
        print(f"[{label}] OK -> {r!r}")
    except Exception as e:
        print(f"[{label}] ERROR {type(e).__name__}: {str(e)[:230]}".replace("\n", " "))

run("1 무파라미터 두 문장", lambda c: c.exec_driver_sql("SELECT 1 AS a; SELECT 2 AS b").fetchall())
run("2 파라미터 + 두 문장", lambda c: c.exec_driver_sql("SELECT %s::int AS a; SELECT 2 AS b", (1,)).fetchall())
run("3 무파라미터 '100%%'", lambda c: c.exec_driver_sql("SELECT '100%%' AS a").scalar())
run("4 무파라미터 'a%sb'", lambda c: c.exec_driver_sql("SELECT 'a%sb' AS a").scalar())
run("5 파라미터 + '100%%'", lambda c: c.exec_driver_sql("SELECT '100%%' AS a, %s::int AS b", (7,)).fetchall())
run("6 파라미터 + 'a%sb'(리터럴 %s)", lambda c: c.exec_driver_sql("SELECT 'a%sb' AS a, %s::int AS b", (7,)).fetchall())
run("7 SQLAlchemy 미리보기(bind) '100%' / 'a %s b'", lambda c: c.execute(select(literal("100%").label("x"), literal("a %s b").label("y"))).fetchall())
run("8 CreateView(literal) '100%' / 'a %s b' / '%(x)s' (파라미터 없음 -> simple)", lambda c: (c.execute(CreateView(select(literal("100%").label("x"), literal("a %s b").label("y"), literal("%(x)s").label("z")), "v_proto", schema="bi_data")), c.execute(sa.select(sa.table("v_proto", sa.column("x"), sa.column("y"), sa.column("z"), schema="bi_data"))).fetchall())[1])
run("9 DropView", lambda c: c.execute(DropView(sa.Table("v_proto", sa.MetaData(), schema="bi_data"), if_exists=True)) and None)
