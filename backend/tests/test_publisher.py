"""Commit and GitHub pull request publication tests."""

import json

import httpx

from app.core.config import Settings
from app.services.publisher import GitHubClient, TaskPublisher
from app.services.workspace import WorkspaceManager


def test_commit_approved_workspace(tmp_path):
    settings = Settings(
        workdir=str(tmp_path / "workspaces"),
        artifact_dir=str(tmp_path / "artifacts"),
        git_author_name="Test Agent",
        git_author_email="agent@example.com",
    )
    manager = WorkspaceManager(settings)
    workspace = manager.prepare("abcdef123456", None, "main")
    (workspace.path / "fix.py").write_text("fixed = True\n", encoding="utf-8")

    commit = TaskPublisher(settings)._commit(workspace.path, "Fix the bug")

    assert len(commit) == 40
    assert TaskPublisher._git(workspace.path, ["status", "--porcelain"]) == ""
    assert TaskPublisher._git(workspace.path, ["log", "-1", "--pretty=%s"]).strip() == "Fix the bug"


def test_parse_github_repository():
    assert TaskPublisher._parse_github_repository(
        "https://github.com/openai/example.git"
    ) == ("openai", "example")
    assert TaskPublisher._parse_github_repository("C:/local/repo") is None


def test_reuse_existing_pull_request():
    def handler(request):
        assert request.url.params["head"] == "openai:codex/task"
        return httpx.Response(
            200,
            json=[{"number": 7, "html_url": "https://github.com/openai/repo/pull/7"}],
        )

    client = httpx.Client(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(handler),
    )
    result = GitHubClient("token", client=client).ensure_pull_request(
        "openai", "repo", "codex/task", "main", "title", "body"
    )
    assert result.number == 7


def test_create_draft_pull_request():
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=[])
        payload = json.loads(request.content)
        assert payload["draft"] is True
        assert payload["base"] == "main"
        return httpx.Response(
            201,
            json={"number": 8, "html_url": "https://github.com/openai/repo/pull/8"},
        )

    client = httpx.Client(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(handler),
    )
    result = GitHubClient("token", client=client).ensure_pull_request(
        "openai", "repo", "codex/task", "main", "title", "body"
    )
    assert result.number == 8
    assert [request.method for request in requests] == ["GET", "POST"]
