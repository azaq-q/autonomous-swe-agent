"""Repository-aware hybrid code search tool."""

from langchain_core.tools import tool

from app.rag.context import get_repository_retriever


@tool
def search_code(query: str, k: int = 5) -> str:
    """按自然语言或符号查询代码，返回相关文件、行号、符号与代码片段。"""
    if not 1 <= k <= 20:
        raise ValueError("k 必须在 1 到 20 之间")
    results = get_repository_retriever().search(query, k=k)
    if not results:
        return "未找到相关代码"
    sections = []
    for result in results:
        sections.append(
            f"{result['source']}:{result['start_line']} [{result['symbol']}] "
            f"score={result['score']}\n{result['content']}"
        )
    return "\n\n---\n\n".join(sections)
