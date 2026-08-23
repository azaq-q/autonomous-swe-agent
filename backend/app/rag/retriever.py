"""BM25/vector hybrid retrieval with reciprocal-rank fusion and optional reranking."""

from collections.abc import Callable

from app.rag.bm25 import BM25
from app.rag.chunker import chunk_code
from app.rag.embeddings import Embedder, cosine_similarity

Reranker = Callable[[str, list[dict]], list[float]]


class CodeRetriever:
    def __init__(
        self,
        files: dict[str, str] | None = None,
        embedder: Embedder | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        self.chunks: list[dict] = []
        self.bm25: BM25 | None = None
        self.embedder = embedder
        self.reranker = reranker
        self.vectors: list[list[float]] = []
        if files:
            self.index(files)

    def index(self, files: dict[str, str]) -> None:
        self.chunks = []
        for path, content in files.items():
            self.chunks.extend(chunk_code(content, source=path))
        documents = [self._document(chunk) for chunk in self.chunks]
        self.bm25 = BM25(documents)
        self.vectors = self.embedder.embed_documents(documents) if self.embedder else []

    def search(self, query: str, k: int = 5) -> list[dict]:
        if not query.strip() or not self.chunks or self.bm25 is None:
            return []
        lexical_scores = self.bm25.score(query)
        lexical_rank = [
            index
            for index in sorted(
                range(len(self.chunks)),
                key=lambda item: lexical_scores[item],
                reverse=True,
            )
            if lexical_scores[index] > 0
        ]

        vector_scores = [0.0] * len(self.chunks)
        vector_rank: list[int] = []
        if self.embedder and self.vectors:
            query_vector = self.embedder.embed_query(query)
            vector_scores = [cosine_similarity(query_vector, vector) for vector in self.vectors]
            vector_rank = [
                index
                for index in sorted(
                    range(len(self.chunks)),
                    key=lambda item: vector_scores[item],
                    reverse=True,
                )
                if vector_scores[index] > 0.1
            ]

        fused: dict[int, float] = {}
        for rank, index in enumerate(lexical_rank, 1):
            fused[index] = fused.get(index, 0.0) + 1 / (60 + rank)
        for rank, index in enumerate(vector_rank, 1):
            fused[index] = fused.get(index, 0.0) + 1 / (60 + rank)
        if not fused:
            return []

        candidate_ids = sorted(fused, key=fused.get, reverse=True)[: max(k * 4, k)]
        candidates = [
            {
                **self.chunks[index],
                "score": round(fused[index], 6),
                "bm25_score": round(lexical_scores[index], 4),
                "vector_score": round(vector_scores[index], 4),
            }
            for index in candidate_ids
        ]
        if self.reranker and candidates:
            rerank_scores = self.reranker(query, candidates)
            if len(rerank_scores) != len(candidates):
                raise ValueError("reranker 返回的分数数量不匹配")
            for candidate, score in zip(candidates, rerank_scores, strict=True):
                candidate["rerank_score"] = round(float(score), 6)
            candidates.sort(key=lambda item: item["rerank_score"], reverse=True)
        return candidates[:k]

    @staticmethod
    def _document(chunk: dict) -> str:
        return f"{chunk['source']}\n{chunk['symbol']}\n{chunk['content']}"
