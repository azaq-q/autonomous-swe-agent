"""Run pinned repository tasks and produce statistically honest benchmark reports."""

import argparse
import hashlib
import json
import math
import random
import re
import statistics
import time
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from app.models.task import ExperimentVariant

TERMINAL_STATUSES = {"awaiting_approval", "done", "failed", "cancelled"}


class BenchmarkCase(BaseModel):
    case_id: str = Field(pattern=r"^[a-zA-Z0-9._-]+$")
    task_key: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9._-]+$")
    repository: str
    source_commit: str = Field(pattern=r"^[a-fA-F0-9]{40,64}$")
    base_branch: str = "main"
    prompt: str
    test_command: str
    max_iterations: int = Field(default=3, ge=1, le=10)
    tags: list[str] = Field(default_factory=list)
    experiment_variant: ExperimentVariant = ExperimentVariant.FULL
    provenance: Literal[
        "curated", "organic", "swe-bench-lite", "swe-bench-verified"
    ] = "curated"
    source_url: str | None = None
    swebench_instance_id: str | None = None
    requires_hidden_evaluation: bool = False
    evaluation_patch_sha256: str | None = Field(
        default=None, pattern=r"^[a-fA-F0-9]{64}$"
    )
    fail_to_pass: list[str] = Field(default_factory=list)
    pass_to_pass: list[str] = Field(default_factory=list)
    gold_patch_file_count: int | None = Field(default=None, ge=1)
    task_scope: Literal["single_file", "multi_file"] | None = None

    @property
    def effective_task_key(self) -> str:
        return self.task_key or self.case_id


class BenchmarkResult(BaseModel):
    run_id: str = ""
    case_id: str
    task_key: str = ""
    seed: int = 0
    repository: str | None = None
    provenance: str = "curated"
    swebench_instance_id: str | None = None
    task_id: str | None = None
    status: str
    workflow_completed: bool = False
    resolved: bool
    public_test_exit_code: int | None = None
    test_exit_code: int | None = None  # compatibility with phase-2 artifacts
    hidden_evaluation: str = "not_required"
    patch_sha256: str | None = None
    model_patch: str | None = None
    iterations: int = 0
    duration_seconds: float
    error: str | None = None
    tags: list[str] = Field(default_factory=list)
    experiment_variant: str = ExperimentVariant.FULL.value
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    failure_category: str | None = None


