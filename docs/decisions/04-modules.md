# 04. 모듈 경계·기능↔Skill 대응·기능 단위 순서 (FU-1 범위)

**상태: 초안(승인 전)** — architect, 2026-10-11. S2 단계(골격 + 부록 A 사전). §6~§7은 05 작성 뒤 한 번 더 확인한다.
- Gate ③ MODULARIZE. 의존 결정: 브리프 5절 2·3·6·7·8(스텁 전제)·9·10·11번(`docs/gate-status.md`), 범위 `03b` 5절(FU-1), 실험 `03c`. 사용자 결정을 바꾸거나 확정하지 않으며 원문은 `03b n-n`·`03c X-n` 참조로만 건다.
- 표지: **[미답]** 사용자가 답하지 않아 기본값으로 쓴 곳 / **[승인 필요]** §9 목록 / **[A-27]** 별도 확인 중인 결과에 따라 달라지는 곳(결과를 가정하지 않음).

## 1. 목적·범위·읽는 법
- 목적: FU-1의 모듈 경계, 화면, 제품 Skill, 구현 순서, 합격 기준 개요를 정하고 05~08이 같이 쓸 이름(부록 A)을 고정한다.
- 범위: FU-1 = 데이터셋 만들기(열 정의) · 팀/정의 담당자/입력자 권한(인증 스텁) · 입력 그리드 · 같은 행 수식/수식 보기/미리보기 · Superset 데이터셋 등록/임베딩 대시보드 보기(`03b` 5-1). 나머지는 §10에 항목만 둔다. 승인된 기능 축소: 브리프 4.3 역할별 열 편집 권한은 후속, 01 디자인의 "역할×데이터셋 격자"는 "팀×사용자"로 변경(`03b` 5-2 K2).
- 문서 관계: **04**(모듈·Skill·순서·이름) → **05** API 계약 / **06** 데이터 모델 / **07** 수식 엔진 / **08** Superset 임베딩. 05는 06·07·08을 받아 쓰므로 마지막에 확정한다.
- 참조 규칙: ① 표·열·enum·역할·계정 이름은 부록 A가 기준이다. 05~08은 그대로 쓰고, 바꾸려면 부록 A를 먼저 고친 뒤 reviewer가 대조한다. ② 각 문서 맨 위에 의존 결정, 끝에 "후속 기능 단위에서 결정" 절을 둔다. ③ 구현 상세(클래스·SQL·props)는 담지 않는다.

## 2. 모듈 경계
backend는 `app/<모듈>/`에 `router`(API) · `service`(로직) · `repo`(데이터 접근) 3층, frontend는 `src/features/<모듈>/`(화면 + API 훅)이다. 모듈 이름은 후보다. 기존 `config.py`·`db.py`·`health.py`는 `core`로 본다.

### 2-1. 공통 계층
| 이름 | 책임 | 소유 | 의존 | 금지 · 확장점 |
| --- | --- | --- | --- | --- |
| `core` | 설정, 오류 형식, DB 세션(`bi_app`, 미리보기용 읽기 전용 트랜잭션), `/health`, 포트 정의(`DatasetSyncPort`, 정의 변경 훅), 정적 표 정의(`MetaData` 한 곳 = Alembic `target_metadata`) | 정적 표 정의만(쓰기 책임은 각 모듈) | 없음 | 슈퍼유저·`bi_owner` 접속 금지(시작 자가 점검). 업무 로직 금지 |
| `auth` | `current_user` 한 곳(신원 어댑터 → `CurrentUser`), 권한 판정(관리자 / 팀 정의 담당자·입력자 / 열람 = 인증된 모두) | 없음(`users`·`team_members` 읽기) | core | 스텁은 개발·시험 전용, 운영 설정에서 켜지면 시작 거부(`03b` 5-2 K3). 확장점: 신원 어댑터 교체(8번 미결정) |
| `ddl` | 런타임 동적 DDL 유일 모듈, `ds_`/`dv_`/`c_` 이름 규칙 함수 | `bi_data`의 표·뷰·인덱스·제약(생성·변경) | core | `text()`·`exec_driver_sql` 금지, 객체 종류 허용 목록(`bi-review` 7-4), 이 모듈 밖 DDL 금지, `bi_app`으로만 실행(`03b` 5-2 Z6) |

