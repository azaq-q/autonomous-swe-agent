"""Dispatch tasks to a local development thread or Celery."""

import threading

from app.core.config import get_settings
from app.services.executor import execute_task


def dispatch_task(task_id: str, revision: int = 0) -> str:
    settings = get_settings()
    dispatch_id = f"swe-agent:{task_id}:{revision}"
    if settings.task_backend.lower() == "celery":
        from app.worker.tasks import execute_task_job

        execute_task_job.apply_async(args=[task_id], task_id=dispatch_id)
    else:
        threading.Thread(target=execute_task, args=(task_id,), daemon=True).start()
    return dispatch_id


def revoke_task(dispatch_id: str | None) -> None:
    if not dispatch_id or get_settings().task_backend.lower() != "celery":
        return
    from app.worker.celery_app import celery_app

    celery_app.control.revoke(dispatch_id, terminate=False)


def dispatch_publish(task_id: str, revision: int) -> str:
    settings = get_settings()
    dispatch_id = f"swe-agent:publish:{task_id}:{revision}"
    if settings.task_backend.lower() == "celery":
        from app.worker.tasks import publish_task_job

        publish_task_job.apply_async(args=[task_id], task_id=dispatch_id)
    else:
        from app.services.publisher import publish_task

        threading.Thread(target=publish_task, args=(task_id,), daemon=True).start()
    return dispatch_id
