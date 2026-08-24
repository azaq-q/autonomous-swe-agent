"""Embedding providers for deterministic fallback and real semantic retrieval."""

import hashlib
import math
import re
from collections.abc import Iterable
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.core.config import Settings

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[\u4e00-\u9fff]")


class Embedder(Protocol):
    dimensions: int
    namespace: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class HashingEmbedder:
    """Offline feature-hashing baseline; replace with a semantic model in production."""

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions
        self.namespace = f"hashing-blake2b-{dimensions}"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in _TOKEN_RE.findall(text.lower()):
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            value = int.from_bytes(digest, "big")
            index = value % self.dimensions
            vector[index] += 1.0 if value & 1 else -1.0
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector


class FastEmbedder:
    """Local neural embeddings backed by FastEmbed and ONNX Runtime."""

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-en",
        dimensions: int = 384,
        batch_size: int = 64,
        cache_dir: str | None = None,
        model_path: str | None = None,
    ) -> None:
        from fastembed import TextEmbedding

        self.model_name = model_name
        self.dimensions = dimensions
        self.batch_size = batch_size
        self.namespace = f"fastembed:{model_name}:{dimensions}"
        self._model = TextEmbedding(
            model_name=model_name,
            cache_dir=cache_dir,
            specific_model_path=model_path,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._vectors(self._model.embed(texts, batch_size=self.batch_size))

    def embed_query(self, text: str) -> list[float]:
        return self._vectors(self._model.query_embed(text))[0]

    def _vectors(self, values: Iterable) -> list[list[float]]:
        vectors = [_normalize([float(value) for value in vector]) for vector in values]
        if any(len(vector) != self.dimensions for vector in vectors):
            actual = len(vectors[0]) if vectors else 0
            raise ValueError(
                f"embedding dimension mismatch: expected={self.dimensions}, actual={actual}"
            )
        return vectors


class OpenAIEmbedder:
    """OpenAI-compatible embeddings with an explicit, fixed vector dimension."""

    def __init__(
        self,
        *,
        model_name: str,
        dimensions: int,
        api_key: str,
        base_url: str | None = None,
    ) -> None:
        from langchain_openai import OpenAIEmbeddings

        self.dimensions = dimensions
        endpoint = (
            hashlib.sha256(base_url.encode()).hexdigest()[:12] if base_url else "default"
        )
        self.namespace = f"openai:{endpoint}:{model_name}:{dimensions}"
        self._model = OpenAIEmbeddings(
            model=model_name,
            dimensions=dimensions,
            api_key=api_key,
            base_url=base_url,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [_normalize(vector) for vector in self._model.embed_documents(texts)]

    def embed_query(self, text: str) -> list[float]:
        return _normalize(self._model.embed_query(text))


def create_embedder(settings: "Settings | None" = None) -> Embedder:
    from app.core.config import get_settings

    selected = settings or get_settings()
    provider = selected.embedding_provider.strip().lower()
    if provider == "hashing":
        return HashingEmbedder(selected.embedding_dimensions)
    if provider == "fastembed":
        return FastEmbedder(
            model_name=selected.embedding_model,
            dimensions=selected.embedding_dimensions,
            batch_size=selected.embedding_batch_size,
            cache_dir=selected.embedding_cache_dir,
            model_path=selected.embedding_model_path,
        )
    if provider == "openai":
        if not selected.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for the openai embedding provider")
        return OpenAIEmbedder(
            model_name=selected.embedding_model,
            dimensions=selected.embedding_dimensions,
            api_key=selected.openai_api_key,
            base_url=selected.openai_base_url,
        )
    raise ValueError(f"unsupported embedding provider: {selected.embedding_provider}")


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("向量维度不一致")
    return sum(a * b for a, b in zip(left, right, strict=True))
