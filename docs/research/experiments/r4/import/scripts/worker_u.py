"""X-27 측정 작업자. 사용: python worker.py <mode> <file> [key=value ...]
mode: precheck | preview | scan | normal | open_only
한 프로세스에서 한 번 실행하고 JSON 한 줄을 출력한다. 최대 RSS는 resource.getrusage(RUSAGE_SELF).ru_maxrss."""
import sys, os, time, json, resource, zipfile, collections

_ras = os.environ.get("RLIMIT_AS_MB")
if _ras:
    resource.setrlimit(resource.RLIMIT_AS, (int(_ras) << 20, int(_ras) << 20))
_rcpu = os.environ.get("RLIMIT_CPU_S")
if _rcpu:
    resource.setrlimit(resource.RLIMIT_CPU, (int(_rcpu), int(_rcpu) + 5))

sys.path.insert(0, "/work/site")
if os.environ.get("USE_DEFUSED") == "1":
    sys.path.insert(0, "/work/site-defused")

T0 = time.perf_counter()
C0 = time.process_time()


def rss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


import openpyxl  # noqa: E402
from openpyxl import load_workbook  # noqa: E402
from openpyxl.xml import DEFUSEDXML  # noqa: E402

BASE_RSS = rss_mb()
T_IMPORT = time.perf_counter() - T0

LIM = dict(max_rows=100000, max_cols=100, max_cells=2000000, max_bytes=10 * 1024 * 1024,
           max_entries=1000, max_unc_total=500 * 1024 * 1024, max_ratio=100.0, max_sst_unc=100 * 1024 * 1024,
           max_part_unc=300 * 1024 * 1024, max_sheets=30, time_limit=1e9, small_xml=2 * 1024 * 1024)


def precheck(path, lim=LIM):
    """zip 중앙 디렉터리만 읽는 사전 검사. 반환: (reasons, info)"""
    import xml.etree.ElementTree as ET
    reasons, info = [], {}
    with open(path, "rb") as f:
        sig = f.read(8)
    info["sig"] = sig.hex()
    if sig[:4] == b"\xd0\xcf\x11\xe0":
        return ["OLE2(암호화 xlsx 또는 구형 xls)"], info
    if sig[:4] != b"PK\x03\x04":
        return ["zip 시그니처 아님"], info
    try:
        z = zipfile.ZipFile(path)
    except Exception as e:  # noqa: BLE001
        return [f"zip 열기 실패: {type(e).__name__}"], info
    with z:
        il = z.infolist()
        info["entries"] = len(il)
        tot_unc = sum(i.file_size for i in il)
        tot_comp = sum(i.compress_size for i in il)
        info["unc_total_mb"] = round(tot_unc / 1048576, 2)
        info["comp_total_mb"] = round(tot_comp / 1048576, 3)
        info["ratio_total"] = round(tot_unc / max(tot_comp, 1), 1)
        info["max_part"] = max(((i.file_size, i.filename) for i in il), default=(0, ""))
        info["max_part_mb"] = round(info["max_part"][0] / 1048576, 2)
        info["max_part"] = info["max_part"][1]
        names = [i.filename for i in il]
        if len(il) > lim["max_entries"]:
            reasons.append("항목 수 초과")
        if tot_unc > lim["max_unc_total"]:
            reasons.append("해제 합계 초과")
        if tot_unc / max(tot_comp, 1) > lim["max_ratio"]:
            reasons.append("압축률 초과")
        if any(i.file_size > lim["max_part_unc"] for i in il):
            reasons.append("항목 하나의 해제 크기 초과")
        if any(i.flag_bits & 1 for i in il):
            reasons.append("암호화 항목")
        if any(n.startswith("/") or ".." in n.replace("\\", "/").split("/") or "\\" in n or ":" in n for n in names):
            reasons.append("경로 순회·절대 경로·역슬래시 항목 이름")
        if any(n.lower().endswith("vbaproject.bin") for n in names):
            reasons.append("매크로(vbaProject.bin)")
        if any(n.startswith("xl/externalLinks/") for n in names):
            reasons.append("외부 링크")
        if any(n.startswith("xl/embeddings/") or n.startswith("xl/activeX/") for n in names):
            reasons.append("임베디드 개체")
        for req in ("[Content_Types].xml", "xl/workbook.xml"):
            if req not in names:
                reasons.append(f"필수 항목 없음: {req}")
        if len(set(names)) != len(names):
            reasons.append("중복 항목 이름")
        sst = [i for i in il if i.filename == "xl/sharedStrings.xml"]
        if sst and sst[0].file_size > lim["max_sst_unc"]:
            reasons.append("sharedStrings 해제 크기 초과")
        if "[Content_Types].xml" in names and "xl/workbook.xml" in names and not reasons:
            ct = z.getinfo("[Content_Types].xml")
            wbi = z.getinfo("xl/workbook.xml")
            if ct.file_size > lim["small_xml"] or wbi.file_size > lim["small_xml"]:
                reasons.append("작은 XML이 너무 큼")
            else:
                cts = z.read("[Content_Types].xml")
                if b"macroEnabled" in cts:
                    reasons.append("macroEnabled 콘텐츠 형식(.xlsm)")
                if b"spreadsheetml.sheet.main+xml" not in cts:
                    reasons.append("워크북 콘텐츠 형식이 xlsx가 아님")
                root = ET.fromstring(z.read("xl/workbook.xml"))
                sheets = [e for e in root.iter() if e.tag.endswith("}sheet")]
                info["sheet_names"] = [e.get("name") for e in sheets][:30]
                info["n_sheets"] = len(sheets)
                if len(sheets) > lim["max_sheets"]:
                    reasons.append("시트 수 초과")
    return reasons, info


