"""轻量 BM25 关键词检索（无外部依赖）。"""

import math
import re
from collections import Counter

_TOKEN_RE = re.compile(r"\w+")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


class BM25:
    """标准 BM25 排序算法实现。"""

    def __init__(self, corpus: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.doc_tokens = [_tokenize(d) for d in corpus]
        self.doc_freqs = [Counter(t) for t in self.doc_tokens]
        self.doc_len = [len(t) for t in self.doc_tokens]
        self.n = len(self.doc_tokens)
        self.avgdl = sum(self.doc_len) / self.n if self.n else 0.0
        self.idf = self._compute_idf()

    def _compute_idf(self) -> dict[str, float]:
        df: Counter = Counter()
        for freq in self.doc_freqs:
            df.update(freq.keys())
        return {
            term: math.log((self.n - cnt + 0.5) / (cnt + 0.5) + 1)
            for term, cnt in df.items()
        }

    def score(self, query: str) -> list[float]:
        q_tokens = _tokenize(query)
        scores = []
        for i in range(self.n):
            s = 0.0
            dl = self.doc_len[i]
            for term in q_tokens:
                f = self.doc_freqs[i].get(term, 0)
                if f == 0:
                    continue
                idf = self.idf.get(term, 0.0)
                denom = f + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                s += idf * (f * (self.k1 + 1)) / denom
            scores.append(s)
        return scores
