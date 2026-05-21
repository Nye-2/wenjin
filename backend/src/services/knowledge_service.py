"""Facade for DataService-owned user knowledge persistence."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.knowledge_api import KnowledgeDataService, normalize_knowledge_category


class KnowledgeService:
    """Compatibility facade for UserKnowledge lifecycle."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self.db = db
        self._knowledge = KnowledgeDataService(db)
        self._knowledge_no_commit = KnowledgeDataService(db, autocommit=False)

    @staticmethod
    def _normalize_category(category: Any) -> str:
        """Coerce category values without exposing ORM enums."""
        return normalize_knowledge_category(category)

    async def create(
        self,
        user_id: str,
        category: Any,
        content: str,
        confidence: float = 0.7,
        source: str | None = None,
        workspace_context: str | None = None,
    ) -> Any:
        """Create a new knowledge entry."""
        return await self._knowledge.create(
            user_id=user_id,
            category=category,
            content=content,
            confidence=confidence,
            source=source,
            workspace_context=workspace_context,
        )

    async def get(self, knowledge_id: str) -> Any | None:
        """Get knowledge by ID."""
        return await self._knowledge.get(knowledge_id)

    async def list_by_user(
        self,
        user_id: str,
        category: Any | None = None,
        min_confidence: float | None = None,
        active_only: bool = True,
    ) -> list[Any]:
        """List knowledge entries for a user."""
        return await self._knowledge.list_by_user(
            user_id=user_id,
            category=category,
            min_confidence=min_confidence,
            active_only=active_only,
        )

    async def update(
        self,
        knowledge_id: str,
        content: str | None = None,
        confidence: float | None = None,
        is_active: bool | None = None,
    ) -> Any | None:
        """Update a knowledge entry."""
        entry = await self.get(knowledge_id)
        if entry is None:
            return None
        if content is not None:
            entry.content = content
        if confidence is not None:
            entry.confidence = confidence
        if is_active is not None:
            entry.is_active = is_active
        await self._db.commit()
        await self._db.refresh(entry)
        return entry

    async def deactivate(self, knowledge_id: str) -> bool:
        """Deactivate a knowledge entry."""
        entry = await self.get(knowledge_id)
        if entry is None:
            return False
        entry.is_active = False
        await self._db.commit()
        return True

    async def delete(self, knowledge_id: str) -> bool:
        """Delete a knowledge entry."""
        entry = await self.get(knowledge_id)
        if entry is None:
            return False
        await self._db.delete(entry)
        await self._db.commit()
        return True

    async def list_active(
        self,
        user_id: str,
        *,
        workspace_context: str | None = None,
        include_global: bool = True,
        min_confidence: float = 0.5,
        limit: int = 20,
    ) -> list[Any]:
        """Return active knowledge ordered by confidence desc."""
        return await self._knowledge_no_commit.list_active(
            user_id=user_id,
            workspace_context=workspace_context,
            include_global=include_global,
            min_confidence=min_confidence,
            limit=limit,
        )

    async def upsert(
        self,
        user_id: str,
        category: Any,
        content: str,
        *,
        confidence: float = 0.7,
        source: str | None = None,
        workspace_context: str | None = None,
    ) -> Any:
        """Insert or update, boosting confidence for duplicate active content."""
        return await self._knowledge_no_commit.upsert(
            user_id=user_id,
            category=category,
            content=content,
            confidence=confidence,
            source=source,
            workspace_context=workspace_context,
        )

    async def archive_low_confidence(
        self,
        user_id: str,
        threshold: float = 0.5,
    ) -> int:
        """Deactivate entries below threshold. Returns count."""
        return await self._knowledge_no_commit.archive_low_confidence(
            user_id=user_id,
            threshold=threshold,
        )

    async def count_active(
        self,
        user_id: str,
        *,
        workspace_context: str | None = None,
        include_global: bool | None = None,
    ) -> int:
        """Count active knowledge entries for a user."""
        return await self._knowledge_no_commit.count_active(
            user_id=user_id,
            workspace_context=workspace_context,
            include_global=include_global,
        )
