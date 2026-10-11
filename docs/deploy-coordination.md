# 배포 전 운영자 협의 목록

BI-Wizard는 사내 도메인을 가진 **메인 플랫폼의 URL 하위 경로**로 서비스된다(브리프 5절 4번 결정, `docs/decisions/03a-deploy-environment.md`). 웹서버에 배포할 때 관리자(웹서버 운영자)와 맞춰야 하는 항목을 여기에 모은다. 합의한 내용은 "결과 기록" 열에 날짜와 함께 적고, 값이 바뀌면 `.env`(Git 제외)와 이 표를 같이 고친다.

상태: `협의 필요`(아직 맞추지 않음), `확인됨`(합의 또는 확인 완료), `실측 대기`(검증 후 채움).

| 번호 | 항목 | 우리 쪽 요구·가정 | 상태 | 결과 기록 |
| --- | --- | --- | --- | --- |
| 1 | **실제 하위 경로 값** (`APP_BASE_PATH`, `SUPERSET_APP_ROOT`) | `.env.example`에는 예시 값 `/bi-wizard`, `/bi-wizard/superset`을 두고 "운영자 확인 필요"로 표시한다. 형식: 루트 배포는 빈 값, 아니면 앞 `/` 필수·뒤 `/` 금지. 두 값은 독립 값이다 | 협의 필요 | - |
| 2 | **메인 플랫폼 프록시의 접두 처리 방식** | 포털(frontend·backend)은 접두를 **떼고 넘기는 방식과 그대로 넘기는 방식을 설정값 `APP_PROXY_STRIP_PREFIX`만으로 전환**할 수 있게 구성한다. 어느 쪽이든 대응 가능하다. **권장: 가능하면 `/bi-wizard/` 전체를 접두를 유지한 채 전달**해 달라(`APP_PROXY_STRIP_PREFIX=false`, 기본값). 운영자 사정상 접두를 떼야 하면 이 변수를 `true`로 바꾼다. 실제 방식을 정해 달라 | 협의 필요 | - |
| 3 | **Superset 경로는 접두를 떼지 않고 그대로 전달** | **필수 요구.** Superset 6.1.0은 요청 경로가 `SUPERSET_APP_ROOT`로 시작하지 않으면 404를 반환한다(`AppRootMiddleware`). 프록시가 접두를 제거하면 동작하지 않는다 | 협의 필요 | - |
| 4 | **사용자 브라우저의 Superset 경로 직접 접근** | 사용자 브라우저가 `${SUPERSET_APP_ROOT}/…`(Embedded iframe의 `/embedded/<id>`, 정적 파일, Superset이 호출하는 API)에 **직접 접근할 수 있어야** 한다. 포털 백엔드만 통하는 구조로는 Embedded가 동작하지 않는다 | 협의 필요 | - |
| 5 | **메모리 8GB 실측 결과와 증설 필요 여부** | 프로젝트 전체 합계 8GB로 시작한다. 부족하면 증설을 요청한다 | 실측 완료(Gate ② 검증) | 2026-10-11 실측(Linux, 빈 볼륨, 커밋 `4fbf7ad`): 상시 4개 서비스 유휴 315MiB, 로그인 후 439MiB, 5세션 순회 + 20만 행 쿼리 6개 병렬 부하 최대 약 1,056MiB(superset 753MiB, 한도 2GiB의 37%). 일회성 최대 superset-init 193MiB(이전 측정). 5MB 엑셀 대리 측정(5.04MiB, 6만 행): openpyxl read-only 45MB, 일반 모드 265MB, pandas 128MB(10MB 파일은 일반 모드 491MB로 선형 증가). **8GB로 충분하며 증설은 현재 불필요.** 단 대시보드·차트가 비어 있었고 실제 가져오기 파이프라인 값이 아니므로 Gate ④ 이후 재측정한다. 한도 합계는 상시 4.75GiB, 테스트 DB 포함 6.875GiB |
| 6 | **Jenkins 실행 환경의 Docker 사용 가능 여부** | 마이그레이션 왕복 테스트(D6, tmpfs 테스트 DB)를 Jenkins에 넣는 방식을 정하기 위한 선행 확인. 에이전트에서 Docker를 쓸 수 있는지, 권한은 어떤지 | 협의 필요 | - |

