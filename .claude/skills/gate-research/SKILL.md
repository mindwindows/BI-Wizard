---
name: gate-research
description: Gate ① RESEARCH & DECIDE에서 디자인 방향 2~3안과 기술 Reference 3~5개를 조사해 비교표를 만드는 절차. researcher 에이전트가 사용한다. 실제 소스 도입이나 구현은 하지 않는다.
---

# gate-research — 디자인·기술 Reference 조사 절차

## 목적
사용자가 비교해서 고를 수 있는 선택지를 근거와 함께 만든다. 조사는 선택지를 만드는 단계이며, 적용하는 단계가 아니다.

## 사용 조건
- Gate ①에서 researcher가 실행될 때
- 사용자가 디자인이나 Reference 후보를 다시 조사하라고 요청할 때 (이 경우 기존 `docs/decisions/` 파일과 비교해 차이를 표시한다)

## 입력
- `docs/project-brief.md`의 1, 2, 4절 (목적, 핵심 흐름, 요구사항)
- `docs/AI_AGENT_DEVELOPMENT_GUIDE_요약.md`의 1절 (조사 항목과 금지 사항)

## 디자인 조사 절차
1. 업무용 Desktop Web 사례를 찾는다. 키워드 예: 데이터 입력 그리드, 대시보드, 가져오기 마법사, 수식 편집기.
2. 조사 항목: 레이아웃, 정보 위계, Navigation, Panel 구조, Table과 Filter, Interaction, 밀도, 시각 언어.
3. 서로 다른 2~3개 방향으로 묶는다. 방향마다 "조합 가능한 요소"를 따로 적는다. 예: "A의 레이아웃 + B의 상세 Panel".

## Reference 조사 절차
1. 핵심 기능별로 후보를 찾는다: 엑셀 가져오기 UI, lark 기반 수식 파서, AG Grid Community 활용, 수식→SQL 변환.
2. 3~5개로 좁히고 각 후보를 아래 기준으로 비교한다.

| 기준 | 확인 방법 |
| --- | --- |
| 기능 관련성 | 우리 기능 중 어디에 쓰는지 한 줄로 적는다 |
| 참고할 구조·알고리즘 | 구체적인 파일이나 모듈 이름을 적는다 |
| 기술 스택 | 언어, 프레임워크 |
| 유지 상태 | 마지막 커밋과 릴리스 날짜 |
| 라이선스 | 허용형 여부를 판정한다 |
| 통합 난이도 | 예상 작업량과 위험 |

## 라이선스 판정
- **허용형 (추천 가능):** MIT, BSD-2/3-Clause, Apache 2.0, PSF, PostgreSQL License
- **주의 (추천 전 사용자 확인):** MPL 2.0, LGPL
- **비추천:** AGPL, GPL, EUPL, Sustainable Use License, Redis 7.4 이후 라이선스
- 라이선스가 불분명하면 "불명확"으로 적고 추천하지 않는다.

## 금지 사항
- 검색 없이 "최신"이라고 단정하지 않는다.
- 첫 검색 결과를 그대로 추천하지 않는다.
- 합의 전에 대규모 소스를 다운로드하지 않는다. README, LICENSE, 릴리스 노트 정도만 읽는다.
- 근거 없는 평가를 쓰지 않는다. 모르는 항목은 "미확인"으로 둔다.

## 산출물 형식
- `_workspace/gate1/design-options.md`: 방향별로 "참고 사례 / 화면 구성 / 시각적 특징 / 업무 UX 적합성 / 장점 / 단점 / 가져올 요소 / 피할 요소" 순서
- `_workspace/gate1/tech-references.md`: 비교표 한 개 + 후보별 상세 (출처 URL, 라이선스, 마지막 활동일)
- 마지막에 추천안 한 개와 추천 이유 한 단락. 선택은 사용자가 한다.

## 승인 후 처리 (메인이 수행)
- 선택된 디자인은 `docs/decisions/01-design-direction.md`
- Reference 비교표와 선택 결과는 `docs/decisions/02-tech-reference.md`
- 실제로 확보할 소스만 루트 `references/`에 출처, 목적, 라이선스, 버전 또는 커밋, 참고 위치와 함께 기록한다.

## 관련 Skill
- `bi-wizard-dev`: Gate 순서와 승인 절차
- `bi-review`: 라이선스 점검
