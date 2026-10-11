"""X-26.2b: 방언은 연결 시 한 번(engine 첫 connect) standard_conforming_strings를 판정한다.
서버 설정이 그 뒤에 바뀌면(ALTER DATABASE ... SET, 이후 새 연결) 렌더가 새 연결과 어긋나는가?
(하네스 전용: 설정 변경은 postgres 계정으로 하며 앱 코드가 아니다.)
"""
import sys, json
sys.stdout.reconfigure(errors="backslashreplace")
import sqlalchemy as sa
from sqlalchemy import literal, select, func
from sqlalchemy.sql.ddl import CreateView, DropView, DropTable
sys.path.insert(0, "/work")
from dblib import make_engine, short

T = sa.table("t", sa.column("id"), sa.column("v"), schema="public")
EVIL = sa.Table("evil", sa.MetaData(), schema="bi_data")
admin = make_engine("postgres", db="x26", isolation_level="AUTOCOMMIT")


def admin_set(val):
    with admin.connect() as c:
        if val is None:
            c.exec_driver_sql("ALTER DATABASE x26 RESET standard_conforming_strings")
        else:
            c.exec_driver_sql(f"ALTER DATABASE x26 SET standard_conforming_strings = {val}")


def state(eng):
    with eng.connect() as c:
        return {"evil_table_exists": sa.inspect(c).has_table("evil", schema="bi_data"),
                "public.t_rows": c.execute(select(func.count()).select_from(T)).scalar()}


def cleanup(eng):
    with eng.connect() as c, c.begin():
        c.execute(DropTable(EVIL, if_exists=True))
        c.execute(DropView(sa.Table("v_inj", sa.MetaData(), schema="bi_data"), if_exists=True))
        c.execute(sa.delete(T)); c.execute(sa.insert(T), [{"id": 1, "v": "a"}, {"id": 2, "v": "b"}])


PAY = [("P4", "x\\'; DELETE FROM public.t; --"), ("P5", "\\'; CREATE TABLE bi_data.evil(a int); --")]


def attempt(eng, label):
    for pid, p in PAY:
        rec = {"scenario": label, "payload": pid, "dialect_backslash_escapes": eng.dialect._backslash_escapes}
        try:
            with eng.connect() as conn, conn.begin():
                scs = conn.execute(select(func.current_setting("standard_conforming_strings"))).scalar()
                rec["session_scs"] = scs
                cv = CreateView(select(literal(p).label("c")), "v_inj", schema="bi_data")
                rec["rendered"] = str(cv.compile(dialect=eng.dialect))
                conn.execute(cv)
                rec["exec"] = "OK"
        except Exception as e:
            rec["exec"] = f"ERROR {type(e).__name__}: {str(e)[:160]}".replace("\n", " ")
        rec["state_after"] = state(eng)
        print(json.dumps(rec, ensure_ascii=False))
        cleanup(eng)

# 시나리오 A: 엔진 초기화는 scs=on, 이후 서버 설정이 off로 바뀌고 새 연결
admin_set(None)
eng = make_engine("bi_app")
with eng.connect() as c: pass
cleanup(eng)
print("A. 초기화 시 on ->", eng.dialect._backslash_escapes)
admin_set("off")
attempt(eng, "A: init=on, 이후 서버=off, 같은 엔진의 새 연결")

# 시나리오 B: 엔진 초기화는 off, 이후 on으로 바뀜 (백슬래시 두 배가 과함 -> 값이 달라지는지)
admin_set("off")
eng2 = make_engine("bi_app")
with eng2.connect() as c: pass
print("B. 초기화 시 off ->", eng2.dialect._backslash_escapes)
admin_set(None)
rec = {"scenario": "B: init=off, 이후 서버=on"}
with eng2.connect() as conn:
    cv = CreateView(select(literal("a\\b").label("c")), "v_inj", schema="bi_data")
    rec["rendered"] = str(cv.compile(dialect=eng2.dialect))
    with conn.begin():
        conn.execute(cv)
        got = conn.execute(select(cv.table.c.c)).scalar()
    rec["readback"] = got; rec["roundtrip_equal"] = (got == "a\\b")
print(json.dumps(rec, ensure_ascii=False))
cleanup(eng2)

# 시나리오 C: 완화책 후보 - 연결 시작 매개변수로 on 고정 (서버 DB 설정이 off여도)
admin_set("off")
eng3 = make_engine("bi_app", connect_args={"startup_params": {"standard_conforming_strings": "on"}})
with eng3.connect() as c: pass
print("C. startup_params=on, 서버 DB 설정=off -> 방언 판정:", eng3.dialect._backslash_escapes)
attempt(eng3, "C: startup_params=on, 서버=off")
admin_set(None)

# 시나리오 A2: A와 같은 어긋남(방언 on, 서버 off) + 앱이 "같은 트랜잭션 안 라운드트립 확인, 불일치면 롤백"을 적용
print("--- A2: 라운드트립 확인 + 불일치 시 롤백(JL1 ③)")
admin_set(None)
eng4 = make_engine("bi_app")
with eng4.connect() as c: pass
cleanup(eng4)
admin_set("off")
PAY2 = PAY + [("P3", "x' AS c; DELETE FROM public.t; --"), ("P2", "x'; CREATE TABLE bi_data.evil(a int); --"),
              ("P8", "x' || (SELECT string_agg(v, ',') FROM public.t) || '")]
for pid, p in PAY2:
    rec = {"scenario": "A2", "payload": pid}
    try:
        with eng4.connect() as conn:
            with conn.begin():
                cv = CreateView(select(literal(p).label("c")), "v_inj", schema="bi_data")
                conn.execute(cv)
                got = conn.execute(select(cv.table.c.c)).scalar()
                if got != p:
                    raise ValueError("roundtrip mismatch -> rollback")
                rec["roundtrip"] = "일치(커밋됨)"
    except Exception as e:
        rec["roundtrip"] = f"불일치/오류 -> 롤백: {type(e).__name__}: {str(e)[:100]}".replace("\n", " ")
    rec["state_after"] = state(eng4)
    print(json.dumps(rec, ensure_ascii=False))
    cleanup(eng4)
admin_set(None)
