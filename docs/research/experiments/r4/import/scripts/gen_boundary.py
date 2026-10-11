"""행·열·셀 경계 시험 파일 생성 (숫자만, 헤더 없이 1행부터 데이터). 사용: python gen_boundary.py <out_dir>"""
import sys, os, random
sys.path.insert(0, "/home/user/BI-Wizard/_workspace/gate3/experiments/r4/import/scripts")
import gen_big as g
out = sys.argv[1]
r = random.Random(11)
def mk(name, nrows, ncols):
    b = g.Book(); sh = g.Sheet("데이터"); b.sheets.append(sh)
    for i in range(nrows):
        b.add_row(sh, [r.randint(0, 99999) for _ in range(ncols)])
    b.save(f"{out}/{name}.xlsx")
    print(name, nrows, ncols, os.path.getsize(f"{out}/{name}.xlsx"))
mk("b_rows_100000_c5", 100000, 5)
mk("b_rows_100001_c5", 100001, 5)
mk("b_rows_300000_c3", 300000, 3)
mk("b_cols_100_r1000", 1000, 100)
mk("b_cols_101_r1000", 1000, 101)
mk("b_cells_2000000_r20000_c100", 20000, 100)
mk("b_cells_2000100_r20001_c100", 20001, 100)
