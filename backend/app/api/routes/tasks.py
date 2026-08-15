"""Task management endpoints (skeleton)."""

from fastapi import APIRouter

router = APIRouter(tags=["tasks"])


@router.get("/tasks")
def list_tasks() -> list:
    return []


@router.post("/tasks")
def create_task() -> dict:
    return {"status": "created"}
