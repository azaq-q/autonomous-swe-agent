"""评测指标：用于量化检索效果。"""


def recall_at_k(predicted: list[str], relevant: list[str], k: int) -> float:
    """召回率@k：top-k 结果中命中的相关项占全部相关项的比例。"""
    if not relevant:
        return 0.0
    return len(set(predicted[:k]) & set(relevant)) / len(relevant)


def mrr(predicted: list[str], relevant: list[str]) -> float:
    """平均倒数排名（MRR）：首个相关项所在排名的倒数。"""
    rel = set(relevant)
    for i, p in enumerate(predicted):
        if p in rel:
            return 1.0 / (i + 1)
    return 0.0
