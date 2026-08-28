"""Per-call LLM budget enforcement tests."""

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from app.agents.planner import PlannerAgent
from app.core.budget import LLMBudgetLedger, LLMBudgetLimits
from app.services.errors import TaskBudgetExceededError


def _limits(**overrides):
    values = {
        "max_input_tokens": 100,
        "max_output_tokens": 50,
        "max_llm_calls": 2,
        "max_cost_usd": 1.0,
    }
    values.update(overrides)
    return LLMBudgetLimits(**values)


def _result(input_tokens: int, output_tokens: int) -> LLMResult:
    message = AIMessage(
        content="ok",
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    )
    return LLMResult(generations=[[ChatGeneration(message=message)]])


def test_callback_records_each_call_and_usage_before_raising():
    events = []
    ledger = LLMBudgetLedger(
        _limits(max_input_tokens=50),
        on_event=lambda event, payload: events.append((event, payload)),
    )
    callback = ledger.callback("coding")

    callback.on_chat_model_start({}, [], run_id=None)
    with pytest.raises(TaskBudgetExceededError, match="input_tokens=60"):
        callback.on_llm_end(_result(60, 5), run_id=None)

    assert [event for event, _ in events] == ["llm.call", "llm.usage"]
    assert ledger.llm_calls == 1
    assert ledger.input_tokens == 60


def test_call_budget_rejects_request_before_provider_invocation():
    events = []
    ledger = LLMBudgetLedger(
        _limits(max_llm_calls=1),
        on_event=lambda event, payload: events.append((event, payload)),
    )
    callback = ledger.callback("coding")
    callback.on_chat_model_start({}, [], run_id=None)

    with pytest.raises(TaskBudgetExceededError, match="llm_calls=1"):
        callback.on_chat_model_start({}, [], run_id=None)

    assert [event for event, _ in events] == ["llm.call"]


def test_cost_budget_uses_configured_model_prices():
    ledger = LLMBudgetLedger(
        _limits(max_cost_usd=0.01),
        on_event=lambda *_args: None,
        input_cost_per_million=100,
        output_cost_per_million=100,
    )
    ledger.before_call("planner")
    with pytest.raises(TaskBudgetExceededError, match="estimated_cost_usd"):
        ledger.record_usage("planner", {"input_tokens": 100, "output_tokens": 1})


def test_real_chat_model_callback_blocks_the_next_invoke():
    ledger = LLMBudgetLedger(_limits(max_llm_calls=1), on_event=lambda *_args: None)
    callback = ledger.callback("planner")
    planner = PlannerAgent(
        llm=FakeListChatModel(responses=['["first"]', '["second"]'])
    )

    assert planner.plan("task", callbacks=[callback]) == ["first"]
    with pytest.raises(TaskBudgetExceededError, match="llm_calls=1"):
        planner.plan("task", callbacks=[callback])
