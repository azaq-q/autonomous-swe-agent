"""Orchestrator：基于 LangGraph 编排多 Agent 工作流。

工作流：Planner → Coding → Testing ⇄ Coding（失败重试）→ Review
"""

from collections.abc import Callable
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.coding import CodingAgent
from app.agents.planner import PlannerAgent
from app.agents.review import ReviewAgent
from app.agents.state import AgentState, TaskStatus
from app.agents.testing import TestingAgent
from app.core.usage import sum_message_usage
from app.sandbox import get_sandbox
from app.services.errors import TaskCancelledError


class Orchestrator:
    def __init__(
        self,
        checkpointer: Any | None = None,
        should_cancel: Callable[[], bool] | None = None,
        planner: Any | None = None,
        coding: Any | None = None,
        testing: Any | None = None,
        review: Any | None = None,
        on_event: Callable[[str, dict], None] | None = None,
    ) -> None:
        self.planner = planner or PlannerAgent()
        self.coding = coding or CodingAgent()
        self.testing = testing or TestingAgent()
        self.review = review or ReviewAgent()
        self.checkpointer = checkpointer
        self.should_cancel = should_cancel or (lambda: False)
        self.on_event = on_event or (lambda _event, _payload: None)
        self.graph = self._build_graph()

    def _build_graph(self):
        g = StateGraph(AgentState)
        g.add_node("planner", self._plan_node)
        g.add_node("coding", self._coding_node)
        g.add_node("testing", self._testing_node)
        g.add_node("review", self._review_node)
        g.add_node("approval", self._approval_node)
        g.add_node("failed", self._failed_node)

        g.add_edge(START, "planner")
        g.add_edge("planner", "coding")
        g.add_edge("coding", "testing")
        g.add_conditional_edges(
            "testing",
            self._after_test,
            {"coding": "coding", "review": "review", "failed": "failed"},
        )
        g.add_conditional_edges(
            "review",
            self._after_review,
            {"coding": "coding", "approval": "approval", "failed": "failed"},
        )
        g.add_edge("approval", END)
        g.add_edge("failed", END)
        return g.compile(checkpointer=self.checkpointer)

    def run(
        self,
        task: str,
        test_command: str = "pytest",
        max_iterations: int = 3,
        thread_id: str | None = None,
        resume: bool = False,
    ) -> dict:
        config = {"configurable": {"thread_id": thread_id}} if thread_id else None
        if resume and config:
            snapshot = self.graph.get_state(config)
            if snapshot.values:
                if not snapshot.next:
                    return dict(snapshot.values)
                return self.graph.invoke(None, config=config)
        initial: AgentState = {
            "task": task,
            "test_command": test_command,
            "iteration": 0,
            "max_iterations": max_iterations,
            "status": TaskStatus.PENDING.value,
            "plan": [],
            "messages": [],
            "test_result": "",
            "test_exit_code": None,
            "review": {},
            "error": "",
        }
        return self.graph.invoke(initial, config=config)

    # ---- 节点实现 ----

    def _plan_node(self, state: AgentState) -> dict:
        self._guard_cancelled()
        self.on_event("agent.started", {"agent": "planner"})
        plan = self.planner.plan(state["task"])
        self._record_usage("planner", getattr(self.planner, "last_usage", {}))
        self.on_event("agent.completed", {"agent": "planner", "steps": len(plan)})
        return {"plan": plan, "status": TaskStatus.PLANNING.value}

    def _coding_node(self, state: AgentState) -> dict:
        self._guard_cancelled()
        self.on_event("agent.started", {"agent": "coding"})
        task = state["task"]
        if state.get("plan"):
            task += "\n\n执行计划：\n- " + "\n- ".join(state["plan"])
        if state.get("test_exit_code") not in (None, 0):
            task += (
                "\n\n上一轮测试失败，请根据日志修复后重新运行测试。"
                f"\n测试日志：\n{state.get('test_result', '')[-8000:]}"
            )
        review = state.get("review", {})
        if review.get("verdict") == "request_changes":
            issues = "\n".join(
                f"- [{issue['severity']}] {issue['message']}"
                for issue in review.get("issues", [])
            )
            task += f"\n\n上一轮 Review 要求修改：\n{issues or review.get('summary', '')}"
        result = self.coding.run(task)
        messages = result.get("messages", [])
        self._record_usage("coding", sum_message_usage(messages))
        self.on_event("agent.completed", {"agent": "coding"})
        return {
            "messages": messages,
            "iteration": state.get("iteration", 0) + 1,
            "status": TaskStatus.CODING.value,
        }

    def _testing_node(self, state: AgentState) -> dict:
        self._guard_cancelled()
        self.on_event("agent.started", {"agent": "testing"})
        result = self.testing.run(state["test_command"])
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"
        self.on_event(
            "agent.completed",
            {"agent": "testing", "exit_code": result.exit_code},
        )
        return {
            "test_result": output,
            "test_exit_code": result.exit_code,
            "status": TaskStatus.TESTING.value,
        }

    def _review_node(self, state: AgentState) -> dict:
        self._guard_cancelled()
        self.on_event("agent.started", {"agent": "review"})
        sandbox = get_sandbox()
        sandbox.run("git add -N -- .")
        diff = sandbox.run("git diff --no-ext-diff HEAD --").stdout
        review = self.review.review(diff) if diff.strip() else {
            "verdict": "request_changes",
            "summary": "没有检测到代码变更",
            "issues": [{"severity": "high", "message": "任务没有产生可审查的补丁"}],
        }
        self._record_usage("review", getattr(self.review, "last_usage", {}))
        self.on_event(
            "agent.completed",
            {"agent": "review", "verdict": review["verdict"]},
        )
        return {"review": review, "status": TaskStatus.REVIEWING.value}

    def _approval_node(self, state: AgentState) -> dict:
        self._guard_cancelled()
        return {"status": TaskStatus.AWAITING_APPROVAL.value}

    @staticmethod
    def _failed_node(state: AgentState) -> dict:
        if state.get("test_exit_code") not in (None, 0):
            error = (
                f"测试在 {state['iteration']} 次修改后仍未通过（退出码 "
                f"{state.get('test_exit_code')}）"
            )
        else:
            error = f"代码在 {state['iteration']} 次修改后仍未通过 Review"
        return {
            "status": TaskStatus.FAILED.value,
            "error": error,
        }

    def _guard_cancelled(self) -> None:
        if self.should_cancel():
            raise TaskCancelledError("任务已被用户取消")

    def _record_usage(self, agent: str, usage: dict) -> None:
        payload = {
            "agent": agent,
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
        }
        if payload["input_tokens"] or payload["output_tokens"]:
            self.on_event("llm.usage", payload)

    # ---- 条件边 ----

    @staticmethod
    def _after_test(state: AgentState) -> str:
        if state.get("test_exit_code") == 0:
            return "review"
        if state.get("iteration", 0) < state.get("max_iterations", 3):
            return "coding"
        return "failed"

    @staticmethod
    def _after_review(state: AgentState) -> str:
        review = state.get("review", {})
        if review.get("verdict") == "approve":
            return "approval"
        if state.get("iteration", 0) < state.get("max_iterations", 3):
            return "coding"
        return "failed"
