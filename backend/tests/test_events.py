"""Task event aggregation tests."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.services.events as event_module
from app.core.config import Settings
from app.db.session import Base
from app.models.task import Task, TaskEvent


def test_llm_call_and_usage_events_update_task_counters(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'events.db'}")
    session_factory = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    with session_factory() as db:
        db.add(Task(task_id="task-1", prompt="fix bug"))
        db.commit()

    monkeypatch.setattr(event_module, "SessionLocal", session_factory)
    monkeypatch.setattr(
        event_module,
        "get_settings",
        lambda: Settings(
            model_input_cost_per_million=2,
            model_output_cost_per_million=4,
        ),
    )

    event_module.emit_task_event(
        "task-1", "llm.call", {"agent": "coding", "llm_calls": 1}
    )
    event_module.emit_task_event(
        "task-1",
        "llm.usage",
        {"agent": "coding", "input_tokens": 100, "output_tokens": 50},
    )

    with session_factory() as db:
        task = db.query(Task).filter(Task.task_id == "task-1").one()
        assert task.llm_calls == 1
        assert task.input_tokens == 100
        assert task.output_tokens == 50
        assert task.estimated_cost_usd == 0.0004
        assert db.query(TaskEvent).count() == 2
