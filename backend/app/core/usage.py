"""Normalize token usage metadata across LangChain providers."""

from typing import Any


def extract_usage(message: Any) -> dict[str, int]:
    usage = getattr(message, "usage_metadata", None) or {}
    response_metadata = getattr(message, "response_metadata", None) or {}
    token_usage = response_metadata.get("token_usage", {})
    return {
        "input_tokens": int(
            usage.get("input_tokens")
            or token_usage.get("prompt_tokens")
            or token_usage.get("input_tokens")
            or 0
        ),
        "output_tokens": int(
            usage.get("output_tokens")
            or token_usage.get("completion_tokens")
            or token_usage.get("output_tokens")
            or 0
        ),
    }


def sum_message_usage(messages: list[Any]) -> dict[str, int]:
    total = {"input_tokens": 0, "output_tokens": 0}
    for message in messages:
        usage = extract_usage(message)
        total["input_tokens"] += usage["input_tokens"]
        total["output_tokens"] += usage["output_tokens"]
    return total
