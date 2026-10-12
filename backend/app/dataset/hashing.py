"""`datasets.def_hash` 자리 값(06 §5): 1d 전에는 **정의 구조 해시**다.

열 번호·종류·형으로 만든 해시이고 표시 이름·필수·규칙·순서는 넣지 않는다(뷰와 무관, 06 §3-4:
표시 이름은 뷰 열이 번호라 해시에 영향 없음). 1d가 뷰 DDL 해시로 바꾸면 이 함수를 대체한다.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

HASH_VERSION = "structure-v1"


def structure_hash(columns: Iterable[Mapping[str, Any]]) -> str:
    """열 목록(`id`, `kind`, `type`)에서 안정적인 sha256 16진 문자열을 만든다."""
    items = sorted((int(c["id"]), str(c["kind"]), str(c["type"])) for c in columns)
    payload = json.dumps([HASH_VERSION, items], separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()
