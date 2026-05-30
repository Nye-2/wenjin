"""Model catalog persistence operations."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.model_catalog import ModelCatalogEntry


class ModelCatalogRepository:
    """Repository for admin-managed model catalog entries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_model(self, values: dict[str, Any]) -> ModelCatalogEntry:
        record = ModelCatalogEntry(**values)
        self.session.add(record)
        return record

    async def get_model(self, model_id: str) -> ModelCatalogEntry | None:
        result = await self.session.execute(
            select(ModelCatalogEntry).where(ModelCatalogEntry.model_id == model_id)
        )
        return result.scalar_one_or_none()

    async def list_models(
        self,
        *,
        category: str | None = None,
        enabled_only: bool = False,
    ) -> list[ModelCatalogEntry]:
        query = select(ModelCatalogEntry)
        if category is not None:
            query = query.where(ModelCatalogEntry.category == category)
        if enabled_only:
            query = query.where(ModelCatalogEntry.enabled.is_(True))
        result = await self.session.execute(
            query.order_by(ModelCatalogEntry.category, ModelCatalogEntry.is_default.desc(), ModelCatalogEntry.model_id)
        )
        return list(result.scalars().all())

    async def unset_default_models(self, *, category: str, except_model_id: str | None = None) -> None:
        rows = await self.list_models(category=category)
        for row in rows:
            if except_model_id is not None and row.model_id == except_model_id:
                continue
            row.is_default = False

    async def count_enabled_models(self, *, category: str) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(ModelCatalogEntry)
            .where(
                ModelCatalogEntry.category == category,
                ModelCatalogEntry.enabled.is_(True),
            )
        )
        return int(result.scalar() or 0)
