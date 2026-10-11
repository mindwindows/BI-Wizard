"""X-26.6 (나) 글자를 별도 표(public.formula_literals)에 저장하고 뷰는 id 서브쿼리로 참조.
- 뷰 정의에 글자가 없고 숫자 id만 있는지, 글자 수정이 뷰 재생성 없이 반영되는지, 락 영향, EXPLAIN ANALYZE 비교.
하네스 전용으로 EXPLAIN/SET LOCAL에 exec_driver_sql을 쓴다(런타임 코드 아님).
"""
import sys, json, time, threading, statistics, re
sys.stdout.reconfigure(errors="backslashreplace")
import sqlalchemy as sa
from sqlalchemy import Column, Integer, Text, MetaData, Table, Identity, select, func, cast, case, literal
from sqlalchemy.sql.ddl import CreateTable, DropTable, CreateView, DropView
sys.path.insert(0, "/work")
from dblib import make_engine

owner, app, ro = make_engine("bi_owner"), make_engine("bi_app"), make_engine("bi_readonly")
SCH = "bi_data"
lit = Table("formula_literals", MetaData(), Column("id", Integer, Identity(), primary_key=True), Column("value", Text), schema="public")

# 준비: 정적 표는 bi_owner가 만들고 bi_app에 DML만 부여(실제 설계와 같음)
with owner.begin() as c:
    c.execute(DropTable(lit, if_exists=True))
    c.execute(CreateTable(lit))
    c.exec_driver_sql("GRANT SELECT, INSERT, UPDATE, DELETE ON public.formula_literals TO bi_app")
print("준비 완료: public.formula_literals (소유자 bi_owner, bi_app에 DML)")

def make_dataset(n_rows, name):
    md = MetaData()
    ds = Table(name, md, Column("id", Integer, Identity(), primary_key=True), Column("status", Text), Column("amount", sa.Numeric), schema=SCH)
    with app.begin() as c:
        c.execute(DropView(Table("dv_" + name, MetaData(), schema=SCH), if_exists=True)); c.execute(DropTable(Table(name, MetaData(), schema=SCH), if_exists=True))
        c.execute(CreateTable(ds))
        statuses = ["완료", "진행", "보류", "O'Brien", "취소"]
        c.execute(sa.insert(ds), [{"status": statuses[i % 5], "amount": i % 100} for i in range(n_rows)])
    return ds

def run_plan(sql_sel, label, n=5):
    """EXPLAIN ANALYZE 를 n번 돌려 Planning/Execution Time 중앙값."""
    pl, ex, text0 = [], [], None
    with app.connect() as c:
        for _ in range(n):
            rows = [r[0] for r in c.exec_driver_sql("EXPLAIN (ANALYZE, BUFFERS OFF, TIMING ON) " + sql_sel)]
            txt = "\n".join(rows)
            pl.append(float(re.search(r"Planning Time: ([\d.]+) ms", txt).group(1))); ex.append(float(re.search(r"Execution Time: ([\d.]+) ms", txt).group(1)))
            text0 = text0 or txt
        c.rollback()
    return {"label": label, "planning_ms_median": round(statistics.median(pl), 3), "exec_ms_median": round(statistics.median(ex), 3), "plan": text0}

results = {}
with app.begin() as c:
    c.execute(sa.delete(lit))
    c.execute(sa.insert(lit), [{"value": "완료"}])            # id 1 (시퀀스는 identity 이므로 delete 후에도 계속 증가 -> id 조회)
    lit_id = c.execute(select(func.max(lit.c.id))).scalar()
print("첫 글자 id =", lit_id)

# 1) 뷰 정의 확인과 수정 반영
ds = make_dataset(100, "ds_300")
lit_sq = select(lit.c.value).where(lit.c.id == lit_id).scalar_subquery()
sel_b = select(ds.c.id, ds.c.status, case((ds.c.status == lit_sq, 1), else_=0).label("flag"))
with app.begin() as c:
    c.execute(CreateView(sel_b, "dv_ds_300", schema=SCH))
    vd = c.execute(select(func.pg_get_viewdef(cast(literal(f"{SCH}.dv_ds_300"), sa.dialects.postgresql.REGCLASS), True))).scalar()
    oid_before = c.execute(select(func.cast(literal(f"{SCH}.dv_ds_300"), sa.dialects.postgresql.REGCLASS).cast(sa.dialects.postgresql.OID))).scalar() if False else None
print("뷰 정의(글자 없음, id만):\n", vd)
V = sa.table("dv_ds_300", sa.column("id"), sa.column("flag"), schema=SCH)
def flagged(engine):
    with engine.connect() as c:
        return c.execute(select(func.sum(V.c.flag))).scalar()
print("수정 전 flag 합(완료=20):", flagged(app), "| bi_readonly로도 읽힘:", flagged(ro))
# bi_readonly는 public.formula_literals를 직접 못 읽는다
try:
    with ro.connect() as c:
        c.execute(select(lit.c.value)).all()
    print("bi_readonly -> formula_literals 직접 SELECT: 허용됨(!)")
except Exception as e:
    print("bi_readonly -> formula_literals 직접 SELECT: 거부", str(e)[:80].replace("\n", " "))
DDL_before = None
with app.begin() as c:
    c.execute(sa.update(lit).where(lit.c.id == lit_id).values(value="O'Brien"))
