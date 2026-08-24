# Curated v1 benchmark report

> Run date: 2026-08-24 · Model: `deepseek-v4-flash` · Dataset SHA-256:
> `833dc2090955a71a06ec62c1ad3556b85a034db1b4d24985305ae34e1d41afa1`

## Executive summary

The full Planner → Coder → Tester → Reviewer workflow resolved **18 of 20
curated regression tasks (90%)**. Across the complete 35-run experiment,
including three matched ablations, 33 tasks reached the strict resolved state.
Every run produced a patch and passed its targeted test; two full-workflow runs
were rejected by Review because generated Python bytecode entered the patch.

The failure investigation led to a concrete reliability fix: sandbox Python
commands now disable bytecode output and each workspace locally ignores common
test byproducts. A pinned two-case post-fix verification resolved both previous
failures in one iteration each.

| Scope | Runs | Resolved | P50 | P95 | Input tokens | Output tokens | Estimated cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Full workflow | 20 | 18 (90%) | 47.492 s | 180.766 s | 1,640,753 | 147,336 | $0.270960 |
| All runs | 35 | 33 (94.29%) | 45.484 s | 180.766 s | 2,559,380 | 208,387 | $0.416662 |
| Post-fix verification | 2 | 2 (100%) | 65.836 s | 81.156 s | 137,627 | 10,275 | $0.022145 |

“Resolved” requires all three conditions: a terminal approval-ready state, a
zero test exit code, and a non-empty patch digest. Passing a test alone is not
counted as resolved.

## Methodology

The public source repository is
[`azaq-q/swe-agent-demo`](https://github.com/azaq-q/swe-agent-demo) at commit
`2fdc9ffb4d9565e80c9069ab484056c73384f2c3`. It contains 20 independent Python
defects and one isolated regression test per defect. All 20 tests fail at the
pinned source commit. Each task runs in a separate workspace and branch with an
exact test command and a maximum of three coding iterations.

The experiment contains 20 full-workflow runs and three five-case ablations.
Only full cases 03, 07, 11, 15, and 19 are compared with ablations; these are
tagged `ablation-anchor` in the dataset. Raw results contain task IDs, source
commit, patch SHA-256, status, test exit code, iterations, latency, token usage,
estimated cost, and failure category.

Cost uses the conservative cache-miss rates of **$0.14 per million input
tokens** and **$0.28 per million output tokens** from the
[official DeepSeek pricing documentation](https://api-docs.deepseek.com/quick_start/pricing/).
It is an estimate rather than a billing statement; cache hits can make actual
cost lower.

## Matched ablation results

| Variant | Workflow change | Resolved | P50 | P95 | Input tokens | Output tokens | Cost | Cost vs Full |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Full | Planner + RAG + Coder + Tester + Reviewer | 5/5 | 49.500 s | 86.890 s | 353,991 | 30,111 | $0.057990 | baseline |
| Single Agent | Skip Planner and Reviewer | 5/5 | 21.234 s | 32.359 s | 217,483 | 12,219 | $0.033869 | -41.6% |
| No RAG | Disable repository index and search tool | 5/5 | 51.531 s | 53.547 s | 257,755 | 24,479 | $0.042940 | -26.0% |
| No Review | Skip Reviewer | 5/5 | 42.437 s | 60.610 s | 443,389 | 24,353 | $0.068893 | +18.8% |

All variants solved the five localized tasks, so this sample shows efficiency
differences but no resolution-rate difference. Single Agent used 41.6% less
estimated cost and had a 57.1% lower P50 than Full. That does **not** establish
that a single agent is generally superior: file and function names were explicit
and the fixes were narrow. No RAG likewise cannot measure retrieval quality on
prompts that already identify the target symbol. The higher No Review input
usage also demonstrates model-run variance; five cases are too few for a strong
causal claim.

## Failure analysis and corrective action

| Case | Test | Patch | Iterations | Duration | Failure |
| --- | ---: | ---: | ---: | ---: | --- |
| `curated-02-divide` | pass | generated | 3 | 180.766 s | Review rejected generated `.pyc` plus over-broad changes |
| `curated-12-counts` | pass | generated | 3 | 279.782 s | Review rejected generated `.pyc` plus unnecessary scope |

The Reviewer correctly identified `benchmark/__pycache__/bugs.cpython-312.pyc`
as an invalid generated artifact. The workflow repeatedly asked the Coder to
address the review but did not prevent the next test from recreating the file,
so both tasks exhausted three iterations. Together they consumed $0.085030,
20.4% of the entire experiment cost, making artifact hygiene a measurable
reliability and cost issue.

Corrective changes:

1. Set `PYTHONDONTWRITEBYTECODE=1` for every local sandbox command.
2. Add `__pycache__/`, `*.py[cod]`, and `.pytest_cache/` to each workspace's
   private `.git/info/exclude`, without modifying the target repository.
3. Add regression tests for both sandbox execution and Git workspace status.
4. Add repeatable `--case-id` selection so targeted post-fix verification is
   recorded and reproducible.

The post-fix run used the original prompts, source commit, tests, model, and Full
workflow. Both cases resolved in one iteration, with no Review rejection.

## Reproduction and artifacts

- Dataset: [`backend/evals/datasets/curated-v1.jsonl`](../backend/evals/datasets/curated-v1.jsonl)
- Dataset notes: [`backend/evals/datasets/README.md`](../backend/evals/datasets/README.md)
- Raw 35-run result: [`deepseek-v4-flash-curated-v1.json`](../backend/evals/results/deepseek-v4-flash-curated-v1.json)
- Raw post-fix result: [`deepseek-v4-flash-curated-v1-post-fix.json`](../backend/evals/results/deepseek-v4-flash-curated-v1-post-fix.json)

```powershell
cd backend
uv run python -m app.evals.benchmark evals/datasets/curated-v1.jsonl `
  --output evals/results/deepseek-v4-flash-curated-v1.json `
  --model deepseek-v4-flash `
  --input-cost-per-million 0.14 `
  --output-cost-per-million 0.28 `
  --max-total-cost-usd 2 `
  --resume
```

## Limitations and next evaluation

This is a curated public regression suite, not SWE-bench and not a claim of
general autonomous software-engineering performance. The tasks are localized,
single-file, explicitly named, and tested narrowly. The next evaluation should
add multi-file defects from organic project history, hidden tests, prompts that
require repository navigation, at least 20 matched cases per ablation, repeated
seeds, and confidence intervals. Those additions are required before claiming
that RAG, Review, or multi-agent planning improves general task resolution.
