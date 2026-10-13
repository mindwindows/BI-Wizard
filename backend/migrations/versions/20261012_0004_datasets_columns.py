"""데이터셋·열 정의 정적 표: datasets, dataset_columns (FU-1b, 06 §2)

- `datasets`: 팀 소속 데이터셋 정의. `team_id`는 불변(팀 열이 뷰에 상수로 들어간다)이고
  `def_version`/`def_hash`는 정의 변경 진입점이 쓴다. 팀 안에서 이름이 유일하다.
- `dataset_columns`: 열 정의(원본 `raw`/계산 `formula`). 데이터셋 안에서 표시 이름이 유일하다.
  열 `type`·`kind`의 변경 금지는 앱 규칙이고 DB는 `kind`·`dataset_id`를 불변으로 강제한다.
- `datasets.base_date_column_id`는 같은 데이터셋의 열만 가리키는 복합 FK
  (`id`, `base_date_column_id`) -> `dataset_columns`(`dataset_id`, `id`)로 보장한다. 두 표가 서로
  참조하는 순환 FK라 표를 먼저 만들고 이 FK를 `create_foreign_key`로 뒤에 추가한다.
- 열거 값(`date_unit`, `status`, `type`, `kind`)은 `text` + 이름 있는 CHECK다. 제약 이름은
  `NAMING_CONVENTION`(app/db_metadata.py)과 같다.
- `bi_app`의 권한은 **명시 GRANT**만이다: 표 단위 SELECT·INSERT, UPDATE는 열 단위.
  `datasets.team_id`·`created_by`·`created_at`, `dataset_columns.dataset_id`·`kind`는 UPDATE
  권한에서 빼서 DB가 불변을 강제한다. `dataset_columns.type`은 계산 열 결과 형이 바뀔 때(05 D5)
  갱신해야 하므로 허용하고, 원본 열의 `type` 변경 금지는 앱 규칙과 시험으로 지킨다. DELETE는 없다
  (FU-1에는 삭제가 없다). `bi_readonly`에는 아무것도 주지 않는다(정적 표는 공개하지 않는다).
- 모든 SQL은 보간 없는 고정 문자열이다(D3). `bi_data`의 동적 객체(`ds_*` 등)는 건드리지 않는다.

downgrade는 순환 FK를 먼저 끊고 표를 외래키 역순으로 지운다(표에 붙은 권한도 함께 사라진다). 이
DROP은 `tests/test_migrations.py`의 `DROP_APPROVED`에 기록된 D2 안전장치 대상이다. 운영 중 문제는
되돌리기가 아니라 수정 revision으로 대응한다(D5). `bi_data` schema와 동적 객체는 건드리지 않으므로
downgrade 뒤에도 `ds_*` 표는 남는다(왕복 시험의 복원 대상은 정적 표와 권한 상태다).

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("date_unit", sa.Text(), nullable=False),
        sa.Column("base_date_column_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'active'"), nullable=False),
        sa.Column("def_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("def_hash", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_datasets")),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], name=op.f("fk_datasets_team_id_teams")),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_datasets_created_by_users")
        ),
        sa.UniqueConstraint("team_id", "name", name=op.f("uq_datasets_team_id_name")),
        sa.CheckConstraint(
            "date_unit IN ('day', 'month', 'year')", name=op.f("ck_datasets_date_unit")
        ),
        sa.CheckConstraint("status IN ('active')", name=op.f("ck_datasets_status")),
    )
    op.create_table(
        "dataset_columns",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("dataset_id", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("required", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("rules", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tag", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset_columns")),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["datasets.id"], name=op.f("fk_dataset_columns_dataset_id_datasets")
        ),
        sa.UniqueConstraint("dataset_id", "id", name=op.f("uq_dataset_columns_dataset_id_id")),
        sa.UniqueConstraint(
            "dataset_id", "display_name", name=op.f("uq_dataset_columns_dataset_id_display_name")
        ),
        sa.CheckConstraint(
            "type IN ('text', 'number', 'date', 'boolean', 'choice')",
            name=op.f("ck_dataset_columns_type"),
        ),
        sa.CheckConstraint("kind IN ('raw', 'formula')", name=op.f("ck_dataset_columns_kind")),
        sa.CheckConstraint(
            "kind = 'raw' OR (NOT required AND type <> 'choice')",
            name=op.f("ck_dataset_columns_formula_shape"),
        ),
    )
    # 순환 FK: 기준 날짜 열은 같은 데이터셋의 열이어야 한다(NULL이면 검사하지 않는다).
    op.create_foreign_key(
        "fk_datasets_id_dataset_columns",
        "datasets",
        "dataset_columns",
        ["id", "base_date_column_id"],
        ["dataset_id", "id"],
    )

    # 명시 GRANT(06 §2). 표 단위로는 SELECT/INSERT만, UPDATE는 열 단위다. DELETE 없음.
    op.execute(
        "GRANT SELECT, INSERT, "
        "UPDATE (name, date_unit, base_date_column_id, status, def_version, def_hash) "
        "ON datasets TO bi_app"
    )
    op.execute(
        "GRANT SELECT, INSERT, "
        "UPDATE (display_name, type, required, rules, tag, position) "
        "ON dataset_columns TO bi_app"
    )


def downgrade() -> None:
    # 순환 FK를 먼저 끊고 외래키 역순으로 지운다. 표를 지우면 인덱스와 권한(ACL)도 함께 사라진다.
    op.drop_constraint("fk_datasets_id_dataset_columns", "datasets", type_="foreignkey")
    op.drop_table("dataset_columns")
    op.drop_table("datasets")
