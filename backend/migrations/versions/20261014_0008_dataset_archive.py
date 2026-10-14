"""데이터셋 보관·복구: CHECK 두 개 교체 (FU-2b, 06 §6 `0008`, 03b 30-1)

- `ck_datasets_status`: `status IN ('active')` -> `status IN ('active', 'archived')`.
- `ck_audit_log_action`: 15개 값 -> 17개 값(`dataset.archive`, `dataset.restore` 추가).
- **새 열·표·인덱스·GRANT 변경이 없다.** `bi_app`은 `datasets.status`의 UPDATE 권한을 0004부터
  가지고 있고 `audit_log`는 SELECT·INSERT 그대로다. `bi_data`의 동적 객체도 건드리지 않는다.
- 제약 이름은 반드시 `op.f(...)`로 쓴다. `op.f`는 이름 규칙(`ck_%(table_name)s_%(constraint_name)s`,
  `app/db_metadata.py`)이 이름을 한 번 더 붙이지 않게 한다(0004·0007과 같은 방식).
- 모든 SQL은 보간 없는 고정 문자열이다(D3).

`drop_constraint` 4개(upgrade 2 + downgrade 2)는 "DROP 확인: 사용자 승인 (2026-10-14, 03b 30-1)"이며
`tests/test_migrations.py`의 `DROP_APPROVED`에 기록돼 있다. 승인은 이 제약 교체에 한한다.

downgrade는 **사전 점검**을 먼저 한다. 보관 행(`datasets.status <> 'active'`)이나 새 감사 행
(`dataset.archive`·`dataset.restore`)이 하나라도 있으면 한국어 메시지로 거부하고 아무것도 바꾸지
않는다(CHECK를 옛 정의로 되돌리면 그 행들이 제약에 걸리고, 감사 기록은 지우지 않는다).
오프라인 `--sql` 생성에서는 DB를 읽을 수 없으므로 사전 점검을 건너뛰고 제약 교체만 출력한다.
운영에서 downgrade를 하지 않는 원칙(D5)은 그대로다.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_datasets_status"), "datasets", type_="check")
    op.create_check_constraint(
        op.f("ck_datasets_status"), "datasets", "status IN ('active', 'archived')"
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


def _refuse_if_archive_data_exists() -> None:
    """보관 행이나 보관·복구 감사 행이 있으면 거부한다(아무것도 바꾸기 전에)."""
    if context.is_offline_mode():
        return
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM datasets WHERE status <> 'active' LIMIT 1")).first():
        raise RuntimeError(
            "되돌릴 수 없습니다: 보관된 데이터셋이 있습니다. 모두 복구한 뒤 다시 시도하세요. "
            "아무것도 바꾸지 않았습니다."
        )
    if bind.execute(
        sa.text(
            "SELECT 1 FROM audit_log WHERE action IN ('dataset.archive', 'dataset.restore') LIMIT 1"
        )
    ).first():
        raise RuntimeError(
            "되돌릴 수 없습니다: 데이터셋 보관·복구 감사 기록이 있습니다. "
            "감사 기록은 지우지 않으므로 수정 revision으로 대응하세요. 아무것도 바꾸지 않았습니다."
        )


def downgrade() -> None:
    _refuse_if_archive_data_exists()
    op.drop_constraint(op.f("ck_audit_log_action"), "audit_log", type_="check")
    op.create_check_constraint(
        op.f("ck_audit_log_action"),
        "audit_log",
        "action IN ('dataset.create', 'dataset.update', 'column.add', 'column.update', "
        "'formula_column.add', 'formula_column.update', 'team.create', 'team.update', "
        "'member.set', 'member.remove', 'user.create', 'user.update', "
        "'user.bootstrap_admin', 'dashboard.create', 'dashboard.update')",
    )
    op.drop_constraint(op.f("ck_datasets_status"), "datasets", type_="check")
    op.create_check_constraint(op.f("ck_datasets_status"), "datasets", "status IN ('active')")
