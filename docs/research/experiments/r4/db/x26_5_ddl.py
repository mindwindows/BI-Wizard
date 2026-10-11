"""X-26.5 런타임 내장 DDL 부품(bi_app, 한 트랜잭션): CreateTable/DropTable/CreateIndex/CreateView/DropView + Alembic Operations.
이 파일은 text()와 exec_driver_sql을 쓰지 않는다(마지막에 자기 소스를 검사해 출력).
"""
import sys, json, re
sys.stdout.reconfigure(errors="backslashreplace")
import sqlalchemy as sa
from sqlalchemy import Column, Integer, Text, Numeric, MetaData, Table, Identity, select, func, cast, literal, event
from sqlalchemy.sql.ddl import CreateTable, DropTable, CreateIndex, DropIndex, CreateView, DropView
from alembic.migration import MigrationContext
from alembic.operations import Operations
sys.path.insert(0, "/work")
from dblib import make_engine, short

eng = make_engine("bi_app")
stmts = []
@event.listens_for(eng, "before_cursor_execute")
def _rec(conn, cursor, statement, parameters, context, executemany):
    stmts.append(re.sub(r"\s+", " ", statement).strip() + (f"   -- params={parameters}" if parameters else ""))

SCH = "bi_data"
PGC = sa.table("pg_class", sa.column("relname"), sa.column("relkind"), sa.column("relowner"), sa.column("relnamespace"), schema="pg_catalog")
PGN = sa.table("pg_namespace", sa.column("oid"), sa.column("nspname"), schema="pg_catalog")


def objects(conn):
    q = (select(PGC.c.relname, PGC.c.relkind, func.pg_get_userbyid(PGC.c.relowner))
         .join(PGN, PGN.c.oid == PGC.c.relnamespace).where(PGN.c.nspname == SCH).order_by(PGC.c.relname))
    return [tuple(r) for r in conn.execute(q)]


def viewdef(conn, name):
    return conn.execute(select(func.pg_get_viewdef(cast(literal(f"{SCH}.{name}"), sa.dialects.postgresql.REGCLASS), True))).scalar()


def cols(conn, table):
    return [(c["name"], str(c["type"])) for c in sa.inspect(conn).get_columns(table, schema=SCH)]


def step(label, fn, show_sql=True):
    del stmts[:]
    rec = {"step": label}
    try:
        with eng.begin() as conn:
            ctx = MigrationContext.configure(conn)
            op = Operations(ctx)
            rec["result"] = fn(conn, op)
        rec["status"] = "OK(커밋)"
    except Exception as e:
        rec["status"] = f"ERROR {type(e).__name__}: {str(e)[:260]}".replace("\n", " ")
    if show_sql:
        rec["sql"] = [s for s in stmts if not s.startswith(("select pg_catalog.version", "select current_schema", "show ", "SELECT pg_catalog.pg_class", "SELECT pg_catalog.pg_attribute", "SELECT pg_catalog.pg_get_userbyid", "SELECT pg_class", "SELECT pg_attribute"))
                      and "pg_catalog.pg_attribute" not in s and "pg_catalog.pg_class" not in s][:14]
    print(json.dumps(rec, ensure_ascii=False, default=str))
    return rec


md = MetaData()
ds = Table("ds_100", md, Column("id", Integer, Identity(), primary_key=True), Column("c_1", Text), Column("c_2", Text), Column("c_3", Numeric), schema=SCH)
ix = sa.Index("ix_ds_100_c_1", ds.c.c_1)


def view_sel(extra=False, with_c2=True):
    cols_ = [ds.c.id, ds.c.c_1.label("name")]
    if with_c2:
        cols_.append(cast(ds.c.c_2, Numeric).label("amount"))
    if extra:
        cols_.append((ds.c.c_3 * 2).label("double"))
    return select(*cols_)

# 사전 정리(이전 실행 잔재)
step("S0 정리", lambda c, op: (c.execute(DropView(Table("dv_100", MetaData(), schema=SCH), if_exists=True)),
                          c.execute(DropTable(Table("ds_100", MetaData(), schema=SCH), if_exists=True)), None)[-1], show_sql=False)

