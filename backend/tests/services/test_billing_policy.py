"""Tests for the billing policy SSOT."""

from src.services.billing_policy import (
    BILLABLE_MISSION_TASK_TYPES,
    OperationBillingPolicy,
    TokenBillingPolicy,
    calculate_model_usage_credits,
    calculate_sandbox_estimate,
    calculate_token_billing_charge,
    calculate_weighted_tokens,
    get_public_workflow_costs,
    get_sandbox_operation_billing_policy,
    get_workflow_costs,
)


def test_billable_mission_task_types_contains_canonical_mission_task() -> None:
    assert BILLABLE_MISSION_TASK_TYPES == frozenset({"mission"})


def test_legacy_mission_policy_ids_are_not_billable_task_types() -> None:
    assert "deep_research" not in BILLABLE_MISSION_TASK_TYPES
    assert "literature_search" not in BILLABLE_MISSION_TASK_TYPES


def test_calculate_token_billing_charge_applies_free_quota() -> None:
    policy = TokenBillingPolicy(
        enabled=True,
        free_tokens=1000,
        tokens_per_credit=500,
        max_overdraft_credits=100,
    )

    charge = calculate_token_billing_charge(
        policy=policy,
        total_tokens=800,
        historical_tokens_before=700,
    )

    assert charge.free_tokens_applied == 300
    assert charge.billable_tokens == 500
    assert charge.credits_to_charge == 1
    assert charge.historical_tokens_after == 1500


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


def test_calculate_sandbox_estimate_charges_startup_and_billable_minutes() -> None:
    estimate = calculate_sandbox_estimate(
        {
            "operation": "run_python",
            "startup_fee_credits": 10,
            "tiers": [
                {"tier": "1gb_1vcpu", "credits_per_minute": 5},
                {"tier": "4gb_2vcpu", "credits_per_minute": 15},
            ],
            "default_tier": "1gb_1vcpu",
            "minimum_billable_seconds": 30,
            "max_charge_credits": 300,
        },
        operation="run_python",
        duration_seconds=31,
    )

    assert estimate.credits == 15
    assert estimate.billable_seconds == 60
    assert estimate.tier == "1gb_1vcpu"


def test_get_workflow_costs_exposes_token_policies_only() -> None:
    costs = get_workflow_costs()

    assert set(costs) == {
        "thread_token_billing",
        "mission_token_billing",
        "sandbox_operation_billing",
    }
    assert costs["thread_token_billing"]["tokens_per_credit"] > 0
    assert costs["mission_token_billing"]["tokens_per_credit"] > 0
    assert costs["sandbox_operation_billing"]["run_python_credits"] > 0


def test_get_public_workflow_costs_hides_token_policy_details() -> None:
    costs = get_public_workflow_costs()

    assert set(costs) == {"thread", "mission", "sandbox_run_python"}
    assert costs["thread"] == {
        "enabled": True,
        "unit": "credits",
        "pricing": "usage_based",
    }
    assert costs["mission"] == {
        "enabled": True,
        "unit": "credits",
        "pricing": "usage_based",
    }
    assert costs["sandbox_run_python"]["unit"] == "credits"
    assert costs["sandbox_run_python"]["credits"] == 1
    assert "tokens_per_credit" not in costs["thread"]
    assert "free_tokens" not in costs["mission"]


def test_sandbox_operation_policy_uses_fixed_credit_unit() -> None:
    policy = get_sandbox_operation_billing_policy()

    assert isinstance(policy, OperationBillingPolicy)
    assert policy.enabled is True
    assert policy.run_python_credits == 1
    assert policy.max_overdraft_credits == 100
