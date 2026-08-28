# Organic benchmark v1: credible evaluation protocol

## Status

The evaluation infrastructure and dataset are complete. A five-task `full`,
seed-11 pilot has been run through the official harness and resolved 3/5 tasks;
see [`organic-pilot-5-results.md`](organic-pilot-5-results.md). This small pilot
is an environment and cost validation, not the pending 360-run matched result.
Pending hidden-test runs are reported as `null`, never as failures or successes.

## Dataset

`organic-swebench-verified-v1` contains 30 engineer-validated GitHub issues
sampled from the official SWE-bench Verified test split at pinned base commits.
It spans 10 repositories, caps each repository at six tasks, and includes 15
tasks whose official fix changes multiple files.

| Property | Value |
| --- | ---: |
| Tasks | 30 |
| Repositories | 10 |
| Multi-file tasks | 15 |
| Maximum tasks per repository | 6 |
| Matched variants | 4 |
| Repeat seeds | 3 |
| Planned runs | 360 |

The committed manifest contains the issue text, provenance URL, base commit,
hidden-test identifiers, and SHA-256 of the official evaluation patch. It does
not contain the gold solution or test patch. The Agent receives only the issue
and a public `git diff --check` gate. Correctness is decided later by the
official SWE-bench harness, which applies its own tests outside the Agent loop.

Selection is deterministic (`seed=42`) and derived from the official dataset.
Gold patch contents are used only to count changed files for the declared
single-file/multi-file stratum, then discarded.

## Run plan

Start the API with a real model and an isolated sandbox, then run all matched
task/variant/seed combinations:

```powershell
cd backend
uv run python -m app.evals.benchmark `
  evals/datasets/organic-swebench-verified-v1.jsonl `
  --output evals/results/organic-v1-raw.json `
  --predictions-dir evals/predictions/organic-v1 `
  --model <model-name> `
  --variants full,single_agent,no_rag,no_review `
  --seeds 11,22,33 `
  --max-total-cost-usd <approved-budget> `
  --max-task-llm-calls 128 `
  --max-task-input-tokens 8000000 `
  --max-task-output-tokens 250000 `
  --max-task-cost-usd 2 `
  --resume
```

Task limits are enforced around every provider call, including calls inside the
Coding ReAct loop. Completed-call usage is persisted immediately. A wall-clock
timeout copies the live counters returned by task cancellation into the
benchmark result, so timed-out work contributes to the batch budget.

The runner produces one official predictions file per cohort, for example
`full-seed-11.jsonl`. Each row contains only `instance_id`, model identifier,
and the generated patch.

Evaluate every cohort with the official SWE-bench Docker harness:

```bash
python -m swebench.harness.run_evaluation \
  --dataset_name SWE-bench/SWE-bench_Verified \
  --split test \
  --predictions_path evals/predictions/organic-v1/full-seed-11.jsonl \
  --max_workers 4 \
  --run_id organic-v1-full-seed-11
```

After all cohort reports exist, import them without rerunning completed tasks:

```powershell
uv run python -m app.evals.benchmark `
  evals/datasets/organic-swebench-verified-v1.jsonl `
  --output evals/results/organic-v1-raw.json `
  --variants full,single_agent,no_rag,no_review `
  --seeds 11,22,33 --resume `
  --swebench-report "full:11=<official-report.json>" `
  --swebench-report "no_rag:11=<official-report.json>"
```

Repeat the report argument for all 12 cohorts. A report without a cohort is
accepted only when the result contains one unique variant/seed cohort, which
prevents one cohort's score from being copied to another.

## Statistics and anti-cherry-picking rules

- Resolution requires the official hidden harness, not the public smoke gate.
- Run-level rates include a 95% Wilson interval.
- Task-level rates and paired effects use a deterministic 2,000-sample bootstrap.
- Ablations use only the exact intersection of `(task_key, seed)` available for
  every variant; unmatched runs cannot enter the causal comparison.
- Reports retain task IDs, repository, seed, variant, patch digest, latency,
  token usage, cost, failure category, dataset hash, and harness report hashes.
- Resume is rejected if the dataset or complete run plan changes.

## Remaining limitation

SWE-bench Verified is substantially more credible than the previous synthetic
suite, but 30 selected tasks remain a subset. Results must be reported with
confidence intervals and the exact selection policy, not generalized to all
software-engineering work. Provider seed support also differs: the seed is sent
to OpenAI-compatible providers; providers without a seed API still receive
repeat labels but may remain nondeterministic.
