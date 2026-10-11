"""X-29 동적 객체 생성/탐침. 모드: create | probe | cleanup"""
import sys, json
sys.stdout.reconfigure(errors="backslashreplace")
import sqlalchemy as sa
from sqlalchemy import Column, Integer, Text, MetaData, Table, Identity, select, func
from sqlalchemy.sql.ddl import CreateTable, DropTable, CreateView, DropView
sys.path.insert(0, "/work")
from dblib import make_engine
mode = sys.argv[1]
app, owner, ro = make_engine("bi_app", db="x29"), make_engine("bi_owner", db="x29"), make_engine("bi_readonly", db="x29")
def mk(name):
    return Table(name, MetaData(), Column("id", Integer, Identity(), primary_key=True), Column("v", Text), schema="bi_data")
if mode == "create":
    ds1, ds2 = mk("ds_1"), mk("ds_2")
    with app.begin() as c:
        c.execute(CreateTable(ds1)); c.execute(sa.insert(ds1), [{"v": "a"}, {"v": "b"}])
        c.execute(CreateView(select(ds1.c.id, ds1.c.v), "dv_1", schema="bi_data"))
    with owner.begin() as c:
        c.execute(CreateTable(ds2)); c.execute(sa.insert(ds2), [{"v": "o"}])
    print("created: ds_1(bi_app), dv_1(bi_app), ds_2(bi_owner)")
elif mode == "probe":
    out = {}
    for name in ("ds_1", "dv_1", "ds_2"):
        t = sa.table(name, sa.column("v") if name != "dv_1" else sa.column("v"), schema="bi_data")
        try:
            with ro.connect() as c:
                out[f"bi_readonly SELECT {name}"] = c.execute(select(func.count()).select_from(t)).scalar()
        except Exception as e:
            out[f"bi_readonly SELECT {name}"] = "거부/오류: " + str(e)[:60].replace("\n", " ")
    with app.connect() as c:
        out["bi_app has_schema_privilege(bi_data, CREATE)"] = c.execute(select(func.has_schema_privilege("bi_app", "bi_data", "CREATE"))).scalar()
        out["bi_app has_schema_privilege(bi_data, USAGE)"] = c.execute(select(func.has_schema_privilege("bi_app", "bi_data", "USAGE"))).scalar()
        out["bi_readonly has_schema_privilege(bi_data, USAGE)"] = c.execute(select(func.has_schema_privilege("bi_readonly", "bi_data", "USAGE"))).scalar()
        out["public.teams 존재(to_regclass)"] = c.execute(select(func.to_regclass("public.teams"))).scalar() is not None
        if out["public.teams 존재(to_regclass)"]:
            out["bi_app has_table_privilege(public.teams, INSERT)"] = c.execute(select(func.has_table_privilege("bi_app", "public.teams", "INSERT"))).scalar()
    print(json.dumps(out, ensure_ascii=False, indent=1))
elif mode == "cleanup":
    with app.begin() as c:
        c.execute(DropView(Table("dv_1", MetaData(), schema="bi_data"), if_exists=True)); c.execute(DropTable(mk("ds_1"), if_exists=True))
    with owner.begin() as c:
        c.execute(DropTable(mk("ds_2"), if_exists=True))
    print("cleaned")
