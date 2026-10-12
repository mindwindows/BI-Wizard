"""입력 그리드(`entry`): 한 기간 = 한 행 입력, 행 조회, 칸 단위 값 비교 갱신, 붙여넣기(04 §2-2).

- `values`  열 타입별 값 해석·재검증(순수 함수, 05 §1 값 표현)
- `repo`    `bi_data.ds_<번호>` 행 읽기·쓰기(SQLAlchemy 표현식만, `text()` 금지, DDL 아님)
- `service` C1~C4 로직과 트랜잭션(`datasets` 행 `FOR SHARE`, 락 대기 → `WRITE_BUSY`)
- `router`  C1~C4 엔드포인트와 붙여넣기 요청 크기 상한
"""
