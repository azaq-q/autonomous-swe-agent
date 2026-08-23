"""Add queue dispatch, retry and cancellation fields."""

import sqlalchemy as sa
from alembic import op

revision = "20260817_03"
down_revision = "20260817_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {column["name"] for column in inspector.get_columns("task")}
    columns = {
        "dispatch_id": sa.Column("dispatch_id", sa.String(length=255), nullable=True),
        "attempt": sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        "cancel_requested": sa.Column(
            "cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    }
    with op.batch_alter_table("task") as batch_op:
        for name, column in columns.items():
            if name not in existing:
                batch_op.add_column(column)


def downgrade() -> None:
    with op.batch_alter_table("task") as batch_op:
        batch_op.drop_column("cancel_requested")
        batch_op.drop_column("attempt")
        batch_op.drop_column("dispatch_id")
