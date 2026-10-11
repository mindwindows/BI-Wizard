"""X-29 스냅샷: 표·열·인덱스·제약·ACL·소유자·기본 권한·멤버십·alembic_version. SQLAlchemy 구성요소만(text 없음).
사용: x29_snapshot.py [--no-dynamic]  (bi_data의 ds_*/dv_* 동적 객체는 --no-dynamic이면 목록에서 뺀다)
"""
import sys, json, re
sys.stdout.reconfigure(errors="backslashreplace")
import sqlalchemy as sa
from sqlalchemy import select, func, cast, Text
sys.path.insert(0, "/work")
from dblib import make_engine

nodyn = "--no-dynamic" in sys.argv
eng = make_engine("bi_owner", db="x29")
T = lambda name, *cols, schema="pg_catalog": sa.table(name, *[sa.column(c) for c in cols], schema=schema)
PGC = T("pg_class", "oid", "relname", "relkind", "relowner", "relnamespace", "relacl", "reloptions")
PGN = T("pg_namespace", "oid", "nspname", "nspowner", "nspacl")
PGR = T("pg_roles", "oid", "rolname", "rolsuper", "rolinherit", "rolcreaterole", "rolcreatedb", "rolcanlogin", "rolreplication", "rolbypassrls", "rolconfig")
PGM = T("pg_auth_members", "roleid", "member", "grantor", "admin_option", "inherit_option", "set_option")
PGD = T("pg_default_acl", "defaclrole", "defaclnamespace", "defaclobjtype", "defaclacl")
snap = {}
with eng.connect() as c:
    rn = lambda col: func.pg_get_userbyid(col)
    snap["roles"] = sorted([list(map(str, r)) for r in c.execute(select(PGR.c.rolname, PGR.c.rolsuper, PGR.c.rolinherit, PGR.c.rolcreaterole, PGR.c.rolcreatedb, PGR.c.rolcanlogin, PGR.c.rolbypassrls, cast(PGR.c.rolconfig, Text)).where(PGR.c.rolname.in_(["bi_owner", "bi_app", "bi_readonly"])))])
    snap["memberships"] = sorted([list(map(str, r)) for r in c.execute(select(rn(PGM.c.roleid), rn(PGM.c.member), rn(PGM.c.grantor), PGM.c.admin_option, PGM.c.inherit_option, PGM.c.set_option).where(rn(PGM.c.member).in_(["bi_owner", "bi_app", "bi_readonly"])))])
    snap["schemas"] = sorted([list(map(str, r)) for r in c.execute(select(PGN.c.nspname, rn(PGN.c.nspowner), cast(PGN.c.nspacl, Text)).where(PGN.c.nspname.in_(["public", "bi_data"])))])
    rel = (select(PGN.c.nspname, PGC.c.relname, PGC.c.relkind, rn(PGC.c.relowner), cast(PGC.c.relacl, Text))
           .join(PGN, PGN.c.oid == PGC.c.relnamespace).where(PGN.c.nspname.in_(["public", "bi_data"])).order_by(PGN.c.nspname, PGC.c.relname))
    rels = [list(map(str, r)) for r in c.execute(rel)]
    dyn = [r for r in rels if r[0] == "bi_data"]
    if nodyn:
        rels = [r for r in rels if r[0] != "bi_data"]
    snap["relations(schema,name,kind,owner,acl)"] = rels
    snap["dynamic_bi_data(schema,name,kind,owner,acl)"] = dyn
    q = (select(rn(PGD.c.defaclrole), func.coalesce(PGN.c.nspname, "(global)"), PGD.c.defaclobjtype, cast(PGD.c.defaclacl, Text))
         .select_from(PGD.outerjoin(PGN, PGN.c.oid == PGD.c.defaclnamespace)))
    snap["default_acl(role,schema,objtype,acl)"] = sorted([list(map(str, r)) for r in c.execute(q)])
    insp = sa.inspect(c)
    tables = {}
    for t in sorted(insp.get_table_names(schema="public")):
        tables[t] = {
            "columns": [(col["name"], str(col["type"]), col["nullable"], str(col.get("default")), bool(col.get("identity"))) for col in insp.get_columns(t, schema="public")],
            "pk": insp.get_pk_constraint(t, schema="public")["constrained_columns"],
            "fks": [(fk["constrained_columns"], fk["referred_table"], fk["referred_columns"]) for fk in insp.get_foreign_keys(t, schema="public")],
            "indexes": sorted([(i["name"], i["column_names"], i["unique"]) for i in insp.get_indexes(t, schema="public")]),
        }
    snap["public_tables"] = tables
    snap["alembic_version"] = None
    if "alembic_version" in insp.get_table_names(schema="public"):
        av = sa.table("alembic_version", sa.column("version_num"), schema="public")
        snap["alembic_version"] = [r[0] for r in c.execute(select(av.c.version_num))]
print(json.dumps(snap, ensure_ascii=False, indent=1, sort_keys=True))
