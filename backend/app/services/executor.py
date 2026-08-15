"""任务执行器：后台执行任务并更新状态。"""

import time

from sqlalchemy.orm.attributes import flag_modified

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.task import Task, TaskStatus
from app.sandbox import get_sandbox

STEPS = ["分析仓库", "定位问题", "修改代码", "运行测试", "创建 PR"]


def execute_task(task_id: str) -> None:
    """后台执行任务。有 LLM key 走真实编排，否则走 mock 模式。"""
    settings = get_settings()
    if settings.openai_api_key or settings.anthropic_api_key:
        _execute_real(task_id)
    else:
        _execute_mock(task_id)


def _execute_mock(task_id: str) -> None:
    """mock 模式：按状态机流转步骤，测试步骤用沙箱真实执行。"""
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.task_id == task_id).first()
        if task is None:
            return

        steps = [{"name": s, "status": "pending"} for s in STEPS]
        task.status = TaskStatus.PLANNING.value
        task.steps = steps
        db.commit()

        for step in steps:
            step["status"] = "running"
            _mark_steps_modified(task, steps)
            db.commit()

            time.sleep(0.6)  # 模拟执行耗时
            if step["name"] == "运行测试":
                result = get_sandbox().run('python -c "print(1)"')
                step["status"] = "done" if result.ok else "failed"
            else:
                step["status"] = "done"
            _mark_steps_modified(task, steps)
            db.commit()

        task.status = TaskStatus.DONE.value
        db.commit()
    finally:
        db.close()


def _execute_real(task_id: str) -> None:
    """真实模式：调用多 Agent 编排执行。"""
    from app.agents.orchestrator import Orchestrator

    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.task_id == task_id).first()
        if task is None:
            return

        steps = [{"name": s, "status": "pending"} for s in STEPS]
        task.status = TaskStatus.PLANNING.value
        task.steps = steps
        db.commit()

        orchestrator = Orchestrator()
        orchestrator.run(task.prompt)

        for step in steps:
            step["status"] = "done"
        _mark_steps_modified(task, steps)
        task.status = TaskStatus.DONE.value
        db.commit()
    finally:
        db.close()


def _mark_steps_modified(task: Task, steps: list) -> None:
    task.steps = steps
    flag_modified(task, "steps")
