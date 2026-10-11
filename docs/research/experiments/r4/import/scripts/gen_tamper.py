"""X-27 변조 파일 생성기. 사용: python gen_tamper.py <out_dir> [name ...]  (이름 생략 시 전부)
모든 파일은 합성이며 out_dir(Git 제외 폴더)에만 둔다."""
import sys, os, io, zipfile, struct, random, json, shutil, time

sys.path.insert(0, "/home/user/BI-Wizard/_workspace/gate3/experiments/r4/import/scripts")
sys.path.insert(0, "/tmp/claude-0/site-crypto")
import gen_big as g  # noqa: E402

OUT = sys.argv[1]
WANT = set(sys.argv[2:])
os.makedirs(OUT, exist_ok=True)
SHEET_HEAD = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
BASE = os.path.join(OUT, "_base.xlsx")


def base():
    if not os.path.exists(BASE):
        g.build("tall", 200, BASE)
    return BASE


def rewrite(out, replace=None, add=None, drop=(), level=9, edit=None):
    """base xlsx를 복사하며 일부 항목을 바꾼다. replace: {name: bytes|iterable[bytes]}, add: 새 항목, edit: {name: fn(bytes)->bytes}"""
    replace, add, edit = replace or {}, add or {}, edit or {}
    with zipfile.ZipFile(base()) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=level) as zout:
        for info in zin.infolist():
            if info.filename in drop:
                continue
            if info.filename in replace or info.filename in edit:
                data = replace.get(info.filename)
                if data is None:
                    data = edit[info.filename](zin.read(info.filename))
            else:
                data = zin.read(info.filename)
            put(zout, info.filename, data, level)
        for n, data in add.items():
            put(zout, n, data, level)


def put(zout, name, data, level=9):
    zi = zipfile.ZipInfo(name, (2026, 10, 11, 0, 0, 0))
    zi.compress_type = zipfile.ZIP_DEFLATED
    zi._compresslevel = level
    if isinstance(data, (bytes, bytearray)):
        zout.writestr(zi, data)
    else:  # 청크 반복자(큰 항목 스트리밍)
        with zout.open(zi, "w") as f:
            for chunk in data:
                f.write(chunk)


