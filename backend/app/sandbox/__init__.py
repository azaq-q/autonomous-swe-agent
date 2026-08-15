"""沙箱执行层：提供隔离的命令执行与文件操作。"""

from app.sandbox.base import CommandResult, Sandbox
from app.sandbox.local import LocalSandbox

_sandbox: Sandbox | None = None


def get_sandbox() -> Sandbox:
    """获取全局沙箱实例（默认本地沙箱，E2B/Docker 接入预留）。"""
    global _sandbox
    if _sandbox is None:
        from app.core.config import get_settings

        settings = get_settings()
        # TODO: 当 SANDBOX_PROVIDER=e2b 且配置 E2B_API_KEY 时接入 E2BSandbox
        _sandbox = LocalSandbox(settings.workdir)
    return _sandbox


def reset_sandbox() -> None:
    """重置沙箱单例（测试用）。"""
    global _sandbox
    _sandbox = None


__all__ = ["CommandResult", "Sandbox", "LocalSandbox", "get_sandbox", "reset_sandbox"]
