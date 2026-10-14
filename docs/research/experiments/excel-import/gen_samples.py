"""엑셀 가져오기 설계 실측용 합성 xlsx 생성기 (xlsxwriter 사용, 개발 전용, 저장소 requirements 아님).

사용: python gen_samples.py <출력폴더> [이름 ...]      (이름 생략 시 전부)
모든 데이터는 난수(seed 고정)로 만든 합성값이다. 실제 회사 파일이 아니다.
각 모양은 목표 파일 크기(기본 5.0 MiB)에 맞춰 행 수를 보정한다(2단계: 작은 시험 -> 선형 보정 -> 재생성).

모양
- m_col_36 : 월 = 열(업무 모양). 제목 행(병합)·빈 행·머리글(진짜 날짜 셀 36개)·항목 행·소계 수식 행·빈 행 반복.
- m_col_12 : 같은 모양, 월 12개(행이 많아진다).
- m_col_text: 머리글이 글자 "1월".."12월", 연도는 시트 이름 "2026"에만 있음(연도 정보 위치 시험).
- table_12 : 이미 "월 = 행" 표 모양(12열 긴 표). 전치 없이 그대로 적재하는 경로의 기준.
- worst_cells: 100열 x 20,000행 = 2,000,000셀, 0~99 정수만(셀 수 상한 근처). worst_cells_flat: 0~1만(더 잘 압축됨).
- worst_sst : 100열, 모든 셀이 서로 다른 5자 영숫자(공유 문자열 최대).
"""

import os
import random
import string
import sys
from datetime import date

import xlsxwriter

SEED = 20261014
TARGET_MIB = 4.9  # 5 MiB 상한 바로 아래(5MB 이하 요구에 맞춤)
WORDS_A = ["전기", "수도", "가스", "난방", "냉방", "조명", "환기", "청소", "보안", "주차", "엘리베이터", "소방"]
WORDS_B = ["A동", "B동", "C동", "본관", "별관", "지하", "옥상", "로비", "사무실", "회의실"]
WORDS_C = ["사용량", "요금", "단가", "비용", "횟수", "시간", "건수"]
UNITS = ["kWh", "m3", "원", "건", "시간", "%"]


def month_starts(n, start_year=2024):
    out = []
    y, m = start_year, 1
    for _ in range(n):
        out.append(date(y, m, 1))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def item_name(rng, i):
    return f"{rng.choice(WORDS_A)} {rng.choice(WORDS_B)} {rng.choice(WORDS_C)} {i:05d}"


def number(rng):
    r = rng.random()
    if r < 0.04:
        return None  # 빈 칸
    if r < 0.05:
        return "-"  # 흔한 "없음" 표기(글자)
    return round(rng.uniform(0, 100000), 2)


def build_month_cols(path, n_items, n_months, text_headers=False):
    """월 = 열 모양. 항목 n_items개(소계/빈 행 별도)."""
    rng = random.Random(SEED)
    wb = xlsxwriter.Workbook(path, {"default_date_format": "yyyy-mm-dd"})
    sheet_name = "2026" if text_headers else "팀실적"
    ws = wb.add_worksheet(sheet_name)
    f_title = wb.add_format({"bold": True, "font_size": 14})
    f_head = wb.add_format({"bold": True, "bg_color": "#DDDDDD"})
    f_date = wb.add_format({"bold": True, "bg_color": "#DDDDDD", "num_format": 'yyyy"년" m"월"'})
    f_num = wb.add_format({"num_format": "#,##0.00"})
    ws.merge_range(0, 0, 0, 4, "○○팀 월별 실적 (합성 데이터)", f_title)
    head_row = 2
    ws.write(head_row, 0, "항목", f_head)
    ws.write(head_row, 1, "구분", f_head)
    ws.write(head_row, 2, "단위", f_head)
    months = month_starts(n_months)
    for j, d in enumerate(months):
        if text_headers:
            ws.write(head_row, 3 + j, f"{d.month}월", f_head)
        else:
            ws.write_datetime(head_row, 3 + j, __import__("datetime").datetime(d.year, d.month, d.day), f_date)
    r = head_row + 1
    block, block_start, sums = 0, r, 0
    for i in range(n_items):
        ws.write(r, 0, item_name(rng, i))
        ws.write(r, 1, "원본" if rng.random() < 0.8 else "계산")
        ws.write(r, 2, rng.choice(UNITS))
        for j in range(n_months):
            v = number(rng)
            if v is None:
                continue
            if isinstance(v, str):
                ws.write_string(r, 3 + j, v)
            else:
                ws.write_number(r, 3 + j, v, f_num)
        r += 1
        block += 1
        if block == 20:  # 20항목마다 소계 수식 행 + 빈 행
            ws.write(r, 0, "소계")
            for j in range(n_months):
                col = xlsxwriter.utility.xl_col_to_name(3 + j)
                ws.write_formula(r, 3 + j, f"=SUM({col}{block_start + 1}:{col}{r})", f_num, 1000000.0)
                sums += 1
            r += 2
            block, block_start = 0, r
    ws.write(r, 0, "합계")
    for j in range(n_months):
        ws.write_formula(r, 3 + j, "=0", f_num, 0)
    wb.close()


