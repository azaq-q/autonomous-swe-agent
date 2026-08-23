"""Docker 容器沙箱实现（需要本机 Docker 守护进程运行）。"""

import shlex
from pathlib import Path, PurePosixPath

from app.sandbox.base import CommandResult


class DockerSandbox:
    """在 Docker 容器内执行命令，宿主工作目录挂载进容器。

    使用前需安装 `docker` SDK（`uv add docker`）并启动本机 Docker。
    """

    def __init__(self, workdir: str, image: str = "python:3.12-slim") -> None:
        try:
            import docker
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("未安装 docker SDK，请先执行 `uv add docker`") from exc

        self.host_workdir = Path(workdir).resolve()
        self.host_workdir.mkdir(parents=True, exist_ok=True)
        self.container_workdir = "/workspace"

        self.client = docker.from_env()
        self.container = self.client.containers.run(
            image,
            command="sleep infinity",
            detach=True,
            network_disabled=True,
            mem_limit="1g",
            nano_cpus=1_000_000_000,
            pids_limit=256,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            read_only=True,
            tmpfs={"/tmp": "rw,noexec,nosuid,size=256m"},
            working_dir=self.container_workdir,
            volumes={
                str(self.host_workdir): {"bind": self.container_workdir, "mode": "rw"}
            },
        )

    def run(self, command: str, cwd: str | None = None, timeout: int = 60) -> CommandResult:
        target = self._container_cwd(cwd)
        script = (
            f"cd {shlex.quote(target)} && "
            f"timeout --signal=KILL {max(1, timeout)}s sh -lc {shlex.quote(command)}"
        )
        exit_code, output = self.container.exec_run(["sh", "-lc", script], demux=True)
        stdout, stderr = output
        return CommandResult(
            exit_code=exit_code,
            stdout=(stdout or b"").decode("utf-8", errors="replace"),
            stderr=(stderr or b"").decode("utf-8", errors="replace"),
        )

    # 文件操作直接作用于挂载的宿主目录（容器内外共享同一份文件）

    def read_file(self, path: str) -> str:
        return self._resolve(path).read_text(encoding="utf-8")

    def write_file(self, path: str, content: str) -> None:
        full = self._resolve(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")

    def exists(self, path: str) -> bool:
        return self._resolve(path).exists()

    def list_dir(self, path: str = ".") -> list[str]:
        full = self._resolve(path)
        if not full.is_dir():
            return []
        return [p.name for p in full.iterdir()]

    def _resolve(self, path: str) -> Path:
        p = Path(path)
        if not p.is_absolute():
            p = self.host_workdir / p
        resolved = p.resolve()
        if not resolved.is_relative_to(self.host_workdir):
            raise ValueError(f"路径越过沙箱工作目录：{path}")
        return resolved

    def _container_cwd(self, cwd: str | None) -> str:
        relative = PurePosixPath(cwd or ".")
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"容器工作目录非法：{cwd}")
        return str(PurePosixPath(self.container_workdir) / relative)

    def close(self) -> None:
        """删除容器，释放资源。"""
        try:
            self.container.remove(force=True)
        except Exception:
            pass
