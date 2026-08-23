"""Add workflow revision and human approval audit records."""

import sqlalchemy as sa
from alembic import op

revision = "20260817_04"
down_revision = "20260817_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    task_columns = {column["name"] for column in inspector.get_columns("task")}
    if "revision" not in task_columns:
        with op.batch_alter_table("task") as batch_op:
            batch_op.add_column(
                sa.Column("revision", sa.Integer(), nullable=False, server_default="0")
            )
    if "approval" not in inspector.get_table_names():
        op.create_table(
            "approval",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("task_id", sa.Integer(), sa.ForeignKey("task.id"), nullable=False),
            sa.Column("decision", sa.String(length=32), nullable=False),
            sa.Column("feedback", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_approval_task_id", "approval", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_approval_task_id", table_name="approval")
    op.drop_table("approval")
    with op.batch_alter_table("task") as batch_op:
        batch_op.drop_column("revision")
