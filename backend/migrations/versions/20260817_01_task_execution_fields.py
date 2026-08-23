"""Add repository task contract and execution results."""

import sqlalchemy as sa
from alembic import op

revision = "20260817_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "task" not in inspector.get_table_names():
        op.create_table(
            "task",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("task_id", sa.String(length=32), nullable=False, unique=True),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("repository", sa.Text(), nullable=True),
            sa.Column("base_branch", sa.String(length=128), nullable=False, server_default="main"),
            sa.Column("test_command", sa.Text(), nullable=False, server_default="pytest"),
            sa.Column("max_iterations", sa.Integer(), nullable=False, server_default="3"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("steps", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("result", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_table(
            "execution",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("task_id", sa.Integer(), sa.ForeignKey("task.id"), nullable=False),
            sa.Column("agent_name", sa.String(length=64), nullable=False),
            sa.Column("input", sa.Text(), nullable=True),
            sa.Column("output", sa.Text(), nullable=True),
            sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        )
        return

    existing = {column["name"] for column in inspector.get_columns("task")}
    with op.batch_alter_table("task") as batch_op:
        if "repository" not in existing:
            batch_op.add_column(sa.Column("repository", sa.Text(), nullable=True))
        if "base_branch" not in existing:
            batch_op.add_column(
                sa.Column(
                    "base_branch",
                    sa.String(length=128),
                    nullable=False,
                    server_default="main",
                )
            )
        if "test_command" not in existing:
            batch_op.add_column(
                sa.Column("test_command", sa.Text(), nullable=False, server_default="pytest")
            )
        if "max_iterations" not in existing:
            batch_op.add_column(
                sa.Column("max_iterations", sa.Integer(), nullable=False, server_default="3")
            )
        if "result" not in existing:
            batch_op.add_column(
                sa.Column("result", sa.JSON(), nullable=False, server_default=sa.text("'{}'"))
            )
        if "error" not in existing:
            batch_op.add_column(sa.Column("error", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("task") as batch_op:
        batch_op.drop_column("error")
        batch_op.drop_column("result")
        batch_op.drop_column("max_iterations")
        batch_op.drop_column("test_command")
        batch_op.drop_column("base_branch")
        batch_op.drop_column("repository")