### 2-2. FU-1 기능 모듈
| 모듈 | 책임 | 소유 정적 표 | 소유 동적 객체 | 외부 의존(허용) | 확장점 |
| --- | --- | --- | --- | --- | --- |
| `access` | 팀·사용자·소속(역할) 관리, 비활성화, 최초 관리자 서버 명령, `/api/me` | `users` `teams` `team_members` | - | core, auth | 데이터셋별 예외 권한(후속) |
| `dataset` | 데이터셋·열 정의(타입, 필수·범위, 기준 날짜 열, 날짜 단위, 열 구분 태그), 정의 버전, 등록 + 원본 표 생성을 한 트랜잭션 | `datasets` `dataset_columns` | `ds_<번호>` (ddl 경유) | core, auth, ddl | 열 타입 등록, 검증 규칙 등록, 정의 변경 훅 호출 |
| `entry` | 한 기간 = 한 행 입력: 행 조회, 칸 단위 값 비교 갱신, 붙여넣기 일괄(충돌 시 전부 취소), 서버 재검증 | 없음 | `ds_<번호>` 행 읽기·쓰기(DDL 아님) | core, auth, dataset(정의 읽기) | 행·열 전환 보기를 나중에 추가할 수 있게 저장 형식 고정 |
| `formula` | 수식 파싱·정적 검사·순환 검사, `dv_` 뷰 생성·시작 시 재생성(정의 해시), 미리보기, 수식 보기, 오류 칸 목록 | `formulas` `formula_deps` | `dv_<번호>` (ddl 경유) | core, auth, dataset(정의 읽기), ddl | 함수 사전, 리터럴 렌더러 접점 한 곳 |
| `superset` | 서비스 계정으로 가상 데이터셋 등록·열 새로고침, 동기 상태, 대시보드 연결(관리자), 입장권 발급, 임베딩 | `superset_datasets` `superset_dashboards` | 없음(Superset 쪽 역할·계정은 `superset-init`) | core, auth, dataset(읽기), ddl(이름 규칙만), `httpx` → Superset | `DatasetSyncPort` 구현 |

## 3. 의존 방향 (순환 없음)
| 모듈 | 의존(→) | 의존받음(←) |
| --- | --- | --- |
| core | 없음 | 전부 |
| auth | core | access, dataset, entry, formula, superset |
| ddl | core | dataset, formula, superset(이름 규칙만) |
| access | core, auth | 앱 조립(`main.py`)만 |
| dataset | core, auth, ddl | entry, formula, superset |
| entry · formula · superset | 각각 core, auth, dataset (+ formula: ddl, superset: ddl 이름) | 없음 |
- 위상 순서: core → auth·ddl → access·dataset → entry·formula·superset. 마지막 세 모듈은 서로 의존하지 않는다.
- 역방향 호출은 `core` 포트로 뒤집는다: dataset이 정의 변경 훅을 호출하면 formula가 등록해 뷰를 재생성하고, 정의/뷰가 바뀌면 `DatasetSyncPort`를 호출하고 superset이 구현한다(커밋 뒤 동기 요청). 연결은 앱 팩토리 한 곳에서 한다.

