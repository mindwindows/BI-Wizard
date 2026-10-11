"""static tables + grants (X-29 실험용)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-11
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table("teams",
                    sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
                    sa.Column("name", sa.Text(), nullable=False),
                    sa.PrimaryKeyConstraint("id"))
    op.create_table("datasets",
                    sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
                    sa.Column("team_id", sa.Integer(), nullable=False),
                    sa.Column("display_name", sa.Text(), nullable=False),
                    sa.Column("def_version", sa.Integer(), server_default="1", nullable=False),
                    sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
                    sa.PrimaryKeyConstraint("id"))
    op.create_table("dataset_columns",
                    sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
                    sa.Column("dataset_id", sa.Integer(), nullable=False),
                    sa.Column("internal_name", sa.Text(), nullable=False),
                    sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"]),
                    sa.PrimaryKeyConstraint("id"))
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.teams, public.datasets, public.dataset_columns TO bi_app")
    op.execute("GRANT USAGE, CREATE ON SCHEMA bi_data TO bi_app")
    op.execute("GRANT USAGE ON SCHEMA bi_data TO bi_readonly")
    op.execute("ALTER DEFAULT PRIVILEGES FOR ROLE bi_app IN SCHEMA bi_data GRANT SELECT ON TABLES TO bi_readonly")


def downgrade() -> None:
    op.execute("ALTER DEFAULT PRIVILEGES FOR ROLE bi_app IN SCHEMA bi_data REVOKE SELECT ON TABLES FROM bi_readonly")
    op.execute("REVOKE USAGE ON SCHEMA bi_data FROM bi_readonly")
    op.execute("REVOKE USAGE, CREATE ON SCHEMA bi_data FROM bi_app")
    op.drop_table("dataset_columns")
    op.drop_table("datasets")
    op.drop_table("teams")
