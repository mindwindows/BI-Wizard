# Windows PC BAT 검증 요청서 (Gate ②)

> **상태: 보류(사내 환경에서 검증, 2026-10-11).** 개인 PC 검증은 하지 않는다. 사내 환경은 Docker Desktop을 쓸 수 없으므로 사내 컨테이너 실행 방식(`docs/deploy-coordination.md` 26번)을 확인한 뒤, 사내 워크스테이션 또는 팀 웹서버 배포 준비 때 이 요청서로 검증한다. 아래 "Docker Desktop" 전제 문구는 그 방식에 맞게 바꿔 읽는다.

- 작성: qa-engineer, 2026-10-11 (커밋 `4fbf7ad` 기준, EW-1 이전). EW-1(DB 계정 분리, 2026-10-11)과 EW-3(Superset 서비스·발급 계정, 2026-10-12) 이후 바뀐 점: `.env` Secret 10개(EW-3에서 `SUPERSET_SERVICE_PASSWORD`, `SUPERSET_GUEST_ISSUER_PASSWORD`와 이름 변수 `SUPERSET_SERVICE_USER`, `SUPERSET_GUEST_ISSUER_USER` 추가)와 `AUTH_STUB_ENABLED` 추가, `scripts\validate-env.bat`·나머지 BAT는 파일 변경 없음(`.env.example`을 읽어 검사). BAT 기대 결과 중 EW-1 이후 기준으로 다시 확인하지 않은 항목은 이 요청서로 사내 환경에서 확인할 때 함께 본다
- **BAT 6종은 Linux 클라우드 세션에서 실행하지 않았다.** 같은 동작의 `docker compose` 명령은 Linux에서 모두 검증했다. 아래는 사용자가 Windows PC에서 직접 확인할 항목이다.
- `scripts\*.bat`은 모두 ASCII 영문 메시지, CRLF, BOM 없음이다(`chcp` 미사용). 한글 깨짐과 레이블 인식 문제 우려는 이 구성으로 해소했다. 실제 동작은 이 요청서로 확인한다.
- 기대 결과 중 BAT 메시지는 BAT 최신 내용을 읽고 적은 것이고, 컨테이너 상태와 화면은 Linux에서 같은 동작을 검증한 값이다.

## 사전 확인 (한 번만)
| 순서 | 실행할 명령 | 기대 결과 | 실패 시 보낼 정보 |
| --- | --- | --- | --- |
| 0-1 | `docker version`, `docker compose version` | Docker Desktop(권장) 또는 Podman이 응답한다. Compose는 v2 이상 | 두 명령 출력, 사용 도구와 버전, Windows 버전 |
| 0-2 | `docker info`의 `Total Memory` 확인 | 8GiB 이상 권장. 부족하면 Docker Desktop Settings → Resources에서 늘린다(WSL2는 기본이 호스트 RAM의 약 50%) | `Total Memory`, PC RAM |
| 0-3 | `curl.exe --version` | 버전이 출력된다(`health-check.bat`이 사용) | 출력 |
| 0-4 | 저장소를 `git clone`으로 받는다(ZIP 아님). 이어서 `dir scripts` | `scripts`에 BAT 6개와 `ci-validate-env.sh`, `test-ci-validate-env.sh`가 있다 | `git config core.autocrlf` 값, 저장소 경로(공백·한글 포함 여부) |

