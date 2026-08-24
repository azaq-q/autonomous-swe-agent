"""Retrieval dataset validation and aggregation tests."""

import json

import pytest

from app.evals.retrieval import RetrievalDataset, evaluate_retriever, load_dataset
from app.rag.retriever import CodeRetriever


def _dataset():
    return RetrievalDataset.model_validate(
        {
            "name": "test",
            "description": "test dataset",
            "files": {
                "a.py": "def alpha():\n    return 'apple'\n",
                "b.py": "def beta():\n    return 'banana'\n",
            },
            "cases": [
                {
                    "case_id": "case-1",
                    "query": "apple",
                    "relevant_sources": ["a.py"],
                }
            ],
        }
    )


def test_evaluate_retriever_reports_recall_and_mrr():
    dataset = _dataset()
    report = evaluate_retriever(
        dataset, CodeRetriever(dataset.files), index_seconds=0.01
    )

    assert report["metrics"]["recall_at_1"] == 1.0
    assert report["metrics"]["mrr"] == 1.0
    assert report["results"][0]["predicted_sources"][0] == "a.py"


def test_load_dataset_rejects_missing_relevant_source(tmp_path):
    payload = _dataset().model_dump()
    payload["cases"][0]["relevant_sources"] = ["missing.py"]
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="missing from corpus"):
        load_dataset(path)
