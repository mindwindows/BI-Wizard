"""기준값 정적 표 두 개와 감사 CHECK 두 개 교체 (FU-3, 06 §2-2·§6)

`reference_items`, `reference_values`.

- `reference_items`: 전역 기준값 항목(이름 유일·불변, 설명 NULL 허용). `name`은 1~50자
  (`ck_reference_items_name_length`, 빈 이름 방지 안전망). 삭제·이름 변경은 없다.
- `reference_values`: 항목마다 연도별 숫자 값 하나. `UNIQUE(item_id, year)`
  (`uq_reference_values_item_id_year`), `year`는 1900~9999(`ck_reference_values_year`), 값은 유한
  (`ck_reference_values_finite`: PostgreSQL에서 NaN은 모든 수보다 크게 비교되므로 NaN·±Infinity를
  함께 거른다). 추가 인덱스는 없다(UNIQUE 인덱스가 행별 조회와 FK 검사를 맡는다).
- `bi_app` 권한은 **명시 GRANT 4줄**이다: 두 표의 SELECT·INSERT, UPDATE는 열 단위(`reference_items`
  의 `description`, `reference_values`의 `number_value`만). DELETE·TRUNCATE·REFERENCES·TRIGGER도
  시퀀스 권한도 없다(identity라 INSERT 권한으로 번호가 붙는다, 0007 선례).
  **`bi_readonly`·PUBLIC에는
  직접 권한을 주지 않는다**: 값은 `dv_` 뷰(소유자 `bi_app`의 권한으로 평가) 경유로만 보인다
  (06 §3-4). 두 표는 `public`(정적 표)이며 `bi_data`에 두지 않는다.
- `ck_audit_log_action`(17 -> 20개: `reference.create`, `reference_value.add`,
  `reference_value.update`)과 `ck_audit_log_target_type`(4 -> 5개: `reference`)을
  `drop_constraint` ->
  `create_check_constraint`로 교체한다. 제약 이름은 반드시 `op.f(...)`로 쓴다(이름 규칙이
  이름을 한 번
  더 붙이지 않게, 0004·0007·0008과 같은 방식).
- `bi_data`·`datasets`·기존 표의 열·권한 변경은 없다. 모든 SQL은 보간 없는 고정 문자열이다(D3).

downgrade는 **사전 점검**을 먼저 한다. 하나라도 해당하면 한국어 메시지로 거부하고 아무것도 바꾸지
않는다: ① `bi_data`의 뷰가 `public.reference_values`를 읽는다(`pg_depend`의 의존 기록으로 판정한다.
뷰 정의 글자 검색은 schema 표기·검색 경로에 따라 달라 쓰지 않는다. 같은 의존이 `DROP TABLE` 자체도
막으므로 `CASCADE`는 절대 쓰지 않는다), ② `audit_log`에 새 행위(`reference.create`,
`reference_value.add`, `reference_value.update`)의 행이 있다(CHECK를 옛 정의로 되돌리면 그 행이
제약에
걸리고, 감사 기록은 지우지 않는다). 둘 다 없을 때만 CHECK 교체 2개를 되돌리고 표를 외래키 역순으로
지운다. 오프라인 `--sql` 생성에서는 DB를 읽을 수 없으므로 사전 점검을 건너뛰고 DDL만 출력한다
(0008과 같음). 운영에서 downgrade를 하지 않는 원칙(D5)은 그대로다.

`drop_constraint` 4개(upgrade 2 + downgrade 2)와 `drop_table` 2개(downgrade)는 "DROP 확인: 사용자
승인 (2026-10-14, 03b 32-3)"이며 `tests/test_migrations.py`의 `DROP_APPROVED`에 기록돼 있다. 승인은
이 항목들에 한한다.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reference_items",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reference_items")),
        sa.UniqueConstraint("name", name=op.f("uq_reference_items_name")),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_reference_items_created_by_users")
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 50", name=op.f("ck_reference_items_name_length")
        ),
    )
    op.create_table(
        "reference_values",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("number_value", sa.Numeric(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reference_values")),
        sa.UniqueConstraint("item_id", "year", name=op.f("uq_reference_values_item_id_year")),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["reference_items.id"],
            name=op.f("fk_reference_values_item_id_reference_items"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_reference_values_created_by_users")
        ),
        sa.CheckConstraint("year BETWEEN 1900 AND 9999", name=op.f("ck_reference_values_year")),
        sa.CheckConstraint(
            "number_value > '-Infinity' AND number_value < 'Infinity'",
            name=op.f("ck_reference_values_finite"),
        ),
    )

    # 명시 GRANT(06 §2-2): 읽기·추가는 표 단위, 정정은 값 열·설명 열만(열 단위). DELETE 없음.
    op.execute("GRANT SELECT, INSERT ON reference_items TO bi_app")
    op.execute("GRANT UPDATE (description) ON reference_items TO bi_app")
    op.execute("GRANT SELECT, INSERT ON reference_values TO bi_app")
    op.execute("GRANT UPDATE (number_value) ON reference_values TO bi_app")

    op.drop_constraint(op.f("ck_audit_log_action"), "audit_log", type_="check")
    op.create_check_constraint(
        op.f("ck_audit_log_action"),
        "audit_log",
        "action IN ('dataset.create', 'dataset.update', 'dataset.archive', 'dataset.restore', "
        "'column.add', 'column.update', "
        "'formula_column.add', 'formula_column.update', 'team.create', 'team.update', "
        "'member.set', 'member.remove', 'user.create', 'user.update', "
        "'user.bootstrap_admin', 'dashboard.create', 'dashboard.update', "
        "'reference.create', 'reference_value.add', 'reference_value.update')",
    )
    op.drop_constraint(op.f("ck_audit_log_target_type"), "audit_log", type_="check")
    op.create_check_constraint(
        op.f("ck_audit_log_target_type"),
        "audit_log",
        "target_type IN ('team', 'user', 'dataset', 'dashboard', 'reference')",
    )


def _refuse_if_reference_data_exists() -> None:
    """기준값을 읽는 뷰나 기준값 감사 행이 있으면 거부한다(아무것도 바꾸기 전에)."""
    if context.is_offline_mode():
        return
    bind = op.get_bind()
    if bind.execute(
        sa.text(
            "SELECT 1 FROM pg_depend d "
            "JOIN pg_rewrite r ON r.oid = d.objid "
            "JOIN pg_class c ON c.oid = r.ev_class "
            "WHERE d.classid = 'pg_rewrite'::regclass "
            "AND d.refclassid = 'pg_class'::regclass "
            "AND d.refobjid = 'public.reference_values'::regclass "
            "AND c.relkind = 'v' LIMIT 1"
        )
    ).first():
        raise RuntimeError(
            "되돌릴 수 없습니다: 기준값(REF)을 쓰는 데이터셋의 뷰가 있습니다. "
            "그 수식을 먼저 고친 뒤 다시 시도하세요. 아무것도 바꾸지 않았습니다."
        )
    if bind.execute(
        sa.text(
            "SELECT 1 FROM audit_log WHERE action IN "
            "('reference.create', 'reference_value.add', 'reference_value.update') LIMIT 1"
        )
    ).first():
        raise RuntimeError(
            "되돌릴 수 없습니다: 기준값 변경 감사 기록이 있습니다. "
            "감사 기록은 지우지 않으므로 수정 revision으로 대응하세요. 아무것도 바꾸지 않았습니다."
        )


def downgrade() -> None:
    _refuse_if_reference_data_exists()
    op.drop_constraint(op.f("ck_audit_log_target_type"), "audit_log", type_="check")
    op.create_check_constraint(
        op.f("ck_audit_log_target_type"),
        "audit_log",
        "target_type IN ('team', 'user', 'dataset', 'dashboard')",
    )
    op.drop_constraint(op.f("ck_audit_log_action"), "audit_log", type_="check")
    op.create_check_constraint(
        op.f("ck_audit_log_action"),
        "audit_log",
        "action IN ('dataset.create', 'dataset.update', 'dataset.archive', 'dataset.restore', "
        "'column.add', 'column.update', "
        "'formula_column.add', 'formula_column.update', 'team.create', 'team.update', "
        "'member.set', 'member.remove', 'user.create', 'user.update', "
        "'user.bootstrap_admin', 'dashboard.create', 'dashboard.update')",
    )
    # 표를 지우면 인덱스·CHECK·권한(ACL)도 함께 사라진다(외래키 역순).
    op.drop_table("reference_values")
    op.drop_table("reference_items")
