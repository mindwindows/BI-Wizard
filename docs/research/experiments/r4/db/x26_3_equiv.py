"""X-26.3 미리보기(bind SELECT)와 뷰(literal SELECT)의 의미 동일성.
같은 SQLAlchemy 표현식 E에 대해 (a) select(E) 를 bind로 실행, (b) CreateView(select(E)) 후 뷰를 select 로 읽는다.
비교: DB 형(pg_typeof), DB 문자 표기(cast(.. as text)), 파이썬 값. text()/exec_driver_sql 미사용.
"""
import sys, json, datetime
from decimal import Decimal
sys.stdout.reconfigure(errors="backslashreplace")
import sqlalchemy as sa
from sqlalchemy import literal, select, func, cast, Text, Numeric, Date, Integer, String, Float, true, and_, case, null
from sqlalchemy.sql.ddl import CreateView, DropView
sys.path.insert(0, "/work")
from dblib import make_engine, short

MODE = sys.argv[1] if len(sys.argv) > 1 else "plain"   # plain | typed
eng = make_engine("bi_app")
with eng.connect() as c0: pass
D = datetime.date


def typed(kind, v):
    """완화책: 값의 SQL 형을 CAST로 못박는다(뷰에서 unknown/정수/numeric으로 추론되지 않도록)."""
    if kind == "str": return cast(literal(v), Text)
    if kind == "int": return cast(literal(v), Numeric)
    if kind == "dec": return cast(literal(v), Numeric)
    if kind == "float": return cast(literal(v), Float)
    if kind == "date": return cast(literal(v), Date)
    if kind == "datetime": return cast(literal(v), sa.DateTime)
    if kind == "none": return cast(literal(None), Text)
    return literal(v)


