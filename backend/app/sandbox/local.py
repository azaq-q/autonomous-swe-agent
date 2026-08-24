"""本地沙箱：基于 subprocess 的最小实现。

注意：仅用于本地开发与演示。生产环境需接入 Docker / E2B 等隔离沙箱，
避免 Agent 生成的命令直接作用于宿主机。
"""

import os
import subprocess
from pathlib import Path

from app.sandbox.base import CommandResult


class LocalSandbox:
    def __init__(self, workdir: str) -> None:
        self.workdir = Path(workdir).resolve()
        self.workdir.mkdir(parents=True, exist_ok=True)

    def run(self, command: str, cwd: str | None = None, timeout: int = 60) -> CommandResult:
        target = self._resolve(cwd) if cwd else self.workdir
        target.mkdir(parents=True, exist_ok=True)
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=str(target),
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            return CommandResult(proc.returncode, proc.stdout, proc.stderr)
        except subprocess.TimeoutExpired:
            return CommandResult(-1, "", f"命令超时（{timeout}s）")

    def read_file(self, path: str) -> str:
        return self._resolve(path).read_text(encoding="utf-8")

    def write_file(self, path: str, content: str) -> None:
        full = self._resolve(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")

    def exists(self, path: str) -> bool:
        return self._resolve(path).exists()

    def list_dir(self, path: str = ".") -> list[str]:
        full = self._resolve(path)
        if not full.is_dir():
            return []
        return [p.name for p in full.iterdir()]

    def _resolve(self, path: str) -> Path:
        p = Path(path)
        if not p.is_absolute():
            p = self.workdir / p
        resolved = p.resolve()
        if not resolved.is_relative_to(self.workdir):
            raise ValueError(f"路径越过沙箱工作目录：{path}")
        return resolved
