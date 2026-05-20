"""Service layer for workspace memory facts."""

import logging
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.memory_fact import MemoryFact

logger = logging.getLogger(__name__)


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
    """CRUD and ranking for memory_facts."""

    def __init__(
        self,
        db: AsyncSession,
        model: type[MemoryFact] = MemoryFact,
    ) -> None:
        self.db = db
        self._model = model

    async def add_facts(
        self, workspace_id: str, facts: list[FactCreate]
    ) -> list[MemoryFact]:
        """Bulk-insert memory facts."""
        rows = []
        for fact in facts:
            row = self._model(
                id=str(uuid4()),
                workspace_id=workspace_id,
                category=fact.category,
                content=fact.content,
                confidence=fact.confidence,
            )
            self.db.add(row)
            rows.append(row)
        await self.db.commit()
        for row in rows:
            await self.db.refresh(row)
        return rows

    async def top(
        self, workspace_id: str, k: int = 15, category: str | None = None
    ) -> list[MemoryFact]:
        """Get top-k facts ordered by reference_count DESC, confidence DESC."""
        stmt = (
            select(self._model)
            .where(
                self._model.workspace_id == workspace_id,
                self._model.deleted_at.is_(None),
            )
            .order_by(self._model.reference_count.desc(), self._model.confidence.desc())
            .limit(k)
        )
        if category is not None:
            stmt = stmt.where(self._model.category == category)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def mark_referenced(self, fact_id: str) -> MemoryFact | None:
        """Increment reference_count and update last_referenced_at."""
        result = await self.db.execute(
            select(self._model).where(self._model.id == fact_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        row.reference_count = (row.reference_count or 0) + 1
        row.last_referenced_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def evict_excess(self, workspace_id: str, max_count: int = 100) -> int:
        """Delete lowest-priority facts until count <= max_count.

        Priority: reference_count ASC, created_at ASC (oldest, least-referenced first).
        Returns number of facts evicted.
        """
        # Count current non-deleted facts
        count_result = await self.db.execute(
            select(func.count()).select_from(self._model).where(
                self._model.workspace_id == workspace_id,
                self._model.deleted_at.is_(None),
            )
        )
        current_count = count_result.scalar_one()

        if current_count <= max_count:
            return 0

        to_evict = current_count - max_count

        # Find lowest-priority facts
        result = await self.db.execute(
            select(self._model)
            .where(
                self._model.workspace_id == workspace_id,
                self._model.deleted_at.is_(None),
            )
            .order_by(
                self._model.reference_count.asc(),
                self._model.created_at.asc(),
            )
            .limit(to_evict)
        )
        victims = result.scalars().all()

        now = datetime.now(UTC)
        for v in victims:
            v.deleted_at = now

        await self.db.commit()
        return len(victims)
