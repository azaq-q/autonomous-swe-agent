"""Review Agent：模拟人工 Code Review。"""

import json
import re
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel, Field

from app.core.llm import get_llm
from app.core.usage import extract_usage

REVIEW_PROMPT = """你是一名资深代码审查者。请从以下维度审查代码变更：

1. Bug 风险
2. 安全问题
3. 性能问题
4. 可维护性

只输出 JSON，结构如下：
{"verdict":"approve|request_changes","summary":"总结","issues":[{"severity":"high|medium|low","message":"问题"}]}
没有阻塞问题时 verdict 必须为 approve。
"""


class ReviewIssue(BaseModel):
    severity: Literal["high", "medium", "low"]
    message: str = Field(min_length=1, max_length=2_000)


class ReviewResult(BaseModel):
    verdict: Literal["approve", "request_changes"]
    summary: str = Field(min_length=1, max_length=4_000)
    issues: list[ReviewIssue] = Field(default_factory=list)


class ReviewAgent:
    def __init__(self, llm: BaseChatModel | None = None) -> None:
        self.llm = llm or get_llm()
        self.last_usage = {"input_tokens": 0, "output_tokens": 0}

    def review(self, diff: str) -> dict:
        messages = [
            ("system", REVIEW_PROMPT),
            ("user", f"请审查以下代码变更：\n{diff}"),
        ]
        resp = self.llm.invoke(messages)
        self.last_usage = extract_usage(resp)
        return self._parse(str(resp.content)).model_dump()

    @staticmethod
    def _parse(content: str) -> ReviewResult:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                return ReviewResult.model_validate(json.loads(match.group()))
            except (json.JSONDecodeError, ValueError):
                pass
        return ReviewResult(
            verdict="request_changes",
            summary="Review 输出无法解析，需要人工检查",
            issues=[ReviewIssue(severity="medium", message=content[:2_000] or "空输出")],
        )
