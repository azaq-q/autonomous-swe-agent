"""Per-task repository workspaces and reproducible patch artifacts."""

import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from app.core.config import Settings, get_settings

_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")


@dataclass(frozen=True)
class Workspace:
    path: Path
    base_commit: str
    branch: str


@dataclass(frozen=True)
class PatchArtifact:
    path: Path
    sha256: str
    size: int


class WorkspaceManager:
    """Creates isolated git workspaces under a configured root."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.root = Path(self.settings.workdir).resolve()
        self.artifact_root = Path(self.settings.artifact_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.artifact_root.mkdir(parents=True, exist_ok=True)

    def prepare(
        self,
        task_id: str,
        repository: str | None,
        base_branch: str,
        expected_commit: str | None = None,
    ) -> Workspace:
        self._validate_task_id(task_id)
        self._validate_branch(base_branch)
        if expected_commit and not re.fullmatch(r"[a-fA-F0-9]{40,64}", expected_commit):
            raise ValueError("固定提交格式无效")
        target = (self.root / task_id).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("任务工作目录越界")
        if target.exists() and any(target.iterdir()):
            raise FileExistsError(f"任务工作目录已存在：{target}")

        if repository:
            source = self._validate_repository(repository)
            self._run(
                [
                    "git",
                    "clone",
                    "--no-tags",
                    "--depth",
                    "1",
                    "--branch",
                    base_branch,
                    "--",
                    source,
                    str(target),
                ],
                cwd=self.root,
                timeout=180,
            )
        else:
            target.mkdir(parents=True, exist_ok=True)
            self._run(["git", "init", "-q", "--initial-branch", base_branch], cwd=target)
            self._run(["git", "config", "user.email", "agent@example.invalid"], cwd=target)
            self._run(["git", "config", "user.name", "Autonomous SWE Agent"], cwd=target)
            self._run(
                ["git", "commit", "--allow-empty", "-q", "-m", "Initial workspace"],
                cwd=target,
            )

        self._configure_local_excludes(target)

        base_commit = self._run(["git", "rev-parse", "HEAD"], cwd=target).strip()
        if repository and expected_commit and base_commit.lower() != expected_commit.lower():
            self._run(
                ["git", "fetch", "--no-tags", "--depth", "1", "origin", expected_commit],
                cwd=target,
                timeout=180,
            )
            self._run(["git", "checkout", "--detach", expected_commit], cwd=target)
            base_commit = self._run(["git", "rev-parse", "HEAD"], cwd=target).strip()
        if expected_commit and base_commit.lower() != expected_commit.lower():
            raise ValueError(
                f"仓库 HEAD 与固定提交不一致：expected={expected_commit}, actual={base_commit}"
            )
        branch = f"codex/{task_id}"
        self._run(["git", "switch", "-c", branch], cwd=target)
        return Workspace(path=target, base_commit=base_commit, branch=branch)

    @staticmethod
    def _configure_local_excludes(target: Path) -> None:
        """Ignore common test/build byproducts without modifying the repository."""
        exclude_file = target / ".git" / "info" / "exclude"
        existing = exclude_file.read_text(encoding="utf-8") if exclude_file.exists() else ""
        patterns = ("__pycache__/", "*.py[cod]", ".pytest_cache/")
        missing = [pattern for pattern in patterns if pattern not in existing.splitlines()]
        if missing:
            separator = "" if not existing or existing.endswith("\n") else "\n"
            exclude_file.parent.mkdir(parents=True, exist_ok=True)
            exclude_file.write_text(
                existing + separator + "\n".join(missing) + "\n",
                encoding="utf-8",
            )

    def export_patch(self, task_id: str, workspace: Workspace) -> PatchArtifact:
        self._validate_task_id(task_id)
        self._run(["git", "add", "-N", "--", "."], cwd=workspace.path)
        patch = self._run_bytes(
            ["git", "diff", "--binary", "--no-ext-diff", workspace.base_commit, "--"],
            cwd=workspace.path,
        )
        target_dir = (self.artifact_root / task_id).resolve()
        if not target_dir.is_relative_to(self.artifact_root):
            raise ValueError("补丁产物目录越界")
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / "changes.patch"
        target.write_bytes(patch)
        return PatchArtifact(
            path=target,
            sha256=hashlib.sha256(patch).hexdigest(),
            size=len(patch),
        )

    def reopen(
        self,
        task_id: str,
        base_commit: str | None,
        branch: str | None,
    ) -> Workspace:
        self._validate_task_id(task_id)
        if not base_commit or not re.fullmatch(r"[a-f0-9]{40,64}", base_commit):
            raise ValueError("缺少合法的基础提交")
        if not branch or branch != f"codex/{task_id}":
            raise ValueError("任务工作分支不匹配")
        path = (self.root / task_id).resolve()
        if not path.is_relative_to(self.root) or not (path / ".git").is_dir():
            raise ValueError("任务工作目录不存在或不是 Git 仓库")
        current_branch = self._run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=path
        ).strip()
        if current_branch != branch:
            raise ValueError("任务工作目录当前分支不匹配")
        self._run(["git", "cat-file", "-e", f"{base_commit}^{{commit}}"], cwd=path)
        return Workspace(path=path, base_commit=base_commit, branch=branch)

    def checkpoint_path(self, task_id: str, revision: int = 0) -> Path:
        self._validate_task_id(task_id)
        if revision < 0:
            raise ValueError("revision 不能为负数")
        target = (
            self.artifact_root / task_id / f"checkpoints-{revision}.sqlite"
        ).resolve()
        if not target.is_relative_to(self.artifact_root):
            raise ValueError("checkpoint 目录越界")
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def _validate_repository(self, repository: str) -> str:
        candidate = Path(repository)
        if candidate.exists():
            if not self.settings.allow_local_repositories:
                raise ValueError("当前环境禁止使用本地仓库")
            resolved = candidate.resolve()
            if not (resolved / ".git").exists():
                raise ValueError("本地路径不是 Git 仓库")
            return str(resolved)

        parsed = urlparse(repository)
        allowed_hosts = {
            host.strip().lower()
            for host in self.settings.repository_allowed_hosts.split(",")
            if host.strip()
        }
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("远程仓库必须使用 HTTPS URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("仓库 URL 不允许包含凭据、查询参数或片段")
        if parsed.hostname.lower() not in allowed_hosts:
            raise ValueError(f"仓库主机不在白名单：{parsed.hostname}")
        return repository

    @staticmethod
    def _validate_task_id(task_id: str) -> None:
        if not re.fullmatch(r"[a-f0-9]{12}", task_id):
            raise ValueError("task_id 格式非法")

    @staticmethod
    def _validate_branch(branch: str) -> None:
        if not _BRANCH_RE.fullmatch(branch) or ".." in branch or branch.endswith("/"):
            raise ValueError("base_branch 格式非法")

    @staticmethod
    def _run(command: list[str], cwd: Path, timeout: int = 60) -> str:
        result = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()[-4_000:]
            raise RuntimeError(f"Git 命令失败（{result.returncode}）：{detail}")
        return result.stdout

    @staticmethod
    def _run_bytes(command: list[str], cwd: Path) -> bytes:
        result = subprocess.run(command, cwd=str(cwd), capture_output=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode("utf-8", errors="replace")[-4_000:])
        return result.stdout
