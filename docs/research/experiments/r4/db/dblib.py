"""X-26/X-29 공용 도우미 (실험 전용). backend 이미지(SQLAlchemy 2.1.4 + pg8000)에서 실행."""
import math
from decimal import Decimal
import sqlalchemy as sa
from sqlalchemy.engine import URL

HOST = "127.0.0.1"
PW = {"bi_app": "dummy_app", "bi_owner": "dummy_owner", "bi_readonly": "dummy_ro", "postgres": "dummy"}


def make_engine(user="bi_app", db="x26", **kw):
    url = URL.create("postgresql+pg8000", username=user, password=PW[user], host=HOST, port=5432, database=db)
    return sa.create_engine(url, poolclass=sa.pool.NullPool, **kw)


def same(a, b):
    """라운드트립 비교: NaN은 NaN끼리 같다고 본다. 형도 같아야 한다."""
    if type(a) is not type(b):
        return False
    if isinstance(a, float) and math.isnan(a):
        return math.isnan(b)
    if isinstance(a, Decimal) and a.is_nan():
        return b.is_nan()
    return a == b


def short(v, n=120):
    r = repr(v)
    return r if len(r) <= n else r[:60] + f"...<len {len(r)}>..." + r[-30:]
