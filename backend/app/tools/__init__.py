"""工具系统：向 Agent 暴露的工具集合。"""

from app.tools.file import list_files, read_file, write_file
from app.tools.git import git_diff, git_status
from app.tools.search import search_code
from app.tools.terminal import run_command

ALL_TOOLS = [
    read_file,
    write_file,
    list_files,
    search_code,
    run_command,
    git_status,
    git_diff,
]


def get_tools(include_search: bool = True) -> list:
    """返回 Agent 可用的工具列表。"""
    return [tool for tool in ALL_TOOLS if include_search or tool is not search_code]


__all__ = ["get_tools", "ALL_TOOLS"]