class BenchmarkRunner:
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        client: httpx.Client | None = None,
        poll_interval: float = 1.0,
        timeout: float = 1_800,
        sleep: Callable[[float], None] = time.sleep,
        max_total_cost_usd: float | None = None,
    ) -> None:
        self.client = client or httpx.Client(base_url=base_url, timeout=30)
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.sleep = sleep
        self.max_total_cost_usd = max_total_cost_usd

    def run_case(
        self,
        case: BenchmarkCase,
        *,
        seed: int = 0,
        variant: ExperimentVariant | None = None,
    ) -> BenchmarkResult:
        selected_variant = variant or case.experiment_variant
        run_id = make_run_id(case, selected_variant, seed)
        started = time.monotonic()
        response = self.client.post(
            "/api/v1/tasks",
            json={
                "prompt": case.prompt,
                "repository": case.repository,
                "source_commit": case.source_commit,
                "base_branch": case.base_branch,
                "test_command": case.test_command,
                "max_iterations": case.max_iterations,
                "experiment_variant": selected_variant.value,
                "random_seed": seed,
            },
        )
        response.raise_for_status()
        task = response.json()
        task_id = task["task_id"]

        while task["status"] not in TERMINAL_STATUSES:
            if time.monotonic() - started >= self.timeout:
                self.client.post(f"/api/v1/tasks/{task_id}/cancel")
                return self._result(
                    case,
                    run_id=run_id,
                    seed=seed,
                    variant=selected_variant,
                    task_id=task_id,
                    status="timeout",
                    duration=time.monotonic() - started,
                    error="benchmark timeout",
                    failure_category="timeout",
                )
            self.sleep(self.poll_interval)
            response = self.client.get(f"/api/v1/tasks/{task_id}")
            response.raise_for_status()
            task = response.json()

        task_result = task.get("result") or {}
        public_exit_code = task_result.get("test_exit_code")
        patch_sha256 = task.get("artifact_sha256")
        error = task.get("error")
        model_patch = None
        if patch_sha256 and task.get("artifact_url"):
            patch_response = self.client.get(task["artifact_url"])
            patch_response.raise_for_status()
            model_patch = patch_response.text
        has_patch = bool(
            patch_sha256
            and (
                model_patch.strip()
                if task.get("artifact_url") and model_patch is not None
                else True
            )
        )
        workflow_completed = (
            task["status"] in {"awaiting_approval", "done"}
            and public_exit_code == 0
            and has_patch
        )
        hidden_state = (
            ("pending" if has_patch else "failed")
            if case.requires_hidden_evaluation
            else "not_required"
        )
        resolved = workflow_completed and hidden_state == "not_required"
        failure_category = _classify_failure(
            resolved=resolved,
            workflow_completed=workflow_completed,
            hidden_evaluation=hidden_state,
            status=task["status"],
            test_exit_code=public_exit_code,
            patch_sha256=patch_sha256 if has_patch else None,
            error=error,
        )
        return self._result(
            case,
            run_id=run_id,
            seed=seed,
            variant=selected_variant,
            task_id=task_id,
            status=task["status"],
            workflow_completed=workflow_completed,
            resolved=resolved,
            public_test_exit_code=public_exit_code,
            hidden_evaluation=hidden_state,
            patch_sha256=patch_sha256,
            model_patch=model_patch,
            iterations=int(task_result.get("iterations") or 0),
            duration=time.monotonic() - started,
            error=error,
            input_tokens=int(task.get("input_tokens") or 0),
            output_tokens=int(task.get("output_tokens") or 0),
            estimated_cost_usd=float(task.get("estimated_cost_usd") or 0),
            failure_category=failure_category,
        )

    @staticmethod
    def _result(
        case: BenchmarkCase,
        *,
        run_id: str,
        seed: int,
        variant: ExperimentVariant,
        status: str,
        duration: float,
        task_id: str | None = None,
        workflow_completed: bool = False,
        resolved: bool = False,
        public_test_exit_code: int | None = None,
        hidden_evaluation: str = "not_required",
        patch_sha256: str | None = None,
        model_patch: str | None = None,
        iterations: int = 0,
        error: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        estimated_cost_usd: float = 0.0,
        failure_category: str | None = None,
    ) -> BenchmarkResult:
        return BenchmarkResult(
            run_id=run_id,
            case_id=case.case_id,
            task_key=case.effective_task_key,
            seed=seed,
            repository=case.repository,
            provenance=case.provenance,
            swebench_instance_id=case.swebench_instance_id,
            task_id=task_id,
            status=status,
            workflow_completed=workflow_completed,
            resolved=resolved,
            public_test_exit_code=public_test_exit_code,
            test_exit_code=public_test_exit_code,
            hidden_evaluation=hidden_evaluation,
            patch_sha256=patch_sha256,
            model_patch=model_patch,
            iterations=iterations,
            duration_seconds=round(duration, 3),
            error=error,
            tags=case.tags,
            experiment_variant=variant.value,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=round(estimated_cost_usd, 8),
            failure_category=failure_category,
        )

    def run(self, cases: Iterable[BenchmarkCase]) -> list[BenchmarkResult]:
        results = []
        for case in cases:
            spent = sum(result.estimated_cost_usd for result in results)
            if self.max_total_cost_usd is not None and spent >= self.max_total_cost_usd:
                raise RuntimeError(
                    f"benchmark cost budget exhausted: ${spent:.6f} >= "
                    f"${self.max_total_cost_usd:.6f}"
                )
            results.append(self.run_case(case))
        return results


def make_run_id(case: BenchmarkCase, variant: ExperimentVariant, seed: int) -> str:
    return f"{case.case_id}::{variant.value}::seed-{seed}"


def expand_runs(
    cases: Sequence[BenchmarkCase],
    *,
    seeds: Sequence[int],
    variants: Sequence[ExperimentVariant] | None,
) -> list[tuple[BenchmarkCase, ExperimentVariant, int]]:
    runs: list[tuple[BenchmarkCase, ExperimentVariant, int]] = []
    seen: set[str] = set()
    for case in cases:
        for variant in variants or [case.experiment_variant]:
            for seed in seeds:
                run_id = make_run_id(case, variant, seed)
                if run_id in seen:
                    raise ValueError(f"benchmark run duplicated: {run_id}")
                seen.add(run_id)
                runs.append((case, variant, seed))
    return runs


