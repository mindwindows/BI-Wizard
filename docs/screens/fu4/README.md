# FU-4 화면 스크린샷 (계산 열 이름 변경·위치 이동·태그 편집·표시 형식, S4 Inspector)

- 촬영일: 2026-10-15(서버 시계 기준), 현재 소스 작업 트리(커밋 전)에서 이미지를 새로 빌드했다. 이미 있던 B6 API만 쓰고 백엔드는 바꾸지 않았다.
- 환경: 로컬 compose(프로젝트명 `fu4shot`, 포털 `127.0.0.1:36280`), `APP_BASE_PATH=/bi-wizard`, `APP_PROXY_STRIP_PREFIX=false`, 새 DB, Superset 없이 `postgres`·`db-bootstrap`·`migrate`·`backend`·`frontend`만. 임시 env는 `_workspace/qa/`(Git 제외)의 더미 값뿐이다.
- 비밀값 대조: 촬영 스크립트가 모든 화면의 글자·HTML을 임시 env의 비밀성 값과 토큰 모양에 대조해 발견 **0건**이었다. 모든 PNG를 눈으로도 확인했다.
- 크기: 모두 1920×1080 PNG(viewport, `deviceScaleFactor` 1). 데이터는 전부 합성이다.
- 신원: 개발용 인증 스텁(`AUTH_STUB_ENABLED=true`, `APP_ENV=local`)의 정의 담당자(`stub-definer`)·입력자(`stub-entry`).

| 파일 | 상태 |
| --- | --- |
| `fu4-inspector-formula-rename-input.png` | 계산 열 '부가세'의 이름을 '부가세(10%)'로 입력한 저장 전 폼(이름 규칙과 "수식은 열 번호로 저장되어 안 깨진다" 안내) |
| `fu4-inspector-formula-rename.png` | 저장 뒤: "열을 저장했습니다.", 열 목록·수식 보기 갱신, 정의 버전 증가 |
| `fu4-inspector-formula-tag.png` | 숫자 결과 열 '전기요금'의 태그를 '비용'에서 '에너지비'로 저장한 뒤 |
| `fu4-inspector-formula-move.png` | '구분'(글자 결과)을 위로 한 칸 옮긴 뒤: "열 순서를 바꿨습니다.", 열 목록과 그리드 열 순서가 같이 바뀜, 글자 결과 열이라 태그 입력칸 없음 |
| `fu4-readonly-nonDefiner.png` | 입력자: 입력칸 읽기 전용, 저장·이동 버튼 없음 |
| `fu4-archived-disabled.png` | 보관된 '작년 전력': 보관 배너, 입력칸·저장·이동 버튼 비활성 |
| `fu4-rename-error.png` | 이름을 기존 열 '사용량'으로 바꾸려 할 때 409 `ALREADY_EXISTS` 안내("같은 이름의 열이 이미 있습니다.") |

## 표시 형식(03b 33절, 추가분 5장)
- 촬영일 2026-10-15, 프로젝트명 `fu4fmt`(포털 `127.0.0.1:36280`), 현재 소스 작업 트리(커밋 전)로 이미지를 새로 빌드한 새 DB. 위 7장과 환경·신원은 같고, 백엔드는 B6 계산 열 `rules`(`display_decimals`·`display_thousands`)를 허용하는 작업 트리 상태다. 비밀값 대조 0건, 이미지 파일·이력 속 임시 env 비밀값 대조 0건.
- 데이터(`capture/seed4fmt.py`): A팀 "월별 지표"(월 단위, 기준일·사용량·단가, 계산 열 연도=`YEAR([기준일])`, 단가당 사용량=`[사용량] / [단가]`, 전기요금, 구분, 행 3개).

