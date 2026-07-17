"""Tests for the billing policy SSOT."""

from src.billing.policies import (
    FreeTokenAllowance,
    calculate_free_token_usage,
    calculate_model_usage_credits,
    calculate_weighted_tokens,
)


def test_calculate_free_token_usage_applies_free_quota() -> None:
    allowance = FreeTokenAllowance(
        enabled=True,
        free_tokens=1000,
    )

    usage = calculate_free_token_usage(
        allowance=allowance,
        total_tokens=800,
        historical_tokens_before=700,
    )

    assert usage.free_tokens_applied == 300
    assert usage.billable_tokens == 500
    assert usage.historical_tokens_after == 1500


def test_calculate_weighted_tokens_uses_value_pricing_weights() -> None:
    weighted_tokens = calculate_weighted_tokens(
        {
            "input_weight": 0.3,
            "cached_input_weight": 0.05,
            "output_weight": 1,
            "reasoning_weight": 1,
        },
        {
            "input_tokens": 1000,
            "cached_input_tokens": 2000,
            "output_tokens": 500,
            "reasoning_tokens": 250,
        },
    )

    assert weighted_tokens == 1150


def test_calculate_model_usage_credits_applies_chat_minimum() -> None:
    charge = calculate_model_usage_credits(
        model_policy={
            "input_weight": 0.3,
            "output_weight": 1,
            "credits_per_1k_weighted_tokens": 6,
            "min_chat_credits": 3,
        },
        global_policy={"credits_per_cny": 10, "usd_to_cny": 7.3},
        token_usage={"input_tokens": 1, "output_tokens": 0, "total_tokens": 1},
        surface="chat",
    )

    assert charge.weighted_credits == 1
    assert charge.minimum_credits == 3
    assert charge.credits_to_charge == 3


def test_calculate_model_usage_credits_applies_mission_minimum() -> None:
    charge = calculate_model_usage_credits(
        model_policy={
            "input_weight": 0.3,
            "output_weight": 1,
            "credits_per_1k_weighted_tokens": 6,
            "min_mission_model_credits": 10,
        },
        global_policy={"credits_per_cny": 10, "usd_to_cny": 7.3},
        token_usage={"input_tokens": 1, "output_tokens": 0, "total_tokens": 1},
        surface="mission",
    )

    assert charge.weighted_credits == 1
    assert charge.minimum_credits == 10
    assert charge.credits_to_charge == 10


def test_calculate_model_usage_credits_applies_raw_cost_guard() -> None:
    charge = calculate_model_usage_credits(
        model_policy={
            "input_weight": 0.3,
            "output_weight": 1,
            "credits_per_1k_weighted_tokens": 1,
            "min_chat_credits": 3,
            "cost_guard_multiplier": 20,
            "raw_cost": {
                "input_usd_per_1m": 1,
                "output_usd_per_1m": 10,
            },
        },
        global_policy={"credits_per_cny": 10, "usd_to_cny": 7.3},
        token_usage={"input_tokens": 1000, "output_tokens": 1000, "total_tokens": 2000},
        surface="chat",
    )

    assert charge.weighted_credits == 2
    assert charge.raw_cost_usd == 0.011
    assert charge.raw_cost_guard_credits == 17
    assert charge.credits_to_charge == 17
