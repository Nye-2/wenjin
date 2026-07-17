"""Tests for canonical pricing resolution and public projection."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.database.models.pricing_policy import PricingPolicyKind
from src.dataservice.common.errors import DataServiceValidationError
from src.dataservice.domains.pricing.resolver import CanonicalPricingResolver
from src.dataservice.domains.pricing.service import DataServicePricingPolicyService


def _policy(
    key: str,
    kind: PricingPolicyKind,
    *,
    config: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=f"id-{key}",
        policy_key=key,
        name=key,
        policy_kind=kind,
        enabled=True,
        version=2,
        config_json=dict(config or {}),
    )


@pytest.mark.asyncio
async def test_model_usage_resolution_follows_catalog_binding() -> None:
    resolver = CanonicalPricingResolver(MagicMock())
    resolver._models = SimpleNamespace(
        get_model=AsyncMock(
            return_value=SimpleNamespace(
                model_id="gpt-5.6-terra",
                enabled=True,
                pricing_policy_id="terra-policy",
            )
        )
    )
    bound = _policy("terra-policy", PricingPolicyKind.MODEL_USAGE)
    resolver._policies = SimpleNamespace(get_policy=AsyncMock(return_value=bound))

    assert await resolver.resolve_model_usage("gpt-5.6-terra") is bound
    resolver._policies.get_policy.assert_awaited_once_with("terra-policy")


@pytest.mark.asyncio
async def test_model_usage_resolution_rejects_wrong_policy_kind() -> None:
    resolver = CanonicalPricingResolver(MagicMock())
    resolver._models = SimpleNamespace(
        get_model=AsyncMock(
            return_value=SimpleNamespace(
                model_id="gpt-5.6-terra",
                enabled=True,
                pricing_policy_id="mission-policy",
            )
        )
    )
    resolver._policies = SimpleNamespace(
        get_policy=AsyncMock(
            return_value=_policy("mission-policy", PricingPolicyKind.MISSION)
        )
    )

    with pytest.raises(DataServiceValidationError, match="binding is unavailable"):
        await resolver.resolve_model_usage("gpt-5.6-terra")


@pytest.mark.asyncio
async def test_mission_resolution_rejects_ambiguous_exact_bindings() -> None:
    resolver = CanonicalPricingResolver(MagicMock())
    config = {"workspace_type": "sci", "mission_policy_id": "sci-paper"}
    resolver._policies = SimpleNamespace(
        list_policies=AsyncMock(
            return_value=[
                _policy("sci-a", PricingPolicyKind.MISSION, config=config),
                _policy("sci-b", PricingPolicyKind.MISSION, config=config),
            ]
        )
    )

    with pytest.raises(DataServiceValidationError, match="ambiguous"):
        await resolver.resolve_mission(
            workspace_type="sci",
            mission_policy_id="sci-paper",
        )


@pytest.mark.asyncio
async def test_mission_resolution_prefers_workspace_specific_exact_binding() -> None:
    resolver = CanonicalPricingResolver(MagicMock())
    exact_global = _policy(
        "paper-global",
        PricingPolicyKind.MISSION,
        config={"mission_policy_id": "sci-paper"},
    )
    exact_workspace = _policy(
        "paper-sci",
        PricingPolicyKind.MISSION,
        config={"workspace_type": "sci", "mission_policy_id": "sci-paper"},
    )
    resolver._policies = SimpleNamespace(
        list_policies=AsyncMock(return_value=[exact_global, exact_workspace])
    )

    resolved = await resolver.resolve_mission(
        workspace_type="sci",
        mission_policy_id="sci-paper",
    )

    assert resolved is exact_workspace


@pytest.mark.asyncio
async def test_mission_resolution_without_policy_id_uses_workspace_default() -> None:
    resolver = CanonicalPricingResolver(MagicMock())
    global_default = _policy("global", PricingPolicyKind.MISSION)
    workspace_default = _policy(
        "sci",
        PricingPolicyKind.MISSION,
        config={"workspace_type": "sci"},
    )
    resolver._policies = SimpleNamespace(
        list_policies=AsyncMock(return_value=[global_default, workspace_default])
    )

    resolved = await resolver.resolve_mission(
        workspace_type="sci",
        mission_policy_id=None,
    )

    assert resolved is workspace_default


@pytest.mark.asyncio
async def test_public_catalog_projects_bound_models_and_missions() -> None:
    service = DataServicePricingPolicyService(MagicMock(), autocommit=False)
    model = SimpleNamespace(
        model_id="gpt-5.6-terra",
        display_name="GPT-5.6 Terra",
        is_default=True,
    )
    model_policy = _policy(
        "terra-policy",
        PricingPolicyKind.MODEL_USAGE,
        config={"min_chat_credits": 3},
    )
    mission_policy = _policy(
        "sci-default",
        PricingPolicyKind.MISSION,
        config={
            "workspace_type": "sci",
            "base_fee_credits": 0,
            "estimate_min_credits": 10,
            "estimate_max_credits": 40,
            "max_charge_credits": 60,
        },
    )
    service.models = SimpleNamespace(list_models=AsyncMock(return_value=[model]))
    service.resolver = SimpleNamespace(
        resolve_model_usage=AsyncMock(return_value=model_policy)
    )
    service.repository = SimpleNamespace(
        list_policies=AsyncMock(return_value=[mission_policy])
    )

    catalog = await service.get_public_catalog()

    assert catalog.chat_models[0].model_id == "gpt-5.6-terra"
    assert catalog.chat_models[0].minimum_credits == 3
    assert catalog.missions[0].workspace_type == "sci"
    assert catalog.missions[0].estimate_max_credits == 40


@pytest.mark.asyncio
async def test_runtime_model_pricing_bundle_uses_canonical_resolver() -> None:
    service = DataServicePricingPolicyService(MagicMock(), autocommit=False)
    model_policy = _policy("terra", PricingPolicyKind.MODEL_USAGE)
    global_policy = _policy("global", PricingPolicyKind.GLOBAL_CREDIT)
    service.resolver = SimpleNamespace(
        resolve_model_usage=AsyncMock(return_value=model_policy),
        resolve_global_credit=AsyncMock(return_value=global_policy),
    )

    resolved = await service.resolve_model_usage_pricing("gpt-5.6-terra")

    assert resolved.model_id == "gpt-5.6-terra"
    assert resolved.model_policy.policy_key == "terra"
    assert resolved.global_policy is not None
    assert resolved.global_policy.policy_key == "global"
