"""Workspace memory service facade backed by DataService rooms."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.rooms_api import MemoryFactCreateCommand, RoomsDataService


class FactCreate:
    """Simple data carrier for creating memory facts."""

    def __init__(
        self,
        category: str,
        content: str,
        confidence: float = 1.0,
    ) -> None:
        self.category = category
        self.content = content
        self.confidence = confidence


class MemoryService:
    """Compatibility facade whose business logic lives in DataService."""

    def __init__(self, db: AsyncSession, model: object | None = None) -> None:
        self.db = db
        self._model = model
        self._rooms = RoomsDataService(db)

    async def add_facts(self, workspace_id: str, facts: list[FactCreate]):
        """Bulk-insert memory facts."""

        return await self._rooms.add_memory_facts(
            [
                MemoryFactCreateCommand(
                    workspace_id=workspace_id,
                    category=fact.category,
                    content=fact.content,
                    confidence=fact.confidence,
                )
                for fact in facts
            ]
        )

    async def top(self, workspace_id: str, k: int = 15, category: str | None = None):
        """Get top-k facts ordered by reference_count DESC, confidence DESC."""

        return await self._rooms.list_memory_facts(workspace_id=workspace_id, limit=k, category=category)

    async def mark_referenced(self, fact_id: str):
        """Increment reference_count and update last_referenced_at."""

        return await self._rooms.mark_memory_fact_referenced(fact_id)

    async def evict_excess(self, workspace_id: str, max_count: int = 100) -> int:
        """Delete lowest-priority facts until count <= max_count."""

        return await self._rooms.evict_excess_memory_facts(workspace_id, max_count=max_count)

    async def delete(self, workspace_id: str, fact_id: str) -> bool:
        """Soft-delete a memory fact."""

        return await self._rooms.soft_delete_memory_fact(workspace_id=workspace_id, fact_id=fact_id)
