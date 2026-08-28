"""任务管理接口（数据库持久化 + 后台执行）。"""

import asyncio
import json
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal, get_db
from app.models.task import Approval, ExperimentVariant, Task, TaskEvent, TaskStatus
from app.services.dispatch import dispatch_publish, dispatch_task, revoke_task
from app.services.events import emit_task_event
from app.services.executor import STEPS

router = APIRouter(tags=["tasks"])


class TaskCreate(BaseModel):
    prompt: str = Field(min_length=3, max_length=20_000)
    repository: str | None = Field(default=None, max_length=2_048)
    base_branch: str = Field(default="main", min_length=1, max_length=128)
    source_commit: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{40,64}$")
    test_command: str = Field(default="pytest", min_length=1, max_length=1_000)
    max_iterations: int = Field(default=3, ge=1, le=10)
    max_input_tokens: int | None = Field(default=None, ge=1, le=100_000_000)
    max_output_tokens: int | None = Field(default=None, ge=1, le=10_000_000)
    max_llm_calls: int | None = Field(default=None, ge=1, le=10_000)
    max_cost_usd: float | None = Field(default=None, gt=0, le=1_000)
    experiment_variant: ExperimentVariant = ExperimentVariant.FULL
    random_seed: int | None = Field(default=None, ge=0, le=2_147_483_647)


class TaskResponse(BaseModel):
    task_id: str
    prompt: str
    repository: str | None
    base_branch: str
    source_commit: str | None
    test_command: str
    max_iterations: int
    max_input_tokens: int
    max_output_tokens: int
    max_llm_calls: int
    max_cost_usd: float
    experiment_variant: str
    random_seed: int | None
    status: str
    steps: list[dict]
    result: dict
    error: str | None
    base_commit: str | None
    work_branch: str | None
    artifact_sha256: str | None
    artifact_url: str | None
    attempt: int
    cancel_requested: bool
    revision: int
    published_commit: str | None
    pr_url: str | None
    pr_number: int | None
    input_tokens: int
    output_tokens: int
    llm_calls: int
    estimated_cost_usd: float


class RequestChanges(BaseModel):
    feedback: str = Field(min_length=3, max_length=10_000)


class TaskEventResponse(BaseModel):
    id: int
    event_type: str
    payload: dict
    created_at: str


DbSession = Annotated[Session, Depends(get_db)]


def _lookup_task_database_id(task_id: str) -> int | None:
    session = SessionLocal()
    try:
        return session.query(Task.id).filter(Task.task_id == task_id).scalar()
    finally:
        session.close()


def _to_response(task: Task) -> TaskResponse:
    return TaskResponse(
        task_id=task.task_id,
        prompt=task.prompt,
        repository=task.repository,
        base_branch=task.base_branch,
        source_commit=task.source_commit,
        test_command=task.test_command,
        max_iterations=task.max_iterations,
        max_input_tokens=task.max_input_tokens,
        max_output_tokens=task.max_output_tokens,
        max_llm_calls=task.max_llm_calls,
        max_cost_usd=task.max_cost_usd,
        experiment_variant=task.experiment_variant,
        random_seed=task.random_seed,
        status=task.status,
        steps=task.steps or [],
        result=task.result or {},
        error=task.error,
        base_commit=task.base_commit,
        work_branch=task.work_branch,
        artifact_sha256=task.artifact_sha256,
        artifact_url=(
            f"/api/v1/tasks/{task.task_id}/artifacts/patch" if task.artifact_path else None
        ),
        attempt=task.attempt,
        cancel_requested=task.cancel_requested,
        revision=task.revision,
        published_commit=task.published_commit,
        pr_url=task.pr_url,
        pr_number=task.pr_number,
        input_tokens=task.input_tokens,
        output_tokens=task.output_tokens,
        llm_calls=task.llm_calls,
        estimated_cost_usd=task.estimated_cost_usd,
    )


