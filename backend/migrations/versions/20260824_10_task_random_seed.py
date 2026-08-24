"""Add a repeat seed to benchmark task executions."""

import sqlalchemy as sa
from alembic import op

revision = "20260824_10"
down_revision = "20260824_09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("task") as batch_op:
        batch_op.add_column(sa.Column("random_seed", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("task") as batch_op:
        batch_op.drop_column("random_seed")
