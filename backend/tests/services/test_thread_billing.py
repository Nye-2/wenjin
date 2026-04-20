"""Tests for chat token usage normalization helpers."""

from types import SimpleNamespace

from src.services.thread_billing import (
    extract_message_usage,
    extract_persisted_message_usage,
    extract_persisted_metadata_usage,
    extract_usage_from_agent_result,
    normalize_token_usage,
    summarize_persisted_messages_usage,
    usage_to_metadata,
)


def test_normalize_token_usage_accepts_provider_shapes() -> None:
    usage = normalize_token_usage(
        {
            "prompt_tokens": "12",
            "completion_tokens": 8,
        }
    )

    assert usage is not None
    assert usage.input_tokens == 12
    assert usage.output_tokens == 8
    assert usage.total_tokens == 20


def test_extract_message_usage_prefers_usage_metadata() -> None:
    message = SimpleNamespace(
        usage_metadata={"input_tokens": 40, "output_tokens": 2},
        response_metadata={"token_usage": {"prompt_tokens": 1, "completion_tokens": 1}},
    )

    usage = extract_message_usage(message)

    assert usage is not None
    assert usage.input_tokens == 40
    assert usage.output_tokens == 2
    assert usage.total_tokens == 42


def test_extract_usage_from_agent_result_aggregates_messages() -> None:
    result = {
        "messages": [
            SimpleNamespace(
                content="first",
                usage_metadata={"input_tokens": 10, "output_tokens": 4},
            ),
            {
                "response_metadata": {
                    "token_usage": {
                        "prompt_tokens": 3,
                        "completion_tokens": 5,
                    }
                }
            },
        ]
    }

    usage = extract_usage_from_agent_result(result)

    assert usage is not None
    assert usage.input_tokens == 13
    assert usage.output_tokens == 9
    assert usage.total_tokens == 22


def test_usage_to_metadata_preserves_source_and_model() -> None:
    usage = normalize_token_usage({"input_tokens": 7, "output_tokens": 1})
    assert usage is not None

    metadata = usage_to_metadata(
        usage,
        model_name="gpt-4o",
        source="thread_agent",
    )

    assert metadata == {
        "input_tokens": 7,
        "output_tokens": 1,
        "total_tokens": 8,
        "source": "thread_agent",
        "model_name": "gpt-4o",
    }


def test_extract_persisted_metadata_usage_prefers_usage_payload() -> None:
    usage = extract_persisted_metadata_usage(
        {
            "usage": {
                "input_tokens": 9,
                "output_tokens": 3,
            },
            "billing": {
                "token_usage": {
                    "total_tokens": 999,
                }
            },
        }
    )
    assert usage is not None
    assert usage.input_tokens == 9
    assert usage.output_tokens == 3
    assert usage.total_tokens == 12


def test_extract_persisted_message_usage_reads_metadata_billing_fallback() -> None:
    usage = extract_persisted_message_usage(
        {
            "role": "assistant",
            "metadata": {
                "billing": {
                    "token_usage": {
                        "input_tokens": 5,
                        "output_tokens": 7,
                    }
                }
            },
        }
    )
    assert usage is not None
    assert usage.input_tokens == 5
    assert usage.output_tokens == 7
    assert usage.total_tokens == 12


def test_summarize_persisted_messages_usage_aggregates_assistant_messages_only() -> None:
    usage = summarize_persisted_messages_usage(
        [
            {
                "role": "user",
                "metadata": {
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 100,
                    }
                },
            },
            {
                "role": "assistant",
                "metadata": {
                    "usage": {
                        "input_tokens": 10,
                        "output_tokens": 4,
                    }
                },
            },
            {
                "role": "assistant",
                "metadata": {
                    "billing": {
                        "token_usage": {
                            "input_tokens": 3,
                            "output_tokens": 6,
                        }
                    }
                },
            },
        ]
    )
    assert usage is not None
    assert usage.input_tokens == 13
    assert usage.output_tokens == 10
    assert usage.total_tokens == 23
