"""Benchmark execution and aggregation tests."""

import httpx

from app.evals.benchmark import BenchmarkCase, BenchmarkResult, BenchmarkRunner, build_report


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
        ),
        BenchmarkResult(
            case_id="b",
            status="failed",
            resolved=False,
            test_exit_code=1,
            iterations=3,
            duration_seconds=10,
        ),
    ]
    report = build_report(results)
    assert report["resolved_rate"] == 0.5
    assert report["test_pass_rate"] == 0.5
    assert report["average_iterations"] == 2
