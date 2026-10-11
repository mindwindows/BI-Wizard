---
name: product-skill-authoring
description: 저장소 루트 skills/<기능>/SKILL.md, 즉 제품 기능 사용설명서를 작성하거나 갱신하는 절차와 형식. 기능 코드를 바꿀 때, local-environment Skill을 만들 때 사용한다. 개발용 하네스인 .claude/skills와는 다른 파일이다.
---

# product-skill-authoring — 제품 기능 Skill 작성

## 목적
제품 기능 Skill은 사람과 AI가 기능의 목적, 사용법, 검증법을 추측하지 않고 알 수 있게 하는 사용설명서다. 코드가 바뀌면 같은 작업에서 함께 바꾼다.

## 두 종류의 skills를 구분한다
| 위치 | 내용 | 독자 |
| --- | --- | --- |
| `skills/<기능>/SKILL.md` (저장소 루트) | 제품 기능 사용설명서 | 사람, 모든 AI 도구 |
| `.claude/skills/<이름>/SKILL.md` | 개발용 하네스 (이 프로젝트를 개발하는 에이전트 팀의 절차) | Claude Code 개발 에이전트 |

이 스킬은 전자만 다룬다. 후자를 수정하지 않는다.

## 위치와 이름
- 기능마다 폴더 하나: `skills/<기능-영문-kebab-case>/SKILL.md`
- 첫 번째 Skill은 `skills/local-environment/SKILL.md`다 (Gate ②).
- 예: `skills/excel-import/`, `skills/dataset-definition/`, `skills/formula-column/`, `skills/data-entry/`, `skills/dashboard-link/`, `skills/permission-management/` (확정은 Gate ③)

## 필수 항목 (9개)
모든 항목을 채운다. 해당 없는 항목은 "해당 없음"과 이유를 적는다.

```markdown
---
name: <기능-영문-kebab-case>
description: <이 기능이 무엇을 하고 언제 쓰는지 한두 문장. 사용자가 말할 법한 표현을 포함한다.>
---

# <기능 이름>

## 1. 목적
이 기능이 사용자에게 주는 가치를 두세 문장으로 쓴다.

## 2. 사용 조건 / 사전 요구사항
- 로그인과 권한
- 필요한 실행 상태 (예: `local-environment` 통과)
- 선행 데이터

## 3. 입력
필드, 타입, 필수 여부, 예시 값

## 4. 출력
성공 시 결과, 저장되는 위치(테이블, 파일)

## 5. 실행 방법
- 사람: 화면 경로, BAT 명령이 있으면 명령
- AI: REST API 호출 예시 또는 CLI 명령

## 6. 관련 UI / API / command / DB
- UI: 화면 이름과 경로
- API: 메서드와 경로
- command: BAT 또는 CLI 명령
- DB: 테이블 이름

## 7. 실패 시 확인 방법
자주 나는 오류, 원인, 확인할 로그나 Health 경로, 해결 방법

## 8. 검증 방법
이 기능이 동작하는지 확인하는 절차. 자동 테스트 명령과 수동 확인 항목을 함께 쓴다.

## 9. 연관 Skill
- `<skill-name>`: 연결 이유 한 줄
```

## 작성 원칙
- 실행 명령과 API 경로는 실제 코드와 대조해서 쓴다. 추측으로 쓰지 않는다.
- 기능 코드가 바뀌면 이 파일을 같은 커밋에서 갱신한다.
- 한 Skill은 한 기능이다. 두 기능을 한 파일에 섞지 않는다.
- 연관 Skill 항목은 양방향으로 적는다. A가 B를 적었으면 B도 A를 적는다.
- Secret 값이나 실제 비밀번호를 예시에 넣지 않는다.

## 관련 Skill
- `feature-unit`: 기능 단위 완료 기준
- `env-bootstrap`: 환경 Skill 항목