def _classify_failure(
    *,
    resolved: bool,
    workflow_completed: bool,
    hidden_evaluation: str,
    status: str,
    test_exit_code: int | None,
    patch_sha256: str | None,
    error: str | None,
) -> str | None:
    if resolved:
        return None
    if hidden_evaluation == "pending" and patch_sha256:
        return "pending_hidden_evaluation"
    if status == "timeout":
        return "timeout"
    message = (error or "").lower()
    if any(word in message for word in ("clone", "workspace", "仓库", "工作目录")):
        return "repository_setup"
    if test_exit_code not in (None, 0):
        return "public_test_failure"
    if not patch_sha256:
        return "no_patch"
    if hidden_evaluation == "failed":
        return "hidden_test_failure"
    if not workflow_completed and "review" in message:
        return "review_rejected"
    return "workflow_failure"


def load_cases(path: Path) -> list[BenchmarkCase]:
    cases = []
    seen_ids: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            case = BenchmarkCase.model_validate_json(line)
        except ValueError as exc:
            raise ValueError(f"数据集第 {line_number} 行无效：{exc}") from exc
        if case.case_id in seen_ids:
            raise ValueError(f"数据集 case_id 重复：{case.case_id}")
        if case.requires_hidden_evaluation and not case.swebench_instance_id:
            raise ValueError(
                f"数据集第 {line_number} 行需要隐藏评测但缺少 swebench_instance_id"
            )
        seen_ids.add(case.case_id)
        cases.append(case)
    if not cases:
        raise ValueError("评测集不能为空")
    return cases


def _wilson_interval(successes: int, total: int, z: float = 1.959964) -> list[float]:
    if total <= 0:
        return [0.0, 0.0]
    rate = successes / total
    denominator = 1 + z**2 / total
    centre = rate + z**2 / (2 * total)
    margin = z * math.sqrt(rate * (1 - rate) / total + z**2 / (4 * total**2))
    return [
        round(max(0.0, (centre - margin) / denominator), 4),
        round(min(1.0, (centre + margin) / denominator), 4),
    ]


def _bootstrap_mean_ci(values: Sequence[float], samples: int = 2_000) -> list[float]:
    if not values:
        return [0.0, 0.0]
    if len(values) == 1:
        value = round(float(values[0]), 4)
        return [value, value]
    rng = random.Random(0)
    means = sorted(
        statistics.fmean(rng.choice(values) for _ in values) for _ in range(samples)
    )
    return [
        round(means[math.floor(samples * 0.025)], 4),
        round(means[math.ceil(samples * 0.975) - 1], 4),
    ]


def _summarize(results: list[BenchmarkResult]) -> dict:
    if not results:
        raise ValueError("评测结果不能为空")
    durations = sorted(result.duration_seconds for result in results)
    statuses: dict[str, int] = defaultdict(int)
    failures: dict[str, int] = defaultdict(int)
    hidden_states: dict[str, int] = defaultdict(int)
    task_rates: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for result in results:
        statuses[result.status] += 1
        hidden_states[result.hidden_evaluation] += 1
        if result.failure_category:
            failures[result.failure_category] += 1
        if result.hidden_evaluation != "pending":
            task_rates[(result.task_key or result.case_id, result.experiment_variant)].append(
                result.resolved
            )
    total = len(results)
    finalized = [result for result in results if result.hidden_evaluation != "pending"]
    finalized_total = len(finalized)
    resolved = sum(result.resolved for result in finalized)
    completed = sum(result.workflow_completed for result in results)
    per_task_rates = [statistics.fmean(values) for values in task_rates.values()]
    return {
        "total": total,
        "total_runs": total,
        "unique_tasks": len({result.task_key or result.case_id for result in results}),
        "seeds": sorted({result.seed for result in results}),
        "resolution_finalized_runs": finalized_total,
        "pending_hidden_runs": total - finalized_total,
        "resolved": resolved,
        "resolved_rate": round(resolved / finalized_total, 4) if finalized_total else None,
        "resolved_rate_ci95_wilson": (
            _wilson_interval(resolved, finalized_total) if finalized_total else None
        ),
        "task_mean_resolved_rate": (
            round(statistics.fmean(per_task_rates), 4) if per_task_rates else None
        ),
        "task_mean_resolved_rate_ci95_bootstrap": (
            _bootstrap_mean_ci(per_task_rates) if per_task_rates else None
        ),
        "workflow_completed": completed,
        "workflow_completion_rate": round(completed / total, 4),
        "public_test_pass_rate": round(
            sum(result.public_test_exit_code == 0 for result in results) / total, 4
        ),
        "test_pass_rate": round(
            sum(
                (
                    result.public_test_exit_code
                    if result.public_test_exit_code is not None
                    else result.test_exit_code
                )
                == 0
                for result in results
            )
            / total,
            4,
        ),
        "patch_rate": round(sum(bool(result.patch_sha256) for result in results) / total, 4),
        "average_iterations": round(
            statistics.fmean(result.iterations for result in results), 3
        ),
        "duration_p50_seconds": round(statistics.median(durations), 3),
        "duration_p95_seconds": round(durations[math.ceil(total * 0.95) - 1], 3),
        "statuses": dict(statuses),
        "hidden_evaluation_states": dict(hidden_states),
        "failure_categories": dict(failures),
        "input_tokens": sum(result.input_tokens for result in results),
        "output_tokens": sum(result.output_tokens for result in results),
        "estimated_cost_usd": round(sum(r.estimated_cost_usd for r in results), 6),
    }


