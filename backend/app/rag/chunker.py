"""语法感知代码分块：按函数/类定义边界切分。

相比固定长度分块，语法感知分块保留代码的语法完整性（函数/类不被打断），
并携带符号名与行号元数据，提升检索精度与可解释性。
"""

import re

_SYMBOL_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<kind>class|def|async[ \t]+def)[ \t]+(?P<name>\w+)",
    re.MULTILINE,
)


def chunk_code(code: str, source: str = "") -> list[dict]:
    """按 class/def 边界切分代码，返回块列表。

    每个块：{source, symbol, content, start_line, end_line}。
    若代码无任何符号（纯脚本），则整体作为单块。
    """
    lines = code.splitlines()
    # 仅切分顶层符号（无缩进的 class/def），类内方法归入类块
    matches = [m for m in _SYMBOL_RE.finditer(code) if m.group("indent") == ""]

    if not matches:
        return [{
            "source": source,
            "symbol": "(module)",
            "content": code,
            "start_line": 1,
            "end_line": max(len(lines), 1),
        }]

    chunks = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(code)
        kind = m.group("kind").replace("async def", "def")
        symbol = f"{kind} {m.group('name')}"
        chunks.append({
            "source": source,
            "symbol": symbol,
            "content": code[start:end].strip(),
            "start_line": code[:start].count("\n") + 1,
            "end_line": code[:end].count("\n") + 1,
        })
    return chunks
