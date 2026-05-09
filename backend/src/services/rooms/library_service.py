"""Service layer for library items."""

import logging
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.library_item import LibraryItem

logger = logging.getLogger(__name__)


class LibraryService:
    """CRUD for library_items."""

    def __init__(
        self,
        db: AsyncSession,
        model: type[LibraryItem] = LibraryItem,
    ) -> None:
        self.db = db
        self._model = model

    async def add(self, workspace_id: str, data: dict[str, Any]) -> LibraryItem:
        """Add a single library item."""
        row = self._model(
            id=str(uuid4()),
            workspace_id=workspace_id,
            **data,
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def bulk_add(
        self, workspace_id: str, items: list[dict[str, Any]]
    ) -> list[LibraryItem]:
        """Add multiple library items in one transaction."""
        rows = []
        for item_data in items:
            row = self._model(
                id=str(uuid4()),
                workspace_id=workspace_id,
                **item_data,
            )
            self.db.add(row)
            rows.append(row)
        await self.db.commit()
        for row in rows:
            await self.db.refresh(row)
        return rows

    async def list(self, workspace_id: str, limit: int = 100) -> list[LibraryItem]:
        """List non-deleted library items for a workspace."""
        result = await self.db.execute(
            select(self._model)
            .where(
                self._model.workspace_id == workspace_id,
                self._model.deleted_at.is_(None),
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get(self, workspace_id: str, item_id: str) -> LibraryItem | None:
        """Get a single non-deleted library item."""
        result = await self.db.execute(
            select(self._model).where(
                self._model.id == item_id,
                self._model.workspace_id == workspace_id,
                self._model.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def delete(self, workspace_id: str, item_id: str) -> bool:
        """Soft-delete a library item. Returns True if found."""
        from datetime import datetime, timezone

        item = await self.get(workspace_id, item_id)
        if item is None:
            return False
        item.deleted_at = datetime.now(timezone.utc)
        await self.db.commit()
        return True
