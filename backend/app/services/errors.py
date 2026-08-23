"""Domain exceptions shared by workers and the orchestration layer."""


class TaskCancelledError(RuntimeError):
    """Raised cooperatively when a running task has been cancelled."""
