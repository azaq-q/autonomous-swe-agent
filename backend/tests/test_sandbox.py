"""沙箱单元测试。"""

from app.sandbox import LocalSandbox


def test_run_command(tmp_path):
    sb = LocalSandbox(str(tmp_path))
    result = sb.run("echo hello")
    assert result.ok
    assert "hello" in result.stdout


def test_run_command_cwd(tmp_path):
    sb = LocalSandbox(str(tmp_path))
    sb.run("mkdir sub")
    result = sb.run('python -c "import os; print(os.getcwd())"', cwd="sub")
    assert result.ok
    assert "sub" in result.stdout


def test_write_and_read_file(tmp_path):
    sb = LocalSandbox(str(tmp_path))
    sb.write_file("a.txt", "hello world")
    assert sb.exists("a.txt")
    assert sb.read_file("a.txt") == "hello world"
