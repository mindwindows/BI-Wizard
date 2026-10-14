"""측정 행렬 실행기. 사용: python bench.py <host|docker> <샘플폴더> <결과.jsonl> [site폴더]

host  : 현재 python(임시 venv)으로 worker.py를 자식 프로세스로 실행
docker: bi-wizard-backend:local 이미지(Python 3.12.15)를 --memory=1g --memory-swap=1g 로 실행하고
        pip install --target 으로 만든 site 폴더와 이 폴더·샘플 폴더를 읽기 전용으로 마운트(이미지는 수정하지 않음)
각 항목을 3회 반복해 한 줄씩 JSON으로 저장한다. 종료 코드 137 = OOM kill.
"""

import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPEAT = 3
IMAGE = "bi-wizard-backend:local"

# (파일, 모드, 인수, 환경변수)
MATRIX = [
    ("m_col_36.xlsx", "baseline", [], {}),
    ("m_col_36.xlsx", "precheck", [], {}),
    ("m_col_36.xlsx", "open_ro", [], {}),
    ("m_col_36.xlsx", "scan_ro", [], {}),
    ("m_col_36.xlsx", "scan_ro", [], {"OPENPYXL_DEFUSEDXML": "False"}),
    ("m_col_36.xlsx", "open_normal", [], {}),
    ("m_col_36.xlsx", "scan_formula", [], {}),
    ("m_col_36.xlsx", "e2e_months", ["item_cap=0"], {}),
    ("m_col_36.xlsx", "e2e_months", ["item_cap=0"], {"OPENPYXL_DEFUSEDXML": "False"}),
    ("m_col_36.xlsx", "e2e_months", ["item_cap=100"], {}),
    ("m_col_12.xlsx", "open_ro", [], {}),
    ("m_col_12.xlsx", "scan_ro", [], {}),
    ("m_col_12.xlsx", "open_normal", [], {}),
    ("m_col_12.xlsx", "scan_formula", [], {}),
    ("m_col_12.xlsx", "e2e_months", ["item_cap=0"], {}),
    ("m_col_12.xlsx", "e2e_months", ["item_cap=100"], {}),
    ("m_col_text.xlsx", "e2e_months", ["item_cap=100"], {}),
    ("m_col_text.xlsx", "e2e_months", ["item_cap=0"], {}),
    ("table_12.xlsx", "open_ro", [], {}),
    ("table_12.xlsx", "scan_ro", [], {}),
    ("table_12.xlsx", "open_normal", [], {}),
    ("table_12.xlsx", "e2e_table", [], {}),
    ("worst_cells_flat.xlsx", "open_ro", [], {}),
    ("worst_cells_flat.xlsx", "scan_ro", [], {}),
    ("worst_cells_flat.xlsx", "open_normal", [], {}),
    ("worst_sst.xlsx", "open_ro", [], {}),
    ("worst_sst.xlsx", "scan_ro", [], {}),
    ("worst_sst.xlsx", "scan_ro", [], {"OPENPYXL_DEFUSEDXML": "False"}),
    ("worst_sst.xlsx", "open_normal", [], {}),
    ("worst_sst.xlsx", "e2e_months", ["item_cap=100"], {}),
]


def run_one(runner, samples, site, fname, mode, args, env):
    if runner == "host":
        cmd = [sys.executable, os.path.join(HERE, "worker.py"), mode, os.path.join(samples, fname), *args]
        child_env = {**os.environ, **env}
    else:
        cmd = ["docker", "run", "--rm", "--memory=1g", "--memory-swap=1g", "-e", "PYTHONPATH=/site",
               *sum((["-e", f"{k}={v}"] for k, v in env.items()), []),
               "-v", f"{site}:/site:ro", "-v", f"{HERE}:/exp:ro", "-v", f"{samples}:/samples:ro",
               "--entrypoint", "python", IMAGE, "/exp/worker.py", mode, f"/samples/{fname}", *args]
        child_env = None
    t0 = time.perf_counter()
    p = subprocess.run(cmd, capture_output=True, text=True, env=child_env)
    wall = time.perf_counter() - t0
    line = p.stdout.strip().splitlines()[-1] if p.stdout.strip() else ""
    try:
        res = json.loads(line)
    except json.JSONDecodeError:
        res = {"mode": mode, "file": fname, "status": f"no-json rc={p.returncode}", "stderr": p.stderr[-200:]}
    res.update(rc=p.returncode, wall_s=round(wall, 2), runner=runner, env=env, args=args)
    return res


def main():
    runner, samples, out_path = sys.argv[1:4]
    site = sys.argv[4] if len(sys.argv) > 4 else ""
    with open(out_path, "a") as fh:
        for fname, mode, args, env in MATRIX:
            reps = 1 if mode == "baseline" else REPEAT
            for _ in range(reps):
                res = run_one(runner, samples, site, fname, mode, args, env)
                fh.write(json.dumps(res, ensure_ascii=False) + "\n")
                fh.flush()
                print(fname, mode, args, env, res.get("status"), res.get("total_s"), res.get("max_rss_mb"), res.get("rc"), flush=True)


if __name__ == "__main__":
    main()
