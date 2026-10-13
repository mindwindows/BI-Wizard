# FU-2a 화면 스크린샷 (S10 감사 기록) — 초안

상태: **초안(촬영 전)**. 스크린샷은 backend 구현이 끝난 뒤 별도 요청으로 찍는다. 이 문서는 촬영 규격과 예정 목록만 적었다.

## 촬영 규격(FU-1과 같다: `docs/screens/fu1/README.md`)
- 크기 1920×1080 PNG, `deviceScaleFactor` 1, Chromium(`ignoreDefaultArgs: ['--hide-scrollbars']`, `timezoneId: 'Asia/Seoul'`, locale `ko-KR`).
- 데이터는 전부 합성이다. 신원은 개발용 인증 스텁(`AUTH_STUB_ENABLED=true`, `APP_ENV=local`)으로 바꿔 찍는다. 환경은 전용 compose 프로젝트와 임시 env 파일(더미 비밀값만, 사용자 `.env` 미사용).
- 촬영한 화면의 DOM 텍스트·HTML을 임시 env의 비밀성 값과 대조해 일치가 없음을 확인하고, 모든 PNG를 눈으로 확인한다(토큰·비밀번호·행 값·수식 원문 없음).
- 파일 이름은 `fu2a-{화면}-{상태}.png`. 촬영 스크립트 초안은 `capture/capture2a.cjs`(실행해 본 적 없음).

## 예정 목록
| 파일 | 화면 | 상태 | 촬영 조건 |
| --- | --- | --- | --- |
| `fu2a-s10-empty-no-records.png` | S10 감사 기록 | 빈 상태(필터 없음): "아직 기록이 없습니다." | 새 DB, `stub-admin`, `/admin/audit` (시드 전) |
| `fu2a-s10-list-default.png` | S10 | 목록(일시·행위자·행위·대상·요약), 서버 명령 행("서버 명령") 포함 | 시드 뒤 `stub-admin` |
| `fu2a-s10-list-filtered.png` | S10 | 필터 줄에 대상 종류·번호·행위를 넣고 조회한 결과 | 데이터셋 1번, 행위 "열 추가" |
| `fu2a-s10-empty-no-match.png` | S10 | 빈 상태(필터 있음): "조건에 맞는 기록이 없습니다." + 필터 지우기 | 없는 대상 번호 |
| `fu2a-s10-forbidden-non-admin.png` | S10 | 비관리자 직접 접속: "관리자만 볼 수 있습니다"(목록·필터 없음, 관리 메뉴 없음) | `stub-entry`가 `/admin/audit`로 접속 |

## 촬영 방법(초안)
1. 스택을 새 DB로 띄우고 `python -m app.cli seed-stub-users`를 한 번 실행한다.
2. 빈 상태 장면을 먼저 찍는다(기록 0건).
3. 시드 단계에서 관리자 API로 합성 변경을 만들어 기록을 쌓는다(스크립트의 TODO를 채운다).
4. 나머지 장면을 찍고 DOM 덤프를 비밀값과 대조한다.