step("S1 CreateTable + CreateIndex + CreateView + 데이터 입력(한 트랜잭션)", lambda c, op: (
    c.execute(CreateTable(ds)), c.execute(CreateIndex(ix)),
    c.execute(sa.insert(ds), [{"c_1": "a", "c_2": "10.5", "c_3": 1}, {"c_1": "b", "c_2": "20", "c_3": 2}]),
    c.execute(CreateView(view_sel(), "dv_100", schema=SCH)),
    {"objects": objects(c), "readonly_can_select_view": c.execute(select(func.has_table_privilege("bi_readonly", f"{SCH}.dv_100", "SELECT"))).scalar(),
     "readonly_can_select_table(기본권한 FOR ROLE bi_app)": c.execute(select(func.has_table_privilege("bi_readonly", f"{SCH}.ds_100", "SELECT"))).scalar()})[-1])

step("S2a CreateView(or_replace=True) 끝에 열 추가", lambda c, op: (
    c.execute(CreateView(view_sel(extra=True), "dv_100", schema=SCH, or_replace=True)), cols(c, "dv_100"))[-1])
step("S2b or_replace로 열 하나 빼기(=열 순서/개수 변경)", lambda c, op: c.execute(CreateView(view_sel(with_c2=False), "dv_100", schema=SCH, or_replace=True)))
step("S2c or_replace로 열 이름 바꾸기", lambda c, op: c.execute(CreateView(select(ds.c.id, ds.c.c_1.label("name2"), cast(ds.c.c_2, Numeric).label("amount"), (ds.c.c_3 * 2).label("double")), "dv_100", schema=SCH, or_replace=True)))
step("S2d or_replace로 열 타입 바꾸기(amount numeric -> text)", lambda c, op: c.execute(CreateView(select(ds.c.id, ds.c.c_1.label("name"), cast(ds.c.c_2, Text).label("amount"), (ds.c.c_3 * 2).label("double")), "dv_100", schema=SCH, or_replace=True)))

step("S3 op.add_column(c_4 integer)", lambda c, op: (op.add_column("ds_100", Column("c_4", Integer), schema=SCH), cols(c, "ds_100"))[-1])

step("S4a 의존 뷰가 있는 열 op.drop_column(c_2) (뷰 그대로)", lambda c, op: op.drop_column("ds_100", "c_2", schema=SCH))
step("S4b 한 트랜잭션: DropView -> op.drop_column(c_2) -> CreateView(c_2 없는 정의)", lambda c, op: (
    c.execute(DropView(Table("dv_100", MetaData(), schema=SCH))), op.drop_column("ds_100", "c_2", schema=SCH),
    c.execute(CreateView(select(ds.c.id, ds.c.c_1.label("name"), (ds.c.c_3 * 2).label("double")), "dv_100", schema=SCH)),
    {"cols": cols(c, "ds_100"), "viewdef": viewdef(c, "dv_100")})[-1])

step("S5-준비 op.add_column(c_2 text) + 데이터", lambda c, op: (op.add_column("ds_100", Column("c_2", Text), schema=SCH),
                                                       c.execute(sa.update(ds).values(c_2=sa.case((ds.c.c_1 == "a", "10.5"), else_=literal("20")))),
                                                       c.execute(DropView(Table("dv_100", MetaData(), schema=SCH))),
                                                       c.execute(CreateView(select(ds.c.id, ds.c.c_1.label("name"), cast(ds.c.c_2, Numeric).label("amount")), "dv_100", schema=SCH)), None)[-1])
step("S5a 의존 뷰 있는 열 타입 변경 op.alter_column(type_=Numeric(12,2), postgresql_using=문자열) (뷰 그대로)", lambda c, op:
     op.alter_column("ds_100", "c_2", type_=Numeric(12, 2), postgresql_using="c_2::numeric(12,2)", schema=SCH))
step("S5b 타입 변경 USING 없이(text->numeric)", lambda c, op: (c.execute(DropView(Table("dv_100", MetaData(), schema=SCH))), op.alter_column("ds_100", "c_2", type_=Numeric(12, 2), schema=SCH)))
step("S5c 한 트랜잭션: DropView -> alter_column(USING 문자열) -> CreateView", lambda c, op: (
    c.execute(DropView(Table("dv_100", MetaData(), schema=SCH))),
    op.alter_column("ds_100", "c_2", type_=Numeric(12, 2), postgresql_using="c_2::numeric(12,2)", schema=SCH),
    c.execute(CreateView(select(ds.c.id, ds.c.c_1.label("name"), ds.c.c_2.label("amount")), "dv_100", schema=SCH)),
    {"cols": cols(c, "ds_100"), "data": [tuple(r) for r in c.execute(select(ds.c.c_1, ds.c.c_2))]})[-1])
