"""Bootstrap helpers for DataService-managed model catalog records."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.model_catalog.seed_loader import DataServiceModelCatalogSeedLoader
from src.dataservice.domains.model_catalog.service import DataServiceModelCatalogService


async def seed_model_catalog_from_env(
    session: AsyncSession,
    *,
    admin_id: str | None = None,
) -> int:
    """Seed model catalog once from environment-shaped model config."""
    model_service = DataServiceModelCatalogService(
        session,
        allow_private_network=True,
        require_https=False,
    )
    model_loader = DataServiceModelCatalogSeedLoader(
        model_service,
        admin_id=admin_id,
    )
    return await model_loader.load_seeds_if_empty()
