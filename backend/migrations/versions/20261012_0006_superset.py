"""Superset 등록 정적 표: superset_datasets, superset_dashboards (FU-1e, 06 §2)

- `superset_datasets`: 데이터셋마다 Superset 가상 데이터셋 동기 상태 한 줄(`dataset_id`가 기본키이자
  외래키). `superset_dataset_id`는 등록 전 NULL, `sync_status`는 `pending`/`registered`/`failed`
  (이름 있는 CHECK), `last_error`는 관리자 현황용 사유 요약 글자(SQL·비밀·Superset 응답 본문 금지).
- `superset_dashboards`: 관리자가 수동으로 등록하는 임베드 대시보드(포털 `id` ↔ Superset embedded
  uuid). `embedded_uuid`는 유일하고 소문자 정규형(하이픈 36자)이어야 한다. `uuid` 형은 값을 항상
  소문자 정규형으로 저장하지만, 형식 CHECK를 한 번 더 둔다(입력 검사는 앱이 먼저 한다).
- 제약 이름은 `NAMING_CONVENTION`(app/db_metadata.py)과 같다.
- `bi_app`의 권한은 **명시 GRANT**만이다(06 §2). `superset_datasets`는 SELECT·INSERT와 열 단위
  UPDATE
  (`superset_dataset_id`, `display_name`, `sync_status`, `synced_at`, `last_error`; `dataset_id`는
  불변), `superset_dashboards`는 SELECT·INSERT와 열 단위 UPDATE(`name`, `is_active`; `id`,
  `embedded_uuid`, `created_at`은 불변). 두 표 모두 DELETE·TRUNCATE가 없다(FU-1에는 삭제가 없다).
  `bi_readonly`에는 아무것도 주지 않는다(정적 표는 Superset에 공개하지 않는다).
- 모든 SQL은 보간 없는 고정 문자열이다(D3). `bi_data`의 동적 객체는 건드리지 않는다.

downgrade는 표를 외래키 역순으로 지운다(`DROP TABLE`, 표에 붙은 권한도 함께 사라진다). 이 DROP은
`tests/test_migrations.py`의 `DROP_APPROVED`에 기록된 D2 안전장치 대상이다. 운영 중 문제는
되돌리기가 아니라 수정 revision으로 대응한다(D5).

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "superset_datasets",
        sa.Column("dataset_id", sa.Integer(), nullable=False),
        sa.Column("superset_dataset_id", sa.Integer(), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("sync_status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("dataset_id", name=op.f("pk_superset_datasets")),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_superset_datasets_dataset_id_datasets"),
        ),
        sa.CheckConstraint(
            "sync_status IN ('pending', 'registered', 'failed')",
            name=op.f("ck_superset_datasets_sync_status"),
        ),
    )
    op.create_table(
        "superset_dashboards",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("embedded_uuid", sa.Uuid(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_superset_dashboards")),
        sa.UniqueConstraint("embedded_uuid", name=op.f("uq_superset_dashboards_embedded_uuid")),
        sa.CheckConstraint(
            "embedded_uuid::text ~ "
            "'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'",
            name=op.f("ck_superset_dashboards_embedded_uuid_format"),
        ),
    )

    # 명시 GRANT(06 §2). UPDATE는 열 단위이고 두 표 모두 DELETE가 없다.
    op.execute(
        "GRANT SELECT, INSERT, UPDATE "
        "(superset_dataset_id, display_name, sync_status, synced_at, last_error) "
        "ON superset_datasets TO bi_app"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE (name, is_active) ON superset_dashboards TO bi_app")


def downgrade() -> None:
    # 표를 지우면 인덱스와 권한(ACL)도 함께 사라진다. 두 표는 서로 참조하지 않는다.
    op.drop_table("superset_dashboards")
    op.drop_table("superset_datasets")
