# FU-3 화면 스크린샷 (S11 기준값, 수식 편집기 REF 자동완성, E4 칸, S5 점검)

**상태: 초안. 아직 촬영하지 않았다.** backend 구현(R1~R6, `REF`, E4)이 끝난 뒤 별도 요청으로 촬영한다. 촬영 스크립트는 문법만 확인했고 한 번도 실행하지 않았다(첫 실행에서 계약과 다른 응답 모양이 나오면 고쳐야 한다).

- 크기: 모두 1920×1080 PNG(viewport, `deviceScaleFactor` 1, 스크롤하지 않은 첫 화면). 7장.
- 데이터: 전부 합성이다. 실제 사용자·업무 데이터는 쓰지 않는다.
- 신원: 개발용 인증 스텁(`AUTH_STUB_ENABLED=true`, `APP_ENV=local`)의 신원 전환기로 관리자(`stub-admin`)·정의 담당자(`stub-definer`)·입력자(`stub-entry`)를 바꿔 찍는다.

## 파일 목록(계획)
| 파일 | 화면 | 상태 | 촬영 조건 |
| --- | --- | --- | --- |
| `fu3-s11-list.png` | S11 | 관리자: 왼쪽 항목 목록(이름·설명·값 개수·연도 범위), 오른쪽 연도별 값 표(내림차순), 항목 추가·연도 값 추가 폼, 위쪽 안내문 | `stub-admin`, 첫 항목 선택 상태 |
| `fu3-s11-add-value.png` | S11 | 연도 값 추가 폼에 2027·13.75를 입력한 상태(저장 전) | 위 화면에서 입력만 |
| `fu3-s11-correct-confirm.png` | S11 | 정정 확인창: "'전기요금_A팀'의 2026년 값을 12.50에서 13.00(으)로 바꿉니다. 이 연도의 결과와 차트가 바뀝니다", 영향 데이터셋 목록(R6), 감사 기록 안내, 정정하기/취소 | "2026년 값 정정" → 새 값 입력 → "정정 확인", **"정정하기"는 누르지 않는다** |
| `fu3-editor-ref-autocomplete.png` | S4 | 수식 편집기에서 `REF("` 입력 중: 항목 이름과 설명이 후보로 보임 | `stub-definer`, 계산 열 추가 |
| `fu3-cell-e4.png` | S4 | 입력 그리드의 E4 칸: 주황 점선 "기준값 없음 E4"(붉은 E1 오류 칸과 구별) | 2027-01 행(2027년 값 없음) |
| `fu3-s5-e4-check.png` | S5 | 점검 화면: E4 열을 펼친 상태, 이유 문구와 "기준값 화면 열기" 링크, E4 안내문 | `?dataset=&column=` 주소 |
| `fu3-s11-nonadmin-readonly.png` | S11 | 입력자: 목록과 값만 보이고 추가·정정 UI가 없음, "관리자만 추가하거나 정정할 수 있습니다" 안내 | `stub-entry` |

촬영하지 않는 것(vitest로만 확인): 정정 확인창의 R6 실패(일반 경고) 상태, 409 같은 연도, 422·403·503 안내, 정정 성공 안내.
(04 §4의 "정정 확인창(영향 목록 있음/조회 실패 두 상태)" 중 조회 실패 상태 스크린샷이 필요하면 촬영 때 R6를 막은 환경이 있어야 한다. 현재 7장 목록에는 넣지 않았다.)

## 촬영 방법(계획, `fu2b`와 같다)
스크립트는 `capture/capture3.cjs`(촬영), `capture/seed3.py`(합성 데이터 시드)다.
1. 이미지: 현재 소스에서 새로 빌드한다(보조 Dockerfile은 저장소 밖 `_workspace/qa/`).
2. 기동: 임시 env로 `postgres`·`db-bootstrap`·`migrate`·`backend`·`frontend`를 띄우고 `exec -T backend python -m app.cli seed-stub-users`.
3. 시드(실제 API): `python3 capture/seed3.py http://127.0.0.1:<포트>/bi-wizard/api <ids3.json>`.
4. 촬영: `PLAYWRIGHT_MODULE=/opt/node-tools/node_modules/playwright node capture/capture3.cjs --origin http://127.0.0.1:<포트> --base /bi-wizard --ids <ids3.json> --env <임시 env> --out .` (마지막 줄 "비밀값·내부 경로 발견 건수: 0" 확인).
5. 정리: `stop`·`rm -f`에 서비스 이름을 지정하고 볼륨·네트워크를 이름으로 삭제(`down -v`·`prune` 금지).
