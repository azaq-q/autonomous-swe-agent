"""沙箱抽象：定义统一的执行接口。"""

from dataclasses import dataclass
from typing import Protocol


@dataclass
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


class Sandbox(Protocol):
    """沙箱执行协议：命令执行与文件读写。"""

    def run(self, command: str, cwd: str | None = None, timeout: int = 60) -> CommandResult: ...

    def read_file(self, path: str) -> str: ...

    def write_file(self, path: str, content: str) -> None: ...

    def exists(self, path: str) -> bool: ...

    def list_dir(self, path: str = ".") -> list[str]: ...
