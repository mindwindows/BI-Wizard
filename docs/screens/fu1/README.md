# FU-1 화면 스크린샷 (1a·1b·1c·1d·1e)

- 촬영일: 2026-10-12(화면 수정분 재촬영: 같은 날, HEAD `809ea5f` 기준으로 이미지를 다시 빌드)
- 크기: 모두 1920×1080 PNG(viewport, `deviceScaleFactor` 1, 스크롤하지 않은 첫 화면 또는 해당 영역으로 스크롤한 화면). 1a·1b·1c 42장(합계 약 5.6 MiB)과 1d 38장(합계 약 7.6 MiB)을 합쳐 PNG 80장, 약 14 MiB. 1d는 2026-10-12(HEAD `c161979` 기준)에 추가로 찍었고, 같은 날 화면 수정분(HEAD `42c3619` + 작업 트리, 프로젝트 `shots5`)으로 17장을 다시 찍고 2장을 새로 추가했다. 1a·1b·1c 42장과 나머지 1d 장은 바이트 그대로다.
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


### 1d 수식 열(계산 열)

촬영 조건 공통: 1920×1080, `deviceScaleFactor` 1, 합성 데이터셋 "월별 손익"(26개월, 인원 0이 2개월·빈 값 1개월, 광고비 빈 값 2개월)과 "월별 수금", compose 프로젝트 `shots4`(수정분 재촬영은 `shots5`, HEAD `42c3619` + 작업 트리), 시드 `capture/seed1d.py`, 촬영 `capture/capture1d.cjs`. 별도 표기가 없으면 실제 서버 응답이다.

