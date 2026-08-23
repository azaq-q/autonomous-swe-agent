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


def test_typescript_ast_chunking():
    code = "interface User { id: string }\n\nexport function login(user: User) { return user.id }\n"
    chunks = chunk_code(code, source="auth.ts")
    assert [chunk["symbol"] for chunk in chunks] == ["interface User", "function login"]
    assert all(chunk["language"] == "typescript" for chunk in chunks)


def test_go_ast_chunking():
    code = (
        "package main\n\n"
        "type User struct { ID string }\n\n"
        "func Login(u User) string { return u.ID }\n"
    )
    chunks = chunk_code(code, source="auth.go")
    assert chunks[0]["symbol"].startswith("type ")
    assert chunks[1]["symbol"] == "func Login"


def test_java_ast_chunking():
    code = "package demo;\npublic class User { String id; }\ninterface Store { void save(); }\n"
    chunks = chunk_code(code, source="User.java")
    assert [chunk["symbol"] for chunk in chunks] == ["class User", "interface Store"]
