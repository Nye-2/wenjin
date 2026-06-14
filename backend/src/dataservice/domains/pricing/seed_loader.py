"""Default pricing policy seed loader."""

from __future__ import annotations

import logging

from src.database.models.pricing_policy import PricingPolicyKind
from src.dataservice.domains.pricing.contracts import PricingPolicyCreateCommand
from src.dataservice.domains.pricing.service import DataServicePricingPolicyService

logger = logging.getLogger(__name__)

DEFAULT_GLOBAL_CREDIT_POLICY_KEY = "default-global-credit"
DEFAULT_MODEL_USAGE_POLICY_KEY = "default-model-usage"
DEFAULT_CAPABILITY_POLICY_KEY = "default-capability"
DEFAULT_TOOL_POLICY_KEY = "default-tool"
DEFAULT_SANDBOX_POLICY_KEY = "default-sandbox"


class DataServicePricingPolicySeedLoader:
    """Seed canonical billing facts needed before model catalog bootstrap."""

    def __init__(
        self,
        service: DataServicePricingPolicyService,
        *,
        admin_id: str | None = None,
    ) -> None:
        self.service = service
        self.admin_id = admin_id

    async def load_defaults(self) -> int:
        loaded = 0
        for command in default_pricing_policy_commands():
            existing = await self.service.get_policy(command.policy_key)
            if existing is not None:
                continue
            await self.service.create_policy(command, admin_id=self.admin_id)
            loaded += 1
        if loaded:
            logger.info("Loaded %d default pricing policy seed(s)", loaded)
        return loaded


def default_pricing_policy_commands() -> list[PricingPolicyCreateCommand]:
    """Return stable default policies for first-run bootstrap."""

    return [
        PricingPolicyCreateCommand(
            policy_key=DEFAULT_GLOBAL_CREDIT_POLICY_KEY,
            policy_kind=PricingPolicyKind.GLOBAL_CREDIT.value,
            name="Default global credit anchor",
            config={
                "credits_per_cny": 10,
                "usd_to_cny": 7.3,
                "target_margin_floor": 0.9,
                "show_token_details_to_users": False,
            },
        ),
        PricingPolicyCreateCommand(
            policy_key=DEFAULT_MODEL_USAGE_POLICY_KEY,
            policy_kind=PricingPolicyKind.MODEL_USAGE.value,
            name="Default model usage",
            config={
                "input_weight": 0.3,
                "cached_input_weight": 0.05,
                "output_weight": 1.0,
                "reasoning_weight": 1.0,
                "credits_per_1k_weighted_tokens": 6,
                "min_chat_credits": 3,
                "min_feature_model_credits": 10,
                "cost_guard_multiplier": 20,
                "raw_cost": {
                    "input_usd_per_1m": 0,
                    "cached_input_usd_per_1m": 0,
                    "output_usd_per_1m": 0,
                    "reasoning_usd_per_1m": 0,
                },
                "free_tokens": 0,
                "max_overdraft_credits": 100,
            },
        ),
        PricingPolicyCreateCommand(
            policy_key=DEFAULT_CAPABILITY_POLICY_KEY,
            policy_kind=PricingPolicyKind.CAPABILITY.value,
            name="Default capability reserve",
            config={
                "base_fee_credits": 0,
                "estimate_min_credits": 0,
                "estimate_max_credits": 0,
                "max_charge_credits": 0,
                "included_revision_loops": 0,
                "platform_failed_refund": "full",
                "user_cancel_policy": "settle_completed_usage",
            },
        ),
        PricingPolicyCreateCommand(
            policy_key=DEFAULT_TOOL_POLICY_KEY,
            policy_kind=PricingPolicyKind.TOOL.value,
            name="Default tool operation",
            config={
                "tool_key": "default",
                "base_credits": 0,
            },
        ),
        PricingPolicyCreateCommand(
            policy_key=DEFAULT_SANDBOX_POLICY_KEY,
            policy_kind=PricingPolicyKind.SANDBOX.value,
            name="Default workspace sandbox",
            config={
                "operation": "workspace_sandbox",
                "startup_fee_credits": 5,
                "minimum_billable_seconds": 60,
                "max_charge_credits": 120,
                "default_tier": "standard",
                "tiers": {
                    "standard": {
                        "credits_per_minute": 1,
                    }
                },
            },
        ),
    ]