step("S5d USING에 SQLAlchemy 표현식 객체(cast(column, Text)) 전달", lambda c, op: (
    c.execute(DropView(Table("dv_100", MetaData(), schema=SCH))),
    op.alter_column("ds_100", "c_2", type_=Text, postgresql_using=cast(sa.column("c_2"), Text), schema=SCH),
    {"cols": cols(c, "ds_100")})[-1])
step("S5e 문자열 없이 타입 변경: 새 열 추가 -> update(cast) -> DropView -> drop_column -> 이름 변경 -> CreateView (한 트랜잭션)", lambda c, op: (
    op.add_column("ds_100", Column("c_2t", Text), schema=SCH),
    c.execute(sa.update(ds).values(c_2t=cast(sa.column("c_2"), Text))) if False else c.execute(
        sa.update(sa.table("ds_100", sa.column("c_2"), sa.column("c_2t"), schema=SCH)).values(c_2t=cast(sa.column("c_2"), Text))),
    c.execute(DropView(Table("dv_100", MetaData(), schema=SCH))),
    op.drop_column("ds_100", "c_2", schema=SCH),
    op.alter_column("ds_100", "c_2t", new_column_name="c_2", schema=SCH),
    c.execute(CreateView(select(ds.c.id, ds.c.c_1.label("name"), ds.c.c_2.label("amount")), "dv_100", schema=SCH)),
    {"cols": cols(c, "ds_100"), "data": [tuple(r) for r in c.execute(select(ds.c.c_1, ds.c.c_2))]})[-1])

step("S6 열 이름 변경 op.alter_column(new_column_name) (의존 뷰 있는 상태로)", lambda c, op: (
    op.alter_column("ds_100", "c_1", new_column_name="c_1b", schema=SCH),
    {"cols": cols(c, "ds_100"), "viewdef": viewdef(c, "dv_100")})[-1])
step("S7 표 이름 변경 op.rename_table (의존 뷰 있는 상태로)", lambda c, op: (
    op.rename_table("ds_100", "ds_101", schema=SCH), {"viewdef": viewdef(c, "dv_100"), "objects": objects(c)})[-1])
step("S8 op.create_index / op.drop_index", lambda c, op: (
    op.create_index("ix_ds_101_c_3", "ds_101", ["c_3"], schema=SCH), op.drop_index("ix_ds_101_c_3", table_name="ds_101", schema=SCH),
    [i["name"] for i in sa.inspect(c).get_indexes("ds_101", schema=SCH)])[-1])
step("S9a 의존 뷰 있는 표 op.drop_table (뷰 그대로)", lambda c, op: op.drop_table("ds_101", schema=SCH))

# 원자성: 앞 단계 성공 후 마지막 단계 실패 -> 전부 롤백
before = {}
def snapshot(c, op):
    before["cols"] = cols(c, "ds_101"); before["view"] = viewdef(c, "dv_100")
step("S10-전 스냅샷", snapshot, show_sql=False)
step("S10 한 트랜잭션: DropView -> op.add_column -> alter_column -> CreateView(없는 열 참조 -> 오류)", lambda c, op: (
    c.execute(DropView(Table("dv_100", MetaData(), schema=SCH))), op.add_column("ds_101", Column("c_9", Integer), schema=SCH),
    c.execute(CreateView(select(literal(1).label("x")).select_from(sa.table("ds_101", sa.column("nope"), schema=SCH)).add_columns(sa.column("nope")), "dv_100", schema=SCH))))
def check_after(c, op):
    return {"cols_unchanged": cols(c, "ds_101") == before["cols"], "view_unchanged": viewdef(c, "dv_100") == before["view"], "c_9_exists": any(n == "c_9" for n, _ in cols(c, "ds_101"))}
step("S10-후 롤백 확인", check_after, show_sql=False)

step("S11 정리: DropView + op.drop_table + 객체 목록", lambda c, op: (
    c.execute(DropView(Table("dv_100", MetaData(), schema=SCH))), op.drop_table("ds_101", schema=SCH), objects(c))[-1])

import ast
tree = ast.parse(open(__file__).read())
calls = [(n.func.id if isinstance(n.func, ast.Name) else n.func.attr) for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, (ast.Name, ast.Attribute))]
print("자기 소스 AST 검사: text() 호출 =", calls.count("text"), "| exec_driver_sql() 호출 =", calls.count("exec_driver_sql"), "| op.execute() 호출 =", calls.count("execute") and sum(1 for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "execute" and isinstance(n.func.value, ast.Name) and n.func.value.id == "op"))
