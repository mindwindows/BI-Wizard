"""셀 값 종류별로 openpyxl read-only가 돌려주는 값·타입을 확인하는 탐침 (합성 셀 모음).

사용: python values_probe.py <작업폴더>      (xlsxwriter, openpyxl 필요)
출력: 마크다운 표. 설계 문서의 '셀 값 변환 규칙'과 '수식 셀' 절의 근거다.
"""

import os
import sys
from datetime import date, datetime, time

import openpyxl
import xlsxwriter
from openpyxl import load_workbook

work = sys.argv[1]
os.makedirs(work, exist_ok=True)
p1 = os.path.join(work, "zoo_xlsxwriter.xlsx")
p2 = os.path.join(work, "zoo_openpyxl_formula_nocache.xlsx")
p3 = os.path.join(work, "zoo_1904.xlsx")

wb = xlsxwriter.Workbook(p1)
ws = wb.add_worksheet("zoo")
f_date = wb.add_format({"num_format": "yyyy-mm-dd"})
f_pct = wb.add_format({"num_format": "0.0%"})
f_time = wb.add_format({"num_format": "hh:mm"})
cells = {}  # 주소 -> 설명


def put(addr, desc, writer, *a):
    getattr(ws, writer)(addr, *a)
    cells[addr] = desc


put("A1", "정수 5", "write_number", 5)
put("A2", "소수 1.1", "write_number", 1.1)
put("A3", "0.1+0.2 부동소수 잡음(파일에 17자리로 기록)", "write_number", 0.1 + 0.2)
put("A4", "큰 정수 123456789012345678 (double로 저장됨)", "write_number", 123456789012345678)
put("A5", "숫자처럼 보이는 글자 '00012'", "write_string", "00012")
put("A6", "글자 '1,234.50' (쉼표)", "write_string", "1,234.50")
put("A7", "글자 '-' (없음 표기)", "write_string", "-")
put("A8", "빈 글자 ''", "write_string", "")
put("A9", "공백 글자 '  '", "write_string", "  ")
put("A10", "불리언 TRUE", "write_boolean", True)
put("A11", "날짜 2026-03-01", "write_datetime", datetime(2026, 3, 1), f_date)
put("A12", "일시 2026-03-01 13:45", "write_datetime", datetime(2026, 3, 1, 13, 45), f_date)
put("A13", "시간만 13:45", "write_datetime", time(13, 45), f_time)
put("A14", "퍼센트 7.5% (값 0.075)", "write_number", 0.075, f_pct)
put("A15", "수식 =1+1 (캐시 2)", "write_formula", "=1+1", None, 2)
put("A16", "수식 문자열 결과 (캐시 'ab')", "write_formula", '="a"&"b"', None, "ab")
put("A17", "수식 오류 결과 (캐시 #DIV/0!)", "write_formula", "=1/0", None, "#DIV/0!")
put("A18", "수식 불리언 결과 (캐시 TRUE)", "write_formula", "=1=1", None, True)
put("A19", "글자가 '=1+1'로 시작(수식 아님, 글자)", "write_string", "=1+1")
put("A20", "글자 \"=cmd|' /C calc'!A0\" (DDE 모양, 글자)", "write_string", "=cmd|' /C calc'!A0")
put("A21", "글자 '+1+1'", "write_string", "+1+1")
put("A22", "글자 '@SUM(1,1)'", "write_string", "@SUM(1,1)")
put("A23", "글자 '-2+3'", "write_string", "-2+3")
put("A24", "글자에 제어문자 'a\\x01b'", "write_string", "a\x01b")
put("A25", "NFD 한글 '가' (ㄱ+ㅏ)", "write_string", "가")
put("A26", "아주 긴 글자 40,000자(엑셀 셀 상한 32,767자 초과 -> 잘림)", "write_string", "가" * 40000)
put("A27", "수식 셀(캐시 없음 모양 흉내, 값 0)", "write_formula", "=SUM(A1:A2)")
ws.merge_range("C1:D2", "병합 셀(C1:D2)", None)
cells["C1"] = "병합 셀의 왼쪽 위"
cells["D2"] = "병합 셀의 나머지(값 없음)"
ws.set_row(29, None, None, {"hidden": True})
ws.write("A30", "숨긴 행의 값")
cells["A30"] = "숨긴 행의 값(행 숨김)"
ws.set_column("F:F", None, None, {"hidden": True})
ws.write("F1", "숨긴 열의 값")
cells["F1"] = "숨긴 열의 값(열 숨김)"
ws.write_rich_string("G1", "굵게", wb.add_format({"bold": True}), "보통")
cells["G1"] = "서식 있는 글자(rich text)"
wb.close()

# openpyxl로 만든 수식(캐시 없음)
wb2 = openpyxl.Workbook()
w = wb2.active
w["A1"] = 3
w["A2"] = 4
w["A3"] = "=A1+A2"
wb2.save(p2)

# 1904 날짜 체계
wb3 = xlsxwriter.Workbook(p3, {"date_1904": True})
w3 = wb3.add_worksheet()
w3.write_datetime("A1", datetime(2026, 3, 1), wb3.add_format({"num_format": "yyyy-mm-dd"}))
wb3.close()


def dump(path, cell_desc, data_only):
    wbr = load_workbook(path, read_only=True, data_only=data_only, keep_links=False)
    wsr = wbr[wbr.sheetnames[0]]
    got = {}
    from openpyxl.utils import get_column_letter

    for r, row in enumerate(wsr.iter_rows(), start=1):
        for k, c in enumerate(row, start=1):  # 빈 칸은 EmptyCell(coordinate 없음)이라 위치로 주소를 만든다
            addr = f"{get_column_letter(k)}{r}"
            if getattr(c, "value", None) is not None or addr in cell_desc:
                got[addr] = (getattr(c, "data_type", "empty"), getattr(c, "value", None))
    wbr.close()
    return got


def show(v):
    s = repr(v)
    return s if len(s) < 40 else s[:37] + "..."


d_true = dump(p1, cells, True)
d_false = dump(p1, cells, False)
print("| 셀 | 설명 | data_only=True (타입, 값) | data_only=False (타입, 값) |")
print("| --- | --- | --- | --- |")
for addr in sorted(cells, key=lambda a: (int("".join(ch for ch in a if ch.isdigit())), a)):
    t = d_true.get(addr, ("-", None))
    f = d_false.get(addr, ("-", None))
    print(f"| {addr} | {cells[addr]} | {t[0]} {show(t[1])} | {f[0]} {show(f[1])} |")
n_true = dump(p2, {"A3": ""}, True)["A3"]
n_false = dump(p2, {"A3": ""}, False)["A3"]
print(f"\nopenpyxl이 저장한 수식 파일(캐시 없음) A3: data_only=True -> {n_true}, data_only=False -> {n_false}")
d1904 = dump(p3, {"A1": ""}, True)["A1"]
print(f"1904 날짜 체계 파일 A1 (2026-03-01로 기록): data_only=True -> {d1904}")
print(f"\nopenpyxl {openpyxl.__version__}, 실행 Python {sys.version.split()[0]}")
