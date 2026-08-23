"""沙箱单元测试。"""

import pytest

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


@pytest.mark.parametrize("path", ["../escape.txt", "../../escape.txt"])
def test_reject_path_traversal(tmp_path, path):
    sb = LocalSandbox(str(tmp_path))
    with pytest.raises(ValueError, match="越过沙箱"):
        sb.write_file(path, "blocked")


def test_reject_absolute_path_outside_workspace(tmp_path):
    sb = LocalSandbox(str(tmp_path))
    outside = tmp_path.parent / "outside.txt"
    with pytest.raises(ValueError, match="越过沙箱"):
        sb.read_file(str(outside))


def test_reject_symlink_escape(tmp_path):
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("secret", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("当前平台不允许创建符号链接")
    sb = LocalSandbox(str(tmp_path))
    with pytest.raises(ValueError, match="越过沙箱"):
        sb.read_file("link.txt")


def test_command_timeout(tmp_path):
    sb = LocalSandbox(str(tmp_path))
    result = sb.run('python -c "import time; time.sleep(2)"', timeout=1)
    assert result.exit_code == -1
    assert "超时" in result.stderr
