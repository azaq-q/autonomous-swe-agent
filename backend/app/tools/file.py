"""文件操作工具。"""

from langchain_core.tools import tool

from app.sandbox import get_sandbox


def _tool_error(exc: ValueError | OSError) -> str:
    """Return recoverable feedback instead of aborting the entire agent graph."""
    return f"操作被拒绝：{exc}。请使用仓库工作目录内的相对路径。"


@tool
def read_file(path: str) -> str:
    """读取指定文件的完整内容。"""
    try:
        return get_sandbox().read_file(path)
    except (ValueError, OSError) as exc:
        return _tool_error(exc)


@tool
def write_file(path: str, content: str) -> str:
    """将 content 写入 path（覆盖写），用于修改代码。"""
    try:
        get_sandbox().write_file(path, content)
    except (ValueError, OSError) as exc:
        return _tool_error(exc)
    return f"已写入 {path}"


@tool
def list_files(path: str = ".") -> str:
    """列出目录下的文件，用于了解项目结构。"""
    try:
        entries = get_sandbox().list_dir(path)
    except (ValueError, OSError) as exc:
        return _tool_error(exc)
    return "\n".join(entries) if entries else "(空目录)"
