"""Domain exceptions shared by workers and the orchestration layer."""


class TaskCancelledError(RuntimeError):
    """Raised cooperatively when a running task has been cancelled."""


class TaskBudgetExceededError(RuntimeError):
    """Raised when a task crosses an explicit LLM resource budget."""

    def __init__(self, *, kind: str, used: int | float, limit: int | float) -> None:
        self.kind = kind
        self.used = used
        self.limit = limit
        super().__init__(f"task LLM budget exhausted: {kind}={used} limit={limit}")
