"""代码分块单元测试。"""

from app.rag.chunker import chunk_code


def test_chunk_by_function():
    code = "def foo():\n    return 1\n\ndef bar():\n    return 2\n"
    chunks = chunk_code(code, source="a.py")
    assert len(chunks) == 2
    assert chunks[0]["symbol"] == "def foo"
    assert chunks[1]["symbol"] == "def bar"


def test_chunk_by_class():
    code = "class A:\n    def m(self):\n        pass\n\nclass B:\n    pass\n"
    chunks = chunk_code(code)
    assert len(chunks) == 2
    assert chunks[0]["symbol"] == "class A"
    assert "def m" in chunks[0]["content"]


def test_chunk_line_numbers():
    code = "# comment\ndef foo():\n    pass\n"
    chunks = chunk_code(code)
    assert chunks[0]["start_line"] == 2


def test_chunk_no_symbol():
    code = "x = 1\ny = 2\n"
    chunks = chunk_code(code)
    assert len(chunks) == 1
    assert chunks[0]["symbol"] == "(module)"
