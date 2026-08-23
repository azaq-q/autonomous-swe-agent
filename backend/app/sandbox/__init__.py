"""沙箱执行层：提供默认沙箱与任务级隔离沙箱。"""

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar

from app.sandbox.base import CommandResult, Sandbox
from app.sandbox.local import LocalSandbox

_sandbox: Sandbox | None = None
_task_sandbox: ContextVar[Sandbox | None] = ContextVar("task_sandbox", default=None)


def get_sandbox() -> Sandbox:
    """按 SANDBOX_PROVIDER 返回沙箱实例（local / docker / e2b）。"""
    global _sandbox
    current = _task_sandbox.get()
    if current is not None:
        return current
    if _sandbox is None:
        from app.core.config import get_settings

        settings = get_settings()
        _sandbox = create_sandbox(settings.workdir)
    return _sandbox


def create_sandbox(workdir: str, provider: str | None = None) -> Sandbox:
    """Create a new sandbox instance; callers own its lifecycle."""
    from app.core.config import get_settings

    settings = get_settings()
    selected_provider = (provider or settings.sandbox_provider).lower()
    if selected_provider == "e2b":
        if not settings.e2b_api_key:
            raise RuntimeError("SANDBOX_PROVIDER=e2b 但未配置 E2B_API_KEY")
        from app.sandbox.e2b import E2BSandbox

        return E2BSandbox(settings.e2b_api_key, settings.e2b_template)
    if selected_provider == "docker":
        from app.sandbox.docker import DockerSandbox

        return DockerSandbox(workdir, settings.docker_image)
    return LocalSandbox(workdir)


@contextmanager
def sandbox_scope(
    workdir: str,
    provider: str | None = None,
) -> Generator[Sandbox, None, None]:
    """Bind an isolated sandbox to the current task/thread and always release it."""
    sandbox = create_sandbox(workdir, provider=provider)
    token = _task_sandbox.set(sandbox)
    try:
        yield sandbox
    finally:
        _task_sandbox.reset(token)
        close = getattr(sandbox, "close", None)
        if callable(close):
            close()


def reset_sandbox() -> None:
    """重置沙箱单例（测试用）。"""
    global _sandbox
    _sandbox = None


__all__ = [
    "CommandResult",
    "Sandbox",
    "LocalSandbox",
    "create_sandbox",
    "get_sandbox",
    "reset_sandbox",
    "sandbox_scope",
]
