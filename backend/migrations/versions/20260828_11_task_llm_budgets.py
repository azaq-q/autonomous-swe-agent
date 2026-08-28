"""Add per-task LLM resource budgets and call accounting."""

import sqlalchemy as sa
from alembic import op

revision = "20260828_11"
down_revision = "20260824_10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("task") as batch_op:
        batch_op.add_column(
            sa.Column("max_input_tokens", sa.Integer(), nullable=False, server_default="8000000")
        )
        batch_op.add_column(
            sa.Column("max_output_tokens", sa.Integer(), nullable=False, server_default="250000")
        )
        batch_op.add_column(
            sa.Column("max_llm_calls", sa.Integer(), nullable=False, server_default="128")
        )
        batch_op.add_column(
            sa.Column("max_cost_usd", sa.Float(), nullable=False, server_default="2.0")
        )
        batch_op.add_column(
            sa.Column("llm_calls", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("task") as batch_op:
        batch_op.drop_column("llm_calls")
        batch_op.drop_column("max_cost_usd")
        batch_op.drop_column("max_llm_calls")
        batch_op.drop_column("max_output_tokens")
        batch_op.drop_column("max_input_tokens")
