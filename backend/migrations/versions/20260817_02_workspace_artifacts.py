"""Add reproducible workspace and patch artifact fields."""

import sqlalchemy as sa
from alembic import op

revision = "20260817_02"
down_revision = "20260817_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {column["name"] for column in inspector.get_columns("task")}
    columns = {
        "workspace_path": sa.Column("workspace_path", sa.Text(), nullable=True),
        "base_commit": sa.Column("base_commit", sa.String(length=64), nullable=True),
        "work_branch": sa.Column("work_branch", sa.String(length=255), nullable=True),
        "artifact_path": sa.Column("artifact_path", sa.Text(), nullable=True),
        "artifact_sha256": sa.Column(
            "artifact_sha256", sa.String(length=64), nullable=True
        ),
    }
    with op.batch_alter_table("task") as batch_op:
        for name, column in columns.items():
            if name not in existing:
                batch_op.add_column(column)


def downgrade() -> None:
    with op.batch_alter_table("task") as batch_op:
        batch_op.drop_column("artifact_sha256")
        batch_op.drop_column("artifact_path")
        batch_op.drop_column("work_branch")
        batch_op.drop_column("base_commit")
        batch_op.drop_column("workspace_path")
