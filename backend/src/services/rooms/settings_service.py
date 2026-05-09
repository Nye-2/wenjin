"""Service layer for workspace settings (1:1 with workspaces)."""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.workspace_settings import WorkspaceSettings

logger = logging.getLogger(__name__)

# Default values matching the spec §4.4.8
_DEFAULTS = {
    "thinking_enabled": True,
    "sandbox_provider": "local",
    "auto_compact_threshold": 0.8,
    "capability_overrides": {},
    "metadata_json": {},
}


class WorkspaceSettingsService:
    """CRUD and mutation helpers for workspace_settings."""

    def __init__(
        self,
        db: AsyncSession,
        model: type[WorkspaceSettings] = WorkspaceSettings,
    ) -> None:
        self.db = db
        self._model = model

    async def get_or_create(self, workspace_id: str) -> WorkspaceSettings:
        """Fetch existing settings for a workspace, or create with defaults.

        Returns the (possibly newly-created) WorkspaceSettings row.
        """
        result = await self.db.execute(
            select(self._model).where(
                self._model.workspace_id == workspace_id
            )
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return row

        row = self._model(
            workspace_id=workspace_id,
            thinking_enabled=_DEFAULTS["thinking_enabled"],
            sandbox_provider=_DEFAULTS["sandbox_provider"],
            auto_compact_threshold=_DEFAULTS["auto_compact_threshold"],
            capability_overrides=_DEFAULTS["capability_overrides"],
            metadata_json=_DEFAULTS["metadata_json"],
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def update(
        self,
        workspace_id: str,
        **kwargs: Any,
    ) -> WorkspaceSettings | None:
        """Update one or more settings fields for a workspace.

        Accepts keyword arguments matching WorkspaceSettings column names.
        Returns the updated row, or None if the workspace has no settings row.

        Example::

            await service.update("ws-123", default_model="claude-opus-4-7")
        """
        result = await self.db.execute(
            select(self._model).where(
                self._model.workspace_id == workspace_id
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None

        changed = False
        for key, value in kwargs.items():
            if hasattr(row, key) and getattr(row, key) != value:
                setattr(row, key, value)
                changed = True

        if changed:
            await self.db.commit()
            await self.db.refresh(row)

        return row

    async def get(self, workspace_id: str) -> WorkspaceSettings | None:
        """Fetch settings for a workspace, returning None if absent."""
        result = await self.db.execute(
            select(self._model).where(
                self._model.workspace_id == workspace_id
            )
        )
        return result.scalar_one_or_none()

    async def delete(self, workspace_id: str) -> bool:
        """Delete settings for a workspace. Returns True if a row was removed."""
        result = await self.db.execute(
            select(self._model).where(
                self._model.workspace_id == workspace_id
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return False
        await self.db.delete(row)
        await self.db.commit()
        return True
