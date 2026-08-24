"""Benchmark execution and aggregation tests."""

from pathlib import Path

import httpx
import pytest

from app.evals.benchmark import (
    BenchmarkCase,
    BenchmarkResult,
    BenchmarkRunner,
    build_report,
    load_cases,
)


def _case():
    return BenchmarkCase(
        case_id="bug-1",
        repository="https://github.com/openai/example.git",
        source_commit="a" * 40,
        prompt="Fix bug",
        test_command="pytest -q",
    )


def test_run_case_until_awaiting_approval():
    calls = 0

    def handler(request):
        nonlocal calls
        if request.method == "POST":
            return httpx.Response(200, json={"task_id": "abc", "status": "pending"})
        calls += 1
        if calls == 1:
            return httpx.Response(200, json={"task_id": "abc", "status": "testing"})
        return httpx.Response(
            200,
            json={
                "task_id": "abc",
                "status": "awaiting_approval",
                "artifact_sha256": "b" * 64,
                "result": {"test_exit_code": 0, "iterations": 2},
                "error": None,
            },
        )

    client = httpx.Client(
        base_url="http://test",
        transport=httpx.MockTransport(handler),
    )
    result = BenchmarkRunner(client=client, poll_interval=0, sleep=lambda _: None).run_case(
        _case()
    )
    assert result.resolved is True
    assert result.iterations == 2


def test_build_report():
    results = [
        BenchmarkResult(
            case_id="a",
            status="done",
            resolved=True,
            test_exit_code=0,
            patch_sha256="a" * 64,
            iterations=1,
            duration_seconds=2,
            experiment_variant="full",
            input_tokens=100,
            output_tokens=20,
            estimated_cost_usd=0.1,
        ),
        BenchmarkResult(
            case_id="b",
            status="failed",
            resolved=False,
            test_exit_code=1,
            iterations=3,
            duration_seconds=10,
            experiment_variant="single_agent",
            failure_category="test_failure",
        ),
    ]
    report = build_report(results)
    assert report["resolved_rate"] == 0.5
    assert report["test_pass_rate"] == 0.5
    assert report["average_iterations"] == 2
    assert report["duration_p95_seconds"] == 10
    assert report["input_tokens"] == 100
    assert report["estimated_cost_usd"] == 0.1
    assert report["by_variant"]["full"]["resolved_rate"] == 1.0
    assert report["by_variant"]["single_agent"]["failure_categories"] == {
        "test_failure": 1
    }


def test_load_cases_rejects_duplicate_ids(tmp_path: Path):
    case = _case().model_dump_json()
    dataset = tmp_path / "duplicate.jsonl"
    dataset.write_text(f"{case}\n{case}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="case_id 重复"):
        load_cases(dataset)