| 파일 | 화면 | 상태 | 촬영 조건 |
| --- | --- | --- | --- |
| `fu1d-editor-empty-new-formula-column.png` | 수식 편집기 | 계산 열 추가 직후 빈 편집기(열 이름 칩, 안내 문구) | `stub-definer`, "월별 손익", "계산 열 추가" |
| `fu1d-editor-column-chip-inserted.png` | 수식 편집기 | 열 이름 칩 클릭으로 `[매출] / [인원]` 삽입(확인 중) | 칩 "매출", `/` 입력, 칩 "인원" |
| `fu1d-editor-autocomplete-function-list.png` | 수식 편집기 | 함수 자동완성 열림(`RO` 입력, 후보와 설명·엑셀과 차이) | `RO` 입력 후 ↓ |
| `fu1d-editor-autocomplete-column-list.png` | 수식 편집기 | `[` 입력 시 열 이름 후보 12개(입력 열·계산 열 구분). 목록이 8줄까지만 보이고 세로 스크롤바가 생기며 아래에 "후보 12개 — 목록을 스크롤하거나 ↑↓로 끝까지 고르고…" 안내(2026-10-12 재촬영) | `[` 입력 |
| `fu1d-editor-autocomplete-column-list-scroll-hint.png` | 수식 편집기 | (신규) 위 목록을 ↓로 마지막 후보("등급")까지 내려 목록이 스크롤된 상태와 "후보 12개" 안내 | `[` 입력 후 ↓ 11번 |
| `fu1d-editor-autocomplete-tag-list.png` | 수식 편집기 | `SUMTAG("` 안의 구분 태그 후보 | `SUMTAG("` 입력 |
| `fu1d-editor-error-unknown-column.png` | 수식 편집기 | 쉬운 말 오류: 없는 열 이름(밑줄이 `[없는열]`에 정확히 일치) | `[없는열]*2` |
| `fu1d-editor-error-arg-count.png` | 수식 편집기 | 쉬운 말 오류: 인수 개수 | `ROUND([매출])` |
| `fu1d-editor-error-type-mismatch-text-plus-number.png` | 수식 편집기 | 쉬운 말 오류: 형 불일치(글자+숫자) | `[담당]+1` |
| `fu1d-editor-error-type-mismatch-ampersand-number.png` | 수식 편집기 | 쉬운 말 오류: `&`에 숫자(자동 변환 없음) | `LEFT([담당],2)&"-"&[1인당 매출]` |
| `fu1d-editor-error-unclosed-parenthesis.png` | 수식 편집기 | 쉬운 말 오류: 수식이 끝났는데 완성되지 않음(수식 끝 위치 표시) | `ROUND([매출]/3, 2` |
| `fu1d-editor-check-ok-top.png` | 수식 편집기 | 검사 통과("결과는 숫자입니다. 쓰는 열"), 태그 입력 칸, 미리보기 시작 | `[매출]-[물류비]` |
| `fu1d-editor-preview-ok-20-rows.png` | 수식 편집기 | 미리보기 정상: 최근 20행, 오류 칸 0개·빈 값 0개(아래로 스크롤한 화면) | 같은 수식 |
| `fu1d-editor-preview-error-and-empty-cells.png` | 수식 편집기 | 미리보기에 오류 칸(0으로 나눔 E1)과 빈 값(빗금) 혼재, `오류 칸 2개 · 빈 값 1개` | `[매출]/[인원]` |
| `fu1d-editor-preview-busy-auto-retrying.png` | 수식 편집기 | `PREVIEW_BUSY` 자동 재시도 안내(**모의 응답**) | 브라우저에서 미리보기 요청만 429로 바꿈 |
| `fu1d-editor-preview-busy-retry-button.png` | 수식 편집기 | `PREVIEW_BUSY` 후 "다시 시도" 버튼(**모의 응답**) | 위와 같고 5초 뒤 |
| `fu1d-editor-circular-after-check.png` | 수식 편집기 | 순환 참조: 검사 단계에서 "열이 서로를 참조해 계산할 수 없습니다: 손익 → 손익률 → 손익" | "손익" 열 수식 고치기에서 `[손익률]+1` |
| `fu1d-editor-result-type-changed-notice.png` | 수식 편집기 | `result_type_changed` 안내(저장 성공 + 차트 확인 안내) | "등급" 열 수식을 글자->숫자 결과로 저장 |
| `fu1d-formula-view-readonly-no-define-permission-viewer.png` | 수식 보기 | 정의 권한 없음(열람자): 수식 보기만 있고 "수식은 팀의 정의 담당자만 고칠 수 있습니다." | `stub-viewer`, "1인당 매출" |
| `fu1d-grid-calculated-columns-overview.png` | 입력 그리드 | 입력 열 쪽 화면(계산 열은 오른쪽으로 스크롤해야 보임; 수정분 재촬영, 화면은 이전과 같음) | `stub-entry` |
| `fu1d-grid-calculated-columns-scrolled-right.png` | 입력 그리드 | 계산 열 머리글 `ƒ`·기울임, 칸 왼쪽 세로 선(계산 열 표지), 값 있는 칸은 회색 배경·이탤릭, 빈 계산 칸은 입력 열과 같은 빗금, 오류 칸은 붉은 배경(2026-10-12 재촬영) | 가로 스크롤 끝 |
| `fu1d-grid-calculated-cell-edit-attempt.png` | 입력 그리드 | 계산 열 오류 칸을 두 번 눌러 `123` 입력 시도: 편집기가 열리지 않고 그리드 위에 노란 안내 "계산 열은 수식으로 계산되어 직접 고칠 수 없습니다. 수식은 Inspector에서 고칠 수 있습니다."(5초간, 2026-10-12 재촬영) | 오류 칸 더블클릭 + 입력 |
| `fu1d-grid-error-cell-e1-and-blank-cells-widened-column.png` | 입력 그리드 | (2026-10-12 재촬영: 안내 문구가 아직 남아 있고 계산 열 표지·빗금 반영) 열 폭을 넓힌 "1인당 매출": `오류 E1` 칸(붉은 배경)과 빈 칸, 선택된 열 머리글 | 머리글 경계를 마우스로 드래그 |
| `fu1d-formula-view-division-with-error-cells-entry.png` | 수식 보기 | `[매출] / [인원]`, 결과 종류, 쓰는 열, 오류 칸 2개 + "점검 화면에서 보기" 링크(입력자, 읽기 전용) | `stub-entry`, "1인당 매출" |
| `fu1d-formula-view-sumtag-with-tag-columns-entry.png` | 수식 보기 | `SUMTAG("비용")`, 태그로 더하는 열(광고비, 물류비) | `stub-entry`, "총비용" |
| `fu1d-formula-view-definer-with-edit-button.png` | 수식 보기 | 정의 담당자: 수식 보기 + "수식 고치기" 버튼이 위에, 접힌 "열 정보"가 아래에(2026-10-12 재촬영) | `stub-definer`, "손익률" |
| `fu1d-formula-view-calculated-column-info-collapsed.png` | 수식 보기(Inspector 전체) | (신규) 계산 열 선택 시 수식 보기·수식 고치기가 위에, 읽기 전용 열 정보는 접힌 "열 정보" 구역(▶)으로 내려감 | `stub-definer`, "손익률" |
| `fu1d-formula-edit-opened-definer.png` | 수식 고치기 | 수식 고치기 편집기가 보기 텍스트로 열림, 검사 통과, 미리보기(빈 값 2개) | "수식 고치기" 클릭 |
| `fu1d-formula-view-no-error-cells-entry.png` | 수식 보기 | 오류 칸 "없음"(원인 값을 고친 뒤) | `stub-entry`, "1인당 매출" |
| `fu1d-s5-checks-error-columns-list.png` | S5 점검 | 오류 칸이 있는 열 목록(데이터셋·팀·계산 열·건수, 오류 칸 보기·작업공간 열기) | `stub-viewer`, `/checks` |
| `fu1d-s5-checks-error-cells-expanded.png` | S5 점검 | 열을 펼침: 기간·행·코드·이유(E1) | "오류 칸 보기" |
| `fu1d-s5-checks-deeplink-from-formula-view.png` | S5 점검 | 수식 보기 링크로 열린 화면(그 열이 처음부터 펼쳐짐) | `/checks?dataset=1&column=7` |
| `fu1d-s5-checks-empty-no-errors.png` | S5 점검 | 빈 상태: "계산 오류 칸이 없습니다. 모든 계산 열이 정상입니다." | 원인 값을 고친 뒤 |
| `fu1d-s9-views-section-normal.png` | S9 현황 | 뷰 재생성 구역 정상: "확인한 데이터셋 2개 중 실패 0개" | `stub-admin`, `/admin/status` |
| `fu1d-s9-views-section-failed-list.png` | S9 현황 | 실패 목록 2건(`LOCK_TIMEOUT`, 실패한 시각, 개별·전부 다시 시도) | 관리자 DB에서 `DROP VIEW` 2개 + 행 잠금을 쥔 채 backend 재시작 |
| `fu1d-s9-views-section-retry-while-locked.png` | S9 현황 | 잠금이 남은 동안 다시 시도: "다른 작업이 진행 중입니다…(약 2초 뒤)" 안내(`DEFINITION_BUSY`), 실패 2건 그대로 | "이 데이터셋 다시 시도" |
| `fu1d-s9-views-section-after-single-retry.png` | S9 현황 | 잠금이 풀린 뒤 1건 다시 시도: "1개를 다시 만들었습니다. 아직 1개가 실패 상태입니다" | 같은 버튼 |
| `fu1d-s9-views-section-recovered.png` | S9 현황 | "실패한 항목 전부 다시 시도" 뒤 복구: 실패 0개 | 전부 다시 시도 |

