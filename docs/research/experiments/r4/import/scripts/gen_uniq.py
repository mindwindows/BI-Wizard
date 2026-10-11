import sys, os, random, json
sys.path.insert(0, "/home/user/BI-Wizard/_workspace/gate3/experiments/r4/import/scripts")
import gen_big as g
F = "/home/user/BI-Wizard/_workspace/gate3/experiments/r4/import/files"
# 최악 사례: 모든 셀이 서로 다른 짧은 문자열(영숫자 5자). 공유 문자열 개수가 파일 크기 대비 가장 많은 쪽.
r = random.Random(5)
def build(rows, path):
    b = g.Book(); sh = g.Sheet("데이터"); b.sheets.append(sh)
    for i in range(rows):
        b.add_row(sh, ["".join(r.choice(g.ALNUM) for _ in range(5)) for _ in range(100)])
    b.save(path)
    return os.path.getsize(path), len(b.sst)
rows = 12000
for it in range(4):
    sz, n = build(rows, f"{F}/uniq_short.xlsx")
    if abs(sz - 10 * 1048576) / (10 * 1048576) < 0.03: break
    rows = int(rows * 10 * 1048576 / sz)
print(json.dumps({"rows": rows, "cols": 100, "bytes": sz, "unique_strings": n}))
