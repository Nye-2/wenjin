"""Service layer for documents v2."""

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.document_v2 import DocumentV2

logger = logging.getLogger(__name__)


class DocumentsService:
    """CRUD for documents_v2."""

    def __init__(
        self,
        db: AsyncSession,
        model: type[DocumentV2] = DocumentV2,
    ) -> None:
        self.db = db
        self._model = model

    async def add(self, workspace_id: str, data: dict[str, Any]) -> DocumentV2:
        """Add a new document (version 1)."""
        row = self._model(
            id=str(uuid4()),
            workspace_id=workspace_id,
            version=1,
            **data,
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def commit_version(
        self, workspace_id: str, parent_id: str, data: dict[str, Any]
    ) -> DocumentV2:
        """Create a new version of a document linked to parent_id.

        The new document gets parent_id set and version = parent.version + 1.
        """
        parent = await self.get(workspace_id, parent_id)
        if parent is None:
            raise ValueError(f"Parent document {parent_id} not found")

        row = self._model(
            id=str(uuid4()),
            workspace_id=workspace_id,
            parent_id=parent_id,
            version=parent.version + 1,
            **data,
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def list(
        self, workspace_id: str, limit: int = 100
    ) -> list[DocumentV2]:
        """List non-deleted documents for a workspace."""
        result = await self.db.execute(
            select(self._model)
            .where(
                self._model.workspace_id == workspace_id,
                self._model.deleted_at.is_(None),
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get(
        self, workspace_id: str, doc_id: str
    ) -> DocumentV2 | None:
        """Get a single non-deleted document."""
        result = await self.db.execute(
            select(self._model).where(
                self._model.id == doc_id,
                self._model.workspace_id == workspace_id,
                self._model.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def delete(self, workspace_id: str, doc_id: str) -> bool:
        """Soft-delete a document. Returns True if found."""
        doc = await self.get(workspace_id, doc_id)
        if doc is None:
            return False
        doc.deleted_at = datetime.now(timezone.utc)
        await self.db.commit()
        return True
