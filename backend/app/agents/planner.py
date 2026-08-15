"""Planner Agent：将用户任务拆解为可执行步骤。"""

import json
import re

from langchain_core.language_models.chat_models import BaseChatModel

from app.core.llm import get_llm

PLANNER_PROMPT = """你是一个任务规划器。请将用户的任务拆解为清晰的执行步骤。

要求：
1. 输出一个 JSON 数组，每个元素是一个步骤描述字符串。
2. 步骤应覆盖：分析、定位、修改、测试、验证。
3. 只输出 JSON 数组，不要输出其他内容。

示例输出：["分析项目结构", "定位相关代码", "修改实现", "运行测试验证"]
"""


class PlannerAgent:
    def __init__(self, llm: BaseChatModel | None = None) -> None:
        self.llm = llm or get_llm()

    def plan(self, task: str) -> list[str]:
        messages = [
            ("system", PLANNER_PROMPT),
            ("user", task),
        ]
        resp = self.llm.invoke(messages)
        return self._parse(resp.content)

    @staticmethod
    def _parse(content: str) -> list[str]:
        """优先解析 JSON 数组，失败则按行解析列表文本。"""
        try:
            match = re.search(r"\[.*\]", content, re.DOTALL)
            if match:
                data = json.loads(match.group())
                if isinstance(data, list):
                    return [str(item) for item in data]
        except (json.JSONDecodeError, ValueError):
            pass

        steps = [line.strip().lstrip("-* ").strip() for line in content.splitlines()]
        return [s for s in steps if s]
