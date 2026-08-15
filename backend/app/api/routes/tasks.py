"""任务管理接口（数据库持久化 + 后台执行）。"""

import threading
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.task import Task, TaskStatus
from app.services.executor import STEPS, execute_task

router = APIRouter(tags=["tasks"])


class TaskCreate(BaseModel):
    prompt: str


class TaskResponse(BaseModel):
    task_id: str
    prompt: str
    status: str
    steps: list[dict]


def _to_response(task: Task) -> TaskResponse:
    return TaskResponse(
        task_id=task.task_id,
        prompt=task.prompt,
        status=task.status,
        steps=task.steps or [],
    )


@router.post("/tasks", response_model=TaskResponse)
def create_task(req: TaskCreate, db: Session = Depends(get_db)) -> TaskResponse:
    task = Task(
        task_id=uuid.uuid4().hex[:12],
        prompt=req.prompt,
        status=TaskStatus.PENDING.value,
        steps=[{"name": s, "status": "pending"} for s in STEPS],
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # 后台线程执行任务，避免阻塞请求
    threading.Thread(target=execute_task, args=(task.task_id,), daemon=True).start()

    return _to_response(task)


@router.get("/tasks", response_model=list[TaskResponse])
def list_tasks(db: Session = Depends(get_db)) -> list[TaskResponse]:
    tasks = db.query(Task).order_by(Task.id.desc()).all()
    return [_to_response(t) for t in tasks]


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, db: Session = Depends(get_db)) -> TaskResponse:
    task = db.query(Task).filter(Task.task_id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return _to_response(task)
