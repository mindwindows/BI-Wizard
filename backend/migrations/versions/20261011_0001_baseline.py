"""baseline: 업무 테이블이 없는 기준 revision

Gate ②의 기준(baseline) revision이다. 의도적으로 스키마 객체를 만들지 않는다.
- upgrade: Alembic이 `alembic_version` 표를 만들고 이 revision을 기록한다.
- downgrade: Alembic이 기록을 지운다(base).
왕복 테스트(upgrade -> downgrade -> upgrade)의 출발점이다.
업무 테이블, 동적 객체(데이터셋 테이블, 수식 뷰), 읽기 전용 계정 권한은 Gate ③ 이후
별도 revision에서 다룬다(D2는 Gate ③에서 결정).

Revision ID: 0001
Revises:
Create Date: 2026-10-11
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 만들 객체가 없다. 버전 기록은 Alembic이 한다.
    return None


def downgrade() -> None:
    # 되돌릴 객체가 없다. 버전 기록 삭제는 Alembic이 한다.
    return None