| 파일 | 상태 |
| --- | --- |
| `fu4-format-year-before.png` | 설정 전: 연도 열이 쉼표 때문에 `2,026`으로 보인다. 표시 형식 구역은 자릿수 "기본", 쉼표 켬, 저장 버튼 비활성 |
| `fu4-format-inspector.png` | 단가당 사용량: 표시 형식 구역(소수 자릿수 2 입력, 천 단위 쉼표, 표시 전용·ROUND*와 다름·Superset 차트와 SQL Lab에는 적용되지 않음·YEAR 쉼표 안내). 저장 전이라 그리드는 아직 기본 표시(8.166667) |
| `fu4-format-error.png` | 서버 검증 오류(422 `VALIDATION_ERROR`, `rules.display_decimals` 허용 범위 밖). 화면은 0~10만 보내므로 촬영 스크립트가 요청 본문의 자릿수만 11로 바꿔 보냈고, 응답과 화면 문구는 실제 서버·화면의 것이다. 그리드는 그대로 |
| `fu4-format-grid-decimals.png` | 자릿수 2 저장 뒤: 단가당 사용량이 `8.80`·`8.17`·`10.42`(끝자리 0 채움, 반올림). 연도 열은 아직 `2,026` |
| `fu4-format-year-thousands-off.png` | 연도 열의 쉼표를 끈 뒤 `2026`. 자릿수는 "기본"이라 비워 둠 |

촬영 순서: `seed4fmt.py http://127.0.0.1:36280/bi-wizard/api <ids4fmt.json>` 다음 `capture4fmt.cjs --origin ... --base /bi-wizard --ids <ids4fmt.json> --env <임시 env> --out ..`(마지막 줄 "발견 건수: 0"). 저장 장면이 데이터를 바꾸므로 다시 찍으려면 새 DB에서 시드부터 한다.

## 데이터(`capture/seed4.py`가 실제 API로 만듦)
A팀 "월별 전력"(월 단위, 기준일·사용량·단가, 계산 열 전기요금=`[사용량] * [단가]` 태그 '비용', 부가세=`[전기요금] * 0.1`, 구분=`IF(...)` 글자 결과, 행 3개)과 같은 구성을 보관한 "작년 전력".

## 촬영 방법(비밀 제외)
1. 이미지: `docker build -f <CA 오버레이 보조 Dockerfile> --build-context ca=/root/.ccr -t bi-wizard-{backend,frontend}:local {backend,frontend}`(보조 Dockerfile은 저장소 밖 `_workspace/qa/`).
2. 기동: `docker compose -p fu4shot --env-file <임시 env> up -d --no-build frontend`, `exec -T backend python -m app.cli seed-stub-users`.
3. 시드: `python3 capture/seed4.py http://127.0.0.1:36280/bi-wizard/api <ids4.json>`.
4. 촬영: `PLAYWRIGHT_MODULE=/opt/node-tools/node_modules/playwright node capture/capture4.cjs --origin http://127.0.0.1:36280 --base /bi-wizard --ids <ids4.json> --env <임시 env> --out .` (마지막 줄 "발견 건수: 0" 확인). 저장·이동·이름 변경 장면이 데이터를 바꾸므로 다시 찍으려면 새 DB에서 시드부터 한다.
5. 정리: `stop`·`rm -f`에 서비스 이름을 지정하고 볼륨 `fu4shot_postgres_data`와 네트워크 `fu4shot_default`를 이름으로 삭제(`down -v`·`prune` 금지).

## 알려진 한계
- 이름 변경 뒤 다른 수식 보기 갱신은 촬영 뒤 API로 따로 확인했다(전기요금 → '전기요금(원)'으로 바꾸자 부가세 수식 보기가 `[전기요금(원)] * 0.1`로 나옴). 화면에는 담지 않았다.
- 409 낡은 버전·422·503·순환 오류는 vitest로만 확인했다(촬영 안 함). 이동은 B6를 두 번 부르므로 두 번째 호출만 실패하는 경우는 vitest로만 확인했다.
- Superset 차트의 표시 이름 반영은 이 촬영 범위가 아니다.
- 표시 형식: 서버 오류 장면은 요청 본문을 바꿔 만든 것이다(정상 화면으로는 범위 밖 값을 보낼 수 없다). 409·503·두 번째 이동 실패는 이 촬영에서도 vitest로만 확인했다. 수식 미리보기는 열 설정이 없는 새 수식이므로 저장된 표시 형식을 따르지 않고 기본 표시(소수 6자리, 쉼표 켬)를 쓴다.
