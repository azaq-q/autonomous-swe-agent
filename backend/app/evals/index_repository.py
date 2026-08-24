"""Build and verify a persistent neural repository index from the command line."""

import argparse
import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.rag.context import build_repository_index
from app.rag.embeddings import FastEmbedder


def main() -> None:
    parser = argparse.ArgumentParser(description="Index a repository in pgvector")
    parser.add_argument("root", type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--model", default="BAAI/bge-small-en")
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--cache-dir", default="./.fastembed_cache")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument(
        "--query",
        default="where is task token usage and estimated model cost recorded",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    engine = create_engine(args.database_url, pool_pre_ping=True)
    session_factory = sessionmaker(engine)
    settings = Settings(
        database_url=args.database_url,
        embedding_provider="fastembed",
        embedding_model=args.model,
        embedding_dimensions=384,
        embedding_batch_size=args.batch_size,
        embedding_cache_dir=args.cache_dir,
        embedding_model_path=args.model_path,
        rag_vector_store="pgvector",
    )
    embedder = FastEmbedder(
        model_name=args.model,
        dimensions=384,
        batch_size=args.batch_size,
        cache_dir=args.cache_dir,
        model_path=args.model_path,
    )
    first = build_repository_index(
        args.root,
        repository=args.repository,
        source_commit=args.source_commit,
        settings=settings,
        embedder=embedder,
        session_factory=session_factory,
    )
    second = build_repository_index(
        args.root,
        repository=args.repository,
        source_commit=args.source_commit,
        settings=settings,
        embedder=embedder,
        session_factory=session_factory,
    )
    hits = second.search(args.query, k=3)
    result = {
        "repository": args.repository,
        "source_commit": args.source_commit,
        "chunks": len(second.chunks),
        "first_cache_hit": first.index_metadata["cache_hit"],
        "second_cache_hit": second.index_metadata["cache_hit"],
        "index_key": second.index_metadata["index_key"],
        "query": args.query,
        "top_hits": [
            {
                "source": hit["source"],
                "symbol": hit["symbol"],
                "score": hit["score"],
                "vector_score": hit["vector_score"],
            }
            for hit in hits
        ],
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    engine.dispose()


if __name__ == "__main__":
    main()
