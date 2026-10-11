"""X-27 합성 xlsx 생성기 (난수·한글, seed 고정). 사용: python gen_big.py <profile> <target_mb> <out.xlsx>
프로필: tall(12열 좁고 긴 표) / wide(150열) / fmt(수식 캐시값·병합·서식 200종) / multi(시트 6개)
Excel이 저장한 파일과 같이 sharedStrings.xml을 쓰도록 시트 XML을 직접 만든다(openpyxl write-only는 inlineStr을 써서 부적합).
스타일(styles.xml)만 openpyxl로 만든 골격에서 가져온다. 압축 후 크기가 target_mb(MiB)에 맞도록 행 수를 보정한다."""
import sys, os, random, zipfile, datetime, json, io, time
sys.path.insert(0, os.environ.get("SITE", "/home/user/BI-Wizard/_workspace/gate3/experiments/r4/import/site"))
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from xml.sax.saxutils import escape

WORDS = "매출 비용 이익 고객 주문 배송 지연 반품 재고 입고 출고 단가 수량 부서 팀장 담당자 서울 부산 대구 인천 광주 대전 울산 세종 수원 창원 제품 서비스 계약 견적 청구 결제 승인 보류 취소 완료 진행 예정 점검 장애 개선 요청 문의 답변 확인 검토 반영".split()
CATS = ["식품", "가전", "의류", "도서", "완구", "가구", "문구", "화장품", "스포츠", "자동차", "주방", "욕실", "정원", "펫", "건강", "여행", "음악", "영화", "게임", "기타"]
ALNUM = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
EPOCH = datetime.date(1899, 12, 30)
BASE_STYLES = 4


def syl(r, n):
    return "".join(chr(r.randint(0xAC00, 0xD7A3)) for _ in range(n))


def memo(r):
    return " ".join(r.choice(WORDS) for _ in range(r.randint(3, 8))) + f" {r.randint(1, 99999)}"


def rdate(r):
    return datetime.date(2020, 1, 1) + datetime.timedelta(days=r.randint(0, 2500))


class F:  # 수식 + 캐시값
    def __init__(self, expr, cached):
        self.expr, self.cached = expr, cached


def make_styles(nfmt_combos=200, seed=7):
    """골격 xlsx(openpyxl)를 만들어 styles.xml과 (fmt용 스타일 그룹)을 돌려준다."""
    r = random.Random(seed)
    thin = Side(style="thin")
    wb = Workbook(write_only=True)
    ws = wb.create_sheet("s")

    def mk(v, fmt="General", bold=False, color="000000", fill=None, border=False, align=None):
        c = WriteOnlyCell(ws, value=v)
        c.number_format = fmt
        c.font = Font(bold=bold, color=color)
        if fill:
            c.fill = PatternFill("solid", fgColor=fill)
        if border:
            c.border = Border(left=thin, right=thin)
        if align:
            c.alignment = Alignment(horizontal=align)
        return c

    row = [mk(1, "yyyy-mm-dd"), mk(1, "yyyy-mm-dd hh:mm:ss"), mk(1, "0.0%"), mk(1, "#,##0.00")]
    groups = {"date": [], "num": [], "pct": [], "text": []}
    fmts = {"date": ["yyyy-mm-dd", "yyyy/mm/dd", "m/d/yyyy"], "num": ["0.00", "#,##0", "#,##0.00;[Red]-#,##0.00", '"₩"#,##0', "General"], "pct": ["0.0%", "0%"], "text": ["General", "@"]}
    seen = set()
    idx = BASE_STYLES
    while len(seen) < nfmt_combos:
        kind = r.choice(list(groups))
        k = (kind, r.choice(fmts[kind]), r.choice([0, 1]), r.choice(["000000", "FF0000", "0000FF", "008000", "808080"]), r.choice(["FFFFFF", "FFFF00", "DDEBF7", "E2EFDA"]), r.choice([0, 1]), r.choice(["left", "center", "right"]))
        if k in seen:
            continue
        seen.add(k)
        row.append(mk(1, k[1], bool(k[2]), k[3], k[4], bool(k[5]), k[6]))
        idx += 1
        groups[kind].append(idx)
    ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    z = zipfile.ZipFile(io.BytesIO(buf.getvalue()))
    sx = z.read("xl/styles.xml")
    # styles.xml의 cellXfs를 직접 읽어 서식 코드별로 인덱스를 분류한다(openpyxl이 같은 xf를 합칠 수 있어 순서를 가정하지 않는다)
    import xml.etree.ElementTree as ET
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    root = ET.fromstring(sx)
    custom = {int(n.get("numFmtId")): n.get("formatCode") for n in root.findall("m:numFmts/m:numFmt", ns)}
    builtin = {0: "General", 2: "0.00", 3: "#,##0", 4: "#,##0.00", 9: "0%", 14: "m/d/yyyy", 49: "@"}
    groups = {"date": [], "num": [], "pct": [], "text": []}
    special = {}
    for i, xf in enumerate(root.findall("m:cellXfs/m:xf", ns)):
        code = custom.get(int(xf.get("numFmtId")), builtin.get(int(xf.get("numFmtId")), "?"))
        if i == 0:
            continue
        if i <= BASE_STYLES:  # 앞 4개(날짜·일시·퍼센트·숫자)는 전용 스타일
            special.setdefault(code, i)
            continue
        if code in ("yyyy-mm-dd", "yyyy/mm/dd", "m/d/yyyy"):
            groups["date"].append(i)
        elif code in ("0.0%", "0%"):
            groups["pct"].append(i)
        elif code in ("General", "@"):
            groups["text"].append(i)
        else:
            groups["num"].append(i)
        special.setdefault(code, i)
    return sx, z.read("xl/theme/theme1.xml"), groups, special