## 4. 화면 목록 **[미답: K9, 기본값 "화면 목록 + 영역 개요"로 씀, 승인 때 확인]**
01 디자인: C(3분할 작업공간) 기본 + 목록·권한·연결 관리는 B(콘솔형), 1920×1080, Inspector 접기·폭 조절. 세부 화면은 소단위마다 만들고 완료 때 사용자가 확인한다.
| 화면 | 영역 개요 | Skill |
| --- | --- | --- |
| S1 포털 셸·접근 안내(B) | 상단 Navigation, 작업 팀 선택(여러 팀 소속), 미등록 사용자에게 "접근 권한이 없습니다". 개발 빌드 한정 스텁 신원 전환기 | permission-management |
| S2 데이터셋 목록(B) | 이름·팀·날짜 단위·생성자·생성일·동기 상태, 소속 팀 데이터셋 상단 정렬(`03b` 2-4), "새 데이터셋"(정의 담당자) | dataset-definition |
| S3 데이터셋 만들기(B 폼) | 팀·이름·날짜 단위 입력 후 작업공간으로 이동. 열은 작업공간에서 추가 | dataset-definition |
| S4 작업공간(C) | 중앙 입력 그리드, 우측 Inspector(열 기본·검증·수식), 수식 편집기(열 이름 칩·자동완성·쉬운 말 오류·미리보기 행), 계산 열 표시와 수식 보기(열람자 읽기 전용), 오류 칸 구별 표시 | data-entry, formula-column, dataset-definition |
| S5 점검(B) | 계산 오류 칸 목록(데이터셋·열·기간) | formula-column |
| S6 권한 관리(B, 관리자) | 팀×사용자 격자, 팀 만들기·소속·역할·비활성화, 저장 전 변경 요약 확인창 | permission-management |
| S7 대시보드 목록·보기 | 연결된 대시보드 목록, 선택 시 Embedded iframe, "차트 만들기" 새 창 링크와 작성자 안내문(차트에 시간 필터 필요, 팀 열) | dashboard-link |
| S8 대시보드 연결 관리(B, 관리자) | 대시보드 이름과 embedded uuid 수동 등록·해제 | dashboard-link |
| S9 관리자 현황(B, 관리자) | Superset 동기 상태, 뷰 재생성 실패(`/health` 본문과 같은 정보), 다시 시도 | dashboard-link |

## 5. 모듈 간 규칙·확장점
- 층 규칙: router는 service만, service는 자기 repo와 다른 모듈의 service 읽기 함수만 호출한다. SQL(SQLAlchemy 표현식)은 repo와 `ddl`에만 둔다. 다른 모듈의 표를 직접 쓰지 않는다.
- 경계 금지: 브라우저 → DB 직접 호출 금지. 브라우저 → Superset REST API 호출 금지(허용 접근은 Embedded iframe과 새 창 링크 둘뿐, 입장권은 FastAPI가 발급하고 서버가 직접 서명하지 않음). 프런트 API 경로는 `config.ts` 한 곳에서 `${basePath}/api`로 조립하고 하드코딩하지 않는다. 클라이언트가 보낸 `rls`·Superset 숫자 id는 받지 않는다(08). SQL 문자열 조립과 `text()` 금지.
- 확장점 합격선: 함수 추가 = 함수 사전 항목 1개 + 시험 사례(`03b` 5-2 K6) / 열 타입 추가 = 타입 등록 1곳 / 신원 방식 교체 = `auth` 1곳 / 보기 전환 = 저장 형식 변경 없이 화면만 추가.

## 6. 기능 ↔ 제품 Skill 대응표 (초안, 05 작성 뒤 재확인)
`skills/<기능>/SKILL.md`(제품 사용설명서, 형식 `product-skill-authoring`)다. `.claude/skills`·`.claude/agents`(개발 하네스)와는 별개이며, FU-1 Skill 5개는 소단위 완료 때 코드와 함께 만들고 연관 Skill은 양방향으로 적는다. 기존 `skills/local-environment`는 유지한다. API 경로는 후보이며 05에서 확정한다.
| 소단위 | Skill 폴더 | 사용자 관점 기능 | 주요 UI | 주요 API 그룹(후보) | 주요 DB | 연관 Skill |
| --- | --- | --- | --- | --- | --- | --- |
| FU-1a | `permission-management` | 팀·사용자·소속·역할 관리, 내 정보 | S1, S6 | `/api/me` `/api/users` `/api/teams` | users, teams, team_members | dataset-definition, dashboard-link |
| FU-1b | `dataset-definition` | 데이터셋 만들기, 열 정의(타입·필수·범위·기준 날짜 열·날짜 단위·태그) | S2, S3, S4 Inspector | `/api/datasets` `/api/datasets/{id}/columns` | datasets, dataset_columns, `ds_*` | permission-management, data-entry, formula-column, dashboard-link |
| FU-1c | `data-entry` | 한 기간=한 행 입력, 칸 편집, 엑셀 붙여넣기 | S4 그리드 | `/api/datasets/{id}/rows` | `ds_*` | dataset-definition, formula-column |
| FU-1d | `formula-column` | 같은 행 수식, 검사·미리보기, 수식 보기, 오류 칸 | S4 수식 편집기, S5 | `/api/datasets/{id}/formulas` (검사·미리보기·오류 칸) | formulas, `dv_*` | dataset-definition, data-entry, dashboard-link |
| FU-1e | `dashboard-link` | Superset 등록, 대시보드 연결·보기, 차트 작성 링크 | S7, S8, S9 | `/api/dashboards` (입장권, 동기 상태) | superset_datasets, superset_dashboards | dataset-definition, formula-column, permission-management |
- `feature-unit`은 "한 단위 = Skill 하나"이므로 FU-1을 Skill 단위인 1a~1e로 나눠 각각 완료 기준을 적용한다 **[확인 필요]**.

