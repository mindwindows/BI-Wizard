"""X-27 실행기(컨테이너 안). 사용: python bench.py <mode> <n_concurrent> <reps> <file> [worker opts]
각 rep마다 worker.py를 n개 동시에 띄우고, 20ms 간격으로 cgroup memory.current와 자식 RSS 합을 표본 추출한다."""
import sys, os, subprocess, threading, time, json

mode, n, reps, path = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
extra = sys.argv[5:]
CG = "/sys/fs/cgroup/memory.current" if os.path.exists("/sys/fs/cgroup/memory.current") else "/sys/fs/cgroup/memory/memory.usage_in_bytes"


def vmrss(pid):
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
    except OSError:
        return 0.0
    return 0.0


for rep in range(1, reps + 1):
    peak_cg = peak_sum = 0.0
    stop = False
    procs = []

    def sampler():
        global peak_cg, peak_sum
        while not stop:
            try:
                cg = int(open(CG).read()) / 1048576
            except OSError:
                cg = 0
            s = sum(vmrss(p.pid) for p in procs if p.poll() is None)
            peak_cg = max(peak_cg, cg)
            peak_sum = max(peak_sum, s)
            time.sleep(0.02)

    th = threading.Thread(target=sampler, daemon=True)
    t0 = time.perf_counter()
    for _ in range(n):
        procs.append(subprocess.Popen([sys.executable, "-I", "/work/scripts/worker.py", mode, path, *extra], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
    th.start()
    results = []
    for p in procs:
        o, e = p.communicate()
        wall_p = time.perf_counter() - t0
        try:
            r = json.loads(o.strip().splitlines()[-1])
        except Exception:  # noqa: BLE001
            r = {"error": f"결과 없음 returncode={p.returncode}", "stderr": e[-200:]}
        r["returncode"] = p.returncode
        r["wall_s"] = round(wall_p, 2)
        results.append(r)
    wall = time.perf_counter() - t0
    stop = True
    th.join()
    print(json.dumps({"mode": mode, "file": os.path.basename(path), "n": n, "rep": rep, "wall_s": round(wall, 2), "peak_rss_sum_mb": round(peak_sum, 1),
                      "peak_cgroup_mb": round(peak_cg, 1), "workers": results}, ensure_ascii=False), flush=True)
