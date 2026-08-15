"""Celery application instance."""

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "swe_agent",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
)
