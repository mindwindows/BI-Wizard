# FU-1 화면 스크린샷 (1a·1b·1c)

- 촬영일: 2026-10-12(화면 수정분 재촬영: 같은 날, HEAD `809ea5f` 기준으로 이미지를 다시 빌드)
- 크기: 모두 1920×1080 PNG(viewport, `deviceScaleFactor` 1, 스크롤하지 않은 첫 화면 또는 해당 영역으로 스크롤한 화면). 42장, 합계 약 5.6 MiB(파일당 최대 약 270 KB).
- 데이터: 전부 합성 데이터다(팀·사용자·데이터셋·값). 실제 사용자·업무 데이터는 없다.
- 신원: 개발용 인증 스텁(`AUTH_STUB_ENABLED=true`, `APP_ENV=local`)의 신원 전환기로 사용자를 바꿔 찍었다. 모든 화면 위쪽의 점선 "개발용 신원" 선택은 이 때문이다(운영 설정에서는 나타나지 않는다).
- 스크롤바: 기본 headless Chromium은 스크롤바를 그리지 않으므로 Playwright를 `ignoreDefaultArgs: ['--hide-scrollbars']`로 띄워 가로·세로 스크롤바가 실제 브라우저처럼 보이게 찍었다(코드 변경 아님, 촬영 옵션).
- 정렬: 서버가 사용자·팀 이름을 한글 가나다순으로 정렬한다. 개발용 신원 전환기·권한 격자의 사용자 행·팀 열이 가나다순으로 보인다(이전 촬영은 로그인 ID순이었다).
- 환경: 로컬 compose(전용 프로젝트명 `shots3`), `APP_BASE_PATH=/bi-wizard`, `APP_PROXY_STRIP_PREFIX=false`, 임시 env 파일(더미 비밀값만, 사용자 `.env` 미사용). 촬영한 화면의 DOM 텍스트·HTML을 임시 env의 비밀성 값(비밀번호·키)과 대조해 일치가 없음을 확인했고, 모든 PNG를 눈으로도 확인했다(비밀번호·토큰·쿠키 값·내부 경로 없음). 화면에 보이는 "문의 번호"는 요청 추적용 ID이며 비밀이 아니다.
- 네이티브 `<select>`의 펼침 목록은 headless 스크린샷에 나오지 않아, "작업 팀 선택 열린 상태"와 "개발용 신원 전환기"는 같은 선택지를 목록 상자로 펼쳐 보여 주는 촬영 전용 표시를 썼다(앱 코드는 바꾸지 않았다).

## 파일 목록

### 1a 셸·접근·권한 관리

| 파일 | 화면 | 상태 | 촬영 조건 |
| --- | --- | --- | --- |
| `fu1a-s1-shell-home-admin.png` | S1 셸 홈 | 관리자, 소속 팀 없음 | `stub-admin`으로 `/` |
| `fu1a-s1-shell-home-entry.png` | S1 셸 홈 | 입력자 | `stub-entry`(시험 A팀 입력자)로 `/` |
| `fu1a-s1-access-denied-unregistered.png` | S1 접근 안내 | 미등록 사용자(403 `USER_NOT_REGISTERED`), 신원 전환기에 "(미등록) ghost-user" 표시 | 등록되지 않은 로그인 ID 쿠키 |
| `fu1a-s1-access-denied-inactive.png` | S1 접근 안내 | 비활성 사용자(403 `USER_INACTIVE`) | `stub-inactive` |
| `fu1a-s1-access-denied-no-identity.png` | S1 접근 안내 | 신원 선택 안 함(401) | 전환기에서 "(선택 안 함)" |
| `fu1a-s1-work-team-select-open-inactive-team.png` | S1 작업 팀 선택 | 목록을 펼침, 비활성 팀 "(비활성)" 선택 불가 표시 | `stub-multi`(A팀 입력자, B팀 정의 담당자, 비활성 구 영업팀 입력자) |
| `fu1a-s1-dev-identity-switcher-open.png` | S1 개발용 신원 전환기 | 목록을 펼침(등록 사용자 전체, 표시 이름 가나다순) | `stub-definer`로 `/` |
| `fu1a-s6-permissions-grid.png` | S6 권한 관리 격자 | 팀 3개(비활성 팀 헤더 "비활성")×사용자 9명(비활성 사용자 배지·회색, 비활성 칸 선택 막힘), 팀 열·사용자 행 가나다순, 격자가 보이도록 아래로 스크롤 | `stub-admin` |
| `fu1a-s6-changes-staged.png` | S6 변경 목록 | 변경 7건이 쌓임(노란 칸 3개) | 소속 추가·해제, 팀 만들기, 사용자 등록, 사용자·팀 수정을 담은 뒤 격자 마지막 행과 변경 목록이 보이게 스크롤 |
| `fu1a-s6-confirm-dialog.png` | S6 변경 요약 확인창 | 위 7건을 실행 순서대로 표시 | "저장하기"(아직 저장하지 않음) |
| `fu1a-s6-last-admin-error-result.png` | S6 저장 결과 창 | 1건 완료, 1건 실패(409 `LAST_ADMIN`) | 소속 추가 1건 + 마지막 관리자 해제를 저장 |
| `fu1a-s6-non-admin-notice.png` | S6 직접 접속 | "관리자만 사용할 수 있는 화면입니다" | `stub-entry`가 `/admin/permissions`로 접속 |

