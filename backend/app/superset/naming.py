"""Superset에 등록하는 이름·SQL 규칙(08 §2). 규칙은 이 파일 한 곳에만 둔다."""

from __future__ import annotations

import re

from app.ddl.names import view_name
from app.superset.constants import SCHEMA

# 가상 데이터셋 SQL 고정 템플릿(AP-2): 이 모양 하나뿐이다. `tests/test_superset_units.py`가
# 정규식으로 고정하고, 등록은 서비스 계정만 한다.
VIRTUAL_SQL_PATTERN = re.compile(r"SELECT \* FROM bi_data\.dv_[1-9][0-9]*")

# 데이터셋 번호 외의 열(06 §7): 팀 열과 행 번호 열의 표시 이름.
TEAM_COLUMN = "team"
ROW_ID_COLUMN = "row_id"
TEAM_COLUMN_LABEL = "팀"
ROW_ID_COLUMN_LABEL = "행 번호"

# Superset 열 표시 이름 상한(1,024자를 넘으면 원인 없는 422, 03c A-27). 앱 상한(100자)이 먼저 막지만
# 안전망으로 한 번 더 자른다.
VERBOSE_NAME_MAX = 1024

_USER_COLUMN = re.compile(r"c_([0-9]+)")


def virtual_sql(dataset_id: int) -> str:
    """가상 데이터셋 SQL. 숫자는 `ddl.names.view_name`이 검증한다(사용자 글자는 들어가지 않는다)."""
    # 고정 템플릿 하나(AP-2): Superset에 등록할 가상 데이터셋의 글자일 뿐
    # 우리가 실행하는 SQL이 아니다.
    return f"SELECT * FROM {SCHEMA}.{view_name(dataset_id)}"  # noqa: S608


def superset_name(team_name: str, dataset_name: str) -> str:
    """가상 데이터셋 이름: `[<팀 표시 이름>] <데이터셋 표시 이름>`(03b 3-3 Y6)."""
    return f"[{team_name}] {dataset_name}"


def column_label(column_name: str, display_names: dict[int, str]) -> tuple[bool, str | None]:
    """Superset 열 이름 -> (우리가 정한 표시 이름이 있는가, 표시 이름).

    `c_<번호>`는 해당 열의 표시 이름, `team`은 "팀", `row_id`는 "행 번호"다. 그 밖의 열(또는 정의에
    없는 번호)은 (False, None)이라 호출한 쪽이 Superset의 기존 값을 그대로 유지한다.
    """
    if column_name == TEAM_COLUMN:
        return True, TEAM_COLUMN_LABEL
    if column_name == ROW_ID_COLUMN:
        return True, ROW_ID_COLUMN_LABEL
    match = _USER_COLUMN.fullmatch(column_name)
    if match is not None:
        label = display_names.get(int(match.group(1)))
        if label is not None:
            return True, label[:VERBOSE_NAME_MAX]
    return False, None
