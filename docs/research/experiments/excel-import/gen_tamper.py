"""변조·위장·폭탄 xlsx 생성기 (설계 실측용, 모두 합성). 사용: python gen_tamper.py <출력폴더> [이름 ...]

기본 파일(작은 정상 xlsx)의 zip 항목 일부를 바꾸거나 더해 만든다. 폭탄의 해제 크기는 100~200 MB이고 압축 후는 1 MB 안팎이다.
출력 폴더에 생성된 파일은 디스크를 쓰므로(합계 약 6 MB) 실험 후에도 남긴다(삭제 명령은 쓰지 않는다).
"""

import os
import struct
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_samples  # noqa: E402

OUT = sys.argv[1]
WANT = set(sys.argv[2:])
os.makedirs(OUT, exist_ok=True)
BASE = os.path.join(OUT, "_base.xlsx")
HEAD = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
NS = b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
MB = 1024 * 1024


def base():
    if not os.path.exists(BASE):
        gen_samples.build_month_cols(BASE, 60, 12)
    return BASE


def put(zout, name, data, level=9):
    zi = zipfile.ZipInfo(name, (2026, 10, 14, 0, 0, 0))
    zi.compress_type = zipfile.ZIP_DEFLATED
    zi._compresslevel = level
    if isinstance(data, (bytes, bytearray)):
        zout.writestr(zi, data)
    else:
        with zout.open(zi, "w", force_zip64=True) as fh:
            for chunk in data:
                fh.write(chunk)


