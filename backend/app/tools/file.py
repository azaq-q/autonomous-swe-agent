"""文件操作工具。"""

from langchain_core.tools import tool

from app.sandbox import get_sandbox


@tool
def read_file(path: str) -> str:
    """读取指定文件的完整内容。"""
    return get_sandbox().read_file(path)


@tool
def write_file(path: str, content: str) -> str:
    """将 content 写入 path（覆盖写），用于修改代码。"""
    get_sandbox().write_file(path, content)
    return f"已写入 {path}"


@tool
def list_files(path: str = ".") -> str:
    """列出目录下的文件，用于了解项目结构。"""
    entries = get_sandbox().list_dir(path)
    return "\n".join(entries) if entries else "(空目录)"
