# Phase 3: neural retrieval and pgvector report

> Run date: 2026-08-24 · Model: `BAAI/bge-small-en` · Dimensions: 384 ·
> Dataset SHA-256: `c4b5aa4504ed8ec90b6d8171a74caa7c40c2ec17c3281526f168476565267fb9`

## Outcome

Phase 3 replaces the in-memory hashing-only vector path with a configurable
retrieval stack while retaining the zero-download fallback:

- real local neural embeddings through [FastEmbed](https://github.com/qdrant/fastembed);
- optional OpenAI-compatible embeddings with an explicit vector dimension;
- persistent PostgreSQL storage and cosine search through
  [pgvector](https://github.com/pgvector/pgvector-python);
- content-addressed caching by repository, source commit, source digest, and
  embedding namespace;
- BM25 + vector reciprocal-rank fusion over either memory or pgvector;
- fixed semantic retrieval data, raw results, and an operational repository
  indexing CLI.

The default remains `hashing + memory`. Neural inference and pgvector are only
enabled through configuration, so a normal local checkout does not download a
model or require PostgreSQL.

## Retrieval ablation

The public `semantic-code-retrieval-v1` dataset contains 20 code files and 20
natural-language queries. Queries intentionally avoid direct target function
names. Every case has one relevant source file.

| Variant | Recall@1 | Recall@3 | Recall@5 | MRR | Index | Query P50 | Query P95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| BM25 | 0.25 | 0.30 | 0.30 | 0.2750 | 15 ms | 0.029 ms | 0.100 ms |
| Hash hybrid | 0.30 | 0.35 | 0.35 | 0.3250 | 3 ms | 0.621 ms | 0.918 ms |
| Neural hybrid, memory | **0.55** | **0.75** | **0.95** | **0.6917** | 264 ms | 9.980 ms | 12.774 ms |
| Neural hybrid, pgvector | **0.55** | **0.75** | **0.95** | **0.6917** | cache | 15.608 ms | 17.431 ms |

On this dataset, the neural hybrid improves Recall@1 by **30 percentage points**
(2.2×) and Recall@5 by **65 points** over BM25. MRR rises from 0.2750 to 0.6917.
The trade-off is explicit: in-memory neural query P50 is about 10 ms, and local
pgvector adds roughly 5.6 ms while providing persistence and shared-worker
access.

The pgvector run began with a cold cache, stored 20 chunks, and verified a cache
hit immediately afterward. The database URL is deliberately excluded from raw
result metadata.

## Real-repository smoke test

The operational indexer was also run against `backend/app/services` from this
repository:

- 16 AST code chunks persisted;
- first build: cache miss;
- second identical build: cache hit with no document re-embedding;
- query: “where is task token usage and estimated model cost recorded”;
- Top-1: `events.py::emit_task_event`, vector similarity **0.8758**.

This verifies the full path rather than only isolated components:

```text
source files → Tree-sitter chunks → BGE embeddings → pgvector/HNSW
             → cosine candidates → BM25/vector RRF → Agent search tool
```

## Persistence and invalidation

The `code_embedding` table stores chunk identity and metadata alongside
`vector(384)`. It has:

- a unique constraint on `(index_key, chunk_id)`;
- an `(index_key, position)` lookup index;
- an HNSW cosine index using `vector_cosine_ops`.

The index key hashes repository identity, fixed source commit, complete chunk
content digest, and embedding namespace. A code change, model change, provider
change, endpoint namespace change, or dimension change cannot silently reuse
stale vectors. PostgreSQL migration was verified with pgvector `0.8.6`; SQLite
still completes the entire migration chain for CI compatibility.

## Reliability finding

Dependency resolution after adding FastEmbed selected `tree-sitter 0.26.0`
while language grammars remained on `0.25.x`. Repeated real-file parsing exposed
a native ABI access violation that small parser fixtures missed. The core is now
pinned to `>=0.25,<0.26`, the `Language` wrapper is retained for the Parser
lifetime, and tests repeatedly parse real service files. This prevents a native
Worker crash before repository indexing.

## Configuration

```dotenv
DATABASE_URL=postgresql+psycopg://user:password@postgres:5432/database
EMBEDDING_PROVIDER=fastembed
EMBEDDING_MODEL=BAAI/bge-small-en
EMBEDDING_DIMENSIONS=384
EMBEDDING_BATCH_SIZE=64
EMBEDDING_CACHE_DIR=/data/embedding-cache
# Optional preloaded/offline model directory:
EMBEDDING_MODEL_PATH=/data/embedding-cache/fast-bge-small-en
RAG_VECTOR_STORE=pgvector
RAG_VECTOR_THRESHOLD=0.1
```

The model used here is the MIT-licensed 384-dimensional
[`BAAI/bge-small-en`](https://huggingface.co/BAAI/bge-small-en) registered by
FastEmbed. Model weights are not committed. Production workers should preload a
pinned model artifact and set `EMBEDDING_MODEL_PATH` rather than downloading on
startup.

## Reproduction

```powershell
cd backend

# Retrieval ablation (add --database-url for the pgvector variant)
uv run python -m app.evals.retrieval evals/retrieval/semantic-v1.json `
  --output evals/results/retrieval-bge-small-semantic-v1.json `
  --model BAAI/bge-small-en --dimensions 384 `
  --model-path ./.fastembed_cache/fast-bge-small-en

# Persistent repository smoke test
uv run python -m app.evals.index_repository app/services `
  --repository azaq-q/autonomous-swe-agent:services `
  --source-commit 7e8a081 `
  --database-url postgresql+psycopg://user:password@localhost:5432/database `
  --model-path ./.fastembed_cache/fast-bge-small-en
```

Artifacts:

- dataset: [`backend/evals/retrieval/semantic-v1.json`](../backend/evals/retrieval/semantic-v1.json)
- raw ablation result: [`retrieval-bge-small-semantic-v1.json`](../backend/evals/results/retrieval-bge-small-semantic-v1.json)
- raw repository smoke result: [`pgvector-services-smoke.json`](../backend/evals/results/pgvector-services-smoke.json)

## Limitations

This is a small curated semantic-retrieval suite, not a general code-search
benchmark. Files are short, each query has one relevant file, and there are no
large-repository or multilingual measurements. The result establishes that the
neural path adds semantic recall and that pgvector persistence works; it does
not prove the same uplift on arbitrary repositories. The next evaluation should
use organic multi-file issues, relevance judgments at chunk level, repeated
queries, larger corpora, and end-to-end task-resolution confidence intervals.
