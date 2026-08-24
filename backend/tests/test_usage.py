"""Provider-neutral token usage normalization tests."""

from langchain_core.messages import AIMessage

import app.core.llm as llm_module
from app.core.config import Settings
from app.core.llm import get_llm, llm_seed_scope
from app.core.usage import extract_usage, sum_message_usage


def test_openai_compatible_llm_receives_task_seed(monkeypatch):
    captured = {}

    def fake_chat_openai(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(llm_module, "ChatOpenAI", fake_chat_openai)
    settings = Settings(
        openai_api_key="test", anthropic_api_key=None, default_model="test-model"
    )
    with llm_seed_scope(123):
        get_llm(settings)

    assert captured["seed"] == 123


def test_extract_standard_usage_metadata():
    message = AIMessage(
        content="ok",
        usage_metadata={"input_tokens": 10, "output_tokens": 4, "total_tokens": 14},
    )
    assert extract_usage(message) == {"input_tokens": 10, "output_tokens": 4}


def test_sum_message_usage_ignores_messages_without_usage():
    messages = [
        AIMessage(
            content="one",
            usage_metadata={"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
        ),
        AIMessage(content="two"),
    ]
    assert sum_message_usage(messages) == {"input_tokens": 3, "output_tokens": 2}