STYLES_XML, THEME_XML, GROUPS, SPECIAL = make_styles()
S_DATE, S_DT, S_PCT, S_NUM = SPECIAL['yyyy-mm-dd'], SPECIAL['yyyy-mm-dd hh:mm:ss'], SPECIAL['0.0%'], SPECIAL['#,##0.00']


def col_name(i):  # 0-based
    s = ""
    i += 1
    while i:
        i, rem = divmod(i - 1, 26)
        s = chr(65 + rem) + s
    return s


class Sheet:
    def __init__(self, name):
        self.name = name
        self.buf = io.StringIO()
        self.nrows = 0
        self.ncols = 0
        self.merges = []


class Book:
    def __init__(self):
        self.sst = {}
        self.sst_count = 0
        self.sheets = []

    def si(self, s):
        self.sst_count += 1
        i = self.sst.get(s)
        if i is None:
            i = self.sst[s] = len(self.sst)
        return i

    def add_row(self, sh, row, styles=None):
        sh.nrows += 1
        rn = sh.nrows
        sh.ncols = max(sh.ncols, len(row))
        w = sh.buf.write
        w(f'<row r="{rn}">')
        for j, v in enumerate(row):
            if v is None:
                continue
            ref = f"{col_name(j)}{rn}"
            s = styles[j] if styles and styles[j] else 0
            sa = f' s="{s}"' if s else ""
            if isinstance(v, F):
                if isinstance(v.cached, str):
                    w(f'<c r="{ref}"{sa} t="str"><f>{escape(v.expr)}</f><v>{escape(v.cached)}</v></c>')
                else:
                    w(f'<c r="{ref}"{sa}><f>{escape(v.expr)}</f><v>{v.cached}</v></c>')
            elif isinstance(v, bool):
                w(f'<c r="{ref}"{sa} t="b"><v>{int(v)}</v></c>')
            elif isinstance(v, str):
                w(f'<c r="{ref}"{sa} t="s"><v>{self.si(v)}</v></c>')
            elif isinstance(v, datetime.datetime):
                d = v - datetime.datetime(1899, 12, 30)
                w(f'<c r="{ref}" s="{s or S_DT}"><v>{d.days + d.seconds / 86400:.10f}</v></c>')
            elif isinstance(v, datetime.date):
                w(f'<c r="{ref}" s="{s or S_DATE}"><v>{(v - EPOCH).days}</v></c>')
            else:
                w(f'<c r="{ref}"{sa}><v>{v}</v></c>')
        w("</row>")

    def save(self, path):
        names = [s.name for s in self.sheets]
        ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
              '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
              + "".join(f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(len(names)))
              + '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
              '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
              '<Override PartName="/xl/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/></Types>')
        rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        wbx = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
               + "".join(f'<sheet name="{escape(n)}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, n in enumerate(names)) + "</sheets></workbook>")
        n = len(names)
        wrels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 + "".join(f'<Relationship Id="rId{i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i + 1}.xml"/>' for i in range(n))
                 + f'<Relationship Id="rId{n + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                 f'<Relationship Id="rId{n + 2}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'
                 f'<Relationship Id="rId{n + 3}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/></Relationships>')
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            z.writestr("[Content_Types].xml", ct)
            z.writestr("_rels/.rels", rels)
            z.writestr("xl/workbook.xml", wbx)
            z.writestr("xl/_rels/workbook.xml.rels", wrels)
            z.writestr("xl/styles.xml", STYLES_XML)
            z.writestr("xl/theme/theme1.xml", THEME_XML)
            for i, sh in enumerate(self.sheets):
                head = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                        f'<dimension ref="A1:{col_name(max(sh.ncols, 1) - 1)}{max(sh.nrows, 1)}"/><sheetViews><sheetView workbookViewId="0"/></sheetViews><sheetFormatPr defaultRowHeight="15"/><sheetData>')
                tail = "</sheetData>"
                if sh.merges:
                    tail += f'<mergeCells count="{len(sh.merges)}">' + "".join(f'<mergeCell ref="{m}"/>' for m in sh.merges) + "</mergeCells>"
                tail += "</worksheet>"
                z.writestr(f"xl/worksheets/sheet{i + 1}.xml", (head + sh.buf.getvalue() + tail).encode("utf-8"))
            items = sorted(self.sst.items(), key=lambda kv: kv[1])
            sx = io.StringIO()
            sx.write(f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{self.sst_count}" uniqueCount="{len(items)}">')
            for s, _ in items:
                sx.write(f'<si><t xml:space="preserve">{escape(s)}</t></si>')
            sx.write("</sst>")
            z.writestr("xl/sharedStrings.xml", sx.getvalue().encode("utf-8"))


def tall_row(r, i):
    return [i, rdate(r), round(r.uniform(100, 99999), 2), r.randint(1, 500), syl(r, r.randint(2, 4)),
            "".join(r.choice(ALNUM) for _ in range(12)), r.choice(CATS), memo(r),
            round(r.random(), 6), r.random() < 0.5, datetime.datetime(2026, 1, 1) + datetime.timedelta(seconds=r.randint(0, 20000000)),
            r.choice(["Y", "N", "보류", None])]


WIDE_COLS = int(os.environ.get("WIDE_COLS", "150"))


def wide_row(r, i, ncols=None):
    ncols = ncols or WIDE_COLS
    row = [i]
    for c in range(1, ncols):
        k = c % 10
        if k == 0:
            row.append(r.choice(CATS))
        elif k == 1:
            row.append(rdate(r))
        elif k == 2:
            row.append(syl(r, r.randint(2, 4)) + str(r.randint(1, 999)))
        else:
            row.append(round(r.uniform(-1e6, 1e6), r.randint(0, 6)))
    return row


def build(profile, rows, path, seed=1):
    r = random.Random(seed)
    b = Book()
    if profile in ("tall", "wide"):
        sh = Sheet("데이터")
        b.sheets.append(sh)
        nc = 12 if profile == "tall" else WIDE_COLS
        b.add_row(sh, [f"열{c + 1}" for c in range(nc)])
        fn = tall_row if profile == "tall" else wide_row
        for i in range(1, rows + 1):
            b.add_row(sh, fn(r, i))
    elif profile == "multi":
        names = ["요약", "데이터1", "데이터2", "데이터3", "데이터4", "설명"]
        for nm in names:
            sh = Sheet(nm)
            b.sheets.append(sh)
            b.add_row(sh, [f"열{c + 1}" for c in range(12)])
            for i in range(1, rows // 6 + 1):
                b.add_row(sh, tall_row(r, i))
    elif profile == "fmt":
        sh = Sheet("서식")
        b.sheets.append(sh)
        hdr = ["번호", "일자", "단가", "수량", "금액(수식)", "분류", "비율", "등급(수식)", "누계(수식)", "비고", "담당", "메모"]
        b.add_row(sh, hdr, [GROUPS["text"][0]] * 12)
        cum = 0.0
        G = GROUPS
        for i in range(1, rows + 1):
            row = i + 1
            price = round(r.uniform(100, 99999), 2)
            qty = r.randint(1, 500)
            amt = round(price * qty, 2)
            cum += amt
            d = rdate(r)
            vals = [i, d, price, qty, F(f"C{row}*D{row}", amt), r.choice(CATS), round(r.random(), 4),
                    F(f'IF(E{row}>1000000,"높음","낮음")', "높음" if amt > 1000000 else "낮음"), F(f"SUM(E$2:E{row})", round(cum, 2)),
                    memo(r), syl(r, 3), round(r.uniform(-1e5, 1e5), 3)]
            st = [r.choice(G["num"]), r.choice(G["date"]), r.choice(G["num"]), r.choice(G["num"]), r.choice(G["num"]), r.choice(G["text"]),
                  r.choice(G["pct"]), r.choice(G["text"]), r.choice(G["num"]), r.choice(G["text"]), r.choice(G["text"]), r.choice(G["num"])]
            b.add_row(sh, vals, st)
            if i % 25 == 0:
                sh.merges.append(f"J{row}:L{row}")
    else:
        raise SystemExit("profile?")
    b.save(path)
    return {"sheets": [(s.name, s.nrows, s.ncols) for s in b.sheets], "sst_unique": len(b.sst), "sst_count": b.sst_count}


def main():
    profile, target_mb, out = sys.argv[1], float(sys.argv[2]), sys.argv[3]
    target = target_mb * 1024 * 1024
    t0 = time.time()
    probe = 3000 if profile != "wide" else 300
    build(profile, probe, out)
    per_row = os.path.getsize(out) / probe
    rows = int(target / per_row)
    for it in range(4):
        info = build(profile, rows, out)
        sz = os.path.getsize(out)
        if abs(sz - target) / target < 0.02:
            break
        rows = int(rows * target / sz)
    sz = os.path.getsize(out)
    print(json.dumps({"profile": profile, "rows_param": rows, **info, "bytes": sz, "mib": round(sz / 1048576, 2), "secs": round(time.time() - t0, 1)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
