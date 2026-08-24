"""Embedding provider configuration and normalization tests."""

import sys
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.rag.embeddings import FastEmbedder, HashingEmbedder, create_embedder


def test_create_hashing_embedder_uses_configured_dimensions():
    embedder = create_embedder(
        Settings(embedding_provider="hashing", embedding_dimensions=16)
    )

    assert isinstance(embedder, HashingEmbedder)
    assert len(embedder.embed_query("semantic search")) == 16


def test_fastembed_normalizes_and_checks_dimensions(monkeypatch):
    class _TextEmbedding:
        def __init__(self, model_name, cache_dir, specific_model_path):
            self.model_name = model_name

        def embed(self, texts, batch_size):
            return iter([[3.0, 4.0] for _ in texts])

        def query_embed(self, text):
            return iter([[0.0, 5.0]])

    monkeypatch.setitem(sys.modules, "fastembed", SimpleNamespace(TextEmbedding=_TextEmbedding))
    embedder = FastEmbedder(model_name="test", dimensions=2, batch_size=8)

    assert embedder.embed_documents(["a"])[0] == [0.6, 0.8]
    assert embedder.embed_query("query") == [0.0, 1.0]


def test_openai_provider_requires_key():
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        create_embedder(Settings(embedding_provider="openai", openai_api_key=None))


def test_unknown_embedding_provider_is_rejected():
    with pytest.raises(ValueError, match="unsupported embedding provider"):
        create_embedder(Settings(embedding_provider="mystery"))
