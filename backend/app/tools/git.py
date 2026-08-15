"""Git 操作工具。"""

import shlex

from langchain_core.tools import tool

from app.sandbox import get_sandbox


@tool
def git_status() -> str:
    """查看 git 工作区状态。"""
    return get_sandbox().run("git status").stdout


@tool
def git_diff() -> str:
    """查看当前代码变更（git diff）。"""
    return get_sandbox().run("git diff").stdout


@tool
def git_commit(message: str) -> str:
    """提交当前所有变更，message 为提交说明。"""
    cmd = f"git add -A && git commit -m {shlex.quote(message)}"
    result = get_sandbox().run(cmd)
    return result.stdout or result.stderr
