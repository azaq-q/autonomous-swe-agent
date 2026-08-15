"""任务管理接口（内存实现，后续替换为数据库持久化）。"""

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["tasks"])

# 内存存储：{task_id: task}
_TASKS: dict[str, dict] = {}


class TaskCreate(BaseModel):
    prompt: str
    repository: str | None = None


class TaskResponse(BaseModel):
    task_id: str
    prompt: str
    repository: str | None = None
    status: str
    steps: list[dict]


@router.post("/tasks", response_model=TaskResponse)
def create_task(req: TaskCreate) -> TaskResponse:
    task_id = uuid.uuid4().hex[:12]
    task = {
        "task_id": task_id,
        "prompt": req.prompt,
        "repository": req.repository,
        "status": "pending",
        "steps": [
            {"name": "分析仓库", "status": "pending"},
            {"name": "定位问题", "status": "pending"},
            {"name": "修改代码", "status": "pending"},
            {"name": "运行测试", "status": "pending"},
            {"name": "创建 PR", "status": "pending"},
        ],
    }
    _TASKS[task_id] = task
    return TaskResponse(**task)


@router.get("/tasks", response_model=list[TaskResponse])
def list_tasks() -> list[TaskResponse]:
    return [TaskResponse(**t) for t in _TASKS.values()]


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: str) -> TaskResponse:
    task = _TASKS.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return TaskResponse(**task)
