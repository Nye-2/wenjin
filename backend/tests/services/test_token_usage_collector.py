"""Tests for execution-scoped token usage collection."""

from src.services.token_usage_collector import (
    bind_token_usage_collector,
    get_collected_token_usage,
    record_token_usage,
    reset_token_usage_collector,
)


def test_token_usage_collector_combines_recorded_usage() -> None:
    token = bind_token_usage_collector()
    try:
        record_token_usage({"input_tokens": 10, "output_tokens": 4})
        record_token_usage({"prompt_tokens": 3, "completion_tokens": 2})
        usage = get_collected_token_usage()
    finally:
        reset_token_usage_collector(token)

    assert usage is not None
    assert usage.input_tokens == 13
    assert usage.output_tokens == 6
    assert usage.total_tokens == 19
