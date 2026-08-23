"""Run pinned repository tasks through the public API and aggregate outcomes."""

import argparse
import json
import statistics
import time
from collections.abc import Callable, Iterable
from pathlib import Path

import httpx
from pydantic import BaseModel, Field

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


class BenchmarkRunner:
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        client: httpx.Client | None = None,
        poll_interval: float = 1.0,
        timeout: float = 1_800,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client or httpx.Client(base_url=base_url, timeout=30)
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.sleep = sleep

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
        return BenchmarkResult(
            case_id=case.case_id,
            task_id=task_id,
            status=task["status"],
            resolved=resolved,
            test_exit_code=test_exit_code,
            patch_sha256=patch_sha256,
            iterations=int(result.get("iterations") or 0),
            duration_seconds=round(time.monotonic() - started, 3),
            error=task.get("error"),
            tags=case.tags,
        )

    def run(self, cases: Iterable[BenchmarkCase]) -> list[BenchmarkResult]:
        return [self.run_case(case) for case in cases]


def load_cases(path: Path) -> list[BenchmarkCase]:
    cases = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                cases.append(BenchmarkCase.model_validate_json(line))
            except ValueError as exc:
                raise ValueError(f"数据集第 {line_number} 行无效：{exc}") from exc
    if not cases:
        raise ValueError("评测集不能为空")
    return cases


def build_report(results: list[BenchmarkResult]) -> dict:
    if not results:
        raise ValueError("评测结果不能为空")
    durations = sorted(result.duration_seconds for result in results)
    statuses: dict[str, int] = {}
    for result in results:
        statuses[result.status] = statuses.get(result.status, 0) + 1
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
        "duration_p95_seconds": round(durations[max(0, int(total * 0.95) - 1)], 3),
        "statuses": statuses,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Autonomous SWE Agent benchmark")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--output", type=Path, default=Path("benchmark-results.json"))
    args = parser.parse_args()

    results = BenchmarkRunner(base_url=args.base_url).run(load_cases(args.dataset))
    payload = {
        "report": build_report(results),
        "results": [result.model_dump() for result in results],
    }
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(payload["report"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
