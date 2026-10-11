# react-datasheet-grid — 붙여넣기 파싱 참고

| 항목 | 내용 |
| --- | --- |
| 출처 URL | https://github.com/nick-keller/react-datasheet-grid |
| 확보 커밋 | `862a1bb7777550fa04445fb283fa035a759c7c22` (2026-03-03, 기본 브랜치 HEAD) |
| 확보일 | 2026-10-11 |
| 라이선스 | MIT (`LICENSE` 원본 동봉, 저작권 Nicolas Keller 2022). NOTICE 파일 없음 |
| 목적 | 브리프 4.4절 데이터 입력: AG Grid Community에 없는 "엑셀에서 복사한 탭 구분 텍스트 붙여넣기"를 브라우저 paste 이벤트로 **직접 구현**할 때 파싱 알고리즘과 행 확장 로직을 참고 |
| 승인 | Gate ① (2026-10-11) 사용자 승인, `docs/decisions/02-tech-reference.md` |

## 참고할 위치
- `src/utils/copyPasting.ts` — `parseTextPlainData`, `parseTextHtmlData`
- `src/components/DataSheetGrid.tsx` — `onPaste`, `applyPasteDataToDatasheet` (붙여넣기 시작 위치, 행 초과 시 행 추가)

## 주의
- 이 후보는 **AG Grid가 아니라 별도 그리드 라이브러리**다. AG Grid Community 위에서 붙여넣기를 구현한 사례는 이번 조사에서 확보하지 못했다. 파싱 알고리즘과 행 확장 로직만 참고하고 AG Grid API(`applyTransaction` 등)로 반영하는 코드는 직접 작성한다.
- AG Grid의 Clipboard, Range Selection, Excel Export, 일괄 편집은 Enterprise 기능이다. `ag-grid-enterprise`는 쓰지 않는다.
- 붙여넣기 후 검증(필수·범위·정규식·유일성)은 이 후보가 제공하지 않으므로 별도 설계가 필요하다.
- **원본 대조로 확인된 한계(그대로 이식하지 말 것):**
  - `parseTextPlainData`는 따옴표 안의 **줄바꿈만** 셀 내용으로 유지한다. **탭은 따옴표 상태와 무관하게 셀을 나눈다**(`"a\tb"\tc` → `"a`, `b"`, `c`). 따옴표 벗기기와 `""`→`"` 복원은 따옴표로 감싼 셀 안에 `\n`이 있을 때만 일어난다. 한 줄짜리 따옴표 셀은 따옴표가 그대로 남는다(엑셀은 `"`가 든 단일행 셀도 따옴표로 감싸 복사한다). `\r`은 전부 제거된다.
  - `text/html`이 있으면 `text/plain`보다 우선한다. `<br>`는 `\n`으로 바꾸고, `<table>`이 없으면 첫 `<span>`을 쓴다.
  - 열에 `pasteValue`가 없으면 그 열은 조용히 무시된다.
  - 우리 구현에는 탭·따옴표·`\r` 테스트 케이스를 직접 작성한다.

## 사용 규칙
- 원본 그대로 보관한다. **파일을 수정하지 않는다.** 복사 시 MIT 저작권 고지를 유지한다.

## 파일 목록과 무결성

| 파일 | 크기(바이트) | SHA-256 |
| --- | --- | --- |
| `LICENSE` | 1071 | `f5c5a20af3769a77c773abeb0b694c2ebcf3c5be98ad9314f0543b98aa2b94a3` |
| `src/components/DataSheetGrid.tsx` | 58577 | `88a72f817ef4a711885014a311fe93ccda9dc3a62d478b8055d46016f2f5354d` |
| `src/utils/copyPasting.ts` | 2521 | `7231b4eab9a325c106e4a01f238cd0c855af642c8a499db58f6925702b1040ed` |
