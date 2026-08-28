"""Coding Agent：单 Agent 闭环（阅读代码 → 修改 → 运行测试）。"""

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.prebuilt import create_react_agent

from app.core.llm import get_llm
from app.tools import get_tools

SYSTEM_PROMPT = """你是一名资深软件工程师（Coding Agent），负责在代码仓库中完成开发任务。

工作方式：
1. 先用 search_code / list_files / read_file 理解项目结构。
2. 定位需要修改的代码。
3. 用 write_file 修改代码。
4. 用 run_command 运行测试验证改动。
5. 用 git_diff 检查改动。禁止自行提交或推送，必须等待人工审批。

要求：每次改动后都要运行相关测试，确认没有破坏现有功能。
"""


class CodingAgent:
    """基于 ReAct 循环的单 Agent，可完成「改文件 → 跑测试」闭环。"""

    def __init__(self, llm: BaseChatModel | None = None, tools: list | None = None) -> None:
        self.llm = llm or get_llm()
        self.tools = tools or get_tools()
        self.agent = create_react_agent(self.llm, self.tools)

    def run(self, task: str, callbacks: list[Any] | None = None) -> dict:
        """执行任务，返回完整的消息轨迹（含工具调用与结果）。"""
        messages = [
            ("system", SYSTEM_PROMPT),
            ("user", task),
        ]
        config = {"callbacks": callbacks} if callbacks else None
        return self.agent.invoke({"messages": messages}, config=config)
