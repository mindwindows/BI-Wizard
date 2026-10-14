"""타입 있는 리터럴 렌더러 접점 **한 곳**(07 §4-1, 03b 5-2 Z6 (가)).

수식의 모든 상수(수식 속 숫자·글자·참거짓, 사전 내부의 10·1 같은 상수, 빈 값, 오류 코드)는 이 파일의
`Literals`를 거쳐 SQLAlchemy 표현식이 된다. 사전과 변환기는 `literal()`·`bindparam()`·`text()`를
직접
부르지 않는다(시험이 코드를 검사한다).

두 가지 실행 방식을 같은 표현식으로 지원한다.
- **미리보기**: 표현식을 그대로 `execute`한다. 상수는 바인드 파라미터로 서버에 간다.
- **뷰**: `render_literal_sql`이 같은 표현식을 `literal_binds`로 SQL 글자로 렌더한다(해시
  계산·시험용).
  `CreateView`도 같은 방식으로 렌더하므로 `ddl` 쪽 뷰 생성은 이 표현식을 그대로 넘기면 된다.
  `literal_binds`는 일반 코드에서 금지이며 **이 파일의 `render_literal_sql` 한 곳만** 예외다
  (`tests/test_ddl.py`의 정적 검사가 이 예외를 정확히 한 곳으로 고정한다).

모든 상수는 `CAST(… AS 형)`으로 감싼다(바인드와 리터럴의 DB 형 추론 차이 제거: X-26.3, 346건 중
98건 차이). 숫자는 `Decimal`로만 받아 `CAST(… AS NUMERIC)`(정수도 `Decimal`: `10**30`의 BIGINT 범위
오류 제거), 형 없는 `NULL`은 만들 수 없다(`null(형)`만 있다).

거부(1차 방어, 07 §4-2·§4-3 ②): 유한하지 않은 수(`NaN`·`Infinity`), 38자리 초과, 글자 상수의
NUL·서로게이트·
역슬래시·제어문자(Cc)·서식 문자(Cf)·줄/문단 구분(Zl·Zp), 200자 초과. 글자는 NFC로 정규화한 뒤
검사한다.
`render_literal_sql`은 렌더 직전에 문장 안의 **모든 바인드 값**을 다시 검사하고 이 파일이 만들지
않은
바인드가 있으면 거부한다(표현식 어디에서 오든 렌더되는 상수는 이 규칙을 지난다).
"""

from __future__ import annotations

import datetime
import unicodedata
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import pg8000
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.sql import ClauseElement
from sqlalchemy.sql.elements import ColumnElement

from app.formula.errors import CELL_ERROR_NUMBERS

MAX_TEXT_CONSTANT_LENGTH = 200  # 07 §4-2 [제안]
MAX_NUMBER_DIGITS = 38  # 07 §4-1
_BIND_PREFIX = "lit"

NUMBER = "number"
TEXT = "text"
BOOLEAN = "boolean"
DATE = "date"
SMALLINT = "smallint"
INTEGER = "integer"

_SQL_TYPES: dict[str, type[sa.types.TypeEngine]] = {
    NUMBER: sa.Numeric,
    TEXT: sa.Text,
    BOOLEAN: sa.Boolean,
    DATE: sa.Date,
    SMALLINT: sa.SmallInteger,
    INTEGER: sa.Integer,
}

# 서식 문자(Cf)·줄/문단 구분(Zl·Zp)·제어(Cc)·서로게이트(Cs)는 거부한다(07 §4-2).
_REJECTED_CATEGORIES = {
    "Cc": "제어 문자(줄바꿈·탭 포함)",
    "Cf": "눈에 보이지 않는 서식 문자",
    "Cs": "잘못된 문자",
    "Zl": "줄 구분 문자",
    "Zp": "문단 구분 문자",
}


class LiteralError(ValueError):
    """리터럴로 만들 수 없는 값.

    메시지는 사용자에게 보일 수 있는 짧은 한국어이며 값은 넣지 않는다.
    """


def normalize_text_constant(value: str) -> str:
    """글자 상수를 NFC로 정규화한다(NFD와 NFC는 DB에서 `=`이 거짓: X-26.4)."""
    return unicodedata.normalize("NFC", value)


def text_constant_problem(value: str) -> str | None:
    """글자 상수를 쓸 수 없는 이유(없으면 None). `value`는 NFC로 정규화된 값이어야 한다."""
    if len(value) > MAX_TEXT_CONSTANT_LENGTH:
        return f"{MAX_TEXT_CONSTANT_LENGTH}자를 넘습니다."
    if "\\" in value:
        return "역슬래시(\\)는 쓸 수 없습니다."
    for char in value:
        if char == "\x00":
            return "NUL 문자는 쓸 수 없습니다."
        reason = _REJECTED_CATEGORIES.get(unicodedata.category(char))
        if reason is not None:
            return f"{reason}는 쓸 수 없습니다."
    return None


def number_problem(value: Decimal) -> str | None:
    """숫자 상수를 쓸 수 없는 이유(없으면 None)."""
    if not value.is_finite():
        return "유한한 숫자만 쓸 수 있습니다."
    _sign, digits, exponent = value.as_tuple()
    assert isinstance(exponent, int)  # noqa: S101 - 유한한 수라 정수다
    if len(digits) > MAX_NUMBER_DIGITS or exponent < -MAX_NUMBER_DIGITS:
        return f"{MAX_NUMBER_DIGITS}자리를 넘습니다."
    if exponent > 0 and len(digits) + exponent > MAX_NUMBER_DIGITS:
        return f"{MAX_NUMBER_DIGITS}자리를 넘습니다."
    return None