## 배포 전에 함께 확인할 항목 (작성자 추가)

| 번호 | 항목 | 이유 | 상태 | 결과 기록 |
| --- | --- | --- | --- | --- |
| 7 | **요청 본문 크기 상한** | 현재 엑셀 파일은 5MB 이하다. 프록시의 요청 본문 상한(예: nginx `client_max_body_size`)이 업로드 크기 상한(Gate ③에서 결정)보다 작지 않아야 한다 | 협의 필요 | - |
| 8 | **프록시 헤더와 TLS 종단** | `X-Forwarded-Proto/Host/Prefix` 전달 여부. Superset의 `ENABLE_PROXY_FIX` 설정 여부가 달라진다. HTTPS를 어디에서 종단하는지 | 협의 필요 | - |
| 9 | **포털과 Superset의 origin** | 같은 도메인 아래 경로만 다른 구성(같은 origin)을 가정한다. 다른 origin이면 쿠키(`SameSite`)와 iframe 허용(`frame-ancestors`, `TALISMAN`) 설정이 추가로 필요하다 | 협의 필요 | - |
| 10 | **프록시 타임아웃** | 엑셀 처리와 대시보드 쿼리 시간. Superset gunicorn 기본 타임아웃은 60초다 | 협의 필요 | - |
| 11 | **Secret 주입 방식** | `.env` 배포 방식 또는 Jenkins Credential 매핑. `SUPERSET_SECRET_KEY`, `GUEST_TOKEN_JWT_SECRET`, DB 비밀번호는 저장소·이미지·프런트 번들에 넣지 않는다 | 협의 필요 | - |
| 12 | **운영 DB 백업·복구 정책** | 동적 객체(사용자 데이터셋 테이블, 수식 뷰)와 입력 데이터는 마이그레이션 이력으로 복구되지 않는다. 볼륨 백업 정책이 필요하다 | 협의 필요 | - |

## 구축 중 알게 된 항목 (env-engineer·QA 보고에서 추가)

