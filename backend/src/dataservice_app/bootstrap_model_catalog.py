"""Bootstrap helpers for DataService-managed model catalog records."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.model_catalog.seed_loader import DataServiceModelCatalogSeedLoader
from src.dataservice.domains.model_catalog.service import DataServiceModelCatalogService
from src.dataservice.domains.pricing.seed_loader import (
    DEFAULT_MODEL_USAGE_POLICY_KEY,
    DataServicePricingPolicySeedLoader,
)
from src.dataservice.domains.pricing.service import DataServicePricingPolicyService


async def seed_model_catalog_from_env(
    session: AsyncSession,
    *,
    admin_id: str | None = None,
) -> int:
    """Seed model catalog once from environment-shaped model config."""
    pricing_service = DataServicePricingPolicyService(session)
    pricing_loader = DataServicePricingPolicySeedLoader(
        pricing_service,
        admin_id=admin_id,
    )
    await pricing_loader.load_defaults()

    model_service = DataServiceModelCatalogService(
        session,
        allow_private_network=True,
        require_https=False,
    )
    model_loader = DataServiceModelCatalogSeedLoader(
        model_service,
        admin_id=admin_id,
        default_pricing_policy_id=DEFAULT_MODEL_USAGE_POLICY_KEY,
    )
    return await model_loader.load_seeds_if_empty()
