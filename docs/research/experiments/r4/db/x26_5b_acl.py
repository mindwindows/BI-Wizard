"""X-26.5b 런타임 DDL 후 bi_readonly가 실제로 읽는가(기본 권한 FOR ROLE bi_app): 재생성/or_replace/이름 변경 뒤."""
import sys, json
import sqlalchemy as sa
from sqlalchemy import Column, Integer, Text, MetaData, Table, Identity, select, func
from sqlalchemy.sql.ddl import CreateTable, DropTable, CreateView, DropView
from alembic.migration import MigrationContext
from alembic.operations import Operations
sys.path.insert(0, "/work")
from dblib import make_engine
app, ro = make_engine("bi_app"), make_engine("bi_readonly")
md = MetaData(); ds = Table("ds_200", md, Column("id", Integer, Identity(), primary_key=True), Column("v", Text), schema="bi_data")
def ro_read(label, name):
    try:
        with ro.connect() as c:
            n = c.execute(select(func.count()).select_from(sa.table(name, sa.column("v"), schema="bi_data"))).scalar()
        print(label, "-> bi_readonly 읽기 OK, 행 수", n)
    except Exception as e:
        print(label, "-> bi_readonly 읽기 실패", type(e).__name__, str(e)[:100])
with app.begin() as c:
    c.execute(CreateTable(ds)); c.execute(sa.insert(ds), [{"v": "x"}, {"v": "y"}])
    c.execute(CreateView(select(ds.c.id, ds.c.v), "dv_200", schema="bi_data"))
ro_read("1 최초 생성", "ds_200"); ro_read("1 최초 생성(뷰)", "dv_200")
with app.begin() as c:
    c.execute(DropView(Table("dv_200", MetaData(), schema="bi_data"))); c.execute(CreateView(select(ds.c.id, ds.c.v), "dv_200", schema="bi_data"))
ro_read("2 DropView+CreateView 후(뷰)", "dv_200")
with app.begin() as c:
    c.execute(CreateView(select(ds.c.id, ds.c.v, (ds.c.id * 2).label("d")), "dv_200", schema="bi_data", or_replace=True))
ro_read("3 or_replace 후(뷰)", "dv_200")
with app.begin() as c:
    op = Operations(MigrationContext.configure(c)); op.rename_table("ds_200", "ds_201", schema="bi_data")
ro_read("4 표 이름 변경 후(표)", "ds_201")
with app.begin() as c:
    op = Operations(MigrationContext.configure(c)); op.add_column("ds_201", Column("w", Integer), schema="bi_data")
ro_read("5 열 추가 후(표)", "ds_201")
with app.begin() as c:
    c.execute(DropView(Table("dv_200", MetaData(), schema="bi_data"))); c.execute(DropTable(Table("ds_201", MetaData(), schema="bi_data")))
print("정리 완료")
