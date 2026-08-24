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


def test_prepare_fetches_pinned_historical_commit(tmp_path):
    source = _source_repository(tmp_path)
    historical = _git(source, "rev-parse", "HEAD")
    (source / "app.py").write_text("answer = 42\n", encoding="utf-8")
    _git(source, "add", "app.py")
    _git(source, "commit", "-q", "-m", "new head")

    workspace = _manager(tmp_path).prepare(
        "abcdef123456", str(source), "main", historical
    )

    assert workspace.base_commit == historical
    assert (workspace.path / "app.py").read_text(encoding="utf-8") == "answer = 41\n"


def test_pinned_commit_does_not_require_declared_branch_to_exist(tmp_path):
    source = _source_repository(tmp_path)
    commit = _git(source, "rev-parse", "HEAD")

    workspace = _manager(tmp_path).prepare(
        "abcdef123456", str(source), "branch-that-does-not-exist", commit
    )

    assert workspace.base_commit == commit


def test_prepare_locally_ignores_python_test_artifacts(tmp_path):
    workspace = _manager(tmp_path).prepare("abcdef123456", None, "main")
    cache = workspace.path / "package" / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "module.cpython-312.pyc").write_bytes(b"generated")
    pytest_cache = workspace.path / ".pytest_cache"
    pytest_cache.mkdir()
    (pytest_cache / "README.md").write_text("generated", encoding="utf-8")

    assert _git(workspace.path, "status", "--short", "--untracked-files=all") == ""


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
