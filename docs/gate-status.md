# Gate 진행 상태

| Gate | 상태 | 승인일 | 승인 내용 | 관련 문서 |
| --- | --- | --- | --- | --- |
| ① RESEARCH & DECIDE | 승인 | 2026-10-11 | 디자인: C(3분할 작업공간) 기본 + 데이터셋 목록·권한 관리·가져오기 앞 두 단계는 B(콘솔형). 기준 해상도 1920×1080, Inspector는 접기·폭 조절. Reference 5개 모두 확보(지목 파일만) | `docs/decisions/01-design-direction.md`, `docs/decisions/02-tech-reference.md`, `references/` |
| ② ENVIRONMENT BOOTSTRAP | 대기 | - | - | - |
| ③ MODULARIZE | 대기 | - | - | - |
| ④ 기능 개발 | 대기 | - | - | - |

## 미결정 사항 (브리프 5절)
| 번호 | 질문 | 상태 | 답변 |
| --- | --- | --- | --- |
| 1 | Azure OpenAI 항목 처리 | 미결정 | - (Gate ②에서 질문, 웹서버 운영자 확인 필요) |
| 2 | 수식 범위 첫 버전 | 미결정 | - (Gate ③에서 질문) |
| 3 | 새 데이터셋 생성 권한 | 미결정 | - (Gate ③에서 질문) |
| 4 | 팀 웹서버 Superset 운영 조건 | 미결정 | - (Gate ②에서 질문, 웹서버 운영자 확인 필요) |
| 5 | 디자인 방향 | 결정 | C(3분할 작업공간) 기본 + 데이터셋 목록·권한 관리·가져오기 앞 두 단계는 B(콘솔형) (2026-10-11, Gate ①) |
| 6 | 수식 미리보기·자동완성을 위한 저장 전 수식 평가 경로 | 미결정 | - (Gate ③에서 결정) |
| 7 | Superset 차트 작성 화면(Explore)을 포털에서 어떻게 제공할지 | 미결정 | - (Gate ③에서 결정. Embedded SDK로 가능한 범위를 공식 문서로 확인한 뒤 결정) |

## Gate ③ 인계 사항
- **RLS `clause`와 `CREATE VIEW`의 SQL 문자열 렌더링 문제:** Superset guest token의 RLS `clause`는 SQL 문자열이고, 수식 속 문자열 리터럴이 뷰 정의(DDL)로 렌더링되는 지점이 생긴다. `CREATE VIEW`에 bind parameter를 쓸 수 없다는 근거는 2012년 메일링 스레드 요약뿐이다. **Gate ③에서 PostgreSQL 공식 문서와 SQLAlchemy 공식 문서로 근거를 확인한 뒤 설계한다.** 설계 전에는 확정하지 않는다.
- 수식 범위(2번)가 정해져야 `references/baserow/`에서 참고할 모듈 범위(lookup·집계 포함 여부)를 확정할 수 있다.
