"""Tests for the billing policy SSOT."""

from src.billing.policies import (
    FreeTokenAllowance,
    calculate_chat_turn_authorization,
    calculate_free_token_usage,
    calculate_model_usage_credit_ceiling,
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


def test_calculate_free_token_usage_bills_everything_when_allowance_is_disabled() -> None:
    usage = calculate_free_token_usage(
        allowance=FreeTokenAllowance(enabled=False, free_tokens=1000),
        total_tokens=800,
        historical_tokens_before=700,
    )

    assert usage.free_tokens_applied == 0
    assert usage.billable_tokens == 800
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
            "cached_input_tokens": 200,
            "output_tokens": 500,
            "reasoning_tokens": 250,
        },
    )

    assert weighted_tokens == 750


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


def test_raw_cost_replaces_parent_rates_for_cached_and_reasoning_subsets() -> None:
    charge = calculate_model_usage_credits(
        model_policy={
            "input_weight": 1,
            "cached_input_weight": 1,
            "output_weight": 1,
            "reasoning_weight": 1,
            "credits_per_1k_weighted_tokens": 1,
            "min_chat_credits": 0,
            "cost_guard_multiplier": 1,
            "raw_cost": {
                "input_usd_per_1m": 10,
                "cached_input_usd_per_1m": 1,
                "output_usd_per_1m": 20,
                "reasoning_usd_per_1m": 2,
            },
        },
        global_policy={"credits_per_cny": 1, "usd_to_cny": 1},
        token_usage={
            "input_tokens": 1_000_000,
            "cached_input_tokens": 400_000,
            "output_tokens": 500_000,
            "reasoning_tokens": 200_000,
            "total_tokens": 1_500_000,
        },
        surface="chat",
    )

    assert charge.raw_cost_usd == 12.8


def test_chat_turn_credit_ceiling_uses_most_expensive_partition() -> None:
    ceiling = calculate_model_usage_credit_ceiling(
        model_policy={
            "input_weight": 0.2,
            "cached_input_weight": 0.05,
            "output_weight": 1,
            "reasoning_weight": 2,
            "credits_per_1k_weighted_tokens": 5,
            "min_chat_credits": 0,
        },
        global_policy=None,
        token_limit=1_000,
        surface="chat",
    )

    assert ceiling == 10


def test_chat_turn_authorization_quotes_free_hold_and_credit_cap() -> None:
    quote = calculate_chat_turn_authorization(
        model_policy={
            "free_tokens": 1_500,
            "chat_turn_token_reserve": 1_000,
            "chat_turn_max_credits": 3,
            "input_weight": 0.3,
            "output_weight": 1,
            "credits_per_1k_weighted_tokens": 6,
            "min_chat_credits": 0,
        },
        global_policy=None,
        historical_tokens=1_000,
        reserved_free_tokens=0,
    )

    assert quote.free_token_hold == 500
    assert quote.billable_token_envelope == 500
    assert quote.uncapped_credit_ceiling == 3
    assert quote.credit_hold == 3