## `.env` 만들기 (비밀 값은 사용자가 직접 채우고 채팅이나 AI에 보내지 않는다)
1. 저장소 루트에서 `copy .env.example .env`.
2. `.env`를 편집기(VS Code 권장)로 열어 **비어 있는 Secret 10개**를 서로 **다른** 값으로 채운다: `POSTGRES_PASSWORD`, `POSTGRES_APP_PASSWORD`, `POSTGRES_OWNER_PASSWORD`, `POSTGRES_READONLY_PASSWORD`, `SUPERSET_DB_PASSWORD`, `SUPERSET_SECRET_KEY`, `GUEST_TOKEN_JWT_SECRET`, `SUPERSET_ADMIN_PASSWORD`, `SUPERSET_SERVICE_PASSWORD`, `SUPERSET_GUEST_ISSUER_PASSWORD`.
3. 값 생성 예(호출마다 새 값): `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Python이 없으면 `powershell -NoProfile -Command "-join ((1..32) | ForEach-Object { '{0:x2}' -f (Get-Random -Maximum 256) })"`.
4. **주의 문자:** 값은 영문, 숫자, `-`, `_`만 쓴다. `$`, `%`, `#`, 작은따옴표, 큰따옴표, 공백, `=`, 한글을 쓰지 않는다. 값 끝에 공백이 남지 않게 한다. 인코딩은 BOM 없는 UTF-8이나 ANSI로 저장한다(메모장의 "UTF-8(BOM 포함)"은 피한다).
5. **접속 주소 기본값:** `FRONTEND_HOST=127.0.0.1`이 기본이라 이 PC의 브라우저에서만 접속된다. 같은 LAN의 다른 PC에서 접속하려면 `FRONTEND_HOST=0.0.0.0`으로 바꾸고 `scripts\restart-local.bat`을 실행한다. 단 그러면 Superset 관리자 로그인 화면도 LAN에 노출되고 Windows 방화벽 허용 창이 뜰 수 있다. 포트가 겹치면 `FRONTEND_PORT`, `POSTGRES_PORT`, `BACKEND_PORT`를 바꾼다.
6. `APP_BASE_PATH=/bi-wizard`, `SUPERSET_APP_ROOT=/bi-wizard/superset`은 예시 값이며 실제 값은 웹서버 운영자와 정한다(`docs/deploy-coordination.md` 1번). 로컬 검증에서는 기본값을 그대로 쓴다.

