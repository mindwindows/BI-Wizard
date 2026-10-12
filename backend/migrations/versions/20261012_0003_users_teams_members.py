"""권한 관리 정적 표: users, teams, team_members (FU-1a, 06 §2)

- `users`: 포털 사용자(`login_id`는 신원 어댑터가 주는 변하지 않는 식별자, 삭제 없이
  비활성화만 한다).
- `teams`: 데이터셋 소유 단위(`code` 불변·형식 제한, `name` 유일).
- `team_members`: 팀 소속과 역할(`definer`/`entry`), 팀마다 사용자당 역할 하나.
- 제약 이름은 `NAMING_CONVENTION`(app/db_metadata.py)과 같다. 열거 값은 이름 있는 CHECK다.
- `bi_app`의 권한은 **명시 GRANT**만이다. 불변 열(`login_id`, `code`, `team_id`, `user_id`)은
  열 단위 UPDATE 권한에서 빼서 DB가 강제한다. 시퀀스 권한은 필요 없다(`GENERATED … AS IDENTITY`).
  `bi_readonly`에는 아무것도 주지 않는다(정적 표는 Superset에 공개하지 않는다).
- 모든 SQL은 보간 없는 고정 문자열이다(D3). 시험용 사용자 시드는 넣지 않는다(03b 5-2 K3).

downgrade는 표를 외래키 역순으로 지운다(`DROP TABLE`, 표에 붙은 권한도 함께 사라진다). 이 DROP은
`tests/test_migrations.py`의 `DROP_APPROVED`에 기록된 D2 안전장치 대상이다. 운영 중 문제는
되돌리기가 아니라 수정 revision으로 대응한다(D5). `bi_data` schema와 동적 객체는 건드리지 않는다.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("login_id", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("is_admin", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("login_id", name=op.f("uq_users_login_id")),
    )
    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teams")),
        sa.UniqueConstraint("code", name=op.f("uq_teams_code")),
        sa.UniqueConstraint("name", name=op.f("uq_teams_name")),
        sa.CheckConstraint("code ~ '^[a-z0-9_]{1,32}$'", name=op.f("ck_teams_code_format")),
    )
    op.create_table(
        "team_members",
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name=op.f("fk_team_members_team_id_teams")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_team_members_user_id_users")
        ),
        sa.PrimaryKeyConstraint("team_id", "user_id", name=op.f("pk_team_members")),
        sa.CheckConstraint("role IN ('definer', 'entry')", name=op.f("ck_team_members_role")),
    )
    op.create_index("ix_team_members_user_id", "team_members", ["user_id"], unique=False)

    # 명시 GRANT(06 §2). 표 단위로는 SELECT/INSERT(와 team_members의 DELETE)만, UPDATE는 열 단위다.
    op.execute(
        "GRANT SELECT, INSERT, UPDATE (display_name, is_admin, is_active) ON users TO bi_app"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE (name, is_active) ON teams TO bi_app")
    op.execute("GRANT SELECT, INSERT, UPDATE (role), DELETE ON team_members TO bi_app")


def downgrade() -> None:
    # 외래키 역순. 표를 지우면 표에 붙은 인덱스와 권한(ACL)도 함께 사라진다.
    op.drop_table("team_members")
    op.drop_table("teams")
    op.drop_table("users")
