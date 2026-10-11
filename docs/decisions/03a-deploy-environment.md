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
- **포털(frontend·backend):** 접두를 떼고 넘기는 방식과 그대로 넘기는 방식을 **설정값만으로 전환**할 수 있게 구성한다(코드 변경 없이). 실제 방식은 웹서버 배포 때 관리자와 맞춘다.
- **전환 변수 `APP_PROXY_STRIP_PREFIX` (승인, 2026-10-11):** `false`면 프록시가 접두를 **유지한 채** 전달하고, `true`면 프록시가 접두를 **떼고** 전달한다. **기본값은 `false`(접두 유지 전달)** 이다. 운영자 사정상 접두를 떼야 하면 `true`로 바꾼다. 권장 사항은 `docs/deploy-coordination.md` 2번. Gate ② 검증에서는 `true`와 `false` 두 값 모두로 로컬 동작을 확인한다.
- **Superset:** 접두를 **떼지 않고 그대로** 넘겨야 한다. 6.1.0의 `AppRootMiddleware`는 요청 경로가 접두로 시작하지 않으면 404를 반환한다.
- **로컬 검증:** 경로 값을 빈 값이 아닌 `/bi-wizard`, `/bi-wizard/superset`으로 두고, frontend nginx가 메인 플랫폼 프록시 역할을 재현한다. QA는 `.env`를 만들거나 수정하지 않고, `_workspace/qa/`에 비밀이 아닌 더미 값으로 임시 env 파일을 만들어 `docker compose --env-file`로 지정한다(승인). 사용자 브라우저가 Superset 경로에 직접 접근할 수 있어야 한다.
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

## 3. 읽기 전용 DB 계정 (승인, 2026-10-11)
상세는 `03-migration-tool.md`의 "읽기 전용 계정과 Superset 메타 DB 생성 방식"을 따른다. 요약: 매 기동 멱등 `db-bootstrap` 서비스(`backend/bootstrap/`, `initdb.d` 미사용), 이름 고정(`bi_readonly`, `superset_meta`, `superset`), 비밀번호만 `POSTGRES_READONLY_PASSWORD`, `SUPERSET_DB_PASSWORD`, D3 예외는 비밀번호 리터럴의 psql `:'var'` 인용만(2026-10-11 3라운드에서 앱 계정 비밀번호 `POSTGRES_APP_PASSWORD`, `POSTGRES_OWNER_PASSWORD`까지 포함하도록 승인). 추가 서비스 `db-bootstrap`의 메모리 한도는 128MB다(일시적, 시작 시 한 번).

## 4. 앱 계정 조건 (승인, 2026-10-11)
Gate ②에서는 `POSTGRES_USER`를 앱·migrate 계정으로 쓴다. 최소 권한 앱 계정 분리는 Gate ③에서 D2와 함께 설계하고, Gate ④ 진입 전 분리 완료가 필수이며, Gate ④에서 backend가 슈퍼유저로 접속하면 `bi-review`가 차단한다. 계정을 나눌 때 `ALTER DEFAULT PRIVILEGES`의 `FOR ROLE` 생략 방식도 다시 정한다.

## 5. Gate ② 결과에 대한 결정 (2026-10-11, 사용자)
상세 표는 `docs/gate-status.md`의 "Gate ② 결과 결정".

- **사후 승인:** BAT ASCII 영문 변환, frontend·postgres·backend 포트의 `127.0.0.1` 게시, 변수 4개(`SUPERSET_SECRET_KEY`, `GUEST_TOKEN_JWT_SECRET`, `SUPERSET_ADMIN_USER`, `SUPERSET_ADMIN_PASSWORD`). 웹서버에서는 메인 플랫폼 프록시 위치에 따라 `FRONTEND_HOST` 값을 바꿔야 할 수 있다(`deploy-coordination.md` 20번).
- **승인 규칙(하네스):** 새 환경변수 추가, 운영 가이드 기준선과 다른 설정, 에이전트 모델 변경은 적용 전에 사용자 승인을 받는다.
- **Embedded guest 역할:** 최소 권한 커스텀 역할로 한다. 권한 목록은 Gate ③에서 데이터 모델과 함께 정한다. `Gamma`와 `PUBLIC_ROLE_LIKE`는 운영 설정에 쓰지 않는다. **이 금지는 임베딩 대시보드를 보는 guest 역할에만 적용된다**(2026-10-11 3라운드, 사용자 확정). 포털 작성자 역할은 내장 `Gamma`를 직접 부여하지 않고 `Gamma`를 복사한 커스텀 역할과 schema 단위 보조 역할로 만든다(기본 `Public`은 `…/api/v1/me/roles/`가 403이라 실패하고 `Gamma`는 대조 실험에서만 성공했다).
- **로고 이중 접두, 404 페이지 일러스트 접두 누락:** 알려진 문제로 두고 수정하지 않는다(Superset 내부 코드 수정 금지). 수정이 포함된 정식 릴리스가 나오면 버전을 올리고 하위 경로 검증을 다시 한다(6.1.0 고정의 변경은 그때 사용자 승인).
- **Scarf:** `superset/superset_config.py`가 기본 CSP(`TALISMAN_CONFIG`, `TALISMAN_DEV_CONFIG`)에서 `scarf.sh` 호스트를 제거한다. 효과 없는 `SCARF_ANALYTICS` 변수는 삭제했다. Google Fonts는 막지 않는다.
- **라이선스 원칙:** 운영 런타임에 포함되는 우리 코드의 의존성은 허용형만 사용한다. 개발·테스트 전용 도구와 업스트림 공식 이미지 내부 구성요소는 약한 카피레프트(LGPL, MPL)를 수정·재배포하지 않는 조건으로 허용한다. GPL·AGPL·EUPL 등 강한 카피레프트와 비오픈소스 라이선스는 위치와 관계없이 금지한다. 보고된 "주의" 항목은 모두 허용하며 목록은 `deploy-coordination.md`의 "배포 전 회사 오픈소스 정책 확인"에 둔다.
- **포털 favicon:** `frontend/index.html`에 `data:,` 아이콘을 두어 `/favicon.ico` 404를 없앤다.

## 5-1. 3라운드 결정 반영 (2026-10-11, 사용자)
상세는 `03b-gate3-round-decisions.md` 3절. 이 문서와 관련된 것만 요약한다.
- **앱 계정:** `bi_owner`(마이그레이션·정적 표 소유)와 `bi_app`(런타임) 2개로 분리하며 Gate ④ 진입 전 구현한다(4절 조건의 이행 방식). `POSTGRES_USER`는 이미지 슈퍼유저 전용으로 좁아진다 → 운영 가이드 기준선과의 **의도적 차이**(`deploy-coordination.md` 29번). 새 환경변수 `POSTGRES_APP_PASSWORD`, `POSTGRES_OWNER_PASSWORD`.
- **Superset 서비스 계정:** 새 환경변수 `SUPERSET_SERVICE_USER`, `SUPERSET_SERVICE_PASSWORD`, 새 운영 런타임 의존성 `httpx`.
- **DB 시간대:** `TZ=Asia/Seoul` 유지(회사 시간대 확인됨).
- **`/health` 응답:** 기본 경로(`/health`, `/health/db`)는 그대로, 응답 필드만 추가(`views`, `views_failed_count`, `public_create`, `db_timezone`).

## 6. 열린 사항

- 메인 플랫폼 프록시의 실제 동작, 실제 경로 값 등은 `docs/deploy-coordination.md`.
- 하위 경로 + Embedded의 쿠키·iframe 허용 설정은 같은 origin 가정(`deploy-coordination.md` 9번)이 맞는지에 달려 있다.