| 번호 | 항목 | 내용 | 상태 | 결과 기록 |
| --- | --- | --- | --- | --- |
| 13 | **Superset 6.1.0 하위 경로 로고 이중 접두** | 로그인 화면이 로고를 `…/superset/bi-wizard/superset/static/…`로 요청해 404가 난다(QA 재현 확인, 기능 영향 없음). 서버가 준 경로에는 접두가 한 번만 있고 프런트가 한 번 더 붙이는 것으로 보인다. **알려진 문제로 두고 그대로 둔다**(사용자 결정, 2026-10-11). Superset 내부 코드는 수정하지 않는다. **수정이 포함된 Superset 정식 릴리스가 나오면 버전을 올리고 하위 경로 검증을 다시 한다**(6.1.0 고정 결정은 그때 사용자 승인으로 변경) | 알려진 문제(결정됨) | 2026-10-11 사용자 결정: 그대로 둠. 업그레이드 시 하위 경로(`APP_PROXY_STRIP_PREFIX` true/false)와 Embedded 검증 재실시 |
| 14 | **앞단 프록시의 `X-Forwarded-Proto/Host`** | Superset은 `ENABLE_PROXY_FIX`(1홉 신뢰)로 이 헤더를 믿는다. 메인 플랫폼 프록시가 클라이언트가 보낸 값을 신뢰할 수 있는 값으로 **덮어써야** 한다. 로컬 재현 nginx는 앞단이 보낸 값이 있으면 보존한다. (8번과 연결) | 협의 필요 | - |
| 15 | **세션 쿠키 충돌 가능성** | Superset 세션 쿠키 이름은 `session`, `Path=/bi-wizard/superset`이다. 포털이 같은 이름의 쿠키를 쓰면 충돌할 수 있다(경로가 달라 지금은 구분됨) | 확인 필요 | - |
| 16 | **정상 경로 `…/superset/superset/…` 오인** | Superset의 정상 라우트 `/superset/welcome/`이 `SUPERSET_APP_ROOT=/bi-wizard/superset` 아래에서는 `/bi-wizard/superset/superset/welcome/`이 된다. 버그가 아니다. 모니터링·접근 규칙에서 중복 접두로 오인해 차단하지 않도록 알린다 | 협의 필요 | - |
| 17 | **`/nginx-health`** | frontend 컨테이너 내부 전용 경로다. 메인 플랫폼이 전달할 필요가 없다 | 확인됨 | - |
| 18 | **외부 요청(사내망 차단 시 영향)** | Superset 6.1.0 화면은 `apachesuperset.gateway.scarf.sh`(텔레메트리 픽셀)와 `fonts.googleapis.com`, `fonts.gstatic.com`에 요청한다. `SCARF_ANALYTICS=false`는 6.1.0에서 효과가 없어(소스와 번들에 읽는 코드 없음) 변수를 삭제했다. **Scarf는 `superset/superset_config.py`가 기본 CSP(`TALISMAN_CONFIG`, `TALISMAN_DEV_CONFIG`)에서 scarf 호스트를 제거해 브라우저가 요청을 보내지 못하게 한다**(사용자 결정, 2026-10-11). 부수 효과로 콘솔에 CSP 위반 경고가 남는다. **Google Fonts는 막지 않았다.** 사내망에서 Google Fonts가 막히면 콘솔 오류와 폰트 대체가 생길 수 있다 | 확인됨(Scarf 차단) / 협의 필요(Google Fonts) | 2026-10-11 재검증: 브라우저가 보낸 Scarf 요청 13건이 모두 CSP에 막혀 전송 0건, Google Fonts 2건은 전송됨. Gamma 대조 조건에서 Embedded 정상 |
| 19 | **Superset 기본 rate limit** | 6.1.0 기본 `RATELIMIT_APPLICATION="50 per second"`(인메모리)이고 클라이언트 IP별이다. 앞단 프록시가 `X-Forwarded-For`를 보내지 않으면 모든 사용자가 한 IP로 집계된다. 연속 호출 테스트에서 429가 837건 났다(5xx는 0건). (8번과 연결) | 협의 필요 | - |
| 20 | **`FRONTEND_HOST` 값은 메인 플랫폼 프록시 위치에 따라 바꿔야 할 수 있다** | `.env`의 `FRONTEND_HOST` 기본값은 `127.0.0.1`이라 이 서버 안(같은 호스트)에서만 접속된다. 메인 플랫폼 프록시가 **같은 호스트**에서 `127.0.0.1:FRONTEND_PORT`로 전달하면 기본값 그대로 쓴다. 프록시가 **다른 서버**이거나 컨테이너 네트워크 밖에서 접근하면 `0.0.0.0` 또는 해당 서버에서 닿는 인터페이스 주소로 바꿔야 하고, 그러면 방화벽으로 접근 대상을 제한해야 한다(Superset 관리자 로그인 화면도 함께 노출되므로). postgres·backend 포트는 계속 `127.0.0.1`에 둔다 | 협의 필요 | - |
| 21 | **Superset 404 오류 페이지 일러스트의 접두 누락** | Superset 6.1.0의 404 오류 페이지가 일러스트 이미지(`/static/assets/….png`)를 `SUPERSET_APP_ROOT` 접두 없이 요청해 404가 난다(QA 재현 확인). 오류 페이지의 그림만 깨지고 기능에는 영향이 없다. **알려진 문제로 기록하고 그대로 둔다**(사용자 결정, 2026-10-11). 13번과 같이 수정 릴리스가 나오면 업그레이드와 함께 재검증한다. 메인 플랫폼 프록시는 접두 없는 `/static/…`을 이 서비스로 보내지 않아도 된다 | 알려진 문제(결정됨) | 2026-10-11 사용자 결정 |

## 배포 전 회사 오픈소스 정책 확인

라이선스 원칙(사용자 결정, 2026-10-11): **운영 런타임에 포함되는 우리 코드의 의존성은 허용형만 사용한다. 개발·테스트 전용 도구와 업스트림 공식 이미지 내부 구성요소는 약한 카피레프트(LGPL, MPL)를 수정·재배포하지 않는 조건으로 허용한다. GPL·AGPL·EUPL 등 강한 카피레프트와 비오픈소스 라이선스는 위치와 관계없이 금지한다.** 아래 "주의" 항목은 이 원칙에 따라 모두 허용했다. 배포 전에 회사의 오픈소스 정책(사내 고지·승인 절차 포함)이 이 목록을 허용하는지 확인한다.

