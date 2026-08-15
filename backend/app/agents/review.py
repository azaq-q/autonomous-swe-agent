"""Review Agent：模拟人工 Code Review。"""

from langchain_core.language_models.chat_models import BaseChatModel

from app.core.llm import get_llm

REVIEW_PROMPT = """你是一名资深代码审查者。请从以下维度审查代码变更：

1. Bug 风险
2. 安全问题
3. 性能问题
4. 可维护性

请给出结构化、具体的审查意见。如果没有明显问题，请说明通过理由。
"""


class ReviewAgent:
    def __init__(self, llm: BaseChatModel | None = None) -> None:
        self.llm = llm or get_llm()

    def review(self, diff: str) -> str:
        messages = [
            ("system", REVIEW_PROMPT),
            ("user", f"请审查以下代码变更：\n{diff}"),
        ]
        resp = self.llm.invoke(messages)
        return resp.content
