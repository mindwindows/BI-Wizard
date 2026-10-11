# 03a. 배포 환경: 하위 경로, 메모리, Superset

- Gate: ② ENVIRONMENT BOOTSTRAP
- 결정일: 2026-10-11 (사용자 결정)
- 해결하는 미결정: 브리프 5절 4번(팀 웹서버의 Superset 운영 조건)
- 번호 `03a`는 Gate ③ 문서(`04-modules.md`, `05-api-contract.md`)와 번호가 겹치지 않게 붙였다. 마이그레이션 결정은 `03-migration-tool.md`다.
- 배포 때 관리자와 맞출 항목: `docs/deploy-coordination.md`

## 1. 미결정 4번 결정

- 추가 컨테이너 운영은 허용된다. **Superset은 `compose.yml`의 정식 서비스**로 포함한다.
- **Redis/Valkey는 제외한다.** Superset 기본 캐시(`FILTER_STATE_CACHE_CONFIG`, `EXPLORE_FORM_DATA_CACHE_CONFIG`)가 `SupersetMetastoreCache`(메타데이터 DB)라서 필수가 아니다(6.1.0 `config.py`에서 확인). 공식 문서는 Redis를 "권장"한다. 필요해지면 다시 논의한다.
- BI-Wizard는 사내 도메인을 가진 **메인 플랫폼의 URL 하위 경로**로 서비스된다.
- 메모리는 **프로젝트 전체 합계 8GB**로 시작하고, 부족하면 증설을 요청할 수 있다.

## 2. 사전 제안 승인 (2026-10-11)

### 2-1. 환경변수 이름과 형식
| 이름 | 의미 | 형식 | 쓰는 곳 |
| --- | --- | --- | --- |
| `APP_BASE_PATH` | 포털(프런트·API)의 하위 경로. 기존 `APP_*` 그룹 | 루트 배포는 빈 값, 아니면 `/경로`(앞 `/` 필수, 뒤 `/` 금지) | 프런트 빌드와 프록시, backend `root_path`, BAT health-check, README |
| `SUPERSET_APP_ROOT` | Superset의 하위 경로. **Superset이 직접 읽는 공식 환경변수명을 그대로** 쓴다 | 동일 | superset 컨테이너, 포털이 iframe 주소를 만들 때 |

- 두 값은 **독립 값**이다. 한쪽에서 다른 쪽을 파생하지 않는다.
- 프런트 컨테이너에는 `APP_BASE_PATH`만 공개 설정으로 전달한다. 전체 `.env`는 넘기지 않는다.
- `.env.example`에는 예시 값으로 `/bi-wizard`, `/bi-wizard/superset`을 두고 **"운영자 확인 필요"** 주석을 단다.
- 같은 의미의 다른 이름(예: `SUPERSET_BASE_PATH`)을 만들지 않는다.

### 2-2. 프록시 접두 처리
- **포털(frontend·backend):** 접두를 떼고 넘기는 방식과 그대로 넘기는 방식을 **설정값만으로 전환**할 수 있게 구성한다(코드 변경 없이). 실제 방식은 웹서버 배포 때 관리자와 맞춘다. 전환 설정값의 이름은 compose 구성 제안에서 정한다(후보: `APP_PROXY_STRIP_PREFIX`).
- **Superset:** 접두를 **떼지 않고 그대로** 넘겨야 한다. 6.1.0의 `AppRootMiddleware`는 요청 경로가 접두로 시작하지 않으면 404를 반환한다.
- **로컬 검증:** 경로 값을 빈 값이 아닌 `/bi-wizard`, `/bi-wizard/superset`으로 두고, frontend nginx가 메인 플랫폼 프록시 역할을 재현한다. 사용자 브라우저가 Superset 경로에 직접 접근할 수 있어야 한다.
- 프런트의 API 경로는 `/api` 고정이 아니라 `${APP_BASE_PATH}/api`다(호스트 없는 상대경로라는 취지는 그대로).

### 2-3. 메모리 배분 (승인, 한도 합계 8GB 안)
모든 숫자는 **추정**이다(Superset 공식 문서에 운영 최소 메모리 수치가 없다). 기동 후 `docker stats`로 실측해 조정한다.

