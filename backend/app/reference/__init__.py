"""기준값(`reference`, FU-3, 04 §2-2, 06 §2-2): 전역 숫자 기준값 항목과 연도별 값의 목록·추가·정정.

쓰기는 관리자만, 읽기는 모두다. 이 모듈은 `formula`·`dataset`·`entry`를 import하지 않는다
(`formula`가 컴파일 때 `service.item_ids_by_name`만 읽는다). 삭제·이름 변경·설명 수정은 없다(후속).
"""
