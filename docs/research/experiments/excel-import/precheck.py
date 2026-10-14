"""xlsx 업로드 사전 검사 시제품 (설계 검증용, 제품 코드 아님).

zip 중앙 디렉터리와 앞부분 몇 KB만 읽는다(항목을 풀지 않는다). openpyxl을 열기 전에 호출한다.
반환: Findings(reasons=[(코드, 한국어 사유)], info=dict). reasons가 비어 있으면 통과.

한도는 Limits에 모았다. 값은 5 MiB 업로드 기준이며 `upload_limit`에 비례한다(문서의 표 참조).
가정: Python 3.12 zipfile은 선언된 file_size까지만 읽고 CRC 불일치를 BadZipFile로 알린다.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field

import defusedxml.ElementTree as DET
from defusedxml import DefusedXmlException

OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ZIP_MAGIC = b"PK\x03\x04"
HEAD_BYTES = 4096
DTD_RE = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)


@dataclass(frozen=True)
class Limits:
    upload_limit: int = 5 * 1024 * 1024  # 바이트(APP_UPLOAD_MAX_MB)
    unc_total_factor: int = 15  # 해제 합계 <= 업로드 상한 x 15 (03c/X-27 후보)
    max_ratio: float = 50.0  # 합계 압축률 상한(정상 최대 9.3, 변조 최소 339)
    max_entry_unc: int = 100 * 1024 * 1024  # 항목 하나의 해제 크기
    max_entries: int = 1000
    max_sheets: int = 30
    max_nodim_sheet_unc: int = 20 * 1024 * 1024  # <dimension> 없는 시트는 열 때 전부 파싱되므로 해제 크기를 더 낮게 제한
    max_small_xml: int = 2 * 1024 * 1024  # [Content_Types].xml, workbook.xml
    reject_external_links: bool = True  # 정책 선택: 거부(true) 또는 경고만(false)

    @property
    def max_unc_total(self) -> int:
        return self.upload_limit * self.unc_total_factor


@dataclass
class Findings:
    reasons: list[tuple[str, str]] = field(default_factory=list)
    info: dict = field(default_factory=dict)

    def add(self, code: str, message: str) -> None:
        self.reasons.append((code, message))

    @property
    def ok(self) -> bool:
        return not self.reasons

    @property
    def codes(self) -> list[str]:
        return [c for c, _ in self.reasons]


def precheck(path_or_file, size: int, lim: Limits = Limits()) -> Findings:
    f = Findings()
    f.info["size"] = size
    if size > lim.upload_limit:
        f.add("TOO_LARGE", "파일이 업로드 상한보다 큽니다.")
        return f
    if size == 0:
        f.add("EMPTY_FILE", "빈 파일입니다.")
        return f
    try:
        if hasattr(path_or_file, "read"):
            path_or_file.seek(0)
            head = path_or_file.read(8)
            path_or_file.seek(0)
        else:
            with open(path_or_file, "rb") as fh:
                head = fh.read(8)
    except OSError:
        f.add("UNREADABLE", "파일을 읽을 수 없습니다.")
        return f
    if head[:8] == OLE2_MAGIC:
        f.add("OLE2", "암호가 걸린 파일이거나 예전 형식(.xls)입니다. 암호를 풀고 .xlsx로 저장해 주세요.")
        return f
    if head[:4] != ZIP_MAGIC:
        f.add("NOT_ZIP", "엑셀(.xlsx) 파일이 아닙니다.")
        return f
    try:
        zf = zipfile.ZipFile(path_or_file)
    except (zipfile.BadZipFile, OSError, NotImplementedError):
        f.add("BAD_ZIP", "파일이 손상되었거나 엑셀(.xlsx) 파일이 아닙니다.")
        return f
    with zf:
        _check_zip(zf, f, lim)
    return f


def _bad_name(name: str) -> bool:
    n = name.replace("\\", "/")
    return (
        n.startswith("/")
        or "\\" in name
        or ":" in name
        or any(seg == ".." for seg in n.split("/"))
        or any(ord(c) < 32 for c in name)
    )


def _check_zip(zf: zipfile.ZipFile, f: Findings, lim: Limits) -> None:
    infos = zf.infolist()
    names = [i.filename for i in infos]
    f.info["entries"] = len(infos)
    if len(infos) > lim.max_entries:
        f.add("TOO_MANY_ENTRIES", "파일 구조가 비정상적으로 큽니다.")
        return  # 이후 검사는 항목 수에 비례하므로 중단
    unc = sum(i.file_size for i in infos)
    comp = sum(i.compress_size for i in infos)
    f.info.update(unc_total=unc, comp_total=comp, ratio=round(unc / max(comp, 1), 1))
    if unc > lim.max_unc_total:
        f.add("UNC_TOTAL", "파일을 풀었을 때 크기가 허용 범위를 넘습니다.")
    if unc / max(comp, 1) > lim.max_ratio:
        f.add("RATIO", "압축 비율이 비정상적으로 높습니다.")
    if any(i.file_size > lim.max_entry_unc for i in infos):
        f.add("ENTRY_UNC", "파일 안의 한 부분이 허용 크기를 넘습니다.")
    if len(set(names)) != len(names):
        f.add("DUP_NAMES", "파일 구조가 비정상입니다(중복 항목).")
    if any(_bad_name(n) for n in names):
        f.add("BAD_NAMES", "파일 안에 허용되지 않는 경로가 있습니다.")
    if any(i.flag_bits & 0x1 for i in infos):
        f.add("ENCRYPTED_ENTRY", "암호화된 항목이 있습니다.")
    if any(i.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED) for i in infos):
        f.add("COMPRESSION", "지원하지 않는 압축 방식입니다.")
    lower = [n.lower() for n in names]
    if any(n.endswith("vbaproject.bin") for n in lower):
        f.add("MACRO", "매크로가 들어 있는 파일은 가져올 수 없습니다. 매크로 없는 .xlsx로 저장해 주세요.")
    if "xl/workbook.bin" in lower:
        f.add("XLSB", ".xlsb 형식은 지원하지 않습니다. .xlsx로 저장해 주세요.")
    for req in ("[Content_Types].xml", "xl/workbook.xml"):
        if req not in names:
            f.add("NOT_XLSX", "엑셀(.xlsx) 파일이 아닙니다.")
            return
    if any(n.startswith(("xl/embeddings/", "xl/activex/", "xl/ctrlprops/")) for n in lower):
        f.add("EMBEDDED", "개체(삽입된 파일·컨트롤)가 들어 있는 파일은 가져올 수 없습니다.")
    if any(n.startswith("xl/externallinks/") for n in lower):
        if lim.reject_external_links:
            f.add("EXTERNAL_LINK", "다른 파일을 가리키는 연결(외부 링크)이 있습니다.")
        else:  # 경고만: openpyxl은 keep_links=False면 따라가지 않는다
            f.info.setdefault("warnings", []).append("EXTERNAL_LINK")
    # 중첩 zip: 규정된 XML/관계 파일이 아닌 항목이 zip 시그니처로 시작하면 거부
    for i in infos:
        if i.file_size >= 4 and not i.filename.lower().endswith((".xml", ".rels", ".vml")) and not i.is_dir():
            with zf.open(i) as fh:
                if fh.read(4) == ZIP_MAGIC:
                    f.add("NESTED_ZIP", "파일 안에 다른 압축 파일이 들어 있습니다.")
                    break
    # 앞부분 읽기: XML 항목마다 DTD/ENTITY 선언 검색. 선언 크기를 속인 항목은 여기서 BadZipFile.
    for i in infos:
        if i.filename.lower().endswith((".xml", ".rels")) and i.file_size:
            try:
                with zf.open(i) as fh:
                    head = fh.read(HEAD_BYTES)
            except (zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError, EOFError):
                f.add("BAD_ENTRY", "파일 안의 항목이 손상되었습니다.")
                break
            if head[:2] in (b"\xff\xfe", b"\xfe\xff"):
                f.add("UTF16_XML", "지원하지 않는 문자 인코딩의 XML이 있습니다.")
                break
            if DTD_RE.search(head):
                f.add("DTD", "허용되지 않는 XML 선언(DTD)이 있습니다.")
                break
            if (
                i.filename.startswith("xl/worksheets/sheet")
                and b"<dimension" not in head
                and i.file_size > lim.max_nodim_sheet_unc
            ):
                f.add("NO_DIMENSION_BIG", "시트 정보가 비정상입니다(범위 정보 없이 큰 시트).")
                break
    ct = zf.getinfo("[Content_Types].xml")
    wb = zf.getinfo("xl/workbook.xml")
    if ct.file_size > lim.max_small_xml or wb.file_size > lim.max_small_xml:
        f.add("SMALL_XML_BIG", "파일 구조가 비정상입니다(워크북 정의가 너무 큼).")
        return
    try:
        cts = zf.read("[Content_Types].xml")
        if b"macroEnabled" in cts:
            f.add("MACRO_TYPE", "매크로가 가능한 형식(.xlsm)입니다. .xlsx로 저장해 주세요.")
        if b"spreadsheetml.sheet.main+xml" not in cts:
            f.add("NOT_XLSX", "엑셀(.xlsx) 파일이 아닙니다.")
        root = DET.fromstring(zf.read("xl/workbook.xml"), forbid_dtd=True)
    except (DefusedXmlException, zipfile.BadZipFile, DET.ParseError, ValueError, OSError):
        f.add("BAD_WORKBOOK", "워크북 정의를 읽을 수 없습니다.")
        return
    sheets = [e for e in root.iter() if e.tag.endswith("}sheet")]
    f.info["sheets"] = len(sheets)
    f.info["sheet_names"] = [e.get("name") for e in sheets][:30]
    if len(sheets) > lim.max_sheets:
        f.add("TOO_MANY_SHEETS", f"시트가 너무 많습니다(최대 {lim.max_sheets}개).")
