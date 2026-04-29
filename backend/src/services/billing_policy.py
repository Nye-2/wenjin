"""Single source of truth for token-based credit billing policy."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from src.config.config_loader import get_app_config
from src.task.registry import WORKSPACE_FEATURE_TASK

BILLABLE_FEATURE_TASK_TYPES: frozenset[str] = frozenset({WORKSPACE_FEATURE_TASK})


@dataclass(frozen=True, slots=True)
class TokenBillingPolicy:
    """Token-to-credit billing parameters for one usage surface."""

    enabled: bool
    free_tokens: int
    tokens_per_credit: int
    max_overdraft_credits: int

    def as_dict(self) -> dict[str, int | bool]:
        return {
            "enabled": self.enabled,
            "free_tokens": self.free_tokens,
            "tokens_per_credit": self.tokens_per_credit,
            "max_overdraft_credits": self.max_overdraft_credits,
        }


@dataclass(frozen=True, slots=True)
class TokenBillingCharge:
    """Calculated billing delta for one token usage event."""

    free_tokens_applied: int
    billable_tokens: int
    credits_to_charge: int
    historical_tokens_after: int


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


def get_thread_token_billing_policy() -> TokenBillingPolicy:
    """Return token billing policy for the freeform thread surface."""
    return _coerce_policy(get_app_config().billing.thread, default_free_tokens=100000)


def get_feature_token_billing_policy() -> TokenBillingPolicy:
    """Return token billing policy for workspace feature tasks."""
    return _coerce_policy(get_app_config().billing.feature, default_free_tokens=0)


def calculate_token_billing_charge(
    *,
    policy: TokenBillingPolicy,
    total_tokens: int,
    historical_tokens_before: int,
) -> TokenBillingCharge:
    """Calculate token billing deltas under a cumulative free-token policy."""
    normalized_total = max(int(total_tokens or 0), 0)
    historical_before = max(int(historical_tokens_before or 0), 0)
    historical_after = historical_before + normalized_total

    if not policy.enabled or normalized_total <= 0:
        return TokenBillingCharge(
            free_tokens_applied=0,
            billable_tokens=0,
            credits_to_charge=0,
            historical_tokens_after=historical_after,
        )

    overage_before = max(historical_before - policy.free_tokens, 0)
    overage_after = max(historical_after - policy.free_tokens, 0)
    billable_tokens = max(overage_after - overage_before, 0)
    free_tokens_applied = max(normalized_total - billable_tokens, 0)
    credits_to_charge = (
        math.ceil(billable_tokens / policy.tokens_per_credit)
        if billable_tokens > 0
        else 0
    )
    return TokenBillingCharge(
        free_tokens_applied=free_tokens_applied,
        billable_tokens=billable_tokens,
        credits_to_charge=credits_to_charge,
        historical_tokens_after=historical_after,
    )


def get_workflow_costs() -> dict[str, dict[str, int | bool]]:
    """Expose public token billing policies for dashboard/API consumers."""
    return {
        "thread_token_billing": get_thread_token_billing_policy().as_dict(),
        "feature_token_billing": get_feature_token_billing_policy().as_dict(),
    }
