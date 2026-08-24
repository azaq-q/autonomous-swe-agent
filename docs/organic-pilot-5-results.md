# Organic pilot: 5 tasks × Full × seed 11

Run date: 2026-08-24

This pilot is a real-model, official-harness validation of the organic
SWE-bench Verified workflow. It is intentionally small: five tasks from five
repositories, one `full` run per task, and seed `11`. The selection contains
three multi-file and two single-file tasks.

## Outcome

| Instance | Generation | Official hidden evaluation | Duration | Conservative recorded cost |
| --- | --- | --- | ---: | ---: |
| `pallets__flask-5014` | public gate passed | resolved | 267.844 s | $0.401478 |
| `pylint-dev__pylint-4551` | timed out; no patch | not run | 1800.266 s | see timeout note |
| `pytest-dev__pytest-8399` | public gate passed | resolved | 401.032 s | $0.571549 |
| `sphinx-doc__sphinx-8593` | public gate passed | resolved | 649.406 s | $0.987648 |
| `sympy__sympy-20916` | public gate passed | unresolved | 595.281 s | $0.871983 |

Final result: **3/5 resolved (60%)**, with a 95% Wilson interval of
**23.07%–88.24%**. Workflow completion and public-gate pass rates were both
4/5 (80%). The final official cohort had no infrastructure failures, ambiguous
failures, empty patches, harness errors, or leftover containers.

The SymPy patch applied cleanly but failed the hidden `test_super_sub` case for
the mathematical Unicode digit `𝟙`. The Pylint task reached the configured
30-minute case timeout during an agent repair/test loop and produced no
submission for the hidden harness.

## Cost accounting

The benchmark report records 19,911,515 input and 160,877 output tokens for the
four completed workflows. At the configured cache-miss prices of $0.14/M input
and $0.28/M output, that is **$2.832658**.

The timed-out Pylint task is a known accounting gap in the batch report. Its API
record contains another 12,336,799 input and 204,543 output tokens, conservatively
estimated at **$1.784424**. Therefore the complete pilot consumed 32,248,314
recorded input and 365,420 output tokens:

- conservative cache-miss estimate: **$4.617082 total**, or **$1.539027 per
  resolved task**;
- all-input-cache-hit lower bound: **$0.192613 total**;
- actual billed cost is between these bounds because the current telemetry does
  not retain provider cache-hit token counts.

Prices were taken from the official DeepSeek pricing documentation on the run
date: $0.0028/M cache-hit input, $0.14/M cache-miss input, and $0.28/M output.

The most important cost finding is not the small cohort total, but the missing
in-flight per-task budget. One task used more than 12 million input tokens before
the wall-clock timeout. The batch budget also excludes a timed-out task because
its final token counters are not copied into the benchmark result.

## Environment validation

- model/provider: `deepseek-v4-flash` through `api.deepseek.com`;
- generation sandbox: project `LocalSandbox` inside the Celery worker;
- correctness sandbox: official `swebench==5.0.2` Docker harness;
- Docker Desktop 29.7.2, 16 CPUs, 7,105,228,800 bytes available memory,
  `overlayfs` storage driver;
- harness concurrency: one worker, 1,800-second per-instance timeout;
- dataset SHA-256:
  `c2b160bf0e5be0188035b525ae0fcaea09d338d961fdc87bdd921d6133f808bd`;
- source commit before pilot-specific changes:
  `1910ccc9fb118f1e3d5129253bbabac1cfc47d16`;
- final warm harness run: 4 minutes 16 seconds for four patches. Cold image
  acquisition was the dominant environment cost and one pull took about
  2 hours 52 minutes on this network;
- post-run Docker usage: 16.72 GB images and 10.51 GB build cache; D: retained
  about 99.3 GB free.

On Windows, the upstream harness writes `patch.diff` and `eval.sh` with CRLF by
default. The former makes `git apply` fall back, while the latter breaks Bash
commands inside the Linux evaluation container and creates false negatives.
The validated run used UTF-8 plus LF for both files. Prediction labels were also
changed from colon-separated values to cross-platform path-safe values because
the upstream harness uses the label as a directory and report filename.

## Reproducibility artifacts

- aggregate result: `backend/evals/results/deepseek-v4-flash-organic-pilot-5.json`;
- official prediction cohort:
  `backend/evals/predictions/organic-pilot-5/full-seed-11.jsonl`;
- official harness report:
  `backend/evals/harness/organic-pilot-5/deepseek-v4-flash--full--seed-11.organic-pilot-5-win-lf2-full-seed-11.json`.

This is a pilot, not a headline benchmark. Five tasks and one seed have a wide
confidence interval and cannot support a general model-quality claim. The next
credible step is to fix in-flight token budgets and timeout accounting, then run
the matched multi-seed protocol on a larger cohort.
