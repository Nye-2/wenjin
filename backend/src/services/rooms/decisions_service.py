"""Workspace decision service facade backed by DataService rooms."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.rooms_api import DecisionSetCommand, RoomsDataService


class DecisionsService:
    """Compatibility facade whose business logic lives in DataService."""

    def __init__(self, db: AsyncSession, model: object | None = None) -> None:
        self.db = db
        self._model = model
        self._rooms = RoomsDataService(db)

    async def set(
        self,
        workspace_id: str,
        key: str,
        value: str,
        extracted_by: str,
        confidence: float = 1.0,
    ):
        """Set a decision value, superseding any existing active decision for the key."""

        return await self._rooms.set_decision(
            DecisionSetCommand(
                workspace_id=workspace_id,
                key=key,
                value=value,
                extracted_by=extracted_by,
                confidence=confidence,
            )
        )

    async def get_active(self, workspace_id: str) -> dict[str, str]:
        """Get all active decisions as {key: value}."""

        return await self._rooms.list_active_decisions(workspace_id)

    async def delete(self, decision_id: str) -> bool:
        """Soft-delete a decision. Returns True if found."""

        return await self._rooms.delete_decision(decision_id)
