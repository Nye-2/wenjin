from src.contracts.model_usage import ModelUsage


def test_provider_usage_treats_cache_and_reasoning_as_token_subsets() -> None:
    usage = ModelUsage.from_provider_metadata(
        {
            "input_tokens": 100,
            "output_tokens": 20,
            "input_token_details": {"cache_read": 60},
            "output_token_details": {"reasoning": 10},
        }
    )

    assert usage is not None
    assert usage.model_dump() == {
        "input_tokens": 100,
        "cached_input_tokens": 60,
        "output_tokens": 20,
        "reasoning_tokens": 10,
        "total_tokens": 120,
    }


def test_provider_total_cannot_be_smaller_than_input_plus_output() -> None:
    usage = ModelUsage.from_provider_metadata(
        {"input_tokens": 100, "output_tokens": 20, "total_tokens": 10}
    )

    assert usage is not None
    assert usage.total_tokens == 120
