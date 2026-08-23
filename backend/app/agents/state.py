"""任务状态机与编排工作流状态定义。"""

from typing import TypedDict

from app.models.task import TaskStatus

# 状态转移表：定义合法的状态流转
TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.PLANNING},
    TaskStatus.PLANNING: {TaskStatus.CODING, TaskStatus.FAILED},
    TaskStatus.CODING: {TaskStatus.TESTING, TaskStatus.FAILED},
    TaskStatus.TESTING: {TaskStatus.CODING, TaskStatus.REVIEWING, TaskStatus.FAILED},
    TaskStatus.REVIEWING: {TaskStatus.AWAITING_APPROVAL, TaskStatus.CODING, TaskStatus.FAILED},
    TaskStatus.AWAITING_APPROVAL: {TaskStatus.DONE, TaskStatus.CODING},
    TaskStatus.DONE: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELLED: set(),
    TaskStatus.PUBLISHING: {TaskStatus.DONE, TaskStatus.FAILED},
}


def can_transition(current: TaskStatus, target: TaskStatus) -> bool:
    """判断从 current 能否合法转移到 target。"""
    return target in TRANSITIONS.get(current, set())


class AgentState(TypedDict):
    """编排工作流的共享状态。"""

    task: str
    test_command: str
    iteration: int
    max_iterations: int
    status: str
    plan: list[str]
    messages: list
    test_result: str
    test_exit_code: int | None
    review: dict
    error: str