### 1b 데이터셋 정의

| 파일 | 화면 | 상태 | 촬영 조건 |
| --- | --- | --- | --- |
| `fu1b-s2-dataset-list-admin-no-create-button.png` | S2 데이터셋 목록 | 관리자(정의 담당자 아님): "새 데이터셋" 버튼 없이 안내 문구 | `stub-admin` |
| `fu1b-s2-dataset-list-definer-with-create-button.png` | S2 데이터셋 목록 | 정의 담당자: "새 데이터셋" 버튼 있음 | `stub-definer`(작업 팀 시험 A팀) |
| `fu1b-s3-create-form-default.png` | S3 데이터셋 만들기 | 기본 폼 | `stub-definer` |
| `fu1b-s3-create-form-error-empty-name.png` | S3 | 이름 비움 검증 오류 | 이름 없이 "만들기" |
| `fu1b-s3-create-form-error-duplicate-name.png` | S3 | 서버 오류 409 `ALREADY_EXISTS`("같은 이름이 이미 있습니다") | 기존 이름 "월별 매출"로 만들기 |
| `fu1b-s3-create-form-error-inactive-team.png` | S3 | 비활성 팀에는 데이터셋을 만들 수 없다는 안내(409 `TARGET_INACTIVE`, 필드 `team`) | 폼에서 팀 "임시 기획팀"을 고른 채 다른 클라이언트(API)로 팀을 비활성화한 뒤 "만들기" |
| `fu1b-s3-no-definer-team-admin.png` | S3 | 정의 담당자인 팀이 없다는 안내 | `stub-admin` |
| `fu1b-s4-workspace-three-pane-definer.png` | S4 작업공간 3분할 | 왼쪽 정보·열 목록, 가운데 입력 그리드, 오른쪽 Inspector(데이터셋 설정) | `stub-definer`, "월별 매출" |
| `fu1b-s4-inspector-column-edit-type-locked.png` | S4 Inspector 열 수정 | 숫자 열: "타입·종류는 바꿀 수 없습니다" 표시, 규칙 입력칸 | 열 목록에서 "매출" |
| `fu1b-s4-inspector-column-edit-choice-options.png` | S4 Inspector 열 수정 | 선택 목록 열: 항목 입력칸 | 열 목록에서 "구분" |
| `fu1b-s4-inspector-add-column-number-rules.png` | S4 Inspector 열 추가 | 숫자 열 규칙(최솟값·최댓값·소수 자릿수·구분 태그) 입력 | "열 추가"에서 값 입력(저장 안 함) |
| `fu1b-s4-inspector-add-column-error-reserved-name.png` | S4 Inspector 열 추가 | 예약어 `team` 오류(저장 버튼 막힘) | 열 이름 `team` |
| `fu1b-s4-inspector-add-column-error-forbidden-char.png` | S4 Inspector 열 추가 | 금지 문자 `[` `]` 오류 | 열 이름 `매출[합계]` |
| `fu1b-s4-dataset-settings-error-has-rows.png` | S4 Inspector 데이터셋 설정 | 행이 있어 날짜 단위를 바꿀 수 없음(422 `DATASET_HAS_ROWS`) | 날짜 단위를 "일"로 바꿔 저장 |
| `fu1b-s4-version-mismatch-reload-notice.png` | S4 Inspector | 409 `DEFINITION_VERSION_MISMATCH`: "다른 사람이 먼저 바꿨습니다. 최신 내용을 다시 읽었습니다…", 열 목록에 새 열 "메모"가 반영되고 입력하던 폼은 유지 | 폼에 입력 후 다른 클라이언트(API)가 열을 먼저 추가 |
| `fu1b-s4-inspector-readonly-no-define-permission.png` | S4 Inspector 읽기 전용 | 정의 권한 없음: 안내 문구, 입력칸 모두 막힘, 저장·열 추가 버튼 없음 | `stub-viewer`(소속 없음) |

