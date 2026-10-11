"""컨테이너 healthcheck: 로컬 /api/health가 200이면 종료 코드 0이다."""

import os
import sys
import urllib.request

port = os.environ.get("BACKEND_PORT", "8000")
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=3) as response:
        sys.exit(0 if response.status == 200 else 1)
except Exception:
    sys.exit(1)
