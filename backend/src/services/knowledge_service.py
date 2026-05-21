"""Facade for DataService-owned user knowledge persistence."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.knowledge import (
    KnowledgeArchiveLowConfidencePayload,
    KnowledgeMemoryCreatePayload,
    KnowledgeMemoryUpdatePayload,
    normalize_knowledge_category,
)
from src.dataservice_client.provider import dataservice_client


class KnowledgeService:
    """Facade for user knowledge lifecycle through DataService."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        dataservice: AsyncDataServiceClient | None = None,
    ) -> None:
        self._db = db
        self.db = db
        self._dataservice = dataservice

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
        command = KnowledgeMemoryCreatePayload(
            user_id=user_id,
            category=self._normalize_category(category),
            content=content,
            confidence=confidence,
            source=source,
            workspace_context=workspace_context,
        )
        if self._dataservice is not None:
            return await self._dataservice.create_knowledge_memory(command)
        async with dataservice_client() as client:
            return await client.create_knowledge_memory(command)

    async def get(self, knowledge_id: str) -> Any | None:
        """Get knowledge by ID."""
        if self._dataservice is not None:
            return await self._dataservice.get_knowledge_memory(knowledge_id)
        async with dataservice_client() as client:
            return await client.get_knowledge_memory(knowledge_id)

    async def list_by_user(
        self,
        user_id: str,
        category: Any | None = None,
        min_confidence: float | None = None,
        active_only: bool = True,
    ) -> list[Any]:
        """List knowledge entries for a user."""
        normalized_category = self._normalize_category(category) if category is not None else None
        if self._dataservice is not None:
            return await self._dataservice.list_user_knowledge_memory(
                user_id=user_id,
                category=normalized_category,
                min_confidence=min_confidence,
                active_only=active_only,
            )
        async with dataservice_client() as client:
            return await client.list_user_knowledge_memory(
                user_id=user_id,
                category=normalized_category,
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
        command = KnowledgeMemoryUpdatePayload(
            content=content,
            confidence=confidence,
            is_active=is_active,
        )
        if self._dataservice is not None:
            return await self._dataservice.update_knowledge_memory(knowledge_id, command)
        async with dataservice_client() as client:
            return await client.update_knowledge_memory(knowledge_id, command)

    async def deactivate(self, knowledge_id: str) -> bool:
        """Deactivate a knowledge entry."""
        if self._dataservice is not None:
            return await self._dataservice.deactivate_knowledge_memory(knowledge_id)
        async with dataservice_client() as client:
            return await client.deactivate_knowledge_memory(knowledge_id)

    async def delete(self, knowledge_id: str) -> bool:
        """Delete a knowledge entry."""
        if self._dataservice is not None:
            return await self._dataservice.delete_knowledge_memory(knowledge_id)
        async with dataservice_client() as client:
            return await client.delete_knowledge_memory(knowledge_id)

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
        if self._dataservice is not None:
            return await self._dataservice.list_active_knowledge_memory(
                user_id=user_id,
                workspace_context=workspace_context,
                include_global=include_global,
                min_confidence=min_confidence,
                limit=limit,
            )
        async with dataservice_client() as client:
            return await client.list_active_knowledge_memory(
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
        command = KnowledgeMemoryCreatePayload(
            user_id=user_id,
            category=self._normalize_category(category),
            content=content,
            confidence=confidence,
            source=source,
            workspace_context=workspace_context,
        )
        if self._dataservice is not None:
            return await self._dataservice.upsert_knowledge_memory(command)
        async with dataservice_client() as client:
            return await client.upsert_knowledge_memory(command)

    async def archive_low_confidence(
        self,
        user_id: str,
        threshold: float = 0.5,
    ) -> int:
        """Deactivate entries below threshold. Returns count."""
        command = KnowledgeArchiveLowConfidencePayload(threshold=threshold)
        if self._dataservice is not None:
            return await self._dataservice.archive_low_confidence_knowledge_memory(
                user_id=user_id,
                command=command,
            )
        async with dataservice_client() as client:
            return await client.archive_low_confidence_knowledge_memory(
                user_id=user_id,
                command=command,
            )

    async def count_active(
        self,
        user_id: str,
        *,
        workspace_context: str | None = None,
        include_global: bool | None = None,
    ) -> int:
        """Count active knowledge entries for a user."""
        if self._dataservice is not None:
            return await self._dataservice.count_active_knowledge_memory(
                user_id=user_id,
                workspace_context=workspace_context,
                include_global=include_global,
            )
        async with dataservice_client() as client:
            return await client.count_active_knowledge_memory(
                user_id=user_id,
                workspace_context=workspace_context,
                include_global=include_global,
            )
