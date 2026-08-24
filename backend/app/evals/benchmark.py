"""Run pinned repository tasks through the public API and aggregate outcomes."""

import argparse
import hashlib
import json
import math
import statistics
import time
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path

import httpx
from pydantic import BaseModel, Field

from app.models.task import ExperimentVariant

TERMINAL_STATUSES = {"awaiting_approval", "done", "failed", "cancelled"}


class BenchmarkCase(BaseModel):
    case_id: str = Field(pattern=r"^[a-zA-Z0-9._-]+$")
    repository: str
    source_commit: str = Field(pattern=r"^[a-fA-F0-9]{40,64}$")
    base_branch: str = "main"
    prompt: str
    test_command: str
    max_iterations: int = Field(default=3, ge=1, le=10)
    tags: list[str] = Field(default_factory=list)
    experiment_variant: ExperimentVariant = ExperimentVariant.FULL


class BenchmarkResult(BaseModel):
    case_id: str
    task_id: str | None = None
    status: str
    resolved: bool
    test_exit_code: int | None = None
    patch_sha256: str | None = None
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

    def run_case(self, case: BenchmarkCase) -> BenchmarkResult:
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
                "experiment_variant": case.experiment_variant.value,
            },
        )
        response.raise_for_status()
        task = response.json()
        task_id = task["task_id"]

        while task["status"] not in TERMINAL_STATUSES:
            if time.monotonic() - started >= self.timeout:
                self.client.post(f"/api/v1/tasks/{task_id}/cancel")
                return BenchmarkResult(
                    case_id=case.case_id,
                    task_id=task_id,
                    status="timeout",
                    resolved=False,
                    duration_seconds=round(time.monotonic() - started, 3),
                    error="benchmark timeout",
                    tags=case.tags,
                    experiment_variant=case.experiment_variant.value,
                    failure_category="timeout",
                )
            self.sleep(self.poll_interval)
            response = self.client.get(f"/api/v1/tasks/{task_id}")
            response.raise_for_status()
            task = response.json()

        result = task.get("result") or {}
        test_exit_code = result.get("test_exit_code")
        patch_sha256 = task.get("artifact_sha256")
        resolved = (
            task["status"] in {"awaiting_approval", "done"}
            and test_exit_code == 0
            and bool(patch_sha256)
        )
        error = task.get("error")
        return BenchmarkResult(
            case_id=case.case_id,
            task_id=task_id,
            status=task["status"],
            resolved=resolved,
            test_exit_code=test_exit_code,
            patch_sha256=patch_sha256,
            iterations=int(result.get("iterations") or 0),
            duration_seconds=round(time.monotonic() - started, 3),
            error=error,
            tags=case.tags,
            experiment_variant=case.experiment_variant.value,
            input_tokens=int(task.get("input_tokens") or 0),
            output_tokens=int(task.get("output_tokens") or 0),
            estimated_cost_usd=round(float(task.get("estimated_cost_usd") or 0), 8),
            failure_category=_classify_failure(
                resolved=resolved,
                status=task["status"],
                test_exit_code=test_exit_code,
                patch_sha256=patch_sha256,
                error=error,
            ),
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


def _classify_failure(
    *,
    resolved: bool,
    status: str,
    test_exit_code: int | None,
    patch_sha256: str | None,
    error: str | None,
) -> str | None:
    if resolved:
        return None
    if status == "timeout":
        return "timeout"
    message = (error or "").lower()
    if any(word in message for word in ("clone", "workspace", "仓库", "工作目录")):
        return "repository_setup"
    if test_exit_code not in (None, 0):
        return "test_failure"
    if not patch_sha256:
        return "no_patch"
    if "review" in message.lower():
        return "review_rejected"
    return "workflow_failure"


def load_cases(path: Path) -> list[BenchmarkCase]:
    cases = []
    seen_ids: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                case = BenchmarkCase.model_validate_json(line)
            except ValueError as exc:
                raise ValueError(f"数据集第 {line_number} 行无效：{exc}") from exc
            if case.case_id in seen_ids:
                raise ValueError(f"数据集 case_id 重复：{case.case_id}")
            seen_ids.add(case.case_id)
            cases.append(case)
    if not cases:
        raise ValueError("评测集不能为空")
    return cases


def _summarize(results: list[BenchmarkResult]) -> dict:
    if not results:
        raise ValueError("评测结果不能为空")
    durations = sorted(result.duration_seconds for result in results)
    statuses: dict[str, int] = {}
    failures: dict[str, int] = {}
    for result in results:
        statuses[result.status] = statuses.get(result.status, 0) + 1
        if result.failure_category:
            failures[result.failure_category] = failures.get(result.failure_category, 0) + 1
    total = len(results)
    return {
        "total": total,
        "resolved": sum(result.resolved for result in results),
        "resolved_rate": round(sum(result.resolved for result in results) / total, 4),
        "test_pass_rate": round(
            sum(result.test_exit_code == 0 for result in results) / total, 4
        ),
        "patch_rate": round(sum(bool(result.patch_sha256) for result in results) / total, 4),
        "average_iterations": round(
            statistics.fmean(result.iterations for result in results), 3
        ),
        "duration_p50_seconds": round(statistics.median(durations), 3),
        "duration_p95_seconds": round(durations[math.ceil(total * 0.95) - 1], 3),
        "statuses": statuses,
        "failure_categories": failures,
        "input_tokens": sum(result.input_tokens for result in results),
        "output_tokens": sum(result.output_tokens for result in results),
        "estimated_cost_usd": round(
            sum(result.estimated_cost_usd for result in results), 6
        ),
    }


def build_report(results: list[BenchmarkResult]) -> dict:
    if not results:
        raise ValueError("评测结果不能为空")
    grouped: dict[str, list[BenchmarkResult]] = {}
    for result in results:
        grouped.setdefault(result.experiment_variant, []).append(result)
    matched_results = [
        result
        for result in results
        if "ablation-anchor" in result.tags or "ablation" in result.tags
    ]
    matched_grouped: dict[str, list[BenchmarkResult]] = {}
    for result in matched_results:
        matched_grouped.setdefault(result.experiment_variant, []).append(result)
    return {
        **_summarize(results),
        "by_variant": {
            variant: _summarize(variant_results)
            for variant, variant_results in sorted(grouped.items())
        },
        "matched_ablation": {
            variant: _summarize(variant_results)
            for variant, variant_results in sorted(matched_grouped.items())
        },
    }


def _write_payload(
    output: Path,
    *,
    metadata: dict,
    results: list[BenchmarkResult],
) -> None:
    payload = {
        "metadata": metadata,
        "report": build_report(results),
        "results": [result.model_dump() for result in results],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Autonomous SWE Agent benchmark")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--output", type=Path, default=Path("benchmark-results.json"))
    parser.add_argument("--model", default="unknown")
    parser.add_argument("--max-total-cost-usd", type=float)
    parser.add_argument("--input-cost-per-million", type=float, default=0.0)
    parser.add_argument("--output-cost-per-million", type=float, default=0.0)
    parser.add_argument(
        "--case-id",
        action="append",
        help="run only this case ID; repeat the option to select multiple cases",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="continue an existing output file and skip completed case IDs",
    )
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

    metadata = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": str(args.dataset),
        "dataset_sha256": hashlib.sha256(dataset_bytes).hexdigest(),
        "model": args.model,
        "input_cost_per_million": args.input_cost_per_million,
        "output_cost_per_million": args.output_cost_per_million,
        "selected_case_ids": [case.case_id for case in all_cases],
    }
    results: list[BenchmarkResult] = []
    if args.resume and args.output.exists():
        previous = json.loads(args.output.read_text(encoding="utf-8"))
        previous_metadata = previous.get("metadata", {})
        if previous_metadata.get("dataset_sha256") != metadata["dataset_sha256"]:
            raise ValueError("cannot resume: benchmark dataset has changed")
        if previous_metadata.get("selected_case_ids") != metadata["selected_case_ids"]:
            raise ValueError("cannot resume: selected case IDs have changed")
        results = [BenchmarkResult.model_validate(item) for item in previous["results"]]

    completed = {result.case_id for result in results}
    cases = [case for case in all_cases if case.case_id not in completed]
    runner = BenchmarkRunner(
        base_url=args.base_url,
        max_total_cost_usd=args.max_total_cost_usd,
    )
    for case in cases:
        spent = sum(result.estimated_cost_usd for result in results)
        if args.max_total_cost_usd is not None and spent >= args.max_total_cost_usd:
            raise RuntimeError(
                f"benchmark cost budget exhausted: ${spent:.6f} >= "
                f"${args.max_total_cost_usd:.6f}"
            )
        results.append(runner.run_case(case))
        _write_payload(args.output, metadata=metadata, results=results)
        print(f"[{len(results)}] {case.case_id}: {results[-1].status}", flush=True)
    if not results:
        raise ValueError("评测结果不能为空")
    _write_payload(args.output, metadata=metadata, results=results)
    print(json.dumps(build_report(results), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
