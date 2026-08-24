"""Task-local repository index available to Agent search tools."""

import hashlib
import json
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from app.core.config import Settings, get_settings
from app.db.session import SessionLocal
from app.models.code_index import VECTOR_DIMENSIONS
from app.rag.chunker import chunk_code
from app.rag.embeddings import Embedder, create_embedder
from app.rag.retriever import CodeRetriever
from app.rag.store import PgVectorCodeIndex, SessionFactory

_SUPPORTED = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java"}
_IGNORED_PARTS = {".git", ".venv", "node_modules", "dist", "build", ".next"}
_current_retriever: ContextVar[CodeRetriever | None] = ContextVar(
    "repository_retriever", default=None
)


def collect_repository_chunks(root: Path, max_files: int = 2_000) -> list[dict]:
    root = root.resolve()
    chunks: list[dict] = []
    file_count = 0
    for path in root.rglob("*"):
        if file_count >= max_files:
            break
        if not path.is_file() or path.suffix.lower() not in _SUPPORTED:
            continue
        relative = path.relative_to(root)
        if any(part in _IGNORED_PARTS for part in relative.parts):
            continue
        if path.stat().st_size > 1_000_000:
            continue
        content = path.read_text(encoding="utf-8", errors="replace")
        chunks.extend(chunk_code(content, source=relative.as_posix()))
        file_count += 1
    return chunks


def build_repository_index(
    root: Path,
    max_files: int = 2_000,
    *,
    repository: str = "local",
    source_commit: str = "working-tree",
    settings: Settings | None = None,
    embedder: Embedder | None = None,
    session_factory: SessionFactory | None = None,
) -> CodeRetriever:
    selected = settings or get_settings()
    selected_embedder = embedder or create_embedder(selected)
    chunks = collect_repository_chunks(root, max_files=max_files)
    documents = [CodeRetriever._document(chunk) for chunk in chunks]
    content_digest = hashlib.sha256(
        json.dumps(documents, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    namespace = getattr(selected_embedder, "namespace", type(selected_embedder).__name__)
    index_key = hashlib.sha256(
        f"{repository}\0{source_commit}\0{content_digest}\0{namespace}".encode()
    ).hexdigest()

    if selected.rag_vector_store.strip().lower() == "memory":
        return CodeRetriever(
            chunks=chunks,
            embedder=selected_embedder,
            vectors=selected_embedder.embed_documents(documents),
            vector_threshold=selected.rag_vector_threshold,
        )
    if selected.rag_vector_store.strip().lower() != "pgvector":
        raise ValueError(f"unsupported RAG vector store: {selected.rag_vector_store}")
    if selected.embedding_dimensions != VECTOR_DIMENSIONS:
        raise ValueError(f"pgvector requires {VECTOR_DIMENSIONS}-dimensional embeddings")
    if not selected.database_url.startswith("postgresql") and session_factory is None:
        raise ValueError("pgvector RAG store requires a PostgreSQL DATABASE_URL")

    store = PgVectorCodeIndex(session_factory or SessionLocal)
    cached_chunks = store.load(index_key)
    cache_hit = bool(cached_chunks)
    if not cache_hit:
        vectors = selected_embedder.embed_documents(documents)
        store.replace(
            index_key=index_key,
            repository=repository,
            source_commit=source_commit,
            content_digest=content_digest,
            embedding_namespace=namespace,
            chunks=CodeRetriever(chunks=chunks).chunks,
            vectors=vectors,
        )
        cached_chunks = store.load(index_key)
    retriever = CodeRetriever(
        chunks=cached_chunks,
        embedder=selected_embedder,
        vector_searcher=lambda query, k: store.search(index_key, query, k),
        vector_threshold=selected.rag_vector_threshold,
    )
    retriever.index_metadata = {
        "index_key": index_key,
        "cache_hit": cache_hit,
        "store": "pgvector",
        "embedding_namespace": namespace,
    }
    return retriever


@contextmanager
def repository_index_scope(
    root: Path,
    *,
    repository: str = "local",
    source_commit: str = "working-tree",
) -> Generator[CodeRetriever, None, None]:
    retriever = build_repository_index(
        root,
        repository=repository,
        source_commit=source_commit,
    )
    token = _current_retriever.set(retriever)
    try:
        yield retriever
    finally:
        _current_retriever.reset(token)


def get_repository_retriever() -> CodeRetriever:
    retriever = _current_retriever.get()
    if retriever is None:
        raise RuntimeError("当前任务尚未建立代码索引")
    return retriever
