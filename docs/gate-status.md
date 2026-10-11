# Gate 진행 상태

| Gate | 상태 | 승인일 | 승인 내용 | 관련 문서 |
| --- | --- | --- | --- | --- |
| ① RESEARCH & DECIDE | 승인 | 2026-10-11 | 디자인: C(3분할 작업공간) 기본 + 데이터셋 목록·권한 관리·가져오기 앞 두 단계는 B(콘솔형). 기준 해상도 1920×1080, Inspector는 접기·폭 조절. Reference 5개 모두 확보(지목 파일만) | `docs/decisions/01-design-direction.md`, `docs/decisions/02-tech-reference.md`, `references/` |
| ② ENVIRONMENT BOOTSTRAP | 진행 중 | - | 마이그레이션 결정(D1~D7), 배포 환경 사전 제안, 읽기 전용 계정 제안 승인 완료. 환경 구축(env-engineer ⇄ qa-engineer) 진행 중 | `docs/decisions/03-migration-tool.md`, `docs/decisions/03a-deploy-environment.md`, `docs/deploy-coordination.md` |
| ③ MODULARIZE | 대기 | - | - | - |
| ④ 기능 개발 | 대기 | - | - | - |

## 미결정 사항 (브리프 5절)
| 번호 | 질문 | 상태 | 답변 |
| --- | --- | --- | --- |
| 1 | Azure OpenAI 항목 처리 | 결정됨(제외) | 제외 (2026-10-11, 사용자 결정). `.env.example`에서 Azure OpenAI 변수를 빼고 `/health/azure-openai`는 만들지 않으며, Environment Ready 체크리스트의 해당 항목은 "해당 없음" |
| 2 | 수식 범위 첫 버전 | 미결정 | - (Gate ③에서 질문) |
| 3 | 새 데이터셋 생성 권한 | 미결정 | - (Gate ③에서 질문) |
| 4 | 팀 웹서버 Superset 운영 조건 | 결정됨 | 추가 컨테이너 운영 허용, Superset은 `compose.yml` 정식 서비스. Redis/Valkey 제외. 메인 플랫폼의 URL 하위 경로로 서비스. 메모리는 프로젝트 전체 합계 8GB로 시작(부족하면 증설 요청) (2026-10-11, 사용자 결정, `docs/decisions/03a-deploy-environment.md`). 배포 때 관리자와 맞출 항목은 `docs/deploy-coordination.md` |
| 5 | 디자인 방향 | 결정 | C(3분할 작업공간) 기본 + 데이터셋 목록·권한 관리·가져오기 앞 두 단계는 B(콘솔형) (2026-10-11, Gate ①) |
| 6 | 수식 미리보기·자동완성을 위한 저장 전 수식 평가 경로 | 미결정 | - (Gate ③에서 결정) |
| 7 | Superset 차트 작성 화면(Explore)을 포털에서 어떻게 제공할지 | 미결정 | - (Gate ③에서 결정. Embedded SDK로 가능한 범위를 공식 문서로 확인한 뒤 결정) |

## Gate ② 결정 사항: DB 마이그레이션 (2026-10-11, `docs/decisions/03-migration-tool.md`)
| 번호 | 항목 | 상태 | 결정 |
| --- | --- | --- | --- |
| D1 | 마이그레이션 도구 | 결정 | Alembic |
| D2 | 동적 객체(사용자 데이터셋 테이블·수식 뷰) 분리 방식 | **연기 (Gate ③)** | Gate ③ 데이터 모델 설계 때 결정. 그때까지 Alembic 자동 생성 초안에 `DROP` 문이 있으면 적용 전에 반드시 사용자 확인 |
| D3 | 마이그레이션 raw SQL 허용 범위 | 결정 | 마이그레이션 디렉터리 안에서만 고정 SQL 문(`op.execute` 등) 허용, 변수 보간(f-string, `%`, `.format()`, `+`) 금지. 그 밖의 코드는 기존 SQL 문자열 조립 금지 규칙 |
| D4 | 마이그레이션 실행 위치 | 결정 | backend 이미지를 재사용하는 일회성 `migrate` 서비스. `backend`는 `migrate` 성공 완료 후에만 시작(`depends_on`) |
| D5 | 되돌리기 정책 | 결정 | 모든 마이그레이션에 `downgrade` 작성, 빈 DB에서 upgrade → downgrade → upgrade 왕복 테스트. 운영 중 문제는 수정 마이그레이션 추가로 대응 |
| D6 | 빈 DB 검증 방식 | 결정 (Jenkins 적용은 추후) | tmpfs 테스트 전용 PostgreSQL 서비스를 compose profile로 정의(평소 미기동), 정리는 `-v` 없는 `docker compose down`. **Jenkins 적용은 Jenkins 실행 환경(Docker 사용 가능 여부) 확인 후 결정** |
| D7 | Superset 메타데이터 DB | 결정 | 같은 PostgreSQL 컨테이너 안의 별도 데이터베이스. Superset의 업무 데이터 연결은 읽기 전용 DB 계정 |

