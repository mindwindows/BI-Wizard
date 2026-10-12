# FU-1 화면 스크린샷 (1a·1b·1c·1d)

- 촬영일: 2026-10-12(화면 수정분 재촬영: 같은 날, HEAD `809ea5f` 기준으로 이미지를 다시 빌드)
- 크기: 모두 1920×1080 PNG(viewport, `deviceScaleFactor` 1, 스크롤하지 않은 첫 화면 또는 해당 영역으로 스크롤한 화면). 1a·1b·1c 42장(합계 약 5.6 MiB)과 1d 36장(합계 약 7.0 MiB)을 합쳐 PNG 78장, 약 13 MiB. 1d는 2026-10-12(HEAD `c161979` 기준, 이미지를 작업 트리로 다시 빌드)에 추가로 찍었고 기존 42장은 바꾸지 않았다.
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

촬영 조건 공통: 1920×1080, `deviceScaleFactor` 1, 합성 데이터셋 "월별 손익"(26개월, 인원 0이 2개월·빈 값 1개월, 광고비 빈 값 2개월)과 "월별 수금", compose 프로젝트 `shots4`, HEAD `c161979`, 시드 `capture/seed1d.py`, 촬영 `capture/capture1d.cjs`. 별도 표기가 없으면 실제 서버 응답이다.

| 파일 | 화면 | 상태 | 촬영 조건 |
| --- | --- | --- | --- |
| `fu1d-editor-empty-new-formula-column.png` | 수식 편집기 | 계산 열 추가 직후 빈 편집기(열 이름 칩, 안내 문구) | `stub-definer`, "월별 손익", "계산 열 추가" |
| `fu1d-editor-column-chip-inserted.png` | 수식 편집기 | 열 이름 칩 클릭으로 `[매출] / [인원]` 삽입(확인 중) | 칩 "매출", `/` 입력, 칩 "인원" |
| `fu1d-editor-autocomplete-function-list.png` | 수식 편집기 | 함수 자동완성 열림(`RO` 입력, 후보와 설명·엑셀과 차이) | `RO` 입력 후 ↓ |
| `fu1d-editor-autocomplete-column-list.png` | 수식 편집기 | `[` 입력 시 열 이름 후보(입력 열·계산 열 구분) | `[` 입력 |
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
| `fu1d-grid-calculated-columns-overview.png` | 입력 그리드 | 입력 열 쪽 화면(계산 열은 오른쪽으로 스크롤해야 보임) | `stub-entry` |
| `fu1d-grid-calculated-columns-scrolled-right.png` | 입력 그리드 | 계산 열 머리글 `ƒ`·기울임·아래 선, 이탤릭 회색 값, 빈 계산 칸 | 가로 스크롤 끝 |
| `fu1d-grid-calculated-cell-edit-attempt.png` | 입력 그리드 | 계산 열 오류 칸을 두 번 눌러 `123` 입력 시도: 편집기가 열리지 않음(안내 문구 없음) | 오류 칸 더블클릭 + 입력 |
| `fu1d-grid-error-cell-e1-and-blank-cells-widened-column.png` | 입력 그리드 | 열 폭을 넓힌 "1인당 매출": `오류 E1` 칸(붉은 배경)과 빈 칸, 선택된 열 머리글 | 머리글 경계를 마우스로 드래그 |
| `fu1d-formula-view-division-with-error-cells-entry.png` | 수식 보기 | `[매출] / [인원]`, 결과 종류, 쓰는 열, 오류 칸 2개 + "점검 화면에서 보기" 링크(입력자, 읽기 전용) | `stub-entry`, "1인당 매출" |
| `fu1d-formula-view-sumtag-with-tag-columns-entry.png` | 수식 보기 | `SUMTAG("비용")`, 태그로 더하는 열(광고비, 물류비) | `stub-entry`, "총비용" |
| `fu1d-formula-view-definer-with-edit-button.png` | 수식 보기 | 정의 담당자: 수식 보기 + "수식 고치기" 버튼 | `stub-definer`, "손익률" |
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

1d에서 찍지 못한 것: `FORMULA_CIRCULAR` 저장 단계의 경로 안내(검사 단계에서 같은 문구가 먼저 나와 저장 버튼이 막힘), 뷰가 없는 동안의 입력 그리드(계산 열이 빈 값). `PREVIEW_BUSY` 두 장은 서버가 아니라 브라우저에서 응답을 바꾼 모의 화면이다.

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

### 1d 재촬영 방법

1. 위 1~3번과 같이 새 DB로 스택을 띄우고 `seed-stub-users`까지 실행한다(포트는 65535 이하여야 한다).
2. 시드: `python3 capture/seed1d.py http://127.0.0.1:<FRONTEND_PORT>/bi-wizard/api <ids1d.json>`
3. 촬영은 단계로 나눠 `--only`로 실행한다: ① `editor-empty,editor-chip,editor-autocomplete,editor-errors,editor-preview-ok,editor-preview-mixed,editor-preview-busy,editor-circular,editor-readonly,grid,formula-view,s5,s9-ok` ② 관리자 DB에서 `DROP VIEW bi_data.dv_1`, `dv_2` 후 `datasets` 행 `FOR NO KEY UPDATE` 잠금을 80초 쥐고(별도 psql 세션) backend를 재시작해 `LOCK_TIMEOUT` 실패를 만든 뒤 `LOCK_WAIT_MS=62000`으로 `s9-failed` ③ `fixdata,s5-empty,result-type-changed`. `capture1d.cjs`는 `capture.cjs`와 같은 방식으로 DOM 텍스트·HTML을 임시 env의 비밀성 값과 대조한다.
