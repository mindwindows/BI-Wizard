"""bi_data schema 권한 부여 (권한 전용 revision)

빈 schema `bi_data`(소유자 `bi_owner`)는 db-bootstrap이 만든다. 이 revision은 객체를 만들지 않고
권한만 부여한다. 전부 `bi_owner`가 실행하는 보간 없는 고정 SQL이다(D3, 역할·schema 이름은 상수).
- `bi_app`(런타임): `bi_data`에 `USAGE, CREATE`. 이후 `bi_app`이 만드는 동적 표·뷰
  (`ds_*`, `dv_*`)의 소유자가 된다.
- `bi_readonly`(Superset): `bi_data`에 `USAGE`, 그리고 `bi_app`이 만드는 표·뷰의 `SELECT`
  (기본 권한). `FOR ROLE bi_app`은 `bi_owner`가 `bi_app`의 상속 멤버
  (`INHERIT TRUE, SET FALSE`, db-bootstrap)일 때만 동작한다.

downgrade는 대응하는 권한을 회수한다. `bi_data` schema 자체와 동적 객체, 멤버십은 건드리지 않는다
(D5 의미 변경: 왕복 테스트는 권한 상태 복원을 검증한다. 03b 3-2, 4-1 Z0, 03c X-29).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-11
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("GRANT USAGE, CREATE ON SCHEMA bi_data TO bi_app")
    op.execute("GRANT USAGE ON SCHEMA bi_data TO bi_readonly")
    op.execute(
        "ALTER DEFAULT PRIVILEGES FOR ROLE bi_app IN SCHEMA bi_data "
        "GRANT SELECT ON TABLES TO bi_readonly"
    )


def downgrade() -> None:
    op.execute(
        "ALTER DEFAULT PRIVILEGES FOR ROLE bi_app IN SCHEMA bi_data "
        "REVOKE SELECT ON TABLES FROM bi_readonly"
    )
    op.execute("REVOKE USAGE ON SCHEMA bi_data FROM bi_readonly")
    op.execute("REVOKE USAGE, CREATE ON SCHEMA bi_data FROM bi_app")
