"""Provider-neutral token usage normalization tests."""

from langchain_core.messages import AIMessage

from app.core.usage import extract_usage, sum_message_usage


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
