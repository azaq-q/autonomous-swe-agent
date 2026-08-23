"""工具单元测试（不依赖 LLM）。"""

import app.sandbox as sandbox_mod
from app.sandbox import LocalSandbox
from app.tools.file import list_files, read_file, write_file
from app.tools.git import git_diff, git_status
from app.tools.terminal import run_command


def _setup_sandbox(monkeypatch, tmp_path):
    sb = LocalSandbox(str(tmp_path))
    monkeypatch.setattr(sandbox_mod, "_sandbox", sb)
    return sb


def test_write_and_read_file_tool(monkeypatch, tmp_path):
    _setup_sandbox(monkeypatch, tmp_path)
    write_file.invoke({"path": "x.py", "content": "print(1)\n"})
    result = read_file.invoke({"path": "x.py"})
    assert "print(1)" in result


def test_list_files_tool(monkeypatch, tmp_path):
    _setup_sandbox(monkeypatch, tmp_path)
    write_file.invoke({"path": "a.txt", "content": "a"})
    result = list_files.invoke({"path": "."})
    assert "a.txt" in result


def test_file_tools_return_recoverable_error_for_path_escape(monkeypatch, tmp_path):
    _setup_sandbox(monkeypatch, tmp_path)
    result = list_files.invoke({"path": str(tmp_path.parent)})
    assert "操作被拒绝" in result
    assert "相对路径" in result


def test_run_command_tool(monkeypatch, tmp_path):
    _setup_sandbox(monkeypatch, tmp_path)
    result = run_command.invoke({"command": "echo hi"})
    assert "hi" in result


def test_git_status_tool(monkeypatch, tmp_path):
    sb = _setup_sandbox(monkeypatch, tmp_path)
    sb.run("git init -q")
    sb.write_file("a.txt", "a")
    result = git_status.invoke({})
    assert "a.txt" in result


def test_git_diff_tool(monkeypatch, tmp_path):
    sb = _setup_sandbox(monkeypatch, tmp_path)
    sb.run("git init -q")
    sb.run('git config user.email "agent@example.com"')
    sb.run('git config user.name "SWE Agent"')
    sb.write_file("a.txt", "a")
    sb.run("git add -A")
    sb.run('git commit -m "init"')
    sb.write_file("a.txt", "b")
    result = git_diff.invoke({})
    assert result.strip() != ""
