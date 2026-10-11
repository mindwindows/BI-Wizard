# grist-core — 엑셀 가져오기 참고

| 항목 | 내용 |
| --- | --- |
| 출처 URL | https://github.com/gristlabs/grist-core |
| 확보 커밋 | `6dfae2fa33af6ef057b5de676afc85e6f3026fc6` (2026-10-09, 기본 브랜치 HEAD) |
| 확보일 | 2026-10-11 |
| 라이선스 | Apache License 2.0 (`LICENSE.txt`, `NOTICE.txt` 원본 동봉) |
| 목적 | 브리프 4.2절 엑셀 가져오기: 헤더 행 자동 탐지, 열 타입 추론, 가져오기 단계 UI 흐름, 기존 표에 추가·갱신하는 흐름을 **구조·알고리즘 수준**에서 참고 |
| 승인 | Gate ① (2026-10-11) 사용자 승인, `docs/decisions/02-tech-reference.md` |

## 참고할 위치
- `sandbox/grist/imports/import_xls.py` — 시트별 테이블 생성, 샘플 행으로 `headers_guess` 호출
- `sandbox/grist/imports/import_utils.py` — `headers_guess` (헤더 행 추정)
- `sandbox/grist/parse_data.py` — `ColumnDetector` (열 타입 추론)
- `app/client/components/Importer.ts` — 가져오기 UI 흐름(미리보기, 대상 테이블 선택, 기존 표 갱신, 열 매핑)

## 원본 대조로 확인된 세부 (비교표 서술의 보정)
- `headers_guess`: 최빈값(`column_count_modal`)은 셀이 2개 이상인 행만 센다. 후보 행은 `find_first_non_empty_row`가 고르며 기준은 비어 있지 않은 셀 수가 아니라 **마지막 비어 있지 않은 셀의 위치+1**(`_count_nonempty`)이고, 조건은 `length >= modal - 1`이다. 후보가 헤더가 아니면 `data_offset`이 줄어들고, 그 앞 행들은 헤더도 데이터도 아닌 채 버려진다. 숫자처럼 보이는 문자열도 헤더로 인정하지 않는다.
- `ColumnDetector`: 90% 기준은 `count >= nonjunk*(1-0.10)`이고, 미달 시 반환 타입은 `Text`가 아니라 **`Any`**(`AnyConverter`)다. 이 모듈은 이미 타입이 있는 값(엑셀)만 다루고 문자열 파싱은 다른 곳에서 한다. 변환 실패 값은 `str(value)`로 남는다.
- `Importer.ts`: "Match on"이라는 문구는 없다. 실제 UI 문구는 "Merge rows that match these fields:", placeholder "Select fields to match on"이다. "Update existing records"는 대상이 기존 표일 때만, "Skip Import"는 소스가 2개 이상일 때만 보인다.

## 받지 않은 것
- `ext/` 디렉터리와 기본 Docker 이미지(`gristlabs/grist`)가 내려받는 확장: README에 따르면 free 또는 open-source 라이선스가 아닌 "Full Grist" 확장이므로 **받지 않았고 열람하지 않는다.**
- 저장소의 나머지 전체. 위 4개 파일과 LICENSE·NOTICE만 있다.

## 사용 규칙
- 원본 그대로 보관한다. **파일을 수정하지 않는다.**
- 코드 복사 대신 알고리즘만 재작성해 참고한다. 복사가 필요하면 Apache 2.0의 라이선스·NOTICE 유지와 변경 표시 의무를 사용자와 먼저 확인한다.
- 병합 셀·다단 헤더 처리는 브리프 범위 밖이므로 참고하지 않는다.

## 파일 목록과 무결성

| 파일 | 크기(바이트) | SHA-256 |
| --- | --- | --- |
| `LICENSE.txt` | 11351 | `b294d13c309ff8634417ff8fe133dbb7447d33245bce801db158f38d7fa40d50` |
| `NOTICE.txt` | 141 | `ed02f6afd97160236b66b20cce087f4d902fe4057b1cf85bdd678d7469643802` |
| `app/client/components/Importer.ts` | 71732 | `29d1c2021c7aa605719ace37705f14a77e377042afad12abe986379d4121a605` |
| `sandbox/grist/imports/import_utils.py` | 4804 | `a2d701a17dceed72a200b5f49b9c818fe9142a0286c617d700ddbcc75b68de1a` |
| `sandbox/grist/imports/import_xls.py` | 4082 | `a6262311b3bd4b0e1cd4e4b827315ea47b17973daf2ebf6632985cca2c707678` |
| `sandbox/grist/parse_data.py` | 7928 | `9fc1fb4426070e338e3efee7f3d0664d8a9afb7412b56de293644d38540c0631` |
