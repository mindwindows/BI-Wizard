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
| 13 | **Superset 6.1.0 하위 경로 로고 이중 접두** | 로그인 화면이 로고를 `…/superset/bi-wizard/superset/static/…`로 요청해 404가 난다(서버가 준 경로에는 접두가 한 번만 있고 프런트가 한 번 더 붙이는 것으로 보임). 기능에는 영향이 없다고 보고됐으나 QA 재현 결과를 확인한다. 대안: 그대로 둠 / `superset_config.py` 설정만으로 로고 값 변경(효과 미검증) / 프록시에서 이중 접두를 한 번으로 줄이는 rewrite(실제 메인 플랫폼 프록시에도 같은 설정 필요) / 수정이 반영된 릴리스로 변경(6.1.0 고정 결정 변경). **Superset 내부 코드는 수정하지 않는다** | 사용자 결정 대기 | - |
| 14 | **앞단 프록시의 `X-Forwarded-Proto/Host`** | Superset은 `ENABLE_PROXY_FIX`(1홉 신뢰)로 이 헤더를 믿는다. 메인 플랫폼 프록시가 클라이언트가 보낸 값을 신뢰할 수 있는 값으로 **덮어써야** 한다. 로컬 재현 nginx는 앞단이 보낸 값이 있으면 보존한다. (8번과 연결) | 협의 필요 | - |
| 15 | **세션 쿠키 충돌 가능성** | Superset 세션 쿠키 이름은 `session`, `Path=/bi-wizard/superset`이다. 포털이 같은 이름의 쿠키를 쓰면 충돌할 수 있다(경로가 달라 지금은 구분됨) | 확인 필요 | - |
| 16 | **정상 경로 `…/superset/superset/…` 오인** | Superset의 정상 라우트 `/superset/welcome/`이 `SUPERSET_APP_ROOT=/bi-wizard/superset` 아래에서는 `/bi-wizard/superset/superset/welcome/`이 된다. 버그가 아니다. 모니터링·접근 규칙에서 중복 접두로 오인해 차단하지 않도록 알린다 | 협의 필요 | - |
| 17 | **`/nginx-health`** | frontend 컨테이너 내부 전용 경로다. 메인 플랫폼이 전달할 필요가 없다 | 확인됨 | - |

| 18 | **외부 요청(사내망 차단 시 영향)** | Superset 6.1.0 화면은 `apachesuperset.gateway.scarf.sh`(텔레메트리 픽셀)와 `fonts.googleapis.com`, `fonts.gstatic.com`에 요청한다. `SCARF_ANALYTICS=false`는 6.1.0에서 효과가 없음을 확인했다(소스와 번들에 읽는 코드가 없음). 사내망에서 막히면 콘솔 오류와 지연이 생길 수 있고, 허용하면 사용 통계가 외부로 나간다. 설정 파일의 CSP(`TALISMAN_CONFIG`)에서 scarf 호스트를 빼는 방안은 사용자 결정 대기 | 사용자 결정 대기 | - |
| 19 | **Superset 기본 rate limit** | 6.1.0 기본 `RATELIMIT_APPLICATION="50 per second"`(인메모리)이고 클라이언트 IP별이다. 앞단 프록시가 `X-Forwarded-For`를 보내지 않으면 모든 사용자가 한 IP로 집계된다. 연속 호출 테스트에서 429가 837건 났다(5xx는 0건). (8번과 연결) | 협의 필요 | - |

## 이미 확인된 사항

- 추가 컨테이너 운영은 허용된다. Superset은 `compose.yml`의 정식 서비스다(2026-10-11, 사용자 확인).
- Redis/Valkey는 쓰지 않는다(2026-10-11 결정).