| 서비스 | 시점 | 한도(`mem_limit`) | 비고 |
| --- | --- | --- | --- |
| `postgres` | 상시 | 1.5GB | `shared_buffers=256MB`. 앱 DB + Superset 메타 DB |
| `superset` (web) | 상시 | 2.0GB | gunicorn 기본 `workers=1`, `threads=20`. `WORKER_MAX_REQUESTS`로 주기적 재시작 |
| `backend` | 상시 | 1.0GB | uvicorn 워커 1개 |
| `frontend` | 상시 | 256MB | nginx 정적 서빙 + 프록시 |
| `migrate` | 시작 시 | 512MB | 일회성 |
| `superset-init` | 시작 시 | 1.0GB | `superset db upgrade` + `superset init` |
| `postgres-test` (profile `test`) | 테스트 시 | 512MB | tmpfs 256MB 포함 |
| Redis/Valkey, Celery | 제외 | 0 | 필요해지면 재논의(+256MB / +1.5GB 이상) |

- 상시 한도 합계 4.75GB, 테스트 DB 포함 5.25GB, 여유 약 2.75GB(OS, Docker 데몬, 페이지 캐시, 순간 사용량).
- 한도는 `compose.yml`에 고정한다(변수화하지 않는다).
- **5MB 엑셀 샘플 실측:** 이 서비스가 다룰 데이터는 대용량이 아니고 현재 엑셀 파일은 5MB 이하다. Gate ② 검증 때 5MB급 샘플로 backend 사용량을 실측해 보고한다. 가져오기 기능은 Gate ④에서 구현되므로, 이 시점의 측정은 backend 이미지 안에서 같은 라이브러리(openpyxl, pandas)로 샘플을 읽는 **대리 측정**이다. 결과는 `docs/deploy-coordination.md`의 5번에 기록한다.
- **업로드 크기 상한은 Gate ③에서** 이 실측값을 근거로 정한다(`gate-status.md` 인계 사항).

### 2-4. Superset 이미지와 하위 경로
- **Superset 이미지는 `6.1.0`으로 고정**한다(마스터는 미릴리스).
- 공식 문서(`configuring-superset.mdx`)는 하위 경로 배포를 **BETA**로 표시한다. 6.1.0 `app.py`는 `SUPERSET_APP_ROOT`를 지원하지만, 마스터의 `UPDATING.md` "Next"에 기록된 하위 경로 관련 수정(중복 접두 `/superset/superset/…` 등)은 6.1.0에 없다(`legacy_prefix_redirect.py` 부재 확인). 증상 재현은 확인하지 않았다.
- **Environment Ready 체크리스트에 "하위 경로 + Embedded 동작 검증"을 추가**한다.
- **하위 경로 버그가 재현되면 Superset 내부 코드는 수정하지 않는다.** 대안과 각 영향을 정리해 보고하고 멈춘다.
- Embedded SDK의 `supersetDomain`은 경로가 든 값(`https://호스트/bi-wizard/superset`)을 받을 수 있다(`index.ts`가 끝의 `/`만 제거). `GUEST_TOKEN_JWT_SECRET`의 기본값은 자리표시 값이므로 `.env` Secret으로 덮어쓴다. `GUEST_TOKEN_JWT_EXP_SECONDS` 기본값은 300초다.

### 2-5. 마이그레이션 디렉터리
- `backend/migrations/`로 승인한다(`03-migration-tool.md`).

## 3. 열린 사항

- **읽기 전용 DB 계정의 생성 방식**(03 문서의 열린 쟁점): env-engineer가 먼저 제안하고 승인을 받는다.
- 프록시 접두 처리 전환 설정값의 변수 이름.
- 메인 플랫폼 프록시의 실제 동작, 실제 경로 값 등은 `docs/deploy-coordination.md`.
- 하위 경로 + Embedded의 쿠키·iframe 허용 설정은 같은 origin 가정(`deploy-coordination.md` 9번)이 맞는지에 달려 있다.
