"""Task workspace and patch artifact integration tests."""

import subprocess

import pytest

from app.core.config import Settings
from app.services.workspace import WorkspaceManager


def _git(cwd, *args):
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout.strip()


def _source_repository(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-q", "--initial-branch", "main")
    _git(source, "config", "user.email", "test@example.com")
    _git(source, "config", "user.name", "Test")
    (source / "app.py").write_text("answer = 41\n", encoding="utf-8")
    _git(source, "add", "app.py")
    _git(source, "commit", "-q", "-m", "initial")
    return source


def _manager(tmp_path):
    settings = Settings(
        workdir=str(tmp_path / "workspaces"),
        artifact_dir=str(tmp_path / "artifacts"),
        allow_local_repositories=True,
    )
    return WorkspaceManager(settings)


def test_clone_branch_and_export_patch(tmp_path):
    source = _source_repository(tmp_path)
    manager = _manager(tmp_path)
    workspace = manager.prepare("abcdef123456", str(source), "main")

    assert workspace.branch == "codex/abcdef123456"
    assert _git(workspace.path, "rev-parse", "--abbrev-ref", "HEAD") == workspace.branch
    assert _git(workspace.path, "rev-parse", "HEAD") == workspace.base_commit

    (workspace.path / "app.py").write_text("answer = 42\n", encoding="utf-8")
    (workspace.path / "new.py").write_text("created = True\n", encoding="utf-8")
    artifact = manager.export_patch("abcdef123456", workspace)

    patch = artifact.path.read_text(encoding="utf-8")
    assert "answer = 42" in patch
    assert "new.py" in patch
    assert artifact.size > 0
    assert len(artifact.sha256) == 64


def test_reject_unapproved_remote_host(tmp_path):
    manager = _manager(tmp_path)
    with pytest.raises(ValueError, match="不在白名单"):
        manager.prepare("abcdef123456", "https://example.com/repo.git", "main")


@pytest.mark.parametrize("branch", ["../main", "-main", "main..evil", "main/"])
def test_reject_invalid_base_branch(tmp_path, branch):
    manager = _manager(tmp_path)
    with pytest.raises(ValueError, match="base_branch"):
        manager.prepare("abcdef123456", None, branch)


def test_reject_invalid_task_id(tmp_path):
    manager = _manager(tmp_path)
    with pytest.raises(ValueError, match="task_id"):
        manager.prepare("../../escape", None, "main")