def _strict_matched_results(
    results: Sequence[BenchmarkResult],
) -> tuple[dict[str, list[BenchmarkResult]], set[tuple[str, int]]]:
    grouped: dict[str, dict[tuple[str, int], BenchmarkResult]] = defaultdict(dict)
    for result in results:
        if result.hidden_evaluation == "pending":
            continue
        grouped[result.experiment_variant][
            (result.task_key or result.case_id, result.seed)
        ] = result
    if len(grouped) < 2:
        return {}, set()
    matched_keys = set.intersection(*(set(group) for group in grouped.values()))
    if not matched_keys:
        return {}, set()
    return {
        variant: [items[key] for key in sorted(matched_keys)]
        for variant, items in sorted(grouped.items())
    }, matched_keys


def _paired_effects(
    matched: dict[str, list[BenchmarkResult]],
    matched_keys: set[tuple[str, int]],
) -> dict[str, dict]:
    baseline = matched.get(ExperimentVariant.FULL.value)
    if not baseline:
        return {}
    baseline_by_key = {
        (r.task_key or r.case_id, r.seed): r for r in baseline
    }
    effects = {}
    for variant, variant_results in matched.items():
        if variant == ExperimentVariant.FULL.value:
            continue
        variant_by_key = {
            (r.task_key or r.case_id, r.seed): r for r in variant_results
        }
        differences = [
            float(variant_by_key[key].resolved) - float(baseline_by_key[key].resolved)
            for key in sorted(matched_keys)
        ]
        effects[variant] = {
            "matched_runs": len(differences),
            "resolved_rate_difference_vs_full": round(statistics.fmean(differences), 4),
            "difference_ci95_cluster_bootstrap": _bootstrap_mean_ci(differences),
            "wins": sum(value > 0 for value in differences),
            "ties": sum(value == 0 for value in differences),
            "losses": sum(value < 0 for value in differences),
        }
    return effects


def build_report(results: list[BenchmarkResult]) -> dict:
    if not results:
        raise ValueError("评测结果不能为空")
    grouped: dict[str, list[BenchmarkResult]] = defaultdict(list)
    repositories: dict[str, int] = defaultdict(int)
    for result in results:
        grouped[result.experiment_variant].append(result)
        if result.repository:
            repositories[result.repository] += 1
    matched, matched_keys = _strict_matched_results(results)
    return {
        **_summarize(results),
        "repositories": dict(sorted(repositories.items())),
        "by_variant": {
            variant: _summarize(items) for variant, items in sorted(grouped.items())
        },
        "matched_ablation": {
            "matched_task_seed_pairs": len(matched_keys),
            "by_variant": {
                variant: _summarize(items) for variant, items in matched.items()
            },
            "paired_effects": _paired_effects(matched, matched_keys),
        },
    }


def _extract_id_set(payload: object, keys: set[str]) -> set[str]:
    found: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key.lower() in keys and isinstance(value, list):
                found.update(str(item) for item in value)
            else:
                found.update(_extract_id_set(value, keys))
    elif isinstance(payload, list):
        for value in payload:
            found.update(_extract_id_set(value, keys))
    return found


