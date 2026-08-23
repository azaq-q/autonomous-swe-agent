"""Task-local repository index available to Agent search tools."""

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from app.rag.embeddings import HashingEmbedder
from app.rag.retriever import CodeRetriever

_SUPPORTED = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java"}
_IGNORED_PARTS = {".git", ".venv", "node_modules", "dist", "build", ".next"}
_current_retriever: ContextVar[CodeRetriever | None] = ContextVar(
    "repository_retriever", default=None
)


def build_repository_index(root: Path, max_files: int = 2_000) -> CodeRetriever:
    root = root.resolve()
    files: dict[str, str] = {}
    for path in root.rglob("*"):
        if len(files) >= max_files:
            break
        if not path.is_file() or path.suffix.lower() not in _SUPPORTED:
            continue
        relative = path.relative_to(root)
        if any(part in _IGNORED_PARTS for part in relative.parts):
            continue
        if path.stat().st_size > 1_000_000:
            continue
        files[relative.as_posix()] = path.read_text(encoding="utf-8", errors="replace")
    return CodeRetriever(files, embedder=HashingEmbedder())


@contextmanager
def repository_index_scope(root: Path) -> Generator[CodeRetriever, None, None]:
    retriever = build_repository_index(root)
    token = _current_retriever.set(retriever)
    try:
        yield retriever
    finally:
        _current_retriever.reset(token)


def get_repository_retriever() -> CodeRetriever:
    retriever = _current_retriever.get()
    if retriever is None:
        raise RuntimeError("当前任务尚未建立代码索引")
    return retriever