def repeat(block: bytes, total: int):
    big = block * max(1, MB // len(block))
    full, rem = divmod((total // len(block)) * len(block), len(big))
    for _ in range(full):
        yield big
    if rem:
        yield big[:rem]


def concat(*parts):
    for p in parts:
        if isinstance(p, bytes):
            yield p
        else:
            yield from p


def rewrite(out, replace=None, add=None, drop=()):
    replace, add = replace or {}, add or {}
    with zipfile.ZipFile(base()) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            if info.filename in drop:
                continue
            put(zout, info.filename, replace.get(info.filename, zin.read(info.filename)))
        for n, d in add.items():
            put(zout, n, d)


def sheet_xml(body):
    return concat(HEAD, NS, b"<sheetData>", body, b"</sheetData></worksheet>")


SHEET = "xl/worksheets/sheet1.xml"
SST = "xl/sharedStrings.xml"
CASES = {}


def case(fn):
    CASES[fn.__name__] = fn
    return fn


# --- 크기·압축 폭탄 ---
@case
def bomb_rows_200mb(p):  # 해제 200MB, 행 반복(dimension 없음)
    rewrite(p, replace={SHEET: sheet_xml(repeat(b'<row><c t="n"><v>1</v></c></row>', 200 * MB))})


@case
def bomb_whitespace_150mb(p):
    rewrite(p, replace={SHEET: sheet_xml(repeat(b" ", 150 * MB))})


@case
def bomb_celltext_100mb(p):  # 셀 하나의 글자 100MB(inlineStr)
    rewrite(p, replace={SHEET: sheet_xml(concat(b'<row r="1"><c r="A1" t="inlineStr"><is><t>', repeat(b"A", 100 * MB), b"</t></is></c></row>"))})


@case
def bomb_sst_many_100mb(p):  # 짧은 공유 문자열 수천만 개
    rewrite(p, replace={SST: concat(HEAD, b'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">', repeat(b"<si><t>x</t></si>", 100 * MB), b"</sst>")})


@case
def bomb_sst_one_100mb(p):
    rewrite(p, replace={SST: concat(HEAD, b'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>', repeat(b"A", 100 * MB), b"</t></si></sst>")})


@case
def gentle_inside_limit(p):  # 한도(5MB x 15 = 75MB, 비율 50) 안쪽의 큰 시트: 70MB, 무작위 숫자라 비율 낮음
    import random

    rng = random.Random(1)
    block = b"".join(b'<row><c><v>%d</v></c></row>' % rng.randrange(60) for _ in range(40000))
    rewrite(p, replace={SHEET: sheet_xml(repeat(block, 70 * MB))})


@case
def declared_size_lie(p):  # 중앙 디렉터리의 file_size를 1000으로 속임(실제 100MB)
    rewrite(p, replace={SHEET: sheet_xml(repeat(b'<row><c t="n"><v>1</v></c></row>', 100 * MB))})
    raw = bytearray(open(p, "rb").read())
    pos = raw.rfind(b"PK\x01\x02")
    while pos != -1:
        nlen = struct.unpack_from("<H", raw, pos + 28)[0]
        name = bytes(raw[pos + 46 : pos + 46 + nlen])
        if name == SHEET.encode():
            struct.pack_into("<I", raw, pos + 24, 1000)  # 압축 전 크기 필드
        pos = raw.rfind(b"PK\x01\x02", 0, pos)
    open(p, "wb").write(raw)


@case
def nested_zip(p):  # 항목 안에 또 다른 zip(100MB 폭탄 포함)
    import io

    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w", zipfile.ZIP_DEFLATED) as z:
        put(z, "big.txt", repeat(b"A", 100 * MB))
    rewrite(p, add={"xl/embeddings/inner.zip": inner.getvalue()})


@case
def many_entries_20000(p):
    rewrite(p, add={f"xl/media/f{i}.xml": b"<a/>" for i in range(20000)})


@case
def sheets_declared_5000(p):
    wb = HEAD + b'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
    wb += b"".join(b'<sheet name="S%d" sheetId="%d" r:id="rId1"/>' % (i, i) for i in range(1, 5001)) + b"</sheets></workbook>"
    rewrite(p, replace={"xl/workbook.xml": wb})


# --- XML 공격 ---
LAUGH = (
    b'<!DOCTYPE lolz [<!ENTITY lol0 "lol">'
    + b"".join(b'<!ENTITY lol%d "%s">' % (k, b"&lol%d;" % (k - 1) * 10) for k in range(1, 10))
    + b"]>"
)


@case
def xxe_external_entity_sheet(p):
    s = HEAD + b'<!DOCTYPE s [<!ENTITY xxe SYSTEM "file:///etc/hostname">]>' + NS + b'<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>&xxe;</t></is></c></row></sheetData></worksheet>'
    rewrite(p, replace={SHEET: s})


@case
def billion_laughs_sheet(p):
    s = HEAD + LAUGH + NS + b'<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>&lol9;</t></is></c></row></sheetData></worksheet>'
    rewrite(p, replace={SHEET: s})


@case
def dtd_in_sst(p):
    s = HEAD + b'<!DOCTYPE s [<!ENTITY a "aaaa">]><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>&a;</t></si></sst>'
    rewrite(p, replace={SST: s})


@case
def dtd_in_content_types(p):
    with zipfile.ZipFile(base()) as z:
        ct = z.read("[Content_Types].xml")
    s = ct.replace(b"?>", b'?><!DOCTYPE t [<!ENTITY a "aaaa">]>', 1)
    rewrite(p, replace={"[Content_Types].xml": s})


# --- 형식 위장 ---
@case
def ole2_encrypted_like(p):
    open(p, "wb").write(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 4000)


@case
def png_renamed(p):
    open(p, "wb").write(b"\x89PNG\r\n\x1a\n" + os.urandom(3000))


@case
def text_renamed(p):
    open(p, "wb").write("가,나\n1,2\n".encode())


@case
def empty_file(p):
    open(p, "wb").write(b"")


@case
def truncated_zip(p):
    data = open(base(), "rb").read()
    open(p, "wb").write(data[: len(data) // 2])


@case
def zip_not_xlsx(p):
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("hello.txt", "x")


@case
def xlsm_macro(p):
    with zipfile.ZipFile(base()) as z:
        ct = z.read("[Content_Types].xml")
    ct = ct.replace(b"spreadsheetml.sheet.main+xml", b"ms-excel.sheet.macroEnabled.main+xml")
    rewrite(p, replace={"[Content_Types].xml": ct}, add={"xl/vbaProject.bin": os.urandom(500)})


@case
def xlsb_like(p):
    rewrite(p, add={"xl/workbook.bin": os.urandom(200)})


@case
def external_link_dde(p):
    x = HEAD + b'<externalLink xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><ddeLink ddeService="cmd" ddeTopic="/C calc"><ddeItems><ddeItem name="A0"/></ddeItems></ddeLink></externalLink>'
    rewrite(p, add={"xl/externalLinks/externalLink1.xml": x})


@case
def embedded_ole_object(p):
    rewrite(p, add={"xl/embeddings/oleObject1.bin": os.urandom(300)})


@case
def path_traversal_names(p):
    rewrite(p, add={"../evil.txt": b"x"})


@case
def backslash_names(p):
    rewrite(p, add={"xl\\evil.txt": b"x"})


@case
def encrypted_flag_entry(p):  # zipfile.writestr은 flag_bits를 지우므로 중앙 디렉터리 바이트를 직접 고친다
    rewrite(p)
    raw = bytearray(open(p, "rb").read())
    pos = raw.rfind(b"PK\x01\x02")
    while pos != -1:
        nlen = struct.unpack_from("<H", raw, pos + 28)[0]
        if bytes(raw[pos + 46 : pos + 46 + nlen]) == b"xl/styles.xml":
            raw[pos + 8] |= 0x01  # 일반 목적 비트 플래그의 암호화 비트
        pos = raw.rfind(b"PK\x01\x02", 0, pos)
    open(p, "wb").write(raw)


@case
def bzip2_entry(p):
    with zipfile.ZipFile(base()) as zin, zipfile.ZipFile(p, "w") as zout:
        for info in zin.infolist():
            zi = zipfile.ZipInfo(info.filename, (2026, 10, 14, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_BZIP2 if info.filename == "xl/styles.xml" else zipfile.ZIP_DEFLATED
            zout.writestr(zi, zin.read(info.filename))


@case
def duplicate_names(p):
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        rewrite(p, add={"xl/styles.xml": b"<a/>"})


if __name__ == "__main__":
    for name, fn in CASES.items():
        if WANT and name not in WANT:
            continue
        path = os.path.join(OUT, f"{name}.xlsx")
        fn(path)
        print(f"{name}: {os.path.getsize(path):,} bytes")
