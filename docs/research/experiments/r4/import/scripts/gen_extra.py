import sys, re, zipfile, os
sys.path.insert(0, "/home/user/BI-Wizard/_workspace/gate3/experiments/r4/import/scripts")
import gen_big as g
F = "/home/user/BI-Wizard/_workspace/gate3/experiments/r4/import/files"
# 1) 정상 파일에서 <dimension> 요소만 제거한 변형(일부 생성기가 dimension을 쓰지 않음)
for m in (5, 10, 20):
    src, dst = f"{F}/tall_{m}mb.xlsx", f"{F}/nodim_tall_{m}mb.xlsx"
    with zipfile.ZipFile(src) as zi, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zo:
        for i in zi.infolist():
            d = zi.read(i.filename)
            if i.filename == "xl/worksheets/sheet1.xml":
                d2 = re.sub(rb"<dimension [^>]*/>", b"", d, count=1)
                assert d2 != d
                d = d2
            zo.writestr(i.filename, d)
    print(dst, os.path.getsize(dst))
# 2) 거짓 dimension(A1:XFD1048576) + 실제 행 20,000개
b = g.Book(); sh = g.Sheet("데이터"); b.sheets.append(sh)
for i in range(20000):
    b.add_row(sh, [i, i * 2])
b.save(f"{F}/tamper/dim_false_20000rows.xlsx")
with zipfile.ZipFile(f"{F}/tamper/dim_false_20000rows.xlsx") as zi:
    data = {n: zi.read(n) for n in zi.namelist()}
data["xl/worksheets/sheet1.xml"] = re.sub(rb'<dimension ref="[^"]*"/>', b'<dimension ref="A1:XFD1048576"/>', data["xl/worksheets/sheet1.xml"])
with zipfile.ZipFile(f"{F}/tamper/dim_false_20000rows.xlsx", "w", zipfile.ZIP_DEFLATED) as zo:
    for n, d in data.items():
        zo.writestr(n, d)
# 3) 거짓 dimension이 작은 경우(A1:B2인데 실제 행 20,000개) — 상한 없이 쓰면 데이터가 잘린다
data["xl/worksheets/sheet1.xml"] = re.sub(rb'<dimension ref="[^"]*"/>', b'<dimension ref="A1:B2"/>', data["xl/worksheets/sheet1.xml"])
with zipfile.ZipFile(f"{F}/tamper/dim_small_20000rows.xlsx", "w", zipfile.ZIP_DEFLATED) as zo:
    for n, d in data.items():
        zo.writestr(n, d)
print("ok")