### 1c 입력 그리드

| 파일 | 화면 | 상태 | 촬영 조건 |
| --- | --- | --- | --- |
| `fu1c-s4-entry-grid-overview.png` | 입력 그리드 | 13개월 행, 쉼표·소수 자릿수 서식(0은 `0.00`), 빈 칸 빗금, 고정 "기간 / 행 번호" 열 | `stub-entry`, "월별 매출" |
| `fu1c-s4-entry-grid-cell-editing.png` | 입력 그리드 | 매출 칸 편집 중(편집기 열림, 저장 전) | 칸을 두 번 눌러 편집 |
| `fu1c-s4-entry-grid-draft-new-row.png` | 입력 그리드 | 임시 새 행(저장 전, 필수 칸 "매출" 남음) 안내와 맨 아래 "새 행 입력" 줄 | 맨 아래 줄에 기준월 입력 |
| `fu1c-s4-entry-grid-validation-error.png` | 입력 그리드 | 검증 오류 칸(붉은 테두리 "!")과 "확인이 필요한 칸"(`OUT_OF_RANGE`, 값은 서버 값으로 복원) | 매출에 `-5`(최솟값 0) 입력 |
| `fu1c-s4-entry-grid-readonly.png` | 입력 그리드 | 읽기 전용(입력 권한 없음): "읽기 전용입니다…" 안내, 새 행 버튼·입력 줄 없음 | `stub-viewer` |
| `fu1c-s4-entry-grid-wide-scroll-left.png` | 열 많은 데이터셋 | 열 16개: 가로로 넘치는 왼쪽 끝 | `stub-multi`, "월별 지표(항목 많음)" |
| `fu1c-s4-entry-grid-wide-scroll-right-pinned-period.png` | 열 많은 데이터셋 | 오른쪽 끝으로 스크롤해도 "기간 / 행 번호" 열 고정, 빈 칸 빗금 | 가로 스크롤을 끝까지 |
| `fu1c-s4-paste-confirm-mixed-existing-and-new.png` | 붙여넣기 확인창 | `text/plain` 3줄×3열: 기존 행 1개 덮어쓰기 + 새 행 2개 | 가장 오래된 행의 기준월 칸을 선택하고 붙여넣기 이벤트 |
| `fu1c-s4-paste-result-ok.png` | 붙여넣기 결과 | "1행을 고치고 2행을 새로 추가했습니다", 새 행 2개가 표에 반영 | 위 확인창에서 "붙여넣기 적용" |
| `fu1c-s4-paste-conflict-all-cancelled.png` | 붙여넣기 충돌 | 409 `PASTE_CONFLICT`: 전부 취소 안내, 칸 충돌 1건(서버 값 `33,333.00`)과 새 행 기간 충돌 1건, 충돌한 칸 주황 강조 | 확인창을 연 동안 다른 클라이언트(API)가 같은 칸 값과 새 행 기간을 먼저 바꿈 |
| `fu1c-s4-cell-conflict-orange-border.png` | 칸 편집 충돌 | 409 `CELL_CONFLICT`: 주황 테두리 "충돌" 칸(서버 값)과 `내 값 / 서버 값` 목록, "내 값으로 저장"/"서버 값 유지" | 다른 클라이언트(API)가 담당 칸을 먼저 바꾼 뒤 화면에서 같은 칸 편집 |
| `fu1c-s4-paste-rejected-over-5000-rows.png` | 붙여넣기 거부 | 5,001행 → "한 번에 5,000행까지만 붙여넣을 수 있습니다(지금 5,001행)", 아무것도 저장 안 함 | 맨 아래 입력 줄에서 5,001줄 붙여넣기(서버에 보내기 전 화면에서 거부) |
| `fu1c-s4-truncated-notice-validation-errors.png` | 붙여넣기 검증 오류(잘림) | 422 `VALIDATION_ERROR`: 20건만 나열하고 "일부만 표시됨(전체 250건 중 일부)", 범위 문구 `0 ~ 1,000,000` | 새 행 250줄(기준월 2040-01부터, 매출은 모두 최댓값 초과)을 붙여넣고 적용 |
| `fu1c-s4-paste-conflict-truncated.png` | 붙여넣기 충돌(잘림) | 409 `PASTE_CONFLICT`: 20건만 나열하고 "일부만 표시됨(전체 1,100건 중 일부)" | "일별 방문자"에 1,100일을 붙여넣는 확인창이 열린 동안 다른 클라이언트(API)가 같은 1,100일을 먼저 만듦 |

