"""Repository index cache-key and pgvector integration boundary tests."""

from app.core.config import Settings
from app.rag.context import build_repository_index


class _Embedder:
    dimensions = 384
    namespace = "test-semantic-v1"

    def __init__(self):
        self.document_calls = 0

    def embed_documents(self, texts):
        self.document_calls += 1
        return [[1.0] + [0.0] * 383 for _ in texts]

    def embed_query(self, text):
        return [1.0] + [0.0] * 383


class _Store:
    rows: dict[str, list[dict]] = {}

    def __init__(self, session_factory):
        pass

    def load(self, index_key):
        return self.rows.get(index_key, [])

    def replace(self, *, index_key, chunks, **kwargs):
        self.rows[index_key] = [dict(chunk) for chunk in chunks]

    def search(self, index_key, query, k):
        return [(chunk["chunk_id"], 1.0) for chunk in self.rows[index_key][:k]]


def test_pgvector_cache_reuses_same_content(monkeypatch, tmp_path):
    from app.rag import context

    _Store.rows = {}
    monkeypatch.setattr(context, "PgVectorCodeIndex", _Store)
    (tmp_path / "auth.py").write_text("def login():\n    return True\n", encoding="utf-8")
    settings = Settings(
        database_url="postgresql+psycopg://test",
        rag_vector_store="pgvector",
        embedding_dimensions=384,
    )
    embedder = _Embedder()

    first = build_repository_index(
        tmp_path,
        repository="repo",
        source_commit="a" * 40,
        settings=settings,
        embedder=embedder,
        session_factory=lambda: None,
    )
    second = build_repository_index(
        tmp_path,
        repository="repo",
        source_commit="a" * 40,
        settings=settings,
        embedder=embedder,
        session_factory=lambda: None,
    )

    assert first.index_metadata["cache_hit"] is False
    assert second.index_metadata["cache_hit"] is True
    assert embedder.document_calls == 1
    assert second.search("authentication")[0]["source"] == "auth.py"


def test_pgvector_cache_invalidates_changed_content(monkeypatch, tmp_path):
    from app.rag import context

    _Store.rows = {}
    monkeypatch.setattr(context, "PgVectorCodeIndex", _Store)
    source = tmp_path / "module.py"
    source.write_text("value = 1\n", encoding="utf-8")
    settings = Settings(
        database_url="postgresql+psycopg://test",
        rag_vector_store="pgvector",
        embedding_dimensions=384,
    )
    embedder = _Embedder()
    first = build_repository_index(
        tmp_path, settings=settings, embedder=embedder, session_factory=lambda: None
    )
    source.write_text("value = 2\n", encoding="utf-8")
    second = build_repository_index(
        tmp_path, settings=settings, embedder=embedder, session_factory=lambda: None
    )

    assert first.index_metadata["index_key"] != second.index_metadata["index_key"]
    assert embedder.document_calls == 2
