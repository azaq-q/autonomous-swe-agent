"""Run reproducible code-retrieval ablations over a fixed semantic dataset."""

import argparse
import hashlib
import json
import math
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.rag.embeddings import FastEmbedder, HashingEmbedder
from app.rag.eval import mrr, recall_at_k
from app.rag.retriever import CodeRetriever
from app.rag.store import PgVectorCodeIndex


class RetrievalCase(BaseModel):
    case_id: str = Field(pattern=r"^[a-zA-Z0-9._-]+$")
    query: str = Field(min_length=1)
    relevant_sources: list[str] = Field(min_length=1)


class RetrievalDataset(BaseModel):
    name: str
    description: str
    files: dict[str, str]
    cases: list[RetrievalCase] = Field(min_length=1)


def load_dataset(path: Path) -> RetrievalDataset:
    dataset = RetrievalDataset.model_validate_json(path.read_text(encoding="utf-8"))
    missing = {
        source
        for case in dataset.cases
        for source in case.relevant_sources
        if source not in dataset.files
    }
    if missing:
        raise ValueError(f"relevant sources missing from corpus: {', '.join(sorted(missing))}")
    case_ids = [case.case_id for case in dataset.cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("retrieval case IDs must be unique")
    return dataset


def evaluate_retriever(
    dataset: RetrievalDataset,
    retriever: CodeRetriever,
    *,
    index_seconds: float,
) -> dict:
    results = []
    latencies = []
    for case in dataset.cases:
        started = time.perf_counter()
        hits = retriever.search(case.query, k=5)
        latency_ms = (time.perf_counter() - started) * 1_000
        latencies.append(latency_ms)
        predicted = list(dict.fromkeys(hit["source"] for hit in hits))
        results.append(
            {
                "case_id": case.case_id,
                "query": case.query,
                "relevant_sources": case.relevant_sources,
                "predicted_sources": predicted,
                "recall_at_1": recall_at_k(predicted, case.relevant_sources, 1),
                "recall_at_3": recall_at_k(predicted, case.relevant_sources, 3),
                "recall_at_5": recall_at_k(predicted, case.relevant_sources, 5),
                "reciprocal_rank": mrr(predicted, case.relevant_sources),
                "latency_ms": round(latency_ms, 3),
            }
        )
    ordered = sorted(latencies)
    total = len(results)
    return {
        "metrics": {
            "total": total,
            "recall_at_1": round(
                statistics.fmean(result["recall_at_1"] for result in results), 4
            ),
            "recall_at_3": round(
                statistics.fmean(result["recall_at_3"] for result in results), 4
            ),
            "recall_at_5": round(
                statistics.fmean(result["recall_at_5"] for result in results), 4
            ),
            "mrr": round(
                statistics.fmean(result["reciprocal_rank"] for result in results), 4
            ),
            "index_seconds": round(index_seconds, 3),
            "query_p50_ms": round(statistics.median(ordered), 3),
            "query_p95_ms": round(ordered[math.ceil(total * 0.95) - 1], 3),
        },
        "results": results,
    }


def _build(files: dict[str, str], embedder=None) -> tuple[CodeRetriever, float]:
    started = time.perf_counter()
    retriever = CodeRetriever(files, embedder=embedder)
    return retriever, time.perf_counter() - started


def main() -> None:
    parser = argparse.ArgumentParser(description="Run semantic code retrieval ablations")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path, default=Path("retrieval-results.json"))
    parser.add_argument("--model", default="BAAI/bge-small-en")
    parser.add_argument("--dimensions", type=int, default=384)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--cache-dir", default="./.fastembed_cache")
    parser.add_argument("--model-path")
    parser.add_argument(
        "--database-url",
        help="also evaluate persistent pgvector search; the URL is never written to results",
    )
    args = parser.parse_args()

    dataset_bytes = args.dataset.read_bytes()
    dataset = load_dataset(args.dataset)
    neural_embedder = FastEmbedder(
        model_name=args.model,
        dimensions=args.dimensions,
        batch_size=args.batch_size,
        cache_dir=args.cache_dir,
        model_path=args.model_path,
    )
    variants = {
        "bm25": None,
        "hash_hybrid": HashingEmbedder(args.dimensions),
        "neural_hybrid": neural_embedder,
    }
    report = {}
    built_retrievers = {}
    for name, embedder in variants.items():
        retriever, index_seconds = _build(dataset.files, embedder)
        built_retrievers[name] = retriever
        report[name] = evaluate_retriever(
            dataset, retriever, index_seconds=index_seconds
        )
        print(f"{name}: {report[name]['metrics']}", flush=True)

    if args.database_url:
        engine = create_engine(args.database_url, pool_pre_ping=True)
        session_factory = sessionmaker(engine)
        store = PgVectorCodeIndex(session_factory)
        index_key = hashlib.sha256(
            f"retrieval-eval\0{dataset.name}\0{args.model}\0{args.dimensions}".encode()
        ).hexdigest()
        cached_chunks = store.load(index_key)
        cache_hit_before = bool(cached_chunks)
        neural = built_retrievers["neural_hybrid"]
        if not cached_chunks:
            store.replace(
                index_key=index_key,
                repository=f"eval:{dataset.name}",
                source_commit=hashlib.sha256(dataset_bytes).hexdigest(),
                content_digest=hashlib.sha256(dataset_bytes).hexdigest(),
                embedding_namespace=neural_embedder.namespace,
                chunks=neural.chunks,
                vectors=neural.vectors,
            )
            cached_chunks = store.load(index_key)
        persistent = CodeRetriever(
            chunks=cached_chunks,
            embedder=neural_embedder,
            vector_searcher=lambda vector, k: store.search(index_key, vector, k),
        )
        persistent_report = evaluate_retriever(
            dataset, persistent, index_seconds=0.0
        )
        persistent_report["cache"] = {
            "index_key": index_key,
            "hit_before_run": cache_hit_before,
            "hit_after_run": bool(store.load(index_key)),
            "stored_chunks": store.count(index_key),
        }
        report["pgvector_neural_hybrid"] = persistent_report
        print(
            f"pgvector_neural_hybrid: {persistent_report['metrics']}", flush=True
        )
        engine.dispose()

    payload = {
        "metadata": {
            "generated_at": datetime.now(UTC).isoformat(),
            "dataset": str(args.dataset),
            "dataset_sha256": hashlib.sha256(dataset_bytes).hexdigest(),
            "dataset_name": dataset.name,
            "model": args.model,
            "dimensions": args.dimensions,
        },
        "report": report,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
