"""적재 시간 측정: 현재 C4 방식(행마다 INSERT ... ON CONFLICT DO NOTHING RETURNING) vs 배치 INSERT.

사용: python db_insert_probe.py <host> <port> <user> <db> [시험 이름 ...]   (비밀번호는 환경변수 PROBE_PGPASSWORD)
시험 이름: row5k row20k batch5k batch20k batch100k batch100k_nr wide20k wide20k_nr precheck
스택은 backend와 같다: SQLAlchemy Core + pg8000. 임시 PostgreSQL 컨테이너에서만 실행한다(운영 DB 금지).
표 모양은 동적 표 ds_<id>와 같은 구성(identity PK, 기준 날짜 열 NOT NULL + UNIQUE, numeric 열)이다.
측정 항목: 5,000행(붙여넣기 상한) / 20,000행 / 100,000행 x 12열, 열 수 12와 100(셀 수 상한 안).
"""

import os
import sys
import time
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import (
    BigInteger, Column, Date, Identity, MetaData, Numeric, Table, UniqueConstraint, create_engine, text,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import URL

host, port, user, db = sys.argv[1:5]
engine = create_engine(
    URL.create("postgresql+pg8000", username=user, password=os.environ["PROBE_PGPASSWORD"], host=host, port=int(port), database=db)
)


def make_table(name, n_numeric):
    md = MetaData()
    cols = [Column("row_id", BigInteger, Identity(always=False), primary_key=True), Column("c_1", Date, nullable=False)]
    cols += [Column(f"c_{k + 2}", Numeric) for k in range(n_numeric)]
    t = Table(name, md, *cols, UniqueConstraint("c_1", name=f"ux_{name}_period"))
    return md, t


def rows_for(n, n_numeric, start=date(1900, 1, 1)):
    # 일 단위 기간 n개(유일), 숫자 열은 소수 둘째 자리
    out = []
    for i in range(n):
        d = start + timedelta(days=i)
        out.append({"c_1": d, **{f"c_{k + 2}": Decimal(f"{(i * 7 + k) % 100000}.25") for k in range(n_numeric)}})
    return out


def timed(label, fn):
    t0 = time.perf_counter()
    r = fn()
    dt = time.perf_counter() - t0
    print(f"| {label} | {dt:.2f} s | {r} |", flush=True)
    return dt


def per_row(n, n_numeric):
    md, t = make_table(f"probe_row_{n}_{n_numeric}", n_numeric)
    with engine.begin() as conn:
        md.drop_all(conn)  # 임시 컨테이너의 시험 표만 대상(같은 이름이 남아 있으면 지우고 다시 만든다)
        md.create_all(conn)
    data = rows_for(n, n_numeric)

    def run():
        with engine.connect() as conn:
            ids = 0
            for r in data:
                stmt = pg_insert(t).values(**r).on_conflict_do_nothing().returning(t.c.row_id)
                if conn.execute(stmt).scalar() is not None:
                    ids += 1
            conn.commit()
        return f"{ids} 행"

    return timed(f"행마다 INSERT ... RETURNING, {n:,}행 x {n_numeric + 1}열", run)


def batched(n, n_numeric, size=1000, ordered_returning=True):
    md, t = make_table(f"probe_batch_{n}_{n_numeric}", n_numeric)
    with engine.begin() as conn:
        md.drop_all(conn)  # 임시 컨테이너의 시험 표만 대상(같은 이름이 남아 있으면 지우고 다시 만든다)
        md.create_all(conn)
    data = rows_for(n, n_numeric)

    def run():
        with engine.connect() as conn:
            total = 0
            for i in range(0, n, size):
                chunk = data[i : i + size]
                stmt = pg_insert(t).on_conflict_do_nothing()
                if ordered_returning:
                    res = conn.execute(stmt.returning(t.c.row_id, t.c.c_1), chunk)
                    total += len(res.all())
                else:
                    conn.execute(stmt, chunk)
                    total += len(chunk)
            conn.commit()
        return f"{total} 행"

    return timed(f"배치 {size}행씩 executemany{' + RETURNING' if ordered_returning else ''}, {n:,}행 x {n_numeric + 1}열", run)


def period_precheck(n_numeric):
    """기존 행 n=50,000개가 있는 표에서 새 기간 5,000개의 충돌을 한 번의 SELECT ... ANY로 미리 찾는 비용."""
    md, t = make_table("probe_precheck", n_numeric)
    with engine.begin() as conn:
        md.drop_all(conn)  # 임시 컨테이너의 시험 표만 대상(같은 이름이 남아 있으면 지우고 다시 만든다)
        md.create_all(conn)
        conn.execute(pg_insert(t), rows_for(50000, n_numeric))
    periods = [date(1900, 1, 1) + timedelta(days=i) for i in range(49000, 54000)]

    def run():
        with engine.connect() as conn:
            rows = conn.execute(t.select().with_only_columns(t.c.row_id, t.c.c_1).where(t.c.c_1.in_(periods))).all()
        return f"충돌 {len(rows)}건"

    return timed("기간 5,000개 충돌 미리 조회(IN)", run)


TESTS = {
    "row5k": lambda: per_row(5000, 11),
    "row20k": lambda: per_row(20000, 11),
    "batch5k": lambda: batched(5000, 11),
    "batch20k": lambda: batched(20000, 11),
    "batch100k": lambda: batched(100000, 11),
    "batch100k_nr": lambda: batched(100000, 11, ordered_returning=False),
    "wide20k": lambda: batched(20000, 99),
    "wide20k_nr": lambda: batched(20000, 99, ordered_returning=False),
    "precheck": lambda: period_precheck(11),
}

if __name__ == "__main__":
    with engine.connect() as c:
        print("PostgreSQL:", c.execute(text("select version()")).scalar())
    print("| 항목 | 시간 | 결과 |\n| --- | --- | --- |")
    for name in (sys.argv[5:] or TESTS):  # 이름을 주면 그것만 실행
        TESTS[name]()
