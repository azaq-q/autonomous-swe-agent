"""混合检索：BM25 关键词检索，向量检索接口预留。"""

from app.rag.bm25 import BM25
from app.rag.chunker import chunk_code


class CodeRetriever:
    """代码语义检索器。

    当前实现基于 BM25 关键词检索；向量检索（pgvector + embeddings）
    作为后续扩展，可通过融合得分实现混合检索。
    """

    def __init__(self, files: dict[str, str] | None = None) -> None:
        """files: {文件路径: 源码内容}。"""
        self.chunks: list[dict] = []
        self.bm25: BM25 | None = None
        if files:
            self.index(files)

    def index(self, files: dict[str, str]) -> None:
        self.chunks = []
        for path, content in files.items():
            self.chunks.extend(chunk_code(content, source=path))
        self.bm25 = BM25([c["content"] for c in self.chunks])

    def search(self, query: str, k: int = 5) -> list[dict]:
        """返回 top-k 相关代码块（含来源、符号、得分）。"""
        if not self.chunks or self.bm25 is None:
            return []
        scores = self.bm25.score(query)
        ranked = sorted(range(len(self.chunks)), key=lambda i: scores[i], reverse=True)
        results = []
        for i in ranked:
            if scores[i] <= 0:
                break
            results.append({**self.chunks[i], "score": round(scores[i], 4)})
            if len(results) >= k:
                break
        return results
