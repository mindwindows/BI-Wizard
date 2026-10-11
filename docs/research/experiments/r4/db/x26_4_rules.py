"""X-26.4 검증 규칙 후보 적용 전/후: 어떤 입력이 라운드트립을 깨는가, 각 규칙이 무엇을 거르는가."""
import sys, json, unicodedata, time
sys.stdout.reconfigure(errors="backslashreplace")
import sqlalchemy as sa
from sqlalchemy import literal, select, func
from sqlalchemy.sql.ddl import CreateView, DropView
sys.path.insert(0, "/work")
from dblib import make_engine, short

eng = make_engine("bi_app")
with eng.connect() as c0: pass

def roundtrip(val, n):
    vname = f"v26r_{n}"
    try:
        with eng.connect() as conn, conn.begin():
            cv = CreateView(select(literal(val).label("c")), vname, schema="bi_data")
            conn.execute(cv)
            got = conn.execute(select(cv.table.c.c)).scalar()
            conn.execute(DropView(cv.table))
        return "일치" if got == val else f"불일치(읽은 값 {short(got, 40)})"
    except Exception as e:
        return f"오류 {type(e).__name__}: {str(e)[:90]}".replace("\n", " ")

def is_cc(s): return any(unicodedata.category(ch) == "Cc" for ch in s)
def is_surr(s): return any(unicodedata.category(ch) == "Cs" for ch in s)
RULES = {
    "R0 규칙 없음": lambda s: True,
    "R1 NUL만 거부": lambda s: "\x00" not in s,
    "R2 제어문자(Cc: NUL, \\n, \\t, \\r, ESC 등) 거부": lambda s: not is_cc(s),
    "R3 R2 + 서로게이트(Cs) 거부": lambda s: not is_cc(s) and not is_surr(s),
    "R4 R3 + 역슬래시 거부": lambda s: not is_cc(s) and not is_surr(s) and "\\" not in s,
    "R5 R4 + 200자 초과 거부": lambda s: not is_cc(s) and not is_surr(s) and "\\" not in s and len(s) <= 200,
}
CASES = [
    ("평범", "hello"), ("한글", "완료"), ("O'Brien", "O'Brien"), ("역슬래시 a\\b", "a\\b"), ("개행", "a\nb"), ("탭", "a\tb"), ("CRLF", "a\r\nb"),
    ("NUL", "a\x00b"), ("서로게이트 \\ud800", "a\ud800b"), ("ESC \\x1b", "a\x1bb"), ("DEL \\x7f", "a\x7fb"), ("BS \\x08", "a\x08b"),
    ("VT \\x0b", "a\x0bb"), ("FF \\x0c", "a\x0cb"), ("C1 \\x85(NEL)", "a\x85b"), ("LS U+2028", "a b"), ("PS U+2029", "a b"),
    ("ZWSP U+200B", "a​b"), ("BOM U+FEFF", "a﻿b"), ("RLO U+202E", "a‮b"), ("NBSP U+00A0", "a b"),
    ("200자", "가" * 200), ("201자", "가" * 201), ("10,000자", "x" * 10000), ("1,000,000자", "x" * 1_000_000),
    ("이모지", "👍"), ("NFD 한글", "한"), ("NFC 한글", "한"),
]
rows = []
for i, (label, val) in enumerate(CASES):
    t0 = time.time()
    rt = roundtrip(val, i)
    dt = time.time() - t0
    verdicts = {name: ("통과" if fn(val) else "거부") for name, fn in RULES.items()}
    rows.append({"case": label, "len": len(val), "roundtrip_without_rule": rt, "sec": round(dt, 2), **verdicts})
    print(json.dumps(rows[-1], ensure_ascii=False))

# NFC/NFD 비교 의미: 표에 저장된 NFC 값과 NFD 리터럴 비교
nfd = "한"; nfc = unicodedata.normalize("NFC", nfd)
with eng.connect() as conn, conn.begin():
    r = conn.execute(select((literal(nfd) == literal(nfc)).label("eq"), (literal(unicodedata.normalize("NFC", nfd)) == literal(nfc)).label("eq_after_nfc"),
                            func.length(literal(nfd)).label("len_nfd"), func.length(literal(nfc)).label("len_nfc"))).one()
print("NFD vs NFC 비교(DB):", dict(r._mapping), "| python 정규화 일치:", unicodedata.normalize("NFC", nfd) == nfc)
