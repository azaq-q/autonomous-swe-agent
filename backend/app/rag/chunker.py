"""Multi-language AST-aware code chunking with a conservative fallback."""

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from tree_sitter import Language, Parser

_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".java": "java",
}

_DECLARATIONS = {
    "python": {"function_definition": "def", "class_definition": "class"},
    "javascript": {"function_declaration": "function", "class_declaration": "class"},
    "typescript": {
        "function_declaration": "function",
        "class_declaration": "class",
        "interface_declaration": "interface",
        "type_alias_declaration": "type",
        "enum_declaration": "enum",
    },
    "tsx": {
        "function_declaration": "function",
        "class_declaration": "class",
        "interface_declaration": "interface",
        "type_alias_declaration": "type",
        "enum_declaration": "enum",
    },
    "go": {
        "function_declaration": "func",
        "method_declaration": "func",
        "type_declaration": "type",
    },
    "java": {
        "class_declaration": "class",
        "interface_declaration": "interface",
        "enum_declaration": "enum",
        "record_declaration": "record",
    },
}

_SYMBOL_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<kind>class|def|async[ \t]+def)[ \t]+(?P<name>\w+)",
    re.MULTILINE,
)


@lru_cache(maxsize=8)
def _language(language: str) -> Language:
    if language == "python":
        import tree_sitter_python as grammar

        capsule = grammar.language()
    elif language == "javascript":
        import tree_sitter_javascript as grammar

        capsule = grammar.language()
    elif language in {"typescript", "tsx"}:
        import tree_sitter_typescript as grammar

        capsule = (
            grammar.language_tsx() if language == "tsx" else grammar.language_typescript()
        )
    elif language == "go":
        import tree_sitter_go as grammar

        capsule = grammar.language()
    elif language == "java":
        import tree_sitter_java as grammar

        capsule = grammar.language()
    else:
        raise ValueError(f"不支持的 Tree-sitter 语言：{language}")
    # Keep the Language wrapper alive independently of Parser. Some native
    # grammar bindings do not retain a strong Python reference, which can leave
    # Parser with a dangling language pointer after repeated parses.
    return Language(capsule)


@lru_cache(maxsize=8)
def _parser(language: str) -> Parser:
    return Parser(_language(language))


def infer_language(source: str) -> str | None:
    return _EXTENSIONS.get(Path(source).suffix.lower())


def chunk_code(code: str, source: str = "", language: str | None = None) -> list[dict]:
    """Split top-level declarations while preserving AST boundaries and metadata."""
    selected = language or infer_language(source)
    if selected in _DECLARATIONS:
        return _chunk_ast(code, source, selected)
    return _chunk_python_fallback(code, source)


def _chunk_ast(code: str, source: str, language: str) -> list[dict]:
    encoded = code.encode("utf-8")
    tree = _parser(language).parse(encoded)
    declarations = _DECLARATIONS[language]
    nodes = []
    for child in tree.root_node.named_children:
        if child.type in declarations:
            nodes.append(child)
        elif child.type == "export_statement":
            nodes.extend(node for node in child.named_children if node.type in declarations)
    if not nodes:
        return [_module_chunk(code, source, language)]

    chunks = []
    for node in nodes:
        name_node = node.child_by_field_name("name")
        if name_node is None and node.type == "type_declaration":
            type_spec = next(iter(node.named_children), None)
            name_node = type_spec.child_by_field_name("name") if type_spec else None
        name = _node_text(name_node, encoded) if name_node is not None else "(anonymous)"
        chunks.append(
            {
                "source": source,
                "language": language,
                "symbol": f"{declarations[node.type]} {name}",
                "node_type": node.type,
                "content": encoded[node.start_byte : node.end_byte].decode(
                    "utf-8", errors="replace"
                ),
                "start_line": node.start_point.row + 1,
                "end_line": node.end_point.row + 1,
            }
        )
    return chunks


def _node_text(node: Any, encoded: bytes) -> str:
    return encoded[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _module_chunk(code: str, source: str, language: str | None = None) -> dict:
    return {
        "source": source,
        "language": language,
        "symbol": "(module)",
        "node_type": "module",
        "content": code,
        "start_line": 1,
        "end_line": max(len(code.splitlines()), 1),
    }


def _chunk_python_fallback(code: str, source: str) -> list[dict]:
    matches = [match for match in _SYMBOL_RE.finditer(code) if not match.group("indent")]
    if not matches:
        return [_module_chunk(code, source)]
    chunks = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(code)
        kind = match.group("kind").replace("async def", "def")
        chunks.append(
            {
                "source": source,
                "language": "python",
                "symbol": f"{kind} {match.group('name')}",
                "node_type": kind,
                "content": code[start:end].strip(),
                "start_line": code[:start].count("\n") + 1,
                "end_line": code[:end].count("\n") + 1,
            }
        )
    return chunks
