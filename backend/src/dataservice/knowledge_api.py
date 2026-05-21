"""Public in-process knowledge memory API for DataService."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.knowledge.service import DataServiceKnowledgeService

KNOWLEDGE_CATEGORIES = ("preference", "knowledge", "context", "behavior", "goal")
KNOWLEDGE_CATEGORY_PREFERENCE = "preference"
KNOWLEDGE_CATEGORY_CONTEXT = "context"


def normalize_knowledge_category(category: Any) -> str:
    """Normalize and validate a knowledge category without exposing ORM enums."""
    return DataServiceKnowledgeService.normalize_category(category)


class KnowledgeDataService:
    """Knowledge-memory API exposed by DataService to runtime modules."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self._domain = DataServiceKnowledgeService(session, autocommit=autocommit)

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
        return await self._domain.create(
            user_id=user_id,
            category=category,
            content=content,
            confidence=confidence,
            source=source,
            workspace_context=workspace_context,
        )

    async def get(self, knowledge_id: str) -> Any | None:
        return await self._domain.get(knowledge_id)

    async def list_by_user(
        self,
        *,
        user_id: str,
        category: Any | None = None,
        min_confidence: float | None = None,
        active_only: bool = True,
    ) -> list[Any]:
        return await self._domain.list_by_user(
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
        return await self._domain.update(
            knowledge_id=knowledge_id,
            content=content,
            confidence=confidence,
            is_active=is_active,
        )

    async def deactivate(self, knowledge_id: str) -> bool:
        return await self._domain.deactivate(knowledge_id)

    async def delete(self, knowledge_id: str) -> bool:
        return await self._domain.delete(knowledge_id)

    async def list_active(
        self,
        *,
        user_id: str,
        workspace_context: str | None = None,
        include_global: bool = True,
        min_confidence: float = 0.5,
        limit: int = 20,
    ) -> list[Any]:
        return await self._domain.list_active(
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
        return await self._domain.upsert(
            user_id=user_id,
            category=category,
            content=content,
            confidence=confidence,
            source=source,
            workspace_context=workspace_context,
        )

    async def archive_low_confidence(self, *, user_id: str, threshold: float = 0.5) -> int:
        return await self._domain.archive_low_confidence(
            user_id=user_id,
            threshold=threshold,
        )

    async def count_active(
        self,
        *,
        user_id: str,
        workspace_context: str | None = None,
        include_global: bool | None = None,
    ) -> int:
        return await self._domain.count_active(
            user_id=user_id,
            workspace_context=workspace_context,
            include_global=include_global,
        )
