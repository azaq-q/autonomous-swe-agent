"""PostgreSQL/pgvector persistence for repository code chunks."""

import hashlib
from collections.abc import Callable

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.code_index import VECTOR_DIMENSIONS, CodeEmbedding

SessionFactory = Callable[[], Session]


class PgVectorCodeIndex:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def load(self, index_key: str) -> list[dict]:
        with self.session_factory() as session:
            rows = session.execute(
                select(
                    CodeEmbedding.chunk_id,
                    CodeEmbedding.source,
                    CodeEmbedding.language,
                    CodeEmbedding.symbol,
                    CodeEmbedding.node_type,
                    CodeEmbedding.content,
                    CodeEmbedding.start_line,
                    CodeEmbedding.end_line,
                )
                .where(CodeEmbedding.index_key == index_key)
                .order_by(CodeEmbedding.position)
            ).all()
        return [
            {
                "chunk_id": row.chunk_id,
                "source": row.source,
                "language": row.language,
                "symbol": row.symbol,
                "node_type": row.node_type,
                "content": row.content,
                "start_line": row.start_line,
                "end_line": row.end_line,
            }
            for row in rows
        ]

    def replace(
        self,
        *,
        index_key: str,
        repository: str,
        source_commit: str,
        content_digest: str,
        embedding_namespace: str,
        chunks: list[dict],
        vectors: list[list[float]],
    ) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunk and embedding counts do not match")
        if any(len(vector) != VECTOR_DIMENSIONS for vector in vectors):
            raise ValueError(f"pgvector storage requires {VECTOR_DIMENSIONS} dimensions")
        with self.session_factory() as session:
            if session.get_bind().dialect.name == "postgresql":
                lock_id = int.from_bytes(
                    hashlib.sha256(index_key.encode()).digest()[:8],
                    "big",
                    signed=True,
                )
                session.execute(select(func.pg_advisory_xact_lock(lock_id)))
            session.execute(delete(CodeEmbedding).where(CodeEmbedding.index_key == index_key))
            session.add_all(
                CodeEmbedding(
                    index_key=index_key,
                    chunk_id=chunk["chunk_id"],
                    position=position,
                    repository=repository,
                    source_commit=source_commit,
                    content_digest=content_digest,
                    embedding_namespace=embedding_namespace,
                    source=chunk["source"],
                    language=chunk.get("language"),
                    symbol=chunk["symbol"],
                    node_type=chunk["node_type"],
                    content=chunk["content"],
                    start_line=chunk["start_line"],
                    end_line=chunk["end_line"],
                    embedding=vector,
                )
                for position, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
            )
            session.commit()

    def search(
        self, index_key: str, query_vector: list[float], k: int
    ) -> list[tuple[str, float]]:
        if len(query_vector) != VECTOR_DIMENSIONS:
            raise ValueError(f"pgvector search requires {VECTOR_DIMENSIONS} dimensions")
        distance = CodeEmbedding.embedding.cosine_distance(query_vector).label("distance")
        with self.session_factory() as session:
            rows = session.execute(
                select(CodeEmbedding.chunk_id, distance)
                .where(CodeEmbedding.index_key == index_key)
                .order_by(distance)
                .limit(k)
            ).all()
        return [(row.chunk_id, 1.0 - float(row.distance)) for row in rows]

    def count(self, index_key: str) -> int:
        with self.session_factory() as session:
            return int(
                session.scalar(
                    select(func.count()).select_from(CodeEmbedding).where(
                        CodeEmbedding.index_key == index_key
                    )
                )
                or 0
            )