| 번호 | 허용한 항목 | 라이선스 | 위치 | 허용 조건 |
| --- | --- | --- | --- | --- |
| 22 | `psycopg2-binary` | LGPL | `superset/Dockerfile`로 만드는 Superset 이미지 안(Superset의 PostgreSQL 연결용). backend는 사용하지 않는다(pg8000, BSD) | 수정·재배포하지 않는다(PyPI 배포본을 그대로 설치) |
| 23 | `certifi` | MPL-2.0 | 테스트 단계 이미지 | 개발·테스트 전용, 수정·재배포하지 않는다 |
| 24 | `lightningcss`와 플랫폼별 패키지 12개 | MPL-2.0 | 프런트 개발 의존성(Vite 빌드·개발 서버). 운영 번들에는 코드가 들어가지 않는다 | 개발 전용, 수정·재배포하지 않는다 |
| 25 | `BlueOak-1.0.0`, `MIT-0`, `CC0-1.0`(mdn-data), `CC-BY-4.0`(caniuse-lite) 표기 패키지 | 허용형에 준하는 라이선스(비표준 표기) | 프런트 개발 의존성 | 개발 전용 데이터·도구. `CC-BY-4.0`은 데이터 고지 의무만 있다 |

각 항목의 상태는 모두 `협의 필요`다(회사 정책 확인 전). 새 "주의" 항목이 생기면 이 표에 추가한다.

## 사내 환경 확인 항목 (Gate ② 조건부 승인 때 추가, 2026-10-11)

