"""인증·권한(`auth`): `current_user` 한 곳, 신원 어댑터 인터페이스, 권한 판정 함수.

신원 출처(헤더/토큰/로그인)는 브리프 5절 8번 미결정이라 어댑터는 교체 가능한 인터페이스로만 둔다.
어댑터가 없으면 항상 401(fail-closed)이다. 스텁 어댑터와 `/dev/*`는 FU-1a에서 만든다.
"""

from app.auth.current_user import CurrentUserDep, current_user
from app.auth.identity import Identity, IdentityAdapter, UserReader, UserRecord
from app.auth.models import CurrentUser, Membership, TeamRole

__all__ = [
    "CurrentUser",
    "CurrentUserDep",
    "Identity",
    "IdentityAdapter",
    "Membership",
    "TeamRole",
    "UserReader",
    "UserRecord",
    "current_user",
]
