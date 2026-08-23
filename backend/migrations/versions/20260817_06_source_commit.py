"""Add optional pinned source commit for reproducible evaluations."""

import sqlalchemy as sa
from alembic import op

revision = "20260817_06"
down_revision = "20260817_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {column["name"] for column in inspector.get_columns("task")}
    if "source_commit" not in existing:
        with op.batch_alter_table("task") as batch_op:
            batch_op.add_column(
                sa.Column("source_commit", sa.String(length=64), nullable=True)
            )


def downgrade() -> None:
    with op.batch_alter_table("task") as batch_op:
        batch_op.drop_column("source_commit")