def precheck2(path, lim=LIM):
    reasons, info = precheck(path, lim)
    if reasons:
        return reasons, info
    import re
    with zipfile.ZipFile(path) as z:
        for i in z.infolist():
            n = i.filename
            if not n.endswith(".xml") and not n.endswith(".rels"):
                continue
            with z.open(i) as f:
                head = f.read(4096)
            if b"<!DOCTYPE" in head or b"<!ENTITY" in head:
                reasons.append(f"DTD/ENTITY 선언: {n}")
            if head[:2] in (b"\xff\xfe", b"\xfe\xff") or (head[:2] and head[0] == 0 and not head.startswith(b"PK")):
                reasons.append(f"UTF-8이 아닌 XML 인코딩 의심: {n}")
            if n.startswith("xl/worksheets/sheet"):
                d = head.find(b"<dimension")
                sd = head.find(b"<sheetData")
                if d < 0 or (sd >= 0 and sd < d):
                    # 앞 4KB에 dimension이 없으면 더 읽지 않고 거부(정상 파일은 sheetData 앞에 dimension이 있다)
                    reasons.append(f"<dimension> 없음(앞 4KB): {n}")
    return reasons, info


def infer(vals):
    t = collections.Counter()
    for v in vals:
        t[type(v).__name__] += 1
    return t


def open_ro(path, **kw):
    return load_workbook(path, read_only=True, data_only=True, keep_links=False, **kw)