## Gate ② 진행 메모
- 마이그레이션 결정(D1~D7)과 사전 제안 6개가 모두 승인됐다(`docs/decisions/03-migration-tool.md`, `docs/decisions/03a-deploy-environment.md`). 승인 내용: 변수 `APP_BASE_PATH`·`SUPERSET_APP_ROOT`(예시 값 `/bi-wizard`, `/bi-wizard/superset`, "운영자 확인 필요" 표시), 포털의 프록시 접두 처리는 설정값만으로 전환(Superset은 접두 유지 전달), 로컬 검증은 frontend nginx가 메인 플랫폼 프록시를 재현, 메모리 배분과 Valkey 제외, Superset `6.1.0` 고정과 하위 경로 + Embedded 검증, 마이그레이션 디렉터리 `backend/migrations/`.
- 미결정 1번 "제외", 미결정 4번 "결정됨"이다. Azure OpenAI 변수·Health 경로·체크리스트 항목은 만들지 않고, Superset은 `compose.yml`의 정식 서비스이며 Redis/Valkey는 두지 않는다.
- **하위 경로 버그가 재현되면** Superset 내부 코드는 수정하지 않고, 대안과 각 영향을 정리해 보고한 뒤 멈춘다.
- **5MB 엑셀 샘플로 backend 메모리를 실측**해 보고하고(Gate ② 검증), 결과를 `docs/deploy-coordination.md` 5번에 기록한다.
- **읽기 전용 계정 제안 승인(2026-10-11):** 매 기동 멱등 `db-bootstrap`(`backend/bootstrap/`, `initdb.d` 미사용), D3 예외(비밀번호 리터럴 두 곳의 psql `:'var'`만, 식별자 보간 금지), 이름 고정 `bi_readonly`/`superset_meta`/`superset`, 비밀번호 변수 `POSTGRES_READONLY_PASSWORD`/`SUPERSET_DB_PASSWORD`. 앱 계정은 Gate ②에서 `POSTGRES_USER`를 쓰며, 분리 조건은 아래 Gate ③ 인계 사항.
- **접두 처리 전환 변수 `APP_PROXY_STRIP_PREFIX` 승인:** 기본값 `false`(접두 유지 전달). Gate ② 검증에서 `true`/`false` 두 값 모두로 로컬 동작을 확인한다. 배포 협의 권장 사항은 `docs/deploy-coordination.md` 2번.
- **QA 환경 파일 규칙 승인:** QA는 `.env`를 만들거나 수정하지 않고 `_workspace/qa/`의 비밀이 아닌 더미 값 임시 env 파일을 `--env-file`로 지정한다.
- **현재 단계:** env-engineer ⇄ qa-engineer 구축·검증 단계 진행 중. 완료 후 Environment Ready 결과, `docker stats` 실측, 하위 경로 + Embedded 검증, BAT 검증 요청서를 보고한다.

