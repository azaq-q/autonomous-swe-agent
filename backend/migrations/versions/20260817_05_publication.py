"""Add commit and pull request publication fields."""

import sqlalchemy as sa
from alembic import op

revision = "20260817_05"
down_revision = "20260817_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {column["name"] for column in inspector.get_columns("task")}
    columns = {
        "published_commit": sa.Column(
            "published_commit", sa.String(length=64), nullable=True
        ),
        "pr_url": sa.Column("pr_url", sa.Text(), nullable=True),
        "pr_number": sa.Column("pr_number", sa.Integer(), nullable=True),
    }
    with op.batch_alter_table("task") as batch_op:
        for name, column in columns.items():
            if name not in existing:
                batch_op.add_column(column)


def downgrade() -> None:
    with op.batch_alter_table("task") as batch_op:
        batch_op.drop_column("pr_number")
        batch_op.drop_column("pr_url")
        batch_op.drop_column("published_commit")