2026-10-12 재촬영 대상(17장): 위 표에서 `fu1d-editor-autocomplete-column-list`, `fu1d-editor-check-ok-top`, `fu1d-editor-circular-after-check`, `fu1d-editor-error-arg-count`("ROUND에는 값이 2개 필요한데 1개가 들어 있습니다."), `fu1d-editor-preview-*`(2장, 기간 줄바꿈 없음), `fu1d-editor-result-type-changed-notice`, `fu1d-formula-*`(6장), `fu1d-grid-*`(4장). 나머지 1d 장(편집기 빈 화면·칩·함수/태그 자동완성·나머지 오류 4장·PREVIEW_BUSY, S5, S9)은 바꾸지 않았다.

1d에서 찍지 못한 것: `FORMULA_CIRCULAR` 저장 단계의 경로 안내(검사 단계에서 같은 문구가 먼저 나와 저장 버튼이 막힘), 뷰가 없는 동안의 입력 그리드(계산 열이 빈 값). `PREVIEW_BUSY` 두 장은 서버가 아니라 브라우저에서 응답을 바꾼 모의 화면이다.

### 1e Superset 연동(S7 대시보드, S8 연결 관리, S9 동기 구역, S2 동기 상태 열)

촬영 조건 공통: 2026-10-13, HEAD `361c32f`, 1920×1080, `deviceScaleFactor` 1, Chromium(`ignoreDefaultArgs: ['--hide-scrollbars']`, `timezoneId: 'Asia/Seoul'`, locale `ko-KR`). compose 프로젝트 `shot1e`(포털 36180, backend 39180, DB 36480, `APP_BASE_PATH=/bi-wizard`, `APP_PROXY_STRIP_PREFIX=false`, `AUTH_STUB_ENABLED=true`), 임시 env 파일(더미 비밀값, 사용자 `.env` 미사용). 합성 데이터셋 "일별 손익"(365일 × 구분 4종, 계산 열 이익·비용률), "월별 수금" 등. 대시보드는 Superset에서 `seed1e.py`가 만들고 임베드를 켰으며 `bi_guest` 입장권으로 열었다. 입장권·비밀번호는 어느 화면에도 나오지 않는다. 시나리오는 `capture/capture1e.cjs`, 데이터는 `capture/seed1e.py`다.

