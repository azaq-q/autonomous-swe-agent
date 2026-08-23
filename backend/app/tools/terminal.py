"""终端命令执行工具（受限）。"""

from langchain_core.tools import tool

from app.sandbox import get_sandbox


@tool
def run_command(command: str) -> str:
    """执行 shell 命令（如运行测试、安装依赖），返回 stdout 与 stderr。"""
    if len(command) > 20_000:
        raise ValueError("命令长度超过 20000 字符限制")
    result = get_sandbox().run(command)
    out = result.stdout
    if result.stderr:
        out += f"\n[stderr]\n{result.stderr}"
    if result.exit_code != 0:
        out += f"\n[exit_code] {result.exit_code}"
    return out