def apply_swebench_report(
    results: list[BenchmarkResult],
    report_payload: object,
    *,
    variant: str | None = None,
    seed: int | None = None,
) -> list[BenchmarkResult]:
    resolved_ids = _extract_id_set(
        report_payload, {"resolved_ids", "resolved", "instances_resolved"}
    )
    unresolved_ids = _extract_id_set(
        report_payload,
        {
            "unresolved_ids",
            "unresolved",
            "error_ids",
            "instances_unresolved",
            "empty_patch_ids",
        },
    )
    evaluated_ids = resolved_ids | unresolved_ids
    if not evaluated_ids:
        raise ValueError("SWE-bench report contains no evaluated instance IDs")
    matching_cohorts = {
        (result.experiment_variant, result.seed)
        for result in results
        if result.swebench_instance_id in evaluated_ids
    }
    if variant is None and seed is None and len(matching_cohorts) > 1:
        raise ValueError("SWE-bench report must select a variant/seed cohort")
    updated = []
    for result in results:
        instance_id = result.swebench_instance_id
        selected = (variant is None or result.experiment_variant == variant) and (
            seed is None or result.seed == seed
        )
        if not selected or not instance_id or instance_id not in evaluated_ids:
            updated.append(result)
            continue
        passed = instance_id in resolved_ids
        updated.append(
            result.model_copy(
                update={
                    "hidden_evaluation": "passed" if passed else "failed",
                    "resolved": passed,
                    "failure_category": None if passed else "hidden_test_failure",
                }
            )
        )
    return updated


def _safe_harness_label(model: str, variant: str, seed: int) -> str:
    """Return a label safe for harness-created paths on Windows and POSIX."""
    label = f"{model}--{variant}--seed-{seed}"
    return re.sub(r"[^A-Za-z0-9._-]+", "-", label).strip(".-") or "model"


def _write_predictions(directory: Path, results: Sequence[BenchmarkResult], model: str) -> None:
    cohorts: dict[tuple[str, int], list[BenchmarkResult]] = defaultdict(list)
    for result in results:
        if result.swebench_instance_id and result.model_patch is not None:
            cohorts[(result.experiment_variant, result.seed)].append(result)
    directory.mkdir(parents=True, exist_ok=True)
    for (variant, seed), cohort in cohorts.items():
        target = directory / f"{variant}-seed-{seed}.jsonl"
        rows = [
            {
                "instance_id": result.swebench_instance_id,
                "model_name_or_path": _safe_harness_label(model, variant, seed),
                "model_patch": result.model_patch,
            }
            for result in sorted(cohort, key=lambda item: item.swebench_instance_id or "")
        ]
        target.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )


