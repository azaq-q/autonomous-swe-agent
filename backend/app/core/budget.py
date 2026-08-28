"""Per-task LLM call, token, and cost budgets with callback enforcement."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from app.core.usage import extract_usage
from app.services.errors import TaskBudgetExceededError


@dataclass(frozen=True)
class LLMBudgetLimits:
    max_input_tokens: int
    max_output_tokens: int
    max_llm_calls: int
    max_cost_usd: float


class LLMBudgetLedger:
    """Track a task budget and persist counters as each provider call finishes."""

    def __init__(
        self,
        limits: LLMBudgetLimits,
        *,
        on_event: Callable[[str, dict], None],
        input_cost_per_million: float = 0.0,
        output_cost_per_million: float = 0.0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        llm_calls: int = 0,
        estimated_cost_usd: float = 0.0,
    ) -> None:
        self.limits = limits
        self.on_event = on_event
        self.input_cost_per_million = input_cost_per_million
        self.output_cost_per_million = output_cost_per_million
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.llm_calls = llm_calls
        self.estimated_cost_usd = estimated_cost_usd

    def callback(self, agent: str) -> "LLMBudgetCallback":
        return LLMBudgetCallback(self, agent)

    def before_call(self, agent: str) -> None:
        if self.llm_calls >= self.limits.max_llm_calls:
            self._raise("llm_calls", self.llm_calls, self.limits.max_llm_calls)
        self.llm_calls += 1
        self.on_event("llm.call", {"agent": agent, "llm_calls": 1})

    def record_usage(self, agent: str, usage: dict[str, int]) -> None:
        input_tokens = int(usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or 0)
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        incremental_cost = (
            input_tokens * self.input_cost_per_million
            + output_tokens * self.output_cost_per_million
        ) / 1_000_000
        self.estimated_cost_usd += incremental_cost
        if input_tokens or output_tokens:
            self.on_event(
                "llm.usage",
                {
                    "agent": agent,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                },
            )
        if self.input_tokens > self.limits.max_input_tokens:
            self._raise(
                "input_tokens", self.input_tokens, self.limits.max_input_tokens
            )
        if self.output_tokens > self.limits.max_output_tokens:
            self._raise(
                "output_tokens", self.output_tokens, self.limits.max_output_tokens
            )
        if self.estimated_cost_usd > self.limits.max_cost_usd:
            self._raise(
                "estimated_cost_usd",
                self.estimated_cost_usd,
                self.limits.max_cost_usd,
            )

    @staticmethod
    def _raise(kind: str, used: int | float, limit: int | float) -> None:
        raise TaskBudgetExceededError(kind=kind, used=used, limit=limit)


class LLMBudgetCallback(BaseCallbackHandler):
    """Enforce and record a shared ledger around each LangChain model call."""

    raise_error = True

    def __init__(self, ledger: LLMBudgetLedger, agent: str) -> None:
        self.ledger = ledger
        self.agent = agent

    def on_llm_start(self, *_args: Any, **_kwargs: Any) -> None:
        self.ledger.before_call(self.agent)

    def on_chat_model_start(self, *_args: Any, **_kwargs: Any) -> None:
        self.ledger.before_call(self.agent)

    def on_llm_end(self, response: LLMResult, **_kwargs: Any) -> None:
        usage = {"input_tokens": 0, "output_tokens": 0}
        for generation_group in response.generations:
            for generation in generation_group:
                message = getattr(generation, "message", None)
                if message is None:
                    continue
                message_usage = extract_usage(message)
                usage["input_tokens"] += message_usage["input_tokens"]
                usage["output_tokens"] += message_usage["output_tokens"]
        if not usage["input_tokens"] and not usage["output_tokens"]:
            token_usage = (response.llm_output or {}).get("token_usage", {})
            usage = {
                "input_tokens": int(
                    token_usage.get("prompt_tokens")
                    or token_usage.get("input_tokens")
                    or 0
                ),
                "output_tokens": int(
                    token_usage.get("completion_tokens")
                    or token_usage.get("output_tokens")
                    or 0
                ),
            }
        self.ledger.record_usage(self.agent, usage)
