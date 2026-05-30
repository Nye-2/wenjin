"""Tests for the billing policy SSOT."""

from src.services.billing_policy import (
    BILLABLE_FEATURE_TASK_TYPES,
    OperationBillingPolicy,
    TokenBillingPolicy,
    calculate_token_billing_charge,
    get_public_workflow_costs,
    get_sandbox_operation_billing_policy,
    get_workflow_costs,
)


def test_billable_feature_task_types_contains_canonical_execution_task() -> None:
    assert BILLABLE_FEATURE_TASK_TYPES == frozenset({"execution"})


def test_legacy_feature_ids_are_not_billable_task_types() -> None:
    assert "deep_research" not in BILLABLE_FEATURE_TASK_TYPES
    assert "literature_search" not in BILLABLE_FEATURE_TASK_TYPES


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


def test_get_workflow_costs_exposes_token_policies_only() -> None:
    costs = get_workflow_costs()

    assert set(costs) == {
        "thread_token_billing",
        "feature_token_billing",
        "sandbox_operation_billing",
    }
    assert costs["thread_token_billing"]["tokens_per_credit"] > 0
    assert costs["feature_token_billing"]["tokens_per_credit"] > 0
    assert costs["sandbox_operation_billing"]["run_python_credits"] > 0


def test_get_public_workflow_costs_hides_token_policy_details() -> None:
    costs = get_public_workflow_costs()

    assert set(costs) == {"thread", "feature", "sandbox_run_python"}
    assert costs["thread"] == {
        "enabled": True,
        "unit": "credits",
        "pricing": "usage_based",
    }
    assert costs["feature"] == {
        "enabled": True,
        "unit": "credits",
        "pricing": "usage_based",
    }
    assert costs["sandbox_run_python"]["unit"] == "credits"
    assert costs["sandbox_run_python"]["credits"] == 1
    assert "tokens_per_credit" not in costs["thread"]
    assert "free_tokens" not in costs["feature"]


def test_sandbox_operation_policy_uses_fixed_credit_unit() -> None:
    policy = get_sandbox_operation_billing_policy()

    assert isinstance(policy, OperationBillingPolicy)
    assert policy.enabled is True
    assert policy.run_python_credits == 1
    assert policy.max_overdraft_credits == 100
