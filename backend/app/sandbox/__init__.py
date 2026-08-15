"""沙箱执行层：提供隔离的命令执行与文件操作。"""

from app.sandbox.base import CommandResult, Sandbox
from app.sandbox.local import LocalSandbox

_sandbox: Sandbox | None = None


def get_sandbox() -> Sandbox:
    """按 SANDBOX_PROVIDER 返回沙箱实例（local / docker / e2b）。"""
    global _sandbox
    if _sandbox is None:
        from app.core.config import get_settings

        settings = get_settings()
        provider = settings.sandbox_provider.lower()

        if provider == "e2b":
            if not settings.e2b_api_key:
                raise RuntimeError("SANDBOX_PROVIDER=e2b 但未配置 E2B_API_KEY")
            from app.sandbox.e2b import E2BSandbox

            _sandbox = E2BSandbox(settings.e2b_api_key, settings.e2b_template)
        elif provider == "docker":
            from app.sandbox.docker import DockerSandbox

            _sandbox = DockerSandbox(settings.workdir, settings.docker_image)
        else:
            _sandbox = LocalSandbox(settings.workdir)
    return _sandbox


def reset_sandbox() -> None:
    """重置沙箱单例（测试用）。"""
    global _sandbox
    _sandbox = None


__all__ = [
    "CommandResult",
    "Sandbox",
    "LocalSandbox",
    "get_sandbox",
    "reset_sandbox",
]