## 7. 기능 단위 순서 (초안, 05 작성 뒤 재확인)
### 7-1. FU-1 내부 구현 순서
| 순서 | 소단위 | 백엔드 → 프런트 | 선행 | 메모 |
| --- | --- | --- | --- | --- |
| 0 | 공통 기반 | core·auth 스텁·오류 형식·`/health` 필드·시작 자가 점검·정적 `MetaData` → 셸·라우팅(STRIP=true 딥링크)·`config.ts` | EW-1, EW-3, EW-4(`03b` 5-4) | 모든 쓰기 API가 `current_user`에 의존 |
| 1 | FU-1a | users·teams·team_members, 최초 관리자 명령, `/api/me`·팀·사용자 → 팀 선택, S6 | 0 | 사람 역할 권한 시험 시작 |
| 2 | FU-1b | datasets·dataset_columns, `ddl`(등록 + `ds_` 생성 한 트랜잭션), 정의 버전 → S2, S3, Inspector | 1 | `bi-review` 7-4 첫 적용. 열 이름 노출 방식은 **[A-27]** 결과 후 확정 |
| 3 | FU-1c | 행 조회, 칸 단위 값 비교 갱신(pg8000 `rowcount` 첫 시험), 붙여넣기 일괄 → 그리드, 붙여넣기 파서 | 2 | 1d와 병렬 가능 |
| 3 | FU-1d | formulas, 파서·정적 검사·순환 검사, `dv_` 생성·정의 해시·시작 시 재생성, 미리보기, 수식 보기, 오류 칸 → 수식 편집기, S5 | 2 | 데이터셋마다 뷰 1개(수식 열이 없어도, 팀 열 포함) **[제안: 06·07에서 확정]** |
| 4 | FU-1e | superset_*, 서비스 계정 등록, 연결 uuid 등록, 입장권 발급(`rls` 빈 목록, 속도 제한) → S7, S8, S9 | 1d | 하위 경로(STRIP true/false) + Embedded 재검증 |

### 7-2. FU-1 다음 단위 순서 제안 (세부 설계 없음, 의존 순서)
| 단위 | 이유 |
| --- | --- |
| FU-2 보관·삭제 정책 + 변경 기록 | 이후 단위가 쓰기·뷰 흐름을 늘리기 전에 보관 조건(뷰·인덱스)과 `audit_log`를 먼저 넣어야 재작업이 적다 |
| FU-3 기준값 표 | 수식 확장의 선행(이름 + 값 + 적용 시작일) |
| FU-4 수식 확장(이전 행 참조, 같은 데이터셋 집계, 기준값 호출) | 기준 날짜 열 필수 조건이 켜지는 첫 단위, FU-3 뒤 |
| FU-5 참조 열 | 입력 검증 + 점검 화면 확장, 보관·삭제 정책(끊어진 참조) 뒤 |
| FU-6 공통 요약 | 수식 열을 최종값으로 연결하므로 FU-4 뒤 |
| FU-7 엑셀 가져오기 | 그리드·정의·참조 열 검증을 재사용, 업로드 상한(EW-2)과 적재 시간 측정이 첫 작업. 업무 가치가 크면 FU-2 직후로 당길 수 있음(비구속) |

