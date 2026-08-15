"""工具系统：向 Agent 暴露的工具集合。"""

from app.tools.file import list_files, read_file, write_file
from app.tools.git import git_commit, git_diff, git_status
from app.tools.terminal import run_command

ALL_TOOLS = [
    read_file,
    write_file,
    list_files,
    run_command,
    git_status,
    git_diff,
    git_commit,
]


def get_tools() -> list:
    """返回 Agent 可用的工具列表。"""
    return list(ALL_TOOLS)


__all__ = ["get_tools", "ALL_TOOLS"]
