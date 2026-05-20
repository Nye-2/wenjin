"""Service layer for workspace decisions."""

import logging
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.decision import Decision

logger = logging.getLogger(__name__)


class DecisionsService:
    """CRUD and mutation for decisions.

    Key business logic: set() finds the current active decision for a key,
    creates a new one, and sets the old one's superseded_by.
    """

    def __init__(
        self,
        db: AsyncSession,
        model: type[Decision] = Decision,
    ) -> None:
        self.db = db
        self._model = model

    async def set(
        self,
        workspace_id: str,
        key: str,
        value: str,
        extracted_by: str,
        confidence: float = 1.0,
    ) -> Decision:
        """Set a decision value, superseding any existing active decision for the key.

        1. Find the current active decision for (workspace_id, key).
        2. Create a new decision row.
        3. If an old active decision exists, set its superseded_by to the new id.
        """
        # Find current active decision (not deleted, not superseded)
        result = await self.db.execute(
            select(self._model).where(
                self._model.workspace_id == workspace_id,
                self._model.key == key,
                self._model.deleted_at.is_(None),
                self._model.superseded_by.is_(None),
            )
        )
        old = result.scalar_one_or_none()

        new_id = str(uuid4())
        new_row = self._model(
            id=new_id,
            workspace_id=workspace_id,
            key=key,
            value=value,
            confidence=confidence,
            extracted_by=extracted_by,
        )
        self.db.add(new_row)

        if old is not None:
            old.superseded_by = new_id

        await self.db.commit()
        await self.db.refresh(new_row)
        return new_row

    async def get(self, workspace_id: str, decision_id: str) -> Decision | None:
        """Get a single decision by id."""
        result = await self.db.execute(
            select(self._model).where(
                self._model.id == decision_id,
                self._model.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_active(self, workspace_id: str) -> dict[str, str]:
        """Get all active (non-deleted, non-superseded) decisions as {key: value}."""
        result = await self.db.execute(
            select(self._model).where(
                self._model.workspace_id == workspace_id,
                self._model.deleted_at.is_(None),
                self._model.superseded_by.is_(None),
            )
        )
        rows = result.scalars().all()
        return {row.key: row.value for row in rows}

    async def delete(self, decision_id: str) -> bool:
        """Soft-delete a decision. Returns True if found."""
        result = await self.db.execute(
            select(self._model).where(self._model.id == decision_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return False
        row.deleted_at = datetime.now(UTC)
        await self.db.commit()
        return True
