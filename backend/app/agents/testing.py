"""Testing Agent：运行测试并返回结果。"""

from app.sandbox import CommandResult, get_sandbox


class TestingAgent:
    def run(self, command: str = "pytest") -> CommandResult:
        """在沙箱中运行测试命令，保留可靠的退出码。"""
        return get_sandbox().run(command)
