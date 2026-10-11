# Gate 진행 상태

| Gate | 상태 | 승인일 | 승인 내용 | 관련 문서 |
| --- | --- | --- | --- | --- |
| ① RESEARCH & DECIDE | 승인 | 2026-10-11 | 디자인: C(3분할 작업공간) 기본 + 데이터셋 목록·권한 관리·가져오기 앞 두 단계는 B(콘솔형). 기준 해상도 1920×1080, Inspector는 접기·폭 조절. Reference 5개 모두 확보(지목 파일만) | `docs/decisions/01-design-direction.md`, `docs/decisions/02-tech-reference.md`, `references/` |
| ② ENVIRONMENT BOOTSTRAP | 진행 중 | - | - | `_workspace/gate2/` (승인 전 초안, Git 제외) |
| ③ MODULARIZE | 대기 | - | - | - |
| ④ 기능 개발 | 대기 | - | - | - |

## 미결정 사항 (브리프 5절)
| 번호 | 질문 | 상태 | 답변 |
| --- | --- | --- | --- |
| 1 | Azure OpenAI 항목 처리 | 결정됨(제외) | 제외 (2026-10-11, 사용자 결정). `.env.example`에서 Azure OpenAI 변수를 빼고 `/health/azure-openai`는 만들지 않으며, Environment Ready 체크리스트의 해당 항목은 "해당 없음" |
| 2 | 수식 범위 첫 버전 | 미결정 | - (Gate ③에서 질문) |
| 3 | 새 데이터셋 생성 권한 | 미결정 | - (Gate ③에서 질문) |
| 4 | 팀 웹서버 Superset 운영 조건 | 운영자 확인 중 | - (사용자가 웹서버 운영자에게 문의 중. 확인 전까지 Superset(및 캐시 서비스)은 로컬 `compose.yml`에만 포함하고 팀 웹서버 구성은 확정하지 않음) |
| 5 | 디자인 방향 | 결정 | C(3분할 작업공간) 기본 + 데이터셋 목록·권한 관리·가져오기 앞 두 단계는 B(콘솔형) (2026-10-11, Gate ①) |
| 6 | 수식 미리보기·자동완성을 위한 저장 전 수식 평가 경로 | 미결정 | - (Gate ③에서 결정) |
| 7 | Superset 차트 작성 화면(Explore)을 포털에서 어떻게 제공할지 | 미결정 | - (Gate ③에서 결정. Embedded SDK로 가능한 범위를 공식 문서로 확인한 뒤 결정) |

## Gate ② 진행 메모
- 마이그레이션 도구 비교안(architect)은 `_workspace/gate2/migration-tool-options.md`에 있다(승인 전 초안, Git 제외). **사용자가 D1~D7을 검토 중이다.** 결정이 나오기 전에는 env-engineer ⇄ qa-engineer 단계를 시작하지 않는다.
  - D1 도구, D2 동적 객체 분리, D3 마이그레이션 raw SQL 허용 범위, D4 실행 위치, D5 되돌리기 정책, D6 CI 빈 DB 검증 방식, D7 Superset 메타데이터 DB 분리
- 미결정 1번이 "제외"로 확정되어 Azure OpenAI 변수·Health 경로·체크리스트 항목을 만들지 않는다. 미결정 4번은 운영자 확인 중이며 Superset은 로컬 `compose.yml`에만 포함한다.

## Gate ③ 인계 사항
Gate ① 원본 대조(`docs/decisions/02-tech-reference.md`)에서 나온 세 가지는 설계 전에 반영한다.
- **붙여넣기 파서의 따옴표 안 탭 처리:** react-datasheet-grid의 `parseTextPlainData`는 따옴표 안의 줄바꿈만 셀 내용으로 유지하고 **탭은 따옴표 안에서도 셀을 나눈다.** 한 줄짜리 따옴표 셀은 따옴표가 그대로 남는다. 그대로 이식하지 말고 탭·따옴표·`\r` 케이스를 요구사항과 테스트 기준으로 설계한다.
- **Baserow 순환 검사기의 f-string raw SQL:** `circular_reference_checker.py`는 SQL을 f-string으로 조립한다. SQL 문자열 조립 금지 원칙과 충돌하므로 알고리즘만 참고하고, 구현은 SQLAlchemy 표현식 또는 파이썬 그래프 탐색으로 설계한다.
- **Superset RLS `clause` 서버 미검증:** 서버는 `clause`를 검증하지 않는다(`api.py`의 TODO). `GUEST_TOKEN_VALIDATOR_HOOK` 검증 추가 여부와 `clause` 생성 규칙(정수 ID·화이트리스트 식별자, 문자열 값 처리)을 설계한다.

- **RLS `clause`와 `CREATE VIEW`의 SQL 문자열 렌더링 문제:** Superset guest token의 RLS `clause`는 SQL 문자열이고, 수식 속 문자열 리터럴이 뷰 정의(DDL)로 렌더링되는 지점이 생긴다. `CREATE VIEW`에 bind parameter를 쓸 수 없다는 근거는 2012년 메일링 스레드 요약뿐이다. **Gate ③에서 PostgreSQL 공식 문서와 SQLAlchemy 공식 문서로 근거를 확인한 뒤 설계한다.** 설계 전에는 확정하지 않는다.
- 수식 범위(2번)가 정해져야 `references/baserow/`에서 참고할 모듈 범위(lookup·집계 포함 여부)를 확정할 수 있다.
