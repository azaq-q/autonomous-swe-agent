"""Publish approved task changes as a commit and optional GitHub pull request."""

import base64
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.core.config import Settings, get_settings
from app.db.session import SessionLocal
from app.models.task import Execution, Task, TaskStatus
from app.services.events import emit_task_event
from app.services.workspace import WorkspaceManager


@dataclass(frozen=True)
class PullRequest:
    number: int
    url: str


class GitHubClient:
    def __init__(
        self,
        token: str,
        api_url: str = "https://api.github.com",
        client: httpx.Client | None = None,
    ) -> None:
        self.client = client or httpx.Client(
            base_url=api_url,
            timeout=30,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2026-03-10",
                "User-Agent": "autonomous-swe-agent",
            },
        )

    def ensure_pull_request(
        self,
        owner: str,
        repo: str,
        branch: str,
        base_branch: str,
        title: str,
        body: str,
    ) -> PullRequest:
        response = self.client.get(
            f"/repos/{owner}/{repo}/pulls",
            params={"state": "open", "head": f"{owner}:{branch}"},
        )
        response.raise_for_status()
        existing = response.json()
        if existing:
            return PullRequest(number=existing[0]["number"], url=existing[0]["html_url"])

        response = self.client.post(
            f"/repos/{owner}/{repo}/pulls",
            json={
                "title": title,
                "body": body,
                "head": branch,
                "base": base_branch,
                "draft": True,
            },
        )
        response.raise_for_status()
        payload = response.json()
        return PullRequest(number=payload["number"], url=payload["html_url"])


class TaskPublisher:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.workspaces = WorkspaceManager(self.settings)

    def publish(self, task_id: str) -> None:
        emit_task_event(task_id, "publication.started", {})
        db = SessionLocal()
        try:
            task = db.query(Task).filter(Task.task_id == task_id).first()
            if task is None:
                return
            if task.status == TaskStatus.DONE.value and task.published_commit:
                return
            if task.status not in {TaskStatus.PUBLISHING.value, TaskStatus.FAILED.value}:
                raise RuntimeError("任务不处于发布状态")
            task.status = TaskStatus.PUBLISHING.value
            db.commit()

            workspace = self.workspaces.reopen(
                task.task_id,
                task.base_commit,
                task.work_branch,
            )
            commit = task.published_commit or self._commit(workspace.path, task.prompt)
            task.published_commit = commit
            db.commit()

            repository = task.repository or ""
            github_repo = self._parse_github_repository(repository)
            if github_repo:
                if not self.settings.github_token:
                    raise RuntimeError("创建 GitHub PR 需要配置 GITHUB_TOKEN")
                self._push(workspace.path, task.work_branch or "", self.settings.github_token)
                owner, repo = github_repo
                pull_request = GitHubClient(
                    self.settings.github_token,
                    self.settings.github_api_url,
                ).ensure_pull_request(
                    owner=owner,
                    repo=repo,
                    branch=task.work_branch or "",
                    base_branch=task.base_branch,
                    title=self._title(task.prompt),
                    body=self._body(task),
                )
                task.pr_number = pull_request.number
                task.pr_url = pull_request.url

            steps = [dict(step) for step in (task.steps or [])]
            for step in steps:
                if step["name"] == "人工审批":
                    step["status"] = "done"
            task.steps = steps
            task.status = TaskStatus.DONE.value
            task.error = None
            db.add(
                Execution(
                    task_id=task.id,
                    agent_name="publisher",
                    input=repository or "local workspace",
                    output=json.dumps(
                        {"commit": commit, "pr_url": task.pr_url},
                        ensure_ascii=False,
                    ),
                )
            )
            db.commit()
            emit_task_event(
                task_id,
                "publication.completed",
                {"commit": commit, "pr_url": task.pr_url},
            )
        except Exception as exc:
            task = db.query(Task).filter(Task.task_id == task_id).first()
            if task is not None:
                task.status = TaskStatus.FAILED.value
                task.error = f"发布失败：{exc}"[:4_000]
                db.commit()
            emit_task_event(task_id, "publication.failed", {"error": str(exc)[:1_000]})
            raise
        finally:
            db.close()

    def _commit(self, workspace: Path, prompt: str) -> str:
        self._git(workspace, ["config", "user.name", self.settings.git_author_name])
        self._git(workspace, ["config", "user.email", self.settings.git_author_email])
        self._git(workspace, ["add", "-A"])
        staged = self._git(workspace, ["diff", "--cached", "--name-only"])
        if not staged.strip():
            raise RuntimeError("没有可发布的代码变更")
        self._git(workspace, ["commit", "-m", self._title(prompt)])
        return self._git(workspace, ["rev-parse", "HEAD"]).strip()

    @staticmethod
    def _push(workspace: Path, branch: str, token: str) -> None:
        credential = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env = os.environ.copy()
        env.update(
            {
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
                "GIT_CONFIG_VALUE_0": f"Authorization: Basic {credential}",
                "GIT_TERMINAL_PROMPT": "0",
            }
        )
        TaskPublisher._git(workspace, ["push", "--set-upstream", "origin", branch], env=env)

    @staticmethod
    def _parse_github_repository(repository: str) -> tuple[str, str] | None:
        parsed = urlparse(repository)
        if parsed.scheme != "https" or parsed.hostname != "github.com":
            return None
        match = re.fullmatch(r"/([^/]+)/([^/]+?)(?:\.git)?/?", parsed.path)
        if not match:
            raise ValueError("GitHub 仓库 URL 格式非法")
        return match.group(1), match.group(2)

    @staticmethod
    def _title(prompt: str) -> str:
        title = " ".join(prompt.split())[:72].strip()
        return title or "SWE Agent change"

    @staticmethod
    def _body(task: Task) -> str:
        result = task.result or {}
        return (
            "## Autonomous SWE Agent\n\n"
            f"{task.prompt}\n\n"
            f"- Base commit: `{task.base_commit}`\n"
            f"- Test exit code: `{result.get('test_exit_code')}`\n"
            f"- Iterations: `{result.get('iterations')}`\n"
            f"- Patch SHA-256: `{task.artifact_sha256}`\n"
        )

    @staticmethod
    def _git(
        workspace: Path,
        args: list[str],
        env: dict[str, str] | None = None,
    ) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=str(workspace),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()[-4_000:]
            raise RuntimeError(f"Git 发布命令失败（{result.returncode}）：{detail}")
        return result.stdout


def publish_task(task_id: str) -> None:
    TaskPublisher().publish(task_id)
