"""评测指标单元测试。"""

from app.rag.eval import mrr, recall_at_k


def test_recall_at_k_full_hit():
    assert recall_at_k(["a", "b", "c"], ["a", "b"], 2) == 1.0


def test_recall_at_k_partial():
    assert recall_at_k(["a", "c"], ["a", "b"], 2) == 0.5


def test_recall_at_k_empty_relevant():
    assert recall_at_k(["a"], [], 1) == 0.0


def test_mrr_first_rank():
    assert mrr(["a", "b"], ["a"]) == 1.0


def test_mrr_second_rank():
    assert mrr(["x", "a"], ["a"]) == 0.5


def test_mrr_no_hit():
    assert mrr(["x", "y"], ["a"]) == 0.0