촬영하지 못한 화면은 없다(요청한 항목 모두 촬영). 열 목록·붙여넣기 결과 등에서 가로 스크롤바가 보이는 화면은 `fu1c-s4-entry-grid-wide-*`(열 16개)이며, 열이 6개인 "월별 매출"은 세로 스크롤바가 생기는 화면에서만 아래쪽에 가로 스크롤바가 함께 나타난다. 단 "개발용 신원 전환기가 보이는 상태"는 모든 화면 위쪽에 항상 나타나므로 전환기를 펼친 화면을 별도 파일로 두었다.

## 재촬영 방법

촬영 스크립트는 `capture/`에 있다(`seed.py` 합성 데이터, `capture.cjs` 촬영). **playwright는 이 저장소의 의존성이 아니다.** 저장소 밖에 설치하고(예: 다른 디렉터리에서 `npm i playwright`) 모듈 위치와 Chromium 실행 파일을 환경변수로 알려 준다. 저장소 `package.json`·락 파일은 건드리지 않는다.

1. 재촬영 순서 메모: `capture.cjs`는 위 시나리오 외에 `fu1c-truncated`, `fu1c-conflict-truncated`, `fu1b-inactive-team`(마지막, 팀 "임시 기획팀"을 만들어 쓰므로 S6 격자·팀 선택에 영향이 없도록 맨 뒤에 둠)을 포함한다. 결과 PNG는 임시 폴더(`--out`)에 찍은 뒤 바꿀 파일만 복사하면 나머지 PNG가 바이트 그대로 유지된다.
1. 더미 값만 든 임시 env 파일을 저장소 밖(또는 Git이 무시하는 위치)에 만든다. `AUTH_STUB_ENABLED=true`, `APP_ENV=local`, `APP_BASE_PATH=/bi-wizard`, `APP_PROXY_STRIP_PREFIX=false`, 비어 있지 않은 더미 비밀번호들. 사용자 `.env`는 쓰지 않는다.
2. **새 DB**로 스택을 띄운다(촬영은 데이터를 바꾸므로 한 번 쓴 DB를 다시 쓰지 않는다): `docker compose -p <프로젝트명> --env-file <임시 env> up -d --build frontend`
3. 시험 사용자 시드: `docker compose -p <프로젝트명> --env-file <임시 env> exec -T backend python -m app.cli seed-stub-users`
4. 합성 데이터 시드: `python3 capture/seed.py http://127.0.0.1:<FRONTEND_PORT>/bi-wizard/api <ids.json 경로>`
5. 촬영: `PLAYWRIGHT_MODULE=<playwright 모듈 경로> CHROMIUM_PATH=<chromium 실행 파일> node capture/capture.cjs --origin http://127.0.0.1:<FRONTEND_PORT> --base /bi-wizard --ids <ids.json 경로> --out . --env <임시 env> [--dump <페이지 텍스트 덤프 경로>] [--only 시나리오,시나리오]`
   - 스크립트는 촬영 순간마다 DOM 텍스트·HTML을 모아 마지막에 `--env` 파일의 비밀성 값(`*PASSWORD*`, `*SECRET*`, `*KEY*`, `*TOKEN*`)과 내부 경로·예외 흔적 패턴을 대조해 발견 건수를 출력한다(0이어야 한다). 그래도 PNG는 눈으로 확인한다.
   - 시나리오는 정의된 순서로 한 번에 돌려야 한다(뒤 시나리오가 앞에서 만든 행·소속에 기대는 부분이 있다). `--only`는 부분 재촬영용이며 앞 시나리오가 이미 바꾼 DB에서는 일부(`fu1a-s6`, `fu1c-paste` 등)가 실패할 수 있다.
6. 정리: `docker compose -p <프로젝트명> --env-file <임시 env> stop` (볼륨을 지우는 명령은 쓰지 않는다)