## 8. FU-1 합격 기준 개요 (`03b` 5-2에 있는 것만, 상세는 07·08)
- 수식 미리보기와 뷰 결과의 **불일치 0건**(X-26에서 `CAST` 적용 후에도 남은 22건의 원인 분석 포함).
- X-26 주입 사례 10종 + 역슬래시 사례를 **회귀 시험으로 고정**. 완화책 3가지(세션 `standard_conforming_strings` 고정, 역슬래시·제어문자·NUL 거부, 생성 후 재읽기 비교·불일치 시 롤백)와 런타임 DDL `bi_app` 실행을 시험한다.
- 인증 스텁이 운영 환경 설정에서 켜져 있으면 backend가 시작을 거부함을 시험한다(`bi-review` 7-5).
- K6 핵심 함수 전부에 시험 사례가 있고 함수 추가가 사전 항목 1개로 끝난다. K7: 빈 칸은 미입력으로 유지되고 결과도 빈 값, 글자 비교는 대소문자 무시, 오류 칸은 빈 값으로 저장·구별 표시·점검 목록 노출.
- K12 열 이름 방식은 **[A-27]** 확인 후 확정(안 되면 결과와 대안을 보고하고 멈춘다).
- 공통 완료 기준은 `feature-unit`, 권한 매트릭스·왕복 시험은 EW-1 완료 기준(`03b` 3-6 BY4)을 따른다.

## 9. 승인 필요 목록 (지금은 요청이 아님. `03b` 3-7·4-7에서 승인된 것은 제외)
- 새 환경변수 후보 `AUTH_STUB_ENABLED`(스텁 켜기). 운영 판별에 기존 `APP_ENV`(코드 기본값 `local`)를 쓸지 포함해 설정 방식을 적용 전에 승인받는다.
- 새 런타임 의존성(FU-1 착수 때 패키지·라이선스 확인 후 요청): backend `lark`, frontend 라우터·AG Grid Community·Superset Embedded SDK. `httpx`는 승인됨.
- 기준선과 다른 설정·하네스 문구: AP-5(db-bootstrap의 `public` CREATE), AP-9(`bi_readonly` `statement_timeout`), AP-10(`bi-review` 7-4 시퀀스·Alembic `Operations` 문구), AP-1·AP-2(`bi-review` 7-2 확장, 가상 데이터셋 SQL 고정). 06·08 승인 때 각각 요청한다.
- 발급 전용 계정 변수 이름 확정(08, 변수 자체는 승인됨). 조건부: `superset-init` 확장, backend `SUPERSET_APP_ROOT` 전달, compose `tmpfs`/`mem_limit`은 필요해질 때 보고 후 적용.
- 에이전트 모델 재판단(FU-1 착수 전)은 제안만 하며 승인 전에는 바꾸지 않는다. 첫 관리자 서버 명령의 운영 서버 실행 가능 여부는 운영자 확인 항목(`deploy-coordination.md` 35번).

## 10. 후속 기능 단위에서 결정
- 범위 제외(`03b` 5-1): 기준값 표, 이전 행 참조, 같은 데이터셋 집계, 엑셀 가져오기, 참조 열, 공통 요약, 보관·삭제 정책, 변경 기록. 기존 엑셀 이관 도구는 범위 제외(`03b` 4-6).
- 미답 질문: K4 변경 기록 보존·열람·범위, K5 소급 변경과 마감, K8 가져오기 추가·교체, K10 보관·비활성 체감 규칙, K11 ㄱ·ㄴ·ㄹ(재업로드, 시트, 데이터셋 개수 상한).
- 8번 인증 방식(헤더/토큰/자체 로그인/SSO), 스텁 안전장치 최종 설계, X-19, Explore 자동 로그인 연동.
- 정규식·유일성 검증과 정규식 평가 의존성(AP-3), 선택 목록 외 참조 타입, 데이터 있는 열의 타입 변환 확인 흐름(FU-1 포함 여부는 06에서 제안).
- 역할별 열 편집 권한, 데이터셋별 예외 권한, 행·열 전환 보기, 같은 날짜에 여러 행이 필요한 데이터셋(`03b` 3-4 Y9 (a)).
- 가져오기 구현 의존성(`python-multipart`·`openpyxl`·`defusedxml`·`rapidfuzz`)과 상한(EW-2), 그 밖의 수식 함수 확장(엑셀 실제 함수 목록 U9).

