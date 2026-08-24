"""任务执行器：后台执行任务并更新状态。"""

import json
import time
from contextlib import nullcontext

from langgraph.checkpoint.sqlite import SqliteSaver
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.task import Execution, ExperimentVariant, Task, TaskStatus
from app.rag.context import repository_index_scope
from app.sandbox import get_sandbox, sandbox_scope
from app.services.errors import TaskCancelledError
from app.services.events import emit_task_event
from app.services.workspace import WorkspaceManager

STEPS = ["分析仓库", "定位问题", "修改代码", "运行测试", "人工审批"]


def execute_task(task_id: str, propagate: bool = False) -> None:
    """后台执行任务。有 LLM key 走真实编排，否则走 mock 模式。"""
    try:
        if not _claim_task(task_id):
            return
        emit_task_event(task_id, "task.started", {})
        settings = get_settings()
        if settings.openai_api_key or settings.anthropic_api_key:
            _execute_real(task_id)
        else:
            _execute_mock(task_id)
    except TaskCancelledError:
        _mark_cancelled(task_id)
        emit_task_event(task_id, "task.cancelled", {})
        if propagate:
            raise
    except Exception as exc:
        db = SessionLocal()
        try:
            task = db.query(Task).filter(Task.task_id == task_id).first()
            if task is not None:
                task.status = TaskStatus.FAILED.value
                task.error = str(exc)[:4_000]
                db.commit()
        finally:
            db.close()
        emit_task_event(task_id, "task.failed", {"error": str(exc)[:1_000]})
        if propagate:
            raise


def _claim_task(task_id: str) -> bool:
    """Idempotently claim a non-terminal task for one execution attempt."""
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.task_id == task_id).with_for_update().first()
        if task is None or task.status in {
            TaskStatus.DONE.value,
            TaskStatus.CANCELLED.value,
            TaskStatus.AWAITING_APPROVAL.value,
        }:
            return False
        if task.cancel_requested:
            task.status = TaskStatus.CANCELLED.value
            db.commit()
            return False
        task.attempt += 1
        task.error = None
        db.commit()
        return True
    finally:
        db.close()


def _mark_cancelled(task_id: str) -> None:
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.task_id == task_id).first()
        if task is not None:
            task.status = TaskStatus.CANCELLED.value
            task.error = "任务已被用户取消"
            db.commit()
    finally:
        db.close()


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

        for step in steps[:-1]:
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

        task.status = TaskStatus.AWAITING_APPROVAL.value
        task.result = {"mode": "mock", "note": "未配置 LLM，未产生真实代码变更"}
        db.commit()
        emit_task_event(task_id, "task.awaiting_approval", {"mode": "mock"})
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

        settings = get_settings()
        if settings.sandbox_provider.lower() == "e2b":
            raise RuntimeError("真实仓库工作区暂不支持 E2B provider，请使用 local 或 docker")

        manager = WorkspaceManager(settings)
        has_workspace = bool(task.workspace_path)
        if has_workspace:
            workspace = manager.reopen(task.task_id, task.base_commit, task.work_branch)
        else:
            workspace = manager.prepare(
                task.task_id,
                task.repository,
                task.base_branch,
                task.source_commit,
            )
            task.workspace_path = str(workspace.path)
            task.base_commit = workspace.base_commit
            task.work_branch = workspace.branch
            db.commit()
            emit_task_event(
                task_id,
                "workspace.ready",
                {"base_commit": workspace.base_commit, "branch": workspace.branch},
            )

        def should_cancel() -> bool:
            check_db = SessionLocal()
            try:
                value = (
                    check_db.query(Task.cancel_requested)
                    .filter(Task.task_id == task_id)
                    .scalar()
                )
                return bool(value)
            finally:
                check_db.close()

        checkpoint_path = manager.checkpoint_path(task.task_id, task.revision)
        resume = checkpoint_path.exists()
        effective_prompt = task.prompt
        human_feedback = (task.result or {}).get("human_feedback")
        if human_feedback:
            effective_prompt += f"\n\n人工复审要求：\n{human_feedback}"
        index_scope = (
            nullcontext(None)
            if task.experiment_variant == ExperimentVariant.NO_RAG.value
            else repository_index_scope(
                workspace.path,
                repository=task.repository or "local",
                source_commit=workspace.base_commit,
            )
        )
        with SqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
            with sandbox_scope(str(workspace.path)):
                with index_scope as retriever:
                    emit_task_event(
                        task_id,
                        "repository.indexed",
                        {
                            "chunks": len(retriever.chunks) if retriever else 0,
                            "enabled": retriever is not None,
                            "metadata": getattr(retriever, "index_metadata", {}),
                        },
                    )
                    orchestrator = Orchestrator(
                        checkpointer=checkpointer,
                        should_cancel=should_cancel,
                        on_event=lambda event, payload: emit_task_event(
                            task_id, event, payload
                        ),
                        experiment_variant=task.experiment_variant,
                    )
                    result = orchestrator.run(
                        effective_prompt,
                        test_command=task.test_command,
                        max_iterations=task.max_iterations,
                        thread_id=f"{task.task_id}:{task.revision}",
                        resume=resume,
                    )
        artifact = manager.export_patch(task.task_id, workspace)

        terminal_status = result["status"]
        for step in steps[:-1]:
            step["status"] = "done" if terminal_status != TaskStatus.FAILED.value else "failed"
        _mark_steps_modified(task, steps)
        task.status = terminal_status
        task.error = result.get("error") or None
        task.result = {
            "iterations": result.get("iteration", 0),
            "test_exit_code": result.get("test_exit_code"),
            "test_output": result.get("test_result", "")[-20_000:],
            "review": result.get("review", ""),
            "base_commit": workspace.base_commit,
            "work_branch": workspace.branch,
            "patch_size": artifact.size,
            "patch_sha256": artifact.sha256,
        }
        task.artifact_path = str(artifact.path)
        task.artifact_sha256 = artifact.sha256
        db.add_all([
            Execution(
                task_id=task.id,
                agent_name="testing",
                input=task.test_command,
                output=task.result["test_output"],
            ),
            Execution(
                task_id=task.id,
                agent_name="review",
                input=None,
                output=json.dumps(task.result["review"], ensure_ascii=False),
            ),
        ])
        db.commit()
        emit_task_event(
            task_id,
            "task.awaiting_approval"
            if terminal_status == TaskStatus.AWAITING_APPROVAL.value
            else "task.failed",
            {"status": terminal_status, "patch_sha256": artifact.sha256},
        )
    finally:
        db.close()


def _mark_steps_modified(task: Task, steps: list) -> None:
    task.steps = steps
    flag_modified(task, "steps")
