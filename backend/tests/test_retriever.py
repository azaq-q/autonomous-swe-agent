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