---

## 부록 A. 용어·엔티티 사전 (05~08이 그대로 쓴다. **임의 변경 금지**: 바꾸려면 이 부록을 먼저 고친다)
(결정) = `03b` 근거가 있는 이름, (제안) = architect 제안으로 승인 때 확인. 영문 이름은 확정 후보다. 타입·제약은 06이 정한다.

### A-1. 용어
| 용어 | 뜻 | 식별자·표기 |
| --- | --- | --- |
| 팀 | 데이터셋 소유 단위. 관리자가 만들고 소속을 지정, 한 사용자가 여러 팀에 속할 수 있음 | `teams`, 불변 `code`(필터 값), 바꿀 수 있는 `name` |
| 관리자 / 정의 담당자 / 입력자 | 팀·소속 관리 등 전체 권한 / 팀의 데이터셋 생성·열·수식 편집 / 데이터 입력 | `users.is_admin` / `team_members.role` = `definer` / `entry`. 정의 담당자의 입력 가능 여부는 06 매트릭스에서 제안 **[미답]** |
| 열람자 | 인증된 모든 사용자(전 팀 데이터·수식 열람) | 별도 역할 값 없음(`03b` 1-3) |
| `current_user` | 접속자를 알려 주는 단 한 곳, 스텁은 개발·시험용 신원 흉내 | `CurrentUser`(id, display_name, is_active, is_admin, memberships) (제안) |
| 데이터셋 | 화면 용어("표"·"뷰"는 화면에서 안 씀). 내부 번호 = `datasets.id` | 원본 표 `bi_data.ds_<번호>`, 수식 뷰 `bi_data.dv_<번호>` (결정 2-6) |
| 열 | 원본 열(`raw`) 또는 계산 열(`formula`). 내부 번호 이름과 표시 이름이 따로 있음 | `c_<번호>`(번호 = `dataset_columns.id`), `display_name`. Superset 표시 방식 **[A-27]** |
| 기준 날짜 열 / 날짜 단위 | 기간을 정하는 `date` 열(이전 행·기준값·요약 연결에 쓸 때만 필수) / 일·월·연, 시각 없음, 기간의 첫날로 저장 | `datasets.base_date_column_id`, `datasets.date_unit` (결정 2-2, 2-3 W3) |
| 한 기간 = 한 행 | 저장·입력 모두 기간 하나가 행 하나, 항목은 열 | 기준 날짜 열이 있으면 같은 기간 행은 기본 하나(`03b` 3-4 Y9) |
| 팀 열 | 모든 `dv_` 뷰에 자동으로 붙는 열, 값은 팀 코드 | 출력 열 이름 `team`(예약) |
| 열 구분 태그 | 정의 담당자가 열에 붙이는 이름표, 같은 태그 열의 조건 합산에 쓴다 | `dataset_columns.tag`(제안, 상세 07) |
| 함수 사전 | 수식 함수를 이름 → 규칙·변환으로 등록하는 구조 | formula 모듈 확장점(결정 5-2 K6) |
| 미입력 / 오류 칸 | 값이 비어 있음(0이 아님), 결과도 빈 값 / 계산 오류로 빈 값이 저장된 칸(화면에서 구별, 점검 목록) | NULL (결정 5-2 K7) |
| 수식 보기 / 미리보기 | 계산 열의 수식을 열 이름으로 풀어 읽기 전용 표시 / 저장 전 일부 행 계산(뷰와 같은 변환기) | 07에서 형식 확정(결정 1-6, 2-3 W7) |
| 정의 버전 / 정의 해시 | 데이터셋 정의 변경 번호(충돌 확인) / 뷰 SQL 구조 해시(시작 시 재생성 판단) | `datasets.def_version`, `datasets.def_hash` (결정 3-4, 2-3 W2) |
| 정적 표 / 동적 객체 | Alembic이 관리하는 포털 표(`public`, 등록 표 포함) / 런타임 DDL이 만드는 `ds_`·`dv_`(`bi_data`) | 소유 계정 `bi_owner` / `bi_app` (결정 2-3 W1, 3-2) |
| 서비스 계정 / 발급 전용 계정 | Superset 데이터셋 등록·새로고침용 / 입장권 발급용(서로 분리) | `SUPERSET_SERVICE_USER`·`_PASSWORD`(결정) / `SUPERSET_GUEST_ISSUER_USER`·`_PASSWORD`(후보, 08에서 확정) |
| 입장권(guest token) / embedded uuid | 대시보드 임베드용 5분짜리 접속 허가, `rls`는 항상 빈 목록 / 관리자가 수동 등록하는 임베드 번호 | `superset_dashboards.embedded_uuid` (결정 4-2) |
| 가상 데이터셋 | `dv_` 뷰를 읽는 Superset 데이터셋(읽기 쉬운 이름) | 이름 `[<팀 표시 이름>] <데이터셋 표시 이름>` (제안, 결정 3-3 Y6) |

