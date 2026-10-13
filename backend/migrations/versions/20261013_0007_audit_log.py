"""감사 기록 정적 표: audit_log (FU-2a, 06 §2-1, 03b 29-1)

- `audit_log`: 정의·권한·대시보드 연결 변경 15개 행위의 누가·언제·무엇을 남기는 추가 전용 표.
  `id`는 `bigint` identity(행이 계속 쌓이는 유일한 표), `actor_user_id`는 사용자 번호만(서버
  명령이면 NULL, FK `users.id`), `target_id`는 여러 표를 가리키므로 FK가 없다. `details`는 jsonb
  객체이며 허용 키·형은 앱(`app/audit/actions.py`)이 지킨다.
- CHECK 6개(이름은 `NAMING_CONVENTION`, `ck_audit_log_<이름>`): `action`(15개 값), `target_type`,
  `actor_source`, `actor_consistency`(행위자를 비울 수 있는 것은 `cli`뿐), `details_object`,
  `details_size`(4000바이트, 앱 규칙의 안전망).
- 인덱스 3개(최소): 기간·기본 정렬, 행위자 필터, 대상 필터. `action` 필터는 인덱스 없이 건다.
- `bi_app`의 권한은 **`GRANT SELECT, INSERT` 한 줄**이다. UPDATE·DELETE·TRUNCATE·REFERENCES·
  TRIGGER도 시퀀스 권한도 없다(identity라 INSERT 권한으로 번호가 붙는다, 06 §2-1).
  `bi_readonly`·Superset에는 아무것도 주지 않는다. `audit_log`는 `public`(정적 표)이며 `bi_data`에
  두지 않는다.
- 업그레이드에는 `DROP`이 없다(새 표와 인덱스만 추가, 기존 표·열·권한 변경 없음). 모든 SQL은
  보간 없는 고정 문자열이다(D3).

downgrade는 표를 지운다(`DROP TABLE`, 인덱스·CHECK·권한도 함께 사라진다). 표를 참조하는 쪽은 없고
`audit_log`만 `users`를 참조하므로 순서 문제가 없다. **경고: downgrade는 감사 기록 전체를 지운다.**
되돌리기용이 아니라 왕복 시험용이다. 운영에서는 하지 않고 문제는 수정 revision으로 대응한다(D5).
이 DROP은 사용자가 2026-10-14에 승인했고(03b 29-3) `tests/test_migrations.py`의 `DROP_APPROVED`에
"DROP 확인: 사용자 승인"으로 기록돼 있다. 운영에서는 하지 않고, 부득이하면 실행 전 백업이 필수다.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_source", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], name=op.f("fk_audit_log_actor_user_id_users")
        ),
        sa.CheckConstraint(
            "action IN ('dataset.create', 'dataset.update', 'column.add', 'column.update', "
            "'formula_column.add', 'formula_column.update', 'team.create', 'team.update', "
            "'member.set', 'member.remove', 'user.create', 'user.update', "
            "'user.bootstrap_admin', 'dashboard.create', 'dashboard.update')",
            name=op.f("ck_audit_log_action"),
        ),
        sa.CheckConstraint(
            "target_type IN ('team', 'user', 'dataset', 'dashboard')",
            name=op.f("ck_audit_log_target_type"),
        ),
        sa.CheckConstraint(
            "actor_source IN ('user', 'cli')", name=op.f("ck_audit_log_actor_source")
        ),
        sa.CheckConstraint(
            "(actor_source = 'user' AND actor_user_id IS NOT NULL) "
            "OR (actor_source = 'cli' AND actor_user_id IS NULL)",
            name=op.f("ck_audit_log_actor_consistency"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(details) = 'object'", name=op.f("ck_audit_log_details_object")
        ),
        sa.CheckConstraint(
            "octet_length(details::text) <= 4000", name=op.f("ck_audit_log_details_size")
        ),
    )
    op.create_index(
        "ix_audit_log_occurred_at_id",
        "audit_log",
        [sa.text("occurred_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_audit_log_actor_user_id_occurred_at_id",
        "audit_log",
        ["actor_user_id", sa.text("occurred_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_audit_log_target_type_target_id_occurred_at_id",
        "audit_log",
        ["target_type", "target_id", sa.text("occurred_at DESC"), sa.text("id DESC")],
    )

    # 명시 GRANT(06 §2-1): 읽기와 추가만. 열 단위가 아니고 UPDATE·DELETE·TRUNCATE는 없다.
    op.execute("GRANT SELECT, INSERT ON audit_log TO bi_app")


def downgrade() -> None:
    # 표를 지우면 인덱스·CHECK·권한(ACL)도 함께 사라진다. 감사 기록 전체가 지워진다(경고 참고).
    op.drop_table("audit_log")
