"""Add persistent pgvector repository code index."""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "20260824_09"
down_revision = "20260824_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    inspector = sa.inspect(bind)
    if "code_embedding" in inspector.get_table_names():
        return
    op.create_table(
        "code_embedding",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("index_key", sa.String(length=64), nullable=False),
        sa.Column("chunk_id", sa.String(length=64), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("repository", sa.Text(), nullable=False),
        sa.Column("source_commit", sa.String(length=64), nullable=False),
        sa.Column("content_digest", sa.String(length=64), nullable=False),
        sa.Column("embedding_namespace", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=True),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("node_type", sa.String(length=64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "index_key", "chunk_id", name="uq_code_embedding_index_chunk"
        ),
    )
    op.create_index(
        "ix_code_embedding_index_position",
        "code_embedding",
        ["index_key", "position"],
    )
    if bind.dialect.name == "postgresql":
        op.create_index(
            "ix_code_embedding_vector_hnsw",
            "code_embedding",
            ["embedding"],
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        )


def downgrade() -> None:
    op.drop_table("code_embedding")
