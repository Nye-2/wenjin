"""Pricing policy domain service."""

from __future__ import annotations

import math
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.pricing.contracts import (
    ModelUsagePolicyConfig,
    PricingSimulationRequest,
    PricingSimulationResult,
)


class DataServicePricingPolicyService:
    """DataService-owned pricing policy operations and simulator."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self.session = session
        self.autocommit = autocommit

    def simulate(self, request: PricingSimulationRequest) -> PricingSimulationResult:
        if request.policy_kind == "model_usage":
            return self._simulate_model_usage(request)
        return PricingSimulationResult(
            charge_credits=0,
            breakdown={"policy_kind": request.policy_kind},
        )

    def _simulate_model_usage(self, request: PricingSimulationRequest) -> PricingSimulationResult:
        policy = request.model_usage_policy or ModelUsagePolicyConfig()
        weighted_tokens = (
            request.prompt_tokens * policy.prompt_token_weight
            + request.completion_tokens * policy.completion_token_weight
        )
        weighted_credits = math.ceil(weighted_tokens / policy.tokens_per_credit)
        raw_cost_cny = (
            request.prompt_tokens / 1000 * policy.input_cny_per_1k_tokens
            + request.completion_tokens / 1000 * policy.output_cny_per_1k_tokens
        )
        raw_cost_guard_credits = math.ceil(raw_cost_cny * request.global_policy.credits_per_cny * policy.raw_cost_markup)
        charge_credits = max(policy.minimum_credits, weighted_credits, raw_cost_guard_credits)
        revenue_cny = charge_credits / request.global_policy.credits_per_cny
        return PricingSimulationResult(
            charge_credits=charge_credits,
            raw_cost_cny=raw_cost_cny,
            margin_cny=revenue_cny - raw_cost_cny,
            breakdown={
                "weighted_tokens": weighted_tokens,
                "weighted_credits": weighted_credits,
                "raw_cost_guard_credits": raw_cost_guard_credits,
            },
        )


def pricing_result_to_dict(result: PricingSimulationResult) -> dict[str, Any]:
    return result.model_dump(mode="json")
