"""수식 컴파일 환경 `ReferenceEnv` 만들기(07 §3-2 "환경 전달"). 컴파일 호출 지점 6곳이 공유한다.

환경 = 기준값 항목 이름 -> 번호(`reference` service의 읽기 함수 하나, 잠금 없는 SELECT)와 그
데이터셋의 기준 날짜 열 번호(`DefinitionView.base_date_column_id`). 호출 지점은 D2 `check`, D3
`preview`, D4·D5 `_compile_for_save`, D6 `view_formula`, 정의 변경 훅 `apply_definition`, 시작 대조
`view_needs_rebuild`이며, `REF`가 없는 수식도 같은 환경을 넘긴다(환경이 없는 채로 `REF`를 만나면
`RuntimeError`다: `tests/test_reference_env_calls.py`가 이 패키지의 컴파일 호출이 모두 `env=`를
넘기는지 AST로 확인한다).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.dataset.service import DefinitionView
from app.formula.context import ReferenceEnv
from app.reference import service as reference_service


def load_env(session: Session, defn: DefinitionView) -> ReferenceEnv:
    """데이터셋 정의와 현재 기준값 항목 목록으로 컴파일 환경을 만든다."""
    return ReferenceEnv(
        item_ids=reference_service.item_ids_by_name(session),
        base_date_column_id=defn.base_date_column_id,
    )