| 파일 | 화면 | 상태 | 촬영 조건 |
| --- | --- | --- | --- |
| `fu1e-s7-dashboard-select-prompt.png` | S7 대시보드 | 대시보드를 고르기 전 빈 상태("왼쪽 목록에서 대시보드를 고르세요"), 작성자 안내문은 접힌 상태 | `stub-viewer`, `/dashboards` |
| `fu1e-s7-dashboard-loading.png` | S7 | 입장권을 받는 중 "대시보드를 불러오는 중…" | 입장권 요청(`/guest-token`) 응답만 브라우저 쪽에서 6초 늦춤(지연 주입, 서버·화면 코드는 그대로) |
| `fu1e-s7-dashboard-six-charts-viewer.png` | S7 정상 | 목록 3개 + 차트 6종(선·막대·표·큰 숫자 추세·원형·혼합)이 모두 그려진 임베드 첫 화면(둘째 줄은 임베드 안쪽 스크롤 때문에 아래가 잘림) | `stub-viewer`, 대시보드 "손익 현황 (지원 차트 6종)" |
| `fu1e-s7-dashboard-six-charts-viewer-scrolled-down.png` | S7 정상 | 같은 대시보드를 임베드 안에서 아래로 스크롤해 둘째 줄(큰 숫자·원형·혼합)이 온전히 보임 | 위 화면에서 마우스 휠 |
| `fu1e-s7-author-guide-open.png` | S7 작성자 안내문 | 펼친 상태: 지원 차트 6가지, `[팀] 이름` 데이터셋 이름, 시간 필터, `team` 열, Superset 별도 로그인 안내. 위쪽 "차트 만들기 (새 창)" 링크 | `stub-viewer`, 안내문 펼침 |
| `fu1e-s7-dashboard-blank-allowed-domains.png` | S7 화면이 비어 있음 안내 | 임베드 허용 도메인이 포털 주소와 다른 대시보드("허용 도메인이 다른 대시보드"): 입장권은 받지만 Superset이 403을 돌려줘 15초 뒤 "대시보드 화면이 비어 있습니다…" 안내가 뜬다 | 허용 도메인 `https://other.example`로 임베드를 켠 대시보드 |
| `fu1e-s7-dashboard-error-429-rate-limited.png` | S7 429 안내 | "요청이 너무 많습니다. 약 59초 뒤에 다시 시도해 주세요." + 문의 번호 + "다시 시도" | 같은 사용자(`stub-entry`)가 60초 안에 입장권 API를 33번 호출(30번 200, 3번 429, 실제 한도) 직후 화면을 연다 |
| `fu1e-s7-dashboard-error-503-superset-down.png` | S7 503 안내 | "대시보드 서비스에 연결할 수 없습니다. 잠시 뒤 다시 시도해 주세요." + 문의 번호 + "다시 시도" | `docker compose stop superset` 상태 |
| `fu1e-s7-dashboard-none-linked.png` | S7 대시보드 없음 | "연결된 대시보드가 없습니다. 차트를 만든 뒤 관리자에게 대시보드 연결을 요청하세요." | 관리자가 대시보드 3개를 모두 연결 해제(촬영 뒤 다시 연결) |
| `fu1e-s8-connections-list-admin.png` | S8 연결 관리 | 관리자: 연결 방법 안내, 새 연결 폼(등록 버튼 비활성), 연결된 대시보드 3개 | `stub-admin`, `/admin/dashboards` |
| `fu1e-s8-form-error-uuid-format.png` | S8 폼 오류 | 번호 형식 오류("임베드 번호는 하이픈이 있는 36자…여야 합니다"), 등록 버튼 비활성 | 번호에 `1234-not-a-uuid` 입력 |
| `fu1e-s8-form-uuid-uppercase-normalized-notice.png` | S8 폼 안내 | 대문자 번호 입력 시 "대문자는 소문자로 바꿔서 등록합니다" 안내 | 기존 번호를 대문자로 입력 |
| `fu1e-s8-form-error-duplicate-409.png` | S8 폼 오류 | 409 중복: "이미 연결된 임베드 번호입니다. 목록에서 해제된 항목이 있으면 '다시 연결'을 쓰세요." + 문의 번호 | 이미 등록된 번호로 "연결 등록" |
| `fu1e-s8-form-error-empty-name.png` | S8 폼 오류 | 이름이 공백뿐: "이름을 입력해 주세요." | 이름에 공백만 입력 |
| `fu1e-s8-rename-inline.png` | S8 이름 변경 | 행 안에서 이름을 고치는 상태(저장은 값이 바뀔 때까지 비활성) | 행의 "이름 변경" |
| `fu1e-s8-connections-list-inactive-row.png` | S8 보관(연결 해제) | 한 항목이 "해제됨" 배지, 버튼은 "다시 연결" | 행의 "연결 해제" |
| `fu1e-s8-connections-list-reactivated.png` | S8 활성 전환 | "다시 연결" 뒤 "연결됨"으로 돌아옴 | 행의 "다시 연결" |
| `fu1e-s8-access-denied-non-admin.png` | S8 접근 거부 | "관리자만 사용할 수 있는 화면입니다." | `stub-entry`가 `/admin/dashboards` 직접 접속 |
| `fu1e-s9-sync-all-registered.png` | S9 동기 구역 registered | 전체 2개 모두 "등록됨", 마지막 등록 시각, "대기·실패 전부 다시 동기" 비활성 | `stub-admin`, `/admin/status` |
| `fu1e-s9-sync-failed-with-error-code-admin.png` | S9 failed(관리자) | "등록 실패" 2개, 실패 사유 `UNAVAILABLE_CONNECT: 대시보드 서비스에 연결하지 못했습니다.`(코드는 관리자에게만), 행마다 "다시 동기" | `docker compose stop superset` 중 데이터셋 생성 |
| `fu1e-s9-sync-filter-failed-admin.png` | S9 failed 필터 | 상태 필터 "등록 실패"로 거른 목록 | 필터 선택 |
| `fu1e-s9-sync-retry-accepted.png` | S9 다시 시도 | "2개를 다시 등록하도록 접수했습니다…" 안내(Superset이 멈춰 있어 결과는 여전히 실패) | "대기·실패 전부 다시 동기" 클릭 |
| `fu1e-s9-sync-pending-admin.png` | S9 pending | "등록 대기" 3개와 "다시 동기" 버튼, 사유 칸은 비어 있음 | Superset 컨테이너를 `docker compose pause`한 채 데이터셋 3개 생성(응답이 없어 처리 중) |
| `fu1e-s9-sync-filter-pending-admin.png` | S9 pending 필터 | 상태 필터 "등록 대기"로 거른 목록 | 필터 선택 |
| `fu1e-s9-sync-recovered-all-registered.png` | S9 복구 | Superset을 되살린 뒤 7개 모두 "등록됨" | `unpause` 후 약 10초 |
| `fu1e-s9-access-denied-non-admin.png` | S9 접근 거부 | 정의 담당자가 `/admin/status` 접속: "관리자만 사용할 수 있는 화면입니다." | `stub-definer` |
| `fu1e-s2-dataset-list-sync-registered.png` | S2 동기 상태 열 registered | "등록됨" 배지 | `stub-definer`, `/datasets` |
| `fu1e-s2-dataset-list-sync-failed-definer.png` | S2 failed(정의 담당자) | "등록 실패" 배지(사유 코드는 보이지 않음) | `stub-definer`, Superset 정지 상태 |
| `fu1e-s2-dataset-list-sync-failed-viewer.png` | S2 failed(열람자) | 같은 배지, "새 데이터셋" 없이 안내 문구 | `stub-viewer` |
| `fu1e-s2-dataset-list-sync-pending-definer.png` | S2 pending | "등록 대기" 배지 | Superset 일시 정지 중 |
| `fu1e-superset-계산열숫자.png` | Superset 화면(선택) | Superset 대시보드 "계산 열 숫자 확인": 표에 계산 열 비용률·이익 숫자, 큰 숫자 0.6115, 비용률 선 | Superset에 관리자로 로그인해 대시보드를 직접 연다(포털 아님) |

