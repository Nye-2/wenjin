"""Service layer for workspace sandboxes."""

import logging
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.sandbox import Sandbox

logger = logging.getLogger(__name__)


class SandboxService:
    """CRUD for sandboxes."""

    def __init__(
        self,
        db: AsyncSession,
        model: type[Sandbox] = Sandbox,
    ) -> None:
        self.db = db
        self._model = model

    async def get_or_create(
        self, workspace_id: str, provider: str = "local"
    ) -> Sandbox:
        """Get existing active sandbox or create a new one.

        Returns existing if state='active', otherwise creates new.
        """
        result = await self.db.execute(
            select(self._model).where(
                self._model.workspace_id == workspace_id,
                self._model.state == "active",
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing

        row = self._model(
            workspace_id=workspace_id,
            sandbox_id=str(uuid4()),
            provider=provider,
            state="active",
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def release(self, workspace_id: str) -> Sandbox | None:
        """Set sandbox state to 'stopped'."""
        result = await self.db.execute(
            select(self._model).where(
                self._model.workspace_id == workspace_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        row.state = "stopped"
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def update_state(
        self, workspace_id: str, state: str
    ) -> Sandbox | None:
        """Update sandbox state."""
        result = await self.db.execute(
            select(self._model).where(
                self._model.workspace_id == workspace_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        row.state = state
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def touch(self, workspace_id: str) -> Sandbox | None:
        """Update last_active_at to now."""
        result = await self.db.execute(
            select(self._model).where(
                self._model.workspace_id == workspace_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        row.last_active_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(row)
        return row
