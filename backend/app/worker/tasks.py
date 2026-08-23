"""Celery task definitions."""

from app.core.config import get_settings
from app.services.errors import TaskCancelledError
from app.services.executor import execute_task
from app.services.publisher import publish_task
from app.worker.celery_app import celery_app


@celery_app.task(
    bind=True,
    name="swe_agent.execute_task",
    acks_late=True,
    reject_on_worker_lost=True,
)
def execute_task_job(self, task_id: str) -> None:
    try:
        execute_task(task_id, propagate=True)
    except TaskCancelledError:
        return
    except Exception as exc:
        settings = get_settings()
        raise self.retry(
            exc=exc,
            max_retries=settings.worker_max_retries,
            countdown=min(60, 2 ** (self.request.retries + 1)),
        ) from exc


@celery_app.task(
    bind=True,
    name="swe_agent.publish_task",
    acks_late=True,
    reject_on_worker_lost=True,
)
def publish_task_job(self, task_id: str) -> None:
    try:
        publish_task(task_id)
    except Exception as exc:
        settings = get_settings()
        raise self.retry(
            exc=exc,
            max_retries=settings.worker_max_retries,
            countdown=min(60, 2 ** (self.request.retries + 1)),
        ) from exc
