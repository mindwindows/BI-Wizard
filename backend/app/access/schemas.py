"""요청·응답 모양(05 §2-1 A1~A9, 05 §1 목록 규칙). 계약에 없는 필드는 만들지 않는다."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
)

from app.core.text import has_control_chars, normalize_text
from app.db_metadata import TEAM_CODE_PATTERN

# 표시 이름 길이 상한(05 §1, 03b 17-1 결정 4): 팀 50자, 사용자 표시 이름 100자, 로그인 ID 200자.
TEAM_NAME_MAX = 50
USER_DISPLAY_NAME_MAX = 100
LOGIN_ID_MAX = 200

_TEAM_CODE = re.compile(TEAM_CODE_PATTERN)


def _reject_control_chars(value: str) -> str:
    if has_control_chars(value):
        raise ValueError("제어문자는 쓸 수 없다")
    return value


def _team_code(value: str) -> str:
    # 파이썬 `$`는 끝의 개행을 허용하므로 fullmatch로 판정한다(DB의 CHECK와 같은 결과).
    if _TEAM_CODE.fullmatch(value) is None:
        raise ValueError("형식이 올바르지 않다")
    return value


# 앞뒤 공백을 지우고 NFC로 정규화한 뒤 길이·제어문자를 검사한다(05 §1).
TeamName = Annotated[
    str,
    BeforeValidator(normalize_text),
    Field(min_length=1, max_length=TEAM_NAME_MAX),
    AfterValidator(_reject_control_chars),
]
UserDisplayName = Annotated[
    str,
    BeforeValidator(normalize_text),
    Field(min_length=1, max_length=USER_DISPLAY_NAME_MAX),
    AfterValidator(_reject_control_chars),
]
# 로그인 ID는 신원 어댑터가 주는 식별자라 정규화·대소문자 변환·공백 제거를 하지 않는다.
LoginId = Annotated[
    str,
    Field(min_length=1, max_length=LOGIN_ID_MAX),
    AfterValidator(_reject_control_chars),
]
TeamCode = Annotated[str, Field(min_length=1, max_length=32), AfterValidator(_team_code)]
Role = Literal["definer", "entry"]


class Strict(BaseModel):
    """요청 본문 기반 모델: 알 수 없는 필드(예: 불변 `code`)는 422로 거부한다."""

    model_config = ConfigDict(extra="forbid")


class TeamCreate(Strict):
    code: TeamCode
    name: TeamName


class TeamUpdate(Strict):
    # 보낸 필드만 바꾼다(`model_fields_set`). null은 허용하지 않는다.
    name: TeamName = ""
    is_active: StrictBool = True


class UserCreate(Strict):
    login_id: LoginId
    display_name: UserDisplayName
    is_admin: StrictBool = False


class UserUpdate(Strict):
    display_name: UserDisplayName = ""
    is_admin: StrictBool = False
    is_active: StrictBool = True


class MemberRoleIn(Strict):
    role: Role


class MembershipMe(BaseModel):
    team_id: int
    team_code: str
    team_name: str
    team_is_active: bool
    role: Role


class MeOut(BaseModel):
    id: int
    display_name: str
    is_active: bool
    is_admin: bool
    memberships: list[MembershipMe]


class TeamOut(BaseModel):
    id: int
    code: str
    name: str
    is_active: bool


class MembershipOut(BaseModel):
    team_id: int
    role: Role


class UserOut(BaseModel):
    id: int
    login_id: str
    display_name: str
    is_admin: bool
    is_active: bool
    memberships: list[MembershipOut]


class MemberOut(BaseModel):
    team_id: int
    user_id: int
    role: Role
