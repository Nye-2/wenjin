"""Canonical pricing policy resolution for runtime and public projections."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.pricing_policy import PricingPolicy, PricingPolicyKind
from src.dataservice.common.errors import DataServiceValidationError
from src.dataservice.domains.model_catalog.repository import ModelCatalogRepository
from src.dataservice.domains.pricing.repository import PricingPolicyRepository


class CanonicalPricingResolver:
    """Resolve every billable surface from persisted DataService bindings."""

    def __init__(self, session: AsyncSession) -> None:
        self._models = ModelCatalogRepository(session)
        self._policies = PricingPolicyRepository(session)

    async def resolve_model_usage(self, model_id: str) -> PricingPolicy:
        model = await self._models.get_model(model_id)
        if model is None or not model.enabled:
            raise DataServiceValidationError(
                "Enabled model catalog entry is required for pricing",
                detail={"model_id": model_id},
            )
        policy_id = str(model.pricing_policy_id or "").strip()
        if not policy_id:
            raise DataServiceValidationError(
                "Model catalog entry has no pricing policy binding",
                detail={"model_id": model_id},
            )
        policy = await self._policies.get_policy(policy_id)
        if (
            policy is None
            or not policy.enabled
            or _kind_value(policy.policy_kind) != PricingPolicyKind.MODEL_USAGE.value
        ):
            raise DataServiceValidationError(
                "Model pricing policy binding is unavailable",
                detail={"model_id": model_id, "pricing_policy_id": policy_id},
            )
        return policy

    async def resolve_global_credit(self) -> PricingPolicy | None:
        policies = await self._policies.list_policies(
            policy_kind=PricingPolicyKind.GLOBAL_CREDIT.value,
            enabled_only=True,
        )
        if not policies:
            return None
        if len(policies) > 1:
            raise DataServiceValidationError(
                "Exactly one enabled global credit policy is required",
                detail={"enabled_policy_keys": [policy.policy_key for policy in policies]},
            )
        return policies[0]

    async def resolve_mission(
        self,
        *,
        workspace_type: str,
        mission_policy_id: str | None,
    ) -> PricingPolicy:
        policies = await self._policies.list_policies(
            policy_kind=PricingPolicyKind.MISSION.value,
            enabled_only=True,
        )
        normalized_policy_id = str(mission_policy_id or "").strip()
        normalized_workspace = str(workspace_type or "").strip()
        exact_workspace: list[PricingPolicy] = []
        exact_global: list[PricingPolicy] = []
        workspace_defaults: list[PricingPolicy] = []
        global_defaults: list[PricingPolicy] = []
        for policy in policies:
            config = dict(policy.config_json or {})
            policy_mission = str(config.get("mission_policy_id") or "").strip()
            policy_workspace = str(config.get("workspace_type") or "").strip()
            if normalized_policy_id and policy_mission == normalized_policy_id:
                if policy_workspace == normalized_workspace:
                    exact_workspace.append(policy)
                elif not policy_workspace:
                    exact_global.append(policy)
            elif not policy_mission and policy_workspace == normalized_workspace:
                workspace_defaults.append(policy)
            elif not policy_mission and not policy_workspace:
                global_defaults.append(policy)
        for candidates, scope in (
            (exact_workspace, "mission_workspace"),
            (exact_global, "mission_global"),
            (workspace_defaults, "workspace"),
            (global_defaults, "global"),
        ):
            if len(candidates) > 1:
                raise DataServiceValidationError(
                    "Mission pricing policy binding is ambiguous",
                    detail={
                        "scope": scope,
                        "workspace_type": normalized_workspace,
                        "mission_policy_id": normalized_policy_id,
                        "policy_keys": [policy.policy_key for policy in candidates],
                    },
                )
            if candidates:
                return candidates[0]
        raise DataServiceValidationError(
            "No enabled Mission pricing policy matches this Mission",
            detail={
                "workspace_type": normalized_workspace,
                "mission_policy_id": normalized_policy_id,
            },
        )


def _kind_value(value: object) -> str:
    return str(value.value if hasattr(value, "value") else value)


__all__ = ["CanonicalPricingResolver"]