"비관리자에게 `last_error`가 숨겨진다"는 API 응답으로도 확인했다(정의 담당자의 E1 응답의 `last_error`가 전부 `null`, 촬영 스크립트의 메모 출력). S2 목록 화면에는 어느 사용자에게도 사유 코드가 보이지 않는다.

1e에서 찍지 못한 것(사유):
- 한 화면에 registered·pending·failed 배지가 함께 나오는 S2: 실패는 Superset 정지(연결 거부)에서, 대기는 Superset 일시 정지에서만 만들어져 같은 시점에 둘을 겹쳐 만들지 못했다. 상태별로 따로 찍었다(S9에는 registered와 pending, registered와 failed가 함께 나온 화면이 있다).
- S8 등록 성공 화면("'이름' 대시보드를 연결했습니다"): 새 임베드 번호를 만들려면 Superset 대시보드를 하나 더 만들어 S7 목록에 남게 되어 생략했다. 단위 시험(`dashboards.test.tsx`)이 문구를 검증한다.
- 5분 넘는 열람의 입장권 갱신 실패 배너, 허용 도메인 안내가 아닌 502(`SUPERSET_REJECTED`) 안내: 재현에 Superset 설정을 바꾸거나 5분 이상 기다려야 해 제외했다.


(1a~1d) 촬영하지 못한 화면은 없다(요청한 항목 모두 촬영). 열 목록·붙여넣기 결과 등에서 가로 스크롤바가 보이는 화면은 `fu1c-s4-entry-grid-wide-*`(열 16개)이며, 열이 6개인 "월별 매출"은 세로 스크롤바가 생기는 화면에서만 아래쪽에 가로 스크롤바가 함께 나타난다. 단 "개발용 신원 전환기가 보이는 상태"는 모든 화면 위쪽에 항상 나타나므로 전환기를 펼친 화면을 별도 파일로 두었다.

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

