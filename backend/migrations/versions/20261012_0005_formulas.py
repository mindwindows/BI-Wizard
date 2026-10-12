"""수식 정적 표: formulas, formula_deps (FU-1d, 06 §2)

- `formulas`: 계산 열(`dataset_columns.kind='formula'`) 하나에 수식 하나(`column_id`가 기본키이자
  외래키). `expression`은 보관용 원문이고 화면 표시에는 쓰지 않는다(수식 보기는 `ast`에서
  현재 열 이름으로 만든다). `ast`는 열 번호 참조 JSON, `ast_hash`는 그 정규형의 sha256이다.
  열이 `kind='formula'`인지는 앱이 확인한다(06 §2).
- `formula_deps`: 계산 열이 읽는 열(`SUMTAG`는 펼친 구체 열 목록). 자기 자신을 가리킬 수 없다
  (CHECK). 같은 데이터셋 여부는 앱이 확인한다.
- 제약 이름은 `NAMING_CONVENTION`(app/db_metadata.py)과 같다.
- `bi_app`의 권한은 **명시 GRANT**만이다. `formulas`는 SELECT·INSERT와 열 단위 UPDATE
  (`expression`, `ast`, `ast_hash`; `column_id`는 불변), `formula_deps`는 SELECT·INSERT·DELETE
  (태그나 수식이 바뀌면 의존 목록을 다시 쓴다). `formulas`에는 DELETE가 없다(FU-1에는 삭제가 없다).
  `bi_readonly`에는 아무것도 주지 않는다(정적 표는 Superset에 공개하지 않는다).
- 모든 SQL은 보간 없는 고정 문자열이다(D3). `bi_data`의 동적 객체(`dv_*`, `de_*`)는 건드리지
  않는다. 뷰가 정적 표를 읽지 않아(자기 `ds_*`만 읽는다, 06 §3-4) downgrade가 뷰에 막히지 않는다.

downgrade는 표를 외래키 역순으로 지운다(`DROP TABLE`, 표에 붙은 권한도 함께 사라진다). 이 DROP은
`tests/test_migrations.py`의 `DROP_APPROVED`에 기록된 D2 안전장치 대상이다. 운영 중 문제는
되돌리기가 아니라 수정 revision으로 대응한다(D5).

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "formulas",
        sa.Column("column_id", sa.Integer(), nullable=False),
        sa.Column("expression", sa.Text(), nullable=False),
        sa.Column("ast", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ast_hash", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("column_id", name=op.f("pk_formulas")),
        sa.ForeignKeyConstraint(
            ["column_id"],
            ["dataset_columns.id"],
            name=op.f("fk_formulas_column_id_dataset_columns"),
        ),
    )
    op.create_table(
        "formula_deps",
        sa.Column("column_id", sa.Integer(), nullable=False),
        sa.Column("depends_on_column_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("column_id", "depends_on_column_id", name=op.f("pk_formula_deps")),
        sa.ForeignKeyConstraint(
            ["column_id"],
            ["dataset_columns.id"],
            name=op.f("fk_formula_deps_column_id_dataset_columns"),
        ),
        sa.ForeignKeyConstraint(
            ["depends_on_column_id"],
            ["dataset_columns.id"],
            name=op.f("fk_formula_deps_depends_on_column_id_dataset_columns"),
        ),
        sa.CheckConstraint(
            "column_id <> depends_on_column_id", name=op.f("ck_formula_deps_not_self")
        ),
    )

    # 명시 GRANT(06 §2). UPDATE는 열 단위이고 `formulas`에는 DELETE가 없다.
    op.execute("GRANT SELECT, INSERT, UPDATE (expression, ast, ast_hash) ON formulas TO bi_app")
    op.execute("GRANT SELECT, INSERT, DELETE ON formula_deps TO bi_app")


def downgrade() -> None:
    # 외래키 역순. 표를 지우면 인덱스와 권한(ACL)도 함께 사라진다.
    op.drop_table("formula_deps")
    op.drop_table("formulas")