def exprs(kind, v):
    L = (lambda: typed(kind, v)) if MODE == "typed" else (lambda: literal(v))
    if kind == "str":
        return [("contains", L().contains("l")), ("startswith", L().startswith("h")), ("like %", L().like("%l%")), ("ilike", L().ilike("H%")), ("L == L", L() == L()), ("c", L()), ("length", func.length(L())), ("upper", func.upper(L())), ("eq 'hello'", L() == "hello"),
                ("concat '!'", L() + "!"), ("lt 'b'", L() < "b"), ("coalesce", func.coalesce(L(), "x")), ("cmp col", L() == sa.table("t", sa.column("v"), schema="public").c.v)]
    if kind == "int":
        return [("mod() func", func.mod(L(), 7)), ("c/c", L() / L()), ("c//c(4)", L() // literal(4)), ("c", L()), ("c+1", L() + 1), ("c*3", L() * 3), ("c/2", L() / 2), ("c//2", L() // 2), ("c%7", L() % 7),
                ("eq 42", L() == 42), ("cast numeric", cast(L(), Numeric)), ("cast text", cast(L(), Text))]
    if kind == "dec":
        return [("c/dec5 (Numeric/Numeric)", L() / literal(Decimal("5")) if MODE == "plain" else L() / cast(literal(Decimal("5")), Numeric)),
                ("mod() func", func.mod(L(), 7)), ("power2", func.power(L(), 2)), ("c==c", L() == L()), ("c>0.5", L() > Decimal("0.5")), ("c", L()), ("c+c", L() + L()), ("c*3", L() * 3), ("c/3", L() / 3), ("round1", func.round(L(), 1)),
                ("eq 1.1", L() == Decimal("1.1")), ("cast text", cast(L(), Text)), ("c+int", L() + 1)]
    if kind == "float":
        return [("c==c", L() == L()), ("round2", func.round(cast(L(), Numeric), 2)), ("c", L()), ("c*3", L() * 3), ("c+0.2", L() + 0.2), ("c/3", L() / 3), ("eq 0.1", L() == 0.1), ("cast text", cast(L(), Text)),
                ("c+int", L() + 1)]
    if kind == "bool":
        return [("c", L()), ("not c", ~L()), ("c and true", and_(L(), true())), ("eq true", L() == True), ("case", case((L(), 1), else_=0))]
    if kind == "date":
        d2 = literal(D(2026, 1, 1))
        return [("c", L()), ("c > d2", L() > d2), ("c - d2", L() - d2), ("c + 1", L() + 1), ("year", func.extract("year", L())),
                ("cast date", cast(L(), Date)), ("to_char", func.to_char(L(), "YYYY-MM")), ("c > '2026-01-01' str", L() > "2026-01-01")]
    if kind == "datetime":
        return [("c", L()), ("year", func.extract("year", L())), ("cast date", cast(L(), Date))]
    if kind == "none":
        return [("c", L()), ("is null", L().is_(None)), ("coalesce 'x'", func.coalesce(L(), "x")), ("c+1", L() + 1), ("eq null", L() == None)]
    raise ValueError(kind)


CASES = [
    ("str", "hello"), ("str", "O'Brien"), ("str", ""), ("str", "100%"), ("str", "a\\b"), ("str", "b"),
    ("int", 42), ("int", -7), ("int", 0), ("int", 2**40), ("int", 10**30), ("int", 7),
    ("dec", Decimal("1.10")), ("dec", Decimal("0.1")), ("dec", Decimal("12")), ("dec", Decimal("1E+3")),
    ("dec", Decimal("12345678901234567890.123456789012345678")), ("dec", Decimal("0.005")), ("dec", Decimal("-0.0")),
    ("float", 0.1), ("float", 1.5), ("float", 3.0), ("float", 1e100), ("float", 1e-7), ("float", 123456789.123456789), ("float", 1 / 3),
    ("bool", True), ("bool", False),
    ("date", D(2026, 10, 11)), ("date", D(2024, 2, 29)), ("date", D(1, 1, 1)),
    ("datetime", datetime.datetime(2026, 10, 11, 20, 0, 1, 123456)),
    ("none", None),
]

res = []
n = 0
for kind, v in CASES:
    for name, E in exprs(kind, v):
        n += 1
        rec = {"mode": MODE, "kind": kind, "value": short(v, 60), "expr": name}
        vn = f"v26e{MODE[0]}_{n}"
        try:
            rec["bind_sql"] = str(select(E.label("c")).compile(dialect=eng.dialect))
        except Exception as e:
            rec["bind_sql"] = f"compile error {e}"
        try:
            with eng.connect() as conn, conn.begin():
                pv = conn.execute(select(E.label("c"))).scalar()
                pt = conn.execute(select(func.pg_typeof(E))).scalar()
                px = conn.execute(select(cast(E, Text))).scalar()
            rec["bind"] = {"val": short(pv, 60), "pytype": type(pv).__name__, "pg": pt, "txt": px}
        except Exception as e:
            rec["bind"] = {"error": f"{type(e).__name__}: {str(e)[:150]}".replace("\n", " ")}
        try:
            with eng.connect() as conn, conn.begin():
                cv = CreateView(select(E.label("c")), vn, schema="bi_data")
                rec["view_sql"] = str(cv.compile(dialect=eng.dialect))
                conn.execute(cv)
                vv = conn.execute(select(cv.table.c.c)).scalar()
                vt = conn.execute(select(func.pg_typeof(cv.table.c.c))).scalar()
                vx = conn.execute(select(cast(cv.table.c.c, Text))).scalar()
                conn.execute(DropView(cv.table))
            rec["view"] = {"val": short(vv, 60), "pytype": type(vv).__name__, "pg": vt, "txt": vx}
        except Exception as e:
            rec["view"] = {"error": f"{type(e).__name__}: {str(e)[:150]}".replace("\n", " ")}
        b, w = rec["bind"], rec["view"]
        if "error" in b or "error" in w:
            rec["verdict"] = "ERR_BOTH" if ("error" in b and "error" in w) else ("ERR_BIND_ONLY" if "error" in b else "ERR_VIEW_ONLY")
        else:
            same_type = b["pg"] == w["pg"]
            same_txt = b["txt"] == w["txt"]
            same_py = (b["val"] == w["val"] and b["pytype"] == w["pytype"])
            rec["verdict"] = "SAME" if (same_type and same_txt and same_py) else ("DIFF[" + ",".join(k for k, ok in (("pgtype", same_type), ("dbtext", same_txt), ("pyvalue", same_py)) if not ok) + "]")
        res.append(rec)
        print(json.dumps(rec, ensure_ascii=False))
