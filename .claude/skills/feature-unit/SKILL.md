---
name: feature-unit
description: Gate ④ 기능 개발에서 기능 단위 하나를 코드, 테스트, 제품 Skill, 연관 Skill, 회귀 테스트까지 완성하는 절차와 완료 기준. backend-dev와 frontend-dev가 사용한다. 기능 추가나 기존 기능 수정에도 사용한다.
---

# feature-unit — 기능 단위 개발 절차

## 원칙
**Feature Code ↔ Skill ↔ Related Skills ↔ Regression Test는 항상 같이 움직인다.** 기능 코드만 바뀌고 Skill이 갱신되지 않았으면 작업 완료로 보지 않는다. (운영 가이드 5절)

## 완료 기준 (Definition of Done)
한 단위가 완료되려면 다음이 모두 참이어야 한다.

- [ ] 승인된 API 계약과 모듈 경계를 따른다. 계약을 바꿨다면 사용자 승인을 받았다.
- [ ] 기능 코드가 있다.
- [ ] 테스트가 있다. 백엔드는 pytest, 프런트는 해당 프로젝트의 테스트 도구를 쓴다.
- [ ] DB 스키마가 바뀌었다면 Alembic revision(`upgrade`와 `downgrade` 모두)이 있고 upgrade → downgrade → upgrade 왕복 테스트를 통과했다. 자동 생성 초안에 `DROP`이 있었다면 사용자 확인을 받았다. 마이그레이션 안에 변수 보간 SQL이 없다 (`docs/decisions/03-migration-tool.md`).
- [ ] `skills/<기능>/SKILL.md`가 있고 필수 항목을 모두 채웠다 (`product-skill-authoring` 참조).
- [ ] 연관 Skill을 찾아 영향도를 확인했고, 필요한 것은 갱신했다.
- [ ] 관련 기능의 회귀 테스트를 실행했고, 결과를 보고했다.
- [ ] `reviewer`의 차단·중요 항목을 고쳤다.
- [ ] 사용자에게 완료 보고를 하고 승인을 받았다.

## 절차
1. **계약 확인:** 승인된 API 계약과 Skill 경계를 읽는다. 부족하면 구현을 멈추고 메인에게 알린다.
2. **테스트 작성:** 기대 동작을 먼저 테스트로 적는다. 오류 경로도 포함한다.
3. **구현:** 계약의 필드 이름과 타입을 정확히 쓴다.
4. **즉시 검증:** qa-engineer가 모듈 단위로 바로 검사한다. 프런트와 백엔드는 응답 구조를 대조한다.
5. **Skill 갱신:** 목적, 입력, 출력, 실행 방법, 관련 UI·API·command·DB, 실패 시 확인 방법, 검증 방법, 연관 Skill을 현재 코드와 맞춘다.
6. **영향도 확인:** 바뀐 기능과 연결된 Skill을 찾아 같이 점검한다.
7. **회귀 테스트:** 연관 기능의 테스트를 함께 실행한다.
8. **리뷰:** reviewer에게 변경 파일과 diff를 넘겨 리뷰를 받는다.
9. **보고:** 변경 파일, 테스트 결과, 갱신한 Skill, 미실행 항목을 적는다.

## 단위 크기
- 한 단위는 Skill 하나에 대응한다. 여러 Skill에 걸치면 단위를 나눈다.
- 단위가 너무 크면 "백엔드 API → 프런트 화면"처럼 계약 단위로 쪼개서 진행하되, Skill 완료는 단위 끝에 한다.

## 기존 기능 수정
1. 수정 대상 기능의 Skill을 먼저 읽는다.
2. 수정 후 Skill의 입력, 출력, 실패 확인 방법이 바뀌었는지 확인한다.
3. 바뀌었으면 Skill과 연관 Skill을 같은 커밋에서 갱신한다.

## 관련 Skill
- `product-skill-authoring`: 제품 Skill 형식
- `qa-verification`: 검증 절차
- `bi-review`: 리뷰 기준