@router.post("/tasks", response_model=TaskResponse)
def create_task(req: TaskCreate, db: DbSession) -> TaskResponse:
    settings = get_settings()
    task = Task(
        task_id=uuid.uuid4().hex[:12],
        prompt=req.prompt,
        repository=req.repository,
        base_branch=req.base_branch,
        source_commit=req.source_commit.lower() if req.source_commit else None,
        test_command=req.test_command,
        max_iterations=req.max_iterations,
        max_input_tokens=req.max_input_tokens or settings.task_max_input_tokens,
        max_output_tokens=req.max_output_tokens or settings.task_max_output_tokens,
        max_llm_calls=req.max_llm_calls or settings.task_max_llm_calls,
        max_cost_usd=req.max_cost_usd or settings.task_max_cost_usd,
        experiment_variant=req.experiment_variant.value,
        random_seed=req.random_seed,
        status=TaskStatus.PENDING.value,
        steps=[{"name": s, "status": "pending"} for s in STEPS],
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    try:
        task.dispatch_id = dispatch_task(task.task_id, task.revision)
        db.commit()
        db.refresh(task)
        emit_task_event(task.task_id, "task.dispatched", {"revision": task.revision})
    except Exception as exc:
        task.status = TaskStatus.FAILED.value
        task.error = f"任务分发失败：{exc}"[:4_000]
        db.commit()
        raise HTTPException(status_code=503, detail="task dispatch failed") from exc

    return _to_response(task)


@router.get("/tasks", response_model=list[TaskResponse])
def list_tasks(
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: TaskStatus | None = None,
) -> list[TaskResponse]:
    query = db.query(Task)
    if status is not None:
        query = query.filter(Task.status == status.value)
    tasks = query.order_by(Task.id.desc()).offset(offset).limit(limit).all()
    return [_to_response(t) for t in tasks]


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, db: DbSession) -> TaskResponse:
    task = db.query(Task).filter(Task.task_id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return _to_response(task)


@router.post("/tasks/{task_id}/approve", response_model=TaskResponse)
def approve_task(task_id: str, db: DbSession) -> TaskResponse:
    task = db.query(Task).filter(Task.task_id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    if task.status != TaskStatus.AWAITING_APPROVAL.value:
        raise HTTPException(status_code=409, detail="task is not awaiting approval")

    task.status = TaskStatus.PUBLISHING.value
    db.add(Approval(task_id=task.id, decision="approve"))
    db.commit()
    try:
        task.dispatch_id = dispatch_publish(task.task_id, task.revision)
        db.commit()
    except Exception as exc:
        task.status = TaskStatus.FAILED.value
        task.error = f"发布任务分发失败：{exc}"[:4_000]
        db.commit()
        raise HTTPException(status_code=503, detail="publish dispatch failed") from exc
    db.refresh(task)
    return _to_response(task)


@router.post("/tasks/{task_id}/request-changes", response_model=TaskResponse)
def request_task_changes(task_id: str, req: RequestChanges, db: DbSession) -> TaskResponse:
    task = db.query(Task).filter(Task.task_id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    if task.status != TaskStatus.AWAITING_APPROVAL.value:
        raise HTTPException(status_code=409, detail="task is not awaiting approval")
    if task.revision >= get_settings().max_human_revisions:
        raise HTTPException(status_code=409, detail="human revision budget exhausted")

    task.revision += 1
    task.status = TaskStatus.PENDING.value
    task.cancel_requested = False
    task.error = None
    result = dict(task.result or {})
    result["human_feedback"] = req.feedback
    task.result = result
    db.add(
        Approval(
            task_id=task.id,
            decision="request_changes",
            feedback=req.feedback,
        )
    )
    db.commit()
    try:
        task.dispatch_id = dispatch_task(task.task_id, task.revision)
        db.commit()
        db.refresh(task)
    except Exception as exc:
        task.status = TaskStatus.FAILED.value
        task.error = f"返工任务分发失败：{exc}"[:4_000]
        db.commit()
        raise HTTPException(status_code=503, detail="task dispatch failed") from exc
    return _to_response(task)


@router.post("/tasks/{task_id}/retry-publication", response_model=TaskResponse)
def retry_publication(task_id: str, db: DbSession) -> TaskResponse:
    task = db.query(Task).filter(Task.task_id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    if task.status != TaskStatus.FAILED.value or not task.artifact_path:
        raise HTTPException(status_code=409, detail="publication is not retryable")
    approved = (
        db.query(Approval)
        .filter(Approval.task_id == task.id, Approval.decision == "approve")
        .first()
    )
    if approved is None:
        raise HTTPException(status_code=409, detail="task has not been approved")

    task.status = TaskStatus.PUBLISHING.value
    task.error = None
    db.commit()
    try:
        task.dispatch_id = dispatch_publish(task.task_id, task.revision)
        db.commit()
        db.refresh(task)
    except Exception as exc:
        task.status = TaskStatus.FAILED.value
        task.error = f"发布任务分发失败：{exc}"[:4_000]
        db.commit()
        raise HTTPException(status_code=503, detail="publish dispatch failed") from exc
    return _to_response(task)


@router.post("/tasks/{task_id}/cancel", response_model=TaskResponse)
def cancel_task(task_id: str, db: DbSession) -> TaskResponse:
    task = db.query(Task).filter(Task.task_id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    if task.status in {
        TaskStatus.DONE.value,
        TaskStatus.AWAITING_APPROVAL.value,
        TaskStatus.PUBLISHING.value,
    }:
        raise HTTPException(status_code=409, detail="task can no longer be cancelled")
    if task.status == TaskStatus.CANCELLED.value:
        return _to_response(task)

    task.cancel_requested = True
    if task.status == TaskStatus.PENDING.value:
        task.status = TaskStatus.CANCELLED.value
    db.commit()
    revoke_task(task.dispatch_id)
    emit_task_event(task.task_id, "task.cancel_requested", {})
    db.refresh(task)
    return _to_response(task)


@router.get("/tasks/{task_id}/artifacts/patch")
def download_patch(task_id: str, db: DbSession) -> FileResponse:
    task = db.query(Task).filter(Task.task_id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    if not task.artifact_path:
        raise HTTPException(status_code=404, detail="patch artifact not found")

    artifact_root = Path(get_settings().artifact_dir).resolve()
    artifact = Path(task.artifact_path).resolve()
    if not artifact.is_relative_to(artifact_root) or not artifact.is_file():
        raise HTTPException(status_code=404, detail="patch artifact not found")
    return FileResponse(
        artifact,
        media_type="text/x-diff",
        filename=f"{task.task_id}.patch",
    )


@router.get("/tasks/{task_id}/events", response_model=list[TaskEventResponse])
def list_task_events(
    task_id: str,
    db: DbSession,
    after_id: int = Query(default=0, ge=0),
) -> list[TaskEventResponse]:
    task = db.query(Task).filter(Task.task_id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    events = (
        db.query(TaskEvent)
        .filter(TaskEvent.task_id == task.id, TaskEvent.id > after_id)
        .order_by(TaskEvent.id)
        .limit(500)
        .all()
    )
    return [
        TaskEventResponse(
            id=event.id,
            event_type=event.event_type,
            payload=event.payload or {},
            created_at=event.created_at.isoformat(),
        )
        for event in events
    ]


@router.get("/tasks/{task_id}/events/stream")
async def stream_task_events(task_id: str, request: Request) -> StreamingResponse:
    database_task_id = _lookup_task_database_id(task_id)
    if database_task_id is None:
        raise HTTPException(status_code=404, detail="task not found")
    last_event_id = int(request.headers.get("last-event-id", "0") or 0)

    async def generate():
        nonlocal last_event_id
        idle_polls = 0
        while not await request.is_disconnected():
            session = SessionLocal()
            try:
                events = (
                    session.query(TaskEvent)
                    .filter(
                        TaskEvent.task_id == database_task_id,
                        TaskEvent.id > last_event_id,
                    )
                    .order_by(TaskEvent.id)
                    .limit(100)
                    .all()
                )
                status = session.query(Task.status).filter(Task.id == database_task_id).scalar()
                for event in events:
                    last_event_id = event.id
                    data = json.dumps(
                        {
                            "id": event.id,
                            "type": event.event_type,
                            "payload": event.payload or {},
                            "created_at": event.created_at.isoformat(),
                        },
                        ensure_ascii=False,
                    )
                    yield f"id: {event.id}\nevent: task_event\ndata: {data}\n\n"
                if events:
                    idle_polls = 0
                else:
                    idle_polls += 1
                if status in {
                    TaskStatus.DONE.value,
                    TaskStatus.FAILED.value,
                    TaskStatus.CANCELLED.value,
                } and not events:
                    yield f"event: end\ndata: {json.dumps({'status': status})}\n\n"
                    return
                if idle_polls >= 30:
                    yield ": keep-alive\n\n"
                    idle_polls = 0
            finally:
                session.close()
            await asyncio.sleep(0.5)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
