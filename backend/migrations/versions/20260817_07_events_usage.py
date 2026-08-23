"""Add append-only task events and token/cost aggregates."""

import sqlalchemy as sa
from alembic import op

revision = "20260817_07"
down_revision = "20260817_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {column["name"] for column in inspector.get_columns("task")}
    columns = {
        "input_tokens": sa.Column(
            "input_tokens", sa.Integer(), nullable=False, server_default="0"
        ),
        "output_tokens": sa.Column(
            "output_tokens", sa.Integer(), nullable=False, server_default="0"
        ),
        "estimated_cost_usd": sa.Column(
            "estimated_cost_usd", sa.Float(), nullable=False, server_default="0"
        ),
    }
    with op.batch_alter_table("task") as batch_op:
        for name, column in columns.items():
            if name not in existing:
                batch_op.add_column(column)
    if "task_event" not in inspector.get_table_names():
        op.create_table(
            "task_event",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("task_id", sa.Integer(), sa.ForeignKey("task.id"), nullable=False),
            sa.Column("event_type", sa.String(length=128), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_task_event_task_id", "task_event", ["task_id"])
        op.create_index("ix_task_event_event_type", "task_event", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_task_event_event_type", table_name="task_event")
    op.drop_index("ix_task_event_task_id", table_name="task_event")
    op.drop_table("task_event")
    with op.batch_alter_table("task") as batch_op:
        batch_op.drop_column("estimated_cost_usd")
        batch_op.drop_column("output_tokens")
        batch_op.drop_column("input_tokens")
