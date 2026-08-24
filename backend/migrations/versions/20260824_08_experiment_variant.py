"""Add per-task experiment variant for benchmark ablations."""

import sqlalchemy as sa
from alembic import op

revision = "20260824_08"
down_revision = "20260817_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {column["name"] for column in inspector.get_columns("task")}
    if "experiment_variant" not in existing:
        with op.batch_alter_table("task") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "experiment_variant",
                    sa.String(length=32),
                    nullable=False,
                    server_default="full",
                )
            )


def downgrade() -> None:
    with op.batch_alter_table("task") as batch_op:
        batch_op.drop_column("experiment_variant")