def repeat(block, total):
    n = total // len(block)
    big = block * max(1, (1 << 20) // len(block))
    full, rem = divmod(n * len(block), len(big))
    for _ in range(full):
        yield big
    if rem:
        yield big[:rem]


def sheet_stream(head, block, total, tail):
    yield SHEET_HEAD + head
    yield from repeat(block, total)
    yield tail


MB = 1 << 20
FILES = {}


def reg(fn):
    FILES[fn.__name__] = fn
    return fn


# ---------- (a) 압축 폭탄 ----------
@reg
def bomb_rows_300mb():  # 행에 r 속성이 없는 동일 행 반복 (순서만 믿는 행)
    rewrite(f"{OUT}/bomb_rows_300mb.xlsx", replace={"xl/worksheets/sheet1.xml": sheet_stream(b"<sheetData>", b'<row><c t="n"><v>1</v></c></row>', 300 * MB, b"</sheetData></worksheet>")})


@reg
def bomb_rows_1gb():
    rewrite(f"{OUT}/bomb_rows_1gb.xlsx", replace={"xl/worksheets/sheet1.xml": sheet_stream(b"<sheetData>", b'<row><c t="n"><v>1</v></c></row>', 1000 * MB, b"</sheetData></worksheet>")})


@reg
def bomb_rows_800mb():  # 압축 후 1MB 미만이 되도록 블록(약 1KB)을 크게 잡은 변형
    blk = b'<row><c t="n"><v>1</v></c></row>' * 30
    rewrite(f"{OUT}/bomb_rows_800mb.xlsx", replace={"xl/worksheets/sheet1.xml": sheet_stream(b"<sheetData>", blk, 800 * MB, b"</sheetData></worksheet>")})


@reg
def bomb_whitespace_900mb():
    rewrite(f"{OUT}/bomb_whitespace_900mb.xlsx", replace={"xl/worksheets/sheet1.xml": sheet_stream(b"<sheetData>", b" " * 1024, 900 * MB, b"</sheetData></worksheet>")})


@reg
def bomb_rows_rattr_300mb():  # 행·셀에 r 속성이 있고 모두 같은 값(r=1 반복)
    rewrite(f"{OUT}/bomb_rows_rattr_300mb.xlsx", replace={"xl/worksheets/sheet1.xml": sheet_stream(b"<sheetData>", b'<row r="1"><c r="A1" t="n"><v>1</v></c></row>', 300 * MB, b"</sheetData></worksheet>")})


@reg
def bomb_whitespace_1gb():  # 시트 XML에 공백 1GB (행 없음)
    rewrite(f"{OUT}/bomb_whitespace_1gb.xlsx", replace={"xl/worksheets/sheet1.xml": sheet_stream(b"<sheetData>", b" " * 1024, 1000 * MB, b"</sheetData></worksheet>")})


@reg
def bomb_celltext_500mb():  # 셀 하나의 inlineStr 텍스트가 500MB
    rewrite(f"{OUT}/bomb_celltext_500mb.xlsx", replace={"xl/worksheets/sheet1.xml": sheet_stream(b'<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>', b"a" * 1024, 500 * MB, b"</t></is></c></row></sheetData></worksheet>")})


@reg
def bomb_sst_many_300mb():  # sharedStrings: 짧은 문자열 수천만 개
    pre = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="1" uniqueCount="1">'
    def s():
        yield pre
        yield from repeat(b"<si><t>x</t></si>", 300 * MB)
        yield b"</sst>"
    rewrite(f"{OUT}/bomb_sst_many_300mb.xlsx", replace={"xl/sharedStrings.xml": s()})


@reg
def bomb_sst_one_200mb():  # sharedStrings: 문자열 하나가 200MB
    pre = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="1" uniqueCount="1"><si><t>'
    def s():
        yield pre
        yield from repeat(b"b" * 1024, 200 * MB)
        yield b"</t></si></sst>"
    rewrite(f"{OUT}/bomb_sst_one_200mb.xlsx", replace={"xl/sharedStrings.xml": s()})


@reg
def bomb_small_declared_lie():  # 중앙 디렉터리 해제 크기를 작게 속인 폭탄(300MB 실제, 선언 1000바이트)
    tmp = f"{OUT}/_tmp_lie.xlsx"
    rewrite(tmp, replace={"xl/worksheets/sheet1.xml": sheet_stream(b"<sheetData>", b'<row><c t="n"><v>1</v></c></row>', 300 * MB, b"</sheetData></worksheet>")})
    data = bytearray(open(tmp, "rb").read())
    i = 0
    cnt = 0
    while True:
        i = data.find(b"PK\x01\x02", i)
        if i < 0:
            break
        nlen = struct.unpack_from("<H", data, i + 28)[0]
        name = bytes(data[i + 46:i + 46 + nlen])
        if name == b"xl/worksheets/sheet1.xml":
            struct.pack_into("<I", data, i + 24, 1000)  # 중앙 디렉터리 file_size만 거짓
            cnt += 1
        i += 4
    open(f"{OUT}/bomb_small_declared_lie.xlsx", "wb").write(data)
    os.remove(tmp)


# ---------- (b) 거짓 dimension ----------
def _sheet_with_dim(dim, nrows=50):
    rows = b"".join(b'<row r="%d"><c r="A%d" t="n"><v>%d</v></c><c r="B%d" t="n"><v>2</v></c></row>' % (i, i, i, i) for i in range(1, nrows + 1))
    return SHEET_HEAD + b'<dimension ref="' + dim.encode() + b'"/><sheetData>' + rows + b"</sheetData></worksheet>"


@reg
def dim_false():
    rewrite(f"{OUT}/dim_false.xlsx", replace={"xl/worksheets/sheet1.xml": _sheet_with_dim("A1:XFD1048576")})


# ---------- (c) 큰 공유 문자열 표 / 긴 문자열 ----------
@reg
def sst_unique_big():  # 정상적인 큰 공유 문자열: 중복 없는 긴 문자열 5만 개(약 100MB 해제)
    r = random.Random(3)
    b = g.Book()
    sh = g.Sheet("데이터")
    b.sheets.append(sh)
    b.add_row(sh, ["a", "b"])
    for i in range(20000):
        b.add_row(sh, [g.syl(r, 400), str(i)])  # 한글 400자(3바이트)=1.2KB * 2만 = 24MB 해제
    b.save(f"{OUT}/sst_unique_big.xlsx")


@reg
def cell_long_string():  # 셀 하나에 한글 3만자(엑셀 한 셀 상한 32,767자)
    r = random.Random(4)
    b = g.Book()
    sh = g.Sheet("데이터")
    b.sheets.append(sh)
    b.add_row(sh, ["a", "b"])
    b.add_row(sh, [g.syl(r, 32767), "x"])
    b.save(f"{OUT}/cell_long_string.xlsx")


@reg
def cols_10000():  # 한 행에 열 1만 개 (X-27 원안)
    b = g.Book()
    sh = g.Sheet("데이터")
    b.sheets.append(sh)
    b.add_row(sh, [f"c{i}" for i in range(10000)])
    for i in range(20):
        b.add_row(sh, list(range(10000)))
    b.save(f"{OUT}/cols_10000.xlsx")


@reg
def cols_16384_rows_20():
    b = g.Book()
    sh = g.Sheet("데이터")
    b.sheets.append(sh)
    for i in range(20):
        b.add_row(sh, [i] * 16384)
    b.save(f"{OUT}/cols_16384_rows_20.xlsx")


# ---------- (d) XML 엔티티 ----------
BILLION = (b'<?xml version="1.0"?>\n<!DOCTYPE lolz [<!ENTITY lol "lol">' + b"".join(
    b'<!ENTITY lol%d "%s">' % (i, b"".join(b"&lol%d;" % (i - 1) if i > 1 else b"&lol;" for _ in range(10))) for i in range(1, 10)) + b"]>\n")


@reg
def xxe_billion_sheet():  # 시트 XML에 billion laughs (10^9 배)
    body = SHEET_HEAD + b'<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>&lol9;</t></is></c></row></sheetData></worksheet>'
    # 선언은 XML 선언 뒤에 와야 하므로 SHEET_HEAD의 XML 선언을 DOCTYPE 포함본으로 교체
    body = BILLION + body.split(b"\n", 1)[1]
    rewrite(f"{OUT}/xxe_billion_sheet.xlsx", replace={"xl/worksheets/sheet1.xml": body})


@reg
def xxe_billion_sst():
    body = (BILLION + b'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="1" uniqueCount="1"><si><t>&lol9;</t></si></sst>')
    rewrite(f"{OUT}/xxe_billion_sst.xlsx", replace={"xl/sharedStrings.xml": body})


@reg
def xxe_external():  # 외부 일반 엔티티 file:///tmp/xxe_canary.txt
    body = (b'<?xml version="1.0"?>\n<!DOCTYPE d [<!ENTITY xxe SYSTEM "file:///tmp/xxe_canary.txt">]>\n' + SHEET_HEAD.split(b"\n", 1)[1]
            + b'<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>&xxe;</t></is></c></row></sheetData></worksheet>')
    rewrite(f"{OUT}/xxe_external.xlsx", replace={"xl/worksheets/sheet1.xml": body})


@reg
def xxe_external_sst():
    body = (b'<?xml version="1.0"?>\n<!DOCTYPE d [<!ENTITY xxe SYSTEM "file:///tmp/xxe_canary.txt">]>\n'
            b'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="1" uniqueCount="1"><si><t>&xxe;</t></si></sst>')
    rewrite(f"{OUT}/xxe_external_sst.xlsx", replace={"xl/sharedStrings.xml": body})


@reg
def xxe_quadratic():  # 이차 확장: 큰 엔티티(수 MB)를 수만 번 참조
    big = b"A" * 50000
    refs = b"&a;" * 50000
    body = (b'<?xml version="1.0"?>\n<!DOCTYPE d [<!ENTITY a "' + big + b'">]>\n' + SHEET_HEAD.split(b"\n", 1)[1]
            + b'<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>' + refs + b"</t></is></c></row></sheetData></worksheet>")
    rewrite(f"{OUT}/xxe_quadratic.xlsx", replace={"xl/worksheets/sheet1.xml": body})


# ---------- (e) 시트 수 과다 ----------
@reg
def sheets_5000():
    b = g.Book()
    for i in range(5000):
        sh = g.Sheet(f"S{i + 1}")
        b.sheets.append(sh)
        b.add_row(sh, ["a", "b"])
        b.add_row(sh, [i, "x"])
    b.save(f"{OUT}/sheets_5000.xlsx")


@reg
def sheets_50000_refs():  # workbook.xml만 시트 5만 개를 선언, 시트 파일은 같은 부분을 가리킴(항목 수는 작음)
    def edit(x):
        s = x.decode()
        head, tail = s.split("<sheets>")
        _, rest = tail.split("</sheets>")
        sheets = "".join(f'<sheet name="S{i}" sheetId="{i}" r:id="rId1"/>' for i in range(1, 50001))
        return (head + "<sheets>" + sheets + "</sheets>" + rest).encode()
    rewrite(f"{OUT}/sheets_50000_refs.xlsx", edit={"xl/workbook.xml": edit})


# ---------- (f) 형식 위장·암호화·매크로·외부 링크 ----------
@reg
def not_zip_random():
    open(f"{OUT}/not_zip_random.xlsx", "wb").write(random.Random(5).randbytes(200000))


@reg
def not_zip_text():
    open(f"{OUT}/not_zip_text.xlsx", "w", encoding="utf-8").write("a,b,c\n1,2,3\n한글,2,3\n")


@reg
def empty_file():
    open(f"{OUT}/empty_file.xlsx", "wb").close()


@reg
def truncated_zip():
    d = open(base(), "rb").read()
    open(f"{OUT}/truncated_zip.xlsx", "wb").write(d[: len(d) // 2])


@reg
def png_as_xlsx():
    open(f"{OUT}/png_as_xlsx.xlsx", "wb").write(b"\x89PNG\r\n\x1a\n" + random.Random(6).randbytes(5000))


@reg
def zip_not_xlsx():  # 정상 zip이지만 xlsx 아님
    with zipfile.ZipFile(f"{OUT}/zip_not_xlsx.xlsx", "w") as z:
        z.writestr("hello.txt", "hi")


@reg
def ole2_signature_only():
    open(f"{OUT}/ole2_signature_only.xlsx", "wb").write(bytes.fromhex("D0CF11E0A1B11AE1") + b"\x00" * 4000)


@reg
def encrypted_xlsx():
    import msoffcrypto
    with open(base(), "rb") as f:
        of = msoffcrypto.OfficeFile(f)
        # 암호화 지원 여부 확인용: 복호화 객체만 쓸 수 있으면 기록
    try:
        from msoffcrypto.format.ooxml import OOXMLFile
        with open(base(), "rb") as src, open(f"{OUT}/encrypted_xlsx.xlsx", "wb") as dst:
            OOXMLFile(src).encrypt("pw1234", dst)
    except Exception as e:  # noqa: BLE001
        print("encrypted_xlsx 생성 실패:", type(e).__name__, e)


@reg
def xlsm_macro():
    def ct(x):
        return x.replace(b"spreadsheetml.sheet.main+xml", b"ms-excel.sheet.macroEnabled.main+xml") + b""
    def ct2(x):
        s = x.decode().replace("</Types>", '<Default Extension="bin" ContentType="application/vnd.ms-office.vbaProject"/></Types>')
        return s.encode().replace(b"spreadsheetml.sheet.main+xml", b"ms-excel.sheet.macroEnabled.main+xml")
    def rels(x):
        return x.decode().replace("</Relationships>", '<Relationship Id="rId99" Type="http://schemas.microsoft.com/office/2006/relationships/vbaProject" Target="vbaProject.bin"/></Relationships>').encode()
    rewrite(f"{OUT}/xlsm_macro.xlsm", edit={"[Content_Types].xml": ct2, "xl/_rels/workbook.xml.rels": rels}, add={"xl/vbaProject.bin": bytes.fromhex("D0CF11E0A1B11AE1") + b"\x00" * 2000})
    shutil.copy(f"{OUT}/xlsm_macro.xlsm", f"{OUT}/xlsm_macro_renamed.xlsx")


@reg
def external_link():
    ext = (b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<externalLink xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
           b'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><externalBook r:id="rId1"><sheetNames><sheetName val="Sheet1"/></sheetNames></externalBook></externalLink>')
    erel = (b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/externalLinkPath" Target="file:///C:/secret/other.xlsx" TargetMode="External"/></Relationships>')
    def ct(x):
        return x.decode().replace("</Types>", '<Override PartName="/xl/externalLinks/externalLink1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.externalLink+xml"/></Types>').encode()
    def rels(x):
        return x.decode().replace("</Relationships>", '<Relationship Id="rId90" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/externalLink" Target="externalLinks/externalLink1.xml"/></Relationships>').encode()
    def wbx(x):
        return x.decode().replace("</sheets>", '</sheets><externalReferences><externalReference r:id="rId90"/></externalReferences>').encode()
    rewrite(f"{OUT}/external_link.xlsx", edit={"[Content_Types].xml": ct, "xl/_rels/workbook.xml.rels": rels, "xl/workbook.xml": wbx},
            add={"xl/externalLinks/externalLink1.xml": ext, "xl/externalLinks/_rels/externalLink1.xml.rels": erel})


# ---------- (g) 경로 순회 ----------
@reg
def zip_path_traversal():
    rewrite(f"{OUT}/zip_path_traversal.xlsx", add={"../evil.txt": b"x", "/abs/evil.txt": b"x", "a/../../b.txt": b"x", "..\\win\\evil.txt": b"x"})


# ---------- 선언 크기 거짓(local+central) ----------
@reg
def bomb_small_declared_lie_local():
    tmp = f"{OUT}/_tmp_lie2.xlsx"
    rewrite(tmp, replace={"xl/worksheets/sheet1.xml": sheet_stream(b"<sheetData>", b'<row><c t="n"><v>1</v></c></row>', 100 * MB, b"</sheetData></worksheet>")})
    data = bytearray(open(tmp, "rb").read())
    for sig, off in ((b"PK\x03\x04", 22), (b"PK\x01\x02", 24)):
        i = 0
        while True:
            i = data.find(sig, i)
            if i < 0:
                break
            nlen = struct.unpack_from("<H", data, i + (26 if sig == b"PK\x03\x04" else 28))[0]
            base_off = 30 if sig == b"PK\x03\x04" else 46
            name = bytes(data[i + base_off:i + base_off + nlen])
            if name == b"xl/worksheets/sheet1.xml":
                struct.pack_into("<I", data, i + off, 1000)
            i += 4
    open(f"{OUT}/bomb_small_declared_lie_local.xlsx", "wb").write(data)
    os.remove(tmp)


if __name__ == "__main__":
    open("/tmp/xxe_canary.txt", "w").write("CANARY-SECRET-12345")
    for name, fn in FILES.items():
        if WANT and name not in WANT:
            continue
        t0 = time.time()
        fn()
        print(name, "ok", round(time.time() - t0, 1), "s", flush=True)
