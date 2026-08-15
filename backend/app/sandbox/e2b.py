"""E2B 云端沙箱实现（需要 E2B_API_KEY）。"""

from app.sandbox.base import CommandResult


class E2BSandbox:
    """基于 E2B 的云端隔离沙箱。

    使用前需安装 `e2b` SDK（`uv add e2b`）并在 .env 配置 E2B_API_KEY。
    """

    def __init__(self, api_key: str, template: str = "base") -> None:
        try:
            from e2b import Sandbox
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("未安装 e2b SDK，请先执行 `uv add e2b`") from exc

        self._sandbox = Sandbox.create(template=template, api_key=api_key)

    def run(self, command: str, cwd: str | None = None, timeout: int = 60) -> CommandResult:
        cmd = f"cd {cwd} && {command}" if cwd else command
        result = self._sandbox.commands.run(cmd)
        return CommandResult(
            exit_code=result.exit_code,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
        )

    def read_file(self, path: str) -> str:
        data = self._sandbox.files.read(path)
        if isinstance(data, bytes):
            return data.decode("utf-8", errors="replace")
        return data

    def write_file(self, path: str, content: str) -> None:
        self._sandbox.files.write(path, content)

    def exists(self, path: str) -> bool:
        try:
            self._sandbox.files.read(path)
            return True
        except Exception:
            return False

    def list_dir(self, path: str = ".") -> list[str]:
        entries = self._sandbox.files.list(path)
        return [entry.name for entry in entries]

    def close(self) -> None:
        """销毁沙箱实例，释放云端资源。"""
        self._sandbox.kill()
