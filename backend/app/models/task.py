"""任务与执行记录模型。"""

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TaskStatus(StrEnum):
    """任务生命周期状态。"""

    PENDING = "pending"
    PLANNING = "planning"
    CODING = "coding"
    TESTING = "testing"
    REVIEWING = "reviewing"
    AWAITING_APPROVAL = "awaiting_approval"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PUBLISHING = "publishing"


class ExperimentVariant(StrEnum):
    """Supported orchestration variants for reproducible ablation studies."""

    FULL = "full"
    SINGLE_AGENT = "single_agent"
    NO_RAG = "no_rag"
    NO_REVIEW = "no_review"


class Task(Base):
    __tablename__ = "task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[str] = mapped_column(String(32), unique=True)
    prompt: Mapped[str] = mapped_column(Text)
    repository: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_branch: Mapped[str] = mapped_column(String(128), default="main")
    source_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    test_command: Mapped[str] = mapped_column(Text, default="pytest")
    max_iterations: Mapped[int] = mapped_column(Integer, default=3)
    experiment_variant: Mapped[str] = mapped_column(String(32), default="full")
    random_seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=TaskStatus.PENDING.value)
    steps: Mapped[list] = mapped_column(JSON, default=list)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    workspace_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    work_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dispatch_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    published_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pr_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class Execution(Base):
    """记录每个 Agent 的输入输出，用于可观测与回放。"""

    __tablename__ = "execution"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("task.id"))
    agent_name: Mapped[str] = mapped_column(String(64))
    input: Mapped[str | None] = mapped_column(Text, nullable=True)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class Approval(Base):
    """Immutable human approval/rework audit record."""

    __tablename__ = "approval"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("task.id"), index=True)
    decision: Mapped[str] = mapped_column(String(32))
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class TaskEvent(Base):
    """Append-only task event used for observability and SSE replay."""

    __tablename__ = "task_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("task.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
