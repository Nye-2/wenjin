"""Knowledge memory command/query service."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.knowledge.repository import KnowledgeRepository


class DataServiceKnowledgeService:
    """DataService-owned user knowledge lifecycle operations."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self.session = session
        self.autocommit = autocommit
        self.repository = KnowledgeRepository(session)

    @staticmethod
    def normalize_category(category: Any) -> str:
        return KnowledgeRepository.normalize_category(category).value

    async def create(
        self,
        *,
        user_id: str,
        category: Any,
        content: str,
        confidence: float = 0.7,
        source: str | None = None,
        workspace_context: str | None = None,
    ) -> Any:
        entry = self.repository.create_entry(
            {
                "user_id": user_id,
                "category": self.repository.normalize_category(category),
                "content": content,
                "confidence": confidence,
                "source": source,
                "workspace_context": workspace_context,
            }
        )
        await self._finish(entry)
        return entry

    async def get(self, knowledge_id: str) -> Any | None:
        return await self.repository.get(knowledge_id)

    async def list_by_user(
        self,
        *,
        user_id: str,
        category: Any | None = None,
        min_confidence: float | None = None,
        active_only: bool = True,
    ) -> list[Any]:
        return await self.repository.list_by_user(
            user_id=user_id,
            category=category,
            min_confidence=min_confidence,
            active_only=active_only,
        )

    async def update(
        self,
        *,
        knowledge_id: str,
        content: str | None = None,
        confidence: float | None = None,
        is_active: bool | None = None,
    ) -> Any | None:
        entry = await self.repository.get(knowledge_id)
        if entry is None:
            return None
        if content is not None:
            entry.content = content
        if confidence is not None:
            entry.confidence = confidence
        if is_active is not None:
            entry.is_active = is_active
        await self._finish(entry)
        return entry

    async def deactivate(self, knowledge_id: str) -> bool:
        entry = await self.repository.get(knowledge_id)
        if entry is None:
            return False
        entry.is_active = False
        await self._finish(entry)
        return True

    async def delete(self, knowledge_id: str) -> bool:
        entry = await self.repository.get(knowledge_id)
        if entry is None:
            return False
        await self.session.delete(entry)
        await self._finish()
        return True

    async def list_active(
        self,
        *,
        user_id: str,
        workspace_context: str | None = None,
        include_global: bool = True,
        min_confidence: float = 0.5,
        limit: int = 20,
    ) -> list[Any]:
        return await self.repository.list_active(
            user_id=user_id,
            workspace_context=workspace_context,
            include_global=include_global,
            min_confidence=min_confidence,
            limit=limit,
        )

    async def upsert(
        self,
        *,
        user_id: str,
        category: Any,
        content: str,
        confidence: float = 0.7,
        source: str | None = None,
        workspace_context: str | None = None,
    ) -> Any:
        existing = await self.repository.find_duplicate(
            user_id=user_id,
            category=category,
            content=content,
            workspace_context=workspace_context,
        )
        if existing:
            existing.boost_confidence(0.1)
            existing.source = source or existing.source
            await self.session.flush()
            return existing

        entry = self.repository.create_entry(
            {
                "user_id": user_id,
                "category": self.repository.normalize_category(category),
                "content": content,
                "confidence": confidence,
                "source": source,
                "workspace_context": workspace_context,
            }
        )
        await self.session.flush()
        return entry

    async def archive_low_confidence(self, *, user_id: str, threshold: float = 0.5) -> int:
        entries = await self.repository.list_low_confidence(
            user_id=user_id,
            threshold=threshold,
        )
        for entry in entries:
            entry.is_active = False
        await self.session.flush()
        return len(entries)

    async def count_active(
        self,
        *,
        user_id: str,
        workspace_context: str | None = None,
        include_global: bool | None = None,
    ) -> int:
        return await self.repository.count_active(
            user_id=user_id,
            workspace_context=workspace_context,
            include_global=include_global,
        )

    async def _finish(self, record: Any | None = None) -> None:
        if self.autocommit:
            await self.session.commit()
            if record is not None:
                await self.session.refresh(record)
            return
        await self.session.flush()