print("UPDATE formula_literals 로 글자만 수정('완료' -> \"O'Brien\") -> flag 합(O'Brien=20):", flagged(app), "(뷰 DDL 없음)")
with app.begin() as c:
    c.execute(sa.update(lit).where(lit.c.id == lit_id).values(value="완료"))
with app.begin() as c:
    c.execute(sa.delete(lit).where(lit.c.id == lit_id))
print("글자 행 삭제 후 flag 합(서브쿼리 NULL -> 비교 거짓 -> 조용히 0):", flagged(app))
with app.begin() as c:
    c.execute(sa.insert(lit).values(id=lit_id, value="완료")) if False else None
    new_id = c.execute(sa.insert(lit).values(value="완료").returning(lit.c.id)).scalar()
print("재삽입 id =", new_id, "(identity라 id 달라짐; 뷰는 옛 id를 가리킴)")
lit_id = new_id
lit_sq = select(lit.c.value).where(lit.c.id == lit_id).scalar_subquery()

# 2) 락: 긴 읽기 중 UPDATE vs CREATE OR REPLACE VIEW
def long_reader(started, done):
    with app.connect() as c, c.begin():
        c.execute(select(func.count()).select_from(V)).scalar()
        started.set(); time.sleep(4.0)
    done.set()
started, done = threading.Event(), threading.Event()
th = threading.Thread(target=long_reader, args=(started, done)); th.start(); started.wait()
t0 = time.time()
with app.begin() as c:
    c.exec_driver_sql("SET LOCAL lock_timeout = '1500ms'")
    c.execute(sa.update(lit).where(lit.c.id == lit_id).values(value="완료"))
t_update = time.time() - t0
t0 = time.time(); err = None
try:
    with app.begin() as c:
        c.exec_driver_sql("SET LOCAL lock_timeout = '1500ms'")
        c.execute(CreateView(sel_b, "dv_ds_300", schema=SCH, or_replace=True))
except Exception as e:
    err = str(e)[:90].replace("\n", " ")
t_replace = time.time() - t0
th.join()
print(f"긴 읽기(4초) 중: 글자 UPDATE {t_update:.2f}s(즉시) | CREATE OR REPLACE VIEW {t_replace:.2f}s 결과={err or '성공'}")

# 3) 성능: 데이터 행 수 × 글자 방식
perf = []
for n_rows in (100, 10_000, 200_000):
    ds = make_dataset(n_rows, "ds_301")
    # 글자 표 크기: 50행, 5000행 (id 조회는 PK)
    for lit_rows in (50, 5000):
        with app.begin() as c:
            c.execute(sa.delete(lit))
            c.execute(sa.insert(lit), [{"value": f"v{i}"} for i in range(lit_rows - 1)] + [{"value": "완료"}])
            tid = c.execute(select(lit.c.id).where(lit.c.value == "완료")).scalar()
        sq = select(lit.c.value).where(lit.c.id == tid).scalar_subquery()
        for kind, cond_expr in (("뷰 안 글자(리터럴)", ds.c.status == literal("완료")), ("서브쿼리(id)", ds.c.status == sq)):
            sel = select(func.count(), func.sum(case((cond_expr, 1), else_=0))).select_from(ds)
            if kind.startswith("뷰 안"):
                sql = str(sel.compile(dialect=app.dialect, compile_kwargs={"literal_binds": True}))
            else:
                sql = str(sel.compile(dialect=app.dialect, compile_kwargs={"literal_binds": True}))
            r = run_plan(sql, f"행 {n_rows} / 글자표 {lit_rows}행 / {kind}")
            perf.append({k: v for k, v in r.items() if k != "plan"})
            if n_rows == 10_000 and lit_rows == 5000:
                print("---- 계획(", r["label"], ")\n", r["plan"])
        # 20개 글자를 CASE로 비교하는 뷰 (여러 글자 상수)
        k20 = [f"v{i}" for i in range(19)] + ["완료"]
        conds_lit = sum_lit = None
        sel_l = select(func.sum(case(*[(ds.c.status == literal(v), i) for i, v in enumerate(k20)], else_=-1))).select_from(ds)
        ids = [None] * 20
        with app.connect() as c:
            idmap = {r[1]: r[0] for r in c.execute(select(lit.c.id, lit.c.value).where(lit.c.value.in_(k20)))}
            c.rollback()
        sel_s = select(func.sum(case(*[(ds.c.status == select(lit.c.value).where(lit.c.id == idmap[v]).scalar_subquery(), i) for i, v in enumerate(k20)], else_=-1))).select_from(ds)
        for kind, sel in (("20개 비교 리터럴", sel_l), ("20개 비교 서브쿼리", sel_s)):
            sql = str(sel.compile(dialect=app.dialect, compile_kwargs={"literal_binds": True}))
            r = run_plan(sql, f"행 {n_rows} / 글자표 {lit_rows}행 / {kind}")
            perf.append({k: v for k, v in r.items() if k != "plan"})
for p in perf:
    print(json.dumps(p, ensure_ascii=False))

# 정리
with app.begin() as c:
    for n in ("dv_ds_300",): c.execute(DropView(Table(n, MetaData(), schema=SCH), if_exists=True))
    for n in ("ds_300", "ds_301"): c.execute(DropTable(Table(n, MetaData(), schema=SCH), if_exists=True))
with owner.begin() as c:
    c.execute(DropTable(lit, if_exists=True))
print("정리 완료")