def _check_bound_value(value: Any, type_: sa.types.TypeEngine) -> None:
    """바인드 값 하나가 허용된 상수인지 확인한다(`Literals`가 만든 값만 통과한다)."""
    if isinstance(type_, sa.Boolean):
        if not isinstance(value, bool):
            raise LiteralError("참거짓 상수가 아닙니다.")
    elif isinstance(type_, sa.Numeric):
        if not isinstance(value, Decimal):
            raise LiteralError("숫자 상수는 Decimal이어야 합니다.")
        problem = number_problem(value)
        if problem:
            raise LiteralError(problem)
    elif isinstance(type_, sa.Text):
        if not isinstance(value, str):
            raise LiteralError("글자 상수가 아닙니다.")
        if value != normalize_text_constant(value):
            raise LiteralError("글자 상수는 NFC로 정규화되어야 합니다.")
        problem = text_constant_problem(value)
        if problem:
            raise LiteralError(problem)
    elif isinstance(type_, sa.Date):
        if type(value) is not datetime.date:
            raise LiteralError("날짜 상수가 아닙니다.")
    elif isinstance(type_, sa.SmallInteger | sa.Integer):
        if isinstance(value, bool) or not isinstance(value, int):
            raise LiteralError("정수 상수가 아닙니다.")
        limit = 2**15 if isinstance(type_, sa.SmallInteger) else 2**31
        if not -limit <= value < limit:
            raise LiteralError("정수 상수가 범위를 벗어났습니다.")
    else:
        raise LiteralError("허용되지 않은 상수 형입니다.")


class Literals:
    """수식 상수를 표현식으로 만드는 유일한 길. 상태가 없으므로 한 객체를 공유해도 된다."""

    @staticmethod
    def _cast(value: Any, kind: str) -> ColumnElement[Any]:
        type_ = _SQL_TYPES[kind]()
        _check_bound_value(value, type_)
        return sa.cast(sa.bindparam(_BIND_PREFIX, value, type_=type_, unique=True), type_)

    def number(self, value: Decimal | int) -> ColumnElement[Any]:
        """`CAST(… AS NUMERIC)`. 정수도 `Decimal`로 바꿔 만든다(`bool`은 거부)."""
        if isinstance(value, bool) or not isinstance(value, Decimal | int):
            raise LiteralError("숫자 상수는 Decimal이나 정수여야 합니다.")
        return self._cast(Decimal(value), NUMBER)

    def integer(self, value: int) -> ColumnElement[Any]:
        """`CAST(… AS INTEGER)`(함수가 정수 인수를 요구할 때)."""
        return self._cast(value, INTEGER)

    def reference_id(self, value: int) -> ColumnElement[Any]:
        """기준값 항목 번호 전용 정수 상수(07 §4-1): `CAST(… AS INTEGER)`, 1 이상 INTEGER 범위.

        `item_id`(integer)와 `NUMERIC` 상수를 비교하면 열에 캐스트가 걸려 인덱스를 못 쓴다.
        `bool`·0·음수·범위 밖은 `LiteralError`다.
        """
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise LiteralError("기준값 항목 번호는 1 이상의 정수여야 합니다.")
        return self._cast(value, INTEGER)

    def smallint(self, value: int) -> ColumnElement[Any]:
        """`CAST(… AS SMALLINT)`."""
        return self._cast(value, SMALLINT)

    def text(self, value: str) -> ColumnElement[Any]:
        """`CAST('…' AS TEXT)`. NFC가 아니거나 규칙 위반이면 `LiteralError`."""
        if not isinstance(value, str):
            raise LiteralError("글자 상수가 아닙니다.")
        return self._cast(value, TEXT)

    def boolean(self, value: bool) -> ColumnElement[Any]:
        """`CAST(true AS BOOLEAN)`."""
        return self._cast(value, BOOLEAN)

    def date(self, value: datetime.date) -> ColumnElement[Any]:
        """`CAST('YYYY-MM-DD' AS DATE)`."""
        return self._cast(value, DATE)

    def null(self, kind: str) -> ColumnElement[Any]:
        """`CAST(NULL AS 형)`. 형 없는 NULL은 만들지 않는다(바인드 `42P18`, X-26.3)."""
        if kind not in _SQL_TYPES:
            raise LiteralError("알 수 없는 형입니다.")
        return sa.cast(sa.null(), _SQL_TYPES[kind]())

    def code(self, cell_error: str) -> ColumnElement[Any]:
        """셀 오류 코드(`E1`~)를 `de_` 뷰의 smallint 값으로."""
        return self.smallint(CELL_ERROR_NUMBERS[cell_error])


LITERALS = Literals()


def render_literal_sql(statement: ClauseElement, dialect: Dialect | None = None) -> str:
    """표현식을 상수가 글자로 들어간 SQL 문자열로 렌더한다(뷰 해시·시험 전용, 실행용이 아니다).

    렌더 전에 문장 안의 모든 바인드 값을 검사한다. `Literals`가 만들지 않은 바인드(이름이 `lit`로
    시작하지 않는 것)나 규칙을 어긴 값이 있으면 `LiteralError`. 기본 방언은 운영과 같은 pg8000이다.
    """
    dialect = dialect or pg8000.dialect()
    bound = statement.compile(dialect=dialect)
    for name, bind in bound.binds.items():
        if not name.startswith(f"{_BIND_PREFIX}_"):
            # 컴파일러가 만드는 위치 표시용 이름은 건너뛰고 실제 값을 가진 이름만 본다.
            if name in bound.params:
                raise LiteralError("허용되지 않은 방식으로 만든 상수가 있습니다.")
            continue
        _check_bound_value(bound.params[name], bind.type)
    # 이 줄이 코드 전체에서 `literal_binds`를 쓰는 유일한 곳이다.
    return str(statement.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))
