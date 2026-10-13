"""수식 엔진의 오류 형식과 쉬운 한국어 문구 사전(07 §2-2·§3, 05 D2·§3).

- 수식 검사(C0) 오류: `FormulaIssue(code, message, start, end)`. 위치는 **원문 수식의
  글자(코드포인트)
  번호**이며 `start` 포함, `end` 미포함이다(JavaScript의 UTF-16 번호와는 이모지 같은 보충 평면
  문자에서
  다르다. 화면이 변환한다). 문구에는 SQL 용어를 쓰지 않는다.
- 셀 오류 코드 `E1`~`E3`: 오류 칸의 코드다(API 오류가 아니다). 뷰 `de_<번호>`의
  `e_<열>`(smallint)에는
  숫자 1~3으로 저장한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# --- 셀 오류 코드(07 §2-2) ----
CELL_ERROR_MESSAGES_KO: dict[str, str] = {
    "E1": "0으로 나눌 수 없어 계산하지 못했습니다.",
    "E2": "글자를 자르는 길이(0~10000)가 범위를 벗어났습니다.",
    "E3": "날짜가 범위(0001-01-01~9999-12-31)를 벗어났습니다.",
}
CELL_ERROR_NUMBERS: dict[str, int] = {code: int(code[1:]) for code in CELL_ERROR_MESSAGES_KO}
CELL_ERROR_BY_NUMBER: dict[int, str] = {number: code for code, number in CELL_ERROR_NUMBERS.items()}

# --- 수식 검사 오류 문구(메시지 사전, `message_ko`) ----
# 값 자리는 `str.format`으로 채운다. 사용자 입력(열 이름 등)은 값으로만 들어간다.
MESSAGES_KO: dict[str, str] = {
    "EMPTY": "수식이 비어 있습니다.",
    "TOO_LONG": "수식이 너무 깁니다. {max}자 이하로 줄여 주세요(지금 {length}자).",
    "TOO_DEEP": "괄호나 함수가 너무 깊게 겹쳐 있습니다(최대 {max}단계). "
    "항이 많은 덧셈은 SUM(…)으로 쓰고, 긴 계산은 여러 열로 나눠 주세요.",
    "BAD_CHARACTER": "사용할 수 없는 문자 {char}입니다. 공백으로 보이는 특수 문자이거나 "
    "열 이름을 대괄호로 감싸지 않았는지 확인하세요.",
    "UNCLOSED_STRING": '글자를 감싼 큰따옴표(")가 닫히지 않았습니다.',
    "UNCLOSED_COLUMN": "열 이름의 닫는 대괄호 ]가 빠졌습니다.",
    "STRAY_BRACKET": "짝이 없는 ]입니다.",
    "EMPTY_COLUMN_NAME": "열 이름이 비어 있습니다. [열 이름]처럼 이름을 써 주세요.",
    "COLUMN_NAME_INVALID": "열 이름에 줄바꿈 같은 제어 문자를 쓸 수 없습니다.",
    "LEADING_EQUALS": "수식 앞에 =를 쓰지 않습니다. 바로 계산식을 적어 주세요.",
    "NOT_EQUALS_SYNTAX": "같지 않음은 !=가 아니라 <>로 씁니다.",
    "UNEXPECTED_END": "수식이 끝났지만 아직 완성되지 않았습니다. "
    "닫는 괄호 )나 빠진 값이 있는지 확인하세요.",
    "UNEXPECTED_TOKEN": "여기에는 {token}을(를) 쓸 수 없습니다. {hint}",
    "BARE_NAME": "'{name}'은(는) 함수 이름처럼 보이지만 여는 괄호 (가 없습니다. "
    "열을 쓰려면 [{name}]처럼 대괄호로 감싸세요.",
    "UNKNOWN_COLUMN": "'{name}' 열을 찾을 수 없습니다.{suggest}",
    "UNKNOWN_FUNCTION": "'{name}' 함수는 없습니다.{suggest}",
    "COLUMN_TYPE_UNSUPPORTED": "'{name}' 열의 종류를 수식에서 쓸 수 없습니다.",
    "ARG_COUNT": "{name}에는 값이 {expected} 필요한데 {actual}개가 들어 있습니다.",
    "ARG_TYPE": "{name}의 {position}번째 값은 {expected}이어야 하는데 {actual}입니다.{hint}",
    "TYPE_MISMATCH": "{name}에 쓴 값들은 같은 종류여야 하는데 {types}이(가) 섞여 있습니다.{hint}",
    "CONST_REQUIRED": "{name}의 {position}번째 값은 계산식이나 열이 아니라 "
    "직접 쓴 {kind}이어야 합니다.",
    "CONST_RANGE": "{name}의 {position}번째 값은 {range}이어야 합니다.",
    "TEXT_CONSTANT_INVALID": "글자 상수에 쓸 수 없는 내용이 있습니다: {reason}",
    "NUMBER_INVALID": "숫자는 38자리 이하로 쓰고 소수점 아래는 38자리까지 쓸 수 있습니다.",
    "TAG_EMPTY": "'{tag}' 태그가 붙은 숫자 열이 없습니다.",
    "REF_FORMULA_INVALID": "'{name}' 열의 수식에 문제가 있어 이 수식에서 쓸 수 없습니다.",
    "REF_MISSING": "참조한 열(번호 {column_id})을 찾을 수 없습니다.",
    "CIRCULAR": "열이 서로를 참조해 계산할 수 없습니다: {path}",
    "CHAIN_TOO_LONG": "다른 계산 열을 따라가는 단계가 너무 깁니다(최대 {max}단계).",
    "TOO_MANY_NODES": "계산이 너무 복잡합니다. 참조한 계산 열을 펼치면 "
    "{max}개를 넘습니다(지금 {count}개).",
    "TOO_COMPLEX": "계산이 너무 복잡해 처리할 수 없습니다. 수식을 나눠 여러 열로 계산해 주세요.",
    "CONSTANT_ERROR": "이 계산은 항상 오류가 됩니다({reason}). 값을 확인하세요.",
    "CONSTANT_PROBE_FAILED": "이 계산은 상수만으로 이루어져 있는데 계산할 수 없습니다.",
}

# 상수 부분식 오류의 이유 문구(셀 오류 코드별).
CONSTANT_ERROR_REASONS_KO: dict[str, str] = {
    "E1": "0으로 나눔",
    "E2": "글자 길이가 범위를 벗어남",
    "E3": "날짜가 범위를 벗어남",
}


@dataclass(frozen=True)
class FormulaIssue:
    """수식 검사 오류 한 건. 05 D2의 `errors[]` 한 원소와 같은 모양(`as_dict`)."""

    code: str
    message: str
    start: int
    end: int
    path: tuple[str, ...] = ()  # CIRCULAR일 때 열 이름 경로

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "start": self.start, "end": self.end}


class FormulaError(Exception):
    """수식 처리 중단 오류. 한 건 이상의 `FormulaIssue`를 담는다."""

    def __init__(self, *issues: FormulaIssue) -> None:
        super().__init__(issues[0].message if issues else "수식 오류")
        self.issues: tuple[FormulaIssue, ...] = tuple(issues)


def make_issue(code: str, start: int, end: int, **values: Any) -> FormulaIssue:
    """코드와 값으로 쉬운 말 문구를 만든다."""
    template = MESSAGES_KO[code]
    path = tuple(values.get("path_names", ()))
    if "path_names" in values:
        values = {**values, "path": " → ".join(path)}
    message = template.format(**{k: v for k, v in values.items() if k != "path_names"})
    return FormulaIssue(code=code, message=message, start=start, end=end, path=path)
