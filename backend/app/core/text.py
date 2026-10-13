"""사용자 입력 글자 정리(05 §1): NFC 정규화, 앞뒤 공백 제거, 제어문자 거부."""

from __future__ import annotations

import unicodedata
from typing import Any


def normalize_text(value: Any) -> Any:
    """문자열이면 NFC 정규화와 앞뒤 공백 제거를 한다. 문자열이 아니면 그대로 둔다(검증이 거부)."""
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value).strip()
    return value


def has_control_chars(value: str) -> bool:
    """개행·탭 등 제어문자(범주 C*: Cc, Cf, Cs, Co, Cn)가 있으면 True."""
    return any(unicodedata.category(ch).startswith("C") for ch in value)
