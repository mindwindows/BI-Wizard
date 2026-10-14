"""사전 검사를 건너뛰고(= openpyxl만으로) 변조 파일을 열었을 때의 동작 측정. 사용: python bench_tamper.py <tamper폴더> <결과.jsonl> <site폴더>

항상 docker(--memory=1g --memory-swap=1g, 120초 timeout)에서 실행한다: 폭탄이 호스트 메모리를 쓰지 않게 하고 OOM kill(종료 코드 137)을 관찰하기 위해서다.
같은 파일을 사전 검사(precheck.py)가 거부하는지는 run_precheck.py 표를 본다.
"""

import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
IMAGE = "bi-wizard-backend:local"
XML_ATTACKS = {"xxe_external_entity_sheet", "billion_laughs_sheet", "dtd_in_sst", "dtd_in_content_types"}


def run(folder, site, name, defused):
    env = ["-e", "PYTHONPATH=/site"] + ([] if defused else ["-e", "OPENPYXL_DEFUSEDXML=False"])
    cmd = ["docker", "run", "--rm", "--memory=1g", "--memory-swap=1g", *env,
           "-v", f"{site}:/site:ro", "-v", f"{HERE}:/exp:ro", "-v", f"{folder}:/samples:ro",
           "--entrypoint", "timeout", IMAGE, "120", "python", "/exp/worker.py", "scan_ro", f"/samples/{name}.xlsx"]
    t0 = time.perf_counter()
    p = subprocess.run(cmd, capture_output=True, text=True)
    wall = time.perf_counter() - t0
    lines = p.stdout.strip().splitlines()
    try:
        res = json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError):
        res = {"status": "no-json"}
    verdict = {0: "정상 종료", 124: "120초 timeout", 137: "OOM kill(137)"}.get(p.returncode, f"rc={p.returncode}")
    return {"file": name, "defused": defused, "rc": p.returncode, "verdict": verdict, "wall_s": round(wall, 1),
            "status": res.get("status"), "max_rss_mb": res.get("max_rss_mb"), "rows": res.get("rows")}


def main():
    folder, out, site = sys.argv[1:4]
    names = sorted(f[:-5] for f in os.listdir(folder) if f.endswith(".xlsx") and not f.startswith("_"))
    with open(out, "a") as fh:
        for name in names:
            for defused in ([True, False] if name in XML_ATTACKS else [True]):
                r = run(folder, site, name, defused)
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                fh.flush()
                print(r, flush=True)


if __name__ == "__main__":
    main()
