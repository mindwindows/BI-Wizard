"""이름순 정렬(한글 가나다순, 03b 19-1 결정 2).

DB 기본 정렬(`en_US.utf8`)은 한글을 가나다순으로 정렬하지 못한다. PostgreSQL의 ICU collation
`ko-KR-x-icu`를 이름 열의 `ORDER BY`에만 붙인다
(표·열의 저장 collation은 바꾸지 않는다: 마이그레이션 없음).

- 표현식은 SQLAlchemy 구성요소다(`text()`·SQL 문자열 조립 없음). PostgreSQL이 아닌 방언
  (SQLite 시험)에서는 COLLATE를 붙이지 않는다. 그 변형은 정렬 순서를 단정하지 않는다.
- collation이 DB에 없으면 시작 자가 점검이 경고를 남기고 `set_collation_available(False)`를 부른다.
  이후 질의는 COLLATE 없이 DB 기본 순서로 정렬한다(목록이 500이 되는 대신 한글 순서가 어긋난다).
  시작을 거부하지 않는 이유: 이름순은 편의 기능이고 데이터 정합성과 무관하다.
- 한계: ICU는 숫자를 글자 순서로 비교한다(`10`이 `9`보다 앞). 라틴과 한글이 섞인 이름은
  한글이 라틴보다 앞선다.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.expression import ColumnClause

KOREAN_COLLATION = "ko-KR-x-icu"

_state = {"available": True}


def set_collation_available(available: bool) -> None:
    _state["available"] = available


def collation_available() -> bool:
    return _state["available"]


class NameOrder(ColumnElement[Any]):
    """이름 열을 한국어 collation으로 정렬하는 `ORDER BY` 키."""

    inherit_cache = True

    def __init__(self, element: ColumnClause[Any] | ColumnElement[Any]) -> None:
        self.element = element
        self.type = element.type

    @property
    def _from_objects(self) -> list[Any]:  # type: ignore[override]
        return self.element._from_objects


@compiles(NameOrder)
def _compile_name_order(element: NameOrder, compiler: Any, **kw: Any) -> str:
    inner = compiler.process(element.element, **kw)
    if compiler.dialect.name == "postgresql" and collation_available():
        return f'{inner} COLLATE "{KOREAN_COLLATION}"'
    return str(inner)


def by_name(column: ColumnElement[Any]) -> NameOrder:
    return NameOrder(column)
