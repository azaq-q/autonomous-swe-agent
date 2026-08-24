"""FastAPI task lifecycle integration tests with an isolated database."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.api.routes.tasks as task_routes
from app.db.session import Base, get_db
from app.main import create_app
from app.models.task import Approval, Task, TaskStatus


@pytest.fixture
def api(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'api.db'}",
        connect_args={"check_same_thread": False},
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)

    def override_db() -> Generator[Session, None, None]:
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(task_routes, "dispatch_task", lambda task_id, revision: "dispatch")
    monkeypatch.setattr(
        task_routes,
        "dispatch_publish",
        lambda task_id, revision: "publish",
    )
    monkeypatch.setattr(task_routes, "revoke_task", lambda dispatch_id: None)
    monkeypatch.setattr(task_routes, "emit_task_event", lambda *args, **kwargs: None)
    application = create_app()
    application.dependency_overrides[get_db] = override_db
    with TestClient(application) as client:
        yield client, testing_session


def _create(client):
    response = client.post(
        "/api/v1/tasks",
        json={
            "prompt": "Fix a reproducible bug",
            "repository": "https://github.com/openai/example.git",
            "source_commit": "a" * 40,
            "base_branch": "main",
            "test_command": "pytest -q",
            "max_iterations": 2,
            "experiment_variant": "no_rag",
        },
    )
    assert response.status_code == 200
    return response.json()


def test_create_get_and_filter_tasks(api):
    client, _ = api
    created = _create(client)
    assert created["source_commit"] == "a" * 40
    assert created["attempt"] == 0
    assert created["experiment_variant"] == "no_rag"

    response = client.get(f"/api/v1/tasks/{created['task_id']}")
    assert response.status_code == 200
    assert response.json()["task_id"] == created["task_id"]

    response = client.get("/api/v1/tasks", params={"status": "pending", "limit": 1})
    assert [task["task_id"] for task in response.json()] == [created["task_id"]]


def test_human_request_changes_and_approval_are_audited(api):
    client, session_factory = api
    created = _create(client)
    with session_factory() as db:
        task = db.query(Task).filter(Task.task_id == created["task_id"]).one()
        task.status = TaskStatus.AWAITING_APPROVAL.value
        db.commit()

    response = client.post(
        f"/api/v1/tasks/{created['task_id']}/request-changes",
        json={"feedback": "Add a regression test"},
    )
    assert response.status_code == 200
    assert response.json()["revision"] == 1

    with session_factory() as db:
        task = db.query(Task).filter(Task.task_id == created["task_id"]).one()
        task.status = TaskStatus.AWAITING_APPROVAL.value
        db.commit()
    response = client.post(f"/api/v1/tasks/{created['task_id']}/approve")
    assert response.status_code == 200
    assert response.json()["status"] == "publishing"

    with session_factory() as db:
        decisions = [approval.decision for approval in db.query(Approval).all()]
    assert decisions == ["request_changes", "approve"]


def test_cancel_pending_task_is_idempotent(api):
    client, _ = api
    created = _create(client)
    url = f"/api/v1/tasks/{created['task_id']}/cancel"
    first = client.post(url)
    second = client.post(url)
    assert first.json()["status"] == "cancelled"
    assert second.json()["status"] == "cancelled"
