"""Orchestrator routing tests that do not call an LLM."""

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from app.agents.orchestrator import Orchestrator
from app.core.config import Settings
from app.sandbox import CommandResult, get_sandbox, sandbox_scope
from app.services.errors import TaskCancelledError
from app.services.workspace import WorkspaceManager


def _state(exit_code: int, iteration: int = 1, max_iterations: int = 3) -> dict:
    return {
        "test_exit_code": exit_code,
        "iteration": iteration,
        "max_iterations": max_iterations,
    }


def test_successful_test_routes_to_review():
    assert Orchestrator._after_test(_state(0)) == "review"


@pytest.mark.parametrize("variant", ["single_agent", "no_review"])
def test_review_ablation_routes_success_directly_to_approval(variant):
    state = _state(0)
    state["experiment_variant"] = variant
    assert Orchestrator._after_test(state) == "approval"


def test_failed_test_routes_back_to_coding():
    assert Orchestrator._after_test(_state(1, iteration=1)) == "coding"


def test_retry_budget_exhaustion_routes_to_failed():
    assert Orchestrator._after_test(_state(1, iteration=3)) == "failed"


def test_failure_detection_uses_exit_code_not_log_words():
    state = _state(0)
    state["test_result"] = "0 errors, 0 failed"
    assert Orchestrator._after_test(state) == "review"


class _Planner:
    calls = 0

    def plan(self, task):
        self.calls += 1
        return ["change code", "run tests"]


class _Coding:
    def __init__(self, fail_once=False):
        self.fail_once = fail_once
        self.calls = 0

    def run(self, task):
        self.calls += 1
        if self.fail_once and self.calls == 1:
            raise RuntimeError("simulated worker crash")
        get_sandbox().write_file("agent-change.txt", "changed\n")
        return {"messages": []}


class _Testing:
    def run(self, command):
        return CommandResult(0, "1 passed", "")


class _Review:
    def review(self, diff):
        return {"verdict": "approve", "summary": "approved", "issues": []}


def _fake_orchestrator(**kwargs):
    return Orchestrator(
        planner=kwargs.pop("planner", _Planner()),
        coding=kwargs.pop("coding", _Coding()),
        testing=_Testing(),
        review=_Review(),
        **kwargs,
    )


def test_cooperative_cancellation_stops_before_agent_call():
    planner = _Planner()
    orchestrator = _fake_orchestrator(planner=planner, should_cancel=lambda: True)
    with pytest.raises(TaskCancelledError):
        orchestrator.run("task")
    assert planner.calls == 0


def test_single_agent_variant_skips_planner_and_review(tmp_path):
    planner = _Planner()
    manager = WorkspaceManager(
        Settings(
            workdir=str(tmp_path / "workspaces"),
            artifact_dir=str(tmp_path / "artifacts"),
        )
    )
    workspace = manager.prepare("abcdef123456", None, "main")
    orchestrator = _fake_orchestrator(
        planner=planner,
        experiment_variant="single_agent",
    )
    with sandbox_scope(str(workspace.path), provider="local"):
        result = orchestrator.run("task")
    assert result["status"] == "awaiting_approval"
    assert planner.calls == 0


def test_review_requests_changes_routes_back_to_coding():
    state = _state(0, iteration=1, max_iterations=3)
    state["review"] = {"verdict": "request_changes"}
    assert Orchestrator._after_review(state) == "coding"


def test_review_approval_routes_to_human_approval():
    state = _state(0)
    state["review"] = {"verdict": "approve"}
    assert Orchestrator._after_review(state) == "approval"


def test_review_retry_budget_exhaustion_routes_to_failed():
    state = _state(0, iteration=3, max_iterations=3)
    state["review"] = {"verdict": "request_changes"}
    assert Orchestrator._after_review(state) == "failed"


def test_sqlite_checkpoint_resumes_after_node_failure(tmp_path):
    manager = WorkspaceManager(
        Settings(
            workdir=str(tmp_path / "workspaces"),
            artifact_dir=str(tmp_path / "artifacts"),
        )
    )
    workspace = manager.prepare("abcdef123456", None, "main")
    checkpoint = manager.checkpoint_path("abcdef123456")
    planner = _Planner()
    coding = _Coding(fail_once=True)

    with SqliteSaver.from_conn_string(str(checkpoint)) as saver:
        first = _fake_orchestrator(checkpointer=saver, planner=planner, coding=coding)
        with sandbox_scope(str(workspace.path), provider="local"):
            with pytest.raises(RuntimeError, match="worker crash"):
                first.run("task", thread_id="abcdef123456")

        resumed = _fake_orchestrator(checkpointer=saver, planner=planner, coding=coding)
        with sandbox_scope(str(workspace.path), provider="local"):
            result = resumed.run("task", thread_id="abcdef123456", resume=True)

    assert result["status"] == "awaiting_approval"
    assert planner.calls == 1
    assert coding.calls == 2