### 1d 재촬영 방법

1. 위 1~3번과 같이 새 DB로 스택을 띄우고 `seed-stub-users`까지 실행한다(포트는 65535 이하여야 한다).
2. 시드: `python3 capture/seed1d.py http://127.0.0.1:<FRONTEND_PORT>/bi-wizard/api <ids1d.json>`
3. 촬영은 단계로 나눠 `--only`로 실행한다: ① `editor-empty,editor-chip,editor-autocomplete,editor-errors,editor-preview-ok,editor-preview-mixed,editor-preview-busy,editor-circular,editor-readonly,grid,formula-view,s5,s9-ok` ② 관리자 DB에서 `DROP VIEW bi_data.dv_1`, `dv_2` 후 `datasets` 행 `FOR NO KEY UPDATE` 잠금을 80초 쥐고(별도 psql 세션) backend를 재시작해 `LOCK_TIMEOUT` 실패를 만든 뒤 `LOCK_WAIT_MS=62000`으로 `s9-failed` ③ `fixdata,s5-empty,result-type-changed`. `capture1d.cjs`는 `capture.cjs`와 같은 방식으로 DOM 텍스트·HTML을 임시 env의 비밀성 값과 대조한다.


### 1e 재촬영 방법

1. 더미 값만 든 임시 env 파일을 저장소 밖 또는 Git이 무시하는 위치(`_workspace/qa/`)에 만든다(`AUTH_STUB_ENABLED=true`, `APP_ENV=local`, `APP_BASE_PATH=/bi-wizard`, `APP_PROXY_STRIP_PREFIX=false`, 비밀 변수 10개는 새로 만든 무작위 값, 포트는 65535 이하). 새 DB(전용 프로젝트명 `shot1e`)로 `docker compose -p shot1e --env-file <임시 env> up -d`. 이미지는 먼저 `build backend frontend`(이 세션은 CA 묶음을 넣는 보조 Dockerfile을 `-f` override로 썼다). `${SUPERSET_APP_ROOT}/health`가 200이 될 때까지 기다린 뒤 `exec -T backend python -m app.cli seed-stub-users`.
2. 합성 데이터: `python3 capture/seed1e.py portal http://127.0.0.1:<FRONTEND_PORT>/bi-wizard/api <ids1e.json>` 다음, Superset 관리자 값을 환경변수로만 넘겨 `SUPERSET_ADMIN_USER=… SUPERSET_ADMIN_PASSWORD=… python3 capture/seed1e.py superset <API 주소> http://127.0.0.1:<FRONTEND_PORT>/bi-wizard/superset <ids1e.json> http://127.0.0.1:<FRONTEND_PORT>`(임시 env를 `set -a; . <임시 env>; set +a`로 읽어 넘긴다. 값을 파일·명령줄에 쓰지 않는다). 포털이 가상 데이터셋을 등록하는 동안(최대 약 1분) 스크립트가 기다린다.
3. 촬영(`PLAYWRIGHT_MODULE`·`CHROMIUM_PATH` 지정, `node capture/capture1e.cjs --origin http://127.0.0.1:<FRONTEND_PORT> --base /bi-wizard --ids <ids1e.json> --out . --env <임시 env> --only …`)은 단계로 나눈다.
   - ① 정상 단계: `s7-select,s7-loading,s7-six,s7-guide,s7-blank,s8,s8-toggle,s8-denied,sync-registered,s7-nodash,s7-429,superset-calc`(`superset-calc`만 `SUPERSET_ADMIN_USER`·`SUPERSET_ADMIN_PASSWORD` 환경변수 필요. `s7-429`는 해당 사용자의 60초 한도를 쓰므로 마지막에 둔다)
   - ② `docker compose -p shot1e … stop superset` → `python3 capture/seed1e.py extra <API 주소> "지점별 재고"`(8초쯤 기다리면 `failed`) → `s7-503`, 이어서 `sync-failed,sync-retry`
   - ③ `docker compose … start superset`로 되살린 뒤 `docker compose … pause superset` → `seed1e.py extra`로 데이터셋 3개 → **곧바로** `sync-pending`(처리 중 대기는 잠시만 유지된다) → `docker compose … unpause superset` → 약 10초 뒤 `sync-recovered`
4. 정리: `docker compose -p shot1e --env-file <임시 env> stop`, 컨테이너는 `rm -f`(서비스 이름 지정), 볼륨은 이름을 지정해 삭제한다(`down -v` 금지).
5. 촬영 스크립트는 촬영 순간마다 포털 DOM 텍스트·HTML(임베드 iframe 안 포함)을 임시 env의 비밀성 값과 입장권 모양(`eyJ…`)·`Bearer`·`Authorization`·내부 경로 패턴에 대조해 발견 건수를 출력한다(0이어야 한다).
