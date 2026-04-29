"""Tests for the billing policy SSOT."""

from src.services.billing_policy import (
    BILLABLE_FEATURE_TASK_TYPES,
    TokenBillingPolicy,
    calculate_token_billing_charge,
    get_workflow_costs,
)


def test_billable_feature_task_types_contains_canonical_workspace_feature_task() -> None:
    assert BILLABLE_FEATURE_TASK_TYPES == frozenset({"workspace_feature"})


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

    assert set(costs) == {"thread_token_billing", "feature_token_billing"}
    assert costs["thread_token_billing"]["tokens_per_credit"] > 0
    assert costs["feature_token_billing"]["tokens_per_credit"] > 0
