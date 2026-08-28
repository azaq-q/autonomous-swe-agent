"""Append task events and maintain aggregate token/cost counters."""

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.task import Task, TaskEvent


def emit_task_event(task_id: str, event_type: str, payload: dict | None = None) -> None:
    payload = payload or {}
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.task_id == task_id).first()
        if task is None:
            return
        db.add(TaskEvent(task_id=task.id, event_type=event_type, payload=payload))
        if event_type == "llm.call":
            task.llm_calls += int(payload.get("llm_calls") or 1)
        elif event_type == "llm.usage":
            input_tokens = int(payload.get("input_tokens") or 0)
            output_tokens = int(payload.get("output_tokens") or 0)
            settings = get_settings()
            task.input_tokens += input_tokens
            task.output_tokens += output_tokens
            task.estimated_cost_usd += (
                input_tokens * settings.model_input_cost_per_million
                + output_tokens * settings.model_output_cost_per_million
            ) / 1_000_000
        db.commit()
    finally:
        db.close()