## Gate ③ 인계 사항
Gate ① 원본 대조(`docs/decisions/02-tech-reference.md`)에서 나온 세 가지는 설계 전에 반영한다.
- **붙여넣기 파서의 따옴표 안 탭 처리:** react-datasheet-grid의 `parseTextPlainData`는 따옴표 안의 줄바꿈만 셀 내용으로 유지하고 **탭은 따옴표 안에서도 셀을 나눈다.** 한 줄짜리 따옴표 셀은 따옴표가 그대로 남는다. 그대로 이식하지 말고 탭·따옴표·`\r` 케이스를 요구사항과 테스트 기준으로 설계한다.
- **Baserow 순환 검사기의 f-string raw SQL:** `circular_reference_checker.py`는 SQL을 f-string으로 조립한다. SQL 문자열 조립 금지 원칙과 충돌하므로 알고리즘만 참고하고, 구현은 SQLAlchemy 표현식 또는 파이썬 그래프 탐색으로 설계한다.
- **Superset RLS `clause` 서버 미검증:** 서버는 `clause`를 검증하지 않는다(`api.py`의 TODO). `GUEST_TOKEN_VALIDATOR_HOOK` 검증 추가 여부와 `clause` 생성 규칙(정수 ID·화이트리스트 식별자, 문자열 값 처리)을 설계한다.

- **RLS `clause`와 `CREATE VIEW`의 SQL 문자열 렌더링 문제:** Superset guest token의 RLS `clause`는 SQL 문자열이고, 수식 속 문자열 리터럴이 뷰 정의(DDL)로 렌더링되는 지점이 생긴다. `CREATE VIEW`에 bind parameter를 쓸 수 없다는 근거는 2012년 메일링 스레드 요약뿐이다. **Gate ③에서 PostgreSQL 공식 문서와 SQLAlchemy 공식 문서로 근거를 확인한 뒤 설계한다.** 설계 전에는 확정하지 않는다.
- 수식 범위(2번)가 정해져야 `references/baserow/`에서 참고할 모듈 범위(lookup·집계 포함 여부)를 확정할 수 있다.
- **앱 계정 분리 (조건부 승인, 2026-10-11):** Gate ②에서는 `POSTGRES_USER`(이미지 슈퍼유저)를 앱·migrate 계정으로 쓴다. 조건: (1) 최소 권한 앱 계정 분리는 Gate ③에서 D2와 함께 설계한다. (2) **Gate ④ 진입 전 분리 완료가 필수 조건**이다. (3) Gate ④에서 backend가 슈퍼유저로 접속하면 `bi-review`가 차단한다. (4) 계정을 나눌 때 `ALTER DEFAULT PRIVILEGES`의 `FOR ROLE` 생략 방식도 다시 정한다(생략하면 마이그레이션 실행 역할과 런타임 DDL 실행 역할이 같아야 하므로, 분리 시 어느 역할이 동적 객체를 만들고 `bi_readonly`에 어떻게 `SELECT`를 주는지 새로 설계).
- **D2 (동적 객체 분리 방식) 결정:** 데이터 모델과 함께 옵션(S 별도 schema, N 이름 규칙, R 등록 테이블 기반, D 별도 DB)을 비교해 사용자가 결정한다. 읽기 전용 계정(D7)의 동적 객체 `SELECT` 권한 부여 방식, 수식 → 뷰 변환 규칙 변경 시 기존 뷰 재생성 방식도 함께 정한다. 결정 전까지 자동 생성 초안의 `DROP`은 사용자 확인 없이 적용하지 않는다.
- **업로드 크기 상한:** 이 서비스가 다룰 데이터는 대용량이 아니고 현재 엑셀 파일은 5MB 이하다. Gate ② 검증에서 5MB급 샘플로 backend 사용량을 실측한 결과를 근거로 Gate ③에서 상한을 정한다. 프록시의 요청 본문 상한(`docs/deploy-coordination.md` 7번)과 맞춘다.
- **D6 Jenkins 적용:** Jenkins 실행 환경에서 Docker 사용 가능 여부를 확인한 뒤 정한다(Jenkinsfile의 초기 Stage에는 마이그레이션 왕복 테스트를 아직 넣지 않는다).
