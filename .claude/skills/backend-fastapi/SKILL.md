---
name: backend-fastapi
description: BI-Wizard 백엔드(FastAPI, SQLAlchemy, PostgreSQL)의 구현 규칙. 엑셀 가져오기, 데이터셋 정의, 엑셀식 수식 파서와 SQL 뷰 생성, 권한, Superset guest token 발급 코드를 작성할 때 사용한다.
---

# backend-fastapi — 백엔드 구현 규칙

## 고정 기술
- FastAPI, SQLAlchemy, PostgreSQL. 다른 프레임워크나 ORM으로 바꾸지 않는다.
- REST를 기본으로 한다. 실시간 기능이 꼭 필요할 때만 WebSocket이나 SSE를 검토한다.
- DB 마이그레이션 도구는 **Alembic**이다(`docs/decisions/03-migration-tool.md`). 다른 도구로 바꾸거나 앱 시작 시 `create_all`로 스키마를 만들지 않는다.

## 필수 규칙
- **Health 우선:** `/health`, `/health/db`를 업무 API보다 먼저 만든다.
- **SQL 문자열 금지:** 수식→SQL 변환을 포함해 SQL을 문자열로 조립하지 않는다. SQLAlchemy Core 또는 ORM 표현식을 쓴다.
- **단일 통로:** 브라우저의 모든 데이터 요청은 FastAPI를 거친다.
- **하위 경로:** FastAPI는 `APP_BASE_PATH`를 `root_path`로 읽는다. 프록시가 접두를 떼고 넘기는 방식과 그대로 넘기는 방식을 설정값만으로 전환할 수 있어야 한다(`docs/decisions/03a-deploy-environment.md`). 경로 접두를 코드에 하드코딩하지 않는다.
- **Secret:** DB 비밀번호, 키는 환경변수에서만 읽는다. 로그와 응답에 넣지 않는다.
- **환경변수:** `.env.example`의 canonical name만 쓴다.
- **라이선스:** 허용형 패키지만 추가한다. 추가 전 `bi-review`의 라이선스 항목을 확인한다.

## DB 마이그레이션 (Alembic, `docs/decisions/03-migration-tool.md`)
- 마이그레이션 파일은 마이그레이션 디렉터리(제안: `backend/migrations/`) 안에만 둔다. 스키마 변경은 항상 revision으로 만든다.
- **허용(D3):** `op.*`, SQLAlchemy 표현식, **보간이 전혀 없는 고정 SQL 문자열**(`op.execute("...")`). 뷰·확장은 autogenerate가 다루지 않으므로 이 방식으로 수동 작성한다.
- **금지(D3):** SQL에 변수를 넣는 f-string, `%`, `.format()`, `+` 연결. 사용자 입력과 환경변수를 SQL 문자열에 넣지 않는다. 마이그레이션 디렉터리 밖의 코드는 위 "SQL 문자열 금지" 규칙을 그대로 따른다.
- **`downgrade()` 필수(D5):** 모든 revision에 실제 동작하는 `downgrade()`를 작성하고, 빈 DB에서 upgrade → downgrade → upgrade 왕복 테스트를 통과시킨다. 운영 중 문제는 되돌리기가 아니라 **수정 마이그레이션을 추가**해서 대응한다.
- **`DROP` 확인(D2 안전장치):** autogenerate 초안에 `DROP`(테이블, 열, 인덱스, 제약)이 있으면 적용하기 전에 메인을 통해 사용자 확인을 받는다. 확인 결과를 변경 요약(커밋 메시지)에 적는다. 확인 전에는 적용하지 않는다. 사용자가 런타임에 만드는 데이터셋 테이블·수식 뷰가 삭제 후보에 섞이는지 특히 살핀다. 동적 객체 분리 방식(D2)은 Gate ③에서 정한다.
- 실행은 compose의 일회성 `migrate` 서비스(backend 이미지 재사용)가 한다. 앱 코드가 시작 시 마이그레이션을 실행하지 않는다.
- DB 계정: 마이그레이션과 앱 쓰기는 앱 계정, Superset 데이터 연결은 읽기 전용 계정이다. Superset 메타데이터는 별도 데이터베이스(D7)이므로 우리 Alembic이 건드리지 않는다.

## 수식 엔진 (lark 기반)
- 파서는 lark(MIT)로 직접 작성한다. 엑셀 수식 전용 라이브러리 중 EUPL 등 비허용 라이선스는 쓰지 않는다.
- 첫 버전 범위는 브리프 5절 2번 답에 따른다. 답이 없으면 구현하지 않는다.
- 엑셀과 의미 차이를 테스트로 고정한다.
  - 빈 셀의 값(0인지 빈 문자열인지)
  - 날짜 연산(엑셀 날짜 일련번호와 SQL 날짜 차이)
  - 문자열 비교(대소문자, 공백)
- **순환 참조 검출:** 수식 의존 그래프에서 사이클을 찾으면 저장을 막고, 사용자가 이해할 말로 오류를 낸다. SQL 오류 메시지를 그대로 노출하지 않는다.
- **열 이름 변경:** 수식 안의 참조를 함께 고친다. 연쇄 수정이 실패하면 변경을 롤백한다.

## 엑셀 가져오기
- 라이브러리: openpyxl, pandas, rapidfuzz(열 이름 유사도)
- 처리 순서: 시트·범위 선택 → 헤더 행 자동 탐지(사용자 수정 가능) → 열별 타입 추론 → 제안 → 사용자 확인
- 표 형태 범위만 다룬다. 병합 셀과 다단 헤더는 범위 밖이므로 명확한 오류를 낸다.
- 확인 후 PostgreSQL에 테이블을 만들고, 등록 테이블에 소유자, 원본 파일명, 생성일, 스키마를 기록한다.
- 같은 양식 재업로드는 저장된 스키마로 매핑한다. 추가 또는 교체를 사용자가 고른다.
- 데이터가 있는 열의 타입 변경은 변환 미리보기를 거쳐 사용자 확인을 받은 뒤에만 실행한다.

## Superset 연동
- Superset 내부 코드를 수정하지 않는다.
- guest token은 FastAPI가 발급한다. 만료 시간과 대상 대시보드를 최소 범위로 제한한다.
- 차트가 읽는 데이터셋은 뷰다. 여러 표를 넘나드는 분석은 뷰로 미리 만든다.

## 테스트
- pytest를 쓴다.
- 수식 엔진은 변환 결과와 계산 결과를 모두 테스트한다.
- DB를 쓰는 테스트는 실제 PostgreSQL 컨테이너 또는 테스트 전용 DB를 쓴다. 운영 DB를 쓰지 않는다. 마이그레이션 왕복 테스트는 compose의 tmpfs 테스트 전용 PostgreSQL 서비스(profile `test`)를 쓴다(D6).

## 관련 Skill
- `feature-unit`: 완료 기준
- `product-skill-authoring`: 기능 Skill 작성
- `modularize`: 계약과 모듈 경계
