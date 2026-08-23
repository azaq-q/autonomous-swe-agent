"""代码检索单元测试。"""

from app.rag.retriever import CodeRetriever

FILES = {
    "auth.py": "def login(user, password):\n    return authenticate(user, password)\n",
    "payment.py": "def process_payment(amount):\n    return charge_card(amount)\n",
    "utils.py": "def helper():\n    return 42\n",
}


def test_index_and_search():
    r = CodeRetriever(FILES)
    results = r.search("user login authentication")
    assert results
    assert results[0]["source"] == "auth.py"
    assert results[0]["symbol"] == "def login"


def test_search_empty_query_returns_empty():
    r = CodeRetriever(FILES)
    results = r.search("zzzz_nonexistent")
    assert results == []


def test_search_top_k_limit():
    r = CodeRetriever(FILES)
    results = r.search("return", k=2)
    assert len(results) <= 2


class _SemanticEmbedder:
    def embed_documents(self, texts):
        return [[1.0, 0.0] if "password" in text else [0.0, 1.0] for text in texts]

    def embed_query(self, text):
        return [1.0, 0.0] if text == "credentials" else [0.0, 1.0]


def test_vector_recall_finds_semantic_candidate_without_keyword_overlap():
    retriever = CodeRetriever(FILES, embedder=_SemanticEmbedder())
    results = retriever.search("credentials")
    assert results[0]["source"] == "auth.py"
    assert results[0]["vector_score"] == 1.0


def test_optional_reranker_changes_candidate_order():
    retriever = CodeRetriever(
        FILES,
        reranker=lambda query, candidates: [
            1.0 if candidate["source"] == "utils.py" else 0.0 for candidate in candidates
        ],
    )
    results = retriever.search("return", k=3)
    assert results[0]["source"] == "utils.py"
