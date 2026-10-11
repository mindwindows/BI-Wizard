"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, Sequence[str], None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    # 규칙: SQL은 보간 없는 고정 문자열만 쓴다(f-string, %, .format(), + 금지).
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    # 규칙: 모든 revision에 downgrade를 구현한다. DROP이 있으면 사용자 확인 기록이 필요하다.
    ${downgrades if downgrades else "pass"}
