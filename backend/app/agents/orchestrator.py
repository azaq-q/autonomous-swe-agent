"""Orchestrator：基于 LangGraph 编排多 Agent 工作流。

工作流：Planner → Coding → Testing ⇄ Coding（失败重试）→ Review
"""

from langgraph.graph import END, START, StateGraph

from app.agents.coding import CodingAgent
from app.agents.planner import PlannerAgent
from app.agents.review import ReviewAgent
from app.agents.state import AgentState, TaskStatus
from app.agents.testing import TestingAgent
from app.sandbox import get_sandbox


class Orchestrator:
    def __init__(self) -> None:
        self.planner = PlannerAgent()
        self.coding = CodingAgent()
        self.testing = TestingAgent()
        self.review = ReviewAgent()
        self.graph = self._build_graph()

    def _build_graph(self):
        g = StateGraph(AgentState)
        g.add_node("planner", self._plan_node)
        g.add_node("coding", self._coding_node)
        g.add_node("testing", self._testing_node)
        g.add_node("review", self._review_node)

        g.add_edge(START, "planner")
        g.add_edge("planner", "coding")
        g.add_edge("coding", "testing")
        g.add_conditional_edges(
            "testing",
            self._after_test,
            {"coding": "coding", "review": "review"},
        )
        g.add_edge("review", END)
        return g.compile()

    def run(self, task: str) -> dict:
        initial: AgentState = {
            "task": task,
            "status": TaskStatus.PENDING.value,
            "plan": [],
            "messages": [],
            "test_result": "",
            "review": "",
        }
        return self.graph.invoke(initial)

    # ---- 节点实现 ----

    def _plan_node(self, state: AgentState) -> dict:
        plan = self.planner.plan(state["task"])
        return {"plan": plan, "status": TaskStatus.PLANNING.value}

    def _coding_node(self, state: AgentState) -> dict:
        result = self.coding.run(state["task"])
        return {
            "messages": result.get("messages", []),
            "status": TaskStatus.CODING.value,
        }

    def _testing_node(self, state: AgentState) -> dict:
        test_result = self.testing.run()
        return {"test_result": test_result, "status": TaskStatus.TESTING.value}

    def _review_node(self, state: AgentState) -> dict:
        diff = get_sandbox().run("git diff").stdout
        review = self.review.review(diff) if diff.strip() else "无代码变更"
        return {"review": review, "status": TaskStatus.AWAITING_APPROVAL.value}

    # ---- 条件边 ----

    @staticmethod
    def _after_test(state: AgentState) -> str:
        result = state.get("test_result", "")
        if result and ("failed" in result.lower() or "error" in result.lower()):
            return "coding"  # 测试失败，回退到 Coding 修复
        return "review"