### A-2. 엔티티(정적 표, `public`)
| 표 | 핵심 필드 후보 | 소유 모듈 |
| --- | --- | --- |
| `users` | id, login_id(유일, 8번 후 종류 확정), display_name, is_admin, is_active, created_at | access |
| `teams` | id, code(유일·불변), name, is_active, created_at | access |
| `team_members` | team_id, user_id, role(`team_role`), PK(team_id, user_id) | access |
| `datasets` | id, team_id, name, date_unit, base_date_column_id, status, def_version, def_hash, created_by, created_at | dataset |
| `dataset_columns` | id, dataset_id, display_name, type, kind, required, rules(범위 등), tag, position | dataset |
| `formulas` / `formula_deps` | column_id(유일), expression(원문), ast(열 번호 참조), ast_hash / column_id, depends_on_column_id | formula |
| `superset_datasets` | dataset_id, superset_dataset_id, display_name, sync_status, synced_at | superset |
| `superset_dashboards` | id, name, embedded_uuid(유일), is_active, created_at | superset |
- 이름 예약(후속 단위가 정함): `audit_log`(`03b` 3-6 BY6 이름), 기준값·공통 지표·연결·가져오기 원본 정보·글자 상수 표. 동적 객체 이름은 번호 기반만 쓴다.

### A-3. enum 값과 계정·객체 이름
| 이름 | 값 · 설명 |
| --- | --- |
| `team_role` | `definer`, `entry` (관리자는 `users.is_admin`, 저장 방식 enum/CHECK는 06) |
| `date_unit` | `day`, `month`, `year` |
| `column_type` | `text`, `number`, `date`, `boolean`, `choice` (참조 타입 `reference`는 후속) |
| `column_kind` | `raw`, `formula` |
| `dataset_status` | `active`, `archived` (`deleted`는 후속, FU-1은 `active`만 사용) |
| `sync_status` | `pending`, `registered`, `failed` (`failed`는 제안) |
| 충돌 코드(05 후보) | `CELL_CONFLICT`, `PASTE_CONFLICT`, `DEFINITION_VERSION_MISMATCH` **[미답: BK6]** |
| DB 계정·schema | `bi_owner`, `bi_app`, `bi_readonly`, `bi_data`, `public` (결정 3-2) |
| Superset | `bi_guest`(guest 역할, 결정 4-2 Z2), 서비스 계정 / 발급 전용 계정(위), 작성자 역할(Gamma 복사본 + schema 보조 역할, 이름은 08) |