def run(mode, path, opt):
    out = {"mode": mode, "file": os.path.basename(path), "file_mb": round(os.path.getsize(path) / 1048576, 2), "defusedxml": bool(DEFUSEDXML),
           "import_s": round(T_IMPORT, 3), "base_rss_mb": round(BASE_RSS, 1)}
    lim = dict(LIM)
    for k in ("max_rows", "max_cols", "max_cells"):
        if k in opt:
            lim[k] = int(opt[k])
    t1 = time.perf_counter()
    if mode == "precheck":
        reasons, info = precheck(path, lim)
        out.update(reasons=reasons, info=info)
    elif mode == "precheck2":
        reasons, info = precheck2(path, lim)
        out.update(reasons=reasons, info=info)
    elif mode == "open_only":
        wb = load_workbook(path, read_only=True, data_only=True, keep_links=False)
        out["open_s"] = round(time.perf_counter() - t1, 3)
        out["sheets"] = wb.sheetnames[:5]
        wb.close()
    elif mode == "preview":
        wb = open_ro(path)
        t_open = time.perf_counter() - t1
        ws = wb[wb.sheetnames[0]]
        cols = collections.defaultdict(collections.Counter)
        n = 0
        t2 = time.perf_counter()
        for row in ws.iter_rows(max_row=1000, max_col=lim["max_cols"] + 1, values_only=True):
            n += 1
            for j, v in enumerate(row):
                if v is not None:
                    cols[j][type(v).__name__] += 1
        out.update(open_s=round(t_open, 3), iter_s=round(time.perf_counter() - t2, 3), rows=n, ncols_seen=len(cols),
                   sheets=wb.sheetnames[:5], n_sheets=len(wb.sheetnames))
        wb.close()
    elif mode == "scan":
        wb = open_ro(path)
        t_open = time.perf_counter() - t1
        ws = wb[wb.sheetnames[opt.get("sheet_idx", 0) if isinstance(opt.get("sheet_idx"), int) else 0]]
        rows = cells = 0
        stop = "끝까지"
        t2 = time.perf_counter()
        R, C, N = lim["max_rows"], lim["max_cols"], lim["max_cells"]
        for row in ws.iter_rows(max_row=R + 1, max_col=C + 1, values_only=True):
            rows += 1
            if rows > R:
                if any(v is not None for v in row):
                    stop = f"행 상한 초과({R}) 행{rows}에서 중단"
                break
            if row[C] is not None:
                stop = f"열 상한 초과({C}) 행{rows}에서 중단"
                break
            cells += sum(1 for v in row[:C] if v is not None)
            if cells > N:
                stop = f"셀 상한 초과({N}) 행{rows}에서 중단"
                break
            if rows % 1000 == 0 and time.perf_counter() - t2 > lim["time_limit"]:
                stop = f"시간 초과 행{rows}에서 중단"
                break
        out.update(open_s=round(t_open, 3), iter_s=round(time.perf_counter() - t2, 3), rows=rows, cells=cells, stop=stop, n_sheets=len(wb.sheetnames))
        wb.close()
    elif mode == "scan_unlimited":  # 상한 없이 끝까지 (H-3 추정 비교용)
        wb = open_ro(path)
        t_open = time.perf_counter() - t1
        ws = wb[wb.sheetnames[0]]
        rows = cells = 0
        t2 = time.perf_counter()
        for row in ws.iter_rows(values_only=True):
            rows += 1
            cells += sum(1 for v in row if v is not None)
        out.update(open_s=round(t_open, 3), iter_s=round(time.perf_counter() - t2, 3), rows=rows, cells=cells, n_sheets=len(wb.sheetnames))
        wb.close()
    elif mode == "dump":
        wb = open_ro(path)
        out["sheets"] = wb.sheetnames[:5]
        ws = wb[wb.sheetnames[0]]
        rows = []
        for row in ws.iter_rows(max_row=3, max_col=3, values_only=True):
            rows.append([(v if not isinstance(v, str) else (v[:60] + f"...(len={len(v)})" if len(v) > 60 else v)) for v in row])
        out["rows"] = [[str(x) for x in r] for r in rows]
        wb.close()
    elif mode == "normal":
        wb = load_workbook(path, read_only=False, data_only=True, keep_links=False)
        t_open = time.perf_counter() - t1
        ws = wb[wb.sheetnames[0]]
        rows = cells = 0
        t2 = time.perf_counter()
        for row in ws.iter_rows(values_only=True):
            rows += 1
            cells += sum(1 for v in row if v is not None)
        out.update(open_s=round(t_open, 3), iter_s=round(time.perf_counter() - t2, 3), rows=rows, cells=cells)
    else:
        raise SystemExit("mode?")
    out["total_s"] = round(time.perf_counter() - t1, 3)
    out["cpu_s"] = round(time.process_time() - C0, 3)
    out["maxrss_mb"] = round(rss_mb(), 1)
    out["delta_rss_mb"] = round(rss_mb() - BASE_RSS, 1)
    return out


if __name__ == "__main__":
    mode, path = sys.argv[1], sys.argv[2]
    opt = {}
    for a in sys.argv[3:]:
        k, v = a.split("=", 1)
        opt[k] = int(v) if v.lstrip("-").isdigit() else v
    try:
        res = run(mode, path, opt)
    except BaseException as e:  # noqa: BLE001
        res = {"mode": mode, "file": os.path.basename(path), "error": f"{type(e).__name__}: {str(e)[:200]}", "maxrss_mb": round(rss_mb(), 1),
               "total_s": round(time.perf_counter() - T0, 3), "base_rss_mb": round(BASE_RSS, 1)}
    print(json.dumps(res, ensure_ascii=False))
