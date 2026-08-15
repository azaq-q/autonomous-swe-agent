"""Testing Agent：运行测试并返回结果。"""

from app.sandbox import get_sandbox


class TestingAgent:
    def run(self, command: str = "pytest") -> str:
        """在沙箱中运行测试命令，返回 stdout + stderr。"""
        result = get_sandbox().run(command)
        out = result.stdout
        if result.stderr:
            out += f"\n[stderr]\n{result.stderr}"
        if result.exit_code != 0:
            out += f"\n[exit_code] {result.exit_code}"
        return out
