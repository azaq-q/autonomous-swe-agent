# Curated benchmark datasets

## `curated-v1.jsonl`

`curated-v1` is a public, reproducible regression benchmark for the project's
end-to-end workflow. Every case targets
[`azaq-q/swe-agent-demo`](https://github.com/azaq-q/swe-agent-demo) at the same
pinned source commit:

```text
2fdc9ffb4d9565e80c9069ab484056c73384f2c3
```

The source commit contains 20 independent Python defects and one isolated
regression test per defect. All 20 tests fail before an agent change. The
dataset runs:

- 20 tasks with the full Planner → Coder → Tester → Reviewer workflow;
- the same five representative tasks with `single_agent`, `no_rag`, and
  `no_review` variants (15 additional runs);
- exact per-case test commands with no third-party runtime dependencies.

The five full-workflow rows tagged `ablation-anchor` are the only full rows
used for matched ablation comparisons. This prevents comparing a 20-case group
with a different 5-case group.

Run from `backend/`:

```bash
uv run python -m app.evals.benchmark evals/datasets/curated-v1.jsonl \
  --output evals/results/curated-v1.json \
  --model <model-name> \
  --max-total-cost-usd 2 \
  --resume
```

Use repeatable `--case-id <id>` options for a reproducible subset or post-fix
verification run. Selected IDs are recorded in result metadata.

The runner records a SHA-256 digest of the dataset, source commit, task IDs,
patch digests, tests, latency, token usage, estimated cost, and categorized
failures. `--resume` verifies the dataset digest and skips completed case IDs.

### Scope and limitations

This is a deliberately small curated benchmark, not SWE-bench and not a claim
of general software-engineering performance. Its defects are localized and its
tests are narrow. It is useful for reproducibility, workflow regression, and
controlled ablations; broader multi-file and real-world repository tasks remain
future evaluation work.

## `organic-swebench-verified-v1.jsonl`

This is the credibility-focused successor to `curated-v1`: 30 deterministic
samples from the official SWE-bench Verified test split, covering 10 real
repositories with at least 15 multi-file fixes and no more than six tasks from
one repository. The manifest excludes both the gold patch and the hidden test
patch. See [`docs/organic-benchmark-v1.md`](../../../docs/organic-benchmark-v1.md)
for the 360-run matched protocol, hidden-harness workflow, and statistical rules.

Regenerate it from the official dataset server:

```bash
uv run python -m app.evals.import_swebench \
  --output evals/datasets/organic-swebench-verified-v1.jsonl \
  --size 30 --seed 42 --max-per-repository 6 --min-multifile 15
```
