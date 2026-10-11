"""X-26.1 렌더링 행렬: CreateView(내장) + literal -> 실행 -> select로 되읽기 -> 입력과 비교.
접속: bi_app, 스키마 bi_data. text()/exec_driver_sql 사용 안 함.
"""
import sys, json, datetime
sys.stdout.reconfigure(errors="backslashreplace")
from decimal import Decimal
import sqlalchemy as sa
from sqlalchemy import literal, select, func, cast
from sqlalchemy.sql.ddl import CreateView, DropView
from sqlalchemy.dialects.postgresql import REGCLASS
sys.path.insert(0, "/work")
from dblib import make_engine, same, short

eng = make_engine("bi_app")
with eng.connect() as c0:
    pass  # 방언 초기화(standard_conforming_strings 판정)
print("dialect._backslash_escapes =", eng.dialect._backslash_escapes, "| _double_percents =", eng.dialect.identifier_preparer._double_percents)

L200 = "가" * 200
CASES = [
    ("S01", "평범한 글자", "hello world"),
    ("S02", "한글", "완료"),
    ("S03", "이모지", "👍🏽 ok 😀"),
    ("S04", "작은따옴표 '", "O'Brien"),
    ("S05", "큰따옴표 \"", 'say "hi"'),
    ("S06", "역슬래시 \\", "a\\b"),
    ("S07", "\\' (역슬래시+작은따옴표)", "a\\'b"),
    ("S08", "'' (두 작은따옴표)", "a''b"),
    ("S09", "% 하나", "100%"),
    ("S10", "%%", "a%%b"),
    ("S11", "%s", "a %s b"),
    ("S12", "%(x)s", "a %(x)s b"),
    ("S13", "세미콜론 ;", "a;b"),
    ("S14", "-- 주석", "a -- b"),
    ("S15", "/* */", "a /* b */ c"),
    ("S16", "개행·탭·CR", "line1\nline2\tTab\r\nCRLF"),
    ("S17", "NUL \\x00", "a\x00b"),
    ("S18", "$$", "a $$ b"),
    ("S19", "E'", "E'abc"),
    ("S20", "200자 한글", L200),
    ("S21", "10,000자", "x" * 10000),
    ("S22", "앞뒤 공백", "  padded  "),
    ("S23", "빈 문자열", ""),
    ("S24", "서로게이트 단독 \\ud800", "a\ud800b"),
    ("S25", "서로게이트 surrogateescape \\udcff", b"\xff".decode("utf-8", "surrogateescape")),
    ("S26", "비문자 \\uffff", "a￿b"),
    ("S27", "최대 코드포인트 U+10FFFF", "a\U0010ffffb"),
    ("S28", ": 와 :name", "a :name b ::int"),
    ("S29", "? 와 $1", "a ? b $1"),
    ("S30", "결합문자 NFD 한글", "한"),
    ("S31", "E'\\\\' 모양", "E'\\\\'"),
    ("S32", "따옴표 끝 + 주석", "x'--"),
    ("N01", "정수 42", 42),
    ("N02", "큰 정수 10**30", 10**30),
    ("N03", "음수 -7", -7),
    ("N04", "정수 0", 0),
    ("N05", "소수 Decimal('1.10')", Decimal("1.10")),
    ("N06", "Decimal('-0.0')", Decimal("-0.0")),
    ("N07", "지수 Decimal('1E+3')", Decimal("1E+3")),
    ("N08", "지수 Decimal('1.5E-7')", Decimal("1.5E-7")),
    ("N09", "Decimal('NaN')", Decimal("NaN")),
    ("N10", "Decimal('Infinity')", Decimal("Infinity")),
    ("N11", "Decimal('-Infinity')", Decimal("-Infinity")),
    ("N12", "float 0.1", 0.1),
    ("N13", "float 1e100", 1e100),
    ("N14", "float('nan')", float("nan")),
    ("N15", "float('inf')", float("inf")),
    ("N16", "float('-inf')", float("-inf")),
    ("N17", "float -0.0", -0.0),
    ("N18", "Decimal 38자리", Decimal("12345678901234567890.123456789012345678")),
    ("N19", "Decimal('sNaN')", Decimal("sNaN")),
    ("N20", "Decimal('  12  ')(공백)", Decimal("12")),
    ("B01", "bool True", True),
    ("B02", "bool False", False),
    ("D01", "date 2026-10-11", datetime.date(2026, 10, 11)),
    ("D02", "date 0001-01-01", datetime.date(1, 1, 1)),
    ("D03", "datetime", datetime.datetime(2026, 10, 11, 20, 0, 1, 123456)),
    ("X01", "None", None),
]

out = []
vn = 0
for cid, label, val in CASES:
    vn += 1
    vname = f"v26_{vn}"
    rec = {"id": cid, "label": label, "input": short(val), "py_type": type(val).__name__}
    try:
        sel = select(literal(val).label("c"))
        cv = CreateView(sel, vname, schema="bi_data")
        sql = str(cv.compile(dialect=eng.dialect))
        rec["rendered"] = sql if len(sql) < 300 else sql[:150] + f"...<len {len(sql)}>..." + sql[-60:]
    except Exception as e:
        rec["render_error"] = f"{type(e).__name__}: {str(e)[:200]}"
        out.append(rec); continue
    try:
        with eng.connect() as conn:
            with conn.begin():
                conn.execute(cv)
                rec["exec"] = "OK"
                got = conn.execute(select(cv.table.c.c)).scalar_one_or_none()
                rec["readback"] = short(got)
                rec["readback_type"] = type(got).__name__
                rec["match"] = same(val, got)
                if rec["match"] is False and val is not None:
                    # 형이 달라서 불일치인지 값이 달라서인지 구분
                    try:
                        rec["match_value_only"] = bool(val == got) or (str(val) == str(got))
                    except Exception:
                        pass
                rec["pg_typeof"] = conn.execute(select(func.pg_typeof(cv.table.c.c))).scalar()
                vd = conn.execute(select(func.pg_get_viewdef(cast(literal(f"bi_data.{vname}"), REGCLASS), True))).scalar()
                rec["viewdef"] = vd if len(vd) < 300 else vd[:120] + f"...<len {len(vd)}>..." + vd[-40:]
                conn.execute(DropView(cv.table))
    except Exception as e:
        rec["exec"] = f"ERROR {type(e).__name__}: {str(e)[:300]}"
        rec["match"] = None
    out.append(rec)

for r in out:
    print(json.dumps(r, ensure_ascii=False))
