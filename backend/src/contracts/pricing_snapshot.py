"""Frozen pricing contracts for deterministic in-flight settlement."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PricingPolicySnapshot(_FrozenModel):
    id: str = Field(min_length=1, max_length=36)
    policy_key: str = Field(min_length=1, max_length=120)
    version: int = Field(ge=1)
    config: dict[str, Any]


class ModelPricingSnapshot(_FrozenModel):
    model_policy: PricingPolicySnapshot
    global_policy: PricingPolicySnapshot | None


class ChatTurnPricingSnapshot(ModelPricingSnapshot):
    authorization: dict[str, int]


class MissionPricingSnapshot(ModelPricingSnapshot):
    mission_policy: PricingPolicySnapshot


def freeze_pricing_policy(
    policy: Any,
    *,
    config: BaseModel,
) -> PricingPolicySnapshot:
    """Freeze an already-validated DataService policy row."""

    return PricingPolicySnapshot(
        id=str(policy.id),
        policy_key=str(policy.policy_key),
        version=int(policy.version or 1),
        config=config.model_dump(mode="json"),
    )


__all__ = [
    "ChatTurnPricingSnapshot",
    "MissionPricingSnapshot",
    "ModelPricingSnapshot",
    "PricingPolicySnapshot",
    "freeze_pricing_policy",
]