def build_table(path, n_rows, n_cols=12):
    """이미 월 = 행인 긴 표."""
    rng = random.Random(SEED)
    wb = xlsxwriter.Workbook(path, {"default_date_format": "yyyy-mm-dd"})
    ws = wb.add_worksheet("데이터")
    ws.write_row(0, 0, ["기준월", "팀", "비고"] + [f"항목{k}" for k in range(1, n_cols - 2)])
    months = month_starts(120)
    for i in range(n_rows):
        d = months[i % 120]
        ws.write_datetime(i + 1, 0, __import__("datetime").datetime(d.year, d.month, 1))
        ws.write(i + 1, 1, f"팀{(i // 120) % 50:02d}")
        ws.write(i + 1, 2, item_name(rng, i % 977))
        for k in range(n_cols - 3):
            ws.write_number(i + 1, 3 + k, round(rng.uniform(0, 100000), 2))
    wb.close()


def build_worst_cells(path, n_rows, n_cols=100, hi=99):
    rng = random.Random(SEED)
    wb = xlsxwriter.Workbook(path, {"constant_memory": True})
    ws = wb.add_worksheet("데이터")
    ws.write_row(0, 0, [f"c{k}" for k in range(n_cols)])
    for i in range(n_rows):
        ws.write_row(i + 1, 0, [rng.randint(0, hi) for _ in range(n_cols)])
    wb.close()


def build_worst_sst(path, n_rows, n_cols=100):
    rng = random.Random(SEED)
    alphabet = string.ascii_letters + string.digits
    wb = xlsxwriter.Workbook(path)  # 기본 모드: 공유 문자열 사용
    ws = wb.add_worksheet("데이터")
    ws.write_row(0, 0, [f"c{k}" for k in range(n_cols)])
    for i in range(n_rows):
        ws.write_row(i + 1, 0, ["".join(rng.choices(alphabet, k=5)) for _ in range(n_cols)])
    wb.close()


SHAPES = {
    "m_col_36": lambda p, n: build_month_cols(p, n, 36),
    "m_col_12": lambda p, n: build_month_cols(p, n, 12),
    "m_col_text": lambda p, n: build_month_cols(p, n, 12, text_headers=True),
    "table_12": lambda p, n: build_table(p, n, 12),
    "worst_cells": lambda p, n: build_worst_cells(p, n),
    "worst_cells_flat": lambda p, n: build_worst_cells(p, n, hi=1),
    "worst_sst": lambda p, n: build_worst_sst(p, n),
}
PROBE_N = {"m_col_36": 1500, "m_col_12": 3000, "m_col_text": 3000, "table_12": 5000, "worst_cells": 2000, "worst_cells_flat": 2000, "worst_sst": 2000}
# 고정 행 수(보정하지 않음): 셀 수 상한(2,000,000)을 맞추기 위해 20,000행
FIXED = {"worst_cells": 20000, "worst_cells_flat": 20000}


def build_calibrated(name, out_dir, target_mib):
    path = os.path.join(out_dir, f"{name}.xlsx")
    if name in FIXED:
        SHAPES[name](path, FIXED[name])
        return path, FIXED[name]
    n0 = PROBE_N[name]
    SHAPES[name](path, n0)
    size0 = os.path.getsize(path)
    n1 = max(10, int(n0 * target_mib * 1048576 / size0))
    SHAPES[name](path, n1)
    size1 = os.path.getsize(path)
    n2 = max(10, int(n1 * target_mib * 1048576 / size1))
    if abs(n2 - n1) / n1 > 0.03:
        SHAPES[name](path, n2)
        n1 = n2
    return path, n1


if __name__ == "__main__":
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    want = sys.argv[2:] or list(SHAPES)
    for nm in want:
        p, n = build_calibrated(nm, out, TARGET_MIB)
        print(f"{nm}: items/rows={n} size={os.path.getsize(p) / 1048576:.2f} MiB -> {p}")
