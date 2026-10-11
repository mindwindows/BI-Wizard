# references/ — 선택된 Reference

운영 가이드 4절(REFERENCE STORAGE)에 따라 **사용자가 선택한 공개 소스만** 보관한다. Gate ① (2026-10-11) 승인 결과이며 선택 근거는 `docs/decisions/02-tech-reference.md`에 있다.

| 폴더 | 영역 | 라이선스 | 참고 우선순위 |
| --- | --- | --- | --- |
| `baserow/` | 수식 → DB 식 변환 | MIT Expat (premium/, enterprise/, docs/ 제외). `circular_reference_checker.py`는 Apache 2.0 파생 헤더 | 1 |
| `lark/` | 수식 파서 | MIT | 2 |
| `superset/` | Embedded SDK, guest token | Apache 2.0 | 3 |
| `grist-core/` | 엑셀 가져오기 | Apache 2.0 (ext/ 제외) | 4 |
| `react-datasheet-grid/` | 붙여넣기 파싱 | MIT | 5 |

## 규칙
- 저장소 전체가 아니라 비교표가 지목한 파일만 받는다. 각 폴더에 원본 `LICENSE`(와 `NOTICE`)를 함께 둔다.
- 폴더의 `README.md`에 출처 URL, 목적, 라이선스, 커밋, 참고 위치, 받지 않은 것, 파일별 SHA-256을 기록한다.
- 업스트림 경로를 그대로 유지하고 **파일을 수정하지 않는다.** 이 폴더의 코드는 제품에 포함하지 않는다. 구조·알고리즘을 참고해 `backend/`, `frontend/`에 직접 작성한다.
- 소스 복사가 필요하면 해당 라이선스의 고지·NOTICE 의무를 사용자와 먼저 확인한다.
- 다음은 받지 않고 열람·참고하지 않는다: Grist `ext/`, Baserow `premium/`·`enterprise/`·`docs/`.
- 후보를 추가하거나 교체하려면 사용자 승인이 필요하다.
