"""기준값 정정 영향 조회(05 §2-8 R6): 항목을 `REF("이름")`으로 쓰는 데이터셋 목록.

저장된 수식 AST(`formulas.ast`)를 **파이썬으로 훑어** `{"t":"call","n":"REF","a":[{"t":"text",
"v":이름}]}` 노드를 찾는다(새 표·열·마이그레이션이 없다). 정정 확인창의 영향 목록용이며 실패하면
화면이 일반 경고로 대체한다. 구현 위치가 `formula`인 이유: `formula`가 `reference`를 읽는 방향이라
`reference`가 `formula`를 부르면 순환이 생긴다(04 §2-2). 항목 이름·존재는 `reference` service를,
데이터셋 이름·팀·상태는 `dataset` service의 읽기 함수를 거친다.
"""

from __future__ import annotations

import unicodedata
from typing import Any

from sqlalchemy.orm import Session

from app.dataset import service as dataset_service
from app.formula import repo
from app.formula.functions import REF_NAME
from app.formula.nodes import Call, Text, ast_from_json, walk
from app.reference import service as reference_service

USAGE_LIMIT = 200  # 응답에 담는 데이터셋 수 상한(넘으면 `truncated`)


def _uses_item(ast: Any, name: str) -> bool:
    try:
        root = ast_from_json(ast)
    except ValueError:
        return False  # 깨진 저장 수식은 뷰 점검(D9)이 알린다
    return any(
        isinstance(node, Call)
        and node.name == REF_NAME
        and len(node.args) == 1
        and isinstance(node.args[0], Text)
        and unicodedata.normalize("NFC", node.args[0].value) == name
        for node in walk(root)
    )


def reference_usage(session: Session, item_id: int) -> dict[str, Any]:
    """항목을 쓰는 데이터셋(활성·보관 모두, 이름순, 최대 200개)과 데이터셋별 계산 열 수."""
    item = reference_service.get_item(session, item_id)  # 없으면 404
    columns_by_dataset: dict[int, int] = {}
    for dataset_id, _column_id, ast in repo.reference_candidates(session):
        if _uses_item(ast, item["name"]):
            columns_by_dataset[dataset_id] = columns_by_dataset.get(dataset_id, 0) + 1
    briefs = dataset_service.list_dataset_briefs(session, list(columns_by_dataset))
    session.rollback()
    items = [
        {
            "dataset_id": int(b["id"]),
            "dataset_name": b["name"],
            "team_id": int(b["team_id"]),
            "team_name": b["team_name"],
            "status": b["status"],
            "column_count": columns_by_dataset[int(b["id"])],
        }
        for b in briefs
    ]
    return {
        "items": items[:USAGE_LIMIT],
        "total": len(items),
        "truncated": len(items) > USAGE_LIMIT,
    }
