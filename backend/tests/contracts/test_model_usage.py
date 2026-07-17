import pytest
from pydantic import ValidationError

from src.contracts.model_usage import (
    ModelCallStartedPayload,
    ModelCallTerminalOutcome,
    ModelCallTerminalPayload,
    ModelUsage,
    ModelUsageReceiptPayload,
)


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


@pytest.mark.parametrize(
    "usage",
    [
        {"input_tokens": 10, "cached_input_tokens": 11},
        {"output_tokens": 10, "reasoning_tokens": 11},
    ],
)
def test_usage_rejects_detail_counters_outside_their_parent(usage) -> None:
    with pytest.raises(ValidationError, match="must be a subset"):
        ModelUsage.model_validate(usage)


def test_model_call_terminal_carries_the_complete_started_binding() -> None:
    started = ModelCallStartedPayload(
        model_call_id="model-call:subagent:1",
        model_id="gpt-5.6-terra",
        turn=2,
        attempt=1,
        parent_operation_id="research-batch",
        job_id="worker-1",
    )

    terminal = ModelCallTerminalPayload(
        **started.model_dump(mode="python"),
        outcome=ModelCallTerminalOutcome.UNRESOLVED,
        error_type="ProviderTransportError",
        detail="Provider usage could not be confirmed",
    )

    assert terminal.outcome is ModelCallTerminalOutcome.UNRESOLVED
    assert terminal.job_id == "worker-1"
    assert terminal.parent_operation_id == "research-batch"


def test_model_call_binding_rejects_half_bound_subagent_identity() -> None:
    with pytest.raises(ValidationError, match="must be provided together"):
        ModelCallStartedPayload(
            model_call_id="model-call:subagent:1",
            model_id="gpt-5.6-terra",
            turn=1,
            attempt=1,
            job_id="worker-1",
        )


def test_usage_receipt_payload_requires_nonzero_measured_usage() -> None:
    with pytest.raises(ValidationError, match="non-zero"):
        ModelUsageReceiptPayload(
            model_call_id="model-call:workspace:1",
            model_id="gpt-5.6-terra",
            turn=1,
            attempt=1,
            usage=ModelUsage(),
        )
