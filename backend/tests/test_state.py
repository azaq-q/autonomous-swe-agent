"""任务状态机单元测试。"""

import pytest

from app.agents.state import can_transition
from app.models.task import TaskStatus


def test_pending_to_planning():
    assert can_transition(TaskStatus.PENDING, TaskStatus.PLANNING)


def test_testing_can_retry_coding():
    assert can_transition(TaskStatus.TESTING, TaskStatus.CODING)


def test_reviewing_to_approval():
    assert can_transition(TaskStatus.REVIEWING, TaskStatus.AWAITING_APPROVAL)


def test_done_is_terminal():
    assert can_transition(TaskStatus.DONE, TaskStatus.CODING) is False


def test_invalid_transition():
    assert can_transition(TaskStatus.PENDING, TaskStatus.DONE) is False
