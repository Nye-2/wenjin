"""Runtime facade for credit billing policy."""

from __future__ import annotations

from typing import Any

from src.billing.policies import (
    CapabilityPricingEstimate,
    GlobalCreditPolicy,
    ModelUsageCreditCharge,
    OperationBillingPolicy,
    SandboxPricingEstimate,
    TokenBillingCharge,
    TokenBillingPolicy,
    calculate_capability_estimate,
    calculate_model_usage_credits,
    calculate_sandbox_estimate,
    calculate_token_billing_charge,
    calculate_weighted_tokens,
)
from src.config.config_loader import get_app_config

BILLABLE_FEATURE_TASK_TYPES: frozenset[str] = frozenset({"execution"})


def _coerce_policy(raw_policy: Any, *, default_free_tokens: int) -> TokenBillingPolicy:
    return TokenBillingPolicy(
        enabled=bool(getattr(raw_policy, "enabled", True)),
        free_tokens=max(int(getattr(raw_policy, "free_tokens", default_free_tokens) or 0), 0),
        tokens_per_credit=max(int(getattr(raw_policy, "tokens_per_credit", 10000) or 0), 1),
        max_overdraft_credits=max(
            int(getattr(raw_policy, "max_overdraft_credits", 100) or 0),
            0,
        ),
    )


def _coerce_operation_policy(raw_policy: Any) -> OperationBillingPolicy:
    return OperationBillingPolicy(
        enabled=bool(getattr(raw_policy, "enabled", True)),
        run_python_credits=max(int(getattr(raw_policy, "run_python_credits", 1) or 0), 0),
        max_overdraft_credits=max(
            int(getattr(raw_policy, "max_overdraft_credits", 100) or 0),
            0,
        ),
    )


def get_thread_token_billing_policy() -> TokenBillingPolicy:
    """Return token billing policy for the freeform thread surface."""
    return _coerce_policy(get_app_config().billing.thread, default_free_tokens=100000)


def get_feature_token_billing_policy() -> TokenBillingPolicy:
    """Return token billing policy for workspace feature tasks."""
    return _coerce_policy(get_app_config().billing.feature, default_free_tokens=0)


def get_sandbox_operation_billing_policy() -> OperationBillingPolicy:
    """Return fixed credit billing policy for sandbox operations."""
    return _coerce_operation_policy(get_app_config().billing.sandbox)


def get_workflow_costs() -> dict[str, dict[str, int | bool]]:
    """Expose internal billing policies for admin/diagnostics consumers."""
    return {
        "thread_token_billing": get_thread_token_billing_policy().as_dict(),
        "feature_token_billing": get_feature_token_billing_policy().as_dict(),
        "sandbox_operation_billing": get_sandbox_operation_billing_policy().as_dict(),
    }


def get_public_workflow_costs() -> dict[str, dict[str, int | str | bool]]:
    """Expose user-facing credit costs without token policy details."""
    sandbox = get_sandbox_operation_billing_policy()
    return {
        "thread": {
            "enabled": get_thread_token_billing_policy().enabled,
            "unit": "credits",
            "pricing": "usage_based",
        },
        "feature": {
            "enabled": get_feature_token_billing_policy().enabled,
            "unit": "credits",
            "pricing": "usage_based",
        },
        "sandbox_run_python": {
            "enabled": sandbox.enabled,
            "unit": "credits",
            "credits": sandbox.run_python_credits,
        },
    }


__all__ = [
    "BILLABLE_FEATURE_TASK_TYPES",
    "CapabilityPricingEstimate",
    "GlobalCreditPolicy",
    "ModelUsageCreditCharge",
    "OperationBillingPolicy",
    "SandboxPricingEstimate",
    "TokenBillingCharge",
    "TokenBillingPolicy",
    "calculate_capability_estimate",
    "calculate_model_usage_credits",
    "calculate_sandbox_estimate",
    "calculate_token_billing_charge",
    "calculate_weighted_tokens",
    "get_feature_token_billing_policy",
    "get_public_workflow_costs",
    "get_sandbox_operation_billing_policy",
    "get_thread_token_billing_policy",
    "get_workflow_costs",
]