def _write_payload(output: Path, *, metadata: dict, results: list[BenchmarkResult]) -> None:
    payload = {
        "metadata": metadata,
        "report": build_report(results),
        "results": [result.model_dump() for result in results],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_seeds(raw: str) -> list[int]:
    try:
        seeds = [int(value.strip()) for value in raw.split(",") if value.strip()]
    except ValueError as exc:
        raise ValueError("--seeds must be a comma-separated list of integers") from exc
    if not seeds or len(seeds) != len(set(seeds)):
        raise ValueError("--seeds must contain unique integers")
    return seeds


def _parse_variants(raw: str | None) -> list[ExperimentVariant] | None:
    if not raw:
        return None
    variants = [ExperimentVariant(value.strip()) for value in raw.split(",") if value.strip()]
    if not variants or len(variants) != len(set(variants)):
        raise ValueError("--variants must contain unique experiment variants")
    return variants


def _parse_swebench_report_spec(raw: str) -> tuple[str | None, int | None, Path]:
    if "=" not in raw:
        return None, None, Path(raw)
    cohort, raw_path = raw.split("=", 1)
    try:
        variant, raw_seed = cohort.split(":", 1)
        ExperimentVariant(variant)
        seed = int(raw_seed)
    except (ValueError, TypeError) as exc:
        raise ValueError(
            "--swebench-report must be PATH or VARIANT:SEED=PATH"
        ) from exc
    return variant, seed, Path(raw_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Autonomous SWE Agent benchmark")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--output", type=Path, default=Path("benchmark-results.json"))
    parser.add_argument("--model", default="unknown")
    parser.add_argument("--max-total-cost-usd", type=float)
    parser.add_argument("--input-cost-per-million", type=float, default=0.0)
    parser.add_argument("--output-cost-per-million", type=float, default=0.0)
    parser.add_argument("--seeds", default="0", help="comma-separated repeat seeds")
    parser.add_argument("--variants", help="comma-separated matched variants")
    parser.add_argument("--predictions-dir", type=Path)
    parser.add_argument(
        "--swebench-report",
        action="append",
        help="official report: PATH or repeat VARIANT:SEED=PATH for multiple cohorts",
    )
    parser.add_argument("--case-id", action="append")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    dataset_bytes = args.dataset.read_bytes()
    all_cases = load_cases(args.dataset)
    selected_ids = set(args.case_id or [])
    if selected_ids:
        known_ids = {case.case_id for case in all_cases}
        unknown_ids = selected_ids - known_ids
        if unknown_ids:
            raise ValueError(f"unknown case IDs: {', '.join(sorted(unknown_ids))}")
        all_cases = [case for case in all_cases if case.case_id in selected_ids]
    seeds = _parse_seeds(args.seeds)
    variants = _parse_variants(args.variants)
    runs = expand_runs(all_cases, seeds=seeds, variants=variants)
    run_plan = [make_run_id(case, variant, seed) for case, variant, seed in runs]
    metadata = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": str(args.dataset),
        "dataset_sha256": hashlib.sha256(dataset_bytes).hexdigest(),
        "model": args.model,
        "input_cost_per_million": args.input_cost_per_million,
        "output_cost_per_million": args.output_cost_per_million,
        "selected_case_ids": [case.case_id for case in all_cases],
        "seeds": seeds,
        "variants": [variant.value for variant in variants] if variants else None,
        "run_plan": run_plan,
        "confidence_interval_method": {
            "run_rate": "Wilson score, 95%",
            "task_rate": "deterministic task bootstrap, 2000 samples",
            "paired_effect": "deterministic matched-pair bootstrap, 2000 samples",
        },
    }
    results: list[BenchmarkResult] = []
    if args.resume and args.output.exists():
        previous = json.loads(args.output.read_text(encoding="utf-8"))
        previous_metadata = previous.get("metadata", {})
        if previous_metadata.get("dataset_sha256") != metadata["dataset_sha256"]:
            raise ValueError("cannot resume: benchmark dataset has changed")
        if previous_metadata.get("run_plan") != metadata["run_plan"]:
            raise ValueError("cannot resume: benchmark run plan has changed")
        results = [BenchmarkResult.model_validate(item) for item in previous["results"]]

    completed = {result.run_id for result in results}
    runner = BenchmarkRunner(base_url=args.base_url, max_total_cost_usd=args.max_total_cost_usd)
    for case, variant, seed in runs:
        run_id = make_run_id(case, variant, seed)
        if run_id in completed:
            continue
        spent = sum(result.estimated_cost_usd for result in results)
        if args.max_total_cost_usd is not None and spent >= args.max_total_cost_usd:
            raise RuntimeError(
                f"benchmark cost budget exhausted: ${spent:.6f} >= "
                f"${args.max_total_cost_usd:.6f}"
            )
        results.append(runner.run_case(case, seed=seed, variant=variant))
        _write_payload(args.output, metadata=metadata, results=results)
        if args.predictions_dir:
            _write_predictions(args.predictions_dir, results, args.model)
        print(f"[{len(results)}] {run_id}: {results[-1].status}", flush=True)
    if not results:
        raise ValueError("评测结果不能为空")
    if args.swebench_report:
        report_metadata = []
        for raw_spec in args.swebench_report:
            report_variant, report_seed, report_path = _parse_swebench_report_spec(
                raw_spec
            )
            report_bytes = report_path.read_bytes()
            results = apply_swebench_report(
                results,
                json.loads(report_bytes),
                variant=report_variant,
                seed=report_seed,
            )
            report_metadata.append(
                {
                    "path": str(report_path),
                    "variant": report_variant,
                    "seed": report_seed,
                    "sha256": hashlib.sha256(report_bytes).hexdigest(),
                }
            )
        metadata["swebench_reports"] = report_metadata
    _write_payload(args.output, metadata=metadata, results=results)
    if args.predictions_dir:
        _write_predictions(args.predictions_dir, results, args.model)
    print(json.dumps(build_report(results), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
