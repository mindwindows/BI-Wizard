# FU-3 화면 스크린샷 (S11 기준값, 수식 편집기 REF 자동완성, E4 칸, S5 점검)

- 촬영일: 2026-10-15(서버 시계 기준), backend HEAD `123c16d` + frontend 작업 트리(커밋 전; 그 작업 트리는 이후 커밋 `440e3de`(제품 코드 최종)에 포함됐다). 이미지는 현재 소스에서 새로 빌드했다.
- 환경: 로컬 compose(프로젝트명 `fu3shot`, 포털 `127.0.0.1:36280`), `APP_BASE_PATH=/bi-wizard`, `APP_PROXY_STRIP_PREFIX=false`, 새 DB, Superset 없이 `postgres`·`db-bootstrap`·`migrate`·`backend`·`frontend`만. 임시 env는 `_workspace/qa/`(Git 제외)의 더미 값뿐이다.
- 비밀값 대조: 촬영 스크립트가 모든 화면의 DOM 글자·HTML을 임시 env의 비밀성 값과 토큰 모양에 대조해 발견 **0건**이었다. 모든 PNG를 눈으로도 확인했다.

- 크기: 모두 1920×1080 PNG(viewport, `deviceScaleFactor` 1, 스크롤하지 않은 첫 화면). 9장(계획 7장 + 감사 행 + 기준 날짜 열 해제 안내).
- 데이터: 전부 합성이다. 실제 사용자·업무 데이터는 쓰지 않는다.
- 신원: 개발용 인증 스텁(`AUTH_STUB_ENABLED=true`, `APP_ENV=local`)의 신원 전환기로 관리자(`stub-admin`)·정의 담당자(`stub-definer`)·입력자(`stub-entry`)를 바꿔 찍는다.

## 파일 목록
| 파일 | 화면 | 상태 | 촬영 조건 |
| --- | --- | --- | --- |
| `fu3-s11-list.png` | S11 | 관리자: 왼쪽 항목 목록(이름·설명·값 개수·연도 범위), 오른쪽 연도별 값 표(내림차순), 항목 추가·연도 값 추가 폼, 위쪽 안내문 | `stub-admin`, 첫 항목 선택 상태 |
| `fu3-s11-add-value.png` | S11 | 연도 값 추가 폼에 2027·13.75를 입력한 상태(저장 전) | 위 화면에서 입력만 |
| `fu3-s11-correct-confirm.png` | S11 | 정정 확인창: "'전기요금_A팀'의 2026년 값을 12.50에서 13.00(으)로 바꿉니다. 이 연도의 결과와 차트가 바뀝니다", 영향 데이터셋 목록(R6), 감사 기록 안내, 정정하기/취소 | "2026년 값 정정" → 새 값 입력 → "정정 확인", **"정정하기"는 누르지 않는다** |
| `fu3-editor-ref-autocomplete.png` | S4 | 수식 편집기에서 `REF("` 입력 중: 항목 이름과 설명이 후보로 보임 | `stub-definer`, 계산 열 추가 |
| `fu3-cell-e4.png` | S4 | 입력 그리드의 E4 칸: 주황 점선 "기준값 없음 E4"(붉은 E1 오류 칸과 구별) | 2027-01 행(2027년 값 없음) |
| `fu3-s5-e4-check.png` | S5 | 점검 화면: E4 열을 펼친 상태, 이유 문구와 "기준값 화면 열기" 링크, E4 안내문 | `?dataset=&column=` 주소 |
| `fu3-audit-reference-rows.png` | S10 | 대상 종류 '기준값' 필터: 항목 만들기·연도 값 추가(값 포함)·정정 "2025년 값 11.00→11.20 정정" | `stub-admin` |
| `fu3-basedate-in-use.png` | S4 | 행이 없는 데이터셋(REF 계산 열 있음)에서 기준 날짜 열을 '없음'으로 저장하려 하면 422 `BASE_DATE_IN_USE` 안내(열 이름 '가스요금' 포함) | `stub-definer`, 데이터셋 설정 |
| `fu3-s11-nonadmin-readonly.png` | S11 | 입력자: 목록과 값만 보이고 추가·정정 UI가 없음, "관리자만 추가하거나 정정할 수 있습니다" 안내 | `stub-entry` |

촬영하지 않은 것(vitest로만 확인): 정정 확인창의 R6 실패(일반 경고) 상태, 409 같은 연도, 422·403·503 안내, 정정 성공 안내.
(04 §4의 "정정 확인창(영향 목록 있음/조회 실패 두 상태)" 중 조회 실패 상태 스크린샷이 필요하면 촬영 때 R6를 막은 환경이 있어야 한다. 현재 7장 목록에는 넣지 않았다.)

## 데이터(전부 합성, `capture/seed3.py`가 실제 API로 만듦)
기준값 항목 3개: 전기요금_A팀(2024 10.00, 2025 11.00→11.20 정정, 2026 12.50), 가스요금_A팀(2024~2026), 환율(2025·2026). A팀 데이터셋 "월별 전력"(월 단위, 기준 날짜 열 '기준일', 계산 열 '전기요금' = `[사용량] * REF("전기요금_A팀")`; 행 2026-01·2026-02는 1,250, 2027-01은 2027년 값이 없어 E4)과 행이 없는 "신규 전력(행 없음)"(REF 계산 열 있음).

## 촬영 방법(실행한 명령, 비밀 제외)
1. 이미지: 현재 소스에서 새로 빌드(CA 오버레이 보조 Dockerfile은 저장소 밖 `_workspace/qa/`): `docker build -f <보조 Dockerfile> --build-context ca=/root/.ccr -t bi-wizard-{backend,frontend}:local {backend,frontend}`.
2. 기동: `docker compose -p fu3shot --env-file <임시 env> up -d --no-build frontend`, `exec -T backend python -m app.cli seed-stub-users`.
3. 시드: `python3 capture/seed3.py http://127.0.0.1:36280/bi-wizard/api <ids3.json>`.
4. 촬영: `PLAYWRIGHT_MODULE=/opt/node-tools/node_modules/playwright node capture/capture3.cjs --origin http://127.0.0.1:36280 --base /bi-wizard --ids <ids3.json> --env <임시 env> --out .` (마지막 줄 "비밀값·내부 경로 발견 건수: 0" 확인). 촬영은 데이터를 바꾸지 않으므로(정정 확인창은 취소, 해제 저장은 서버가 거부) 다시 찍어도 된다.
5. 정리: `stop`·`rm -f`에 서비스 이름을 지정하고 볼륨 `fu3shot_postgres_data`와 네트워크 `fu3shot_default`를 이름으로 삭제(`down -v`·`prune` 금지).

## 알려진 한계
- `fu3-editor-ref-autocomplete.png`는 따옴표를 연 채라 수식 오류 표시("글자를 감싼 큰따옴표가 닫히지 않았습니다")가 함께 보인다(입력 중 정상 동작).
- `fu3-cell-e4.png`의 Inspector는 선택된 열이 없어 '데이터셋 설정'이 보인다.
- 정정 확인창의 R6 실패(일반 경고) 상태·409·422·403·503 안내는 촬영하지 않았다(vitest로만 확인).
- Superset 차트 반영(정정 뒤 차트 값 변화)은 이 촬영 범위가 아니다(Superset 없음).
