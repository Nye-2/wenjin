"""Tests for DataService pricing policy domain."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.dataservice.domains.pricing.contracts import (
    CapabilityPricingPolicyConfig,
    GlobalCreditPolicyConfig,
    ModelUsagePolicyConfig,
    PricingSimulationRequest,
    SandboxPricingPolicyConfig,
)
from src.dataservice.domains.pricing.service import DataServicePricingPolicyService


def test_global_credit_policy_accepts_positive_exchange_rate() -> None:
    policy = GlobalCreditPolicyConfig(credits_per_cny=10)

    assert policy.credits_per_cny == 10


def test_model_usage_policy_calculates_weighted_tokens() -> None:
    service = DataServicePricingPolicyService(None, autocommit=False)  # type: ignore[arg-type]
    policy = ModelUsagePolicyConfig(tokens_per_credit=1000, prompt_token_weight=1, completion_token_weight=4)

    result = service.simulate(
        PricingSimulationRequest(
            policy_kind="model_usage",
            global_policy=GlobalCreditPolicyConfig(credits_per_cny=10),
            model_usage_policy=policy,
            prompt_tokens=1000,
            completion_tokens=500,
        )
    )

    assert result.charge_credits == 3
    assert result.breakdown["weighted_tokens"] == 3000


def test_raw_cost_guard_can_dominate_weighted_token_price() -> None:
    service = DataServicePricingPolicyService(None, autocommit=False)  # type: ignore[arg-type]
    policy = ModelUsagePolicyConfig(
        tokens_per_credit=1000000,
        prompt_token_weight=1,
        completion_token_weight=1,
        input_cny_per_1k_tokens=1.0,
        output_cny_per_1k_tokens=9.0,
        raw_cost_markup=2.0,
    )

    result = service.simulate(
        PricingSimulationRequest(
            policy_kind="model_usage",
            global_policy=GlobalCreditPolicyConfig(credits_per_cny=10),
            model_usage_policy=policy,
            prompt_tokens=1000,
            completion_tokens=1000,
        )
    )

    assert result.raw_cost_cny == 10
    assert result.charge_credits == 200
    assert result.breakdown["raw_cost_guard_credits"] == 200


def test_invalid_negative_rates_are_rejected() -> None:
    with pytest.raises(ValidationError):
        GlobalCreditPolicyConfig(credits_per_cny=-1)
    with pytest.raises(ValidationError):
        ModelUsagePolicyConfig(tokens_per_credit=-100)


def test_capability_policy_requires_max_charge_not_below_estimate() -> None:
    with pytest.raises(ValidationError):
        CapabilityPricingPolicyConfig(estimate_max_credits=20, max_charge_credits=10)


def test_sandbox_policy_requires_at_least_one_tier() -> None:
    with pytest.raises(ValidationError):
        SandboxPricingPolicyConfig(tiers={})
