---
name: bi-review
description: BI-Wizard 변경 사항을 읽기 전용으로 리뷰하는 체크리스트와 보고 형식. 라이선스, 환경변수, Secret, SQL 조립, 마이그레이션(변수 보간, DROP 확인, downgrade), Enterprise 패키지, 코드와 Skill 동기화, 미결정 사항 준수를 점검한다. reviewer 에이전트가 사용한다. 리뷰어는 파일을 수정하지 않는다.
---

# bi-review — 읽기 전용 리뷰 기준

## 원칙
- 리뷰어는 코드, 테스트, 설정, 문서를 수정하지 않는다. 발견 사항과 수정 방향만 보고한다.
- 근거 없는 지적을 하지 않는다. 모든 발견 사항에 파일과 줄 번호를 붙인다.
- 문제가 없으면 "발견 없음"과 점검한 항목을 적는다.

## 입력
메인이 변경 파일 목록과 diff를 `_workspace/review/`에 넣어 준다. 리뷰어에게 Bash가 없으므로 git 명령을 직접 실행하지 않는다.

## 점검 항목

### 1. 라이선스 (차단)
- 새로 추가된 패키지의 라이선스를 확인한다. 허용형은 MIT, BSD, Apache 2.0, PSF, PostgreSQL License다.
- 차단: `ag-grid-enterprise`, AGPL, GPL, EUPL, Sustainable Use License, Redis 7.4 이후 라이선스
- 라이선스가 불분명하면 "불명확 (확인 필요)"로 중요 항목에 올린다.

### 2. Secret (차단)
- 키, 비밀번호, 토큰이 코드, 이미지 설정, 프런트 번들, 로그, 문서에 들어가지 않았는지 확인한다.
- `.env` 파일이 커밋 대상에 포함되지 않았는지 확인한다.

### 3. SQL 조립 (차단)
- 문자열 연결, f-string, `%` 포맷, `.format()`으로 SQL을 만들지 않았는지 확인한다.
- SQLAlchemy 표현식을 썼는지 확인한다.
- **예외(D3, `docs/decisions/03-migration-tool.md`):** 마이그레이션 디렉터리(`backend/migrations/`) 안에서만 **보간이 전혀 없는 고정 SQL 문**(`op.execute("...")` 등)을 허용한다. 마이그레이션 안에서도 변수 보간은 차단이다. 마이그레이션 디렉터리 밖의 raw SQL은 예외 없이 차단이다.

### 4. 환경변수 (중요)
- `.env.example`의 canonical name과 맞는지 확인한다.
- 같은 의미의 새 이름이 생기지 않았는지 확인한다.

### 5. 경계 (중요)
- 브라우저 코드가 DB나 Superset 내부를 직접 호출하지 않는지 확인한다.
- API 주소가 상대경로 `/api`인지 확인한다.

### 6. Skill 동기화 (중요)
- 기능 코드가 바뀌었는데 `skills/<기능>/SKILL.md`가 갱신되지 않았다면 완료로 보지 않는다.
- 연관 Skill의 영향도를 확인했는지 본다.

### 7. 미결정 사항 (차단)
- 브리프 5절의 미결정 항목을 임의로 정한 흔적이 없는지 확인한다. `docs/gate-status.md`의 미결정 표가 현재 상태의 정본이다.
- 수식 범위(2번), 생성 권한(3번), Superset 운영 조건(4번), 수식 평가 경로(6번), Explore 제공 방식(7번)이 승인 전에 코드에 확정되어 있으면 차단 항목이다.
- 결정된 항목을 어기면 차단이다. Azure OpenAI(1번)는 "제외"로 결정됐으므로 `AZURE_OPENAI_*` 변수, `/health/azure-openai`, Azure OpenAI 호출 코드가 사용자 승인 없이 들어 있으면 차단한다. 디자인(5번) 결정은 `docs/decisions/01-design-direction.md`를 따른다.