## 실행 확인
| 순서 | 실행할 명령 (또는 BAT) | 기대 결과 | 실패 시 보낼 정보 |
| --- | --- | --- | --- |
| 1 | `scripts\validate-env.bat` | 마지막 줄 `[OK] .env check passed: all variable names exist and have values.` 문제가 있으면 `[MISSING] 변수이름`, `[EMPTY] 변수이름`이 나오고 `[FAIL] .env check failed: N missing, M empty.` | 콘솔 출력 전체(변수 이름만. 값은 보내지 않는다) |
| 2 | `scripts\start-local.bat` | 이미지 빌드(첫 기동 몇 분), `docker compose ps` 표시. `db-bootstrap`, `migrate`, `superset-init`은 `Exited (0)`, `postgres`, `backend`, `frontend`, `superset`은 `healthy`. `backend`와 `superset-init`은 `migrate`가 끝난 뒤 시작한다. `superset-init` 로그(`scripts\logs-local.bat superset-init`)에 역할 4개와 계정 2개 확인 줄이 있고 비밀번호는 없다. 마지막 줄 `[OK] Start requested. Next: scripts\health-check.bat` | `docker compose ps -a`와 `scripts\logs-local.bat db-bootstrap`, `…migrate`, `…superset-init`, `…backend`, `…superset`(각각 `--tail=200`) 출력 |
| 3 | `scripts\health-check.bat` | 첫 줄 `Target: http://localhost:5173/bi-wizard/`, 이어서 `[OK] portal page`, `[OK] API /health`, `[OK] API /health/db PostgreSQL`, `[OK] Superset /health`, 마지막 `[OK] All checks passed.` (Superset은 기동 후 1분쯤 걸릴 수 있어 실패하면 1분 뒤 재시도) | `[FAIL] …` 줄과 URL, `scripts\logs-local.bat frontend` 출력 |
| 4 | 브라우저에서 `http://localhost:5173/bi-wizard/` (포트는 `.env`의 `FRONTEND_PORT`) | 제목 BI-Wizard, 표에 `API 정상 (HTTP 200)`, `DB 정상 (HTTP 200)`. 개발자 도구 콘솔에 오류가 없다(`favicon.ico` 404는 수정됨) | 화면 캡처(주소창 포함)와 콘솔 오류 |
| 5 | 브라우저에서 `http://localhost:5173/bi-wizard/superset/` | 로그인 화면(`…/bi-wizard/superset/login/?next=…`)으로 이동한다. 좌상단 로고가 깨진 이미지로 보이는 것은 알려진 Superset 6.1.0 현상이다(`deploy-coordination.md` 13번). 콘솔에 Scarf(`apachesuperset.gateway.scarf.sh`) 이미지가 CSP로 차단됐다는 경고가 보이는 것은 의도된 동작이다. `SUPERSET_ADMIN_USER`(기본 `admin`)와 `SUPERSET_ADMIN_PASSWORD`로 로그인하면 홈(`…/superset/superset/welcome/`)이 열린다. Dashboards, Charts, Datasets, SQL Lab 이동이 된다. Settings → Database Connections에 `BI-Wizard (read-only)`가 있다 | 화면 캡처, 개발자 도구 Network 탭의 404 요청 목록(로고, service-worker.js, 404 오류 페이지 일러스트 외에 다른 것이 있는지) |
| 6 | `scripts\stop-local.bat` 실행 후 `docker volume ls` | `[OK] Stopped. The data volume is kept.` 볼륨 `bi-wizard_postgres_data`가 남아 있다 | 콘솔 출력 |
| 7 | 다시 `scripts\start-local.bat` → `scripts\health-check.bat` | 2~3과 같이 `[OK]`. Superset 관리자 로그인이 그대로 된다(계정과 데이터 유지). 두 번째 기동은 캐시로 빠르다 | `docker compose ps -a`, `scripts\logs-local.bat db-bootstrap` |
| 8 | `.env`에서 `APP_PROXY_STRIP_PREFIX=true`로 바꾸고 `scripts\restart-local.bat` 후 `scripts\health-check.bat` | restart 마지막 줄 `[OK] Restart requested. Next: scripts\health-check.bat`, health-check는 모두 `[OK]`. `docker compose logs backend`에 `프록시가 접두를 떼는가=True, 받는 API 접두=/api`. 확인 후 `false`로 되돌리고 다시 `restart-local.bat` | 콘솔 출력, `docker compose logs backend` 마지막 20줄 |
| 9 | (선택) `scripts\logs-local.bat backend` | 로그가 계속 출력된다(종료는 Ctrl+C) | 출력 |
| 10 | (선택) `docker stats --no-stream` | 서비스별 메모리가 한도(postgres 1.5GiB, superset 2GiB, backend 1GiB, frontend 256MiB) 안이고 `MEM LIMIT`에 한도가 표시된다(`mem_limit` 적용 확인) | 출력 |

## Docker Desktop과 Podman에 따라 달라질 수 있는 확인 항목
- **`service_completed_successfully` 지원:** 2단계에서 `backend`가 `migrate` 종료 뒤에만 시작되는지(`docker compose ps -a`의 시작 시각 또는 `scripts\logs-local.bat migrate`) 확인한다. Podman의 compose 구현이 이 조건을 무시하면 `backend`가 `migrate`보다 먼저 뜰 수 있다. 확인이 안 되면 `docker compose version`과 `podman version`을 보낸다.
- **bind mount 경로:** `db-bootstrap`은 `./backend/bootstrap`을 `/bootstrap:ro`로 마운트한다. 저장소 경로에 공백이나 한글이 있거나 Docker Desktop 파일 공유 범위 밖이면 `db-bootstrap` 로그에 `No such file` 오류가 날 수 있다. 이 경우 `scripts\logs-local.bat db-bootstrap` 출력과 저장소 경로를 보낸다.
- **`mem_limit` 동작:** 10단계의 `MEM LIMIT` 열과 0-2의 Total Memory를 확인한다. Podman은 cgroup 설정에 따라 무시될 수 있다.
- **tmpfs와 `user: postgres`:** `db-bootstrap`이 `Exited (0)`인지 확인한다.

## 실패 시 공통으로 보낼 정보
실행한 BAT 이름과 콘솔 출력 전체, `docker compose ps -a`, 해당 서비스의 `docker compose logs --tail=200 <서비스>`, `docker version`과 `docker compose version`, Windows 버전. **`.env`의 값은 보내지 말고 변수 이름만 확인한다.**