| 번호 | 항목 | 내용 | 상태 | 결과 기록 |
| --- | --- | --- | --- | --- |
| 26 | **Docker Desktop 없이 BAT 실행하는 방식** | BAT가 실제로 쓰일 사내 환경은 라이선스 문제로 Docker Desktop을 쓸 수 없다. 팀의 실제 방식(Podman, BAT 안에서 `wsl` 경유 등)을 확인한다. 확인 후 필요하면 BAT 6종을 그 방식에 맞게 고친다(명령 이름, 경로 변환, `docker compose` 대체, `service_completed_successfully` 지원 여부, `mem_limit` 적용 여부는 `docs/windows-bat-verification.md`의 "Docker Desktop과 Podman에 따라 달라질 수 있는 확인 항목" 참고). BAT 실행 검증은 이 확인 뒤 사내 환경에서 한다 | 협의 필요(BAT 검증 보류 해소 조건) | - |
| 27 | **Superset 화면의 Google Fonts 외부 요청** | Superset 6.1.0 화면은 `fonts.googleapis.com`, `fonts.gstatic.com`에서 글꼴을 받는다. 외부 접속이 제한된 사내망에서는 요청이 실패해 기본 글꼴로 표시될 수 있다. 기능에는 영향이 없다. 배포 때 사내망 정책을 확인한다(18번과 연결) | 협의 필요 | - |
| 28 | **인증·신원 방식 (미결정 8번) 운영자 질문 20개** | 메인 플랫폼이 사용자 신원을 어떻게 넘기는지 등 20개 질문을 `docs/operator-questions.md`에 모았다(핵심 10개 표시). 사용자가 검토해 직접 답하고 남은 것은 운영자에게 전달한다. 답을 받으면 8번 방식과 새 환경변수(적용 전 승인)를 정한다. 이전까지 포털은 `current_user` 한 곳으로 격리하고 로컬은 스텁 신원으로 진행한다(Gate ③ 1라운드 U1) | 협의 필요(8·14·15·20번과 함께) | - |
| 29 | **`POSTGRES_USER` 의미 축소(운영 가이드 기준선과의 의도적 차이)와 새 환경변수** | 3라운드 결정(2026-10-11)으로 DB 계정을 분리한다: `bi_owner`(마이그레이션·정적 표 소유), `bi_app`(런타임, `bi_data`에만 `CREATE`), `bi_readonly`(Superset). `POSTGRES_USER`/`POSTGRES_PASSWORD`는 **이미지 슈퍼유저 전용**이 되어 backend·migrate는 더 이상 이 계정으로 접속하지 않는다(운영 가이드의 `POSTGRES_USER`는 앱 계정 의미라 다름). 새 비밀번호 변수: `POSTGRES_APP_PASSWORD`, `POSTGRES_OWNER_PASSWORD`. 배포 때 운영 가이드의 `.env`/Secret 틀에 이 변수들을 추가해야 한다. 구현은 Gate ④ 진입 전 | 협의 필요(구현 전) | - |
| 30 | **Superset 서비스 계정 변수** | 서버가 Superset에 데이터셋을 등록·새로고침하는 전용 Superset 계정(최소 권한). 새 환경변수 `SUPERSET_SERVICE_USER`, `SUPERSET_SERVICE_PASSWORD`(3라운드 승인). 서버 이미지에 `httpx`가 운영 의존성으로 들어간다(허용형 라이선스). 구현은 Gate ④ | 협의 필요(구현 전) | - |
| 31 | **업로드 상한 `APP_UPLOAD_MAX_MB`와 프록시 본문 상한** | 4라운드 결정(2026-10-11): 업로드 상한 10MB, 새 환경변수 `APP_UPLOAD_MAX_MB` 하나를 서버·프록시·화면이 공유한다. 메인 플랫폼 프록시의 요청 본문 상한(예: nginx `client_max_body_size`)을 **앱 상한 + 약 1MB 여유**(예: 11MB 이상)로 맞춰야 한다(7번과 연결). 로컬 compose의 nginx도 같은 값으로 바꾼다(구현은 Gate ④ 진입 전) | 협의 필요(구현 전) | - |
| 32 | **Superset guest token 발급 계정 변수** | 서버가 Superset 발급 API를 호출할 때 쓰는 발급 전용 Superset 계정(데이터셋 등록 계정과 분리). 새 환경변수 2개(후보 `SUPERSET_GUEST_ISSUER_USER`, `SUPERSET_GUEST_ISSUER_PASSWORD`, 4라운드 승인). 발급 API는 사용자별 속도 제한(429)을 둔다. Secret 주입 방식(11번)에 포함해야 한다 | 협의 필요(구현 전) | - |
| 33 | **Superset 설정 추가 3건** | `GUEST_ROLE_NAME=bi_guest`(최소 권한 커스텀 역할을 `superset-init`이 생성), `GUEST_TOKEN_VALIDATOR_HOOK`(발급 시 `rls` 비어 있음·resource type 확인), 로컬 `GUEST_TOKEN_JWT_AUDIENCE`는 X-28 결과에 따라 필요할 때만. 4라운드 승인(기준선과 다른 설정). 임베드 대시보드의 CSV·이미지 내보내기는 허용하지 않는다 | 협의 필요(구현 전) | - |
| 34 | **가져오기 처리와 메모리** | 가져오기는 전역 동시 1건·사용자당 1건, openpyxl read-only(pandas 미사용). 메모리 8GB(5번) 안에서 backend `mem_limit` 1g 기준으로 설계하고, X-27 실측 결과에 따라 `mem_limit`/`tmpfs` 변경이 필요해지면 내용과 이유를 보고하고 적용한다. 메인 플랫폼 프록시 타임아웃(10번)이 60초 미만이면 확정 적재 목표(30초) 재검토 | 실측 후 보고 | - |
| 35 | **운영 서버(컨테이너) 안에서 관리 명령 실행 가능 여부** | 첫 관리자는 서버에서 명령 한 줄로 만든다(FU-1 K3 ㄷ 결정, 새 환경변수 없음). 운영 서버(backend 컨테이너) 안에서 명령을 실행할 수 있는지, 누가 실행하는지 운영자에게 확인해야 한다. 불가능하면 대안(예: 배포 때 한 번 실행하는 일회성 서비스)을 정한다. 인증 스텁은 운영 환경 설정에서 켜져 있으면 backend가 시작을 거부한다 | 운영자 확인 필요 | - |

## 이미 확인된 사항

- 추가 컨테이너 운영은 허용된다. Superset은 `compose.yml`의 정식 서비스다(2026-10-11, 사용자 확인).
- Redis/Valkey는 쓰지 않는다(2026-10-11 결정).
- BAT 6종은 ASCII 영문 메시지로, frontend·postgres·backend 포트는 `127.0.0.1`에 게시하는 구성이다(2026-10-11 사후 승인). Superset 컨테이너 필수 변수는 `SUPERSET_SECRET_KEY`, `GUEST_TOKEN_JWT_SECRET`, `SUPERSET_ADMIN_USER`, `SUPERSET_ADMIN_PASSWORD` 4개다(사후 승인).
