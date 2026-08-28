"""Benchmark execution and aggregation tests."""

from pathlib import Path

import httpx
import pytest

from app.evals.benchmark import (
    BenchmarkCase,
    BenchmarkResult,
    BenchmarkRunner,
    _safe_harness_label,
    apply_swebench_report,
    build_report,
    expand_runs,
    load_cases,
)
from app.models.task import ExperimentVariant


def _case():
    return BenchmarkCase(
        case_id="bug-1",
        repository="https://github.com/openai/example.git",
        source_commit="a" * 40,
        prompt="Fix bug",
        test_command="pytest -q",
    )


def test_swebench_harness_label_is_cross_platform_path_safe():
    assert (
        _safe_harness_label("org/model:v1", "full", 11)
        == "org-model-v1--full--seed-11"
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


def test_timeout_preserves_live_usage_and_cost_from_cancel_response():
    def handler(request):
        if request.url.path.endswith("/cancel"):
            return httpx.Response(
                200,
                json={
                    "task_id": "abc",
                    "status": "planning",
                    "input_tokens": 123,
                    "output_tokens": 45,
                    "llm_calls": 7,
                    "estimated_cost_usd": 0.067,
                },
            )
        return httpx.Response(200, json={"task_id": "abc", "status": "pending"})

    client = httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler))
    result = BenchmarkRunner(client=client, timeout=0).run_case(_case())

    assert result.status == "timeout"
    assert result.input_tokens == 123
    assert result.output_tokens == 45
    assert result.llm_calls == 7
    assert result.estimated_cost_usd == 0.067


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
            llm_calls=3,
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
    assert report["llm_calls"] == 3
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


def test_hidden_evaluation_is_pending_until_official_report():
    case = _case().model_copy(
        update={
            "requires_hidden_evaluation": True,
            "swebench_instance_id": "owner__repo-1",
            "provenance": "swe-bench-lite",
        }
    )

    def handler(request):
        if request.method == "POST":
            assert request.read()
            return httpx.Response(200, json={"task_id": "abc", "status": "pending"})
        if request.url.path.endswith("/artifacts/patch"):
            return httpx.Response(200, text="diff --git a/a.py b/a.py\n")
        return httpx.Response(
            200,
            json={
                "task_id": "abc",
                "status": "awaiting_approval",
                "artifact_sha256": "b" * 64,
                "artifact_url": "/api/v1/tasks/abc/artifacts/patch",
                "result": {"test_exit_code": 0, "iterations": 1},
                "error": None,
            },
        )

    client = httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler))
    result = BenchmarkRunner(client=client, poll_interval=0, sleep=lambda _: None).run_case(
        case, seed=7
    )

    assert result.workflow_completed is True
    assert result.resolved is False
    assert result.hidden_evaluation == "pending"
    assert result.failure_category == "pending_hidden_evaluation"
    assert result.model_patch.startswith("diff --git")

    [finalized] = apply_swebench_report(
        [result], {"resolved_ids": ["owner__repo-1"], "unresolved_ids": []}
    )
    assert finalized.resolved is True
    assert finalized.hidden_evaluation == "passed"


def test_expand_runs_and_strict_matched_ablation():
    case = _case().model_copy(update={"task_key": "shared-task"})
    variants = [ExperimentVariant.FULL, ExperimentVariant.NO_RAG]
    runs = expand_runs([case], seeds=[1, 2, 3], variants=variants)
    assert len(runs) == 6

    results = []
    for _, variant, seed in runs:
        results.append(
            BenchmarkResult(
                run_id=f"run-{variant.value}-{seed}",
                case_id="bug-1",
                task_key="shared-task",
                seed=seed,
                status="done",
                workflow_completed=True,
                resolved=variant == ExperimentVariant.FULL or seed != 3,
                public_test_exit_code=0,
                duration_seconds=seed,
                experiment_variant=variant.value,
            )
        )
    report = build_report(results)
    matched = report["matched_ablation"]
    assert matched["matched_task_seed_pairs"] == 3
    assert matched["paired_effects"]["no_rag"]["matched_runs"] == 3
    assert report["resolved_rate_ci95_wilson"][0] < report["resolved_rate"]


def test_swebench_report_requires_cohort_for_repeated_instance():
    results = [
        BenchmarkResult(
            case_id="a",
            task_key="a",
            seed=seed,
            status="done",
            resolved=False,
            duration_seconds=1,
            swebench_instance_id="owner__repo-1",
            hidden_evaluation="pending",
        )
        for seed in (1, 2)
    ]
    report = {"resolved_ids": ["owner__repo-1"], "unresolved_ids": []}
    with pytest.raises(ValueError, match="variant/seed cohort"):
        apply_swebench_report(results, report)

    updated = apply_swebench_report(results, report, variant="full", seed=1)
    assert [result.hidden_evaluation for result in updated] == ["passed", "pending"]


def test_empty_generated_patch_is_a_final_failure():
    case = _case().model_copy(
        update={
            "requires_hidden_evaluation": True,
            "swebench_instance_id": "owner__repo-1",
        }
    )

    def handler(request):
        if request.method == "POST":
            return httpx.Response(200, json={"task_id": "abc", "status": "pending"})
        if request.url.path.endswith("/artifacts/patch"):
            return httpx.Response(200, text="")
        return httpx.Response(
            200,
            json={
                "task_id": "abc",
                "status": "awaiting_approval",
                "artifact_sha256": "e" * 64,
                "artifact_url": "/api/v1/tasks/abc/artifacts/patch",
                "result": {"test_exit_code": 0},
                "error": None,
            },
        )

    client = httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler))
    result = BenchmarkRunner(client=client, poll_interval=0, sleep=lambda _: None).run_case(
        case
    )
    assert result.hidden_evaluation == "failed"
    assert result.failure_category == "no_patch"
    assert build_report([result])["pending_hidden_runs"] == 0
