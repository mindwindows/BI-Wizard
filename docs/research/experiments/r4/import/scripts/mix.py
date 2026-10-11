import subprocess, sys, time, json
w = "/work/scripts/worker_t.py"
b = subprocess.Popen([sys.executable, "-I", w, "scan", "/work/files/tamper/bomb_rows_1gb.xlsx"], stdout=subprocess.PIPE, text=True)
time.sleep(8)
t0 = time.time()
l = subprocess.Popen([sys.executable, "-I", w, "scan", "/work/files/tall_10mb.xlsx"], stdout=subprocess.PIPE, text=True)
lo, _ = l.communicate()
t_l = time.time() - t0
bo, _ = b.communicate()
print("legit rc", l.returncode, "legit sec", round(t_l, 1), (lo.strip().splitlines() or ["(출력 없음)"])[-1][:200])
print("bomb rc", b.returncode, (bo.strip().splitlines() or ["(출력 없음)"])[-1][:100])
