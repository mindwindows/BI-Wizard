"""업로드 수신 방식 비교 측정: 멀티파트 UploadFile(python-multipart) vs 원본 본문(octet-stream) 스트리밍.

사용: python upload_probe.py <작업폴더>        (임시 venv에 fastapi, uvicorn, httpx, python-multipart 필요 -> bk-venv)
시나리오마다 uvicorn 서버를 새로 띄워 서버 프로세스의 최대 RSS(/proc/self/status VmHWM)를 읽는다.
- up_5mb      : 4.9 MiB 파일을 멀티파트로(UploadFile). SpooledTemporaryFile이 디스크로 넘어갔는지(_rolled) 확인
- raw_5mb     : 같은 파일을 application/octet-stream 본문으로, request.stream()을 상한 검사하며 BytesIO에 모음
- raw_7mb_cl  : 7 MiB 본문 + Content-Length -> 읽기 전에 413 (상한 5 MiB + 여유 1 MiB 초과)
- raw_chunked : 길이를 모르는 청크 전송 64 MiB -> 상한(5 MiB + 1 MiB 여유)에서 중단하고 413
- up_64mb     : 멀티파트 64 MiB. 앱에는 상한 검사가 없다(프록시 몫임을 보이기 위한 대조)
- + RequestBodyLimitMiddleware: starlette.middleware.body_limit(상한 + 1MiB)을 켠 뒤 64 MiB / 5 MiB 멀티파트
"""

import os
import subprocess
import sys
import time

import httpx

PORT = 18765
LIMIT = 5 * 1024 * 1024
SERVER = r'''
import os, sys
from fastapi import FastAPI, Request, UploadFile
from fastapi.responses import JSONResponse
import io
app = FastAPI()
LIMIT = 5 * 1024 * 1024
if os.environ.get("MW") == "1":  # Starlette 내장 본문 상한 미들웨어(상한 + 1MiB 여유)
    from starlette.middleware.body_limit import RequestBodyLimitMiddleware
    app.add_middleware(RequestBodyLimitMiddleware, max_body_size=LIMIT + 1048576)

def hwm():
    for line in open("/proc/self/status"):
        if line.startswith("VmHWM"):
            return int(line.split()[1]) / 1024

@app.post("/up")
async def up(file: UploadFile):
    data = await file.read()
    return {"size": len(data), "rolled_to_disk": getattr(file.file, "_rolled", None), "name": file.filename}

@app.post("/raw")
async def raw(request: Request):
    cl = request.headers.get("content-length")
    if cl and int(cl) > LIMIT + 1048576:
        return JSONResponse({"code": "PAYLOAD_TOO_LARGE"}, status_code=413)
    buf = io.BytesIO()
    async for chunk in request.stream():
        buf.write(chunk)
        if buf.tell() > LIMIT + 1048576:
            return JSONResponse({"code": "PAYLOAD_TOO_LARGE", "read": buf.tell()}, status_code=413)
    return {"size": buf.tell()}

@app.get("/hwm")
def get_hwm():
    return {"vmhwm_mb": round(hwm(), 1)}
'''


def start(work, extra_env=None):
    path = os.path.join(work, "probe_server.py")
    with open(path, "w") as fh:
        fh.write(SERVER)
    env = {**os.environ, "TMPDIR": work, "PYTHONPATH": work, **(extra_env or {})}
    p = subprocess.Popen([sys.executable, "-m", "uvicorn", "probe_server:app", "--port", str(PORT), "--log-level", "warning"],
                         env=env, cwd=work, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            httpx.get(f"http://127.0.0.1:{PORT}/hwm", timeout=0.5)
            return p
        except httpx.HTTPError:
            time.sleep(0.2)
    raise RuntimeError("서버가 뜨지 않음")


def chunks(total, size=65536):
    sent = 0
    while sent < total:
        n = min(size, total - sent)
        yield b"\x00" * n
        sent += n


def scenario(work, name, fn, extra_env=None):
    p = start(work, extra_env)
    try:
        base = httpx.get(f"http://127.0.0.1:{PORT}/hwm").json()["vmhwm_mb"]
        t0 = time.perf_counter()
        try:
            r = fn(f"http://127.0.0.1:{PORT}")
            status, body = r.status_code, r.text[:90]
        except httpx.HTTPError as e:
            status, body = type(e).__name__, ""
        dt = time.perf_counter() - t0
        hwm = httpx.get(f"http://127.0.0.1:{PORT}/hwm").json()["vmhwm_mb"]
        print(f"| {name} | {status} | {body} | {dt:.2f} s | 시작 {base} -> 최대 {hwm} MB (증가 {hwm - base:.1f}) |")
    finally:
        p.terminate()
        p.wait()


def main():
    work = sys.argv[1]
    os.makedirs(work, exist_ok=True)
    sample = os.path.join(work, "payload.bin")
    with open(sample, "wb") as fh:
        fh.write(os.urandom(int(4.9 * 1048576)))
    print("| 시나리오 | 응답 | 본문 | 소요 | 서버 RSS |")
    print("| --- | --- | --- | --- | --- |")
    scenario(work, "up_5mb (멀티파트 UploadFile)", lambda b: httpx.post(b + "/up", files={"file": ("x.xlsx", open(sample, "rb"), "application/octet-stream")}, timeout=60))
    scenario(work, "raw_5mb (octet-stream, 스트리밍 BytesIO)", lambda b: httpx.post(b + "/raw", content=open(sample, "rb").read(), headers={"content-type": "application/octet-stream"}, timeout=60))
    scenario(work, "raw_7mb_cl (7MiB, Content-Length 있음 -> 읽기 전에 거부)", lambda b: httpx.post(b + "/raw", content=os.urandom(7 * 1048576), timeout=60))
    scenario(work, "raw_chunked (64MiB, 길이 모름)", lambda b: httpx.post(b + "/raw", content=chunks(64 * 1048576), timeout=60))
    scenario(work, "up_64mb (멀티파트 64MiB, 앱 상한 없음)", lambda b: httpx.post(b + "/up", files={"file": ("x.xlsx", chunks_to_bytes(64), "application/octet-stream")}, timeout=120))
    scenario(work, "up_64mb + RequestBodyLimitMiddleware(6MiB)", lambda b: httpx.post(b + "/up", files={"file": ("x.xlsx", chunks_to_bytes(64), "application/octet-stream")}, timeout=120), {"MW": "1"})
    scenario(work, "up_5mb + RequestBodyLimitMiddleware(6MiB)", lambda b: httpx.post(b + "/up", files={"file": ("x.xlsx", open(sample, "rb"), "application/octet-stream")}, timeout=60), {"MW": "1"})


def chunks_to_bytes(mib):
    return b"\x00" * (mib * 1048576)


if __name__ == "__main__":
    main()