### 7-1. 마이그레이션 (D2·D3·D5·D4·D6·D7, `docs/decisions/03-migration-tool.md`)
- **D3 (차단):** 마이그레이션 파일에서 `op.execute`, `text()`, `connection.execute` 등에 넘기는 SQL 문자열에 f-string, `%`, `.format()`, `+` 연결이 있는지 확인한다. 하나라도 있으면 차단이다. 마이그레이션 디렉터리 밖에서 raw SQL을 쓰면 차단이다(점검 항목 3).
- **D2 안전장치 (차단):** 마이그레이션에 `DROP`(`op.drop_table`, `op.drop_column`, `op.drop_index`, `op.drop_constraint`, SQL의 `DROP` 등)이 있는지 확인한다. 있으면 **사용자 확인 기록**(커밋 메시지나 변경 요약의 "DROP 확인: 사용자 승인" 문구)이 있는지 본다. 기록이 없으면 차단이다. D2(동적 객체 분리 방식)는 Gate ③ 결정 전이므로, 사용자 데이터셋 테이블·수식 뷰가 삭제 대상에 섞였는지도 본다.
- **D5 (중요):** 모든 revision에 `downgrade()`가 실제로 구현되어 있는지(`pass`, `NotImplementedError`만 있으면 미구현) 확인한다. upgrade → downgrade → upgrade 왕복 테스트 결과(qa-engineer 보고)가 첨부되어 있는지 본다. 운영 문제를 되돌리기로 해결하라는 문구나 스크립트가 있으면 지적한다(수정 마이그레이션 추가가 원칙).
- **D4 (중요):** `compose.yml`에 backend 이미지를 재사용하는 일회성 `migrate` 서비스가 있고, `backend`가 `migrate`의 `service_completed_successfully`에 의존하는지 확인한다.
- **D6 (중요):** 테스트용 PostgreSQL 서비스가 `tmpfs` 데이터이고 compose profile로 평소에는 뜨지 않는지 확인한다. 정리 방법이 `-v` 없는 `docker compose down`인지 본다(점검 항목 8과 같이).
- **D7 (중요):** Superset 메타데이터가 우리 앱 DB와 **별도 데이터베이스**인지, Superset이 업무 데이터를 읽는 연결이 **읽기 전용 계정**(쓰기 권한 없음)인지 확인한다. Superset 연결 문자열이나 설정에 앱 DB 소유자 계정이 쓰이면 차단이다.
- 마이그레이션 도구는 Alembic이다. 다른 도구(Flyway, Atlas 등)나 앱 시작 시 `create_all`로 스키마를 만드는 코드가 새로 들어오면 사용자 승인 여부를 확인한다.

### 8. 파괴적 명령 (차단)
- 스크립트나 문서가 다음을 실행하도록 쓰지 않았는지 확인한다: `.env` 삭제, `rm -rf`, `git clean -fdx`, `git reset --hard`, `docker compose down -v`

### 9. BAT 파일 (권장)
- BAT 파일은 작성만 되어 있어야 한다. Linux에서 실행한 흔적이 없어야 한다.
- 경로 구분자와 인코딩(UTF-8 BOM 여부)을 확인한다.

### 10. 운영 가이드 준수 (중요)
- FastAPI, PostgreSQL, React, Docker Compose, Jenkins 기준을 따르는지 확인한다.
- Frontend 컨테이너에 전체 `.env`가 전달되지 않는지 확인한다.

## 심각도
| 심각도 | 의미 | 예 |
| --- | --- | --- |
| 차단 | 머지 전에 반드시 고친다 | Secret 노출, 금지 라이선스, SQL 조립(마이그레이션 변수 보간 포함), 확인 없는 `DROP`, 미결정 사항 확정 |
| 중요 | 기능이나 계약에 영향이 있다 | Skill 미갱신, 계약과 다른 응답, 환경변수 중복 |
| 권장 | 개선하면 좋다 | 이름 개선, 테스트 보강 |

## 보고 형식
| 심각도 | 위치 | 근거 | 담당 | 수정 방향 |
| --- | --- | --- | --- | --- |

- 담당은 `backend-dev`, `frontend-dev`, `env-engineer`, `architect` 중 하나로 적는다.
- 같은 원인의 항목은 묶는다.
- 마지막 줄에 점검한 항목 번호 목록을 적는다.

## 관련 Skill
- `feature-unit`: 완료 기준
- `product-skill-authoring`: 제품 Skill 형식
